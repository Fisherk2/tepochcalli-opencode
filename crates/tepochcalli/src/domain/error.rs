//! Typed wizard failures → exit codes (plan §5.4) + MCP `E_*` (D27).
//!
//! Ranges are fixed by the spec; the exact number inside each range is the
//! wizard's documented choice. `e_star` maps a failure to its MCP-contract
//! equivalent where one exists, else `None`.

use thiserror::Error;

/// Every way the wizard can fail, with its exit code and `E_*` mapping.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Error)]
pub enum WizardError {
    /// RAM below the 8 GB minimum.
    #[error("insufficient RAM (need 8 GB)")]
    PrereqRam,
    /// Free disk below the 4 GB minimum.
    #[error("insufficient disk space (need 4 GB)")]
    PrereqDisk,
    /// OS/arch combination the wizard does not support.
    #[error("unsupported platform")]
    PrereqPlatform,
    /// Network fetch failed (payload, `uv` binary, model download).
    #[error("download failed")]
    NetDownload,
    /// `--offline` with nothing usable in the local cache.
    #[error("offline with empty cache")]
    OfflineNoCache,
    /// External API key rejected (menu path 4).
    #[error("API key rejected")]
    ApiAuth,
    /// Disk filled up mid-install.
    #[error("disk full")]
    DiskFull,
    /// OS refused a write the install needs.
    #[error("permission denied")]
    PermissionDenied,
    /// Release asset failed its SHA-256 check (or is unparseable).
    #[error("payload corrupt")]
    PayloadCorrupt,
    /// Free HF id is not an embedding model (menu gate, path 3).
    #[error("not an embedding model")]
    ModelInvalid,
    /// Model dims differ from the existing index (reindex/swap guard).
    #[error("model/index dimension mismatch")]
    ModelMismatch,
    /// A phase failed after its compensation ran (user data intact).
    #[error("install phase failed (compensated)")]
    PhaseFailed,
    /// Bug in the wizard itself (unreachable states, stub paths in T3).
    #[error("internal wizard error")]
    Internal,
    /// The user cancelled (Ctrl-C / declined a required confirm).
    #[error("cancelled by user")]
    UserAborted,
}

impl WizardError {
    /// Exit code: spec range per failure class, exact number documented here.
    #[must_use]
    pub fn exit_code(self) -> u8 {
        match self {
            // 10-19: prerequisites (§5.4).
            Self::PrereqRam => 10,
            Self::PrereqDisk => 11,
            Self::PrereqPlatform => 12,
            // 20-29: network/auth (§5.4; 21/22 pinned by the plan table).
            Self::NetDownload => 20,
            Self::OfflineNoCache => 21,
            Self::ApiAuth => 22,
            // 30-39: filesystem/asset (§5.4).
            Self::DiskFull => 30,
            Self::PermissionDenied => 31,
            Self::PayloadCorrupt => 32,
            // 40+: user cancel, model guards, phase failure, internal (§5.4).
            Self::Internal => 40,
            Self::UserAborted => 41,
            Self::PhaseFailed => 42,
            Self::ModelInvalid => 43,
            Self::ModelMismatch => 44,
        }
    }

    /// MCP-contract `E_*` equivalent where one exists (D27).
    #[must_use]
    pub fn e_star(self) -> Option<&'static str> {
        match self {
            Self::OfflineNoCache => Some("E_OFFLINE_NO_CACHE"),
            Self::ApiAuth => Some("E_API_AUTH"),
            Self::ModelInvalid => Some("E_MODEL_INVALID"),
            Self::ModelMismatch => Some("E_MODEL_MISMATCH"),
            _ => None,
        }
    }
}
