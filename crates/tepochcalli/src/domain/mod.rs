//! Pure installer domain: phases, vault path, embedder menu, errors.
//!
//! No I/O here: no filesystem, process, or network access, no `adapters/`,
//! no third-party infra crates — only std core types plus `thiserror`.

pub mod embedder;
pub mod error;
pub mod failure;
pub mod menu;
pub mod phase;
pub mod plan;
pub mod version;

pub use embedder::{Badge, EmbedderChoice, ResourceFacts};
pub use error::WizardError;
pub use menu::{installed_state, menu_spec, InstalledState, MenuAction, MenuButton, MenuSpec};
pub use phase::Phase;
pub use plan::VaultPath;
pub use version::Version;
