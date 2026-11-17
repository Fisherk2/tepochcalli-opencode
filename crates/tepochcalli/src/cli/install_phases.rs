//! F3..F8 with `--resume` skips (marker + artifacts, never a re-download):
//! the sequential phase runner shared by every `install` invocation.

use std::io::IsTerminal;
use std::path::Path;

use tepochcalli::adapters::{
    fetch_release_payload, mirror_http_non_loopback, release_base_url, LocalPayload,
    ReleasePayload, StdCommandRunner, SysHostProbe, UreqHttpClient,
};
use tepochcalli::application::{
    compensate_phase3, compensate_phase7, is_phase_done, mark_phase_done, read_completed_report,
    run_phase3, run_phase4, run_phase5, run_phase7, run_phase8, Phase6Deps,
};
use tepochcalli::domain::{Phase, VaultPath, WizardError};
use tepochcalli::ports::Ui;

use super::install::{offline_map, run_f6_or_degraded};
use super::report::report_failure;
use super::usage::VERSION;

/// F3..F8 with `--resume` skips (marker + artifacts, never a re-download).
#[allow(clippy::too_many_arguments)]
pub(crate) fn run_phases(
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
