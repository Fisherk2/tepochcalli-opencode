//! The 8 install phases (frozen by the spec) and their lifecycle.

/// Install phase F1..F8, in execution order.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Phase {
    /// F1: prerequisite detection (OS/arch, RAM, disk).
    F1,
    /// F2: vault directory selection.
    F2,
    /// F3: payload extraction.
    F3,
    /// F4: `uv` bootstrap.
    F4,
    /// F5: `uv venv` + `uv sync`.
    F5,
    /// F6: embedding provider menu.
    F6,
    /// F7: initial index.
    F7,
    /// F8: `mcp.servers` merge.
    F8,
}

impl Phase {
    /// Position in execution order (0 for F1 .. 7 for F8).
    #[must_use]
    pub fn order_index(self) -> u8 {
        self as u8
    }

    /// Short spec name (`"F1"` .. `"F8"`).
    #[must_use]
    pub fn name(self) -> &'static str {
        match self {
            Self::F1 => "F1",
            Self::F2 => "F2",
            Self::F3 => "F3",
            Self::F4 => "F4",
            Self::F5 => "F5",
            Self::F6 => "F6",
            Self::F7 => "F7",
            Self::F8 => "F8",
        }
    }

    /// All phases in execution order.
    #[must_use]
    pub fn all() -> [Self; 8] {
        [
            Self::F1,
            Self::F2,
            Self::F3,
            Self::F4,
            Self::F5,
            Self::F6,
            Self::F7,
            Self::F8,
        ]
    }
}

/// Lifecycle state of one phase (rollback by compensation, never booleans).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PhaseState {
    /// Not attempted yet.
    NotStarted,
    /// Currently executing.
    InProgress,
    /// Finished without errors.
    Done,
    /// Failed and compensated (user data untouched).
    Compensated,
}

/// How a phase finished, once it leaves `InProgress`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PhaseOutcome {
    /// Phase completed; artifacts in place.
    Done,
    /// Phase failed and its compensation ran.
    Compensated,
}
