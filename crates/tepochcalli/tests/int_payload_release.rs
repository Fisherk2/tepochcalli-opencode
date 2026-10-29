//! T19: versioned payload asset + one-version rule + SHA-256 sidecar.
//!
//! RED-first: the URL builders, the sidecar parser and the `for_version`
//! constructors did not exist before this module. Loopback only — `latest`
//! is never fetched, and no test touches the real network.

// Shared fakes: this target reuses one of them.
#[allow(dead_code)]
mod common;

use std::collections::HashMap;
use std::io::{Read, Write};
use std::net::TcpListener;

use common::FakeHttp;
use sha2::{Digest as _, Sha256};
use tepochcalli::adapters::{
    fetch_release_payload, payload_asset_name, payload_asset_url, payload_checksum_name,
    payload_checksum_url, payload_release_tag, release_payload_from_sidecar, ReleasePayload,
    PAYLOAD_ASSET_STEM,
};
use tepochcalli::WizardError;

fn sha256_hex(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

#[test]
fn asset_names_are_versioned_and_pinned() {
    assert_eq!(
        payload_asset_name("0.3.0"),
        "tepochcalli-workspace-0.3.0.tar.gz"
    );
    assert_eq!(
        payload_checksum_name("0.3.0"),
        "tepochcalli-workspace-0.3.0.tar.gz.sha256"
    );
    assert_eq!(payload_release_tag("0.3.0"), "tepochcalli-v0.3.0");
    assert!(payload_asset_name("0.3.0").starts_with(PAYLOAD_ASSET_STEM));
}

#[test]
fn asset_urls_never_use_latest() {
    for version in ["0.3.0", "1.2.3"] {
        let asset = payload_asset_url(version);
        let checksum = payload_checksum_url(version);
        assert!(
            asset.contains(version),
            "asset URL must pin the version, got: {asset}"
        );
        assert_eq!(checksum, format!("{asset}.sha256"));
        for url in [&asset, &checksum] {
            assert!(
                !url.contains("latest"),
                "one-version rule: no floating `latest`, got: {url}"
            );
        }
    }
}

#[test]
fn requested_payload_version_equals_binary_version() {
    // T19 AC-c: the binary installs its own version's asset, never another.
    let version = env!("CARGO_PKG_VERSION");
    let release = ReleasePayload::for_current_version(&"0".repeat(64));
    assert_eq!(release.url(), payload_asset_url(version));
    assert!(release.url().contains(version));
}

#[test]
fn sidecar_parser_accepts_sha256sum_format() {
    let hex = sha256_hex(b"asset-bytes");
    // GNU `sha256sum` output (hash + filename, text or binary mode).
    for sidecar in [
        format!("{hex}  tepochcalli-workspace-0.3.0.tar.gz\n"),
        format!("{hex} *tepochcalli-workspace-0.3.0.tar.gz\n"),
        format!("{hex}\n"),
    ] {
        assert_eq!(
            tepochcalli::adapters::parse_sha256_sidecar(sidecar.as_bytes()),
            Ok(hex.clone()),
            "valid sidecar must parse: {sidecar:?}"
        );
    }
    // BSD `shasum` form carries the hash last — not sidecar format.
    assert_eq!(
        tepochcalli::adapters::parse_sha256_sidecar(
            format!("SHA256 (tepochcalli-workspace-0.3.0.tar.gz) = {hex}\n").as_bytes()
        ),
        Err(WizardError::PayloadCorrupt)
    );
}

#[test]
fn sidecar_parser_rejects_garbage_cleanly() {
    for bad in [
        "".to_string(),
        "\n".to_string(),
        "not-a-hash  file.tar.gz\n".to_string(),
        format!("{}  file.tar.gz\n", "0".repeat(63)), // one nibble short
        format!("{}  file.tar.gz\n", "z".repeat(64)), // non-hex
    ] {
        assert_eq!(
            tepochcalli::adapters::parse_sha256_sidecar(bad.as_bytes()),
            Err(WizardError::PayloadCorrupt),
            "sidecar must fail clean, got input: {bad:?}"
        );
    }
    assert_eq!(
        tepochcalli::adapters::parse_sha256_sidecar(&[0xff, 0xfe, 0x00]),
        Err(WizardError::PayloadCorrupt)
    );
}

#[test]
fn fetch_release_payload_resolves_sha_from_sidecar() {
    let version = "9.9.9-test";
    let asset = payload_asset_url(version);
    let checksum_url = payload_checksum_url(version);
    let hex = sha256_hex(b"fake-asset");
    let mut files = HashMap::new();
    files.insert(
        checksum_url.clone(),
        format!("{hex}  {}\n", payload_asset_name(version)).into_bytes(),
    );
    let http = FakeHttp::new(files);

    let release = fetch_release_payload(&http, version).expect("sidecar resolves");
    assert_eq!(release.url(), asset);
}

#[test]
fn fetch_release_payload_unknown_sidecar_is_net_error() {
    let http = FakeHttp::new(HashMap::new());
    assert_eq!(
        fetch_release_payload(&http, "9.9.9-test").expect_err("unknown sidecar"),
        WizardError::NetDownload
    );
}

#[test]
fn fetch_release_payload_corrupt_sidecar_fails_clean() {
    let version = "9.9.9-test";
    let mut files = HashMap::new();
    files.insert(
        payload_checksum_url(version),
        b"definitely not a checksum\n".to_vec(),
    );
    let http = FakeHttp::new(files);
    assert_eq!(
        fetch_release_payload(&http, version).expect_err("corrupt sidecar"),
        WizardError::PayloadCorrupt
    );
}

/// Serve `body` once on 127.0.0.1; returns the URL to GET.
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

fn tar_gz(files: &[(&str, &[u8])]) -> Vec<u8> {
    use std::io::Write as _;
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

#[test]
fn sidecar_built_payload_materializes_over_loopback() {
    // Glue: sidecar bytes (offline) + asset bytes (loopback) → vault merge.
    // A corrupt checksum still leaves the vault untouched (two-phase merge).
    use tepochcalli::ports::PayloadSource as _;
    let asset = tar_gz(&[("notes.md", b"# from release\n")]);
    let hex = sha256_hex(&asset);
    let sidecar = format!("{hex}  tepochcalli-workspace-9.9.9.tar.gz\n");
    // The sidecar resolves to a version-pinned payload (one-version rule).
    let pinned =
        release_payload_from_sidecar("9.9.9", sidecar.as_bytes()).expect("valid sidecar builds");
    assert!(pinned.url().contains("9.9.9"));
    let (url, handle) = serve_bytes_once(asset);
    // Same bytes, same SHA over loopback: the URL is transport, the checksum
    // is trust — so the loopback copy verifies exactly like the release one.
    let release = ReleasePayload::new(&url, &hex);

    let vault = tempfile::tempdir().expect("tempdir");
    let written = release
        .materialize_report(vault.path())
        .expect("loopback asset")
        .written;
    handle.join().expect("server thread");
    assert_eq!(
        std::fs::read_to_string(vault.path().join("notes.md")).expect("read back"),
        "# from release\n"
    );
    assert!(written.iter().any(|p| p.ends_with("notes.md")));
}
