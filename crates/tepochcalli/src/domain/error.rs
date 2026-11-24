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

#[cfg(test)]
mod tests {
    //! Tier 1: this table is what the network tests, the failure panel and the
    //! FTR quote; a copy-paste slip between two variants is a wrong diagnosis
    //! shown to the user, so every row is pinned here.

    use super::WizardError;

    /// One row per variant. Not derived from the enum: the point is to pin the
    /// number a user sees, not to restate the `match`.
    const EXIT_CODES: [(WizardError, u8); 14] = [
        (WizardError::PrereqRam, 10),
        (WizardError::PrereqDisk, 11),
        (WizardError::PrereqPlatform, 12),
        (WizardError::NetDownload, 20),
        (WizardError::OfflineNoCache, 21),
        (WizardError::ApiAuth, 22),
        (WizardError::DiskFull, 30),
        (WizardError::PermissionDenied, 31),
        (WizardError::PayloadCorrupt, 32),
        (WizardError::Internal, 40),
        (WizardError::UserAborted, 41),
        (WizardError::PhaseFailed, 42),
        (WizardError::ModelInvalid, 43),
        (WizardError::ModelMismatch, 44),
    ];

    /// The bands as documented on the enum itself. No wildcard arm: a new
    /// variant breaks this compile instead of silently escaping the tables.
    fn documented_band(error: WizardError) -> std::ops::RangeInclusive<u8> {
        match error {
            WizardError::PrereqRam | WizardError::PrereqDisk | WizardError::PrereqPlatform => {
                10..=19
            }
            WizardError::NetDownload | WizardError::OfflineNoCache | WizardError::ApiAuth => {
                20..=29
            }
            WizardError::DiskFull | WizardError::PermissionDenied | WizardError::PayloadCorrupt => {
                30..=39
            }
            WizardError::Internal
            | WizardError::UserAborted
            | WizardError::PhaseFailed
            | WizardError::ModelInvalid
            | WizardError::ModelMismatch => 40..=u8::MAX,
        }
    }

    #[test]
    fn exit_code_table_is_pinned_per_variant() {
        assert_eq!(EXIT_CODES.len(), 14, "one row per variant");
        for (error, code) in EXIT_CODES {
            assert_eq!(error.exit_code(), code, "{error:?} exit code");
        }
        // The two numbers §5.4 pins explicitly.
        assert_eq!(WizardError::OfflineNoCache.exit_code(), 21);
        assert_eq!(WizardError::ApiAuth.exit_code(), 22);
    }

    #[test]
    fn exit_codes_are_unique() {
        // Two variants sharing a code means one of them was copy-pasted and
        // never reviewed: `main` cannot tell the failures apart.
        for (index, (left, left_code)) in EXIT_CODES.iter().enumerate() {
            for (right, right_code) in &EXIT_CODES[index + 1..] {
                assert_ne!(
                    left_code, right_code,
                    "{left:?} and {right:?} share exit code {left_code}"
                );
            }
        }
    }

    #[test]
    fn every_exit_code_falls_in_its_documented_band() {
        for (error, code) in EXIT_CODES {
            let band = documented_band(error);
            assert!(
                band.contains(&code),
                "{error:?} exits {code}, outside its documented band {band:?}"
            );
        }
    }

    #[test]
    fn e_star_table_is_pinned_per_variant() {
        let expected: [(WizardError, Option<&str>); 14] = [
            (WizardError::PrereqRam, None),
            (WizardError::PrereqDisk, None),
            (WizardError::PrereqPlatform, None),
            (WizardError::NetDownload, None),
            (WizardError::OfflineNoCache, Some("E_OFFLINE_NO_CACHE")),
            (WizardError::ApiAuth, Some("E_API_AUTH")),
            (WizardError::DiskFull, None),
            (WizardError::PermissionDenied, None),
            (WizardError::PayloadCorrupt, None),
            (WizardError::Internal, None),
            (WizardError::UserAborted, None),
            (WizardError::PhaseFailed, None),
            (WizardError::ModelInvalid, Some("E_MODEL_INVALID")),
            (WizardError::ModelMismatch, Some("E_MODEL_MISMATCH")),
        ];
        for (error, code) in expected {
            assert_eq!(error.e_star(), code, "{error:?} E_* mapping");
        }
    }

    #[test]
    fn e_star_codes_are_unique_and_carry_the_contract_prefix() {
        let mut seen: Vec<&str> = Vec::new();
        for error in EXIT_CODES.map(|(error, _)| error) {
            let Some(code) = error.e_star() else {
                continue;
            };
            assert!(code.starts_with("E_"), "{error:?} code {code}");
            assert!(!seen.contains(&code), "{error:?} reuses {code}");
            seen.push(code);
        }
        assert_eq!(seen.len(), 4, "the contract defines 4 E_* failures");
    }
}
