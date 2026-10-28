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

/// What to install where; flags stay out until their task (T14) needs them.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct InstallPlan {
    /// Target vault directory (created/reused, never wiped).
    pub vault: VaultPath,
    /// Fail with a typed error instead of prompting when input is missing.
    pub non_interactive: bool,
}

/// Everything one installer run needs to know up front.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct InstallContext {
    /// The plan this run executes.
    pub plan: InstallPlan,
}

impl InstallContext {
    /// Wrap a plan as a fresh run context.
    #[must_use]
    pub fn new(plan: InstallPlan) -> Self {
        Self { plan }
    }
}
