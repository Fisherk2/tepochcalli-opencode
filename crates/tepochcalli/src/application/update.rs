//! H7 `update`: overwrite the 5 payload scopes with a mandatory `.bak` per
//! replaced file and a rollback on any mid-flight failure.
//!
//! The warning panel is shown BEFORE anything is touched (H7) and the journal
//! — not a guess — decides what the rollback restores.

use std::path::Path;

use crate::adapters::payload::rollback_overwrite;
use crate::domain::WizardError;
use crate::ports::{OverwriteJournal, PayloadSource, Ui};

/// The only vault paths `update` may overwrite (H7): the payload files plus
/// the two harness roots. Notes, trays, templates and `.obsidian/` are not
/// listed, so they are never visited.
pub const UPDATE_SCOPES: [&str; 5] = [
    ".opencode",
    ".tepochcalli",
    ".gitignore",
    "opencode.json",
    "AGENTS.md",
];

/// What the overwrite established (basis of the closing panel).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct UpdateReport {
    /// Files written (created or replaced); `0` on a no-op second run.
    pub written: usize,
    /// Previous versions saved as `<ruta>.bak` before being replaced.
    pub backed_up: usize,
}

/// H7: warn (5 paths + target dir) → overwrite with backup → panel. Any
/// failure rolls the journal back, so the vault keeps its original bytes.
pub fn run_update(
    payload: &dyn PayloadSource,
    ui: &dyn Ui,
    vault: &Path,
) -> Result<UpdateReport, WizardError> {
    ui.panel(
        "Update (H7)",
        &format!(
            "Se sobrescribirán 5 rutas de {}: .opencode/, .tepochcalli/, .gitignore, \
             opencode.json y AGENTS.md. Antes de pisar cada fichero existente se guarda una \
             copia `<ruta>.bak`. Tus notas (00-resources/, 01-…05-), 10-templates/, .obsidian/ \
             y el runtime (venv/, db/, models/, bin/, config/) NO se tocan.",
            vault.display()
        ),
    );
    // Survivors: out-of-scope trees are never walked; runtime artifacts never
    // travel in the payload asset, so they are never written either.
    let mut journal = OverwriteJournal::default();
    if let Err(err) = payload.materialize_overwrite(vault, &UPDATE_SCOPES, &mut journal) {
        rollback_overwrite(vault, &journal);
        return Err(err);
    }
    let report = UpdateReport {
        written: journal.written.len(),
        backed_up: journal.backed_up.len(),
    };
    ui.panel(
        "Update completo",
        &format!(
            "{} ficheros escritos · {} backups (.bak) en {}",
            report.written,
            report.backed_up,
            vault.display()
        ),
    );
    Ok(report)
}
