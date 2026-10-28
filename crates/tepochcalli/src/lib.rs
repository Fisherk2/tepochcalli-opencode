pub mod adapters;
pub mod application;
pub mod archive;
pub mod config;
pub mod domain;
pub mod fetch;
pub mod ports;

pub use application::{
    check_prereqs, check_prereqs_on, compensate_phase4, compensate_phase5, ensure_vault_dir,
    is_supported_os, resolve_vault_dir, run_phase3, run_phase4, run_phase4_with, run_phase5,
    tool_present_in, Phase3Report, Phase4Report, Phase5Report, PrereqReport, DEFAULT_VAULT_DIR,
    IMPORT_CHECK, INSTALL_INTENT_PATH, MIN_DISK_FREE_GB, MIN_RAM_GB, PLACEHOLDER_MD_NAME,
    PLACEHOLDER_PDF_NAME, RESOURCES_DIR, RUNTIME_DIR, SUPPORTED_OS, UV_BIN_DIR, UV_MANAGED_PYTHON,
    UV_PROJECT_ENVIRONMENT, UV_STAGE_DIR, VENV_DIR_NAME,
};

pub use domain::{
    Badge, EmbedderChoice, InstallContext, InstallOutcome, InstallPlan, Phase, PhaseOutcome,
    PhaseState, ResourceFacts, VaultPath, WizardError,
};
pub use ports::{CommandOutput, CommandRunner, GpuInfo, HostProbe, HttpClient, PayloadSource, Ui};
