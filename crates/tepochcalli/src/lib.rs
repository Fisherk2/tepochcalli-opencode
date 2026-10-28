pub mod adapters;
pub mod application;
pub mod archive;
pub mod domain;
pub mod fetch;
pub mod ports;

pub use application::{
    check_prereqs, check_prereqs_on, ensure_vault_dir, is_supported_os, resolve_vault_dir,
    run_phase3, tool_present_in, Phase3Report, PrereqReport, DEFAULT_VAULT_DIR,
    INSTALL_INTENT_PATH, MIN_DISK_FREE_GB, MIN_RAM_GB, PLACEHOLDER_MD_NAME, PLACEHOLDER_PDF_NAME,
    RESOURCES_DIR, SUPPORTED_OS,
};

pub use domain::{
    Badge, EmbedderChoice, InstallContext, InstallOutcome, InstallPlan, Phase, PhaseOutcome,
    PhaseState, ResourceFacts, VaultPath, WizardError,
};
pub use ports::{CommandOutput, CommandRunner, GpuInfo, HostProbe, HttpClient, PayloadSource, Ui};
