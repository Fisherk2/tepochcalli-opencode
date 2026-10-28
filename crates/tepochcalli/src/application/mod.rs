//! Application layer: installer use-cases over the T4 ports (T7).
//!
//! Depends on `domain` + `ports` only — never on `adapters/` (hexagonal
//! rule, same direction as `domain/`).

pub mod embedder_menu;
pub mod failure;
pub mod installer;
pub mod phase7;
pub mod phase8;

pub use embedder_menu::{
    compensate_phase6, config_path, read_completed_report, run_phase6, Phase6Deps, Phase6Report,
    Provenance, EMBEDDER_PATHS,
};
pub use installer::{
    check_prereqs, check_prereqs_on, compensate_phase1, compensate_phase2, compensate_phase3,
    compensate_phase4, compensate_phase5, completed_phases, ensure_vault_dir,
    guard_offline_before_touch, is_phase_done, is_supported_os, mark_phase_done,
    payload_local_ready, resolve_vault_dir, run_phase3, run_phase4, run_phase4_with, run_phase5,
    tool_present_in, venv_python, Phase3Report, Phase4Report, Phase5Report, PrereqReport,
    DEFAULT_VAULT_DIR, IMPORT_CHECK, INSTALL_INTENT_PATH, INSTALL_STATE_PATH, MIN_DISK_FREE_GB,
    MIN_RAM_GB, PLACEHOLDER_MD_NAME, PLACEHOLDER_PDF_NAME, RESOURCES_DIR, RUNTIME_DIR,
    SUPPORTED_OS, UV_BIN_DIR, UV_MANAGED_PYTHON, UV_PROJECT_ENVIRONMENT, UV_STAGE_DIR,
    VENV_DIR_NAME,
};
pub use phase7::{compensate_phase7, index_meta_path, run_phase7, Phase7Report};
pub use phase8::{
    compensate_phase8, mcp_python_command, mcp_python_command_for, run_phase8, Phase8Report,
    RagHealth, MANAGED_RAG, OPENCODE_BAK, OPENCODE_JSON, RAG_STATUS_PROBE, STALE_MARKITDOWN,
};
