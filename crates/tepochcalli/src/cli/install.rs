//! `install` flag parsing (T6) + F1→F2 execution (T7): gates, vault dir
//! selection, offline pre-check and the hand-off to `run_phases` — plus the
//! offline error mapping and the F6 degraded fallback.

use std::path::Path;

use tepochcalli::adapters::{
    mirror_http_non_loopback, path_dirs, payload_asset_url, release_base_url, HeadlessUi,
    SysHostProbe, TtyUi, UreqHttpClient,
};
use tepochcalli::application::{
    check_prereqs_on, compensate_phase6, embedder_presence, ensure_vault_dir,
    guard_offline_before_touch, is_phase_done, litellm_config_present, mark_phase_done,
    payload_endpoint, payload_local_ready, resolve_vault_dir, rollback_install, run_phase6,
    EmbedderPresence, InstallSnapshot, Phase6Deps, Phase6Report,
};
use tepochcalli::domain::{EmbedderChoice, Phase, VaultPath, WizardError};
use tepochcalli::ports::{HttpClient, Ui};
use tepochcalli::EMBEDDER_PATHS;

use super::flags::{parse_flags, tty_ok, FlagSpec};
use super::install_phases::{run_phases, PayloadArgs, RunFlags};
use super::report::{report_failure, report_usage_failure};
use super::usage::VERSION;

const INSTALL_SPEC: FlagSpec = FlagSpec {
    prefix: "install",
    help_command: "install",
    takes_value: &["--vault", "--payload", "--payload-url", "--payload-sha256"],
    boolean: &["--non-interactive", "--skip-model", "--resume", "--offline"],
};

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
    let flags = match parse_flags(&args, &INSTALL_SPEC, stdout, stderr) {
        Ok(Some(flags)) => flags,
        Ok(None) => return 0,
        Err(code) => return code,
    };
    let non_interactive = flags.is_set("--non-interactive");
    let skip_model = flags.is_set("--skip-model");
    let resume = flags.is_set("--resume");
    let offline = flags.is_set("--offline");
    let vault = flags.value("--vault").map(str::to_string);
    let payload = PayloadArgs {
        dir: flags.value("--payload").map(str::to_string),
        url: flags.value("--payload-url").map(str::to_string),
        sha: flags.value("--payload-sha256").map(str::to_string),
    };
    // Payload source validation (usage errors, exit 2 — no network touched).
    if let Err(code) = validate_payload_flags(
        "install",
        payload.dir.as_deref(),
        payload.url.as_deref(),
        payload.sha.as_deref(),
        stderr,
    ) {
        return code;
    }
    // T6 rule: no TTY means no prompts — fail fast instead of hanging.
    if !tty_ok(stderr, non_interactive, "install") {
        return WizardError::UserAborted.exit_code();
    }
    let ui = install_ui(non_interactive, skip_model);
    if let Err(code) = prereqs_gate(&*ui, stderr) {
        return code;
    }
    // F2: vault directory (`--vault` wins; otherwise the process cwd).
    let raw = match resolve_vault_for_install(&*ui, non_interactive, vault.as_deref()) {
        Ok(raw) => raw,
        Err(code) => return code,
    };
    // One line naming the absolute target before the first write (F2 probe).
    let target =
        std::path::absolute(Path::new(&raw)).unwrap_or_else(|_| Path::new(&raw).to_path_buf());
    let _ = writeln!(stderr, "install: destino: {}", target.display());
    let payload_dir = payload.dir.as_deref();
    let url_override = payload.url.as_deref();
    if let Err(code) = offline_guard(&*ui, &raw, offline, resume, skip_model, payload_dir) {
        return code;
    }
    if let Err(code) = network_preflight(&*ui, offline, payload_dir, url_override) {
        return code;
    }
    // R-offline-3 (T15): huella read-only del vault ANTES del primer write.
    let (vault_path, snapshot) = match capture_and_ensure(&*ui, &raw, stderr) {
        Ok(pair) => pair,
        Err(code) => return code,
    };
    mark_phase_done(vault_path.as_path(), Phase::F1);
    mark_phase_done(vault_path.as_path(), Phase::F2);
    run_phases_and_rollback(
        &vault_path,
        &payload,
        RunFlags {
            resume,
            offline,
            non_interactive,
        },
        &*ui,
        stdout,
        stderr,
        &snapshot,
    )
}

/// El `Ui` del instalador: [`HeadlessUi`] con las filas reales del menú (D7.1)
/// en `--non-interactive`, [`TtyUi`] en interactivo.
fn install_ui(non_interactive: bool, skip_model: bool) -> Box<dyn Ui> {
    if non_interactive {
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
    }
}

/// F1: prerequisites (RAM/disk/platform gate) — missing tools only warn.
/// `Err(code)` is the panel already emitted, on both failures.
fn prereqs_gate(ui: &dyn Ui, stderr: &mut dyn std::io::Write) -> Result<(), u8> {
    // L4-5 (S-4): las path_dirs reales llegan del adapter — main es el caller
    // del composition-edge; la sonda GPU comparte la misma fuente de `PATH`.
    let disk_cwd = match std::env::current_dir() {
        Ok(cwd) => cwd,
        Err(_) => {
            return Err(report_failure(
                ui,
                Some(Phase::F1),
                "install: prerequisites failed",
                WizardError::PermissionDenied,
                None,
            ))
        }
    };
    let report =
        match check_prereqs_on(&SysHostProbe, std::env::consts::OS, &disk_cwd, &path_dirs()) {
            Ok(report) => report,
            Err(err) => {
                return Err(report_failure(
                    ui,
                    Some(Phase::F1),
                    "install: prerequisites failed",
                    err,
                    None,
                ));
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
    Ok(())
}

/// F2: `--vault` wins; otherwise the process cwd. `Err(code)` is the panel
/// already emitted (a cwd that cannot be read is a typed filesystem failure).
fn resolve_vault_for_install(
    ui: &dyn Ui,
    non_interactive: bool,
    vault: Option<&str>,
) -> Result<String, u8> {
    match resolve_vault_dir(ui, vault) {
        Ok(raw) => Ok(raw),
        // Sin `--vault` ya no hay pregunta: solo puede fallar la lectura del
        // cwd (filesystem tipado). El brazo de abajo conserva el panel de
        // cancelación genuina por si otro resolver emitiera `UserAborted`.
        Err(err) if non_interactive => Err(report_usage_failure(
            ui,
            "install",
            Some(Phase::F2),
            "vault selection failed",
            "--vault <directorio>",
            "tepochcalli install --vault <directorio> --non-interactive",
            err,
            None,
        )),
        Err(err) => Err(report_failure(
            ui,
            Some(Phase::F2),
            "install: vault selection failed",
            err,
            None,
        )),
    }
}

/// T14: offline pre-check BEFORE the vault is touched (exit 21, no writes).
/// D7.3 (L3-5): los brazos válidos son — payload local + cache (o litellm
/// config, que no necesita modelo local), o un resume cuyo payload ya está
/// local (F3 resuelta por artefacto: nada se re-descarga).
fn offline_guard(
    ui: &dyn Ui,
    raw: &str,
    offline: bool,
    resume: bool,
    skip_model: bool,
    payload_dir: Option<&str>,
) -> Result<(), u8> {
    if !offline {
        return Ok(());
    }
    let vault = Path::new(raw);
    let local_model_cached = embedder_presence(vault) == EmbedderPresence::LocalModel;
    let cache_ready = skip_model || local_model_cached || litellm_config_present(vault);
    let resume_payload_local = resume && is_phase_done(vault, Phase::F3);
    guard_offline_before_touch(
        true,
        payload_local_ready(payload_dir),
        cache_ready,
        resume_payload_local,
    )
    .map_err(|err| {
        report_failure(
            ui,
            Some(Phase::F2),
            "install: offline without local payload/cache",
            err,
            None,
        )
    })
}

/// R-offline-1 (T13): sin red no se toca el vault — cero ficheros.
fn network_preflight(
    ui: &dyn Ui,
    offline: bool,
    payload_dir: Option<&str>,
    url_override: Option<&str>,
) -> Result<(), u8> {
    // Con un mirror http sin TLS el sondeo espera al consentimiento de
    // `run_phases` (probar http antes de consentir saltaría el gate L4-2).
    let base = release_base_url();
    let mirror_pending =
        payload_dir.is_none() && url_override.is_none() && mirror_http_non_loopback(&base);
    if !offline && !mirror_pending {
        let release = payload_asset_url(VERSION);
        if let Some(url) = payload_endpoint(payload_dir, url_override, &release) {
            if let Err(err) = UreqHttpClient::new().probe(&url) {
                return Err(report_failure(
                    ui,
                    Some(Phase::F2),
                    "install: sin red (preflight)",
                    err,
                    None,
                ));
            }
        }
    }
    Ok(())
}

/// R-offline-3 (T15): huella read-only del vault ANTES del primer write.
fn capture_and_ensure(
    ui: &dyn Ui,
    raw: &str,
    stderr: &mut dyn std::io::Write,
) -> Result<(VaultPath, InstallSnapshot), u8> {
    let snapshot = InstallSnapshot::capture(Path::new(raw));
    match ensure_vault_dir(Path::new(raw)) {
        Ok(path) => Ok((path, snapshot)),
        Err(err) => {
            // Orden: causa (panel tipado) → estado MEDIDO del rollback → exit.
            // El panel se emite SIEMPRE: sin causa, el 42 no explica nada.
            let code = report_failure(
                ui,
                Some(Phase::F2),
                "install: vault directory failed",
                err,
                None,
            );
            let report = rollback_install(Path::new(raw), &snapshot);
            if !announce_rollback(
                stderr,
                &report.compensated,
                &report.leftovers,
                &report.preserved,
            ) {
                return Err(WizardError::PhaseFailed.exit_code());
            }
            Err(code)
        }
    }
}

/// F3..F8 + el punto único de rollback: cualquier salida no-cero deshace lo
/// aplicado.
fn run_phases_and_rollback(
    vault_path: &VaultPath,
    payload: &PayloadArgs,
    flags: RunFlags,
    ui: &dyn Ui,
    stdout: &mut dyn std::io::Write,
    stderr: &mut dyn std::io::Write,
    snapshot: &InstallSnapshot,
) -> u8 {
    let code = run_phases(vault_path, payload, flags, ui, stdout, stderr);
    if code != 0 {
        let report = rollback_install(vault_path.as_path(), snapshot);
        if !announce_rollback(
            stderr,
            &report.compensated,
            &report.leftovers,
            &report.preserved,
        ) {
            // P0-1: no se afirma lo que no se midió; si quedan restos, se
            // devuelve el código de fase fallida, no el del fallo original.
            return WizardError::PhaseFailed.exit_code();
        }
    }
    code
}

/// Escribe el resultado MEDIDO del rollback (P0-1). Devuelve `true` cuando no
/// quedó ningún resto; `preserved` nunca cuenta como resto.
fn announce_rollback(
    stderr: &mut dyn std::io::Write,
    compensated: &[String],
    leftovers: &[String],
    preserved: &[String],
) -> bool {
    if !compensated.is_empty() {
        let _ = writeln!(stderr, "install: deshecho: {}", compensated.join(", "));
    }
    if !preserved.is_empty() {
        let _ = writeln!(
            stderr,
            "install: se conservó {} (no era del instalador)",
            preserved.join(", ")
        );
    }
    if leftovers.is_empty() {
        let _ = writeln!(
            stderr,
            "install: rollback aplicado — el vault quedó como estaba (verificado)"
        );
        true
    } else {
        let _ = writeln!(
            stderr,
            "install: rollback INCOMPLETO — quedan restos: {}",
            leftovers.join(", ")
        );
        false
    }
}

/// Shared `--payload*` usage validation (`install` + `update`, exit 2, no
/// network touched). An EMPTY value is a typo, not an absent flag — filtering
/// it out used to turn `--payload-url "$URL"` with an empty `$URL` into a
/// silent release download.
pub(crate) fn validate_payload_flags(
    command: &str,
    payload: Option<&str>,
    url: Option<&str>,
    sha: Option<&str>,
    stderr: &mut dyn std::io::Write,
) -> Result<(), u8> {
    for (flag, value) in [
        ("--payload", payload),
        ("--payload-url", url),
        ("--payload-sha256", sha),
    ] {
        if value.is_some_and(|v| v.trim().is_empty()) {
            let _ = writeln!(
                stderr,
                "{command}: {flag} got an empty value (a shell variable that expanded to \
                 nothing?); pass a real value, or drop the flag"
            );
            return Err(2);
        }
    }
    if payload.is_some() && (url.is_some() || sha.is_some()) {
        let _ = writeln!(
            stderr,
            "{command}: --payload conflicts with --payload-url/--payload-sha256 \
             (local tree or release asset, not both)"
        );
        return Err(2);
    }
    if url.is_some() != sha.is_some() {
        let _ = writeln!(
            stderr,
            "{command}: --payload-url needs --payload-sha256 (and vice versa)"
        );
        return Err(2);
    }
    Ok(())
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
