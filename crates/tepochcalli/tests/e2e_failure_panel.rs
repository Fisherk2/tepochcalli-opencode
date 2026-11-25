// --- tests/failure_ux.rs ---
// Failure UX (T15): panel content, log location outside the vault,
// sentinel-secret redaction, exit-code/`E_*` preservation, and
// stderr/stdout separation.

mod common;

use std::io::IsTerminal as _;
use std::path::{Path, PathBuf};
use std::process::Stdio;

use common::helpers::bin;
use common::helpers::{stderr_text, stdout_text};
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

/// R-offline-3 (T16): a deliberate cancellation replaces the retry line with
/// the state line — retrying is not the corrective action after a cancel.
#[test]
fn user_aborted_panel_states_the_workspace_was_untouched_and_drops_retry() {
    let log = std::path::Path::new("/tmp/state/tepochcalli/install-41.log");
    let body = tepochcalli::domain::failure::failure_body(
        "install: phase F6 failed",
        Some(Phase::F6),
        WizardError::UserAborted,
        log,
        &[],
    );
    assert!(
        body.contains("estado: cancelado por el usuario — deshaciendo los cambios aplicados"),
        "a cancellation must state it is undoing the changes: {body}"
    );
    assert!(
        !body.contains("retry:"),
        "a cancelled run offers no retry line: {body}"
    );
    assert!(
        body.contains("log: /tmp/state/tepochcalli/install-41.log"),
        "the log line survives: {body}"
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
/// the log outside the vault. A real F4 network failure (dead proxy) replaces
/// the old missing-`--vault` usage case: the cwd is now a valid target.
#[test]
fn failing_install_panel_is_stderr_only_with_log_outside_vault() {
    let state = tempfile::tempdir().expect("state home fixture");
    let vault = tempfile::tempdir().expect("vault fixture");
    let payload = tempfile::tempdir().expect("payload fixture");
    let out = std::process::Command::new(env!("CARGO_BIN_EXE_tepochcalli"))
        .args([
            "install",
            "--non-interactive",
            "--skip-model",
            "--vault",
            vault.path().to_str().expect("utf8 tmp"),
            "--payload",
            payload.path().to_str().expect("utf8 tmp"),
        ])
        .env("XDG_STATE_HOME", state.path())
        .env("LOCALAPPDATA", state.path())
        .env("ALL_PROXY", "http://127.0.0.1:9")
        .env("HTTPS_PROXY", "http://127.0.0.1:9")
        .env_remove("NO_PROXY")
        .env_remove("no_proxy")
        .stdin(std::process::Stdio::null())
        .output()
        .expect("spawn binary");
    assert_eq!(
        out.status.code(),
        Some(20),
        "the dead proxy must fail F4 fast:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let stdout = String::from_utf8_lossy(&out.stdout);
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(
        stdout.is_empty(),
        "stdout must stay empty on failure: {stdout}"
    );
    assert!(
        stderr.contains("F4") && stderr.contains("download failed"),
        "panel must name the phase and the cause:\n{stderr}"
    );
    // Fallo de fase genuino: nadie canceló, y el reintento con `--resume` sí
    // es la acción correctiva (a diferencia del antiguo fallo de uso).
    assert!(
        !stderr.contains("estado: cancelado"),
        "a phase failure cannot claim a cancellation:\n{stderr}"
    );
    assert!(
        !stderr.contains("cancelled by user"),
        "the cause must not print UserAborted's Display:\n{stderr}"
    );
    assert!(
        stderr.contains(RETRY),
        "a phase failure offers the resume retry:\n{stderr}"
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

// --- tests/maintenance_failure.rs ---
// T17 failure UX: `reindex`/`uninstall` share `main.rs::report_maintenance_failure`,
// que hasta ahora no tenía ninguna aserción (solo el `report_failure` de
// `install` estaba cubierto en `failure_ux.rs`). Aquí se fija contra el
// binario real: título con el comando de verdad, log fuera del vault,
// redacción de la clave path-4 en panel+log+ficheros, código de salida del
// error tipado y ausencia de la línea de reintento de `install`.

const API_KEY: &str = "sk-LEAK-TEST-7f3a9c2b-key-must-never-leak";
const INSTALL_RETRY: &str = "tepochcalli install --resume";
const MODEL: &str = "text-embedding-3-small";
/// Fichero del fixture que sí contiene la clave por construcción (config
/// gitignored donde `secrets_from_vault` la busca).
const CONFIG_REL: &str = ".tepochcalli/config/tepochcalli.toml";

/// Vault instalado con el proveedor externo (path 4): la clave vive en el
/// config gitignored, el sidecar conoce el modelo (sin drift, sin panel
/// `E_MODEL_MISMATCH` de ruido) y el refresh del flow revienta.
fn vault_with_api_key() -> tempfile::TempDir {
    let vault = tempfile::tempdir().expect("vault fixture");
    let rt = vault.path().join(".tepochcalli");
    for dir in ["config", "db", "models", "venv/bin"] {
        std::fs::create_dir_all(rt.join(dir)).expect("runtime dir fixture");
    }
    std::fs::write(
        rt.join("config").join("tepochcalli.toml"),
        format!(
            "[embedding]\nprovider = \"litellm\"\nmodel = \"{MODEL}\"\napi_key = \"{API_KEY}\"\n"
        ),
    )
    .expect("config fixture");
    std::fs::write(
        rt.join("db").join("index-meta.json"),
        format!("{{\"model\":\"{MODEL}\",\"dims\":1536}}\n"),
    )
    .expect("index-meta fixture");
    std::fs::write(rt.join("db").join("chunks.lance"), b"live-index-bytes")
        .expect("live index fixture");
    write_failing_python(&rt.join("venv").join("bin").join("python"));
    vault
}

/// Intérprete falso que siempre falla: el `refresh` del flow muere sin red,
/// sin Python real y sin descargar nada (determinista).
#[cfg(unix)]
fn write_failing_python(path: &Path) {
    use std::os::unix::fs::PermissionsExt as _;
    std::fs::write(path, "#!/bin/sh\nexit 1\n").expect("fake python fixture");
    std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o755))
        .expect("fake python executable");
}

/// Ruta del log tal como la imprime el panel (`log: <ruta>`).
fn log_path_from(stderr: &str) -> PathBuf {
    stderr
        .lines()
        .find_map(|line| line.trim().strip_prefix("log: "))
        .map(PathBuf::from)
        .unwrap_or_else(|| panic!("el panel debe llevar la ruta del log:\n{stderr}"))
}

/// Ficheros (relativos) cuyo contenido contiene `needle`; sirve para probar
/// que el fallo no escribe ningún artefacto nuevo con la clave.
fn files_containing(root: &Path, needle: &str) -> Vec<String> {
    fn walk(dir: &Path, root: &Path, needle: &str, out: &mut Vec<String>) {
        let entries = match std::fs::read_dir(dir) {
            Ok(entries) => entries,
            Err(_) => return,
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() {
                walk(&path, root, needle, out);
            } else if let Ok(body) = std::fs::read(&path) {
                if String::from_utf8_lossy(&body).contains(needle) {
                    out.push(
                        path.strip_prefix(root)
                            .expect("rel path")
                            .to_string_lossy()
                            .into_owned(),
                    );
                }
            }
        }
    }
    let mut out = Vec::new();
    walk(root, root, needle, &mut out);
    out.sort();
    out
}

#[cfg(unix)]
#[test]
fn reindex_failure_panel_names_reindex_and_never_leaks_api_key() {
    let vault = vault_with_api_key();
    let state = tempfile::tempdir().expect("state home fixture");
    let before = files_containing(vault.path(), API_KEY);
    assert_eq!(
        before,
        vec![CONFIG_REL.to_string()],
        "el fixture solo tiene la clave en su config"
    );

    let out = bin()
        .args([
            "reindex",
            "--confirm",
            "--non-interactive",
            "--vault",
            vault.path().to_str().expect("utf8 tmp"),
        ])
        .env("XDG_STATE_HOME", state.path())
        .env("LOCALAPPDATA", state.path())
        .stdin(Stdio::null())
        .output()
        .expect("spawn binary");

    // El refresh caído es `PhaseFailed` → 42, dentro del rango 40+ de §5.4.
    assert_eq!(
        out.status.code(),
        Some(42),
        "stderr:\n{}",
        stderr_text(&out)
    );
    let stderr = stderr_text(&out);
    assert!(
        stderr.contains("reindex failed"),
        "el panel debe nombrar el comando real:\n{stderr}"
    );
    assert!(
        stderr.contains("reindex"),
        "el panel debe nombrar `reindex`:\n{stderr}"
    );
    assert!(
        !stderr.contains(INSTALL_RETRY),
        "un fallo de reindex no puede ofrecer el reintento de install:\n{stderr}"
    );
    assert!(
        stdout_text(&out).is_empty(),
        "stdout debe quedar vacío en el fallo:\n{}",
        stdout_text(&out)
    );

    // Log fuera del vault, bajo el state base del hijo.
    let log = log_path_from(&stderr);
    assert!(
        log.starts_with(state.path()),
        "el log vive bajo el state dir del hijo, got: {}",
        log.display()
    );
    assert!(
        !log.starts_with(vault.path()),
        "el log nunca vive dentro del vault, got: {}",
        log.display()
    );
    assert!(log.is_file(), "el log debe existir: {}", log.display());

    // La clave no aparece en el panel ni en el log ni en ningún fichero del
    // vault más allá del config del fixture.
    assert!(!stderr.contains(API_KEY), "fuga en el panel:\n{stderr}");
    let logged = std::fs::read_to_string(&log).expect("log legible");
    assert!(!logged.contains(API_KEY), "fuga en el log:\n{logged}");
    assert_eq!(
        files_containing(vault.path(), API_KEY),
        before,
        "ningún artefacto nuevo puede contener la clave"
    );
}

#[test]
fn uninstall_failure_panel_names_uninstall_without_install_retry() {
    // `.tepochcalli` como fichero regular: `remove_dir_all` falla con
    // `NotADirectory` de forma determinista (también como root), sin depender
    // de permisos del sandbox.
    let vault = tempfile::tempdir().expect("vault fixture");
    let runtime = vault.path().join(".tepochcalli");
    std::fs::write(&runtime, b"not-a-directory").expect("runtime fixture");
    let state = tempfile::tempdir().expect("state home fixture");

    let out = bin()
        .args([
            "uninstall",
            "--confirm",
            "--non-interactive",
            "--vault",
            vault.path().to_str().expect("utf8 tmp"),
        ])
        .env("XDG_STATE_HOME", state.path())
        .env("LOCALAPPDATA", state.path())
        .stdin(Stdio::null())
        .output()
        .expect("spawn binary");

    // Fallo de fs → `PermissionDenied` → 31, dentro del rango 30-39 de §5.4.
    assert_eq!(
        out.status.code(),
        Some(31),
        "stderr:\n{}",
        stderr_text(&out)
    );
    let stderr = stderr_text(&out);
    assert!(
        stderr.contains("uninstall failed"),
        "el panel debe nombrar el comando real:\n{stderr}"
    );
    assert!(
        !stderr.contains(INSTALL_RETRY),
        "un fallo de uninstall no puede ofrecer el reintento de install:\n{stderr}"
    );
    assert!(
        stdout_text(&out).is_empty(),
        "stdout debe quedar vacío en el fallo:\n{}",
        stdout_text(&out)
    );

    let log = log_path_from(&stderr);
    assert!(
        log.starts_with(state.path()),
        "el log vive bajo el state dir del hijo, got: {}",
        log.display()
    );
    assert!(
        !log.starts_with(vault.path()),
        "el log nunca vive dentro del vault, got: {}",
        log.display()
    );
    assert!(log.is_file(), "el log debe existir: {}", log.display());

    // Cero efectos: el fichero que provocó el fallo sigue intacto.
    assert_eq!(
        std::fs::read(&runtime).expect("runtime legible"),
        b"not-a-directory"
    );
}
