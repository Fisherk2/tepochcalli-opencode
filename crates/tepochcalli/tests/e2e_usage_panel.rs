//! P0-2: un flag ausente en `--non-interactive` es un fallo de USO, no una
//! cancelación. El panel nombra lo que falta y el comando correctivo — nunca
//! el Display `cancelled by user` de `UserAborted` (nadie canceló) ni una
//! línea `estado:` de cancelación.

mod common;

use std::process::Stdio;

use common::helpers::bin;

fn state() -> tempfile::TempDir {
    tempfile::tempdir().expect("state home fixture")
}

/// `tepochcalli --non-interactive` sin `--vault`: el cwd es el vault, así que
/// lo único que puede faltar es la selección del menú (sin guion). Nunca se
/// pregunta por el directorio ni se afirma una cancelación.
#[test]
fn home_non_interactive_without_vault_reports_menu_usage_not_cancel() {
    let state = state();
    let cwd = tempfile::tempdir().expect("cwd fixture");
    let out = bin()
        .arg("--non-interactive")
        .current_dir(cwd.path())
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
        stderr.contains("menu selection failed"),
        "the only missing answer is the menu button:\n{stderr}"
    );
    assert!(
        !stderr.contains("falta: --vault <directorio>"),
        "the vault is no longer a question:\n{stderr}"
    );
    assert!(!stderr.contains("estado: cancelado"), "{stderr}");
    assert!(!stderr.contains("cancelled by user"), "{stderr}");
    assert!(
        !stderr.contains("tepochcalli failed"),
        "the menu had no script, not a failure:\n{stderr}"
    );
}

/// `update --non-interactive` sin `--vault`: el cwd es el vault; sin runtime
/// instalado el fallo es de fase (2), no un panel de flag ausente.
#[test]
fn update_non_interactive_without_vault_uses_cwd_and_fails_for_missing_install() {
    let state = state();
    let cwd = tempfile::tempdir().expect("cwd fixture");
    let out = bin()
        .args(["update", "--non-interactive"])
        .current_dir(cwd.path())
        .env("XDG_STATE_HOME", state.path())
        .env("LOCALAPPDATA", state.path())
        .stdin(Stdio::null())
        .output()
        .expect("spawn binary");

    assert_eq!(
        out.status.code(),
        Some(2),
        "stderr:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(
        stderr.contains("no hay instalación") && stderr.contains(cwd.path().to_str().unwrap()),
        "the cwd must be named as the target:\n{stderr}"
    );
    assert!(
        !stderr.contains("falta: --vault <directorio>") && !stderr.contains("estado: cancelado"),
        "no vault question was asked:\n{stderr}"
    );
    assert!(!stderr.contains("cancelled by user"), "{stderr}");
}

/// `uninstall --non-interactive` sin `--vault`: el cwd es el vault. `--confirm`
/// viaja porque su ausencia sigue siendo un gate de uso (2).
#[test]
fn uninstall_non_interactive_without_vault_uses_cwd_and_is_idempotent() {
    let state = state();
    let cwd = tempfile::tempdir().expect("cwd fixture");
    let out = bin()
        .args(["uninstall", "--non-interactive", "--confirm"])
        .current_dir(cwd.path())
        .env("XDG_STATE_HOME", state.path())
        .env("LOCALAPPDATA", state.path())
        .stdin(Stdio::null())
        .output()
        .expect("spawn binary");

    assert_eq!(
        out.status.code(),
        Some(0),
        "stderr:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(
        String::from_utf8_lossy(&out.stdout).contains("nothing to remove"),
        "an empty cwd has no runtime to remove:\n{}",
        String::from_utf8_lossy(&out.stdout)
    );
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(
        !stderr.contains("falta: --vault <directorio>"),
        "no vault question was asked:\n{stderr}"
    );
    assert!(!stderr.contains("cancelado"), "{stderr}");
    assert!(!stderr.contains("cancelled by user"), "{stderr}");
}

/// `reindex --non-interactive --confirm` sin `--vault`: el cwd es el vault y
/// el reindex falla tipado porque allí no hay instalación.
#[test]
fn reindex_non_interactive_without_vault_uses_cwd_and_fails_typed() {
    let state = state();
    let cwd = tempfile::tempdir().expect("cwd fixture");
    let out = bin()
        .args(["reindex", "--non-interactive", "--confirm"])
        .current_dir(cwd.path())
        .env("XDG_STATE_HOME", state.path())
        .env("LOCALAPPDATA", state.path())
        .stdin(Stdio::null())
        .output()
        .expect("spawn binary");

    assert_eq!(
        out.status.code(),
        Some(42),
        "stderr:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(
        stderr.contains("Sin instalación"),
        "the empty cwd must be reported as an uninstalled vault:\n{stderr}"
    );
    assert!(
        !stderr.contains("falta: --vault <directorio>"),
        "no vault question was asked:\n{stderr}"
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
