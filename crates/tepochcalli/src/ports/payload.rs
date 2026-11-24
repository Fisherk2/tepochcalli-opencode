//! `PayloadSource`: where the vault payload comes from.

use std::path::{Path, PathBuf};

use crate::domain::{CancelToken, WizardError};

/// What a merge wrote vs. left untouched (pre-existing user files,
/// `.obsidian/`, symlinks). Paths are absolute under the vault `dest`.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct MergeReport {
    /// Files newly written by this merge (basis of `.install-intent`).
    pub written: Vec<PathBuf>,
    /// Files left byte-intact ("ya estaba") or skipped by policy.
    pub skipped: Vec<PathBuf>,
}

/// What an overwrite wrote and backed up (H7 `update`). Feeds
/// [`crate::application::update::rollback_overwrite`] when a run fails midway:
/// `backed_up` are the originals saved as `<ruta>.bak`, `written` every file
/// the overwrite created or replaced.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct OverwriteJournal {
    /// Files written by the overwrite (new or replaced).
    pub written: Vec<PathBuf>,
    /// Pre-existing files copied to `<ruta>.bak` before being replaced.
    pub backed_up: Vec<PathBuf>,
}

/// Materializes the workspace payload (`ReleasePayload` vs `LocalPayload`
/// in T8). Returns exactly written + skipped (pre-existing user files,
/// `.obsidian/`, symlinks) — basis of `.install-intent`.
pub trait PayloadSource {
    /// Copy/extract the payload under `dest`; return written + skipped.
    fn materialize_report(&self, dest: &Path) -> Result<MergeReport, WizardError>;
    /// Overwrite ONLY the entries whose first component is in `scopes`
    /// (H7 `update`): every replaced file is saved as `<ruta>.bak` first and
    /// journaled, identical content is a no-op. On error the journal keeps
    /// what was done so the caller can roll back. A cancelled `cancel`
    /// stops the walk at the next entry with [`WizardError::UserAborted`],
    /// journal intact.
    fn materialize_overwrite(
        &self,
        dest: &Path,
        scopes: &[&str],
        journal: &mut OverwriteJournal,
        cancel: Option<&CancelToken>,
    ) -> Result<(), WizardError>;
}

/// `<ruta>.bak`: the byte backup taken before an overwrite (H7). Part of the
/// journal contract — whichever side writes it, [`rollback_overwrite`] reads
/// it back by the same name.
///
/// [`rollback_overwrite`]: crate::application::update::rollback_overwrite
pub fn backup_path(target: &Path) -> PathBuf {
    let mut name = target.as_os_str().to_os_string();
    name.push(".bak");
    PathBuf::from(name)
}
