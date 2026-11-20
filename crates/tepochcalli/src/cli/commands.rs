//! `config embedder` (T16), `reindex` (T17), `uninstall` (T17/H8) and
//! `update` (H7): the non-install commands, flag parsing and typed exits.

use std::path::Path;

use tepochcalli::adapters::{
    fetch_release_payload, HeadlessUi, LocalPayload, ReleasePayload, StdCommandRunner,
    SysHostProbe, TtyUi, UreqHttpClient,
};
use tepochcalli::application::text::or_fallback;
use tepochcalli::application::{
    resolve_vault_dir, run_reindex, run_swap, run_uninstall, run_update, SwapDeps, SwapOptions,
};
use tepochcalli::domain::{CancelToken, WizardError};
use tepochcalli::ports::{HttpClient, PayloadSource, Ui};

use super::flags::{parse_flags, tty_ok, FlagSpec};
use super::install::validate_payload_flags;
use super::report::{report_failure, report_maintenance_failure};
use super::usage::VERSION;

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

const UPDATE_SPEC: FlagSpec = FlagSpec {
    prefix: "update",
    help_command: "update",
    takes_value: &["--vault", "--payload", "--payload-url", "--payload-sha256"],
    boolean: &["--non-interactive"],
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
        // Non-interactive answers: MiniLM row (same default as the TUI) más
        // la fila del dispositivo (`0` = cpu, H9); no scripted vault (must
        // come from `--vault`, never a guess).
        Box::new(HeadlessUi::new(
            vec![0, 0].into(),
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
        // T16 conectará el disparo (botón TUI / Ctrl+C) a este token.
        cancel: CancelToken::new(),
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

/// `uninstall` (H8): remove `.opencode/`, `.tepochcalli/` and
/// `opencode.json` — nothing else (`AGENTS.md`, the notes, the trays,
/// `10-templates/` and `.obsidian/` survive by construction). Each removed
/// scope is backed up first. Idempotent: missing scopes are a no-op `Ok`.
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
    // ni se borra — el uninstall elimina el payload del harness y el runtime.
    if !confirm {
        let _ = writeln!(
            stderr,
            "uninstall: nada que hacer sin --confirm — el uninstall borra \
             .opencode/, .tepochcalli/ (venv, bin, db, models, config) y opencode.json. \
             Re-ejecuta con `--confirm` para proceder."
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
    match run_uninstall(&*ui, path) {
        Ok(report) => {
            if report.removed {
                let _ = writeln!(
                    stdout,
                    "uninstall: removed .opencode/, .tepochcalli/ and opencode.json from {}",
                    path.display()
                );
                if let Some(backup) = &report.backup_dir {
                    let _ = writeln!(stdout, "uninstall: backup en {}", backup.display());
                    let _ = writeln!(
                        stdout,
                        "uninstall: el backup contiene .tepochcalli/config/ (posible API key); \
                         el directorio se auto-ignora con su propio .gitignore (`*`) — no lo \
                         commitees"
                    );
                }
            } else {
                let _ = writeln!(
                    stdout,
                    "uninstall: nothing to remove (no .opencode/, .tepochcalli/ or opencode.json)"
                );
            }
            0
        }
        Err(err) => {
            report_maintenance_failure(&*ui, "uninstall", "uninstall failed", err, Some(path))
        }
    }
}

/// `update` (H7): overwrite the 5 payload scopes of an installed vault with a
/// `.bak` per replaced file and a rollback on failure. The payload is
/// resolved like `install` (`--payload` → `--payload-url`+sha → the versioned
/// release asset for this binary).
pub(crate) fn run_update_cmd(
    args: Vec<&str>,
    stdout: &mut dyn std::io::Write,
    stderr: &mut dyn std::io::Write,
) -> u8 {
    let flags = match parse_flags(&args, &UPDATE_SPEC, stdout, stderr) {
        Ok(Some(flags)) => flags,
        Ok(None) => return 0,
        Err(code) => return code,
    };
    let non_interactive = flags.is_set("--non-interactive");
    let vault = flags.value("--vault").map(str::to_string);
    let payload = flags.value("--payload").map(str::to_string);
    let payload_url = flags.value("--payload-url").map(str::to_string);
    let payload_sha256 = flags.value("--payload-sha256").map(str::to_string);
    if let Err(code) = validate_payload_flags(
        "update",
        payload.as_deref(),
        payload_url.as_deref(),
        payload_sha256.as_deref(),
        stderr,
    ) {
        return code;
    }
    // T6 rule: no TTY means no prompts — fail fast instead of hanging.
    if !tty_ok(stderr, non_interactive, "update") {
        return WizardError::UserAborted.exit_code();
    }
    let ui: Box<dyn Ui> = if non_interactive {
        Box::new(HeadlessUi::new(Default::default(), Default::default()))
    } else {
        Box::new(TtyUi)
    };
    let raw = match resolve_vault_dir(&*ui, vault.as_deref()) {
        Ok(raw) => raw,
        Err(err) => {
            return report_maintenance_failure(
                &*ui,
                "update",
                "update: vault selection failed",
                err,
                None,
            );
        }
    };
    let path = Path::new(&raw);
    let source: Box<dyn PayloadSource> = match (payload, payload_url, payload_sha256) {
        (Some(dir), None, None) => Box::new(LocalPayload::new(Path::new(&dir))),
        (None, Some(url), Some(sha)) => {
            // R-offline-1 (T13): la rama release ya GET-ea el sidecar en
            // `fetch_release_payload` y `--payload` local no usa red; el
            // override es el único camino que llegaría al write sin sonda.
            if let Err(err) = UreqHttpClient::new().probe(&url) {
                return report_maintenance_failure(
                    &*ui,
                    "update",
                    "update: sin red (preflight)",
                    err,
                    Some(path),
                );
            }
            Box::new(ReleasePayload::new(&url, &sha))
        }
        (None, None, None) => match fetch_release_payload(&UreqHttpClient::new(), VERSION) {
            Ok(release) => Box::new(release),
            Err(err) => {
                return report_maintenance_failure(
                    &*ui,
                    "update",
                    "update: payload resolution failed",
                    err,
                    Some(path),
                );
            }
        },
        // Unreachable: `validate_payload_flags` rejects half/conflicting sets.
        _ => return 2,
    };
    match run_update(&*source, &*ui, path) {
        Ok(report) => {
            let _ = writeln!(
                stdout,
                "update: {} ficheros escritos · {} backups (.bak)",
                report.written, report.backed_up
            );
            0
        }
        Err(err) => report_maintenance_failure(&*ui, "update", "update failed", err, Some(path)),
    }
}
