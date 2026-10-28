//! Real [`crate::ports::HttpClient`] over `ureq` (same call pattern as the
//! T2 `fetch_verified` spike): bounded timeout + redirects, SHA-256 check
//! **before** anything lands on disk, so a mismatch never leaves a file.

use std::fs;
use std::io::{ErrorKind, Read as _};
use std::path::Path;
use std::time::Duration;

use sha2::{Digest, Sha256};

use crate::domain::WizardError;
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

fn decode_sha256(hex: &str) -> Result<[u8; 32], WizardError> {
    if hex.len() != 64 || !hex.bytes().all(|b| b.is_ascii_hexdigit()) {
        return Err(WizardError::PayloadCorrupt);
    }
    let mut out = [0u8; 32];
    for (i, chunk) in hex.as_bytes().chunks(2).enumerate() {
        let pair = std::str::from_utf8(chunk).map_err(|_| WizardError::PayloadCorrupt)?;
        out[i] = u8::from_str_radix(pair, 16).map_err(|_| WizardError::PayloadCorrupt)?;
    }
    Ok(out)
}

impl HttpClient for UreqHttpClient {
    fn get(&self, url: &str) -> Result<Vec<u8>, WizardError> {
        self.fetch_bytes(url)
    }

    fn download(&self, url: &str, dest: &Path, expected_sha256: &str) -> Result<(), WizardError> {
        // Validate the checksum first: a malformed expectation fails before
        // any network or disk I/O.
        let expected = decode_sha256(expected_sha256)?;
        let bytes = self.fetch_bytes(url)?;
        if Sha256::digest(&bytes)[..] != expected {
            return Err(WizardError::PayloadCorrupt);
        }
        // Write only after the hash matches: a corrupt body never lands.
        if let Some(parent) = dest.parent() {
            fs::create_dir_all(parent).map_err(|_| WizardError::DiskFull)?;
        }
        fs::write(dest, &bytes).map_err(|e| {
            if e.kind() == ErrorKind::PermissionDenied {
                WizardError::PermissionDenied
            } else {
                WizardError::DiskFull
            }
        })
    }
}
