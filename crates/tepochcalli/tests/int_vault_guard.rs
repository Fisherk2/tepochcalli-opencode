//! F2 guard: `--vault` no puede ser él mismo un enlace (`x -> /`), o el probe
//! de escritura se materializaría fuera del vault destino.
#![cfg(unix)]

use tepochcalli::application::ensure_vault_dir;
use tepochcalli::domain::WizardError;

#[test]
fn symlinked_vault_root_is_rejected() {
    let outside = tempfile::tempdir().expect("outside");
    let parent = tempfile::tempdir().expect("parent");
    let link = parent.path().join("vault");
    std::os::unix::fs::symlink(outside.path(), &link).expect("raíz enlazada");

    let err = ensure_vault_dir(&link).expect_err("un enlace no es un vault válido");
    assert!(matches!(err, WizardError::PermissionDenied), "got: {err:?}");
    assert!(
        !outside.path().join(".tepochcalli-write-probe").exists(),
        "el probe no se escribe a través de la raíz enlazada"
    );
}
