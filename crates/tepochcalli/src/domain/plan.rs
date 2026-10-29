//! Install plan: validated vault path plus the context a run needs.

use std::path::{Path, PathBuf};

/// Vault directory, validated at construction (never empty).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VaultPath(PathBuf);

impl VaultPath {
    /// Build from raw CLI input; `None` when empty/blank (CLI maps it to a
    /// usage error, exit 2 — never a wizard failure code).
    #[must_use]
    pub fn new(raw: &str) -> Option<Self> {
        let trimmed = raw.trim();
        (!trimmed.is_empty()).then(|| Self(PathBuf::from(trimmed)))
    }

    /// Borrow the validated path.
    #[must_use]
    pub fn as_path(&self) -> &Path {
        &self.0
    }
}

#[cfg(test)]
mod tests {
    //! Tier 1: `VaultPath` is the only validated path in the domain — an empty
    //! value must never reach an installer phase (it would resolve to the CWD).

    use super::VaultPath;
    use std::path::Path;

    #[test]
    fn vault_path_rejects_empty_and_blank_input() {
        for raw in ["", " ", "   ", "\t", "\n", "  \t\n "] {
            assert!(
                VaultPath::new(raw).is_none(),
                "{raw:?} must be rejected, not resolved to the CWD"
            );
        }
    }

    #[test]
    fn vault_path_trims_the_edges_and_keeps_the_rest_verbatim() {
        let Some(vault) = VaultPath::new("  /tmp/my vault  ") else {
            panic!("a non-blank path must be accepted");
        };
        assert_eq!(vault.as_path(), Path::new("/tmp/my vault"));
    }
}
