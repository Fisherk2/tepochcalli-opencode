//! Application layer: installer use-cases over the T4 ports (T7).
//!
//! Depends on `domain` + `ports` only — never on `adapters/` (hexagonal
//! rule, same direction as `domain/`).

pub mod installer;

pub use installer::{
    check_prereqs, check_prereqs_on, ensure_vault_dir, is_supported_os, resolve_vault_dir,
    run_phase3, tool_present_in, Phase3Report, PrereqReport, DEFAULT_VAULT_DIR,
    INSTALL_INTENT_PATH, MIN_DISK_FREE_GB, MIN_RAM_GB, PLACEHOLDER_MD_NAME, PLACEHOLDER_PDF_NAME,
    RESOURCES_DIR, SUPPORTED_OS,
};
