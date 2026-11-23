//! P0-2: un flag ausente en `--non-interactive` es un fallo de USO, no una
//! cancelación. El panel nombra lo que falta y el comando correctivo — nunca
//! el Display `cancelled by user` de `UserAborted` (nadie canceló) ni una
//! línea `estado:` de cancelación.

#[allow(dead_code)]
mod common;

use std::process::Stdio;

use common::helpers::bin;

fn state() -> tempfile::TempDir {
    tempfile::tempdir().expect("state home fixture")
}

/// `tepochcalli --non-interactive` sin `--vault`: el menú no puede adivinar el
/// directorio. Uso (falta `--vault`), no cancelación.
#[test]
fn home_non_interactive_without_vault_reports_usage_not_cancel() {
    let state = state();
    let out = bin()
        .arg("--non-interactive")
        .env("XDG_STATE_HOME", state.path())
        .env("LOCALAPPDATA", state.path())
        .stdin(Stdio::null())
        .output()
        .expect("spawn binary");

    assert_eq!(
        out.status.code(),
        Some(41),
        "stderr:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(
        stderr.contains("falta: --vault <directorio>"),
        "el panel debe nombrar el flag que falta:\n{stderr}"
    );
    assert!(
        stderr.contains("uso: tepochcalli --vault <directorio> --non-interactive <subcomando>"),
        "el correctivo es pasar el flag:\n{stderr}"
    );
    assert!(!stderr.contains("estado: cancelado"), "{stderr}");
    assert!(!stderr.contains("cancelled by user"), "{stderr}");
    assert!(
        !stderr.contains("tepochcalli failed"),
        "nadie falló ni canceló: falta un flag:\n{stderr}"
    );
}

/// `update --non-interactive` sin `--vault`: mismo contrato que `install`.
#[test]
fn update_non_interactive_without_vault_reports_usage_not_cancel() {
    let state = state();
    let out = bin()
        .args(["update", "--non-interactive"])
        .env("XDG_STATE_HOME", state.path())
        .env("LOCALAPPDATA", state.path())
        .stdin(Stdio::null())
        .output()
        .expect("spawn binary");

    assert_eq!(
        out.status.code(),
        Some(41),
        "stderr:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(
        stderr.contains("falta: --vault <directorio>"),
        "el panel debe nombrar el flag que falta:\n{stderr}"
    );
    assert!(
        stderr.contains("uso: tepochcalli update --vault <directorio> --non-interactive"),
        "el correctivo es pasar el flag:\n{stderr}"
    );
    assert!(!stderr.contains("estado: cancelado"), "{stderr}");
    assert!(!stderr.contains("cancelled by user"), "{stderr}");
}

/// `uninstall --non-interactive` sin `--vault`: uso (falta `--vault`), no
/// cancelación. `--confirm` viaja porque su ausencia es OTRO gate de uso (2),
/// anterior a la resolución del vault.
#[test]
fn uninstall_non_interactive_without_vault_reports_usage() {
    let state = state();
    let out = bin()
        .args(["uninstall", "--non-interactive", "--confirm"])
        .env("XDG_STATE_HOME", state.path())
        .env("LOCALAPPDATA", state.path())
        .stdin(Stdio::null())
        .output()
        .expect("spawn binary");

    assert_eq!(
        out.status.code(),
        Some(41),
        "stderr:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(
        stderr.contains("falta: --vault <directorio>"),
        "el panel debe nombrar el flag que falta:\n{stderr}"
    );
    assert!(!stderr.contains("cancelado"), "{stderr}");
    assert!(!stderr.contains("cancelled by user"), "{stderr}");
}

/// `reindex --non-interactive --confirm` sin `--vault`: mismo contrato.
#[test]
fn reindex_non_interactive_without_vault_reports_usage() {
    let state = state();
    let out = bin()
        .args(["reindex", "--non-interactive", "--confirm"])
        .env("XDG_STATE_HOME", state.path())
        .env("LOCALAPPDATA", state.path())
        .stdin(Stdio::null())
        .output()
        .expect("spawn binary");

    assert_eq!(
        out.status.code(),
        Some(41),
        "stderr:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(
        stderr.contains("falta: --vault <directorio>"),
        "el panel debe nombrar el flag que falta:\n{stderr}"
    );
    assert!(!stderr.contains("cancelado"), "{stderr}");
    assert!(!stderr.contains("cancelled by user"), "{stderr}");
}

/// `install --non-interactive` contra un mirror `http` no-loopback (TEST-NET-2,
/// sin red real): el gate L4-2 no puede pedir consentimiento sin TUI ⇒ uso
/// (falta un transporte TLS o el consentimiento), no cancelación. Hoy el brazo
/// de uso de `install_phases` devuelve `UserAborted.exit_code()` = 41.
#[test]
fn install_mirror_http_non_interactive_reports_usage() {
    let state = state();
    let vault = tempfile::tempdir().expect("vault fixture");
    let out = bin()
        .args([
            "install",
            "--non-interactive",
            "--skip-model",
            "--vault",
            vault.path().to_str().expect("utf8 vault path"),
        ])
        .env("TEPOCHCALLI_RELEASE_BASE_URL", "http://198.51.100.7")
        .env("XDG_STATE_HOME", state.path())
        .env("LOCALAPPDATA", state.path())
        .stdin(Stdio::null())
        .output()
        .expect("spawn binary");

    let stderr = String::from_utf8_lossy(&out.stderr);
    assert_eq!(out.status.code(), Some(41), "stderr:\n{stderr}");
    assert!(
        stderr.contains("falta:"),
        "el panel debe nombrar lo que falta:\n{stderr}"
    );
    assert!(!stderr.contains("cancelado"), "{stderr}");
    assert!(!stderr.contains("cancelled by user"), "{stderr}");
}

/// `config embedder --non-interactive` sin `--confirm`: el flag ausente es uso
/// (2, como `reindex`/`uninstall`), no cancelación (41). El panel sigue
/// nombrando `--confirm` como correctivo.
#[test]
fn config_embedder_non_interactive_without_confirm_reports_usage() {
    let state = state();
    let vault = tempfile::tempdir().expect("vault fixture");
    let out = bin()
        .args([
            "config",
            "embedder",
            "--non-interactive",
            "--vault",
            vault.path().to_str().expect("utf8 vault path"),
        ])
        .env("XDG_STATE_HOME", state.path())
        .env("LOCALAPPDATA", state.path())
        .stdin(Stdio::null())
        .output()
        .expect("spawn binary");

    let stderr = String::from_utf8_lossy(&out.stderr);
    assert_eq!(out.status.code(), Some(2), "stderr:\n{stderr}");
    assert!(
        stderr.contains("falta:") && stderr.contains("--confirm"),
        "el panel debe nombrar el flag que falta:\n{stderr}"
    );
    assert!(!stderr.contains("cancelado"), "{stderr}");
    assert!(!stderr.contains("cancelled by user"), "{stderr}");
}
