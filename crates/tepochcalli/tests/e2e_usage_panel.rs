//! P0-2: un flag ausente en `--non-interactive` es un fallo de USO, no una
//! cancelación. El panel nombra lo que falta y el comando correctivo — nunca
//! el Display `cancelled by user` de `UserAborted` (nadie canceló) ni una
//! línea `estado:` de cancelación.

use std::process::{Command, Stdio};

fn bin() -> Command {
    Command::new(env!("CARGO_BIN_EXE_tepochcalli"))
}

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
