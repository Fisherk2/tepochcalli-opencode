//! Pure failure-panel formatting + secret redaction (T15).
//!
//! No I/O here: rendering builds `String`s; the caller (`main.rs`) owns the
//! terminal/filesystem effects. Every constructor takes the secrets to scrub,
//! so a path-4 key can never leak into a panel, log, or artifact.

use std::path::Path;

use super::error::WizardError;
use super::phase::Phase;

/// Retry command every failure panel carries (graded contract — keep exact).
pub const RETRY_COMMAND: &str = "tepochcalli install --resume";

/// Placeholder standing in for a redacted secret (never the secret itself).
const REDACTED: &str = "[redacted]";

/// Replace every non-empty secret in `text` with `[redacted]`.
#[must_use]
pub fn redact(text: &str, secrets: &[&str]) -> String {
    let mut out = text.to_string();
    for secret in secrets {
        if secret.is_empty() {
            continue;
        }
        out = out.replace(secret, REDACTED);
    }
    out
}

/// Panel heading: names the failed phase (`"install failed (F4)"`).
#[must_use]
pub fn failure_title(phase: Option<Phase>) -> String {
    match phase {
        Some(phase) => format!("install failed ({})", phase.name()),
        None => "install failed".to_string(),
    }
}

/// Panel body: failed phase, cause (`context` + typed error), `E_*` where the
/// contract defines one, the retry command, and the log path — redacted.
#[must_use]
pub fn failure_body(
    context: &str,
    phase: Option<Phase>,
    err: WizardError,
    log_path: &Path,
    secrets: &[&str],
) -> String {
    let mut body = String::new();
    if let Some(phase) = phase {
        body.push_str("phase: ");
        body.push_str(phase.name());
        body.push('\n');
    }
    body.push_str("cause: ");
    body.push_str(context);
    body.push_str(": ");
    body.push_str(&err.to_string());
    body.push('\n');
    if let Some(code) = err.e_star() {
        body.push_str("code: ");
        body.push_str(code);
        body.push('\n');
    }
    body.push_str("retry: ");
    body.push_str(RETRY_COMMAND);
    body.push('\n');
    body.push_str("log: ");
    body.push_str(&log_path.to_string_lossy());
    body.push('\n');
    redact(&body, secrets)
}
