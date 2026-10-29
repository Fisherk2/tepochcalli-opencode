//! F3 payload merge + `00-Resources/` + placeholders (T8).
//!
//! RED-first: every behavior here failed before `adapters::payload` and
//! `installer::run_phase3` existed. Real `tempfile` vaults (D26: no FS
//! port); loopback HTTP only — never the internet.

use std::io::{Read, Write};
use std::net::TcpListener;
use std::path::Path;

use sha2::{Digest as _, Sha256};
use tepochcalli::adapters::{LocalPayload, ReleasePayload};
use tepochcalli::application::installer::run_phase3;
use tepochcalli::ports::PayloadSource;
use tepochcalli::WizardError;

fn tmp() -> tempfile::TempDir {
    tempfile::tempdir().expect("tempdir for T8 fixtures")
}

fn write(path: &Path, body: &str) {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).expect("fixture parents");
    }
    std::fs::write(path, body).expect("fixture write");
}

/// Fake payload tree: `a.md` collides with the user's file, `b.md` and
/// `sub/c.md` are new, `.obsidian/` must never cross the merge.
fn payload_tree(base: &Path) {
    write(&base.join("a.md"), "# payload version\n");
    write(&base.join("b.md"), "# fresh file\n");
    write(&base.join("sub").join("c.md"), "# nested fresh file\n");
    write(
        &base.join(".obsidian").join("app.json"),
        "{\"payload\":true}",
    );
}

fn intent_lines(vault: &Path) -> Vec<String> {
    let intent = vault.join(".tepochcalli").join(".install-intent");
    let body = std::fs::read_to_string(&intent).expect("intent must exist after F3");
    let mut lines: Vec<String> = body.lines().map(str::to_string).collect();
    lines.sort();
    lines
}

#[test]
fn merge_copies_new_files_and_leaves_user_files_intact() {
    let payload = tmp();
    payload_tree(payload.path());
    let vault = tmp();
    write(
        &vault.path().join("a.md"),
        "# USER version — do not touch\n",
    );

    let report =
        run_phase3(&LocalPayload::new(payload.path()), vault.path()).expect("F3 must succeed");

    // The user's file is byte-intact and recorded as skipped, never written.
    assert_eq!(
        std::fs::read_to_string(vault.path().join("a.md")).expect("read back"),
        "# USER version — do not touch\n"
    );
    assert!(
        report.skipped.iter().any(|p| p.ends_with("a.md")),
        "a.md must be reported skipped, got: {:?}",
        report.skipped
    );
    assert!(
        !report.written.iter().any(|p| p.ends_with("a.md")),
        "a.md must not be reported written"
    );
    // Fresh files land with payload contents.
    assert_eq!(
        std::fs::read_to_string(vault.path().join("b.md")).expect("read back"),
        "# fresh file\n"
    );
    assert_eq!(
        std::fs::read_to_string(vault.path().join("sub").join("c.md")).expect("read back"),
        "# nested fresh file\n"
    );
    // Intent lists exactly the written files (payload + placeholders).
    let mut expected = vec![
        "00-Resources/ejemplo.md".to_string(),
        "00-Resources/ejemplo.pdf".to_string(),
        "b.md".to_string(),
        "sub/c.md".to_string(),
    ];
    expected.sort();
    assert_eq!(intent_lines(vault.path()), expected);
}

#[test]
fn merge_never_touches_obsidian() {
    let payload = tmp();
    payload_tree(payload.path());
    let vault = tmp();
    write(
        &vault.path().join(".obsidian").join("app.json"),
        "{\"user\":true}",
    );

    let report =
        run_phase3(&LocalPayload::new(payload.path()), vault.path()).expect("F3 must succeed");

    assert_eq!(
        std::fs::read_to_string(vault.path().join(".obsidian").join("app.json"))
            .expect("read back"),
        "{\"user\":true}",
        "user .obsidian must survive F3"
    );
    assert!(
        !report
            .written
            .iter()
            .any(|p| p.components().any(|c| c.as_os_str() == ".obsidian")),
        ".obsidian must never be written, got: {:?}",
        report.written
    );
    assert!(
        !vault.path().join(".obsidian").join("app.json").exists()
            || std::fs::read_to_string(vault.path().join(".obsidian").join("app.json"))
                .expect("read back")
                == "{\"user\":true}",
        "payload .obsidian must not overwrite the user's"
    );
}

#[cfg(unix)]
#[test]
fn merge_skips_symlinks_without_following_them() {
    use std::os::unix::fs::symlink;

    let payload = tmp();
    payload_tree(payload.path());
    // A hostile payload symlink pointing outside the tree.
    let outside = tmp();
    let sentinel = outside.path().join("secret.txt");
    write(&sentinel, "outside-secret");
    symlink(&sentinel, payload.path().join("evil-link")).expect("fixture symlink");

    let vault = tmp();
    let report = run_phase3(&LocalPayload::new(payload.path()), vault.path())
        .expect("F3 must succeed despite the symlink");

    // The link is skipped (never materialized, never followed into the vault).
    assert!(
        report.skipped.iter().any(|p| p.ends_with("evil-link")),
        "symlink must be reported skipped, got: {:?}",
        report.skipped
    );
    assert!(
        !vault.path().join("evil-link").exists()
            && std::fs::symlink_metadata(vault.path().join("evil-link")).is_err(),
        "symlink must not land in the vault"
    );
    assert_eq!(
        std::fs::read_to_string(&sentinel).expect("read back"),
        "outside-secret",
        "outside file untouched"
    );
}

#[test]
fn placeholders_use_exact_resources_case_and_no_phase5_dirs() {
    let payload = tmp();
    payload_tree(payload.path());
    let vault = tmp();

    run_phase3(&LocalPayload::new(payload.path()), vault.path()).expect("F3 must succeed");

    // Exact case the flow indexes (`citation.py: RESOURCES_DIR = "00-Resources"`).
    assert!(vault.path().join("00-Resources").is_dir());
    assert!(vault
        .path()
        .join("00-Resources")
        .join("ejemplo.md")
        .is_file());
    assert!(vault
        .path()
        .join("00-Resources")
        .join("ejemplo.pdf")
        .is_file());
    // Phase 5 owns the agent trays — F3 must not create them (TD-8).
    for tray in ["02-drafts", "03-citations", "04-review", "05-outputs"] {
        assert!(
            !vault.path().join(tray).exists(),
            "{tray} is Phase 5 scope, F3 must not create it"
        );
    }
}

#[test]
fn existing_placeholders_are_not_overwritten() {
    let payload = tmp();
    payload_tree(payload.path());
    let vault = tmp();
    write(
        &vault.path().join("00-Resources").join("ejemplo.md"),
        "# mine\n",
    );

    let report =
        run_phase3(&LocalPayload::new(payload.path()), vault.path()).expect("F3 must succeed");

    assert_eq!(
        std::fs::read_to_string(vault.path().join("00-Resources").join("ejemplo.md"))
            .expect("read back"),
        "# mine\n",
        "user placeholder wins over the wizard default"
    );
    assert!(
        report.skipped.iter().any(|p| p.ends_with("ejemplo.md")),
        "pre-existing placeholder must be skipped, got: {:?}",
        report.skipped
    );
}

/// Minimal structural check: `%PDF` header, `%%EOF` trailer, and every
/// `xref` offset pointing at a real `N G obj` header.
fn assert_pdf_structure(bytes: &[u8]) {
    assert!(
        bytes.starts_with(b"%PDF-"),
        "placeholder must start with %PDF-"
    );
    let text = std::str::from_utf8(bytes).expect("placeholder PDF is ASCII");
    assert!(
        text.trim_end().ends_with("%%EOF"),
        "placeholder must end with %%EOF"
    );
    let xref_at = text
        .find("\nxref\n")
        .expect("placeholder must have an xref table");
    let trailer_at = text[xref_at..]
        .find("\ntrailer")
        .expect("placeholder must have a trailer");
    for line in text[xref_at + "\nxref\n".len()..xref_at + trailer_at]
        .lines()
        .skip(1)
    // subsection header (`0 N`)
    {
        let mut parts = line.split_whitespace();
        let offset: usize = parts
            .next()
            .expect("offset")
            .parse()
            .expect("numeric offset");
        let rest: Vec<&str> = parts.collect();
        if rest == ["65535", "f"] {
            assert_eq!(offset, 0, "the only free entry must be object 0");
            continue;
        }
        assert_eq!(
            rest,
            ["00000", "n"],
            "free entries unsupported in placeholder"
        );
        assert!(
            bytes.len() > offset,
            "xref offset {offset} escapes the file"
        );
        let obj_head = std::str::from_utf8(&bytes[offset..]).expect("ASCII at offset");
        assert!(
            obj_head.contains(" 0 obj"),
            "offset {offset} must open an object, got: {}",
            &obj_head[..obj_head.find('\n').unwrap_or(32).min(obj_head.len())]
        );
    }
}

#[test]
fn placeholder_pdf_is_structurally_valid() {
    let payload = tmp();
    payload_tree(payload.path());
    let vault = tmp();

    run_phase3(&LocalPayload::new(payload.path()), vault.path()).expect("F3 must succeed");

    let bytes = std::fs::read(vault.path().join("00-Resources").join("ejemplo.pdf"))
        .expect("placeholder PDF must exist");
    assert_pdf_structure(&bytes);
}

// --- `ReleasePayload` over loopback (mirrors `tests/adapters.rs`) ---

fn tar_gz(files: &[(&str, &[u8])]) -> Vec<u8> {
    let mut tar_buf = Vec::new();
    {
        let mut builder = tar::Builder::new(&mut tar_buf);
        for (name, body) in files {
            let mut header = tar::Header::new_gnu();
            header.set_size(body.len() as u64);
            header.set_mode(0o644);
            header.set_cksum();
            builder
                .append_data(&mut header, name, *body)
                .expect("tar fixture");
        }
        builder.into_inner().expect("finish tar");
    }
    let mut encoder = flate2::write::GzEncoder::new(Vec::new(), flate2::Compression::default());
    encoder.write_all(&tar_buf).expect("gzip fixture");
    encoder.finish().expect("finish gzip")
}

fn serve_bytes_once(body: Vec<u8>) -> (String, std::thread::JoinHandle<()>) {
    let listener = TcpListener::bind("127.0.0.1:0").expect("bind loopback");
    let port = listener.local_addr().expect("local addr").port();
    let handle = std::thread::spawn(move || {
        let (mut stream, _) = listener.accept().expect("accept one conn");
        let mut buf = vec![0u8; 8192];
        let _ = stream.read(&mut buf);
        let header = format!(
            "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
            body.len()
        );
        stream.write_all(header.as_bytes()).expect("write header");
        stream.write_all(&body).expect("write body");
    });
    (format!("http://127.0.0.1:{port}/asset"), handle)
}

fn sha256_hex(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

/// Raw tar builder: the `tar` crate refuses to *write* `..` names (like the
/// extractor refuses to read them), so the traversal fixture is hand-packed
/// — 512-byte USTAR headers with computed checksums, data padded to 512.
fn raw_tar(files: &[(&str, &[u8])]) -> Vec<u8> {
    fn octal(value: usize, width: usize) -> Vec<u8> {
        let mut field = format!("{value:o}").into_bytes();
        while field.len() < width {
            field.insert(0, b'0');
        }
        field
    }

    let mut out = Vec::new();
    for (name, body) in files {
        assert!(name.len() <= 100, "fixture names fit the USTAR field");
        let mut header = vec![0u8; 512];
        header[..name.len()].copy_from_slice(name.as_bytes());
        header[100..108].copy_from_slice(&[b'0'; 8]); // mode (fixed later)
        header[100..107].copy_from_slice(b"0000644");
        header[124..136].copy_from_slice(b"00000000000\0"); // size placeholder
        let size = octal(body.len(), 11);
        header[124..135].copy_from_slice(&size);
        header[156] = b'0'; // regular file
        header[257..262].copy_from_slice(b"ustar");
        header[263..265].copy_from_slice(b"00");
        header[148..156].copy_from_slice(b"        "); // checksum field = spaces
        let sum: usize = header.iter().map(|b| *b as usize).sum();
        let mut cksum = octal(sum, 6);
        cksum.push(0);
        cksum.push(b' ');
        header[148..156].copy_from_slice(&cksum);
        out.extend_from_slice(&header);
        out.extend_from_slice(body);
        while out.len() % 512 != 0 {
            out.push(0);
        }
    }
    out.extend_from_slice(&[0u8; 1024]); // end-of-archive markers
    let mut encoder = flate2::write::GzEncoder::new(Vec::new(), flate2::Compression::default());
    encoder.write_all(&out).expect("gzip fixture");
    encoder.finish().expect("finish gzip")
}

#[test]
fn release_payload_materializes_over_loopback() {
    let asset = tar_gz(&[("notes.md", b"# from release\n")]);
    let (url, handle) = serve_bytes_once(asset.clone());
    let release = ReleasePayload::new(&url, &sha256_hex(&asset));

    let vault = tmp();
    let written = release
        .materialize_report(vault.path())
        .expect("loopback asset")
        .written;

    handle.join().expect("server thread");
    assert_eq!(
        std::fs::read_to_string(vault.path().join("notes.md")).expect("read back"),
        "# from release\n"
    );
    assert!(
        written.iter().any(|p| p.ends_with("notes.md")),
        "written must list the asset file, got: {written:?}"
    );
}

#[test]
fn release_payload_corrupt_sha_leaves_dest_intact() {
    let asset = tar_gz(&[("notes.md", b"# from release\n")]);
    let (url, handle) = serve_bytes_once(asset);
    let release = ReleasePayload::new(&url, &"0".repeat(64));

    let vault = tmp();
    let err = release
        .materialize_report(vault.path())
        .expect_err("SHA mismatch must fail typed");

    handle.join().expect("server thread");
    assert_eq!(err, WizardError::PayloadCorrupt);
    assert!(
        std::fs::read_dir(vault.path())
            .expect("read dest")
            .next()
            .is_none(),
        "a corrupt asset must leave the vault untouched"
    );
}

#[test]
fn release_payload_rejects_traversal_member() {
    // Hand-packed: the `tar` builder API refuses to write `..` names.
    let asset = raw_tar(&[("../evil.md", b"escape\n"), ("ok.md", b"fine\n")]);
    let (url, handle) = serve_bytes_once(asset.clone());
    let release = ReleasePayload::new(&url, &sha256_hex(&asset));

    let vault = tmp();
    let err = release
        .materialize_report(vault.path())
        .expect_err("traversal member must fail typed");

    handle.join().expect("server thread");
    assert_eq!(err, WizardError::PayloadCorrupt);
    assert!(
        !vault.path().join("ok.md").exists(),
        "rejection happens before any write (two-phase extract)"
    );
}

#[test]
fn install_help_mentions_payload_flag() {
    let out = std::process::Command::new(env!("CARGO_BIN_EXE_tepochcalli"))
        .args(["install", "--help"])
        .output()
        .expect("spawn install --help");
    assert_eq!(out.status.code(), Some(0));
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(
        stdout.contains("--payload"),
        "install --help must document --payload, got:\n{stdout}"
    );
}

#[test]
fn install_without_payload_offline_fails_clean_before_touch() {
    // T19: no `--payload` means the versioned release asset (network). Under
    // `--offline` with no local payload there is nothing to install from, so
    // the guard fails with `E_OFFLINE_NO_CACHE` (exit 21) BEFORE the vault is
    // touched — never a half-written tree, never a network attempt.
    let dir = tmp();
    let target = dir.path().join("vault-no-payload");
    let out = std::process::Command::new(env!("CARGO_BIN_EXE_tepochcalli"))
        .args([
            "install",
            "--non-interactive",
            "--offline",
            "--vault",
            target.to_str().expect("utf8 tmp"),
        ])
        .output()
        .expect("spawn install");
    assert_eq!(
        out.status.code(),
        Some(i32::from(WizardError::OfflineNoCache.exit_code())),
        "stderr:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(
        stderr.contains("offline"),
        "the failure must name the offline cause, got:\n{stderr}"
    );
    assert!(
        !target.exists(),
        "the offline guard runs before F2: no vault dir may exist"
    );
}

#[test]
fn install_payload_flag_conflicts_with_url_override() {
    // Usage error (exit 2), decided before any I/O or network.
    let dir = tmp();
    let out = std::process::Command::new(env!("CARGO_BIN_EXE_tepochcalli"))
        .args([
            "install",
            "--non-interactive",
            "--vault",
            dir.path().join("v").to_str().expect("utf8 tmp"),
            "--payload",
            dir.path().to_str().expect("utf8 tmp"),
            "--payload-url",
            "http://127.0.0.1:9/asset.tar.gz",
            "--payload-sha256",
            &"0".repeat(64),
        ])
        .output()
        .expect("spawn install");
    assert_eq!(out.status.code(), Some(2));
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(
        stderr.contains("--payload"),
        "the failure must name the conflict, got:\n{stderr}"
    );
}

#[test]
fn install_half_url_override_is_usage_error() {
    // `--payload-url` without `--payload-sha256` (and vice versa) is exit 2
    // before any network: a URL without a checksum is never fetched.
    for extra in [
        vec!["--payload-url", "http://127.0.0.1:9/asset.tar.gz"],
        vec!["--payload-sha256", &"0".repeat(64)],
    ] {
        let dir = tmp();
        let mut cmd = std::process::Command::new(env!("CARGO_BIN_EXE_tepochcalli"));
        cmd.args([
            "install",
            "--non-interactive",
            "--vault",
            dir.path().join("v").to_str().expect("utf8 tmp"),
        ]);
        cmd.args(extra);
        let out = cmd.output().expect("spawn install");
        assert_eq!(out.status.code(), Some(2));
        let stderr = String::from_utf8_lossy(&out.stderr);
        assert!(
            stderr.contains("--payload-sha256") || stderr.contains("--payload-url"),
            "the failure must name the missing half, got:\n{stderr}"
        );
    }
}
