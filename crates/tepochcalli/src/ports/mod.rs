//! Hexagonal ports: the wizard's seams to the outside world (T4).
//!
//! Ports depend on `domain` only (never on `adapters/` or infra crates), so
//! T5 adapters and `tests/common` fakes are interchangeable behind them.
//! No `FileSystem` port on purpose (D26): compensation tests run on a real
//! `tempfile` dir.

pub mod host;
pub mod net;
pub mod payload;
pub mod proc;
pub mod ui;

pub use host::{GpuInfo, HostFacts, HostProbe};
pub use net::HttpClient;
pub use payload::{backup_path, MergeReport, OverwriteJournal, PayloadSource};
pub use proc::{CommandOutput, CommandRunner};
pub use ui::{MenuView, Ui};
