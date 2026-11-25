//! H8 partial desinstall: cuando el borrado falla a mitad, el error tipado
//! debe seguir diciendo DÓNDE está el backup ya creado con lo irreemplazable.

mod common;

use common::helpers;
use common::TapUi;
use tepochcalli::application::maintenance::run_uninstall;
use tepochcalli::domain::WizardError;

#[cfg(unix)]
#[test]
fn uninstall_partial_desinstall_names_the_backup_dir() {
    use std::os::unix::fs::PermissionsExt as _;

    if helpers::running_as_root() {
        eprintln!("skipped: running as root (CAP_DAC_OVERRIDE)");
        return;
    }

    let vault = tempfile::tempdir().expect("tempdir for the uninstall fixture");
    let opencode = vault.path().join(".opencode");
    std::fs::create_dir_all(&opencode).expect("fixture dir");
    std::fs::write(opencode.join("hijo.md"), "# hijo\n").expect("fixture file");
    // Sin escritura en el directorio, `remove_dir_all` no puede vaciarlo.
    std::fs::set_permissions(&opencode, std::fs::Permissions::from_mode(0o555))
        .expect("quitar escritura");

    let ui = TapUi::new(vec![], vec![]);
    let result = run_uninstall(&ui, vault.path());

    // Restaura los permisos antes de asertar para que `TempDir` pueda limpiar.
    std::fs::set_permissions(&opencode, std::fs::Permissions::from_mode(0o755))
        .expect("restaurar permisos");

    let err = result.expect_err("el scope sin permiso de escritura falla");
    assert!(matches!(err, WizardError::PermissionDenied), "got: {err:?}");

    let backup = std::fs::read_dir(vault.path())
        .expect("vault readable")
        .filter_map(|entry| entry.ok())
        .map(|entry| entry.path())
        .find(|path| {
            path.file_name()
                .is_some_and(|name| name.to_string_lossy().starts_with(".tepochcalli-backup-"))
        })
        .expect("el backup se crea ANTES de borrar");

    let captured = ui.captured().join("\n");
    assert!(
        captured.contains("El backup con lo irreemplazable está en"),
        "panel de desinstall interrumpido ausente:\n{captured}"
    );
    assert!(
        captured.contains(&backup.display().to_string()),
        "la ruta del backup debe estar en el panel:\n{captured}"
    );
    assert!(
        vault.path().join(".opencode").exists(),
        "el fallo es parcial: el scope sigue ahí"
    );
}
