//! Codice invariant (ADR-011 / `InstallUseCaseBase.ts:59-105`): executables
//! live in the runner/cache root; the destination receives only data files
//! and relative links — no exec bit is ever needed inside the target.
//! In-process: fake asset + fake HTTP + recording proc, no subprocess.

mod common;

use std::collections::HashMap;
use std::io::Write as _;
use std::path::Path;

use common::helpers::sha256_hex;
use common::{FakeHttp, RecordingProc};
use tepochcalli::adapters::fetch::{self, UvAsset};
use tepochcalli::application::failure::state_dir_from;
use tepochcalli::application::installer::{run_phase4_with_state, UV_STAGE_DIR};
use tepochcalli::application::{is_phase_done, mark_phase_done};
use tepochcalli::domain::Phase;
use tepochcalli::ports::{CommandOutput, CommandRunner};
use tepochcalli::WizardError;

#[cfg(not(windows))]
const UV_BIN: &str = "uv";
#[cfg(windows)]
const UV_BIN: &str = "uv.exe";

fn tmp() -> tempfile::TempDir {
    let dir = tempfile::tempdir().expect("tempdir for uv-root fixture");
    // Keep fixtures private; the wizard also repairs a legacy 0755 root.
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt as _;
        std::fs::set_permissions(dir.path(), std::fs::Permissions::from_mode(0o700))
            .expect("private fixture");
    }
    dir
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
    let stages: Vec<String> = std::fs::read_dir(state.path())
        .expect("state dir readable")
        .flatten()
        .map(|entry| entry.file_name().to_string_lossy().into_owned())
        .filter(|name| name.starts_with(UV_STAGE_DIR))
        .collect();
    assert!(
        stages.is_empty(),
        "no per-invocation stage residue in the state root: {stages:?}"
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

/// Two installs of two different vaults share one state root at the same
/// time: `<state>/bin/uv` must end up complete (tmp → rename), and neither
/// vault's link may observe truncated bytes.
#[test]
fn concurrent_installs_share_the_state_root_without_truncation() {
    struct AlwaysOk;
    impl CommandRunner for AlwaysOk {
        fn run(
            &self,
            _program: &str,
            _args: &[&str],
            _cwd: &Path,
            _env: &[(&str, &str)],
        ) -> Result<CommandOutput, WizardError> {
            Ok(CommandOutput {
                status: 0,
                stdout: format!("uv {} (fake)\n", fetch::UV_VERSION),
                stderr: String::new(),
            })
        }
    }

    let body = uv_tar_gz(b"fake-uv-binary");
    let asset = UvAsset {
        os: "linux",
        arch: "x86_64",
        filename: "uv-concurrent-test.tar.gz",
        sha256_hex: Box::leak(sha256_hex(&body).into_boxed_str()),
    };
    let url = fetch::uv_download_url(&asset);
    let http = FakeHttp::new(HashMap::from([(url, body)]));
    let proc = AlwaysOk;
    let state = tmp();
    let vault_a = tmp();
    let vault_b = tmp();
    let barrier = std::sync::Barrier::new(2);

    let (a, b) = std::thread::scope(|scope| {
        let ha = scope.spawn(|| {
            barrier.wait();
            run_phase4_with_state(&http, &proc, vault_a.path(), &asset, state.path())
        });
        let hb = scope.spawn(|| {
            barrier.wait();
            run_phase4_with_state(&http, &proc, vault_b.path(), &asset, state.path())
        });
        (ha.join().expect("thread A"), hb.join().expect("thread B"))
    });

    let external = state.path().join("bin").join(UV_BIN);
    assert_eq!(
        std::fs::read(&external).expect("shared binary readable"),
        b"fake-uv-binary",
        "the shared executable must be complete, never truncated"
    );
    for report in [a.expect("install A"), b.expect("install B")] {
        assert_eq!(
            std::fs::read(&report.uv).expect("vault link resolves"),
            b"fake-uv-binary",
            "each vault link must resolve to the complete executable"
        );
    }
    let stages: Vec<String> = std::fs::read_dir(state.path())
        .expect("state dir readable")
        .flatten()
        .map(|entry| entry.file_name().to_string_lossy().into_owned())
        .filter(|name| name.starts_with(UV_STAGE_DIR))
        .collect();
    assert!(stages.is_empty(), "no stage residue: {stages:?}");
}

/// The pure fallback decision: no env mutation needed to pin it.
#[test]
fn state_dir_from_prefers_xdg_then_home_then_private_tmp() {
    let tmp = Path::new("/tmp-fixture");
    let home = Path::new("/home/u");
    let xdg = Path::new("/state/u");
    assert_eq!(
        state_dir_from(Some(home), Some(xdg), tmp),
        xdg.join("tepochcalli")
    );
    #[cfg(not(windows))]
    assert_eq!(
        state_dir_from(Some(home), None, tmp),
        home.join(".local/state/tepochcalli")
    );
    assert_eq!(
        state_dir_from(None, None, tmp),
        tmp.join(format!("tepochcalli-{}", std::process::id())),
        "the tmp fallback is per process, never a shared bare `tepochcalli`"
    );
}

/// A legacy beta.1 state dir is `0755`: F4 must repair it to `0700` and
/// proceed, never reject it (every upgrading user would be locked out).
#[cfg(unix)]
#[test]
fn legacy_0755_state_root_is_repaired_to_0700() {
    use std::os::unix::fs::PermissionsExt as _;

    let body = uv_tar_gz(b"fake-uv-binary");
    let asset = UvAsset {
        os: "linux",
        arch: "x86_64",
        filename: "uv-repair-test.tar.gz",
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
    std::fs::set_permissions(state.path(), std::fs::Permissions::from_mode(0o755))
        .expect("legacy 0755 fixture");

    run_phase4_with_state(&http, &proc, vault.path(), &asset, state.path())
        .expect("a legacy 0755 state root must be repaired, not rejected");

    let mode = std::fs::symlink_metadata(state.path())
        .expect("state root metadata")
        .permissions()
        .mode()
        & 0o777;
    assert_eq!(mode, 0o700, "the legacy state root must end up 0700");
}

/// The repair never follows a link: a symlinked state root is refused.
#[cfg(unix)]
#[test]
fn symlinked_state_root_is_rejected() {
    let body = uv_tar_gz(b"fake-uv-binary");
    let asset = UvAsset {
        os: "linux",
        arch: "x86_64",
        filename: "uv-symlink-test.tar.gz",
        sha256_hex: Box::leak(sha256_hex(&body).into_boxed_str()),
    };
    let url = fetch::uv_download_url(&asset);
    let http = FakeHttp::new(HashMap::from([(url, body)]));
    let proc = RecordingProc::scripted([Ok(CommandOutput {
        status: 0,
        stdout: format!("uv {} (fake)\n", fetch::UV_VERSION),
        stderr: String::new(),
    })]);
    let real = tmp();
    let holder = tmp();
    let link = holder.path().join("state");
    std::os::unix::fs::symlink(real.path(), &link).expect("state symlink");
    let vault = tmp();

    let err = run_phase4_with_state(&http, &proc, vault.path(), &asset, &link)
        .expect_err("a symlinked state root must be refused");
    assert_eq!(err, WizardError::PermissionDenied);
}

/// A link whose target vanished is not a done F4: `--resume` must re-run.
#[cfg(unix)]
#[test]
fn dangling_link_is_not_a_done_phase() {
    let vault = tmp();
    let bin = vault.path().join(".tepochcalli").join("bin");
    std::fs::create_dir_all(&bin).expect("bin fixture");
    std::os::unix::fs::symlink("/nonexistent/uv", bin.join(UV_BIN)).expect("dangling link");
    mark_phase_done(vault.path(), Phase::F4);
    assert!(
        !is_phase_done(vault.path(), Phase::F4),
        "a dangling link must force F4 to re-run, never skip"
    );
}
