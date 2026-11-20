//! R-offline-3: deshacer una instalación fallida o cancelada.
//!
//! Orden inverso al de ejecución: primero lo que vive FUERA del runtime
//! (`opencode.json` de F8, payload y placeholders de F3) y después el
//! runtime. Dentro de él solo se compensan las fases que ESTA corrida
//! añadió más allá del snapshot; lo ya hecho antes se respeta. F6 se
//! restaura con los bytes del snapshot: `compensate_phase6` escribiría
//! `provider = "none"` (instalación degradada), prohibido por R-offline-4.
//! Los errores de fs se ignoran: es higiene tras un fallo ya reportado.

use std::collections::BTreeSet;
use std::path::Path;

use crate::domain::Phase;

use super::embedder_gate::{models_snapshot, purge_partials};
use super::embedder_menu::config_path;
use super::installer::{
    compensate_phase3, compensate_phase4, compensate_phase5, completed_phases, INSTALL_STATE_PATH,
    RESOURCES_DIR, RUNTIME_DIR,
};
use super::phase7::{compensate_phase7, index_meta_path};
use super::phase8::compensate_phase8;

/// Estado del vault justo ANTES del primer write de una corrida de install.
#[derive(Debug)]
pub struct InstallSnapshot {
    vault_existed: bool,
    runtime_existed: bool,
    resources_existed: bool,
    config: Option<Vec<u8>>,
    index_meta: Option<Vec<u8>>,
    state: Option<Vec<u8>>,
    completed: Vec<Phase>,
    models: BTreeSet<String>,
}

impl InstallSnapshot {
    /// Captura read-only (nunca crea nada). Se llama ANTES de
    /// `ensure_vault_dir`: un vault inexistente es un estado válido.
    #[must_use]
    pub fn capture(vault: &Path) -> Self {
        Self {
            vault_existed: vault.is_dir(),
            runtime_existed: vault.join(RUNTIME_DIR).is_dir(),
            resources_existed: vault.join(RESOURCES_DIR).is_dir(),
            config: std::fs::read(config_path(vault)).ok(),
            index_meta: std::fs::read(index_meta_path(vault)).ok(),
            state: std::fs::read(vault.join(INSTALL_STATE_PATH)).ok(),
            completed: completed_phases(vault),
            models: models_snapshot(vault),
        }
    }
}

fn restore_or_remove(target: &Path, before: Option<&[u8]>) {
    match before {
        Some(bytes) => {
            let _ = std::fs::write(target, bytes);
        }
        None => {
            let _ = std::fs::remove_file(target);
        }
    }
}

/// R-offline-3: deshace una instalación fallida o cancelada. En orden
/// inverso: primero lo que escribe fuera del runtime (F8 → F3), después el
/// runtime. Un `--resume` NO revierte lo que ya estaba: solo las fases que
/// esta corrida añadió más allá de `snapshot.completed`.
pub fn rollback_install(vault: &Path, snapshot: &InstallSnapshot) {
    let executed: Vec<Phase> = completed_phases(vault)
        .into_iter()
        .filter(|phase| !snapshot.completed.contains(phase))
        .collect();
    // F8/F7/F3 dejan rastro fuera (o antes) del runtime: compensan primero.
    if executed.contains(&Phase::F8) {
        compensate_phase8(vault);
    }
    if executed.contains(&Phase::F7) {
        compensate_phase7(vault);
    }
    if executed.contains(&Phase::F3) {
        compensate_phase3(vault);
    }
    if !snapshot.runtime_existed {
        // Todo el runtime (F4/F5/F6/F7, `bin/`, `venv/`, `db/`, `models/`,
        // `config/`, markers) lo creó esta corrida: se va entero.
        let _ = std::fs::remove_dir_all(vault.join(RUNTIME_DIR));
    } else {
        // Config/meta/state van SIEMPRE a los bytes del snapshot: escribirlos
        // iguales no es un cambio, y `completed_phases` no distingue una fase
        // re-ejecutada de una que ya estaba (los artefactos también cuentan).
        restore_or_remove(&config_path(vault), snapshot.config.as_deref());
        if executed.contains(&Phase::F5) {
            compensate_phase5(vault);
        }
        if executed.contains(&Phase::F4) {
            compensate_phase4(vault);
        }
        purge_partials(vault, &snapshot.models);
        restore_or_remove(&index_meta_path(vault), snapshot.index_meta.as_deref());
        restore_or_remove(&vault.join(INSTALL_STATE_PATH), snapshot.state.as_deref());
    }
    if !snapshot.resources_existed {
        // `remove_dir` se niega si hay algo: el contenido del usuario manda.
        let _ = std::fs::remove_dir(vault.join(RESOURCES_DIR));
    }
    if !snapshot.vault_existed {
        // El vault entero lo creó esta corrida: ahí no había nada del usuario.
        let _ = std::fs::remove_dir_all(vault);
    }
}
