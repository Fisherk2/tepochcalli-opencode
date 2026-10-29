//! Real [`crate::ports::CommandRunner`]: direct `std::process` spawn.
//!
//! Never `sh -c`: `program` is the executed binary itself. A caller that
//! needs a shell passes it explicitly as `program` (e.g. `sh`, `-c`, …).

use std::path::Path;
use std::process::Command;
use std::sync::{mpsc, Arc, Mutex};

use crate::domain::WizardError;
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
        let mut child = build_command(program, args, cwd, env)
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .spawn()
            .map_err(|_| WizardError::PhaseFailed)?;
        let stdout_pipe = child.stdout.take();
        let stderr_pipe = child.stderr.take();
        let child = Arc::new(Mutex::new(child));

        // Lector: drena stdout y stderr (EOF al morir el hijo, natural o
        // killed). Abandonado pasar el plazo — los buffers nueno fugan.
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

        // Watcher: sondea el status con el lock tomado en ráfagas (so el
        // padreNavLink puede tomar el lock para kill pasa del plazo).
        let (status_tx, status_rx) = mpsc::channel::<i32>();
        let slot_for_watcher = Arc::clone(&child);
        std::thread::spawn(move || loop {
            std::thread::sleep(std::time::Duration::from_millis(50));
            let verdict = match slot_for_watcher.lock() {
                Ok(mut guard) => guard.try_wait().unwrap_or_default(),
                Err(_) => return,
            };
            if let Some(status) = verdict {
                // El padre pudo vencer el plazo y soltar el canal: send(si llega)
                // falla y salimos — ningun thread queda eterno.
                if status_tx.send(status.code().unwrap_or(-1)).is_err() {
                    return;
                }
            }
        });

        match status_rx.recv_timeout(timeout) {
            Ok(status) => {
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
}
