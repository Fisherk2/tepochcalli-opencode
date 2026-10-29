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

#[cfg(test)]
mod tests {
    //! Tier 1: `order_index` drives resume/rollback order and `name` is what
    //! the failure panel prints, so both must stay unique and complete.

    use super::Phase;

    #[test]
    fn all_is_the_eight_phases_in_execution_order() {
        assert_eq!(
            Phase::all(),
            [
                Phase::F1,
                Phase::F2,
                Phase::F3,
                Phase::F4,
                Phase::F5,
                Phase::F6,
                Phase::F7,
                Phase::F8,
            ]
        );
    }

    #[test]
    fn order_index_is_positional_therefore_strictly_increasing_and_unique() {
        // Equality with the position proves both properties in one table: a
        // duplicate or an out-of-order variant breaks it immediately.
        for (position, phase) in Phase::all().iter().enumerate() {
            assert_eq!(
                usize::from(phase.order_index()),
                position,
                "{phase:?} must sit at position {position}"
            );
        }
    }

    #[test]
    fn name_is_non_empty_unique_and_matches_the_order_index() {
        let mut seen: Vec<&str> = Vec::new();
        for phase in Phase::all() {
            let name = phase.name();
            assert!(!name.is_empty(), "{phase:?} has no printable name");
            assert!(!seen.contains(&name), "duplicate phase name {name}");
            seen.push(name);
            assert_eq!(
                name,
                format!("F{}", phase.order_index() + 1).as_str(),
                "{phase:?} name/order mismatch"
            );
        }
    }
}
