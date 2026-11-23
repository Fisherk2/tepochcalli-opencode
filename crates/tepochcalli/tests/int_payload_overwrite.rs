//! H7 (`update`) payload overwrite: [`overwrite_tree`] vs [`rollback_overwrite`].
//!
//! The dangerous half of the wizard: it PISES user files. Every test here
//! pins one guarantee of the journal — identical content is a no-op, a real
//! change leaves `.bak` with the previous bytes, a mid-flight failure can be
//! undone by the caller, and nothing outside the 5 scopes is even visited.

#[allow(dead_code)]
mod common;

use std::path::{Path, PathBuf};

use common::helpers::write_rel;
use tepochcalli::adapters::payload::{merge_tree, overwrite_tree};
use tepochcalli::application::update::rollback_overwrite;
use tepochcalli::domain::{CancelToken, WizardError};
use tepochcalli::ports::OverwriteJournal;
use tepochcalli::UPDATE_SCOPES;

fn tmp() -> tempfile::TempDir {
    tempfile::tempdir().expect("tempdir for the overwrite fixtures")
}

fn read(root: &Path, rel: &str) -> String {
    std::fs::read_to_string(root.join(rel)).expect("fixture read")
}

fn journal() -> OverwriteJournal {
    OverwriteJournal::default()
}

#[test]
fn identical_content_is_a_noop_without_bak() {
    let payload = tmp();
    let vault = tmp();
    write_rel(payload.path(), "AGENTS.md", "mismo\n");
    write_rel(payload.path(), "opencode.json", "{}\n");
    write_rel(vault.path(), "AGENTS.md", "mismo\n");
    write_rel(vault.path(), "opencode.json", "{}\n");

    let mut j = journal();
    overwrite_tree(payload.path(), vault.path(), &UPDATE_SCOPES, &mut j, None).expect("overwrite");

    assert!(j.written.is_empty(), "nada cambió, nada se escribe: {j:?}");
    assert!(j.backed_up.is_empty(), "sin escritura no hay .bak: {j:?}");
    assert!(
        !vault.path().join("AGENTS.md.bak").exists(),
        "la idempotencia real no genera backups"
    );
}

#[test]
fn changed_content_is_written_after_a_bak_of_the_original() {
    let payload = tmp();
    let vault = tmp();
    write_rel(payload.path(), "AGENTS.md", "nuevo\n");
    write_rel(
        payload.path(),
        ".opencode/agents/itzamna.md",
        "nuevo agente\n",
    );
    write_rel(vault.path(), "AGENTS.md", "viejo\n");

    let mut j = journal();
    overwrite_tree(payload.path(), vault.path(), &UPDATE_SCOPES, &mut j, None).expect("overwrite");

    assert_eq!(read(vault.path(), "AGENTS.md"), "nuevo\n");
    assert_eq!(
        read(vault.path(), "AGENTS.md.bak"),
        "viejo\n",
        "el .bak guarda el contenido anterior"
    );
    assert_eq!(
        read(vault.path(), ".opencode/agents/itzamna.md"),
        "nuevo agente\n",
        "un fichero nuevo se crea con sus directorios"
    );
    assert_eq!(j.backed_up, vec![vault.path().join("AGENTS.md")]);
    assert_eq!(j.written.len(), 2, "got: {j:?}");
}

#[test]
fn rollback_restores_the_original_and_removes_created_files() {
    let payload = tmp();
    let vault = tmp();
    write_rel(payload.path(), "AGENTS.md", "nuevo\n");
    write_rel(payload.path(), "opencode.json", "{\"nuevo\":1}\n");
    write_rel(
        payload.path(),
        ".opencode/agents/itzamna.md",
        "nuevo agente\n",
    );
    write_rel(vault.path(), "AGENTS.md", "viejo\n");
    // `opencode.json` no existe en el vault: es un fichero creado.

    let mut j = journal();
    overwrite_tree(payload.path(), vault.path(), &UPDATE_SCOPES, &mut j, None).expect("overwrite");
    assert!(vault.path().join("AGENTS.md.bak").is_file());

    rollback_overwrite(&j);

    assert_eq!(
        read(vault.path(), "AGENTS.md"),
        "viejo\n",
        "el original vuelve byte a byte"
    );
    assert!(
        !vault.path().join("AGENTS.md.bak").exists(),
        "el .bak es residuo del rollback"
    );
    assert!(
        !vault.path().join("opencode.json").exists(),
        "lo que no existía antes del update no sobrevive al rollback"
    );
    assert!(
        !vault.path().join(".opencode/agents/itzamna.md").exists(),
        "los ficheros nuevos también se retiran"
    );
}

#[test]
fn paths_outside_the_scopes_are_ignored() {
    let payload = tmp();
    let vault = tmp();
    write_rel(
        payload.path(),
        "00-resources/payload.md",
        "no debe llegar\n",
    );
    write_rel(payload.path(), "10-templates/base.md", "no debe llegar\n");
    write_rel(payload.path(), ".obsidian/app.json", "{}\n");
    write_rel(payload.path(), "AGENTS.md", "sí\n");
    write_rel(vault.path(), "00-resources/nota.md", "# mía\n");

    let mut j = journal();
    overwrite_tree(payload.path(), vault.path(), &UPDATE_SCOPES, &mut j, None).expect("overwrite");

    assert!(
        !vault.path().join("00-resources/payload.md").exists(),
        "00-resources/ no está en el alcance del update"
    );
    assert!(!vault.path().join("10-templates").exists());
    assert!(
        !vault.path().join(".obsidian/app.json").exists(),
        ".obsidian/ nunca cruza"
    );
    assert_eq!(read(vault.path(), "00-resources/nota.md"), "# mía\n");
    assert_eq!(read(vault.path(), "AGENTS.md"), "sí\n");
    assert_eq!(j.written, vec![vault.path().join("AGENTS.md")]);
}

#[test]
fn midway_failure_leaves_the_journal_for_rollback() {
    let payload = tmp();
    let vault = tmp();
    // El primer fichero se escribe bien; el fallo llega dentro de `.opencode/`,
    // donde el destino es un DIRECTORIO con el nombre que el payload trae como
    // fichero (fs::copy falla con EISDIR: determinista, sin depender del uid).
    write_rel(payload.path(), "AGENTS.md", "nuevo\n");
    write_rel(
        payload.path(),
        ".opencode/agents.md",
        "fichero del payload\n",
    );
    write_rel(vault.path(), "AGENTS.md", "viejo\n");
    std::fs::create_dir_all(vault.path().join(".opencode/agents.md")).expect("dir trampa");
    write_rel(vault.path(), ".opencode/agents.md/hijo.md", "x\n");

    let mut j = journal();
    let err = overwrite_tree(payload.path(), vault.path(), &UPDATE_SCOPES, &mut j, None)
        .expect_err("el destino directorio no se puede pisar con un fichero");
    assert!(
        matches!(err, WizardError::DiskFull | WizardError::PermissionDenied),
        "fallo tipado, nunca pánico: {err:?}"
    );
    assert!(
        !j.written.is_empty() || !j.backed_up.is_empty(),
        "el diario conserva lo hecho hasta el fallo: {j:?}"
    );

    rollback_overwrite(&j);
    assert_eq!(read(vault.path(), "AGENTS.md"), "viejo\n");
    assert!(
        vault.path().join(".opencode/agents.md").is_dir(),
        "el directorio trampa sigue siendo un directorio"
    );
}

#[cfg(unix)]
#[test]
fn update_no_escribe_a_traves_de_un_bak_symlink() {
    // Un `.bak` que ya existía como enlace (puesto por otro) no puede ser el
    // destino del backup: `fs::copy` escribiría a través de él, fuera del vault.
    let payload = tmp();
    let vault = tmp();
    let outside = tmp();
    write_rel(payload.path(), "AGENTS.md", "nuevo\n");
    write_rel(vault.path(), "AGENTS.md", "viejo\n");
    write_rel(outside.path(), "secret", "no tocar\n");
    std::os::unix::fs::symlink(
        outside.path().join("secret"),
        vault.path().join("AGENTS.md.bak"),
    )
    .expect("symlink .bak");

    let mut j = journal();
    overwrite_tree(payload.path(), vault.path(), &UPDATE_SCOPES, &mut j, None).expect("overwrite");

    assert_eq!(
        read(outside.path(), "secret"),
        "no tocar\n",
        "el backup no se escribe a través del .bak enlazado"
    );
    assert_eq!(read(vault.path(), "AGENTS.md"), "nuevo\n");
}

#[cfg(unix)]
#[test]
fn rollback_no_lee_a_traves_de_un_bak_symlink() {
    // Restaurar desde un `.bak` enlazado copiaría contenido externo al vault.
    let vault = tmp();
    let outside = tmp();
    write_rel(vault.path(), "AGENTS.md", "nuevo\n");
    write_rel(outside.path(), "evil", "contenido externo\n");
    std::os::unix::fs::symlink(
        outside.path().join("evil"),
        vault.path().join("AGENTS.md.bak"),
    )
    .expect("symlink .bak");

    let mut j = journal();
    j.backed_up.push(vault.path().join("AGENTS.md"));
    rollback_overwrite(&j);

    assert_eq!(
        read(vault.path(), "AGENTS.md"),
        "nuevo\n",
        "no se restaura desde un .bak ajeno"
    );
}

#[cfg(unix)]
#[test]
fn symlinks_are_never_followed() {
    let payload = tmp();
    let vault = tmp();
    let outside = tmp();
    write_rel(outside.path(), "secreto.md", "no debe copiarse\n");
    std::os::unix::fs::symlink(
        outside.path().join("secreto.md"),
        payload.path().join("AGENTS.md"),
    )
    .expect("symlink fixture");

    let mut j = journal();
    overwrite_tree(payload.path(), vault.path(), &UPDATE_SCOPES, &mut j, None).expect("overwrite");

    assert!(
        !vault.path().join("AGENTS.md").exists(),
        "un symlink del payload no se materializa como fichero"
    );
    assert!(j.written.is_empty() && j.backed_up.is_empty(), "got: {j:?}");
    assert_eq!(read(outside.path(), "secreto.md"), "no debe copiarse\n");
}

#[cfg(unix)]
#[test]
fn symlink_destination_file_is_rejected() {
    let payload = tmp();
    let vault = tmp();
    let outside = tmp();
    write_rel(payload.path(), "AGENTS.md", "nuevo\n");
    write_rel(outside.path(), "secreto.md", "no tocar\n");
    std::os::unix::fs::symlink(
        outside.path().join("secreto.md"),
        vault.path().join("AGENTS.md"),
    )
    .expect("symlink de destino");

    let mut j = journal();
    let err = overwrite_tree(payload.path(), vault.path(), &UPDATE_SCOPES, &mut j, None)
        .expect_err("un destino enlazado escribiría fuera del vault");
    assert!(matches!(err, WizardError::PayloadCorrupt), "got: {err:?}");
    assert_eq!(
        read(outside.path(), "secreto.md"),
        "no tocar\n",
        "el fichero externo queda byte-intacto"
    );
    assert!(j.written.is_empty() && j.backed_up.is_empty(), "got: {j:?}");
}

#[cfg(unix)]
#[test]
fn symlink_destination_dir_is_rejected() {
    let payload = tmp();
    let vault = tmp();
    let outside = tmp();
    write_rel(payload.path(), ".opencode/x.md", "nuevo\n");
    std::fs::create_dir_all(outside.path().join("dir")).expect("outside dir");
    std::os::unix::fs::symlink(outside.path().join("dir"), vault.path().join(".opencode"))
        .expect("symlink de directorio");

    let mut j = journal();
    let err = overwrite_tree(payload.path(), vault.path(), &UPDATE_SCOPES, &mut j, None)
        .expect_err("un directorio enlazado escribiría fuera del vault");
    assert!(matches!(err, WizardError::PayloadCorrupt), "got: {err:?}");
    assert!(
        !outside.path().join("dir/x.md").exists(),
        "nada se materializa a través del enlace"
    );
}

#[cfg(unix)]
#[test]
fn merge_tree_rejects_a_dangling_symlink_destination() {
    let payload = tmp();
    let vault = tmp();
    let outside = tmp();
    write_rel(payload.path(), "AGENTS.md", "nuevo\n");
    // Enlace a una ruta INEXISTENTE: `target.exists()` es `false` y `fs::copy`
    // crearía el fichero a través del enlace, fuera del vault.
    std::os::unix::fs::symlink(
        outside.path().join("ausente"),
        vault.path().join("AGENTS.md"),
    )
    .expect("symlink colgante");

    let err = merge_tree(payload.path(), vault.path())
        .expect_err("un destino enlazado no puede materializarse");
    assert!(matches!(err, WizardError::PayloadCorrupt), "got: {err:?}");
    assert!(
        !outside.path().join("ausente").exists(),
        "el destino externo NO se crea"
    );
}

#[test]
fn scope_entries_match_whole_components_only() {
    // `.opencode-evil/` empieza por el mismo texto que `.opencode` pero es
    // otro componente: el alcance es por componente, no por prefijo de texto.
    let payload = tmp();
    let vault = tmp();
    write_rel(payload.path(), ".opencode-evil/x.md", "fuera\n");
    write_rel(payload.path(), ".opencode/x.md", "dentro\n");

    let mut j = journal();
    overwrite_tree(payload.path(), vault.path(), &UPDATE_SCOPES, &mut j, None).expect("overwrite");

    assert!(!vault.path().join(".opencode-evil").exists());
    assert_eq!(read(vault.path(), ".opencode/x.md"), "dentro\n");
    assert_eq!(j.written, vec![vault.path().join(".opencode/x.md")]);
}

#[test]
fn cancelled_before_the_walk_touches_nothing() {
    // H7 cancelable: un token ya disparado aborta tipado en la primera
    // entrada del walk — sin escritura, sin `.bak`, journal intacto.
    let payload = tmp();
    let vault = tmp();
    write_rel(payload.path(), "AGENTS.md", "nuevo\n");
    write_rel(vault.path(), "AGENTS.md", "viejo\n");
    let cancel = CancelToken::new();
    cancel.cancel();

    let mut j = journal();
    let err = overwrite_tree(
        payload.path(),
        vault.path(),
        &UPDATE_SCOPES,
        &mut j,
        Some(&cancel),
    )
    .expect_err("un token cancelado debe abortar tipado");
    assert!(matches!(err, WizardError::UserAborted), "got: {err:?}");
    assert_eq!(read(vault.path(), "AGENTS.md"), "viejo\n");
    assert!(j.written.is_empty() && j.backed_up.is_empty(), "got: {j:?}");
}

#[test]
fn scopes_are_exactly_the_five_payload_paths() {
    // Pin del alcance: si alguien amplía el update, este test lo delata.
    assert_eq!(
        UPDATE_SCOPES,
        [
            ".opencode",
            ".tepochcalli",
            ".gitignore",
            "opencode.json",
            "AGENTS.md"
        ]
    );
}

#[test]
fn journal_is_a_plain_path_list() {
    // Sin magia: el caller (application/update) lo serializa a conteos.
    let mut j = journal();
    j.written.push(PathBuf::from("/v/AGENTS.md"));
    assert_eq!(j.written.len() + j.backed_up.len(), 1);
}
