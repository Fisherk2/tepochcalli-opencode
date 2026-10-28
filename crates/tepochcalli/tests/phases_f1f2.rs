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
    let err = check_prereqs_on(&host(4.0, 100.0), "linux", dir.path())
        .expect_err("4 GB RAM must abort the install");
    assert_eq!(err, WizardError::PrereqRam);
    assert_eq!(err.exit_code(), 10);
}

#[test]
fn ram_16gb_passes_prereqs() {
    let dir = tmp();
    let report =
        check_prereqs_on(&host(16.0, 100.0), "linux", dir.path()).expect("16 GB RAM must pass F1");
    assert_eq!(report.os, "linux");
}

#[test]
fn insufficient_disk_aborts_with_code_11() {
    let dir = tmp();
    let err = check_prereqs_on(&host(16.0, 2.5), "linux", dir.path())
        .expect_err("2.5 GB free disk must abort the install");
    assert_eq!(err, WizardError::PrereqDisk);
    assert_eq!(err.exit_code(), 11);
}

#[test]
fn unsupported_platform_aborts_with_code_12() {
    let dir = tmp();
    for os in ["freebsd", "plan9", ""] {
        let err = check_prereqs_on(&host(16.0, 100.0), os, dir.path())
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
        check_prereqs_on(&host(16.0, 100.0), os, dir.path()).expect("supported OS must pass F1");
    }
    assert!(!is_supported_os("freebsd"));
}

#[test]
fn missing_optional_tools_never_fail_prereqs() {
    // `obsidian`/`opencode` detection is best-effort: absence only warns.
    let dir = tmp();
    check_prereqs_on(&host(16.0, 100.0), "linux", dir.path())
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

#[test]
fn install_non_interactive_vault_runs_f1_f2_for_real() {
    let dir = tmp();
    let target = dir.path().join("tepochcalli-vault");
    let out = std::process::Command::new(env!("CARGO_BIN_EXE_tepochcalli"))
        .args([
            "install",
            "--non-interactive",
            "--vault",
            target.to_str().expect("utf8 tmp"),
        ])
        .output()
        .expect("spawn install");
    assert_eq!(
        out.status.code(),
        Some(0),
        "stderr:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(target.is_dir(), "F2 must create the vault dir for real");
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(
        stdout.contains(target.to_str().expect("utf8 tmp")),
        "vault path goes to stdout, got:\n{stdout}"
    );
}
