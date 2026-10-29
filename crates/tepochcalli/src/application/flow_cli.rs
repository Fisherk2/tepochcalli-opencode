//! Shared flow-CLI subprocess trunk: every phase that talks to
//! `tepochcalli_flow` (F6 gate, refresh, F7, reindex, swap) and the F8
//! `rag_status` probe convenes here (was: five hand-copied interpreter/env/
//! status blocks — H1: only swap and phase7 carried the interpreter guard).
//!
//! The caller keeps its parser and its locals; only the spawn trunk is
//! shared. `HF_TOKEN` travels only in the child env, never logged.

use std::path::Path;

use crate::domain::WizardError;
use crate::ports::{CommandOutput, CommandRunner};

use super::installer::{venv_python, RUNTIME_DIR, VENV_DIR_NAME};

/// Model cache dir, sandboxed under the vault via `HF_HOME` (same dir the
/// F6 gate, F7 and the swap pass: the download happens once, every pass
/// reuses it).
const MODELS_DIR: &str = "models";

/// Plazos de subprocess (L3-6): el gate mide RSS de un embed (generoso:
/// descarga de modelo incluida, 300 s); el refresh reconstruye el índice
/// sobre vaults grandes (900 s); el probe `rag_status` de F8 es una llamada
/// local (120 s). Un cuelgue de infarto se mata tipado, nunca cuelga el
/// instalador.
pub(super) const GATE_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(300);
pub(super) const REFRESH_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(900);
pub(super) const PROBE_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(120);

/// Run the vault venv interpreter with its model-cache sandbox and the
/// caller's argv. A vault without the interpreter means F5 never ran: typed
/// `Internal`, never a spawn attempt. A non-zero child status is
/// `PhaseFailed`; the caller owns parsing the stdout payload.
pub(super) fn run_flow_cli(
    proc: &dyn CommandRunner,
    vault: &Path,
    args: &[&str],
    extra_env: &[(&str, &str)],
    token: Option<&str>,
    timeout: std::time::Duration,
) -> Result<CommandOutput, WizardError> {
    // shortcut: a vault without the venv interpreter means F5 never ran;
    // same class as F5's missing-`uv` check (typed, never a spawn attempt).
    let python = venv_python(&vault.join(RUNTIME_DIR).join(VENV_DIR_NAME));
    if !python.is_file() {
        return Err(WizardError::Internal);
    }
    let models = vault
        .join(RUNTIME_DIR)
        .join(MODELS_DIR)
        .to_string_lossy()
        .into_owned();
    let program = python.to_str().ok_or(WizardError::Internal)?.to_string();
    let mut env: Vec<(&str, &str)> = vec![
        ("HF_HOME", &models),
        ("SENTENCE_TRANSFORMERS_HOME", &models),
    ];
    env.extend_from_slice(extra_env);
    if let Some(secret) = token {
        // shortcut: the token travels only in the child env (T11g redacts all
        // UI/log surfaces; a generic env-scrubber is T15 scope).
        env.push(("HF_TOKEN", secret));
    }
    let out = proc.run_with_timeout(&program, args, vault, &env, timeout)?;
    if out.status != 0 {
        return Err(WizardError::PhaseFailed);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::RefCell;
    use std::collections::VecDeque;

    type Script = VecDeque<Result<CommandOutput, WizardError>>;
    type RecordedCall = (String, Vec<String>, Vec<(String, String)>);

    struct RecordingProc {
        calls: RefCell<Vec<RecordedCall>>,
        script: RefCell<Script>,
    }

    impl CommandRunner for RecordingProc {
        fn run(
            &self,
            program: &str,
            args: &[&str],
            _cwd: &Path,
            env: &[(&str, &str)],
        ) -> Result<CommandOutput, WizardError> {
            self.calls.borrow_mut().push((
                program.to_string(),
                args.iter().map(ToString::to_string).collect(),
                env.iter()
                    .map(|(k, v)| (k.to_string(), v.to_string()))
                    .collect(),
            ));
            self.script
                .borrow_mut()
                .pop_front()
                .unwrap_or(Err(WizardError::Internal))
        }
    }

    fn out() -> CommandOutput {
        CommandOutput {
            status: 0,
            stdout: "{\"ok\":true}".to_string(),
            stderr: String::new(),
        }
    }

    fn fake_venv(vault: &Path) {
        let python = venv_python(&vault.join(RUNTIME_DIR).join(VENV_DIR_NAME));
        if let Some(parent) = python.parent() {
            if let Err(err) = std::fs::create_dir_all(parent) {
                panic!("venv fixture: {err}");
            }
        }
        if let Err(err) = std::fs::write(&python, b"fake-python") {
            panic!("python fixture: {err}");
        }
    }

    fn proc_with(script: Script) -> RecordingProc {
        RecordingProc {
            calls: RefCell::new(Vec::new()),
            script: RefCell::new(script),
        }
    }

    #[test]
    fn run_flow_cli_sets_the_sandbox_and_the_token_in_child_env_only() {
        let vault = match tempfile::tempdir() {
            Ok(dir) => dir,
            Err(err) => panic!("tempdir: {err}"),
        };
        fake_venv(vault.path());
        let proc = proc_with(VecDeque::from(vec![Ok(out())]));
        let got = run_flow_cli(
            &proc,
            vault.path(),
            &["-m", "tepochcalli_flow", "refresh"],
            &[],
            Some("hf-secret"),
            REFRESH_TIMEOUT,
        );
        let got = match got {
            Ok(out) => out,
            Err(err) => panic!("cli run: {err:?}"),
        };
        assert_eq!(got.stdout, "{\"ok\":true}");
        let calls = proc.calls.borrow();
        assert_eq!(calls.len(), 1, "una sola llamada");
        let (program, args, env) = &calls[0];
        let expected = venv_python(&vault.path().join(RUNTIME_DIR).join(VENV_DIR_NAME));
        let expected_path = match expected.to_str() {
            Some(path) => path.to_string(),
            None => panic!("venv path utf-8"),
        };
        assert_eq!(program, &expected_path, "programa = intérprete del venv");
        assert_eq!(
            args.iter().map(String::as_str).collect::<Vec<_>>(),
            ["-m", "tepochcalli_flow", "refresh"]
        );
        for key in ["HF_HOME", "SENTENCE_TRANSFORMERS_HOME"] {
            let value = match env
                .iter()
                .find_map(|(k, v)| (k == key).then_some(v.as_str()))
            {
                Some(value) => value,
                None => panic!("el env del hijo lleva {key}: {env:?}"),
            };
            assert!(
                value.ends_with("/models") || value.ends_with("\\models"),
                "el sandbox apunta al models/ del vault: {env:?}"
            );
        }
        let token = match env
            .iter()
            .find_map(|(k, v)| (k == "HF_TOKEN").then_some(v.as_str()))
        {
            Some(token) => token,
            None => panic!("HF_TOKEN en el env del hijo: {env:?}"),
        };
        assert_eq!(token, "hf-secret");
        // El token viaja solo en el env del hijo: nunca en argv ni programa.
        assert!(!program.contains("hf-secret"));
        assert!(!args.iter().any(|arg| arg.contains("hf-secret")));
    }

    #[test]
    fn missing_interpreter_is_internal_without_any_spawn() {
        let vault = match tempfile::tempdir() {
            Ok(dir) => dir,
            Err(err) => panic!("tempdir: {err}"),
        };
        let proc = proc_with(VecDeque::from(vec![Ok(out())]));
        assert_eq!(
            run_flow_cli(
                &proc,
                vault.path(),
                &["-m", "tepochcalli_flow"],
                &[],
                None,
                REFRESH_TIMEOUT,
            ),
            Err(WizardError::Internal)
        );
        assert!(proc.calls.borrow().is_empty(), "no spawn sin venv");
    }

    #[test]
    fn non_zero_status_is_phase_failed_and_extra_env_reaches_the_child() {
        let vault = match tempfile::tempdir() {
            Ok(dir) => dir,
            Err(err) => panic!("tempdir: {err}"),
        };
        fake_venv(vault.path());
        let proc = proc_with(VecDeque::from(vec![Ok(CommandOutput {
            status: 3,
            stdout: String::new(),
            stderr: String::new(),
        })]));
        assert_eq!(
            run_flow_cli(
                &proc,
                vault.path(),
                &["-c", "probe"],
                &[("TEPOCHCALLI_ROOT", ".")],
                None,
                PROBE_TIMEOUT,
            ),
            Err(WizardError::PhaseFailed)
        );
        let calls = proc.calls.borrow();
        assert_eq!(calls.len(), 1, "una sola llamada");
        let (_, _, env) = &calls[0];
        let root = match env
            .iter()
            .find_map(|(k, v)| (k == "TEPOCHCALLI_ROOT").then_some(v.as_str()))
        {
            Some(root) => root,
            None => panic!("TEPOCHCALLI_ROOT del extra_env: {env:?}"),
        };
        assert_eq!(root, ".");
        assert!(
            env.iter().all(|(k, _)| k != "HF_TOKEN"),
            "sin token: {env:?}"
        );
    }
}
