//! F3..F8 with `--resume` skips (marker + artifacts, never a re-download):
//! the sequential phase runner shared by every `install` invocation.

use std::io::IsTerminal;
use std::path::Path;

use tepochcalli::adapters::{
    fetch_release_payload, mirror_http_non_loopback, payload_asset_url, release_base_url,
    LocalPayload, ReleasePayload, StdCommandRunner, SysHostProbe, UreqHttpClient,
};
use tepochcalli::application::{
    compensate_phase3, compensate_phase7,
    embedder_menu::{preselect_embedder, take_preselected},
    is_phase_done, mark_phase_done, read_completed_report, run_phase3, run_phase4, run_phase5,
    run_phase7, run_phase8, Phase6Deps, Phase7Report,
};
use tepochcalli::domain::{CancelToken, Phase, VaultPath, WizardError};
use tepochcalli::ports::{advance_active_stage, set_active_progress, ProgressSpec, Ui};

use super::install::{offline_map, run_f6_or_degraded};
use super::report::{report_failure, report_usage_failure};
use super::usage::VERSION;

/// Marker-and-artifact skip for one phase: prints the resume note and
/// returns `true` when the caller may skip. Callers guard with `resume`
/// (`resume && resume_skip(...)`) so the note only prints on a real resume.
fn resume_skip(
    stderr: &mut dyn std::io::Write,
    path: &VaultPath,
    phase: Phase,
    note: &str,
) -> bool {
    let done = is_phase_done(path.as_path(), phase);
    if done {
        let _ = writeln!(
            stderr,
            "resume: {} already done, skipping{note}",
            phase.name()
        );
    }
    done
}

/// The `--payload*` triple (local tree, or URL override + sha).
pub(crate) struct PayloadArgs {
    pub dir: Option<String>,
    pub url: Option<String>,
    pub sha: Option<String>,
}

/// The three booleans that change how every phase runs.
#[derive(Clone, Copy)]
pub(crate) struct RunFlags {
    pub resume: bool,
    pub offline: bool,
    pub non_interactive: bool,
}

/// The one failure exit of F3..F8: same panel, phase and vault path; the
/// caller only decides the mapping (some phases are not offline-mapped).
fn phase_failed(ui: &dyn Ui, path: &VaultPath, phase: Phase, err: WizardError) -> u8 {
    report_failure(
        ui,
        Some(phase),
        &format!("install: phase {} failed", phase.name()),
        err,
        Some(path.as_path()),
    )
}

/// F3..F8 with `--resume` skips (marker + artifacts, never a re-download).
/// Una sola barra de siete hitos envuelve todas las fases; `run_cancellable`
/// sigue siendo la pantalla de cada fase, pero con la barra activa cede el
/// frame (ver `ui_ratatui::run_progress`) y el watcher exterior posee el token.
pub(crate) fn run_phases(
    path: &VaultPath,
    payload: &PayloadArgs,
    flags: RunFlags,
    ui: &dyn Ui,
    stdout: &mut dyn std::io::Write,
    stderr: &mut dyn std::io::Write,
) -> u8 {
    // El token es compartido por la barra y el gate de F6: cancelar desde la
    // pantalla detiene la descarga del modelo (R-offline-2).
    let cancel = CancelToken::new();
    let spec = install_progress_spec(format!("Instalando en {}", path.as_path().display()));
    let mut result = None;
    ui.run_stages(&spec, &cancel, &mut |progress| {
        set_active_progress(Some(progress));
        // T2: la elección de embedder es la PRIMERA interacción, todavía bajo
        // la barra única (T1). Con F6 ya resuelta por `--resume` no se pregunta
        // ni se consume una fila de la cola de `HeadlessUi::for_install`.
        let f6_cached = flags.resume && is_phase_done(path.as_path(), Phase::F6);
        let _ = take_preselected();
        if !f6_cached {
            if let Err(err) = preselect_embedder(ui, &SysHostProbe) {
                result = Some(phase_failed(ui, path, Phase::F6, err));
                set_active_progress(None);
                return;
            }
        }
        result = Some(run_phases_stages(
            path,
            payload,
            flags,
            ui,
            &mut *stdout,
            &mut *stderr,
            &cancel,
        ));
        set_active_progress(None);
    });
    result.unwrap_or(WizardError::Internal.exit_code())
}

/// Cuerpo de F3..F8 con el contador de la barra exterior.
fn run_phases_stages(
    path: &VaultPath,
    payload: &PayloadArgs,
    flags: RunFlags,
    ui: &dyn Ui,
    stdout: &mut dyn std::io::Write,
    stderr: &mut dyn std::io::Write,
    cancel: &CancelToken,
) -> u8 {
    // L4-2 security del mirror: la rama release (sin `--payload`/override)
    // con base http NO-loopback exige consentimiento TUI en interactivo y
    // es fallo tipado en non-interactive. Decidido antes de tocar transporte.
    let release_path = payload.dir.is_none() && payload.url.is_none();
    let base = if release_path {
        release_base_url()
    } else {
        String::new()
    };
    let mirror_http = release_path && mirror_http_non_loopback(&base);
    if mirror_http {
        if flags.non_interactive {
            let _ = writeln!(
                stderr,
                "install: mirror http no-loopback ({base}) exige transporte sin TLS; \
                 en --non-interactive no hay confirmación posible"
            );
            return report_usage_failure(
                ui,
                "install",
                Some(Phase::F3),
                "mirror http sin consentimiento",
                "un transporte TLS o aceptar el mirror en interactivo",
                "re-ejecuta sin --non-interactive o usa --payload/--payload-url https",
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
    let skip_f3 = flags.resume && resume_skip(stderr, path, Phase::F3, "");
    // Estado fuera de la pantalla alternativa: el asset que se va a intentar
    // se nombra ANTES de F3, así el camino de fallo también lo muestra.
    let announced_url = if skip_f3 {
        None
    } else {
        match (&payload.dir, &payload.url) {
            (None, Some(url)) => Some(url.clone()),
            (None, None) => Some(payload_asset_url(VERSION)),
            // `--payload` local tree: no release asset que nombrar.
            _ => None,
        }
    };
    if let Some(url) = &announced_url {
        let _ = writeln!(
            stderr,
            "payload: release asset {url} (one-version {})",
            VERSION
        );
    }
    let mut f3: Result<(Option<ReleasePayload>, Vec<std::path::PathBuf>), WizardError> =
        Err(WizardError::Internal);
    if !skip_f3 {
        ui.run_cancellable(
            &format!("Instalando F3 (payload) en {}", path.as_path().display()),
            &CancelToken::new(),
            &mut || {
                let online = match (&payload.url, &payload.sha) {
                    (Some(url), Some(sha)) => Ok(Some(ReleasePayload::new(url, sha))),
                    (None, None) if payload.dir.is_none() => fetch_release_payload(&http, VERSION)
                        .map(Some)
                        .map_err(|err| offline_map(flags.offline, err)),
                    // `--payload` local tree: source lives in the F3 branch.
                    (None, None) => Ok(None),
                    // Unreachable: `run_install` rejects a half override.
                    _ => Err(WizardError::Internal),
                };
                f3 = online.and_then(|online| {
                    let report = match (&payload.dir, &online) {
                        (Some(dir), None) => {
                            run_phase3(&LocalPayload::new(Path::new(dir)), path.as_path())
                        }
                        (None, Some(release)) => run_phase3(release, path.as_path()),
                        // Unreachable: `run_install` rejects `--payload` + override.
                        _ => return Err(WizardError::Internal),
                    }?;
                    mark_phase_done(path.as_path(), Phase::F3);
                    Ok((online, report.skipped))
                });
            },
        );
    }
    let (_, skipped) = if skip_f3 {
        (None, Vec::new())
    } else {
        match f3 {
            Ok(pair) => pair,
            Err(err) => {
                // L3-2: wiring del compensador antes del panel — un F3 que
                // falló a mitad deja el vault como al entrar, sin intent.
                compensate_phase3(path.as_path());
                return phase_failed(ui, path, Phase::F3, err);
            }
        }
    };
    advance_active_stage(); // hito 1/7: F3 payload
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
    let skip_f4 = flags.resume && resume_skip(stderr, path, Phase::F4, " (uv cached)");
    if !skip_f4 {
        let mut f4: Result<String, WizardError> = Err(WizardError::Internal);
        ui.run_cancellable(
            &format!("Instalando F4 (uv) en {}", path.as_path().display()),
            &CancelToken::new(),
            &mut || {
                f4 = run_phase4(&http, &proc, path.as_path()).map(|phase4| phase4.version);
            },
        );
        match f4 {
            Ok(version) => {
                mark_phase_done(path.as_path(), Phase::F4);
                let _ = writeln!(stderr, "{version} ready");
            }
            Err(err) => {
                return phase_failed(ui, path, Phase::F4, offline_map(flags.offline, err));
            }
        }
    }
    advance_active_stage(); // hito 2/7: F4 uv
                            // F5: venv + frozen sync + R6 import check. `bin/` stays when F5 fails
                            // (each phase compensates only what it wrote).
    let skip_f5 = flags.resume && resume_skip(stderr, path, Phase::F5, " (venv cached)");
    if !skip_f5 {
        let mut f5: Result<(), WizardError> = Err(WizardError::Internal);
        ui.run_cancellable(
            &format!("Instalando F5 (venv) en {}", path.as_path().display()),
            &CancelToken::new(),
            &mut || {
                f5 = run_phase5(&proc, path.as_path()).map(|_| ());
            },
        );
        match f5 {
            Ok(()) => mark_phase_done(path.as_path(), Phase::F5),
            Err(err) => {
                return phase_failed(ui, path, Phase::F5, offline_map(flags.offline, err));
            }
        }
    }
    advance_active_stage(); // hito 3/7: F5 venv
                            // F6: embedder menu + test-embed gate + atomic config. `--skip-model`
                            // preselects path 5 (configure later, degraded, no index).
    let deps = Phase6Deps {
        ui,
        host: &SysHostProbe,
        proc: &proc,
        http: &http,
        // Mismo token que la barra exterior: su watcher cancela la descarga.
        cancel: cancel.clone(),
    };
    // Descarta un aviso de gate de una corrida anterior en esta hebra (swap).
    let _ = tepochcalli::application::take_gate_stage();
    let cached = if flags.resume && is_phase_done(path.as_path(), Phase::F6) {
        read_completed_report(path.as_path())
    } else {
        None
    };
    if cached.is_some() {
        let _ = writeln!(stderr, "resume: F6 already done, skipping");
    }
    let mut degraded_cause = None;
    let picked = match cached {
        Some(report) => report,
        None => {
            match run_f6_or_degraded(&deps, path, flags.offline, ui, stderr, &mut degraded_cause) {
                Ok(picked) => picked,
                Err(code) => return code,
            }
        }
    };
    advance_active_stage(); // hito 4/7: F6 selección + config
                            // El punto de UI de `embedder_gate` marca el gate de descarga; aquí se
                            // consume el aviso. Sin descarga (resume / ruta 5) el hueco se cierra
                            // igual: 100 % significa trabajo terminado, no "gate ejecutado".
    let _ = tepochcalli::application::take_gate_stage();
    advance_active_stage(); // hito 5/7: gate de descarga
    if let Some(cause) = degraded_cause {
        // F6 degradado: panel + log con la causa real, SIN cambiar el exit 0.
        let context = format!("install: phase F6 failed ({})", cause.context());
        let _ = report_failure(
            ui,
            Some(Phase::F6),
            &context,
            cause.error,
            Some(path.as_path()),
        );
    }
    let _ = writeln!(
        stderr,
        "embedder: provider={} {}",
        picked.provider,
        picked.model.as_deref().unwrap_or("(none)")
    );
    // F7: initial index via the flow CLI. Path 5 short-circuits inside
    // `run_phase7` (no spawn, no index).
    let skip_f7 = flags.resume && resume_skip(stderr, path, Phase::F7, "");
    if !skip_f7 {
        let mut f7: Result<Phase7Report, WizardError> = Err(WizardError::Internal);
        ui.run_cancellable(
            &format!("Instalando F7 (índice) en {}", path.as_path().display()),
            &CancelToken::new(),
            &mut || {
                f7 = run_phase7(&proc, path.as_path(), &picked);
            },
        );
        match f7 {
            Ok(indexed) => {
                mark_phase_done(path.as_path(), Phase::F7);
                let _ = writeln!(
                    stderr,
                    "index: scanned={} indexed={} ({} ms)",
                    indexed.scanned, indexed.indexed, indexed.elapsed_ms
                );
            }
            Err(err) => {
                // L3-2: wiring del compensador antes del panel — el sidecar
                // y su temp fuera; el índice queda sin metadatos huérfanos.
                compensate_phase7(path.as_path());
                return phase_failed(ui, path, Phase::F7, offline_map(flags.offline, err));
            }
        }
    }
    advance_active_stage(); // hito 6/7: F7 índice
                            // F8: merge `mcp.servers` (+ `.bak`) and verify `rag_status` end to end.
    if flags.resume && resume_skip(stderr, path, Phase::F8, "") {
        // MCP registration already merged on a previous run.
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
                return phase_failed(ui, path, Phase::F8, err);
            }
        }
    }
    advance_active_stage(); // hito 7/7: F8 MCP
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

/// Spec de la barra del install: los siete hitos (F3, F4, F5, F6, gate de
/// descarga, F7, F8) sin ETA declarada — el install no conoce una estimación.
fn install_progress_spec(title: String) -> ProgressSpec {
    ProgressSpec {
        title,
        steps: 7,
        eta: None,
    }
}

#[cfg(test)]
mod tests {
    use super::install_progress_spec;

    #[test]
    fn install_declara_siete_hitos_sin_eta_inventada() {
        let spec = install_progress_spec("Instalando".to_string());
        assert_eq!(spec.steps, 7);
        assert!(spec.eta.is_none(), "sin estimación declarada, ETA —");
    }
}
