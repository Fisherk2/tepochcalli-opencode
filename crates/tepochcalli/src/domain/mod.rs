//! Pure installer domain: phases, vault path, embedder menu, errors.
//!
//! No I/O here: no filesystem, process, or network access, no `adapters/`,
//! no third-party infra crates — only std core types plus `thiserror`.

pub mod embedder;
pub mod error;
pub mod failure;
pub mod phase;
pub mod plan;

pub use embedder::{Badge, EmbedderChoice, ResourceFacts};
pub use error::WizardError;
pub use phase::Phase;
pub use plan::VaultPath;
