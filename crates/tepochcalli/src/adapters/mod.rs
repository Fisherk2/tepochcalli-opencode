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
    fetch_release_payload, merge_tree, parse_sha256_sidecar, payload_asset_name, payload_asset_url,
    payload_checksum_name, payload_checksum_url, payload_release_tag, release_payload_from_sidecar,
    LocalPayload, ReleasePayload, PAYLOAD_ASSET_STEM, PAYLOAD_RELEASE_REPO,
    RELEASE_ASSET_SHA256_PLACEHOLDER, RELEASE_ASSET_URL_PLACEHOLDER,
};
pub use std_proc::StdCommandRunner;
pub use ui::{HeadlessUi, TtyUi};
