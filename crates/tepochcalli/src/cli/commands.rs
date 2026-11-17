//! `config embedder` (T16), `reindex` (T17) and `uninstall` (T17): the three
//! non-install commands, flag parsing and typed exits byte-identical.

use std::io::IsTerminal;
use std::path::Path;

use tepochcalli::adapters::{HeadlessUi, StdCommandRunner, SysHostProbe, TtyUi, UreqHttpClient};
use tepochcalli::application::text::or_fallback;
use tepochcalli::application::{
    resolve_vault_dir, run_reindex, run_swap, run_uninstall, SwapDeps, SwapOptions,
};
use tepochcalli::domain::WizardError;
use tepochcalli::ports::Ui;

use super::report::{report_failure, report_maintenance_failure};
use super::usage::{print_help, print_version};

/// `config embedder` (T16, D8.4): six-step atomic swap on an installed vault —
/// current-state display, same D7.1 menu, `--confirm` warning, gate + reindex,
/// atomic config/metadata switch, auto-GC unless `--keep-previous`.
pub(crate) fn run_config_embedder(
    args: Vec<&str>,
    stdout: &mut dyn std::io::Write,
    stderr: &mut dyn std::io::Write,
) -> u8 {
    let mut non_interactive = false;
    let mut confirm = false;
    let mut keep_previous = false;
    let mut vault: Option<String> = None;
    let mut i = 0;
    while i < args.len() {
        match args[i] {
            "--help" => {
                print_help(stdout, Some("config embedder"));
                return 0;
            }
            "--version" => {
                print_version(stdout);
                return 0;
            }
            "--non-interactive" => non_interactive = true,
            "--confirm" => confirm = true,
            "--keep-previous" => keep_previous = true,
            "--vault" => {
                i += 1;
                match args.get(i) {
                    Some(value) => vault = Some((*value).to_string()),
                    None => {
                        let _ = writeln!(stderr, "config embedder: --vault needs a value");
                        return 2;
                    }
                }
            }
            flag if flag.starts_with("--vault=") => {
                vault = Some(flag["--vault=".len()..].to_string());
            }
            flag => {
                let _ = writeln!(stderr, "config embedder: unknown flag: {flag}");
                return 2;
            }
        }
        i += 1;
    }
    // T6 rule: no TTY means no prompts — fail fast instead of hanging.
    if !non_interactive && !std::io::stdin().is_terminal() {
        let _ = writeln!(
            stderr,
            "config embedder: no TTY detected; re-run with --non-interactive (and --vault <ruta>)"
        );
        return WizardError::UserAborted.exit_code();
    }
    let ui: Box<dyn Ui> = if non_interactive {
        // Non-interactive answers: MiniLM row (same default as the TUI) and
        // no scripted vault (must come from `--vault`, never a guess).
        Box::new(HeadlessUi::new(
            vec![0].into(),
            std::collections::VecDeque::new(),
        ))
    } else {
        Box::new(TtyUi)
    };
    let raw = match resolve_vault_dir(&*ui, vault.as_deref()) {
        Ok(raw) => raw,
        Err(err) => {
            return report_failure(
                &*ui,
                None,
                "config embedder: vault selection failed",
                err,
                None,
            );
        }
    };
    let path = Path::new(&raw);
    let http = UreqHttpClient::new();
    let proc = StdCommandRunner;
    let deps = SwapDeps {
        ui: &*ui,
        host: &SysHostProbe,
        proc: &proc,
        http: &http,
    };
    let opts = SwapOptions {
        confirm,
        keep_previous,
    };
    match run_swap(&deps, path, &opts) {
        Ok(report) => {
            let _ = writeln!(
                stdout,
                "embedder: {} (dims {})",
                report.model,
                or_fallback(report.dims)
            );
            0
        }
        Err(err) => report_failure(&*ui, None, "config embedder failed", err, Some(path)),
    }
}

/// `reindex` (T17): destructive full rebuild with the current model.
/// `--confirm` is a usage gate, not a prompt: without it nothing is resolved,
/// spawned or written — exit 2 with the reason on stderr.
pub(crate) fn run_reindex_cmd(
    args: Vec<&str>,
    stdout: &mut dyn std::io::Write,
    stderr: &mut dyn std::io::Write,
) -> u8 {
    let mut non_interactive = false;
    let mut confirm = false;
    let mut vault: Option<String> = None;
    let mut i = 0;
    while i < args.len() {
        match args[i] {
            "--help" => {
                print_help(stdout, Some("reindex"));
                return 0;
            }
            "--version" => {
                print_version(stdout);
                return 0;
            }
            "--non-interactive" => non_interactive = true,
            "--confirm" => confirm = true,
            "--vault" => {
                i += 1;
                match args.get(i) {
                    Some(value) => vault = Some((*value).to_string()),
                    None => {
                        let _ = writeln!(stderr, "reindex: --vault needs a value");
                        return 2;
                    }
                }
            }
            flag if flag.starts_with("--vault=") => {
                vault = Some(flag["--vault=".len()..].to_string());
            }
            flag => {
                let _ = writeln!(stderr, "reindex: unknown flag: {flag}");
                return 2;
            }
        }
        i += 1;
    }
    if !confirm {
        let _ = writeln!(
            stderr,
            "reindex: nada que hacer sin --confirm — el re-index completo es destructivo \
             (reconstruye el índice con el modelo actual). Re-ejecuta con `--confirm` para proceder."
        );
        return 2;
    }
    // T6 rule: no TTY means no prompts — fail fast instead of hanging.
    if !non_interactive && !std::io::stdin().is_terminal() {
        let _ = writeln!(
            stderr,
            "reindex: no TTY detected; re-run with --non-interactive (and --vault <ruta>)"
        );
        return WizardError::UserAborted.exit_code();
    }
    let ui: Box<dyn Ui> = if non_interactive {
        // The flag (when given) answers the directory question in
        // `resolve_vault_dir` without asking; an absent one surfaces as a
        // typed `UserAborted` — never a guess, never stdin.
        Box::new(HeadlessUi::new(Default::default(), Default::default()))
    } else {
        Box::new(TtyUi)
    };
    let raw = match resolve_vault_dir(&*ui, vault.as_deref()) {
        Ok(raw) => raw,
        Err(err) => {
            return report_maintenance_failure(
                &*ui,
                "reindex",
                "reindex: vault selection failed",
                err,
                None,
            );
        }
    };
    let path = Path::new(&raw);
    match run_reindex(&StdCommandRunner, &*ui, path) {
        Ok(report) => {
            let _ = writeln!(
                stdout,
                "reindex: modelo {} · dims {} · indexed {} ({} ms)",
                report.model,
                or_fallback(report.dims),
                report.indexed,
                report.elapsed_ms
            );
            0
        }
        Err(err) => report_maintenance_failure(&*ui, "reindex", "reindex failed", err, Some(path)),
    }
}

/// `uninstall` (T17): remove `.tepochcalli/` only. Notes, payload,
/// `opencode.json`, `00-resources/` and `.obsidian/` survive by construction
/// (the orchestrator never enumerates them). Idempotent: a missing runtime is
/// a no-op `Ok`, never an error.
pub(crate) fn run_uninstall_cmd(
    args: Vec<&str>,
    stdout: &mut dyn std::io::Write,
    stderr: &mut dyn std::io::Write,
) -> u8 {
    let mut non_interactive = false;
    let mut confirm = false;
    let mut vault: Option<String> = None;
    let mut i = 0;
    while i < args.len() {
        match args[i] {
            "--help" => {
                print_help(stdout, Some("uninstall"));
                return 0;
            }
            "--version" => {
                print_version(stdout);
                return 0;
            }
            "--non-interactive" => non_interactive = true,
            "--confirm" => confirm = true,
            "--vault" => {
                i += 1;
                match args.get(i) {
                    Some(value) => vault = Some((*value).to_string()),
                    None => {
                        let _ = writeln!(stderr, "uninstall: --vault needs a value");
                        return 2;
                    }
                }
            }
            flag if flag.starts_with("--vault=") => {
                vault = Some(flag["--vault=".len()..].to_string());
            }
            flag => {
                let _ = writeln!(stderr, "uninstall: unknown flag: {flag}");
                return 2;
            }
        }
        i += 1;
    }
    // Gate `--confirm` (patrón reindex, L4-3): sin el flag nada se resuelve
    // ni se borra — el uninstall elimina TODO el runtime, destructivo.
    if !confirm {
        let _ = writeln!(
            stderr,
            "uninstall: nada que hacer sin --confirm — el uninstall borra TODO \
             .tepochcalli/ (venv, bin, db, models, config). Re-ejecuta con `--confirm` \
             para proceder."
        );
        return 2;
    }
    // T6 rule: no TTY means no prompts — fail fast instead of hanging.
    if !non_interactive && !std::io::stdin().is_terminal() {
        let _ = writeln!(
            stderr,
            "uninstall: no TTY detected; re-run with --non-interactive (and --vault <ruta>)"
        );
        return WizardError::UserAborted.exit_code();
    }
    let ui: Box<dyn Ui> = if non_interactive {
        // Same contract as `reindex`: the flag answers, absence aborts typed.
        Box::new(HeadlessUi::new(Default::default(), Default::default()))
    } else {
        Box::new(TtyUi)
    };
    let raw = match resolve_vault_dir(&*ui, vault.as_deref()) {
        Ok(raw) => raw,
        Err(err) => {
            return report_maintenance_failure(
                &*ui,
                "uninstall",
                "uninstall: vault selection failed",
                err,
                None,
            );
        }
    };
    let path = Path::new(&raw);
    match run_uninstall(path) {
        Ok(report) => {
            if report.removed {
                let _ = writeln!(
                    stdout,
                    "uninstall: removed {}",
                    path.join(".tepochcalli").display()
                );
            } else {
                let _ = writeln!(stdout, "uninstall: nothing to remove (no .tepochcalli/)");
            }
            0
        }
        Err(err) => {
            report_maintenance_failure(&*ui, "uninstall", "uninstall failed", err, Some(path))
        }
    }
}
