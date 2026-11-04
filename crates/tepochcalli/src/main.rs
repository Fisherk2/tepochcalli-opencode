//! `tepochcalli` entrypoint: hand-rolled argv dispatch (no clap until T6).
//!
//! `install` runs F1→F2 for real (T7) + F3 payload merge (T8) + F4 `uv`
//! bootstrap and F5 venv/`sync` (T9) + F6 embedder menu (T11) + F7 initial
//! index (T12); `config embedder` runs the D8.4 atomic swap (T16);
//! `reindex --confirm` rebuilds the index (T17) and `uninstall` removes the
//! runtime (T17).

use std::io::IsTerminal;
use std::path::Path;
use std::process::ExitCode;

use tepochcalli::adapters::UreqHttpClient;
use tepochcalli::adapters::{
    fetch_release_payload, mirror_http_non_loopback, path_dirs, release_base_url, HeadlessUi,
    LocalPayload, ReleasePayload, StdCommandRunner, SysHostProbe, TtyUi,
};
use tepochcalli::application::failure::{
    log_path_in, now_secs, secrets_from_vault, state_dir, write_failure_log,
};
use tepochcalli::application::text::or_fallback;
use tepochcalli::application::{
    check_prereqs_on, compensate_phase3, compensate_phase6, compensate_phase7, ensure_vault_dir,
    guard_offline_before_touch, is_phase_done, litellm_config_present, mark_phase_done,
    payload_local_ready, read_completed_report, resolve_vault_dir, run_phase3, run_phase4,
    run_phase5, run_phase6, run_phase7, run_phase8, run_reindex, run_swap, run_uninstall,
    Phase6Deps, Phase6Report, SwapDeps, SwapOptions,
};
use tepochcalli::domain::failure::{failure_body, failure_title, redact};
use tepochcalli::domain::{EmbedderChoice, Phase, VaultPath, WizardError};
use tepochcalli::{ports::Ui, EMBEDDER_PATHS};

const VERSION: &str = env!("CARGO_PKG_VERSION");

fn usage_top() -> &'static str {
    "Usage: tepochcalli <command> [options]\n\
     \n\
     Commands:\n  \
     install            install a vault\n  \
     config embedder    pick the embedding provider\n  \
     reindex            rebuild the index\n  \
     uninstall          remove the runtime\n\
     \n\
     Options:\n  \
     --help     print this help\n  \
     --version  print the version\n"
}

fn usage_for(command: &str) -> String {
    if command == "install" {
        return "Usage: tepochcalli install [options]\n\
         \nOptions:\n  \
         --non-interactive  never prompt; a missing answer is a typed error\n  \
         --skip-model       preselect \"configure later\" (degraded, no index)\n  \
         --vault <ruta>     vault directory (asked interactively if omitted)\n  \
         --payload <ruta>   local payload tree (dev/tests; default: the\n  \
         versioned release asset for this binary (one-version rule))\n  \
         --payload-url <url>   override the release asset URL (dev/tests;\n  \
         needs --payload-sha256)\n  \
         --payload-sha256 <hex>  expected SHA-256 for --payload-url\n  \
         --resume           skip phases already done (artifacts + .install-state)\n  \
         --offline          no network: local payload + cached model only\n  \
         --help     print this help\n  \
         --version  print the version\n"
            .to_string();
    }
    if command == "config embedder" {
        return "Usage: tepochcalli config embedder [options]\n\
         \nOptions:\n  \
         --vault <ruta>      vault directory (asked interactively if omitted)\n  \
         --non-interactive  never prompt; a missing answer is a typed error\n  \
         --confirm          mandatory: the swap rebuilds the whole index\n  \
         --keep-previous    retain the previous model cache (no auto-GC)\n  \
         --help     print this help\n  \
         --version  print the version\n"
            .to_string();
    }
    if command == "reindex" {
        return "Usage: tepochcalli reindex [options]\n\
         \nOptions:\n  \
         --confirm          mandatory: the rebuild is destructive (full re-index)\n  \
         --vault <ruta>     vault directory (asked interactively if omitted)\n  \
         --non-interactive  never prompt; a missing answer is a typed error\n  \
         --help     print this help\n  \
         --version  print the version\n"
            .to_string();
    }
    if command == "uninstall" {
        return "Usage: tepochcalli uninstall [options]\n\
         \nOptions:\n  \
         --vault <ruta>     vault directory (asked interactively if omitted)\n  \
         --confirm          mandatory: the uninstall removes the whole runtime\n  \
         --non-interactive  never prompt; a missing answer is a typed error\n  \
         --help     print this help\n  \
         --version  print the version\n"
            .to_string();
    }
    format!(
        "Usage: tepochcalli {command} [options]\n\
         \nOptions:\n  \
         --help     print this help\n  \
         --version  print the version\n"
    )
}

fn print_help(stdout: &mut dyn std::io::Write, command: Option<&str>) {
    match command {
        None => {
            let _ = stdout.write_all(usage_top().as_bytes());
        }
        Some(cmd) => {
            let _ = stdout.write_all(usage_for(cmd).as_bytes());
        }
    }
}

fn print_version(stdout: &mut dyn std::io::Write) {
    let _ = writeln!(stdout, "tepochcalli {VERSION}");
}

/// T17 failure exit (reindex/uninstall): same shared `report()` shape
/// (panel on stderr + redacted log outside the vault), but the title/body
/// carry the real command — never the install retry line, which would point
/// at the wrong fix.
fn report_maintenance_failure(
    ui: &dyn Ui,
    command: &str,
    context: &str,
    err: WizardError,
    vault: Option<&Path>,
) -> u8 {
    let owned: Vec<String> = vault.map(secrets_from_vault).unwrap_or_default();
    let log_path = log_path_in(&state_dir(), now_secs());
    let title = format!("{command} failed");
    let mut body = format!("cause: {context}: {err}\n");
    if let Some(code) = err.e_star() {
        body.push_str(&format!("code: {code}\n"));
    }
    body.push_str(&format!("log: {}\n", log_path.display()));
    report(ui, &title, body, &owned, err.exit_code())
}

fn unknown(stderr: &mut dyn std::io::Write, arg: &str) -> u8 {
    let _ = writeln!(stderr, "unknown subcommand: {arg}");
    let _ = stderr.write_all(usage_top().as_bytes());
    2
}

fn bare_config(stderr: &mut dyn std::io::Write) -> u8 {
    let _ = stderr.write_all(usage_top().as_bytes());
    let _ = writeln!(stderr, "Usage: tepochcalli config <embedder> [options]");
    2
}

/// Shared T15/T17 failure exit (S-3): best-effort redacted log under the OS
/// state dir (never the vault) + redacted stderr panel via the `Ui` port.
/// `title`/`body` arrive composed by the caller (install keeps the graded
/// `failure_title/failure_body` shapes; maintenance names its own command
/// and carries no install retry line); the typed exit code is returned
/// unchanged.
fn report(ui: &dyn Ui, title: &str, body: String, secrets: &[String], code: u8) -> u8 {
    let masked: Vec<&str> = secrets.iter().map(String::as_str).collect();
    let log_path = log_path_in(&state_dir(), now_secs());
    write_failure_log(&log_path, &redact(&format!("{title}\n{body}"), &masked));
    ui.panel(title, &redact(&body, &masked));
    code
}

/// Centralized install-failure exit (T15): log + `failure_*` panel shape.
fn report_failure(
    ui: &dyn Ui,
    phase: Option<Phase>,
    context: &str,
    err: WizardError,
    vault: Option<&Path>,
) -> u8 {
    let owned: Vec<String> = vault.map(secrets_from_vault).unwrap_or_default();
    let masked: Vec<&str> = owned.iter().map(String::as_str).collect();
    let log_path = log_path_in(&state_dir(), now_secs());
    let title = failure_title(phase);
    let body = failure_body(context, phase, err, &log_path, &masked);
    report(ui, &title, body, &owned, err.exit_code())
}

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
fn run_install(
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
fn offline_map(offline: bool, err: WizardError) -> WizardError {
    if offline && err == WizardError::NetDownload {
        WizardError::OfflineNoCache
    } else {
        err
    }
}

/// F6 with T14(f) fallback: any failure but an explicit abort (or a missing
/// offline cache) compensates to salida 5 — a COMPLETE degraded install.
fn run_f6_or_degraded(
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

/// F3..F8 with `--resume` skips (marker + artifacts, never a re-download).
#[allow(clippy::too_many_arguments)]
fn run_phases(
    path: &VaultPath,
    payload_dir: Option<String>,
    payload_url: Option<String>,
    payload_sha256: Option<String>,
    resume: bool,
    offline: bool,
    non_interactive: bool,
    ui: &dyn Ui,
    stdout: &mut dyn std::io::Write,
    stderr: &mut dyn std::io::Write,
) -> u8 {
    // L4-2 security del mirror: la rama release (sin `--payload`/override)
    // con base http NO-loopback exige consentimiento TUI en interactivo y
    // es fallo tipado en non-interactive. Decidido antes de tocar transporte.
    let release_path = payload_dir.is_none() && payload_url.is_none();
    let base = if release_path {
        release_base_url()
    } else {
        String::new()
    };
    let mirror_http = release_path && mirror_http_non_loopback(&base);
    if mirror_http {
        if non_interactive {
            let _ = writeln!(
                stderr,
                "install: mirror http no-loopback ({base}) exige transporte sin TLS; \
                 en --non-interactive no hay confirmación posible"
            );
            return report_failure(
                ui,
                Some(Phase::F3),
                "install: mirror http sin consentimiento",
                WizardError::UserAborted,
                Some(path.as_path()),
            );
        }
        // Sin respuesta clara (Esc/Ctrl-C): abortar — nunca confiar.
        let choice = ui
            .select(
                "Mirror http (sin TLS) detectado",
                &[
                    "Abortar (recomendado)",
                    "Confiar en este mirror para esta instalación",
                ],
                0,
            )
            .unwrap_or_default();
        if choice != 1 {
            let _ = writeln!(stderr, "install: el mirror http non-loopback se rechazó");
            return report_failure(
                ui,
                Some(Phase::F3),
                "install: mirror http rechazado por el usuario",
                WizardError::UserAborted,
                Some(path.as_path()),
            );
        }
        let _ = writeln!(
            stderr,
            "payload: mirror http autorizado por el usuario: {base}"
        );
    }
    // The HTTP client lives before F3 now: the online payload source (T19)
    // needs it, the local one ignores it. L4-2: https_only salvo mirror
    // http autorizado (el guard del client deja pasar loopback siempre).
    let http = UreqHttpClient::with_https_only(!mirror_http);
    // F3: merge the payload without overwrite (placeholders + intent).
    // Source priority: `--payload` (local tree, dev/tests) →
    // `--payload-url` + `--payload-sha256` (override, dev/tests) →
    // the versioned release asset for this binary (one-version rule).
    // L3-5: bajo `--resume` con F3 resuelta por artefacto el payload ya está
    // local — ni guard ni fetch de red; es el mismo brazo del guard offline.
    let resume_covers_payload = resume && is_phase_done(path.as_path(), Phase::F3);
    let online: Option<ReleasePayload> = match (&payload_url, &payload_sha256) {
        (Some(url), Some(sha)) => Some(ReleasePayload::new(url, sha)),
        (None, None) if payload_dir.is_none() => {
            if resume_covers_payload {
                // Payload ya local (F3 por artefacto): ninguna red en un resume.
                None
            } else {
                match fetch_release_payload(&http, VERSION) {
                    Ok(release) => {
                        let _ = writeln!(
                            stderr,
                            "payload: release asset {} (one-version {})",
                            release.url(),
                            VERSION
                        );
                        Some(release)
                    }
                    Err(err) => {
                        return report_failure(
                            ui,
                            Some(Phase::F3),
                            "install: phase F3 failed",
                            offline_map(offline, err),
                            Some(path.as_path()),
                        );
                    }
                }
            }
        }
        // `--payload` local tree: source lives in the F3 branch, not online.
        (None, None) => None,
        // Unreachable: `run_install` rejects a half override with exit 2.
        _ => return 2,
    };
    let skipped: Vec<std::path::PathBuf> = if resume && is_phase_done(path.as_path(), Phase::F3) {
        let _ = writeln!(stderr, "resume: F3 already done, skipping");
        Vec::new()
    } else {
        let outcome = match (&payload_dir, &online) {
            (Some(dir), None) => run_phase3(&LocalPayload::new(Path::new(dir)), path.as_path()),
            (None, Some(release)) => run_phase3(release, path.as_path()),
            // Unreachable: `run_install` rejects `--payload` + override.
            _ => return 2,
        };
        match outcome {
            Ok(report) => {
                mark_phase_done(path.as_path(), Phase::F3);
                report.skipped
            }
            Err(err) => {
                // L3-2: wiring del compensador antes del panel — un F3 que
                // falló a mitad deja el vault como al entrar, sin intent.
                compensate_phase3(path.as_path());
                return report_failure(
                    ui,
                    Some(Phase::F3),
                    "install: phase F3 failed",
                    err,
                    Some(path.as_path()),
                );
            }
        }
    };
    // V-5 contracción: en pipe una sola línea (count + muestra), en tty el detalle.
    if !skipped.is_empty() {
        if std::io::stderr().is_terminal() {
            for already in &skipped {
                let _ = writeln!(
                    stderr,
                    "warning: ya estaba (sin cambios): {}",
                    already.display()
                );
            }
        } else {
            let head = skipped
                .iter()
                .take(5)
                .map(|p| {
                    p.file_name()
                        .unwrap_or_default()
                        .to_string_lossy()
                        .into_owned()
                })
                .collect::<Vec<_>>()
                .join(", ");
            let _ = writeln!(
                stderr,
                "warning: {} ficheros ya estaban (sin cambios): {}…",
                skipped.len(),
                head
            );
        }
    }
    // F4: pinned `uv` into `.tepochcalli/bin/` (+ version proof).
    // Compensates itself on failure.
    let proc = StdCommandRunner;
    if resume && is_phase_done(path.as_path(), Phase::F4) {
        let _ = writeln!(stderr, "resume: F4 already done, skipping (uv cached)");
    } else {
        match run_phase4(&http, &proc, path.as_path()) {
            Ok(phase4) => {
                mark_phase_done(path.as_path(), Phase::F4);
                let _ = writeln!(stderr, "uv {} ready", phase4.version);
            }
            Err(err) => {
                let err = offline_map(offline, err);
                return report_failure(
                    ui,
                    Some(Phase::F4),
                    "install: phase F4 failed",
                    err,
                    Some(path.as_path()),
                );
            }
        }
    }
    // F5: venv + frozen sync + R6 import check. `bin/` stays when F5 fails
    // (each phase compensates only what it wrote).
    if resume && is_phase_done(path.as_path(), Phase::F5) {
        let _ = writeln!(stderr, "resume: F5 already done, skipping (venv cached)");
    } else {
        match run_phase5(&proc, path.as_path()) {
            Ok(_) => mark_phase_done(path.as_path(), Phase::F5),
            Err(err) => {
                let err = offline_map(offline, err);
                return report_failure(
                    ui,
                    Some(Phase::F5),
                    "install: phase F5 failed",
                    err,
                    Some(path.as_path()),
                );
            }
        }
    }
    // F6: embedder menu + test-embed gate + atomic config. `--skip-model`
    // preselects path 5 (configure later, degraded, no index).
    let deps = Phase6Deps {
        ui,
        host: &SysHostProbe,
        proc: &proc,
        http: &http,
    };
    let picked = if resume && is_phase_done(path.as_path(), Phase::F6) {
        match read_completed_report(path.as_path()) {
            Some(report) => {
                let _ = writeln!(stderr, "resume: F6 already done, skipping");
                report
            }
            None => match run_f6_or_degraded(&deps, path, offline, ui, stderr) {
                Ok(picked) => picked,
                Err(code) => return code,
            },
        }
    } else {
        match run_f6_or_degraded(&deps, path, offline, ui, stderr) {
            Ok(picked) => picked,
            Err(code) => return code,
        }
    };
    let _ = writeln!(
        stderr,
        "embedder: provider={} {}",
        picked.provider,
        picked.model.as_deref().unwrap_or("(none)")
    );
    // F7: initial index via the flow CLI. Path 5 short-circuits inside
    // `run_phase7` (no spawn, no index).
    if resume && is_phase_done(path.as_path(), Phase::F7) {
        let _ = writeln!(stderr, "resume: F7 already done, skipping");
    } else {
        match run_phase7(&proc, path.as_path(), &picked) {
            Ok(indexed) => {
                mark_phase_done(path.as_path(), Phase::F7);
                let _ = writeln!(
                    stderr,
                    "index: scanned={} indexed={} ({} ms)",
                    indexed.scanned, indexed.indexed, indexed.elapsed_ms
                );
            }
            Err(err) => {
                let err = offline_map(offline, err);
                // L3-2: wiring del compensador antes del panel — el sidecar
                // y su temp fuera; el índice queda sin metadatos huérfanos.
                compensate_phase7(path.as_path());
                return report_failure(
                    ui,
                    Some(Phase::F7),
                    "install: phase F7 failed",
                    err,
                    Some(path.as_path()),
                );
            }
        }
    }
    // F8: merge `mcp.servers` (+ `.bak`) and verify `rag_status` end to end.
    if resume && is_phase_done(path.as_path(), Phase::F8) {
        let _ = writeln!(stderr, "resume: F8 already done, skipping");
    } else {
        match run_phase8(&proc, path.as_path(), Some(ui)) {
            Ok(f8) => {
                mark_phase_done(path.as_path(), Phase::F8);
                let _ = writeln!(
                    stderr,
                    "mcp: tepochcalli-rag {} (rag_status={})",
                    if f8.changed {
                        "registered"
                    } else {
                        "up to date"
                    },
                    f8.health.as_str()
                );
            }
            Err(err) => {
                return report_failure(
                    ui,
                    Some(Phase::F8),
                    "install: phase F8 failed",
                    err,
                    Some(path.as_path()),
                );
            }
        }
    }
    let _ = writeln!(stdout, "{}", path.as_path().display());
    // Checklist degraded (4c-6): una salida 5 deja el RAG sin índice —
    // las órdenes exactas de re-entrada van en stdout (no se pierden entre
    // el ruido de stderr del install).
    if picked.provider == "none" {
        let _ = writeln!(
            stdout,
            "\n== RAG degradado: sin embedder (ruta 5) ==\n\
             El índice no se construyó. Re-entrada:\n  \
             1) tepochcalli config embedder --confirm\n  \
             2) tepochcalli reindex --confirm\n"
        );
    }
    0
}

/// `config embedder` (T16, D8.4): six-step atomic swap on an installed vault —
/// current-state display, same D7.1 menu, `--confirm` warning, gate + reindex,
/// atomic config/metadata switch, auto-GC unless `--keep-previous`.
fn run_config_embedder(
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
fn run_reindex_cmd(
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
/// `opencode.json`, `00-Resources/` and `.obsidian/` survive by construction
/// (the orchestrator never enumerates them). Idempotent: a missing runtime is
/// a no-op `Ok`, never an error.
fn run_uninstall_cmd(
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

/// Pure dispatch over argv (sans program name); returns the exit code.
fn run(args: &[String], stdout: &mut dyn std::io::Write, stderr: &mut dyn std::io::Write) -> u8 {
    let mut it = args.iter().map(String::as_str);
    let Some(first) = it.next() else {
        let _ = stderr.write_all(usage_top().as_bytes());
        return 2;
    };
    match first {
        "--help" => {
            print_help(stdout, None);
            0
        }
        "--version" => {
            print_version(stdout);
            0
        }
        "install" => run_install(it.collect(), stdout, stderr),
        "reindex" => run_reindex_cmd(it.collect(), stdout, stderr),
        "uninstall" => run_uninstall_cmd(it.collect(), stdout, stderr),
        "config" => match it.next() {
            None => bare_config(stderr),
            Some("--help") => {
                print_help(stdout, Some("config"));
                0
            }
            Some("--version") => {
                print_version(stdout);
                0
            }
            Some("embedder") => run_config_embedder(it.collect(), stdout, stderr),
            Some(sub) => {
                let _ = writeln!(stderr, "config: unknown subcommand: {sub}");
                bare_config(stderr)
            }
        },
        other => unknown(stderr, other),
    }
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let code = run(&args, &mut std::io::stdout(), &mut std::io::stderr());
    if code != 0 {
        std::process::exit(code.into());
    }
    ExitCode::SUCCESS
}
