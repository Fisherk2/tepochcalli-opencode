//! Real [`crate::ports::CommandRunner`]: direct `std::process` spawn.
//!
//! Never `sh -c`: `program` is the executed binary itself. A caller that
//! needs a shell passes it explicitly as `program` (e.g. `sh`, `-c`, …).

use std::path::Path;
use std::process::{Child, ChildStderr, ChildStdout, Command};
use std::sync::mpsc::Receiver;
use std::sync::{mpsc, Arc, Mutex};

use crate::domain::{CancelToken, WizardError};
use crate::ports::{CommandOutput, CommandRunner};

/// [`CommandRunner`] over [`std::process::Command`] (no shell wrapping).
#[derive(Debug, Default, Clone, Copy)]
pub struct StdCommandRunner;

/// Env del padre que un subproceso NO puede arrastrar por herencia (4b-B):
/// fuera PYTHONPATH hostil, tokens de fondo, vars de CI... El allowlist
/// re-añade lo benigno que el toolchain necesita, y NINGÚN par explícito
/// del caller se pierde (se aplican después, con override).
const ENV_KEEP_EXACT: &[&str] = &[
    "PATH",
    "HOME",
    "USERPROFILE",
    "SYSTEMROOT",
    "COMSPEC",
    "TMP",
    "TEMP",
    "APPDATA",
    "LOCALAPPDATA",
    "LANG",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "http_proxy",
    "https_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "no_proxy",
    "NO_PROXY",
];
const ENV_KEEP_PREFIX: &[&str] = &["LC_", "XDG_"];

/// Aplica env_clear + allowlist del padre sobre `child` (los pares del
/// caller los pone el caller después, ganando cualquier allowlist).
fn build_command(program: &str, args: &[&str], cwd: &Path, env: &[(&str, &str)]) -> Command {
    let mut child = Command::new(program);
    child.args(args).current_dir(cwd).env_clear();
    for (key, value) in std::env::vars_os() {
        let Some(key_str) = key.to_str() else {
            continue;
        };
        // Allowlist exact + prefijos: en Windows las claves son
        // case-insensitive, y la tabla ya lista ambas grafías para las
        // variables de tarea (lower y upper en ENV_KEEP_EXACT).
        let kept = ENV_KEEP_EXACT.contains(&key_str)
            || ENV_KEEP_PREFIX.iter().any(|p| key_str.starts_with(p));
        if kept {
            child.env(key, value);
        }
    }
    child.envs(env.iter().copied());
    child
}

impl CommandRunner for StdCommandRunner {
    fn run(
        &self,
        program: &str,
        args: &[&str],
        cwd: &Path,
        env: &[(&str, &str)],
    ) -> Result<CommandOutput, WizardError> {
        let output = build_command(program, args, cwd, env)
            .output()
            .map_err(|_| WizardError::PhaseFailed)?;
        Ok(CommandOutput {
            // `code()` is `None` on Unix signal death; keep it numeric.
            status: output.status.code().unwrap_or(-1),
            stdout: String::from_utf8_lossy(&output.stdout).into_owned(),
            stderr: String::from_utf8_lossy(&output.stderr).into_owned(),
        })
    }

    /// Run with deadline (L3-6): pipes drained by a dedicated reader, the
    /// child polled by a watcher; past the plazo the parent KILLS the
    /// child (no orphan writes) and returns `PhaseFailed`. Los demas spawns
    /// sin hang plausible quedan en `run` (default del port).
    fn run_with_timeout(
        &self,
        program: &str,
        args: &[&str],
        cwd: &Path,
        env: &[(&str, &str)],
        timeout: std::time::Duration,
    ) -> Result<CommandOutput, WizardError> {
        run_inner(program, args, cwd, env, timeout, None)
    }

    /// Variante cancelable (R-offline-2): el mismo watcher sondea el token y,
    /// disparado, mata al hijo y devuelve `UserAborted`. La descarga del
    /// modelo ocurre en el hijo del flow, así que matarlo ES detenerla.
    fn run_cancellable(
        &self,
        program: &str,
        args: &[&str],
        cwd: &Path,
        env: &[(&str, &str)],
        timeout: std::time::Duration,
        cancel: &CancelToken,
    ) -> Result<CommandOutput, WizardError> {
        run_inner(program, args, cwd, env, timeout, Some(cancel))
    }
}

/// Veredicto del watcher: muerte natural (status) o cancelación del token.
enum Verdict {
    Exited(i32),
    Cancelled,
}

/// Lector: drena stdout y stderr (EOF al morir el hijo, natural o killed).
/// Abandonado pasado el plazo — los buffers no se fugan.
fn spawn_reader(
    stdout_pipe: Option<ChildStdout>,
    stderr_pipe: Option<ChildStderr>,
) -> Receiver<(String, String)> {
    let (text_tx, text_rx) = mpsc::channel::<(String, String)>();
    std::thread::spawn(move || {
        let mut out = String::new();
        let mut err = String::new();
        if let Some(mut pipe) = stdout_pipe {
            use std::io::Read as _;
            let _ = pipe.read_to_string(&mut out);
        }
        if let Some(mut pipe) = stderr_pipe {
            use std::io::Read as _;
            let _ = pipe.read_to_string(&mut err);
        }
        let _ = text_tx.send((out, err));
    });
    text_rx
}

/// Watcher: sondea el status con el lock tomado en ráfagas (así el padre
/// puede tomar el lock para el kill pasado el plazo). Con token, primero
/// mira la cancelación: disparada ⇒ kill + veredicto `Cancelled`. El token
/// es un `Arc`: llega clonado (la UI conserva el suyo).
fn spawn_watcher(child: Arc<Mutex<Child>>, cancel: Option<CancelToken>) -> Receiver<Verdict> {
    let (status_tx, status_rx) = mpsc::channel::<Verdict>();
    std::thread::spawn(move || loop {
        std::thread::sleep(std::time::Duration::from_millis(50));
        if cancel.as_ref().is_some_and(CancelToken::is_cancelled) {
            if let Ok(mut guard) = child.lock() {
                let _ = guard.kill();
                let _ = guard.wait();
            }
            let _ = status_tx.send(Verdict::Cancelled);
            return;
        }
        let verdict = match child.lock() {
            Ok(mut guard) => guard.try_wait().unwrap_or_default(),
            Err(_) => return,
        };
        if let Some(status) = verdict {
            // El padre pudo vencer el plazo y soltar el canal: send(si llega)
            // falla y salimos — ningun thread queda eterno.
            let _ = status_tx.send(Verdict::Exited(status.code().unwrap_or(-1)));
            return;
        }
    });
    status_rx
}

/// Trunk único de `run_with_timeout`/`run_cancellable` (mismo lector y
/// watcher); `cancel: None` es el comportamiento byte-idéntico anterior.
fn run_inner(
    program: &str,
    args: &[&str],
    cwd: &Path,
    env: &[(&str, &str)],
    timeout: std::time::Duration,
    cancel: Option<&CancelToken>,
) -> Result<CommandOutput, WizardError> {
    if cancel.is_some_and(CancelToken::is_cancelled) {
        return Err(WizardError::UserAborted);
    }
    let mut child = build_command(program, args, cwd, env)
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .map_err(|_| WizardError::PhaseFailed)?;
    let stdout_pipe = child.stdout.take();
    let stderr_pipe = child.stderr.take();
    let child = Arc::new(Mutex::new(child));

    let text_rx = spawn_reader(stdout_pipe, stderr_pipe);
    let status_rx = spawn_watcher(Arc::clone(&child), cancel.cloned());

    match status_rx.recv_timeout(timeout) {
        Ok(Verdict::Exited(status)) => {
            // El plazo del text_rx no re-verdicta: sin texto, vacíos.
            let (stdout, stderr) = text_rx
                .recv_timeout(timeout)
                .unwrap_or_else(|_| (String::new(), String::new()));
            Ok(CommandOutput {
                status,
                stdout,
                stderr,
            })
        }
        Ok(Verdict::Cancelled) => {
            // El watcher ya hizo kill + wait; los buffers del lector se
            // descartan (la salida de una descarga cancelada no es dato).
            Err(WizardError::UserAborted)
        }
        Err(_) => {
            // Plazo vencido con el hijo vivo: kill; las ráfagas cortas del
            // watcher permiten tomar el lock al padre.
            if let Ok(mut guard) = child.lock() {
                let _ = guard.kill();
                let _ = guard.wait();
            }
            Err(WizardError::PhaseFailed)
        }
    }
}
