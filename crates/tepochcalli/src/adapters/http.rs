//! Real [`crate::ports::HttpClient`] over `ureq`.
//!
//! Single-implementation rule (T9): the verified download lives in
//! [`crate::fetch::fetch_verified`] (T2 spike, pinned by
//! `tests/fetch_verified.rs`); this adapter only maps its [`FetchError`]
//! to [`WizardError`]. `get` stays here — `fetch` has no equivalent.

use std::io::{ErrorKind, Read as _};
use std::path::Path;
use std::time::Duration;

use crate::domain::WizardError;
use crate::fetch::{fetch_verified, FetchError};
use crate::ports::HttpClient;

/// GET timeout for every request (payloads, `uv` binary, HF estimates).
const TIMEOUT: Duration = Duration::from_secs(120);
/// Bounded redirect hops; excess ⇒ [`WizardError::NetDownload`].
const MAX_REDIRECTS: u32 = 10;

/// [`HttpClient`] over `ureq` with timeout and bounded redirects.
#[derive(Debug, Clone)]
pub struct UreqHttpClient {
    timeout: Duration,
    max_redirects: u32,
}

impl UreqHttpClient {
    /// Client with the house defaults (120 s timeout, 10 redirects).
    #[must_use]
    pub fn new() -> Self {
        Self {
            timeout: TIMEOUT,
            max_redirects: MAX_REDIRECTS,
        }
    }

    fn agent(&self) -> ureq::Agent {
        let config = ureq::Agent::config_builder()
            .timeout_global(Some(self.timeout))
            .max_redirects(self.max_redirects)
            .build();
        ureq::Agent::new_with_config(config)
    }

    fn fetch_bytes(&self, url: &str) -> Result<Vec<u8>, WizardError> {
        let mut response = self
            .agent()
            .get(url)
            .call()
            .map_err(|_| WizardError::NetDownload)?;
        let mut bytes = Vec::new();
        response
            .body_mut()
            .as_reader()
            .read_to_end(&mut bytes)
            .map_err(|_| WizardError::NetDownload)?;
        Ok(bytes)
    }
}

impl Default for UreqHttpClient {
    fn default() -> Self {
        Self::new()
    }
}

/// Map the single implementation's failure to the wizard contract: bad or
/// mismatched hashes are `PayloadCorrupt`, transport failures are
/// `NetDownload`, disk failures keep their kind.
fn map_fetch_error(error: FetchError) -> WizardError {
    match error {
        FetchError::ChecksumMismatch { .. } | FetchError::BadChecksumFormat => {
            WizardError::PayloadCorrupt
        }
        FetchError::Http(_) => WizardError::NetDownload,
        FetchError::Io(e) => {
            if e.kind() == ErrorKind::PermissionDenied {
                WizardError::PermissionDenied
            } else {
                WizardError::DiskFull
            }
        }
        // Unreachable on the download path (`--version` runs via the
        // `CommandRunner` port, never through `fetch`).
        FetchError::VersionCheck { .. } | FetchError::BadVersionOutput(_) => WizardError::Internal,
    }
}

impl HttpClient for UreqHttpClient {
    fn get(&self, url: &str) -> Result<Vec<u8>, WizardError> {
        self.fetch_bytes(url)
    }

    fn download(&self, url: &str, dest: &Path, expected_sha256: &str) -> Result<(), WizardError> {
        fetch_verified(url, dest, expected_sha256).map_err(map_fetch_error)
    }
}
