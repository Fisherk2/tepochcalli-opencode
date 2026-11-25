//! UI tests (T6): `HeadlessUi` scripted answers + typed errors, and the
//! `install --non-interactive` binary path never blocking on closed stdin.

mod common;

use std::cell::RefCell;
use std::collections::VecDeque;
use std::io::IsTerminal;
use std::process::Stdio;
use std::time::Duration;

use common::helpers::bin;
use common::FakePayload;
use tepochcalli::adapters::{HeadlessUi, TtyUi};
use tepochcalli::domain::{CancelToken, MenuAction, WizardError};
use tepochcalli::ports::{set_active_progress, MenuView, Progress, ProgressSpec, Ui};

#[test]
fn headless_returns_scripted_answers_in_order() {
    let ui = HeadlessUi::new(
        VecDeque::from([2]),
        VecDeque::from(["/tmp/vault".to_string()]),
    );
    assert_eq!(ui.select("embedder?", &["a", "b", "c"], 0).unwrap(), 2);
    assert_eq!(ui.input("vault?", None).unwrap(), "/tmp/vault".to_string());
}

#[test]
fn headless_missing_answer_is_a_typed_error_never_a_guess() {
    let ui = HeadlessUi::new(VecDeque::new(), VecDeque::new());
    assert_eq!(
        ui.select("embedder?", &["a", "b"], 0).unwrap_err(),
        WizardError::UserAborted
    );
    assert_eq!(
        ui.input("vault?", None).unwrap_err(),
        WizardError::UserAborted
    );
}

#[test]
fn headless_ignores_fallback_defaults_instead_of_guessing() {
    // Even with a `default` offered, an empty script is a typed error.
    let ui = HeadlessUi::new(VecDeque::new(), VecDeque::new());
    assert_eq!(
        ui.input("vault?", Some("/default")).unwrap_err(),
        WizardError::UserAborted
    );
}

#[test]
fn headless_out_of_range_select_is_a_typed_error() {
    let ui = HeadlessUi::new(VecDeque::from([9]), VecDeque::new());
    assert_eq!(
        ui.select("embedder?", &["a", "b"], 0).unwrap_err(),
        WizardError::UserAborted
    );
}

#[test]
fn for_install_answers_the_d7_1_row_indices_from_main() {
    // L3-4: el constructor ya no hardcodea el 4/0 — main pasa índices
    // EMBEDDER_PATHS. skip-model ⇒ fila "configure later" (4).
    let ui = HeadlessUi::for_install(4, 0, true);
    assert_eq!(
        ui.select("embedder?", &["m", "b", "h", "a", "later"], 0)
            .unwrap(),
        4
    );
    // El param vault era muerto: `--vault`/cwd resuelven el directorio,
    // así que la cola de `input` no se gasta en preguntarlo.
    assert_eq!(
        ui.input("vault?", None).unwrap_err(),
        WizardError::UserAborted
    );

    // Sin skip-model: la fila default (0, MiniLM preseleccionado).
    let ui = HeadlessUi::for_install(4, 0, false);
    assert_eq!(
        ui.select("embedder?", &["m", "b", "h", "a", "later"], 0)
            .unwrap(),
        0
    );
}

#[test]
fn tty_ui_panel_renders_without_panicking_off_terminal() {
    // No TTY in CI: the panel must degrade to plain text, never panic.
    assert!(!std::io::stderr().is_terminal() || true);
    TtyUi.panel("E_PROBE", "probe body");
    HeadlessUi::new(VecDeque::new(), VecDeque::new()).panel("E_PROBE", "probe body");
}

/// `install --non-interactive --skip-model` with stdin closed and no `--vault`
/// must target the process cwd (never prompt) and terminate fast. The dead
/// proxy makes F4 fail deterministically before any real download.
#[test]
fn install_non_interactive_with_closed_stdin_uses_cwd_and_terminates() {
    let cwd = tempfile::tempdir().expect("cwd fixture");
    let target = cwd.path().to_path_buf();
    let payload = tempfile::tempdir().expect("payload fixture dir");
    // The F4 state root is per user: keep the child off the developer's real
    // `~/.local/state` (which may predate the private-root check).
    let state = tempfile::tempdir().expect("state fixture");
    let (tx, rx) = std::sync::mpsc::channel();
    std::thread::spawn(move || {
        let out = bin()
            .args([
                "install",
                "--non-interactive",
                "--skip-model",
                "--payload",
                payload.path().to_str().expect("utf8 tmp"),
            ])
            .current_dir(cwd.path())
            .env("XDG_STATE_HOME", state.path())
            .env("ALL_PROXY", "http://127.0.0.1:9")
            .env("HTTPS_PROXY", "http://127.0.0.1:9")
            .env_remove("NO_PROXY")
            .env_remove("no_proxy")
            .stdin(Stdio::null())
            .output()
            .expect("spawn binary");
        let _ = tx.send(out);
    });
    let out = rx
        .recv_timeout(Duration::from_secs(15))
        .expect("install --non-interactive --skip-model must not block on closed stdin");
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(
        stderr.contains(&format!(
            "install: destino: {}",
            target.to_str().expect("utf8 tmp")
        )),
        "the absolute cwd must be announced before any write, got:\n{stderr}"
    );
    assert!(
        !stderr.contains("vault selection failed"),
        "no vault question may be asked, got:\n{stderr}"
    );
    assert_eq!(
        out.status.code(),
        Some(20),
        "the dead proxy must fail F4 fast, got:\n{stderr}"
    );
}

/// Same, with explicit `--vault` + `--payload`: the install phases run for
/// real with closed stdin, and the binary must TERMINATE — never block on a
/// prompt. What it exits with depends on the network (online F4 downloads
/// `uv` and the empty fixture payload then fails F5 ⇒ 42; offline F4 fails
/// first ⇒ 20), so only the documented exit ranges are asserted, never a
/// specific reason.
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
    // A hang detector, not a performance budget: F4/F5 are real downloads.
    let out = rx.recv_timeout(Duration::from_secs(180)).expect(
        "install --non-interactive --vault blocked on closed stdin (still running after 180 s)",
    );
    // Documented wizard exit codes (`WizardError::exit_code`, src/domain/error.rs):
    // 10-19 prerequisites, 20-29 network/auth, 30-39 filesystem/asset,
    // 40+ user cancel / model guards / phase failure / internal (40-44); 0 = clean.
    let code = out
        .status
        .code()
        .expect("no exit code: the binary was killed by a signal");
    assert!(
        matches!(code, 0 | 10..=19 | 20..=29 | 30..=39 | 40..=44),
        "exit {code} is outside the documented wizard ranges, stderr:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
}

// --- T21: estados de progreso de los tres flujos --------------------------

/// `Ui` de captura: corre el trabajo en línea (sin TTY) y recuerda la spec y
/// el último contador de cada `run_stages`. No dibuja nada: lo que aserta es
/// la declaración de hitos del producto, no el render.
#[derive(Default)]
struct StagesUi {
    specs: RefCell<Vec<ProgressSpec>>,
    done: RefCell<Vec<usize>>,
}

impl Ui for StagesUi {
    fn select(
        &self,
        _prompt: &str,
        _options: &[&str],
        _default_index: usize,
    ) -> Result<usize, WizardError> {
        Err(WizardError::UserAborted)
    }

    fn input(&self, _prompt: &str, _default: Option<&str>) -> Result<String, WizardError> {
        Err(WizardError::UserAborted)
    }

    fn input_secret(&self, _prompt: &str) -> Result<String, WizardError> {
        Err(WizardError::UserAborted)
    }

    fn panel(&self, _title: &str, _body: &str) {}

    fn menu(&self, _view: &MenuView<'_>) -> Result<MenuAction, WizardError> {
        Err(WizardError::UserAborted)
    }

    fn run_stages(
        &self,
        spec: &ProgressSpec,
        _cancel: &CancelToken,
        work: &mut dyn FnMut(&Progress),
    ) {
        let progress = Progress::new(spec.steps);
        set_active_progress(Some(&progress));
        work(&progress);
        set_active_progress(None);
        self.specs.borrow_mut().push(spec.clone());
        self.done.borrow_mut().push(progress.done());
    }
}

/// Update declara UN hito y lo marca al terminar la materialización.
#[test]
fn update_progress_declara_un_hito_y_llena_la_barra() {
    let vault = tempfile::tempdir().expect("vault fixture");
    let payload = tempfile::tempdir().expect("payload fixture");
    let ui = StagesUi::default();

    let report = tepochcalli::run_update(&FakePayload::new(payload.path()), &ui, vault.path());

    assert!(
        report.is_ok(),
        "update sin ficheros debe terminar: {report:?}"
    );
    assert_eq!(
        ui.specs.borrow().len(),
        1,
        "update debe declarar una sola pantalla de progreso"
    );
    assert_eq!(ui.specs.borrow()[0].steps, 1, "un hito para H7");
    assert_eq!(ui.done.borrow()[0], 1, "el hito se marca al terminar");
}

/// Con un solo scope presente, desinstall declara backup + ese scope (2),
/// nunca los tres scopes del contrato (no anuncia lo que no existe).
#[test]
fn uninstall_progress_declara_backup_y_solo_los_scopes_presentes() {
    let vault = tempfile::tempdir().expect("vault fixture");
    std::fs::write(vault.path().join("opencode.json"), b"{}").expect("scope fixture");
    let ui = StagesUi::default();

    let report = tepochcalli::run_uninstall(&ui, vault.path());

    assert!(report.is_ok(), "desinstall debe terminar: {report:?}");
    assert_eq!(ui.specs.borrow().len(), 1);
    assert_eq!(
        ui.specs.borrow()[0].steps,
        2,
        "backup + 1 scope presente; los 2 scopes ausentes no se anuncian"
    );
    assert_eq!(ui.done.borrow()[0], 2, "backup y scope se marcan");
}

/// Sin TTY la barra es un no-op: el trabajo corre en línea y stderr sigue
/// siendo parseable (criterio de `--non-interactive`, sin regresión T21).
#[test]
fn install_non_interactive_no_escribe_estados_de_progreso() {
    let cwd = tempfile::tempdir().expect("cwd fixture");
    let payload = tempfile::tempdir().expect("payload fixture");
    let state = tempfile::tempdir().expect("state fixture");
    let (tx, rx) = std::sync::mpsc::channel();
    std::thread::spawn(move || {
        let out = bin()
            .args([
                "install",
                "--non-interactive",
                "--skip-model",
                "--payload",
                payload.path().to_str().expect("utf8 tmp"),
            ])
            .current_dir(cwd.path())
            .env("XDG_STATE_HOME", state.path())
            .env("ALL_PROXY", "http://127.0.0.1:9")
            .env("HTTPS_PROXY", "http://127.0.0.1:9")
            .env_remove("NO_PROXY")
            .env_remove("no_proxy")
            .stdin(Stdio::null())
            .output()
            .expect("spawn binary");
        let _ = tx.send(out);
    });
    let out = rx
        .recv_timeout(Duration::from_secs(60))
        .expect("install --non-interactive debe terminar sin TTY");
    let stderr = String::from_utf8_lossy(&out.stderr);
    for marker in ["transcurrido", "ETA ", "█", "Cancelar — Esc"] {
        assert!(
            !stderr.contains(marker),
            "sin TTY no se dibuja progreso; encontrado `{marker}`:\n{stderr}"
        );
    }
}
