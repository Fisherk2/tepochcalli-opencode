//! F1 prereqs + F2 vault dir (T7): `FakeHost` fixtures, real `tempfile`
//! vaults, `ScriptedUi` answers, plus one real-binary smoke test.
//!
//! F1/F2 never touch user data, so they have no compensation (todo T7).

// Shared fakes: this target only needs three of them.
#[allow(dead_code)]
mod common;

use std::path::Path;

use common::{FakeHost, FakeUiScript, ScriptedUi};
use tepochcalli::application::installer::{
    check_prereqs_on, ensure_vault_dir, is_supported_os, resolve_vault_dir, tool_present_in,
};
use tepochcalli::WizardError;

fn host(ram_gb: f64, disk_gb: f64) -> FakeHost {
    FakeHost::new(Some(ram_gb), Some(ram_gb), Some(disk_gb), None)
}

fn tmp() -> tempfile::TempDir {
    tempfile::tempdir().expect("tempdir for T7 fixtures")
}

#[test]
fn ram_4gb_aborts_with_code_10() {
    let dir = tmp();
    let err = check_prereqs_on(&host(4.0, 100.0), "linux", dir.path(), &[])
        .expect_err("4 GB RAM must abort the install");
    assert_eq!(err, WizardError::PrereqRam);
    assert_eq!(err.exit_code(), 10);
}

#[test]
fn ram_16gb_passes_prereqs() {
    let dir = tmp();
    let report = check_prereqs_on(&host(16.0, 100.0), "linux", dir.path(), &[])
        .expect("16 GB RAM must pass F1");
    assert_eq!(report.os, "linux");
}

#[test]
fn insufficient_disk_aborts_with_code_11() {
    let dir = tmp();
    let err = check_prereqs_on(&host(16.0, 2.5), "linux", dir.path(), &[])
        .expect_err("2.5 GB free disk must abort the install");
    assert_eq!(err, WizardError::PrereqDisk);
    assert_eq!(err.exit_code(), 11);
}

#[test]
fn unsupported_platform_aborts_with_code_12() {
    let dir = tmp();
    for os in ["freebsd", "plan9", ""] {
        let err = check_prereqs_on(&host(16.0, 100.0), os, dir.path(), &[])
            .expect_err("unknown OS must abort the install");
        assert_eq!(err, WizardError::PrereqPlatform, "os={os}");
        assert_eq!(err.exit_code(), 12, "os={os}");
    }
}

#[test]
fn supported_platforms_pass() {
    let dir = tmp();
    for os in ["linux", "macos", "windows"] {
        assert!(is_supported_os(os), "os={os}");
        check_prereqs_on(&host(16.0, 100.0), os, dir.path(), &[])
            .expect("supported OS must pass F1");
    }
    assert!(!is_supported_os("freebsd"));
}

#[test]
fn missing_optional_tools_never_fail_prereqs() {
    // `obsidian`/`opencode` detection is best-effort: absence only warns.
    let dir = tmp();
    check_prereqs_on(&host(16.0, 100.0), "linux", dir.path(), &[])
        .expect("missing optional tools must not fail F1");
}

#[test]
fn tool_lookup_scans_given_dirs() {
    let dir = tmp();
    let found = dir.path().join("obsidian");
    std::fs::write(&found, "#!/bin/sh\n").expect("fixture tool");
    let dirs = vec![
        Path::new("/nonexistent-t7").to_path_buf(),
        dir.path().to_path_buf(),
    ];
    assert!(tool_present_in("obsidian", &dirs));
    assert!(!tool_present_in("opencode", &dirs));
}

#[test]
fn vault_flag_creates_missing_dir() {
    let dir = tmp();
    let target = dir.path().join("tepochcalli-vault");
    assert!(!target.exists());
    let ui = ScriptedUi::new(FakeUiScript::default());
    let raw = resolve_vault_dir(&ui, Some(target.to_str().expect("utf8 tmp")))
        .expect("--vault must win without prompting");
    assert_eq!(raw, target.to_str().expect("utf8 tmp"));
    let vault = ensure_vault_dir(Path::new(&raw)).expect("missing dir must be created");
    assert!(vault.as_path().is_dir());
}

#[test]
fn existing_vault_dir_is_reused_without_deleting() {
    let dir = tmp();
    let sentinel = dir.path().join("notes.md");
    std::fs::write(&sentinel, "# keep me\n").expect("sentinel");
    let before = std::fs::read_to_string(&sentinel).expect("sentinel readable");

    let first = ensure_vault_dir(dir.path()).expect("existing dir must be reused");
    let second = ensure_vault_dir(dir.path()).expect("second run must be idempotent");
    assert_eq!(first, second);
    assert_eq!(
        std::fs::read_to_string(&sentinel).expect("sentinel readable"),
        before,
        "F2 must never delete user content"
    );
}

#[test]
fn vault_without_flag_asks_ui_with_sensible_default() {
    let ui = ScriptedUi::new(FakeUiScript {
        inputs: ["my-vault".to_string()].into(),
        ..FakeUiScript::default()
    });
    let raw = resolve_vault_dir(&ui, None).expect("Ui answer must be honored");
    assert_eq!(raw, "my-vault");

    // Blank flag behaves like no flag: ask the Ui instead of guessing.
    let ui = ScriptedUi::new(FakeUiScript {
        inputs: ["fallback".to_string()].into(),
        ..FakeUiScript::default()
    });
    let raw = resolve_vault_dir(&ui, Some("   ")).expect("blank flag must prompt");
    assert_eq!(raw, "fallback");
}

#[test]
fn vault_path_through_file_fails_typed() {
    let dir = tmp();
    let file = dir.path().join("not-a-dir");
    std::fs::write(&file, "x").expect("fixture file");
    ensure_vault_dir(&file).expect_err("a file is not a vault dir");
    assert!(
        std::fs::read_to_string(&file).is_ok(),
        "probe must not delete"
    );
}

/// Fixture shared by both real-binary install tests: an empty payload tree
/// (F3 still writes the placeholders + intent, T8) and a missing vault dir.
fn install_fixture() -> (tempfile::TempDir, std::path::PathBuf, std::path::PathBuf) {
    let dir = tmp();
    let target = dir.path().join("tepochcalli-vault");
    let payload = dir.path().join("payload");
    std::fs::create_dir_all(&payload).expect("payload fixture dir");
    (dir, target, payload)
}

/// The install command with the network forced down: `ureq` reads the proxy
/// from the environment (`ALL_PROXY`/`HTTPS_PROXY`), and the port below is a
/// bound-then-dropped loopback listener, so the F4 `uv` download dies at the
/// proxy connect — no DNS and no real network involved, deterministic offline
/// or online.
fn forced_offline_install(target: &Path, payload: &Path) -> std::process::Command {
    let port = std::net::TcpListener::bind("127.0.0.1:0")
        .expect("bind a port to close")
        .local_addr()
        .expect("loopback addr")
        .port();
    let dead = format!("http://127.0.0.1:{port}");
    let mut cmd = std::process::Command::new(env!("CARGO_BIN_EXE_tepochcalli"));
    cmd.args([
        "install",
        "--non-interactive",
        "--vault",
        target.to_str().expect("utf8 tmp"),
        "--payload",
        payload.to_str().expect("utf8 tmp"),
    ])
    .env("ALL_PROXY", &dead)
    .env("HTTPS_PROXY", &dead)
    .env_remove("NO_PROXY")
    .env_remove("no_proxy");
    cmd
}

/// F4 always downloads the pinned `uv` (`installer.rs:413`), so a blocked
/// network must be reported as the network failure — never as a full disk —
/// and must compensate `bin/`.
#[test]
fn install_offline_fails_at_f4_with_a_network_error() {
    let (_dir, target, payload) = install_fixture();
    let out = forced_offline_install(&target, &payload)
        .output()
        .expect("spawn install");
    let stderr = String::from_utf8_lossy(&out.stderr);
    // The documented code for `WizardError::NetDownload` (20-29 network range).
    assert_eq!(
        out.status.code(),
        Some(i32::from(WizardError::NetDownload.exit_code())),
        "stderr:\n{stderr}"
    );
    assert!(
        stderr.contains("install: phase F4 failed") && stderr.contains("download failed"),
        "the failure must name F4 and the network cause, got:\n{stderr}"
    );
    for wrong in ["disk", "espacio"] {
        assert!(
            !stderr.to_lowercase().contains(wrong),
            "a blocked network must not be diagnosed as {wrong:?}, got:\n{stderr}"
        );
    }
    // F1-F3 ran before the download failed...
    assert!(target.is_dir(), "F2 must create the vault dir for real");
    assert!(
        target
            .join(".tepochcalli")
            .join(".install-intent")
            .is_file(),
        "F3 must have written the intent file before F4"
    );
    // ...and F4 compensated what it wrote.
    assert!(
        !target.join(".tepochcalli").join("bin").exists(),
        "failed F4 must compensate bin/"
    );
}

/// T9: install runs F1→F2→F3→F4→F5 for real. The empty fixture payload
/// carries no pyproject.toml/uv.lock, so the real F5 `uv sync --frozen`
/// fails AFTER F1–F4 succeeded (F4 proves the pinned download, the
/// executable bit and `uv --version`); F5 compensates `venv/`.
#[test]
#[ignore = "needs network: F4 downloads uv and F5 a managed CPython"]
fn install_non_interactive_vault_runs_f1_f2_for_real() {
    let (_dir, target, payload) = install_fixture();
    let out = std::process::Command::new(env!("CARGO_BIN_EXE_tepochcalli"))
        .args([
            "install",
            "--non-interactive",
            "--vault",
            target.to_str().expect("utf8 tmp"),
            "--payload",
            payload.to_str().expect("utf8 tmp"),
        ])
        .output()
        .expect("spawn install");
    assert_eq!(
        out.status.code(),
        Some(42),
        "stderr:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(target.is_dir(), "F2 must create the vault dir for real");
    assert!(
        target.join("00-Resources").join("ejemplo.md").is_file(),
        "F3 must leave the markdown placeholder"
    );
    assert!(
        target
            .join(".tepochcalli")
            .join(".install-intent")
            .is_file(),
        "F3 must write the intent file"
    );
    assert!(
        target.join(".tepochcalli").join("bin").join("uv").is_file()
            || target
                .join(".tepochcalli")
                .join("bin")
                .join("uv.exe")
                .is_file(),
        "F4 must leave the bootstrapped uv behind"
    );
    assert!(
        !target.join(".tepochcalli").join("venv").exists(),
        "failed F5 must compensate venv/"
    );
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(
        stderr.contains("phase F5 failed"),
        "the failure must name F5, got:\n{stderr}"
    );
}
