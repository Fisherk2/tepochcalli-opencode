//! R-offline-3 (T15): el rollback restaura los bytes del snapshot y borra lo
//! que la corrida añadió — notas, PDFs y `.obsidian/` nunca se tocan.
//!
//! Vaults `tempfile` reales (D26: sin puerto FS) y sin procesos hijo.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use tepochcalli::adapters::LocalPayload;
use tepochcalli::application::{ensure_vault_dir, rollback_install, run_phase3, InstallSnapshot};

/// Ruta relativa → bytes, recursivo. Los directorios vacíos no aparecen en el
/// mapa: la igualdad es de FICHEROS, no de estructura vacía.
fn tree(dir: &Path) -> BTreeMap<String, Vec<u8>> {
    let mut out = BTreeMap::new();
    let mut stack = vec![dir.to_path_buf()];
    while let Some(current) = stack.pop() {
        let Ok(entries) = std::fs::read_dir(&current) else {
            continue;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() {
                stack.push(path);
            } else if let Ok(bytes) = std::fs::read(&path) {
                if let Ok(rel) = path.strip_prefix(dir) {
                    out.insert(rel.to_string_lossy().into_owned(), bytes);
                }
            }
        }
    }
    out
}

fn write(path: &Path, body: &[u8]) {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).expect("fixture dir");
    }
    std::fs::write(path, body).expect("fixture file");
}

fn tmp() -> tempfile::TempDir {
    tempfile::tempdir().expect("tempdir")
}

/// Payload local de 2 `.md` (uno dentro de `00-resources/`).
fn payload(dir: &Path) -> PathBuf {
    write(&dir.join("00-resources").join("nuevo.md"), b"# nuevo\n");
    write(&dir.join("AGENTS.md"), b"# agents\n");
    dir.to_path_buf()
}

/// Vault con runtime previo: config, markers y los artefactos de F4/F5.
fn prior_vault(marker: &str) -> (tempfile::TempDir, PathBuf) {
    let dir = tmp();
    let vault = dir.path().join("vault");
    write(&vault.join("00-resources/nota.md"), b"# nota del usuario\n");
    write(&vault.join(".obsidian/app.json"), b"{\"theme\":\"dark\"}");
    write(
        &vault.join(".tepochcalli/config/tepochcalli.toml"),
        b"viejo",
    );
    write(
        &vault.join(".tepochcalli/.install-state"),
        marker.as_bytes(),
    );
    write(&vault.join(".tepochcalli/bin/uv"), b"uv");
    write(&vault.join(".tepochcalli/venv/bin/python"), b"python");
    (dir, vault)
}

#[test]
fn install_fresco_fallido_no_deja_ni_el_directorio() {
    let dir = tmp();
    let vault = dir.path().join("vault");
    let payload_dir = payload(&dir.path().join("payload"));
    let snapshot = InstallSnapshot::capture(&vault);

    ensure_vault_dir(&vault).expect("vault nuevo");
    run_phase3(&LocalPayload::new(&payload_dir), &vault).expect("F3");
    // Fases posteriores simuladas: marker, `bin/`, `venv/` y config.
    write(
        &vault.join(".tepochcalli/.install-state"),
        b"F1\nF2\nF3\nF4\nF5\nF6\n",
    );
    write(&vault.join(".tepochcalli/bin/uv"), b"uv");
    write(&vault.join(".tepochcalli/venv/bin/python"), b"python");
    write(
        &vault.join(".tepochcalli/config/tepochcalli.toml"),
        b"nuevo",
    );

    rollback_install(&vault, &snapshot);

    assert!(
        !vault.exists(),
        "un install fresco fallido no deja ni el directorio"
    );
}

/// Marker sin F3 a propósito: los artefactos de F4/F5 los corrobora el probe,
/// y F3 queda como fase de ESTA corrida — su journal (`.install-intent`) solo
/// lista lo que escribe ahora. Con un intent previo borrarlo destruiría el
/// payload anterior: ese caso queda fuera de la promesa (límite declarado).
#[test]
fn reinstalacion_no_toca_lo_del_usuario_y_restaura_los_bytes() {
    let (dir, vault) = prior_vault("F1\nF2\n");
    let before = tree(&vault);
    let snapshot = InstallSnapshot::capture(&vault);

    let payload_dir = payload(&dir.path().join("payload"));
    run_phase3(&LocalPayload::new(&payload_dir), &vault).expect("F3");
    write(
        &vault.join(".tepochcalli/config/tepochcalli.toml"),
        b"nuevo",
    );
    write(
        &vault.join(".tepochcalli/db/index-meta.json"),
        b"{\"model\":\"nuevo\",\"dims\":1}\n",
    );
    write(
        &vault.join(".tepochcalli/.install-state"),
        b"F1\nF2\nF3\nF4\nF5\nF6\nF7\n",
    );

    rollback_install(&vault, &snapshot);

    assert_eq!(tree(&vault), before, "el árbol vuelve byte a byte");
    assert!(
        !vault.join(".tepochcalli/.install-intent").exists(),
        "el journal de F3 no sobrevive al rollback"
    );
}

#[test]
fn modelo_previo_sobrevive() {
    let (dir, vault) = prior_vault("F1\nF2\n");
    let old = vault.join(".tepochcalli/models/old@sha");
    write(&old.join("config.json"), b"{}");
    let snapshot = InstallSnapshot::capture(&vault);

    let payload_dir = payload(&dir.path().join("payload"));
    run_phase3(&LocalPayload::new(&payload_dir), &vault).expect("F3");
    let new = vault.join(".tepochcalli/models/new@sha");
    write(&new.join("config.json"), b"{}");

    rollback_install(&vault, &snapshot);

    assert!(old.is_dir(), "un modelo previo legítimo nunca se toca");
    assert!(!new.exists(), "el snapshot nacido en la corrida se purga");
}

#[test]
fn resume_no_revierte_lo_que_ya_estaba() {
    let (_dir, vault) = prior_vault("F1\nF2\nF3\nF4\nF5\n");
    let snapshot = InstallSnapshot::capture(&vault);

    // Solo F6/F7 se escriben en esta corrida.
    write(
        &vault.join(".tepochcalli/config/tepochcalli.toml"),
        b"nuevo",
    );
    write(
        &vault.join(".tepochcalli/db/index-meta.json"),
        b"{\"model\":\"nuevo\",\"dims\":1}\n",
    );
    write(
        &vault.join(".tepochcalli/.install-state"),
        b"F1\nF2\nF3\nF4\nF5\nF6\nF7\n",
    );

    rollback_install(&vault, &snapshot);

    assert!(
        vault.join(".tepochcalli/bin/uv").is_file(),
        "lo ya instalado (F4) sobrevive a un resume"
    );
    assert!(
        vault.join(".tepochcalli/venv/bin/python").is_file(),
        "lo ya instalado (F5) sobrevive a un resume"
    );
    assert_eq!(
        std::fs::read(vault.join("00-resources/nota.md")).expect("nota"),
        b"# nota del usuario\n",
        "el payload previo y los datos del usuario quedan intactos"
    );
    assert_eq!(
        std::fs::read(vault.join(".tepochcalli/config/tepochcalli.toml")).expect("config"),
        b"viejo",
        "la config vuelve a sus bytes previos"
    );
    assert!(
        !vault.join(".tepochcalli/db/index-meta.json").exists(),
        "el sidecar de esta corrida se revierte (ausente antes ⇒ ausente ahora)"
    );
    assert_eq!(
        std::fs::read(vault.join(".tepochcalli/.install-state")).expect("marker"),
        b"F1\nF2\nF3\nF4\nF5\n",
        "el marker vuelve a las fases que ya estaban"
    );
}
