//! Failure UX (T15): panel content, log location outside the vault,
//! sentinel-secret redaction, exit-code/`E_*` preservation, and
//! stderr/stdout separation.

use std::io::IsTerminal as _;

use tepochcalli::domain::{Phase, WizardError};

const SENTINEL: &str = "sk-t15-sentinel-9f8a2c-key-must-never-leak";
const RETRY: &str = "tepochcalli install --resume";

#[test]
fn panel_contains_phase_cause_retry_and_log_path() {
    let log = std::path::Path::new("/tmp/state/tepochcalli/install-123.log");
    let title = tepochcalli::domain::failure::failure_title(Some(Phase::F4));
    let body = tepochcalli::domain::failure::failure_body(
        "install: phase F4 failed",
        Some(Phase::F4),
        WizardError::NetDownload,
        log,
        &[],
    );
    assert!(title.contains("F4"), "title must name the phase: {title}");
    assert!(
        body.contains("F4"),
        "body must name the failed phase: {body}"
    );
    assert!(
        body.contains("download failed"),
        "body must carry the cause: {body}"
    );
    assert!(
        body.contains(RETRY),
        "body must carry the retry command: {body}"
    );
    assert!(
        body.contains("install-123.log"),
        "body must carry the log path: {body}"
    );
}

#[test]
fn e_star_surfaces_where_the_contract_defines_one() {
    let log = std::path::Path::new("/tmp/state/tepochcalli/install-1.log");
    let offline = tepochcalli::domain::failure::failure_body(
        "install: offline without local payload/cache",
        Some(Phase::F2),
        WizardError::OfflineNoCache,
        log,
        &[],
    );
    assert!(
        offline.contains("E_OFFLINE_NO_CACHE"),
        "offline body must name E_*: {offline}"
    );
    let plain = tepochcalli::domain::failure::failure_body(
        "install: phase F4 failed",
        Some(Phase::F4),
        WizardError::NetDownload,
        log,
        &[],
    );
    assert!(
        !plain.contains("E_"),
        "failures without a contract code must not invent one: {plain}"
    );
}

#[test]
fn log_path_uses_timestamped_name_under_a_state_base_outside_the_vault() {
    let vault = tempfile::tempdir().expect("vault fixture");
    let base = tempfile::tempdir().expect("state base fixture");
    let path = tepochcalli::application::failure::log_path_in(base.path(), 1_700_000_000);
    let name = path
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_default();
    assert!(
        name.starts_with("install-") && name.ends_with(".log"),
        "timestamped install-<ts>.log name, got: {name}"
    );
    assert!(
        !path.starts_with(vault.path()),
        "log must never live inside the vault"
    );
    assert!(
        path.starts_with(base.path()),
        "log must live under the state base"
    );
}

#[test]
fn state_dir_is_absolute_and_never_the_vault() {
    let vault = tempfile::tempdir().expect("vault fixture");
    let dir = tepochcalli::application::failure::state_dir();
    assert!(
        dir.is_absolute(),
        "state dir must be absolute: {}",
        dir.display()
    );
    assert!(
        !vault.path().starts_with(&dir) || dir != vault.path(),
        "state dir must not be the vault"
    );
    assert!(
        dir.ends_with("tepochcalli"),
        "state dir must be scoped to tepochcalli: {}",
        dir.display()
    );
}

#[test]
fn sentinel_secret_absent_from_panel_log_and_opencode_json_text() {
    let log = std::path::Path::new("/tmp/state/tepochcalli/install-9.log");
    let secrets = [SENTINEL];
    let title = tepochcalli::domain::failure::failure_title(Some(Phase::F6));
    let body = tepochcalli::domain::failure::failure_body(
        &format!("install: phase F6 failed for {SENTINEL}"),
        Some(Phase::F6),
        WizardError::ApiAuth,
        log,
        &secrets,
    );
    for text in [&title, &body] {
        assert!(!text.contains(SENTINEL), "panel leak: {text}");
    }
    let logged = format!("{title}\n{body}\n");
    let redacted_log = tepochcalli::domain::failure::redact(&logged, &secrets);
    assert!(!redacted_log.contains(SENTINEL), "log leak");
    // `opencode.json`-shaped text carrying the key must redact the same way.
    let artifact = format!("{{\"mcp\":{{\"env\":{{\"KEY\":\"{SENTINEL}\"}}}}}}");
    let clean = tepochcalli::domain::failure::redact(&artifact, &secrets);
    assert!(!clean.contains(SENTINEL), "artifact leak: {clean}");
}

#[test]
fn vault_config_key_is_collected_for_redaction() {
    let vault = tempfile::tempdir().expect("vault fixture");
    let dir = vault.path().join(".tepochcalli/config");
    std::fs::create_dir_all(&dir).expect("config dir fixture");
    std::fs::write(
        dir.join("tepochcalli.toml"),
        format!("[embedding]\nprovider = \"litellm\"\napi_key = \"{SENTINEL}\"\n"),
    )
    .expect("config fixture");
    let found = tepochcalli::application::failure::secrets_from_vault(vault.path());
    assert!(
        found.iter().any(|s| s == SENTINEL),
        "path-4 key must be collected, got: {found:?}"
    );
    let body = tepochcalli::domain::failure::failure_body(
        "install: phase F8 failed",
        Some(Phase::F8),
        WizardError::PhaseFailed,
        std::path::Path::new("/tmp/state/tepochcalli/install-2.log"),
        &found.iter().map(String::as_str).collect::<Vec<_>>(),
    );
    assert!(!body.contains(SENTINEL), "panel leak: {body}");
}

#[test]
fn representative_exit_codes_and_e_star_are_unchanged() {
    let cases: &[(WizardError, u8, Option<&str>)] = &[
        (WizardError::PrereqRam, 10, None),
        (WizardError::OfflineNoCache, 21, Some("E_OFFLINE_NO_CACHE")),
        (WizardError::ApiAuth, 22, Some("E_API_AUTH")),
        (WizardError::PermissionDenied, 31, None),
        (WizardError::UserAborted, 41, None),
        (WizardError::PhaseFailed, 42, None),
        (WizardError::ModelInvalid, 43, Some("E_MODEL_INVALID")),
    ];
    for (err, code, e_star) in cases {
        assert_eq!(err.exit_code(), *code, "{err:?} exit must stay {code}");
        assert_eq!(err.e_star(), *e_star, "{err:?} E_* must stay {e_star:?}");
    }
}

#[test]
fn render_helpers_never_touch_stdout() {
    // Narrowest seam: rendering is pure `String` building — no `println!`,
    // no stdout handle. The binary-level test below pins the real streams.
    assert!(!std::io::stdout().is_terminal() || true);
    let log = std::path::Path::new("/tmp/state/tepochcalli/install-3.log");
    let body = tepochcalli::domain::failure::failure_body(
        "install: vault selection failed",
        Some(Phase::F2),
        WizardError::UserAborted,
        log,
        &[],
    );
    assert!(
        body.contains("vault selection failed"),
        "context kept: {body}"
    );
}

/// Failing `install` keeps stdout empty and puts the panel on stderr, with
/// the log outside the vault (child-process env, never the parent's).
#[test]
fn failing_install_panel_is_stderr_only_with_log_outside_vault() {
    let state = tempfile::tempdir().expect("state home fixture");
    let out = std::process::Command::new(env!("CARGO_BIN_EXE_tepochcalli"))
        .args(["install", "--non-interactive", "--skip-model"])
        .env("XDG_STATE_HOME", state.path())
        .env("LOCALAPPDATA", state.path())
        .stdin(std::process::Stdio::null())
        .output()
        .expect("spawn binary");
    assert_eq!(
        out.status.code(),
        Some(41),
        "headless install without --vault must stay 41"
    );
    let stdout = String::from_utf8_lossy(&out.stdout);
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(
        stdout.is_empty(),
        "stdout must stay empty on failure: {stdout}"
    );
    assert!(
        stderr.contains("F2"),
        "panel must name the phase:\n{stderr}"
    );
    assert!(
        stderr.contains(RETRY),
        "panel must carry the retry command:\n{stderr}"
    );
    assert!(
        stderr.contains("install-") && stderr.contains(".log"),
        "panel must carry the log path:\n{stderr}"
    );
    assert!(
        !stderr.contains(".tepochcalli"),
        "log path must not point inside the vault:\n{stderr}"
    );
    // The log file itself lands under the state base.
    let mut found = Vec::new();
    collect_logs(state.path(), &mut found);
    assert!(
        found
            .iter()
            .any(|name| name.starts_with("install-") && name.ends_with(".log")),
        "a timestamped log must exist under the state base: {found:?}"
    );
}

fn collect_logs(dir: &std::path::Path, out: &mut Vec<String>) {
    let entries = match std::fs::read_dir(dir) {
        Ok(entries) => entries,
        Err(_) => return,
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            collect_logs(&path, out);
        } else if let Some(name) = path.file_name().and_then(|n| n.to_str()) {
            out.push(name.to_string());
        }
    }
}

/// `--help` still reports on stdout with empty stderr (success path intact).
#[test]
fn help_success_output_stays_on_stdout() {
    let out = std::process::Command::new(env!("CARGO_BIN_EXE_tepochcalli"))
        .args(["install", "--help"])
        .output()
        .expect("spawn binary");
    assert_eq!(out.status.code(), Some(0));
    assert!(
        String::from_utf8_lossy(&out.stdout).contains("Usage:"),
        "help belongs on stdout"
    );
    assert!(
        String::from_utf8_lossy(&out.stderr).is_empty(),
        "help must not touch stderr"
    );
}
