//! `CommandRunner`: run a subprocess with explicit `cwd` + `env`.

use std::path::Path;
use std::time::Duration;

use crate::domain::{CancelToken, WizardError};

/// Captured child output (status code kept as `i32`, as the OS reports it).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CommandOutput {
    /// Process exit status.
    pub status: i32,
    /// Captured stdout.
    pub stdout: String,
    /// Captured stderr.
    pub stderr: String,
}

/// Runs external commands (`uv`, `python -m tepochcalli_flow`, …).
/// Never `shell = true`: the program path is always explicit.
pub trait CommandRunner {
    /// Run `program` with `args` in `cwd` and the given extra `env` pairs.
    fn run(
        &self,
        program: &str,
        args: &[&str],
        cwd: &Path,
        env: &[(&str, &str)],
    ) -> Result<CommandOutput, WizardError>;

    /// Run with a plazo duro (L3-6): un hijo colgado es KILLED y el resultado
    /// es el `PhaseFailed` tipado — nunca un instalador colgado eterno.
    /// Default = sin deadline: los spawns sin riesgo de hang quedan como están.
    fn run_with_timeout(
        &self,
        program: &str,
        args: &[&str],
        cwd: &Path,
        env: &[(&str, &str)],
        timeout: Duration,
    ) -> Result<CommandOutput, WizardError> {
        let _ = timeout;
        self.run(program, args, cwd, env)
    }

    /// Como `run_with_timeout`, pero honra `cancel` (R-offline-2): token ya
    /// disparado ⇒ `UserAborted` sin spawn; el runner real además mata al
    /// hijo a mitad. Default: solo la comprobación previa.
    fn run_cancellable(
        &self,
        program: &str,
        args: &[&str],
        cwd: &Path,
        env: &[(&str, &str)],
        timeout: Duration,
        cancel: &CancelToken,
    ) -> Result<CommandOutput, WizardError> {
        if cancel.is_cancelled() {
            return Err(WizardError::UserAborted);
        }
        self.run_with_timeout(program, args, cwd, env, timeout)
    }
}
