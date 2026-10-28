//! `PayloadSource`: where the vault payload comes from.

use std::path::{Path, PathBuf};

use crate::domain::WizardError;

/// Materializes the workspace payload (`ReleasePayload` vs `LocalPayload`
/// in T8). Returns exactly the files written (basis of `.install-intent`).
pub trait PayloadSource {
    /// Copy/extract the payload under `dest`; return the files written.
    fn materialize(&self, dest: &Path) -> Result<Vec<PathBuf>, WizardError>;
}
