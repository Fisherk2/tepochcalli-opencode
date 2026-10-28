//! `PayloadSource`: where the vault payload comes from.

use std::path::{Path, PathBuf};

use crate::domain::WizardError;

/// What a merge wrote vs. left untouched (pre-existing user files,
/// `.obsidian/`, symlinks). Paths are absolute under the vault `dest`.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct MergeReport {
    /// Files newly written by this merge (basis of `.install-intent`).
    pub written: Vec<PathBuf>,
    /// Files left byte-intact ("ya estaba") or skipped by policy.
    pub skipped: Vec<PathBuf>,
}

/// Materializes the workspace payload (`ReleasePayload` vs `LocalPayload`
/// in T8). Returns exactly the files written (basis of `.install-intent`).
pub trait PayloadSource {
    /// Copy/extract the payload under `dest`; return the files written.
    fn materialize(&self, dest: &Path) -> Result<Vec<PathBuf>, WizardError>;

    /// Copy/extract the payload under `dest`; return written + skipped.
    /// The default reports everything as written (fakes with no merge).
    fn materialize_report(&self, dest: &Path) -> Result<MergeReport, WizardError> {
        Ok(MergeReport {
            written: self.materialize(dest)?,
            skipped: Vec::new(),
        })
    }
}
