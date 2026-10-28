//! `HttpClient`: fetch bytes and download assets with SHA-256 verification.

use std::path::Path;

use crate::domain::WizardError;

/// Network access (release payload, `uv` binary, HF API estimates).
/// The `--offline` path (T14) bypasses this port entirely.
pub trait HttpClient {
    /// GET `url` fully into memory.
    fn get(&self, url: &str) -> Result<Vec<u8>, WizardError>;
    /// Download `url` to `dest`, failing unless its SHA-256 matches.
    fn download(&self, url: &str, dest: &Path, expected_sha256: &str) -> Result<(), WizardError>;
}
