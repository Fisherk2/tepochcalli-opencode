//! Real adapters behind the T4 ports (T5): OS processes, HTTP, host probe.
//!
//! Each adapter maps its failures to [`crate::domain::WizardError`] with
//! `map_err` — no `unwrap`/`expect` in this tree.

pub mod archive;
pub mod fetch;
pub mod host;
pub mod http;
pub mod payload;
pub mod std_proc;
pub mod ui;
pub mod ui_ratatui;

pub use host::{find_tool_in, path_dirs, SysHostProbe};
pub use http::UreqHttpClient;
pub use payload::{
    fetch_release_payload, is_loopback_base, merge_tree, mirror_http_non_loopback,
    parse_sha256_sidecar, payload_asset_name, payload_asset_url, payload_checksum_name,
    payload_checksum_url, payload_release_tag, release_base_url, release_payload_from_sidecar,
    sidecar_url_for, LocalPayload, ReleasePayload, PAYLOAD_ASSET_STEM, PAYLOAD_RELEASE_REPO,
};
pub use std_proc::StdCommandRunner;
pub use ui::{HeadlessUi, TtyUi};
