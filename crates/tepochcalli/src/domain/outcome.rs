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

#[cfg(test)]
mod tests {
    //! Tier 1: both outcomes exit 0 (§5.4); the difference the user sees is the
    //! hint and the `E_NO_EMBEDDER` code, so each variant is pinned here.

    use super::{InstallOutcome, VaultPath};

    fn vault() -> VaultPath {
        let Some(vault) = VaultPath::new("vault") else {
            panic!("fixture vault is non-empty");
        };
        vault
    }

    #[test]
    fn degraded_names_the_swap_command_and_the_contract_code() {
        let outcome = InstallOutcome::degraded(vault());
        assert!(matches!(outcome, InstallOutcome::Degraded { .. }));
        assert_eq!(outcome.e_star(), Some("E_NO_EMBEDDER"));
        let hint = outcome.fix_hint_text();
        assert!(!hint.is_empty(), "degraded install must carry a hint");
        assert!(
            hint.contains("tepochcalli config embedder"),
            "hint must name the swap command, got: {hint}"
        );
    }

    #[test]
    fn complete_install_has_no_hint_and_no_code() {
        let outcome = InstallOutcome::Ok { vault: vault() };
        assert_eq!(outcome.fix_hint_text(), "");
        assert_eq!(outcome.e_star(), None);
    }

    #[test]
    fn degraded_keeps_the_vault_it_was_built_with() {
        let expected = vault();
        let outcome = InstallOutcome::degraded(expected.clone());
        match outcome {
            InstallOutcome::Degraded { vault, .. } => assert_eq!(vault, expected),
            InstallOutcome::Ok { .. } => panic!("degraded() must build the Degraded variant"),
        }
    }
}
