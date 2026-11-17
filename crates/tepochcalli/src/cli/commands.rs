//! `config embedder` (T16), `reindex` (T17) and `uninstall` (T17): the three
//! non-install commands, flag parsing and typed exits byte-identical.

use std::path::Path;

use tepochcalli::adapters::{HeadlessUi, StdCommandRunner, SysHostProbe, TtyUi, UreqHttpClient};
use tepochcalli::application::text::or_fallback;
use tepochcalli::application::{
    resolve_vault_dir, run_reindex, run_swap, run_uninstall, SwapDeps, SwapOptions,
};
use tepochcalli::domain::WizardError;
use tepochcalli::ports::Ui;

use super::flags::{parse_flags, tty_ok, FlagSpec};
use super::report::{report_failure, report_maintenance_failure};

const SWAP_SPEC: FlagSpec = FlagSpec {
    prefix: "config embedder",
    help_command: "config embedder",
    takes_value: &["--vault"],
    boolean: &["--non-interactive", "--confirm", "--keep-previous"],
};

const REINDEX_SPEC: FlagSpec = FlagSpec {
    prefix: "reindex",
    help_command: "reindex",
    takes_value: &["--vault"],
    boolean: &["--non-interactive", "--confirm"],
};

const UNINSTALL_SPEC: FlagSpec = FlagSpec {
    prefix: "uninstall",
    help_command: "uninstall",
    takes_value: &["--vault"],
    boolean: &["--non-interactive", "--confirm"],
};

/// `config embedder` (T16, D8.4): six-step atomic swap on an installed vault —
/// current-state display, same D7.1 menu, `--confirm` warning, gate + reindex,
/// atomic config/metadata switch, auto-GC unless `--keep-previous`.
pub(crate) fn run_config_embedder(
    args: Vec<&str>,
    stdout: &mut dyn std::io::Write,
    stderr: &mut dyn std::io::Write,
) -> u8 {
    let flags = match parse_flags(&args, &SWAP_SPEC, stdout, stderr) {
        Ok(Some(flags)) => flags,
        Ok(None) => return 0,
        Err(code) => return code,
    };
    let non_interactive = flags.is_set("--non-interactive");
    let confirm = flags.is_set("--confirm");
    let keep_previous = flags.is_set("--keep-previous");
    let vault = flags.value("--vault").map(str::to_string);
    // T6 rule: no TTY means no prompts — fail fast instead of hanging.
    if !tty_ok(stderr, non_interactive, "config embedder") {
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
    let flags = match parse_flags(&args, &REINDEX_SPEC, stdout, stderr) {
        Ok(Some(flags)) => flags,
        Ok(None) => return 0,
        Err(code) => return code,
    };
    let non_interactive = flags.is_set("--non-interactive");
    let confirm = flags.is_set("--confirm");
    let vault = flags.value("--vault").map(str::to_string);
    if !confirm {
        let _ = writeln!(
            stderr,
            "reindex: nada que hacer sin --confirm — el re-index completo es destructivo \
             (reconstruye el índice con el modelo actual). Re-ejecuta con `--confirm` para proceder."
        );
        return 2;
    }
    // T6 rule: no TTY means no prompts — fail fast instead of hanging.
    if !tty_ok(stderr, non_interactive, "reindex") {
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
    let flags = match parse_flags(&args, &UNINSTALL_SPEC, stdout, stderr) {
        Ok(Some(flags)) => flags,
        Ok(None) => return 0,
        Err(code) => return code,
    };
    let non_interactive = flags.is_set("--non-interactive");
    let confirm = flags.is_set("--confirm");
    let vault = flags.value("--vault").map(str::to_string);
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
    if !tty_ok(stderr, non_interactive, "uninstall") {
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
