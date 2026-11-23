//! H7/H8 cancelación (R-offline-2): [`CancellingUi`] dispara el token antes de
//! `work`, así que `run_update`/`run_uninstall` abortan tipados y el vault no
//! cambia. Cubre las dos operaciones de escritura con alcance fijo de ficheros.

// `common` es módulo compartido: este target no toca la mayoría de fakes.
#[allow(dead_code)]
mod common;

use common::{CancellingUi, FakePayload};
use tepochcalli::domain::WizardError;
use tepochcalli::{run_uninstall, run_update};

fn tmp() -> tempfile::TempDir {
    tempfile::tempdir().expect("tempdir para la cancelación")
}

#[test]
fn update_cancelado_antes_de_escribir_deja_el_vault_intacto() {
    let payload = tmp();
    let vault = tmp();
    std::fs::write(payload.path().join("AGENTS.md"), "nuevo\n").expect("fixture payload");
    std::fs::write(vault.path().join("AGENTS.md"), "mío\n").expect("fixture vault");

    let err = run_update(
        &FakePayload::new(payload.path()),
        &CancellingUi::default(),
        vault.path(),
    )
    .expect_err("un update cancelado debe abortar tipado");

    assert!(matches!(err, WizardError::UserAborted), "got: {err:?}");
    assert_eq!(
        std::fs::read_to_string(vault.path().join("AGENTS.md")).expect("leer AGENTS.md"),
        "mío\n",
        "un overwrite cancelado no pisa nada"
    );
    assert!(
        !vault.path().join("AGENTS.md.bak").exists(),
        "sin escritura no hay backup"
    );
}

#[test]
fn uninstall_cancelado_antes_del_backup_conserva_los_tres_scopes() {
    let vault = tmp();
    std::fs::create_dir_all(vault.path().join(".opencode")).expect("scope .opencode");
    std::fs::write(vault.path().join(".opencode/x.md"), "x\n").expect("fichero .opencode");
    std::fs::create_dir_all(vault.path().join(".tepochcalli")).expect("scope .tepochcalli");
    std::fs::write(
        vault.path().join(".tepochcalli/pyproject.toml"),
        "version = \"0.1.0\"\n",
    )
    .expect("pyproject del runtime");
    std::fs::write(vault.path().join("opencode.json"), "{}\n").expect("opencode.json");
    std::fs::write(vault.path().join("nota.md"), "# mía\n").expect("nota del usuario");

    let err = run_uninstall(&CancellingUi::default(), vault.path())
        .expect_err("un desinstall cancelado debe abortar tipado");

    assert!(matches!(err, WizardError::UserAborted), "got: {err:?}");
    for scope in [".opencode", ".tepochcalli", "opencode.json"] {
        assert!(
            vault.path().join(scope).exists(),
            "{scope} debe seguir presente"
        );
    }
    assert_eq!(
        std::fs::read_to_string(vault.path().join("nota.md")).expect("leer nota"),
        "# mía\n"
    );
    let leftovers = std::fs::read_dir(vault.path())
        .expect("leer vault")
        .filter_map(Result::ok)
        .filter(|entry| {
            entry
                .file_name()
                .to_string_lossy()
                .starts_with(".tepochcalli-backup-")
        })
        .count();
    assert_eq!(leftovers, 0, "cancelar antes del backup no deja residuo");
}
