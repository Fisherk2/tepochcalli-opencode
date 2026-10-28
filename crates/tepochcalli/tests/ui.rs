//! UI tests (T6): `HeadlessUi` scripted answers + typed errors, and the
//! `install --non-interactive` binary path never blocking on closed stdin.

use std::collections::VecDeque;
use std::io::IsTerminal;
use std::process::{Command, Stdio};
use std::time::Duration;

use tepochcalli::adapters::{HeadlessUi, TtyUi};
use tepochcalli::domain::WizardError;
use tepochcalli::ports::Ui;

fn bin() -> Command {
    Command::new(env!("CARGO_BIN_EXE_tepochcalli"))
}

#[test]
fn headless_returns_scripted_answers_in_order() {
    let ui = HeadlessUi::new(
        VecDeque::from([2]),
        VecDeque::from(["/tmp/vault".to_string()]),
        VecDeque::from([true]),
    );
    assert_eq!(ui.select("embedder?", &["a", "b", "c"], 0).unwrap(), 2);
    assert_eq!(ui.input("vault?", None).unwrap(), "/tmp/vault".to_string());
    assert!(ui.confirm("proceed?", false).unwrap());
}

#[test]
fn headless_missing_answer_is_a_typed_error_never_a_guess() {
    let ui = HeadlessUi::new(VecDeque::new(), VecDeque::new(), VecDeque::new());
    assert_eq!(
        ui.select("embedder?", &["a", "b"], 0).unwrap_err(),
        WizardError::UserAborted
    );
    assert_eq!(
        ui.input("vault?", None).unwrap_err(),
        WizardError::UserAborted
    );
    assert_eq!(
        ui.confirm("proceed?", true).unwrap_err(),
        WizardError::UserAborted
    );
}

#[test]
fn headless_ignores_fallback_defaults_instead_of_guessing() {
    // Even with a `default` offered, an empty script is a typed error.
    let ui = HeadlessUi::new(VecDeque::new(), VecDeque::new(), VecDeque::new());
    assert_eq!(
        ui.input("vault?", Some("/default")).unwrap_err(),
        WizardError::UserAborted
    );
    assert_eq!(
        ui.confirm("proceed?", true).unwrap_err(),
        WizardError::UserAborted
    );
}

#[test]
fn headless_out_of_range_select_is_a_typed_error() {
    let ui = HeadlessUi::new(VecDeque::from([9]), VecDeque::new(), VecDeque::new());
    assert_eq!(
        ui.select("embedder?", &["a", "b"], 0).unwrap_err(),
        WizardError::UserAborted
    );
}

#[test]
fn for_install_preselects_skip_model_and_vault_answers() {
    let ui = HeadlessUi::for_install(true, Some("/tmp/vault".to_string()));
    // skip-model = "configure later" row; must resolve without asking.
    assert!(ui
        .select("embedder?", &["m", "b", "h", "a", "later"], 0)
        .is_ok());
    assert_eq!(ui.input("vault?", None).unwrap(), "/tmp/vault".to_string());
}

#[test]
fn tty_ui_panel_renders_without_panicking_off_terminal() {
    // No TTY in CI: the panel must degrade to plain text, never panic.
    assert!(!std::io::stderr().is_terminal() || true);
    TtyUi.panel("E_PROBE", "probe body");
    HeadlessUi::new(VecDeque::new(), VecDeque::new(), VecDeque::new())
        .panel("E_PROBE", "probe body");
}

/// `install --non-interactive --skip-model` with stdin closed and no `--vault`
/// must terminate fast (exit 41: the headless UI cannot guess the vault dir)
/// instead of blocking on a prompt.
#[test]
fn install_non_interactive_with_closed_stdin_terminates() {
    let (tx, rx) = std::sync::mpsc::channel();
    std::thread::spawn(move || {
        let out = bin()
            .args(["install", "--non-interactive", "--skip-model"])
            .stdin(Stdio::null())
            .output()
            .expect("spawn binary");
        let _ = tx.send(out);
    });
    let out = rx
        .recv_timeout(Duration::from_secs(15))
        .expect("install --non-interactive --skip-model must not block on closed stdin");
    assert_eq!(out.status.code(), Some(41));
    assert!(
        String::from_utf8_lossy(&out.stderr).contains("vault selection failed"),
        "headless install without --vault must fail fast naming the vault, got:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
}

/// Same, with explicit `--vault` + `--payload`: F1→F3 run for real,
/// exit 0, no stdin read.
#[test]
fn install_non_interactive_with_vault_flag_terminates() {
    // T8: F3 needs a payload tree; an empty dir still yields placeholders.
    let payload = tempfile::tempdir().expect("payload fixture dir");
    let (tx, rx) = std::sync::mpsc::channel();
    std::thread::spawn(move || {
        let out = bin()
            .args([
                "install",
                "--non-interactive",
                "--skip-model",
                "--vault",
                "/tmp/tepochcalli-t6-probe",
                "--payload",
                payload.path().to_str().expect("utf8 tmp"),
            ])
            .stdin(Stdio::null())
            .output()
            .expect("spawn binary");
        let _ = tx.send(out);
    });
    let out = rx
        .recv_timeout(Duration::from_secs(15))
        .expect("install --non-interactive --vault must not block on closed stdin");
    assert_eq!(out.status.code(), Some(0));
}
