//! Pure installer domain: phases, plan, embedder menu, outcome, errors.
//!
//! No I/O here: no filesystem, process, or network access, no `adapters/`,
//! no third-party infra crates — only std core types plus `thiserror`.

pub mod embedder;
pub mod error;
pub mod outcome;
pub mod phase;
pub mod plan;

pub use embedder::{Badge, EmbedderChoice, ResourceFacts};
pub use error::WizardError;
pub use outcome::InstallOutcome;
pub use phase::{Phase, PhaseOutcome, PhaseState};
pub use plan::{InstallContext, InstallPlan, VaultPath};
