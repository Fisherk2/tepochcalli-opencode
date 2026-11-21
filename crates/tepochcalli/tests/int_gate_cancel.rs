//! Hueco #6 — composición del gate cancelable (R-offline-2 / T16) bajo
//! `run_phase6`: la rama `None ⇒ Err(Internal)` de
//! `embedder_gate::run_gate_cancellable` y la purga de parciales en la
//! composición COMPLETA (hasta ahora la purga era un no-op observable en
//! todos los tests).
//!
//! Vaults `tempfile` reales (D26), sin proceso hijo y sin TTY: la UI es un
//! fake que decide QUÉ hace `run_cancellable` — comportamiento de UI, no
//! del producto.

// Shared fakes: this target reuses four of them.
#[allow(dead_code)]
mod common;

use std::cell::RefCell;
use std::collections::{HashMap, VecDeque};
use std::path::{Path, PathBuf};

use common::{host_16gb, FakeHost, FakeHttp, RecordingProc};
use tepochcalli::domain::{CancelToken, MenuAction, WizardError};
use tepochcalli::ports::{CommandOutput, CommandRunner, HttpClient, MenuView, Ui};
use tepochcalli::Phase6Deps;

/// Los dos valores del preset default de `presets.toml` (espejo de
/// `int_embedder_menu`): el snapshot del gate es `<slug>@<sha>`.
const MINILM: &str = "paraphrase-multilingual-MiniLM-L12-v2";
const MINILM_SHA: &str = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42";

fn tmp() -> tempfile::TempDir {
    tempfile::tempdir().expect("tempdir for gate-cancel fixtures")
}

/// Materializa el intérprete del venv: sin él `run_flow_cli` devuelve
/// `Internal` ANTES de tocar el `CommandRunner`, y el test mediría otra
/// cosa que la composición del gate.
fn create_venv_python(vault: &Path) {
    let python = vault
        .join(".tepochcalli")
        .join("venv")
        .join(if cfg!(windows) {
            "Scripts/python.exe"
        } else {
            "bin/python"
        });
    std::fs::create_dir_all(python.parent().expect("venv bin parent")).expect("venv fixture");
    std::fs::write(python, b"fake-python").expect("venv python fixture");
}

fn deps<'a>(
    ui: &'a dyn Ui,
    host: &'a FakeHost,
    proc: &'a dyn CommandRunner,
    http: &'a dyn HttpClient,
) -> Phase6Deps<'a> {
    Phase6Deps {
        ui,
        host,
        proc,
        http,
        cancel: CancelToken::new(),
    }
}

/// Qué hace la pantalla de descarga con `work`.
#[derive(Clone, Copy)]
enum Screen {
    /// `work()` en línea y DESPUÉS dispara el token: el usuario cancela
    /// cuando el hijo ya corrió (el escenario de R-offline-2).
    WorkThenCancel,
    /// Una UI que se rinde: nunca ejecuta `work` ⇒ el `outcome` del gate
    /// queda `None`.
    NeverRunWork,
}

/// `Ui` fake del gate: responde el menú por guion y ejecuta
/// `run_cancellable` según [`Screen`]. Sin terminal y sin estado que
/// comparta con otros tests.
struct GateUi {
    selects: RefCell<VecDeque<usize>>,
    screen: Screen,
}

impl GateUi {
    fn new(selects: Vec<usize>, screen: Screen) -> Self {
        Self {
            selects: RefCell::new(selects.into()),
            screen,
        }
    }
}

impl Ui for GateUi {
    fn select(
        &self,
        _prompt: &str,
        _options: &[&str],
        _default_index: usize,
    ) -> Result<usize, WizardError> {
        self.selects
            .borrow_mut()
            .pop_front()
            .ok_or(WizardError::UserAborted)
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

    fn run_cancellable(&self, _title: &str, cancel: &CancelToken, work: &mut dyn FnMut()) {
        match self.screen {
            Screen::WorkThenCancel => {
                work();
                cancel.cancel();
            }
            Screen::NeverRunWork => {}
        }
    }
}

/// `CommandRunner` fake que modela una descarga que YA empezó a escribir su
/// snapshot en `models/` y termina cancelada: crea el parcial ANTES de
/// devolver `UserAborted` (el estado que dejaría el hijo real a medias — es
/// exactamente lo que la purga de R-offline-2 existe para limpiar).
struct AbortingDownload {
    partial: PathBuf,
}

impl CommandRunner for AbortingDownload {
    fn run(
        &self,
        _program: &str,
        _args: &[&str],
        _cwd: &Path,
        _env: &[(&str, &str)],
    ) -> Result<CommandOutput, WizardError> {
        std::fs::create_dir_all(&self.partial).expect("partial dir fixture");
        std::fs::write(self.partial.join("config.json"), b"{}").expect("partial file fixture");
        Err(WizardError::UserAborted)
    }
}

/// Hueco #6(a) — rama `None ⇒ Err(Internal)`: una UI que nunca ejecuta
/// `work` deja el `outcome` sin llenar y el gate falla en RUIDO, nunca en
/// silencio (no hay gate que haya corrido y nada que purgar).
///
/// Regresión que detecta: si `embedder_gate.rs:64` cambiara el
/// `None => Err(WizardError::Internal)` por cualquier otro brazo (un
/// default `Ok`, un `UserAborted`, o dejar de hacer `match` sobre
/// `outcome`), el aserto sale en rojo. El `RecordingProc` vacío prueba que
/// no hubo hijo: el venv SÍ está materializado (su guarda pasaría), así que
/// si `work` se hubiera ejecutado habría un spawn registrado en su sitio.
#[test]
fn ui_que_no_ejecuta_work_falla_con_internal_sin_spawn() {
    let vault = tmp();
    create_venv_python(vault.path());
    let ui = GateUi::new(vec![0, 0], Screen::NeverRunWork);
    let host = host_16gb();
    let proc = RecordingProc::scripted([]);
    let http = FakeHttp::new(HashMap::new());

    let got = tepochcalli::run_phase6(&deps(&ui, &host, &proc, &http), vault.path());

    assert_eq!(
        got,
        Err(WizardError::Internal),
        "un outcome que nunca se llenó es un error interno, no un éxito"
    );
    assert!(
        proc.calls().is_empty(),
        "sin `work` no hay gate que lanzar: {:?}",
        proc.calls()
    );
    assert!(
        !tepochcalli::config_path(vault.path()).exists(),
        "no se escribe media config cuando el gate ni corrió"
    );
}

/// Hueco #6(b) — composición entera: el gate aborta y LA PURGA observa el
/// parcial que la descarga dejó a medias. El fake de proceso crea
/// `<models>/<slug>@<sha>/` antes de devolver `UserAborted` y la UI
/// dispara el token tras correr `work` («el usuario cancela al verse en
/// pantalla; el hijo ya empezó a escribir»).
///
/// Regresión que detecta: si desapareciera el `purge_partials` del brazo
/// `Some(Err(UserAborted))` (embedder_gate.rs:60), el parcial nuevo
/// sobreviviría y el primer aserto sale en rojo; si la purga borrara de más
/// (un snapshot previo legítimo), el segundo.
#[test]
fn gate_abortado_purga_el_parcial_y_conserva_el_modelo_previo() {
    let vault = tmp();
    create_venv_python(vault.path());
    // Un modelo ya cacheado antes de la corrida: la purga jamás lo toca.
    let prev = vault
        .path()
        .join(".tepochcalli")
        .join("models")
        .join("prev-model@sha");
    std::fs::create_dir_all(&prev).expect("prev model dir fixture");
    std::fs::write(prev.join("config.json"), b"{}").expect("prev model fixture");
    // El parcial de la descarga cancelada, con la fórmula real del snapshot.
    let partial = vault
        .path()
        .join(".tepochcalli")
        .join("models")
        .join(format!("{MINILM}@{MINILM_SHA}"));
    let ui = GateUi::new(vec![0, 0], Screen::WorkThenCancel);
    let host = host_16gb();
    let proc = AbortingDownload {
        partial: partial.clone(),
    };
    let http = FakeHttp::new(HashMap::new());

    let got = tepochcalli::run_phase6(&deps(&ui, &host, &proc, &http), vault.path());

    assert_eq!(
        got,
        Err(WizardError::UserAborted),
        "la cancelación se propaga tipada hasta F6"
    );
    assert!(
        !partial.exists(),
        "el parcial nacido durante la descarga cancelada se purga"
    );
    assert!(
        prev.join("config.json").is_file(),
        "un modelo previo legítimo sobrevive a la purga"
    );
}
