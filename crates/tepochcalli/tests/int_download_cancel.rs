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

/// Hueco #5(a) — pre-spawn del `StdCommandRunner` REAL con token disparado:
/// `UserAborted` sin llegar a `spawn()`.
///
/// Regresión que detecta: si desapareciera la comprobación previa del token
/// de `run_inner` (la línea ANTES de `spawn`), el runner intentaría lanzar
/// `/nonexistent/probe`, `spawn()` fallaría y el resultado sería
/// `Err(PhaseFailed)` — nunca `UserAborted` —, así que el aserto sale en
/// rojo. Por eso el programa es INEXISTENTE: es la única forma DETERMINISTA
/// de demostrar que no se spawneó. Un `sleep 30` con el token ya disparado
/// tampoco discriminaría: si se spawneara, el watcher lo mataría a los
/// 50 ms y devolvería `UserAborted` igualmente.
#[test]
fn token_disparado_no_llega_a_spawnear_en_el_runner_real() {
    let Ok(cwd) = tempfile::tempdir() else {
        panic!("tempdir");
    };
    let token = CancelToken::new();
    token.cancel();
    let got = StdCommandRunner.run_cancellable(
        "/nonexistent/probe",
        &["--never-spawned"],
        cwd.path(),
        &[],
        Duration::from_secs(5),
        &token,
    );
    assert_eq!(
        got,
        Err(WizardError::UserAborted),
        "sin spawn: la cancelación se decide ANTES de lanzar el hijo"
    );
}

/// Hueco #5(b) — con `cancel: Some` pero token VIVO, el PLAZO manda: un
/// hijo largo se mata con `Err(PhaseFailed)` (timeout), jamás como
/// cancelación.
///
/// Regresión que detecta: si el brazo de timeout de `run_inner` devolviera
/// `UserAborted` cuando hay token (o si el watcher confundiera el plazo con
/// una cancelación), el aserto sale en rojo. El suelo de 150 ms prueba que
/// el fallo vino del plazo de 200 ms y el techo de 2 s que el kill cortó la
/// espera de los 30 s del hijo.
#[cfg(unix)]
#[test]
fn el_plazo_manda_sobre_un_token_vivo() {
    let Ok(cwd) = tempfile::tempdir() else {
        panic!("tempdir");
    };
    let token = CancelToken::new();
    let started = Instant::now();
    let got = StdCommandRunner.run_cancellable(
        "sleep",
        &["30"],
        cwd.path(),
        &[],
        Duration::from_millis(200),
        &token,
    );
    let elapsed = started.elapsed();
    assert_eq!(
        got,
        Err(WizardError::PhaseFailed),
        "un plazo vencido es PhaseFailed, no una cancelación que nadie pidió"
    );
    assert!(
        elapsed >= Duration::from_millis(150),
        "el fallo debe venir del plazo, no de un cierre prematuro: {elapsed:?}"
    );
    assert!(
        elapsed < Duration::from_secs(2),
        "el plazo de 200 ms mata al hijo de 30 s: {elapsed:?}"
    );
    assert!(
        !token.is_cancelled(),
        "el timeout no dispara el token: son dos señales distintas"
    );
}

/// Hueco #5(c) — hijo VIVO en el primer tick de 50 ms + cancelación
/// concurrente: el watcher mira el token ANTES de `try_wait`, mata al hijo
/// y devuelve `UserAborted` sin pánico ni esperar el plazo de 5 s.
///
/// Límite declarado (auditoría): el caso «hijo YA muerto + `kill` sobre
/// él» NO es determinista —depende de la carrera entre la muerte del hijo y
/// el tick de 50 ms— y no se inventa un test flake. Aquí el hijo
/// `sleep 30` sigue vivo en el primer tick y la cancelación llega a los
/// 30 ms, ANTES de ese tick.
///
/// Regresión que detecta: si el watcher dejara de mirar el token (o solo lo
/// mirara tras agotar el plazo), el resultado sería `Err(PhaseFailed)` a los
/// 5 s — lo delata tanto el `UserAborted` como el techo de 2 s.
#[cfg(unix)]
#[test]
fn cancel_concurrente_en_el_primer_tick_mata_al_hijo() {
    let Ok(cwd) = tempfile::tempdir() else {
        panic!("tempdir");
    };
    let token = CancelToken::new();
    let arm = token.clone();
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_millis(30));
        arm.cancel();
    });
    let started = Instant::now();
    let got = StdCommandRunner.run_cancellable(
        "sleep",
        &["30"],
        cwd.path(),
        &[],
        Duration::from_secs(5),
        &token,
    );
    let elapsed = started.elapsed();
    assert_eq!(got, Err(WizardError::UserAborted));
    assert!(
        elapsed < Duration::from_secs(2),
        "la respuesta viene del tick de 50 ms, no del plazo de 5 s: {elapsed:?}"
    );
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
