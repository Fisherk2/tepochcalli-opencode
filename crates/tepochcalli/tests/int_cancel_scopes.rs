//! H7 cancelación (R-offline-2): [`CancellingUi`] dispara el token antes de
//! `work`, así que `run_update` aborta tipado y el vault no cambia. H8 se
//! cubre en el commit de `run_uninstall`.

// `common` es módulo compartido: este target no toca la mayoría de fakes.
#[allow(dead_code)]
mod common;

use common::{CancellingUi, FakePayload};
use tepochcalli::domain::WizardError;
use tepochcalli::run_update;

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
