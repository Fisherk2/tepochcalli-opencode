//! Install result: full success or degraded (path 5, no embedder yet).

use super::plan::VaultPath;

/// Final result of an install run: exit 0 in both cases (§5.4).
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum InstallOutcome {
    /// Complete install with a working index.
    Ok {
        /// Vault that was installed.
        vault: VaultPath,
    },
    /// Complete install without an embedder (path 5): RAG answers
    /// `E_NO_EMBEDDER` until `tepochcalli config embedder` runs.
    Degraded {
        /// Vault that was installed.
        vault: VaultPath,
        /// Human-readable next step (always names the swap command).
        fix_hint: String,
    },
}

impl InstallOutcome {
    /// Degraded result with the canonical next-step hint.
    #[must_use]
    pub fn degraded(vault: VaultPath) -> Self {
        Self::Degraded {
            vault,
            fix_hint: String::from(
                "RAG index disabled (no embedder). Run `tepochcalli config embedder` to enable search.",
            ),
        }
    }

    /// Next-step hint; empty when the install is complete.
    #[must_use]
    pub fn fix_hint_text(&self) -> &str {
        match self {
            Self::Ok { .. } => "",
            Self::Degraded { fix_hint, .. } => fix_hint,
        }
    }

    /// MCP `E_*` surfaced by `search` while degraded; `None` when complete.
    #[must_use]
    pub fn e_star(&self) -> Option<&'static str> {
        match self {
            Self::Ok { .. } => None,
            Self::Degraded { .. } => Some("E_NO_EMBEDDER"),
        }
    }
}
