//! T14: install state (`.install-state` marker), compensation of
//! F3/F6/F7-support helpers and the offline guard — everything `--resume`
//! consults. Re-exported through `application::installer`; the historical
//! public paths do not change.

use std::path::{Path, PathBuf};

use crate::domain::{Phase, WizardError};

use super::embedder_menu::config_path;
use super::installer::{runtime_dir, INSTALL_INTENT_PATH, UV_BIN_DIR, VENV_DIR_NAME};
use super::phase7::index_meta_path;
use super::text::provider_is_none;

/// Marker listing completed phases (`F3`.. one per line); D21 resolves
/// `--resume` as artifacts + this marker, never a re-download.
pub const INSTALL_STATE_PATH: &str = ".tepochcalli/.install-state";
/// F8 entry the resume check looks for in `opencode.json`.
const MANAGED_RAG_KEY: &str = "tepochcalli-rag";

/// F1 compensation: no-op — F1 never writes (T7).
pub fn compensate_phase1(_vault: &Path) {}

/// F2 compensation: no-op — F2 reuses the dir, never wipes (T7).
pub fn compensate_phase2(_vault: &Path) {}

/// F3 compensation: remove exactly the files `.install-intent` lists, prune
/// the directories that quedaron vacíos y retira el intent. Pre-existing user
/// files were never listed, so they survive; missing entries are a no-op.
///
/// Un residuo que el intent NO lista (F3 murió antes de escribirlo) no se
/// puede distinguir desde aquí; por eso `rollback_install` lo mide contra el
/// snapshot y lo reporta como resto.
pub fn compensate_phase3(vault: &Path) {
    let intent = vault.join(INSTALL_INTENT_PATH);
    let body = std::fs::read_to_string(&intent).unwrap_or_default();
    for line in body.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        let mut target = vault.to_path_buf();
        for part in trimmed.split('/') {
            if part.is_empty() || part == "." || part == ".." {
                continue;
            }
            target.push(part);
        }
        if std::fs::remove_file(&target).is_ok() {
            prune_empty_ancestors(vault, &target);
        }
    }
    let _ = std::fs::remove_file(&intent);
}

/// Sube desde `target` podando directorios VACÍOS; `remove_dir` se niega si
/// tienen algo, y esa negativa es la guarda que protege el contenido del
/// usuario. Nunca toca el vault.
fn prune_empty_ancestors(vault: &Path, target: &Path) {
    let mut current = target.parent();
    while let Some(dir) = current {
        if dir == vault || std::fs::remove_dir(dir).is_err() {
            break;
        }
        current = dir.parent();
    }
}

/// Record `phase` as done in the marker (idempotent: no duplicate lines).
pub fn mark_phase_done(vault: &Path, phase: Phase) {
    let state = vault.join(INSTALL_STATE_PATH);
    if let Some(parent) = state.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    let mut done = completed_from_marker(vault);
    if !done.contains(&phase) {
        done.push(phase);
        done.sort_by_key(|phase: &Phase| phase.order_index());
        let mut body = String::new();
        for phase in &done {
            body.push_str(phase.name());
            body.push('\n');
        }
        let _ = std::fs::write(&state, body);
    }
}

/// Phases the marker file records (never fails: missing file ⇒ empty).
fn completed_from_marker(vault: &Path) -> Vec<Phase> {
    let body = std::fs::read_to_string(vault.join(INSTALL_STATE_PATH)).unwrap_or_default();
    let mut out = Vec::new();
    for line in body.lines() {
        let phase = match line.trim() {
            "F1" => Phase::F1,
            "F2" => Phase::F2,
            "F3" => Phase::F3,
            "F4" => Phase::F4,
            "F5" => Phase::F5,
            "F6" => Phase::F6,
            "F7" => Phase::F7,
            "F8" => Phase::F8,
            _ => continue,
        };
        if !out.contains(&phase) {
            out.push(phase);
        }
    }
    out
}

fn venv_python_candidates(vault: &Path) -> [PathBuf; 2] {
    let runtime = runtime_dir(vault);
    [
        runtime.join(VENV_DIR_NAME).join("bin/python"),
        runtime.join(VENV_DIR_NAME).join("Scripts/python.exe"),
    ]
}

/// Verdict of the artifact check for one phase: `Done` skips (el artefacto
/// corrobora), `Indeterminate` defers to the marker (no decidible), `Missing`
/// FUERZA el re-run (L3-3: lo borrado se re-instala; el marker solo no salta).
enum ArtifactProbe {
    Done,
    Indeterminate,
    Missing,
}

/// Artifact check per phase (D21 + L3-3). F1/F2 have no artifact
/// (Indeterminate: the marker mandates). F8 distinguishes "el fichero no
/// existe" (Missing) de un JSON ilegible (Indeterminate).
fn phase_artifact_probe(vault: &Path, phase: Phase) -> ArtifactProbe {
    match phase {
        Phase::F1 | Phase::F2 => ArtifactProbe::Indeterminate,
        Phase::F3 => {
            if vault.join(INSTALL_INTENT_PATH).is_file() {
                ArtifactProbe::Done
            } else {
                ArtifactProbe::Missing
            }
        }
        Phase::F4 => {
            let runtime = runtime_dir(vault);
            let uv_present = runtime.join(UV_BIN_DIR).join("uv").is_file()
                || runtime.join(UV_BIN_DIR).join("uv.exe").is_file();
            if uv_present {
                ArtifactProbe::Done
            } else {
                ArtifactProbe::Missing
            }
        }
        Phase::F5 => {
            if venv_python_candidates(vault)
                .iter()
                .any(|candidate| candidate.is_file())
            {
                ArtifactProbe::Done
            } else {
                ArtifactProbe::Missing
            }
        }
        Phase::F6 => {
            if config_path(vault).is_file() {
                ArtifactProbe::Done
            } else {
                ArtifactProbe::Missing
            }
        }
        Phase::F7 => {
            if index_meta_path(vault).is_file() {
                return ArtifactProbe::Done;
            }
            // Path 5 leaves no index by design: config `none` ⇒ F7 is done.
            match std::fs::read_to_string(config_path(vault)) {
                Ok(body) if provider_is_none(&body) => ArtifactProbe::Done,
                _ => ArtifactProbe::Missing,
            }
        }
        Phase::F8 => match std::fs::read_to_string(vault.join("opencode.json")) {
            Ok(body) if body.contains(MANAGED_RAG_KEY) => ArtifactProbe::Done,
            Ok(_) => ArtifactProbe::Missing,
            Err(err) if err.kind() == std::io::ErrorKind::NotFound => ArtifactProbe::Missing,
            Err(_) => ArtifactProbe::Indeterminate,
        },
    }
}

/// Marker ∪ artifacts, in execution order: what `--resume` may skip.
#[must_use]
pub fn completed_phases(vault: &Path) -> Vec<Phase> {
    let mut done = completed_from_marker(vault);
    for phase in Phase::all() {
        if !done.contains(&phase)
            && matches!(phase_artifact_probe(vault, phase), ArtifactProbe::Done)
        {
            done.push(phase);
        }
    }
    done.sort_by_key(|phase: &Phase| phase.order_index());
    done
}

/// `true` when `--resume` may skip `phase` (L3-3 artifact-first):
/// - F1/F2 solo marker (sin artefacto que chequear).
/// - F3..F8: el artefacto presente salta; si el chequeo es indeterminable
///   manda el marker; si el artefacto falta NO hay skip (el marker ya no
///   oculta una fase cuyo producto se borró).
#[must_use]
pub fn is_phase_done(vault: &Path, phase: Phase) -> bool {
    let marker = completed_from_marker(vault).contains(&phase);
    match phase_artifact_probe(vault, phase) {
        ArtifactProbe::Done => true,
        ArtifactProbe::Indeterminate => marker,
        ArtifactProbe::Missing => false,
    }
}

/// Offline pre-check (D7.3, brazos OR L3-5), ANTES de tocar el vault: sin
/// nada con que trabajar offline es un fallo limpio `E_OFFLINE_NO_CACHE`
/// (exit 21), nunca un half-write. Dos brazos válidos:
/// 1. payload local + cache de modelo — `(payload_local_ready && cache_ready)`
///    (o ruta artificial skip);
/// 2. un resume cuyo payload ya está local — `resume_payload_local` (F3 por
///    artefacto: la descarga no va a repetirse).
pub fn guard_offline_before_touch(
    offline: bool,
    payload_local_ready: bool,
    cache_ready: bool,
    resume_payload_local: bool,
) -> Result<(), WizardError> {
    if offline && !(payload_local_ready && cache_ready) && !resume_payload_local {
        return Err(WizardError::OfflineNoCache);
    }
    Ok(())
}

/// `true` when `flag` points at an existing local payload tree
/// (`--payload <ruta>` for dev/tests; the T19 release asset is the online path).
#[must_use]
pub fn payload_local_ready(flag: Option<&str>) -> bool {
    match flag {
        Some(raw) if !raw.trim().is_empty() => Path::new(raw.trim()).is_dir(),
        _ => false,
    }
}
