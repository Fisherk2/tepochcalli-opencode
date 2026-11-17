//! Binary-only CLI modules split out of `main.rs` (pure relocations: the
//! messages, exit codes and phase order are byte-identical). They never
//! cross `lib.rs` — the `application::*` public exports are unchanged.

mod commands;
mod flags;
mod install;
mod install_phases;
mod report;
mod usage;

pub(crate) use commands::{run_config_embedder, run_reindex_cmd, run_uninstall_cmd};
pub(crate) use install::run_install;
pub(crate) use usage::{bare_config, print_help, print_version, unknown, usage_top};
