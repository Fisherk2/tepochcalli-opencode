pub mod adapters;
pub mod application;
pub mod archive;
pub mod domain;
pub mod fetch;
pub mod ports;

pub use application::{
    check_prereqs, check_prereqs_on, ensure_vault_dir, is_supported_os, resolve_vault_dir,
    tool_present_in, PrereqReport, DEFAULT_VAULT_DIR, MIN_DISK_FREE_GB, MIN_RAM_GB, SUPPORTED_OS,
};

pub use domain::{
    Badge, EmbedderChoice, InstallContext, InstallOutcome, InstallPlan, Phase, PhaseOutcome,
    PhaseState, ResourceFacts, VaultPath, WizardError,
};
pub use ports::{CommandOutput, CommandRunner, GpuInfo, HostProbe, HttpClient, PayloadSource, Ui};
