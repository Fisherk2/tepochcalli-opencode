pub mod archive;
pub mod domain;
pub mod fetch;
pub mod ports;

pub use domain::{
    Badge, EmbedderChoice, InstallContext, InstallOutcome, InstallPlan, Phase, PhaseOutcome,
    PhaseState, ResourceFacts, VaultPath, WizardError,
};
pub use ports::{CommandOutput, CommandRunner, GpuInfo, HostProbe, HttpClient, PayloadSource, Ui};
