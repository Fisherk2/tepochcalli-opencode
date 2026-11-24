//! On-demand availability check for the default embedder download (gap 5 of
//! the Phase 6.5 audit): the HuggingFace URLs the product really uses must
//! not be a broken link.
//!
//! Real network traffic, so every test is `#[ignore]`d: the default suite
//! (`just rust-test`, `just ci`) must never depend on the network — same
//! convention as `int_fetch_verified.rs`, which pins all traffic to a
//! localhost fake. Run explicitly with `just rust-model-check`.
//!
//! URLs are read from the product code, not from memory:
//! * API: `HF_API_BASE` in `src/application/embedder_estimate.rs:11`
//!   (`pub(super)`, unreachable from a test target) — the endpoint the wizard
//!   calls for the pre-download estimate of a free model id.
//! * resolve: the gate downloads the PINNED revision of the default preset
//!   (`src/config/presets.toml` → `revision`, same SHA as
//!   `tepochcalli_flow.config.MODEL_REVISION`) through `sentence-transformers`,
//!   which prefixes bare ids with the `sentence-transformers` org
//!   (`default_huggingface_organization`, sentence_transformers/base/model.py)
//!   — the bare id answers 401 on the HF API, the org-qualified one is the
//!   link the installer actually follows.

use std::time::Duration;

/// `HF_API_BASE` (`src/application/embedder_estimate.rs:11`), replicated
/// because the constant is `pub(super)` to the `application` module.
const HF_API_BASE: &str = "https://huggingface.co/api/models/";
/// Default model, org-qualified the way the download path resolves it.
const DEFAULT_MODEL: &str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2";
/// Pinned revision of the default preset (`src/config/presets.toml`).
const DEFAULT_REVISION: &str = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42";
/// Per-request budget: short on purpose — a dead link or an absent network
/// must fail fast with a clear message, never hang the run.
const TIMEOUT: Duration = Duration::from_secs(15);

/// Agent that fails on any status instead of turning it into `Err`: the
/// assertions below own the verdict so a non-200 reads as `left: 401`, not as
/// an opaque transport error.
fn agent() -> ureq::Agent {
    let config = ureq::Agent::config_builder()
        .timeout_global(Some(TIMEOUT))
        .http_status_as_error(false)
        .build();
    ureq::Agent::new_with_config(config)
}

/// Transport failure (DNS down, timeout, TLS) with the URL and the fix hint.
fn unreachable(url: &str, error: ureq::Error) -> ! {
    panic!(
        "HuggingFace unreachable for {url}: {error} — \
         no network, or the download link is broken. \
         Re-run with `just rust-model-check` once connectivity is back."
    );
}

#[test]
#[ignore = "network: run with `just rust-model-check`"]
fn hf_api_serves_metadata_for_the_default_model() {
    let url = format!("{HF_API_BASE}{DEFAULT_MODEL}");
    let mut response = agent()
        .get(&url)
        .call()
        .unwrap_or_else(|e| unreachable(&url, e));
    let status = response.status().as_u16();
    assert!(
        (200..300).contains(&status) || (300..400).contains(&status),
        "HF API for {url} answered {status}, expected 200 (3xx = redirect HF follows to its CDN)"
    );
    if (300..400).contains(&status) {
        return; // headers only: the redirect target is checked by the test below
    }
    let body = response
        .body_mut()
        .read_to_string()
        .unwrap_or_else(|e| unreachable(&url, e));
    assert!(
        body.contains("\"modelId\""),
        "HF API answer for {url} carries no `modelId`: {}",
        body.chars().take(200).collect::<String>()
    );
}

#[test]
#[ignore = "network: run with `just rust-model-check`"]
fn default_model_snapshot_resolves_on_huggingface() {
    let url =
        format!("https://huggingface.co/{DEFAULT_MODEL}/resolve/{DEFAULT_REVISION}/config.json");
    // HEAD: headers only — never the ~470 MB of weights.
    let response = agent()
        .head(&url)
        .call()
        .unwrap_or_else(|e| unreachable(&url, e));
    let status = response.status().as_u16();
    assert!(
        (200..300).contains(&status) || (300..400).contains(&status),
        "pinned snapshot {url} answered {status}, expected 200 (3xx = redirect HF follows to its CDN) — \
         the default model download would fail"
    );
}
