//! R-offline-3: deshacer una instalación fallida o cancelada.
//!
//! Orden inverso al de ejecución: primero lo que vive FUERA del runtime
//! (`opencode.json` de F8, payload y placeholders de F3) y después el
//! runtime. Dentro de él solo se compensan las fases que ESTA corrida
//! añadió más allá del snapshot; lo ya hecho antes se respeta. F6 se
//! restaura con los bytes del snapshot: `compensate_phase6` escribiría
//! `provider = "none"` (instalación degradada), prohibido por R-offline-4.
//! Tras compensar, el rollback MIDE el resultado contra el snapshot y lo
//! declara en un [`RollbackReport`]: quien lo llama ya no afirma «el vault
//! quedó como estaba» sin haberlo comprobado.

use std::collections::BTreeSet;
use std::ffi::OsStr;
use std::path::Path;

use crate::domain::Phase;

use super::embedder_gate::{models_snapshot, purge_partials};
use super::embedder_menu::config_path;
use super::installer::{
    compensate_phase3, compensate_phase4, compensate_phase5, completed_phases, AGENTS_MD,
    GITIGNORE, INSTALL_STATE_PATH, OPENCODE_DIR, RESOURCES_DIR, RUNTIME_DIR, TEMPLATES_DIR,
};
use super::phase7::{compensate_phase7, index_meta_path};
use super::phase8::{compensate_phase8, OPENCODE_JSON};

/// Estado del vault justo ANTES del primer write de una corrida de install.
#[derive(Debug)]
pub struct InstallSnapshot {
    vault_existed: bool,
    runtime_existed: bool,
    resources_existed: bool,
    /// Raíces que F3/F8 escriben FUERA del runtime, con su existencia previa.
    scopes: Vec<(&'static str, bool)>,
    config: Option<Vec<u8>>,
    opencode_json: Option<Vec<u8>>,
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
            scopes: [OPENCODE_DIR, TEMPLATES_DIR, AGENTS_MD, GITIGNORE]
                .into_iter()
                .map(|scope| (scope, vault.join(scope).exists()))
                .collect(),
            config: std::fs::read(config_path(vault)).ok(),
            opencode_json: std::fs::read(vault.join(OPENCODE_JSON)).ok(),
            index_meta: std::fs::read(index_meta_path(vault)).ok(),
            state: std::fs::read(vault.join(INSTALL_STATE_PATH)).ok(),
            completed: completed_phases(vault),
            models: models_snapshot(vault),
        }
    }
}

/// Restores the snapshotted bytes or removes the file the run created; shared
/// with the swap rollback (`swap::rollback`).
pub(super) fn restore_or_remove(target: &Path, before: Option<&[u8]>) {
    // Un target que es un enlace no se toca: escribir a través de él
    // contaminaría su destino fuera del vault (L2-8). Se deja el enlace y la
    // verificación `bytes_match` lo reportará como resto.
    if std::fs::symlink_metadata(target).is_ok_and(|m| m.file_type().is_symlink()) {
        return;
    }
    match before {
        Some(bytes) => {
            let _ = std::fs::write(target, bytes);
        }
        None => {
            let _ = std::fs::remove_file(target);
        }
    }
}

/// Resultado MEDIDO del rollback contra el snapshot: qué sobrevivió sin ser
/// del instalador y qué quedó sin poder compensar.
#[derive(Debug, Default, PartialEq, Eq)]
pub struct RollbackReport {
    /// Rutas relativas que siguen presentes y no deberían.
    pub leftovers: Vec<String>,
    /// Contenido del usuario que se conservó a propósito (no es un resto).
    pub preserved: Vec<String>,
}

impl RollbackReport {
    /// `true` cuando no quedó ningún resto del instalador.
    #[must_use]
    pub fn is_complete(&self) -> bool {
        self.leftovers.is_empty()
    }
}

/// `true` cuando el estado actual coincide con el del snapshot (`None` =
/// ausente).
fn bytes_match(path: &Path, before: Option<&[u8]>) -> bool {
    match before {
        Some(bytes) => std::fs::read(path).is_ok_and(|now| now == bytes),
        None => !path.exists(),
    }
}

fn relative(vault: &Path, path: &Path) -> String {
    path.strip_prefix(vault)
        .unwrap_or(path)
        .to_string_lossy()
        .into_owned()
}

/// Raíces que escribe el instalador: una entrada así en el vault nunca es
/// «contenido del usuario» (es un resto si sobrevive al rollback).
fn is_managed_root(name: &OsStr) -> bool {
    [
        OPENCODE_DIR,
        RUNTIME_DIR,
        RESOURCES_DIR,
        TEMPLATES_DIR,
        AGENTS_MD,
        GITIGNORE,
        OPENCODE_JSON,
    ]
    .iter()
    .any(|root| name == OsStr::new(root))
}

/// R-offline-3: deshace una instalación fallida o cancelada. En orden
/// inverso: primero lo que escribe fuera del runtime (F8 → F3), después el
/// runtime. Un `--resume` NO revierte lo que ya estaba: solo las fases que
/// esta corrida añadió más allá de `snapshot.completed`.
pub fn rollback_install(vault: &Path, snapshot: &InstallSnapshot) -> RollbackReport {
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
    let mut preserved = Vec::new();
    if !snapshot.vault_existed && vault.exists() {
        // P1-2: el vault lo creó esta corrida, pero puede haber ficheros del
        // usuario escritos DURANTE el install. Solo se borra si está vacío.
        if let Ok(entries) = std::fs::read_dir(vault) {
            let mut empty = true;
            let mut managed = false;
            for entry in entries.flatten() {
                empty = false;
                managed |= is_managed_root(&entry.file_name());
            }
            if empty {
                let _ = std::fs::remove_dir(vault);
            } else if !managed {
                // Una raíz gestionada que sigue aquí es un resto, no
                // contenido del usuario: la verificación de abajo lo declara.
                preserved.push(format!("contenido del usuario en {}", vault.display()));
            }
        }
    }
    // R-offline-3 medido: no se afirma un estado sin comprobarlo.
    let mut leftovers = Vec::new();
    let runtime_dir = vault.join(RUNTIME_DIR);
    if runtime_dir.is_dir() != snapshot.runtime_existed {
        leftovers.push(relative(vault, &runtime_dir));
    }
    let resources_dir = vault.join(RESOURCES_DIR);
    if resources_dir.is_dir() != snapshot.resources_existed {
        leftovers.push(relative(vault, &resources_dir));
    }
    // F3/F8 escriben fuera del runtime: sin medirlo, un fichero suyo que
    // sobreviva se daba por «vault como estaba».
    for (scope, before) in &snapshot.scopes {
        let path = vault.join(scope);
        if path.exists() != *before {
            leftovers.push(relative(vault, &path));
        }
    }
    let opencode_json = vault.join(OPENCODE_JSON);
    if !bytes_match(&opencode_json, snapshot.opencode_json.as_deref()) {
        leftovers.push(relative(vault, &opencode_json));
    }
    for (path, before) in [
        (config_path(vault), snapshot.config.as_deref()),
        (index_meta_path(vault), snapshot.index_meta.as_deref()),
        (vault.join(INSTALL_STATE_PATH), snapshot.state.as_deref()),
    ] {
        if !bytes_match(&path, before) {
            leftovers.push(relative(vault, &path));
        }
    }
    if models_snapshot(vault) != snapshot.models {
        leftovers.push(relative(vault, &runtime_dir.join("models")));
    }
    RollbackReport {
        leftovers,
        preserved,
    }
}

#[cfg(test)]
mod tests {
    use super::bytes_match;
    use std::path::Path;

    #[test]
    fn bytes_match_compares_bytes_and_absence() {
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("config");
        std::fs::write(&path, b"viejo").expect("fixture");
        assert!(bytes_match(&path, Some(b"viejo")), "mismos bytes");
        assert!(!bytes_match(&path, Some(b"nuevo")), "bytes distintos");
        assert!(
            !bytes_match(&path, None),
            "existe pero el snapshot lo daba por ausente"
        );
        let missing = dir.path().join("no-existe");
        assert!(bytes_match(&missing, None), "ausente como en el snapshot");
        assert!(
            !bytes_match(&missing, Some(b"x")),
            "falta lo que el snapshot tenía"
        );
    }

    #[test]
    fn relative_keeps_the_path_readable_inside_the_vault() {
        let vault = Path::new("/vault");
        let path = Path::new("/vault/.tepochcalli/config/tepochcalli.toml");
        assert_eq!(
            super::relative(vault, path),
            ".tepochcalli/config/tepochcalli.toml"
        );
    }
}
