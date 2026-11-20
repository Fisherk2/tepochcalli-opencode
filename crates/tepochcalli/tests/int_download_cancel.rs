//! R-offline-2: la cancelación de una descarga de modelo en curso.
//!
//! DESVIACIÓN del plan (hecho verificado): el modelo NO lo descarga `ureq`;
//! lo descarga el subproceso `venv python -m tepochcalli_flow embed-check`.
//! Por eso la unidad cancelable es el HIJO (`CommandRunner::run_cancellable`
//! lo mata), no un stream HTTP: aquí no hay servidor loopback que sirva el
//! modelo. El `sleep 30` del test hace de doble de una descarga larga.

use std::cell::Cell;
use std::path::Path;
use std::time::{Duration, Instant};

use tepochcalli::adapters::StdCommandRunner;
use tepochcalli::domain::{CancelToken, WizardError};
use tepochcalli::ports::{CommandOutput, CommandRunner};

/// Fake que solo implementa `run`: así ejercita el DEFAULT del port (la
/// comprobación previa del token), no una sobreescritura.
struct CountingProc {
    calls: Cell<usize>,
}

impl CommandRunner for CountingProc {
    fn run(
        &self,
        _program: &str,
        _args: &[&str],
        _cwd: &Path,
        _env: &[(&str, &str)],
    ) -> Result<CommandOutput, WizardError> {
        self.calls.set(self.calls.get() + 1);
        Ok(CommandOutput {
            status: 0,
            stdout: String::new(),
            stderr: String::new(),
        })
    }
}

/// Token ya disparado ⇒ `UserAborted` sin spawn (default del port).
#[test]
fn token_ya_disparado_aborta_sin_spawn() {
    let Ok(cwd) = tempfile::tempdir() else {
        panic!("tempdir");
    };
    let proc = CountingProc {
        calls: Cell::new(0),
    };
    let token = CancelToken::new();
    token.cancel();
    let got = proc.run_cancellable("true", &[], cwd.path(), &[], Duration::from_secs(5), &token);
    assert_eq!(got, Err(WizardError::UserAborted));
    assert_eq!(
        proc.calls.get(),
        0,
        "un token disparado no llega a spawnear"
    );
}

/// Un token VIVO no cambia nada: el hijo corre y su salida vuelve intacta.
#[cfg(unix)]
#[test]
fn token_vivo_no_cambia_el_resultado() {
    let Ok(cwd) = tempfile::tempdir() else {
        panic!("tempdir");
    };
    let token = CancelToken::new();
    let got = StdCommandRunner.run_cancellable(
        "true",
        &[],
        cwd.path(),
        &[],
        Duration::from_secs(5),
        &token,
    );
    assert_eq!(got.map(|out| out.status), Ok(0));
    assert!(!token.is_cancelled());
}

/// Cancelar a mitad mata al hijo: `UserAborted` y sin esperar el plazo de 30 s.
#[cfg(unix)]
#[test]
fn cancelar_mata_el_hijo() {
    let Ok(cwd) = tempfile::tempdir() else {
        panic!("tempdir");
    };
    // Un modelo ya cacheado: matar al hijo NO lo toca (solo la purga del
    // gate, en la capa de aplicación, borra los parciales de la descarga).
    let old = cwd.path().join("models").join("old@sha");
    if let Err(err) = std::fs::create_dir_all(&old) {
        panic!("mkdir old: {err}");
    }
    let token = CancelToken::new();
    let arm = token.clone();
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_millis(200));
        arm.cancel();
    });
    let started = Instant::now();
    let got = StdCommandRunner.run_cancellable(
        "sleep",
        &["30"],
        cwd.path(),
        &[],
        Duration::from_secs(30),
        &token,
    );
    let elapsed = started.elapsed();
    assert_eq!(got, Err(WizardError::UserAborted));
    assert!(
        elapsed < Duration::from_secs(5),
        "el kill corta la espera, no el plazo: {elapsed:?}"
    );
    assert!(old.is_dir(), "cancelar no borra un modelo previo");
}
