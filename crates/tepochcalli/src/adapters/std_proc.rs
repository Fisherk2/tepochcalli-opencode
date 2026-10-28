//! Real [`crate::ports::CommandRunner`]: direct `std::process` spawn.
//!
//! Never `sh -c`: `program` is the executed binary itself. A caller that
//! needs a shell passes it explicitly as `program` (e.g. `sh`, `-c`, …).

use std::path::Path;
use std::process::Command;

use crate::domain::WizardError;
use crate::ports::{CommandOutput, CommandRunner};

/// [`CommandRunner`] over [`std::process::Command`] (no shell wrapping).
#[derive(Debug, Default, Clone, Copy)]
pub struct StdCommandRunner;

impl CommandRunner for StdCommandRunner {
    fn run(
        &self,
        program: &str,
        args: &[&str],
        cwd: &Path,
        env: &[(&str, &str)],
    ) -> Result<CommandOutput, WizardError> {
        let output = Command::new(program)
            .args(args)
            .current_dir(cwd)
            .envs(env.iter().copied())
            .output()
            .map_err(|_| WizardError::PhaseFailed)?;
        Ok(CommandOutput {
            // `code()` is `None` on Unix signal death; keep it numeric.
            status: output.status.code().unwrap_or(-1),
            stdout: String::from_utf8_lossy(&output.stdout).into_owned(),
            stderr: String::from_utf8_lossy(&output.stderr).into_owned(),
        })
    }
}
