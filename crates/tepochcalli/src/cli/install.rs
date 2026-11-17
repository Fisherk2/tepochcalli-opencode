//! `install` flag parsing (T6) + F1→F2 execution (T7): gates, vault dir
//! selection, offline pre-check and the hand-off to `run_phases` — plus the
//! offline error mapping and the F6 degraded fallback.

use std::io::IsTerminal;
use std::path::Path;

use tepochcalli::adapters::{path_dirs, HeadlessUi, SysHostProbe, TtyUi};
use tepochcalli::application::{
    check_prereqs_on, compensate_phase6, ensure_vault_dir, guard_offline_before_touch,
    is_phase_done, litellm_config_present, mark_phase_done, payload_local_ready, resolve_vault_dir,
    run_phase6, Phase6Deps, Phase6Report,
};
use tepochcalli::domain::{EmbedderChoice, Phase, VaultPath, WizardError};
use tepochcalli::ports::Ui;
use tepochcalli::EMBEDDER_PATHS;

use super::install_phases::run_phases;
use super::report::report_failure;
use super::usage::{print_help, print_version};

/// `install` flag parsing (T6) + F1→F2 execution (T7) + F3 merge (T8) +
/// F4 `uv` bootstrap, F5 venv/`sync` (T9), F6 embedder menu (T11) and F7
/// initial index (T12):
/// `--non-interactive`, `--skip-model`, `--vault <ruta>` and
/// `--payload <ruta>` select the [`HeadlessUi`] answers (never stdin) vs.
/// [`TtyUi`]; then F1 gates prereqs, F2 ensures the vault dir, F3 merges
/// the payload (local tree, URL override, or the versioned release asset),
/// F4 installs the pinned `uv`, F5 syncs the venv, F6 picks
/// the embedder (menu + gate + atomic config) and F7 indexes the vault
/// (path 5 skips it: degraded install, no index).
pub(crate) fn run_install(
    args: Vec<&str>,
    stdout: &mut dyn std::io::Write,
    stderr: &mut dyn std::io::Write,
) -> u8 {
    let mut non_interactive = false;
    let mut skip_model = false;
    let mut resume = false;
    let mut offline = false;
    let mut vault: Option<String> = None;
    let mut payload: Option<String> = None;
    let mut payload_url: Option<String> = None;
    let mut payload_sha256: Option<String> = None;
    let mut i = 0;
    while i < args.len() {
        match args[i] {
            "--help" => {
                print_help(stdout, Some("install"));
                return 0;
            }
            "--version" => {
                print_version(stdout);
                return 0;
            }
            "--non-interactive" => non_interactive = true,
            "--skip-model" => skip_model = true,
            "--resume" => resume = true,
            "--offline" => offline = true,
            "--vault" => {
                i += 1;
                match args.get(i) {
                    Some(value) => vault = Some((*value).to_string()),
                    None => {
                        let _ = writeln!(stderr, "install: --vault needs a value");
                        return 2;
                    }
                }
            }
            "--payload" => {
                i += 1;
                match args.get(i) {
                    Some(value) => payload = Some((*value).to_string()),
                    None => {
                        let _ = writeln!(stderr, "install: --payload needs a value");
                        return 2;
                    }
                }
            }
            "--payload-url" => {
                i += 1;
                match args.get(i) {
                    Some(value) => payload_url = Some((*value).to_string()),
                    None => {
                        let _ = writeln!(stderr, "install: --payload-url needs a value");
                        return 2;
                    }
                }
            }
            "--payload-sha256" => {
                i += 1;
                match args.get(i) {
                    Some(value) => payload_sha256 = Some((*value).to_string()),
                    None => {
                        let _ = writeln!(stderr, "install: --payload-sha256 needs a value");
                        return 2;
                    }
                }
            }
            flag if flag.starts_with("--vault=") => {
                vault = Some(flag["--vault=".len()..].to_string());
            }
            flag if flag.starts_with("--payload=") => {
                payload = Some(flag["--payload=".len()..].to_string());
            }
            flag if flag.starts_with("--payload-url=") => {
                payload_url = Some(flag["--payload-url=".len()..].to_string());
            }
            flag if flag.starts_with("--payload-sha256=") => {
                payload_sha256 = Some(flag["--payload-sha256=".len()..].to_string());
            }
            flag => {
                let _ = writeln!(stderr, "install: unknown flag: {flag}");
                return 2;
            }
        }
        i += 1;
    }
    // Payload source validation (usage errors, exit 2 — no network touched).
    // First: an EMPTY value is a typo, not an absent flag. Filtering it out
    // used to turn `--payload-url "$URL"` with an empty `$URL` into a silent
    // release-asset download (network), so it fails here — before any HTTP
    // client exists.
    for (flag, value) in [
        ("--payload", &payload),
        ("--payload-url", &payload_url),
        ("--payload-sha256", &payload_sha256),
    ] {
        if value.as_deref().is_some_and(|v| v.trim().is_empty()) {
            let _ = writeln!(
                stderr,
                "install: {flag} got an empty value (a shell variable that expanded to \
                 nothing?); pass a real value, or drop the flag"
            );
            return 2;
        }
    }
    // Then: `--payload` (local tree) conflicts with the URL override, and the
    // override needs both halves (URL + SHA-256) or neither.
    let payload_dir = payload;
    let url_override = payload_url;
    let sha_override = payload_sha256;
    if payload_dir.is_some() && (url_override.is_some() || sha_override.is_some()) {
        let _ = writeln!(
            stderr,
            "install: --payload conflicts with --payload-url/--payload-sha256 \
             (local tree or release asset, not both)"
        );
        return 2;
    }
    if url_override.is_some() != sha_override.is_some() {
        let _ = writeln!(
            stderr,
            "install: --payload-url needs --payload-sha256 (and vice versa)"
        );
        return 2;
    }
    // T6 rule: no TTY means no prompts — fail fast instead of hanging or
    // resolving the default dir under an unintended cwd.
    if !non_interactive && !std::io::stdin().is_terminal() {
        let _ = writeln!(
            stderr,
            "install: no TTY detected; re-run with --non-interactive (and --vault <ruta>)"
        );
        return WizardError::UserAborted.exit_code();
    }
    let ui: Box<dyn Ui> = if non_interactive {
        // Índices reales de EMBEDDER_PATHS (D7.1, L3-4): el acoplamiento del
        // constructor hardcodeado muere — reordenar el menú se rompe aquí.
        let skip_row = {
            let last = EMBEDDER_PATHS.len() - 1;
            match EMBEDDER_PATHS[last] {
                EmbedderChoice::ConfigureLater => last,
                _ => 0, // no atingible: D7.1 fija la fila 4 al final
            }
        };
        let default_row = 0; // EMBEDDER_PATHS[0] == PresetDefault (D7.1)
        Box::new(HeadlessUi::for_install(skip_row, default_row, skip_model))
    } else {
        Box::new(TtyUi)
    };
    // F1: prerequisites (RAM/disk/platform gate; missing tools only warn).
    // L4-5 (S-4): las path_dirs reales llegan del adapter — main es el caller
    // del composition-edge; la sonda GPU comparte la misma fuente de `PATH`.
    let disk_cwd = match std::env::current_dir() {
        Ok(cwd) => cwd,
        Err(_) => {
            return report_failure(
                &*ui,
                Some(Phase::F1),
                "install: prerequisites failed",
                WizardError::PermissionDenied,
                None,
            )
        }
    };
    let report =
        match check_prereqs_on(&SysHostProbe, std::env::consts::OS, &disk_cwd, &path_dirs()) {
            Ok(report) => report,
            Err(err) => {
                return report_failure(
                    &*ui,
                    Some(Phase::F1),
                    "install: prerequisites failed",
                    err,
                    None,
                );
            }
        };
    for (tool, found) in [
        ("obsidian", report.obsidian_found),
        ("opencode", report.opencode_found),
    ] {
        if !found {
            let _ = writeln!(
                stderr,
                "warning: `{tool}` not found in PATH (optional; continuing)"
            );
        }
    }
    // F2: vault directory (`--vault` wins; otherwise the Ui asks).
    let raw = match resolve_vault_dir(&*ui, vault.as_deref()) {
        Ok(raw) => raw,
        Err(err) => {
            return report_failure(
                &*ui,
                Some(Phase::F2),
                "install: vault selection failed",
                err,
                None,
            );
        }
    };
    // T14: offline pre-check BEFORE the vault is touched (exit 21, no writes).
    // D7.3 (L3-5): los brazos válidos son — payload local + cache (o litellm
    // config, que no necesita modelo local), o un resume cuyo payload ya está
    // local (F3 resuelta por artefacto: nada se re-descarga).
    if offline {
        let vault = Path::new(&raw);
        let cache_ready = skip_model || models_cached(vault) || litellm_config_present(vault);
        let resume_payload_local = resume && is_phase_done(vault, Phase::F3);
        match guard_offline_before_touch(
            true,
            payload_local_ready(payload_dir.as_deref()),
            cache_ready,
            resume_payload_local,
        ) {
            Ok(()) => {}
            Err(err) => {
                return report_failure(
                    &*ui,
                    Some(Phase::F2),
                    "install: offline without local payload/cache",
                    err,
                    None,
                );
            }
        }
    }
    let vault_path = match ensure_vault_dir(Path::new(&raw)) {
        Ok(path) => path,
        Err(err) => {
            return report_failure(
                &*ui,
                Some(Phase::F2),
                "install: vault directory failed",
                err,
                None,
            );
        }
    };
    mark_phase_done(vault_path.as_path(), Phase::F1);
    mark_phase_done(vault_path.as_path(), Phase::F2);
    run_phases(
        &vault_path,
        payload_dir,
        url_override,
        sha_override,
        resume,
        offline,
        non_interactive,
        &*ui,
        stdout,
        stderr,
    )
}

/// `true` when the vault already holds downloaded models (offline resume).
fn models_cached(vault: &Path) -> bool {
    match std::fs::read_dir(vault.join(".tepochcalli/models")) {
        Ok(mut entries) => entries.next().is_some(),
        Err(_) => false,
    }
}

/// Offline mapping: a network failure under `--offline` is the typed offline
/// error (exit 21), never a generic download failure.
pub(crate) fn offline_map(offline: bool, err: WizardError) -> WizardError {
    if offline && err == WizardError::NetDownload {
        WizardError::OfflineNoCache
    } else {
        err
    }
}

/// F6 with T14(f) fallback: any failure but an explicit abort (or a missing
/// offline cache) compensates to salida 5 — a COMPLETE degraded install.
pub(crate) fn run_f6_or_degraded(
    deps: &Phase6Deps<'_>,
    path: &VaultPath,
    offline: bool,
    ui: &dyn Ui,
    stderr: &mut dyn std::io::Write,
) -> Result<Phase6Report, u8> {
    match run_phase6(deps, path.as_path()) {
        Ok(picked) => {
            mark_phase_done(path.as_path(), Phase::F6);
            Ok(picked)
        }
        Err(err) => {
            let err = offline_map(offline, err);
            // shortcut: Internal/UserAborted/OfflineNoCache never degrade —
            // a bug, an explicit cancel and an empty cache stay failures.
            if err == WizardError::UserAborted
                || err == WizardError::Internal
                || err == WizardError::OfflineNoCache
            {
                return Err(report_failure(
                    ui,
                    Some(Phase::F6),
                    "install: phase F6 failed",
                    err,
                    Some(path.as_path()),
                ));
            }
            match compensate_phase6(path.as_path()) {
                Ok(()) => {
                    mark_phase_done(path.as_path(), Phase::F6);
                    let _ = writeln!(
                        stderr,
                        "embedder: F6 failed ({err}); continuing degraded (configure later)"
                    );
                    Ok(Phase6Report::configure_later())
                }
                Err(comp_err) => Err(report_failure(
                    ui,
                    Some(Phase::F6),
                    "install: phase F6 failed",
                    comp_err,
                    Some(path.as_path()),
                )),
            }
        }
    }
}
