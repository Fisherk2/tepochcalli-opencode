//! Real adapters behind the T4 ports (T5): OS processes, HTTP, host probe.
//!
//! Each adapter maps its failures to [`crate::domain::WizardError`] with
//! `map_err` — no `unwrap`/`expect` in this tree.

pub mod host;
pub mod http;
pub mod std_proc;

pub use host::{find_tool_in, SysHostProbe};
pub use http::UreqHttpClient;
pub use std_proc::StdCommandRunner;
