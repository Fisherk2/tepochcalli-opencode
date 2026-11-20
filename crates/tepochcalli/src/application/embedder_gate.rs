//! Gate `test-embed` y snapshot del modelo (F6/T6c, D59).
//!
//! Ejecuta `venv python -m tepochcalli_flow embed-check --model <id>
//! [--revision <sha>]` y verifica que `<models>/<slug>@<sha>/` quedó
//! materializado antes de escribir la config.

use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

use crate::domain::{CancelToken, WizardError};
use crate::ports::CommandRunner;

use super::flow_cli::MODELS_DIR;
use super::flow_contract::{spawn_gate, GateOk};
use super::installer::RUNTIME_DIR;

/// Runs `venv python -m tepochcalli_flow embed-check --model <id> [--revision
/// <sha>]` (spawn trunk + parser del contrato compartido, T11/S5). `ok:false`
/// is the portero verdict (`E_MODEL_INVALID`); a crashed/garbled gate is
/// `PhaseFailed`.
pub(super) fn run_gate(
    proc: &dyn CommandRunner,
    vault: &Path,
    model_id: &str,
    revision: Option<&str>,
    token: Option<&str>,
    cancel: Option<&CancelToken>,
) -> Result<GateOk, WizardError> {
    let out = spawn_gate(proc, vault, model_id, revision, token, cancel)?;
    parse_gate(&out.stdout)
}

/// Gate cancelable (R-offline-2): una cancelación purga los snapshots que la
/// descarga dejó a medias y NADA MÁS. Un gate roto conserva el comportamiento
/// actual (sin purga: puede no haber descargado nada).
pub(super) fn run_gate_cancellable(
    proc: &dyn CommandRunner,
    vault: &Path,
    model_id: &str,
    revision: Option<&str>,
    token: Option<&str>,
    cancel: &CancelToken,
) -> Result<GateOk, WizardError> {
    let before = models_snapshot(vault);
    match run_gate(proc, vault, model_id, revision, token, Some(cancel)) {
        Err(WizardError::UserAborted) => {
            purge_partials(vault, &before);
            Err(WizardError::UserAborted)
        }
        other => other,
    }
}

/// Nombres de los snapshots de `models/` antes del gate (R-offline-2).
pub(super) fn models_snapshot(vault: &Path) -> BTreeSet<String> {
    std::fs::read_dir(vault.join(RUNTIME_DIR).join(MODELS_DIR))
        .map(|entries| {
            entries
                .flatten()
                .map(|entry| entry.file_name().to_string_lossy().into_owned())
                .collect()
        })
        .unwrap_or_default()
}

/// Borra SOLO los snapshots que no estaban antes: un modelo previo legítimo
/// nunca se toca. Errores de fs se ignoran (higiene, no dato del usuario).
pub(super) fn purge_partials(vault: &Path, before: &BTreeSet<String>) {
    let dir = vault.join(RUNTIME_DIR).join(MODELS_DIR);
    let Ok(entries) = std::fs::read_dir(&dir) else {
        return;
    };
    for entry in entries.flatten() {
        let name = entry.file_name().to_string_lossy().into_owned();
        if !before.contains(&name) {
            let _ = std::fs::remove_dir_all(entry.path());
        }
    }
}

/// `BAAI/bge-m3` → `BAAI__bge-m3`: un id con `/` no puede anidar el
/// directorio del snapshot. Espejo de `tepochcalli_flow.config.model_slug`.
fn model_slug(model: &str) -> String {
    model.replace('/', "__")
}

/// Snapshot estable del modelo: `<vault>/.tepochcalli/models/<slug>@<sha>/` —
/// la MISMA fórmula que `tepochcalli_flow.config.Config.embedding_model_path`
/// (write y read cargan ese path, D59).
fn model_dir(vault: &Path, model: &str, revision: &str) -> PathBuf {
    vault
        .join(RUNTIME_DIR)
        .join(MODELS_DIR)
        .join(format!("{}@{revision}", model_slug(model)))
}

/// `true` cuando el directorio existe y NO está vacío (misma regla que
/// `tepochcalli_flow.model_store.is_materialized`).
fn is_materialized(dir: &Path) -> bool {
    dir.is_dir()
        && std::fs::read_dir(dir)
            .map(|mut entries| entries.next().is_some())
            .unwrap_or(false)
}

/// AC T6(c): tras un gate `ok`, el snapshot debe estar materializado. Sin SHA
/// (la API de HF no respondió: el CLI heredó el default del vault) no se puede
/// nombrar el directorio — basta un `<slug>@*` no vacío.
pub(super) fn verify_materialized(
    vault: &Path,
    model: &str,
    revision: Option<&str>,
) -> Result<(), WizardError> {
    let ok = match revision {
        Some(sha) => is_materialized(&model_dir(vault, model, sha)),
        None => {
            let prefix = format!("{}@", model_slug(model));
            std::fs::read_dir(vault.join(RUNTIME_DIR).join(MODELS_DIR))
                .map(|entries| {
                    entries.flatten().any(|entry| {
                        entry.file_name().to_string_lossy().starts_with(&prefix)
                            && is_materialized(&entry.path())
                    })
                })
                .unwrap_or(false)
        }
    };
    if ok {
        Ok(())
    } else {
        // El gate dijo `ok` pero no dejó snapshot: fallo de fase. `main` lo
        // compensa a la salida 5 (config `none`) — nunca media config.
        Err(WizardError::PhaseFailed)
    }
}

fn parse_gate(body: &str) -> Result<GateOk, WizardError> {
    super::flow_contract::parse_gate(body)
}

#[cfg(test)]
mod tests {
    use super::{is_materialized, model_dir, models_snapshot, parse_gate, purge_partials};

    /// R-offline-2: la purga borra SOLO lo que nació durante la descarga
    /// cancelada; un snapshot previo del usuario sobrevive intacto.
    #[test]
    fn purge_partials_removes_only_the_new_snapshot() {
        let Ok(vault) = tempfile::tempdir() else {
            panic!("tempdir");
        };
        let models = vault.path().join(".tepochcalli").join("models");
        let old = models.join("old@sha");
        let new = models.join("new@sha");
        if let Err(err) = std::fs::create_dir_all(&old) {
            panic!("mkdir old: {err}");
        }
        // Snapshot ANTES del gate: solo `old@sha` existía.
        let before = models_snapshot(vault.path());
        if let Err(err) = std::fs::create_dir_all(&new) {
            panic!("mkdir new: {err}");
        }
        purge_partials(vault.path(), &before);
        assert!(old.is_dir(), "un modelo previo legítimo nunca se toca");
        assert!(
            !new.exists(),
            "el parcial de la descarga cancelada se borra"
        );
    }

    /// Sin `models/` (vault recién creado) no hay nada que purgar ni que
    /// romper: el snapshot es vacío y la purga es un no-op.
    #[test]
    fn purge_partials_tolerates_a_missing_models_dir() {
        let Ok(vault) = tempfile::tempdir() else {
            panic!("tempdir");
        };
        let before = models_snapshot(vault.path());
        assert!(before.is_empty());
        purge_partials(vault.path(), &before);
    }

    /// El path estable del snapshot es el MISMO que resuelven write y read del
    /// flow (`config.py`: `model_slug` + `embedding_model_path`). Los dos
    /// literales son los SHAs de `presets.toml`; si la fórmula cambia en un
    /// lado, este test lo dice antes de que el read path devuelva
    /// `E_MODEL_INVALID`.
    #[test]
    fn model_dir_is_the_flow_snapshot_path() {
        let vault = std::path::Path::new("/v");
        assert_eq!(
            model_dir(
                vault,
                "paraphrase-multilingual-MiniLM-L12-v2",
                "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
            ),
            vault.join(".tepochcalli").join("models").join(
                "paraphrase-multilingual-MiniLM-L12-v2@e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
            )
        );
        // Un id con `/` es UN nivel de directorio, no una ruta anidada.
        assert_eq!(
            model_dir(vault, "BAAI/bge-m3", "5617a9f"),
            vault
                .join(".tepochcalli")
                .join("models")
                .join("BAAI__bge-m3@5617a9f")
        );
    }

    /// Regla de `model_store.is_materialized`: directorio presente **y** con
    /// algo dentro. El vacío (o el ausente) no cuenta.
    #[test]
    fn is_materialized_needs_a_non_empty_dir() {
        let Ok(vault) = tempfile::tempdir() else {
            panic!("tempdir");
        };
        let dir = model_dir(
            vault.path(),
            "paraphrase-multilingual-MiniLM-L12-v2",
            "abc123",
        );
        assert!(!is_materialized(&dir), "ausente no está materializado");
        if let Err(err) = std::fs::create_dir_all(&dir) {
            panic!("mkdir: {err}");
        }
        assert!(!is_materialized(&dir), "un directorio vacío no cuenta");
        if let Err(err) = std::fs::write(dir.join("config.json"), b"{}") {
            panic!("write: {err}");
        }
        assert!(is_materialized(&dir), "con contenido sí está materializado");
    }

    #[test]
    fn gate_ok_parses_model_dims_and_rss() {
        match parse_gate("{\"ok\":true,\"model\":\"m\",\"dims\":384,\"rss_peak_bytes\":650000000}")
        {
            Ok(gate) => {
                assert_eq!(gate.model, "m");
                assert_eq!(gate.dims, 384);
                assert_eq!(gate.rss_peak_bytes, 650_000_000);
            }
            Err(err) => panic!("valid gate must parse, got: {err:?}"),
        }
    }

    #[test]
    fn gate_false_is_model_invalid_and_garbage_is_phase_failed() {
        match parse_gate("{\"ok\":false,\"code\":\"E_MODEL_INVALID\"}") {
            Err(crate::domain::WizardError::ModelInvalid) => {}
            other => panic!("portero must reject, got: {other:?}"),
        }
        match parse_gate("not json at all") {
            Err(crate::domain::WizardError::PhaseFailed) => {}
            other => panic!("garbled gate must fail the phase, got: {other:?}"),
        }
    }
}
