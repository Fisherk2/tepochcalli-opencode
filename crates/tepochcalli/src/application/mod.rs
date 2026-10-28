//! Application layer: installer use-cases over the T4 ports (T7).
//!
//! Depends on `domain` + `ports` only — never on `adapters/` (hexagonal
//! rule, same direction as `domain/`).

pub mod installer;

pub use installer::{
    check_prereqs, check_prereqs_on, ensure_vault_dir, is_supported_os, resolve_vault_dir,
    tool_present_in, PrereqReport, DEFAULT_VAULT_DIR, MIN_DISK_FREE_GB, MIN_RAM_GB, SUPPORTED_OS,
};
