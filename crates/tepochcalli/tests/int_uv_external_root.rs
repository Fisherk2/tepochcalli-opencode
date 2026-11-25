//! Codice invariant (ADR-011 / `InstallUseCaseBase.ts:59-105`): executables
//! live in the runner/cache root; the destination receives only data files
//! and relative links — no exec bit is ever needed inside the target.
//! In-process: fake asset + fake HTTP + recording proc, no subprocess.

mod common;

use std::collections::HashMap;
use std::io::Write as _;

use common::helpers::sha256_hex;
use common::{FakeHttp, RecordingProc};
use tepochcalli::adapters::fetch::{self, UvAsset};
use tepochcalli::application::installer::run_phase4_with_state;
use tepochcalli::ports::CommandOutput;

#[cfg(not(windows))]
const UV_BIN: &str = "uv";
#[cfg(windows)]
const UV_BIN: &str = "uv.exe";

fn tmp() -> tempfile::TempDir {
    tempfile::tempdir().expect("tempdir for uv-root fixture")
}

/// Minimal `.tar.gz` with a single `uv` member (same shape as the real asset).
fn uv_tar_gz(body: &[u8]) -> Vec<u8> {
    let mut tar_buf = Vec::new();
    {
        let mut builder = tar::Builder::new(&mut tar_buf);
        let mut header = tar::Header::new_gnu();
        header.set_size(body.len() as u64);
        header.set_mode(0o755);
        header.set_cksum();
        builder
            .append_data(&mut header, UV_BIN, body)
            .expect("tar fixture");
        builder.into_inner().expect("finish tar");
    }
    let mut encoder = flate2::write::GzEncoder::new(Vec::new(), flate2::Compression::default());
    encoder.write_all(&tar_buf).expect("gzip fixture");
    encoder.finish().expect("finish gzip")
}

#[test]
fn uv_bytes_and_exec_bits_live_outside_the_vault() {
    let body = uv_tar_gz(b"fake-uv-binary");
    let asset = UvAsset {
        os: "linux",
        arch: "x86_64",
        filename: "uv-external-test.tar.gz",
        sha256_hex: Box::leak(sha256_hex(&body).into_boxed_str()),
    };
    let url = fetch::uv_download_url(&asset);
    let http = FakeHttp::new(HashMap::from([(url, body)]));
    let proc = RecordingProc::scripted([Ok(CommandOutput {
        status: 0,
        stdout: format!("uv {} (fake)\n", fetch::UV_VERSION),
        stderr: String::new(),
    })]);

    let vault = tmp();
    let state = tmp();
    let log = state.path().join("install-1.log");
    std::fs::write(&log, "failure log").expect("state log fixture");

    let report = run_phase4_with_state(&http, &proc, vault.path(), &asset, state.path())
        .expect("F4 must succeed");
    let link = vault.path().join(".tepochcalli").join("bin").join(UV_BIN);
    let external = state.path().join("bin").join(UV_BIN);
    assert_eq!(report.uv, link, "the report stays vault-based");

    #[cfg(unix)]
    {
        let meta = std::fs::symlink_metadata(&link).expect("vault uv symlink metadata");
        assert!(meta.file_type().is_symlink(), "the vault holds only a link");
        assert_eq!(
            std::fs::read_link(&link).expect("vault uv link target"),
            external,
            "the link points at the external state root"
        );
        use std::os::unix::fs::PermissionsExt as _;
        let mode = std::fs::metadata(&external)
            .expect("external uv metadata")
            .permissions()
            .mode();
        assert!(mode & 0o111 != 0, "the external binary must be executable");
    }
    #[cfg(windows)]
    {
        assert!(
            !std::fs::symlink_metadata(&link)
                .expect("vault uv metadata")
                .file_type()
                .is_symlink(),
            "Windows keeps a direct .exe copy (no symlink privilege)"
        );
    }

    assert_eq!(
        std::fs::read(&external).expect("external bytes"),
        b"fake-uv-binary"
    );
    assert_eq!(
        std::fs::read(&link).expect("bytes resolve through the vault entry"),
        b"fake-uv-binary"
    );
    assert!(
        !state.path().join(".uv-stage").exists(),
        "no download stage residue in the state root"
    );
    assert_eq!(
        std::fs::read_to_string(&log).expect("state log survives F4"),
        "failure log"
    );

    let calls = proc.calls();
    assert_eq!(calls.len(), 1, "only the version check runs in F4");
    assert_eq!(
        calls[0].program,
        external.to_str().expect("utf8 temp path"),
        "`uv --version` must execute the external binary"
    );
    assert_eq!(calls[0].args, ["--version"]);
    assert_eq!(calls[0].cwd, vault.path(), "cwd stays the vault");
}
