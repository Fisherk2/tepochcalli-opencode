//! Real [`crate::ports::HttpClient`] over `ureq`.
//!
//! Single-implementation rule (T9): the verified download lives in
//! [`crate::adapters::fetch::fetch_verified`] (T2 spike, pinned by
//! `tests/fetch_verified.rs`); this adapter only maps its [`FetchError`]
//! to [`WizardError`]. `get` stays here — `fetch` has no equivalent.

use std::io::{ErrorKind, Read as _};
use std::path::Path;
use std::time::Duration;

use crate::adapters::fetch::{fetch_verified, FetchError};
use crate::domain::WizardError;
use crate::ports::HttpClient;

/// GET timeout for every request (payloads, `uv` binary, HF estimates).
const TIMEOUT: Duration = Duration::from_secs(120);
/// Budget del preflight (R-offline-1): corto y fail-fast; el `TIMEOUT` de
/// 120 s es para transferencias, no para decidir si hay red.
const PROBE_TIMEOUT: Duration = Duration::from_secs(8);
/// Bounded redirect hops; excess ⇒ [`WizardError::NetDownload`].
const MAX_REDIRECTS: u32 = 10;

/// [`HttpClient`] over `ureq` with timeout and bounded redirects.
/// `https_only` (L4-2): http solo se admite en loopback o cuando el caller
/// autorizó el mirror no-TLS; lo demás es rechazo temprano tipo `NetDownload`.
#[derive(Debug, Clone)]
pub struct UreqHttpClient {
    timeout: Duration,
    max_redirects: u32,
    https_only: bool,
}

impl UreqHttpClient {
    /// Client with the house defaults (120 s timeout, 10 redirects, https only).
    #[must_use]
    pub fn new() -> Self {
        Self {
            timeout: TIMEOUT,
            max_redirects: MAX_REDIRECTS,
            https_only: true,
        }
    }

    /// `https_only = false` ⇒ mirror http no-loopback autorizado por TUI.
    #[must_use]
    pub fn with_https_only(https_only: bool) -> Self {
        Self {
            https_only,
            ..Self::new()
        }
    }

    /// Rechazo temprano del esquema (guard del L4-2): https vale siempre;
    /// http vale en loopback o con la autorización del mirror.
    fn transport_allowed(&self, url: &str) -> Result<(), WizardError> {
        let scheme = url
            .split_once("://")
            .map(|(scheme, _)| scheme.to_ascii_lowercase());
        match scheme.as_deref() {
            Some("https") => Ok(()),
            Some("http") if !self.https_only || crate::adapters::payload::is_loopback_base(url) => {
                Ok(())
            }
            _ => Err(WizardError::NetDownload),
        }
    }

    fn agent(&self) -> ureq::Agent {
        // timeout_global deliberado aquí: fetch_bytes solo lee respuestas de
        // KB (sidecar, metadatos HF) donde el budget total no puede abortar
        // una transferencia legítima a mitad de cuerpo.
        let config = ureq::Agent::config_builder()
            .timeout_global(Some(self.timeout))
            .max_redirects(self.max_redirects)
            .build();
        ureq::Agent::new_with_config(config)
    }

    fn fetch_bytes(&self, url: &str) -> Result<Vec<u8>, WizardError> {
        self.transport_allowed(url)?;
        let mut response = self
            .agent()
            .get(url)
            .call()
            .map_err(|_| WizardError::NetDownload)?;
        // Cap RAM (L2-2): sidecar/HF metadata son respuestas de KB; un
        // servidor malicioso no dicta la asignación. 1 MiB ⇒ margen x10.
        const MAX_FETCH_BYTES: u64 = 1024 * 1024;
        let mut bytes = Vec::new();
        response
            .body_mut()
            .as_reader()
            .take(MAX_FETCH_BYTES + 1)
            .read_to_end(&mut bytes)
            .map_err(|_| WizardError::NetDownload)?;
        if bytes.len() as u64 > MAX_FETCH_BYTES {
            return Err(WizardError::NetDownload);
        }
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
        // Activo del servidor hostil, no del usuario: mismo código de asset.
        FetchError::TooLarge { .. } => WizardError::PayloadCorrupt,
        FetchError::Http(_) => WizardError::NetDownload,
        FetchError::Io(e) => map_io_error(&e),
        // Unreachable on the download path (`--version` runs via the
        // `CommandRunner` port, never through `fetch`).
        FetchError::VersionCheck { .. } | FetchError::BadVersionOutput(_) => WizardError::Internal,
    }
}

/// Classify an `io::Error` from the transfer path. A blocked or dying network
/// surfaces here (mid-body reset, unreachable host), so those kinds are named
/// before the disk verdict; unknown kinds keep the historical `DiskFull`.
fn map_io_error(error: &std::io::Error) -> WizardError {
    match error.kind() {
        ErrorKind::PermissionDenied => WizardError::PermissionDenied,
        ErrorKind::StorageFull => WizardError::DiskFull,
        ErrorKind::ConnectionRefused
        | ErrorKind::ConnectionReset
        | ErrorKind::ConnectionAborted
        | ErrorKind::TimedOut
        | ErrorKind::NetworkUnreachable
        | ErrorKind::NetworkDown
        | ErrorKind::HostUnreachable
        | ErrorKind::AddrNotAvailable
        | ErrorKind::NotConnected
        | ErrorKind::UnexpectedEof
        | ErrorKind::BrokenPipe => WizardError::NetDownload,
        _ => WizardError::DiskFull,
    }
}

impl HttpClient for UreqHttpClient {
    fn get(&self, url: &str) -> Result<Vec<u8>, WizardError> {
        self.transport_allowed(url)?;
        self.fetch_bytes(url)
    }

    fn download(&self, url: &str, dest: &Path, expected_sha256: &str) -> Result<(), WizardError> {
        self.transport_allowed(url)?;
        fetch_verified(url, dest, expected_sha256).map_err(map_fetch_error)
    }

    /// R-offline-1: solo importa «¿hay red?», así que un 4xx/5xx es `Ok`.
    fn probe(&self, url: &str) -> Result<(), WizardError> {
        self.transport_allowed(url)?;
        let config = ureq::Agent::config_builder()
            .timeout_global(Some(PROBE_TIMEOUT))
            .timeout_connect(Some(PROBE_TIMEOUT))
            .http_status_as_error(false)
            .max_redirects(self.max_redirects)
            .build();
        ureq::Agent::new_with_config(config)
            .get(url)
            .call()
            .map(|_| ())
            .map_err(|_| WizardError::NetDownload)
    }
}

#[cfg(test)]
mod tests {
    //! Tier 1: this mapping is the only place a transport failure becomes a
    //! user-facing exit code, so a mislabelled branch is a wrong diagnosis.

    use super::{map_fetch_error, UreqHttpClient};
    use crate::adapters::fetch::FetchError;
    use crate::domain::WizardError;
    use std::io::ErrorKind;

    fn io_error(kind: ErrorKind) -> FetchError {
        FetchError::Io(std::io::Error::new(kind, "probe"))
    }

    /// A blocked/unreachable network arrives as `io::Error` on the transfer
    /// path (never as `FetchError::Http`), so none of these kinds may be
    /// reported as "disk full" (exit 30).
    #[test]
    fn network_io_kinds_map_to_net_download() {
        let network = [
            ErrorKind::ConnectionRefused,
            ErrorKind::ConnectionReset,
            ErrorKind::ConnectionAborted,
            ErrorKind::TimedOut,
            ErrorKind::NetworkUnreachable,
            ErrorKind::NetworkDown,
            ErrorKind::HostUnreachable,
            ErrorKind::AddrNotAvailable,
            ErrorKind::NotConnected,
            ErrorKind::UnexpectedEof,
            ErrorKind::BrokenPipe,
        ];
        for kind in network {
            assert_eq!(
                map_fetch_error(io_error(kind)),
                WizardError::NetDownload,
                "{kind:?} is a network failure, not a disk one"
            );
        }
    }

    #[test]
    fn permission_denied_keeps_its_own_code() {
        assert_eq!(
            map_fetch_error(io_error(ErrorKind::PermissionDenied)),
            WizardError::PermissionDenied
        );
    }

    /// `ErrorKind::StorageFull` (stable since Rust 1.83) is what ENOSPC
    /// becomes, so a genuinely full disk keeps exit 30.
    #[test]
    fn storage_full_stays_disk_full() {
        assert_eq!(
            map_fetch_error(io_error(ErrorKind::StorageFull)),
            WizardError::DiskFull
        );
    }

    /// Same case through the real OS error a full disk raises (ENOSPC = 28).
    #[cfg(target_os = "linux")]
    #[test]
    fn enospc_raw_os_error_stays_disk_full() {
        let full = std::io::Error::from_raw_os_error(28);
        assert_eq!(full.kind(), ErrorKind::StorageFull);
        assert_eq!(map_fetch_error(FetchError::Io(full)), WizardError::DiskFull);
    }

    /// Documented fallback, unchanged by this fix: a kind on neither list
    /// stays `DiskFull`. Rationale: past the socket, the only other `io` step
    /// on this path is writing the verified bytes (`fs::write`), where exit 30
    /// is the actionable hint; the listed network kinds above cover the
    /// transport case that used to be mislabelled.
    #[test]
    fn unlisted_io_kind_keeps_the_disk_full_fallback() {
        assert_eq!(
            map_fetch_error(io_error(ErrorKind::InvalidData)),
            WizardError::DiskFull
        );
    }

    /// L4-2 guard: https siempre; http loopback siempre; http no-loopback
    /// solo con el mirror autorizado.
    #[test]
    fn transport_guard_allows_https_and_loopback_http_only() {
        assert_eq!(
            UreqHttpClient::new().transport_allowed("https://mirror.test/x"),
            Ok(())
        );
        assert_eq!(
            UreqHttpClient::new().transport_allowed("http://127.0.0.1:9/x"),
            Ok(())
        );
        assert_eq!(
            UreqHttpClient::new().transport_allowed("http://localhost:9/x"),
            Ok(())
        );
        assert_eq!(
            UreqHttpClient::new().transport_allowed("http://mirror-public.test/x"),
            Err(WizardError::NetDownload),
            "http no-loopback sin autorización"
        );
        assert_eq!(
            UreqHttpClient::with_https_only(false).transport_allowed("http://mirror-public.test/x"),
            Ok(()),
            "con mirror autorizado el transporte http vale"
        );
    }

    #[test]
    fn checksum_failures_are_payload_corrupt() {
        let mismatch = FetchError::ChecksumMismatch {
            url: "http://127.0.0.1/asset".to_string(),
            expected: "e".repeat(64),
            actual: "a".repeat(64),
        };
        assert_eq!(map_fetch_error(mismatch), WizardError::PayloadCorrupt);
        assert_eq!(
            map_fetch_error(FetchError::BadChecksumFormat),
            WizardError::PayloadCorrupt
        );
    }

    /// Pins the existing behaviour for real `ureq` transport errors.
    #[test]
    fn ureq_transport_errors_are_net_download() {
        let transport = ureq::Error::Io(std::io::Error::new(ErrorKind::ConnectionRefused, "probe"));
        assert_eq!(
            map_fetch_error(FetchError::Http(transport)),
            WizardError::NetDownload
        );
    }
}
