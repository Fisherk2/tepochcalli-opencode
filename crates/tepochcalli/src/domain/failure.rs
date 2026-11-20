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
    // R-offline-3: tras una cancelación deliberada la acción correctiva no es
    // reintentar, sino confirmar que el workspace quedó intacto.
    if err == WizardError::UserAborted {
        body.push_str(
            "estado: cancelado por el usuario — el workspace quedó como estaba (cambios deshechos)\n",
        );
    } else {
        body.push_str("retry: ");
        body.push_str(RETRY_COMMAND);
        body.push('\n');
    }
    body.push_str("log: ");
    body.push_str(&log_path.to_string_lossy());
    body.push('\n');
    redact(&body, secrets)
}

#[cfg(test)]
mod tests {
    //! Tier 1: `redact` is a security boundary (no path-4 key may reach a panel,
    //! log or artifact) and the panel text is the graded contract, so both are
    //! pinned here rather than through the CLI.

    use super::{failure_body, failure_title, redact, RETRY_COMMAND};
    use crate::domain::{Phase, WizardError};
    use std::path::Path;

    const SECRET: &str = "sk-live-3f8a-path4-secret";
    const OTHER_SECRET: &str = "hf_OTHER-9f8a2c";

    #[test]
    fn redact_ignores_an_empty_secret_instead_of_shredding_the_text() {
        // `str::replace("")` splices the placeholder between every character;
        // an unset key (menu path 1/2/5) is exactly that empty string.
        assert_eq!(redact("tepochcalli install", &[""]), "tepochcalli install");
    }

    #[test]
    fn redact_replaces_every_occurrence_of_a_repeated_secret() {
        let text = format!("key={SECRET} again={SECRET}");
        let out = redact(&text, &[SECRET]);
        assert!(!out.contains(SECRET), "secret survived: {out}");
        assert_eq!(out, "key=[redacted] again=[redacted]");
        assert_eq!(out.matches("[redacted]").count(), 2, "both copies: {out}");
    }

    #[test]
    fn redact_leaves_text_without_the_secret_untouched() {
        assert_eq!(redact("nothing to hide", &[SECRET]), "nothing to hide");
    }

    #[test]
    fn redact_scrubs_several_secrets_and_leaves_no_fragment_behind() {
        let text = format!("a={SECRET} b={OTHER_SECRET} c={SECRET}");
        let out = redact(&text, &[SECRET, OTHER_SECRET, ""]);
        for secret in [SECRET, OTHER_SECRET] {
            assert!(!out.contains(secret), "{secret} survived: {out}");
        }
        assert_eq!(out.matches("[redacted]").count(), 3, "{out}");
    }

    #[test]
    fn redact_scrubs_a_secret_embedded_in_json_or_a_path() {
        // The shapes that actually leak: `opencode.json` and a log path.
        let json = format!("{{\"api_key\": \"{SECRET}\"}}");
        assert_eq!(
            redact(&json, &[SECRET]),
            "{\"api_key\": \"[redacted]\"}",
            "JSON arm must not keep the key"
        );
        let path = format!("/tmp/state/{SECRET}/install.log");
        let out = redact(&path, &[SECRET]);
        assert!(!out.contains(SECRET), "path leaked: {out}");
        assert_eq!(out, "/tmp/state/[redacted]/install.log");
    }

    #[test]
    fn title_names_the_phase_only_when_one_is_known() {
        assert_eq!(failure_title(None), "install failed");
        for phase in Phase::all() {
            let title = failure_title(Some(phase));
            assert_eq!(title, format!("install failed ({})", phase.name()));
        }
    }

    #[test]
    fn body_without_phase_omits_the_phase_line_but_keeps_the_contract() {
        let body = failure_body(
            "install: path 4",
            None,
            WizardError::ApiAuth,
            Path::new("/tmp/state/install-1.log"),
            &[],
        );
        assert!(!body.contains("phase:"), "no phase was known: {body}");
        assert!(
            body.contains("cause: install: path 4: API key rejected"),
            "cause line must carry context + typed error: {body}"
        );
        assert!(body.contains("code: E_API_AUTH"), "{body}");
        assert!(body.contains(RETRY_COMMAND), "{body}");
        assert!(body.contains("log: /tmp/state/install-1.log"), "{body}");
    }

    #[test]
    fn body_for_user_aborted_states_the_cancellation_and_skips_retry() {
        // R-offline-3 (T16): retrying is not the fix after a deliberate
        // cancel; the panel states the workspace is untouched instead.
        let body = failure_body(
            "install: cancelled",
            Some(Phase::F6),
            WizardError::UserAborted,
            Path::new("/tmp/state/install-4.log"),
            &[],
        );
        assert!(
            body.contains("estado: cancelado por el usuario — el workspace quedó como estaba"),
            "{body}"
        );
        assert!(!body.contains("retry:"), "{body}");
        assert!(body.contains("log: /tmp/state/install-4.log"), "{body}");
    }

    #[test]
    fn body_with_phase_names_it_and_skips_the_code_line_without_e_star() {
        let body = failure_body(
            "install: phase F7 failed",
            Some(Phase::F7),
            WizardError::Internal,
            Path::new("/tmp/state/install-2.log"),
            &[],
        );
        assert!(body.starts_with("phase: F7\n"), "{body}");
        assert!(body.contains("internal wizard error"), "{body}");
        assert!(
            !body.contains("code:"),
            "`Internal` has no E_* equivalent, so no code line: {body}"
        );
    }

    #[test]
    fn body_redacts_a_secret_from_the_context_and_the_log_path() {
        let context = format!("config rejected {SECRET}");
        let log = format!("/tmp/state/{SECRET}/install-3.log");
        let body = failure_body(
            &context,
            Some(Phase::F6),
            WizardError::ApiAuth,
            Path::new(&log),
            &[SECRET],
        );
        assert!(
            !body.contains(SECRET),
            "secret leaked into the panel: {body}"
        );
        assert!(body.contains("[redacted]"), "{body}");
        assert!(body.contains("code: E_API_AUTH"), "{body}");
    }
}
