pub mod adapters;
pub mod application;
pub mod config;
pub mod domain;
pub mod ports;

pub use application::{
    check_prereqs_on, compensate_phase1, compensate_phase2, compensate_phase3, compensate_phase4,
    compensate_phase5, compensate_phase6, compensate_phase7, completed_phases, config_path,
    ensure_vault_dir, guard_offline_before_touch, index_meta_path, is_phase_done, is_supported_os,
    litellm_config_present, mark_phase_done, mcp_python_command, mcp_python_command_for,
    payload_local_ready, read_completed_report, resolve_vault_dir, run_phase3, run_phase4,
    run_phase4_with, run_phase5, run_phase6, run_phase7, run_phase8, run_reindex, run_swap,
    run_uninstall, run_update, tool_present_in, venv_python, Phase3Report, Phase4Report,
    Phase5Report, Phase6Deps, Phase6Report, Phase7Report, Phase8Report, PrereqReport, Provenance,
    RagHealth, ReindexReport, SwapDeps, SwapOptions, SwapReport, UninstallReport, UpdateReport,
    DEFAULT_VAULT_DIR, EMBEDDER_PATHS, IMPORT_CHECK, INSTALL_INTENT_PATH, INSTALL_STATE_PATH,
    MANAGED_RAG, MIN_DISK_FREE_GB, MIN_RAM_GB, OPENCODE_BAK, OPENCODE_JSON, PLACEHOLDER_MD_NAME,
    PLACEHOLDER_PDF_NAME, RAG_STATUS_PROBE, RESOURCES_DIR, RUNTIME_DIR, STALE_MARKITDOWN,
    SUPPORTED_OS, UNINSTALL_BACKUP_SCOPES, UNINSTALL_SCOPES, UPDATE_SCOPES, UV_BIN_DIR,
    UV_MANAGED_PYTHON, UV_PROJECT_ENVIRONMENT, UV_STAGE_DIR, VENV_DIR_NAME,
};

pub use domain::{Badge, EmbedderChoice, Phase, ResourceFacts, VaultPath, WizardError};
pub use ports::{CommandOutput, CommandRunner, GpuInfo, HostProbe, HttpClient, PayloadSource, Ui};
