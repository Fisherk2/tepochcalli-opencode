//! Real adapters behind the T4 ports (T5): OS processes, HTTP, host probe.
//!
//! Each adapter maps its failures to [`crate::domain::WizardError`] with
//! `map_err` — no `unwrap`/`expect` in this tree.

pub mod host;
pub mod http;
pub mod payload;
pub mod std_proc;
pub mod ui;

pub use host::{find_tool_in, SysHostProbe};
pub use http::UreqHttpClient;
pub use payload::{
    merge_tree, LocalPayload, ReleasePayload, RELEASE_ASSET_SHA256_PLACEHOLDER,
    RELEASE_ASSET_URL_PLACEHOLDER,
};
pub use std_proc::StdCommandRunner;
pub use ui::{HeadlessUi, TtyUi};
