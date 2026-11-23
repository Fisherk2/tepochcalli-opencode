//! R-offline-3 (T15): el rollback restaura los bytes del snapshot y borra lo
//! que la corrida añadió — notas, PDFs y `.obsidian/` nunca se tocan.
//!
//! Vaults `tempfile` reales (D26: sin puerto FS) y sin procesos hijo.

// `common` es módulo compartido: este target no toca la mayoría de fakes.
mod common;

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use common::helpers;

use tepochcalli::adapters::LocalPayload;
use tepochcalli::application::{ensure_vault_dir, rollback_install, run_phase3, InstallSnapshot};
use tepochcalli::{OPENCODE_BAK, OPENCODE_JSON};

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

    let report = rollback_install(&vault, &snapshot);

    assert!(
        report.compensated.iter().any(|label| label == "runtime"),
        "el runtime creado por la corrida se declara deshecho: {report:?}"
    );
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

/// Hueco #7(a) — `rollback_install` con `executed` VACÍO: el snapshot y el
/// estado actual coinciden ⇒ no se compensa nada, no hay pánico y no se
/// crea ningún temporal.
///
/// Regresión que detecta: si `executed` se calculara mal (p. ej. metiendo
/// fases que YA estaban en `snapshot.completed`, o compensando por
/// defecto), el rollback tocaría F4/F5 sobre un vault que nunca cambió —
/// `compensate_phase4`/`compensate_phase5` se llevarían `bin/uv` o
/// `venv/`— y `tree()` dejaría de ser byte-idéntico. Un temporal huérfano
/// también aparecería en el mapa.
#[test]
fn rollback_sin_fases_ejecutadas_es_un_no_op_byte_identico() {
    let (_dir, vault) = prior_vault("F1\nF2\n");
    let before = tree(&vault);
    let snapshot = InstallSnapshot::capture(&vault);

    let report = rollback_install(&vault, &snapshot);

    assert!(
        report.compensated.is_empty(),
        "sin fases ejecutadas no se deshizo nada: {report:?}"
    );
    assert_eq!(
        tree(&vault),
        before,
        "sin fases nuevas el árbol vuelve byte a byte, sin temporales"
    );
    assert!(
        vault.join(".tepochcalli/bin/uv").is_file(),
        "lo ya instalado (F4) no se compensa en una corrida que no lo tocó"
    );
    assert!(
        vault.join(".tepochcalli/venv/bin/python").is_file(),
        "lo ya instalado (F5) no se compensa en una corrida que no lo tocó"
    );
}

/// Hueco #7(b) — PRIMER brazo del orden inverso: F8 en `executed` (jamás
/// ejercitado antes). Runtime preexistente para no disparar el
/// `remove_dir_all` del runtime; el snapshot se captura SIN F8 completado y
/// después F8 «corre»: `opencode.json` con la key gestionada
/// (`completed_phases` lo detecta por su artefacto, no por marker) más su
/// `.bak` con los bytes previos.
///
/// Regresión que detecta: si `rollback_install` no llamara a
/// `compensate_phase8` (rollback.rs:77), `opencode.json` seguiría con el
/// merge y sobreviviría `opencode.json.bak` ⇒ `tree()` deja de ser
/// byte-idéntico. También distingue los dos brazos del contrato de
/// `compensate_phase8`: con `.bak` RESTAURA los bytes previos y retira el
/// backup (sin `.bak` borraría el fichero que F8 creó — caso que este test
/// no ejercita a propósito, para no mezclar ramas).
#[test]
fn rollback_compens_f8_y_restaura_opencode_json_desde_su_backup() {
    let (_dir, vault) = prior_vault("F1\nF2\n");
    // El fichero del USUARIO, SIN la key gestionada: F8 no está completado
    // en el momento del snapshot.
    let original: &[u8] = b"{\"mcp\":{\"servers\":{\"otro-server\":{}}}}\n";
    write(&vault.join(OPENCODE_JSON), original);
    let snapshot = InstallSnapshot::capture(&vault);
    let before = tree(&vault);

    // F8 «corrió»: backup de los bytes previos + merge con la key.
    write(&vault.join(OPENCODE_BAK), original);
    write(
        &vault.join(OPENCODE_JSON),
        b"{\"mcp\":{\"servers\":{\"otro-server\":{},\"tepochcalli-rag\":{\"type\":\"local\"}}}}\n",
    );
    assert!(
        tepochcalli::completed_phases(&vault).contains(&tepochcalli::Phase::F8),
        "el fixture debe dejar F8 completado por su artefacto"
    );

    rollback_install(&vault, &snapshot);

    assert_eq!(
        std::fs::read(vault.join(OPENCODE_JSON)).expect("opencode.json"),
        original,
        "compensate_phase8 restaura los bytes previos desde el .bak"
    );
    assert!(
        !vault.join(OPENCODE_BAK).exists(),
        "el backup de F8 se retira al restaurar"
    );
    assert_eq!(
        tree(&vault),
        before,
        "el resto del árbol queda byte-idéntico"
    );
}

/// P0-1 (P1-2): un fichero del usuario creado DESPUÉS del snapshot (mientras
/// la instalación corría) sobrevive al rollback. Antes se hacía
/// `remove_dir_all(vault)` y se lo llevaba por delante.
#[test]
fn rollback_no_borra_el_contenido_del_usuario_creado_tras_el_snapshot() {
    let dir = tmp();
    let vault = dir.path().join("vault");
    let snapshot = InstallSnapshot::capture(&vault); // no existía

    ensure_vault_dir(&vault).expect("vault nuevo");
    write(&vault.join(".tepochcalli/bin/uv"), b"uv");
    // El usuario guarda una nota mientras la instalación corre.
    write(&vault.join("nota-usuario.md"), "# mía\n".as_bytes());

    let report = rollback_install(&vault, &snapshot);

    assert_eq!(
        std::fs::read(vault.join("nota-usuario.md")).expect("la nota sobrevive"),
        "# mía\n".as_bytes(),
        "un fichero del usuario creado durante el install no se borra"
    );
    assert!(
        !report.preserved.is_empty(),
        "el informe debe declarar el contenido conservado: {report:?}"
    );
    assert!(
        !report.leftovers.iter().any(|p| p.contains("nota-usuario")),
        "lo conservado no es un resto: {report:?}"
    );
}

/// Hueco verificado: F3 escribe fuera del runtime (`.opencode/`,
/// `10-templates/`, `AGENTS.md`, `.gitignore`) ANTES de que exista
/// `.install-intent` (se escribe tras el ÉXITO de F3). Si F3 falla a mitad, la
/// compensación por intent no tiene qué borrar: la verificación debe declarar
/// esas raíces como resto, no afirmar «el vault quedó como estaba».
#[test]
fn rollback_declara_resto_cuando_f3_dejo_ficheros_sin_intent() {
    let dir = tmp();
    let vault = dir.path().join("vault");
    std::fs::create_dir_all(&vault).expect("vault preexistente vacío");
    let snapshot = InstallSnapshot::capture(&vault);

    // F3 a medias: mergeó parte del payload y murió antes de write_intent.
    write(&vault.join(".opencode/agents/x.md"), b"# agente\n");

    let report = rollback_install(&vault, &snapshot);

    assert!(
        !report.is_complete(),
        "un residuo sin intent no puede darse por limpio: {report:?}"
    );
    assert!(
        report.leftovers.iter().any(|p| p == ".opencode"),
        "la raíz gestionada que sobrevivió se declara como resto: {report:?}"
    );
}

/// F8 escribe `opencode.json` FUERA del runtime; si la corrida lo pisó sin
/// dejar `.bak` (fallo antes del backup), el rollback debe medir los bytes
/// contra el snapshot y declarar el fichero como resto.
#[test]
fn rollback_detecta_opencode_json_modificado() {
    let dir = tmp();
    let vault = dir.path().join("vault");
    write(&vault.join(OPENCODE_JSON), b"{\"mcp\":{\"servers\":{}}}\n");
    let snapshot = InstallSnapshot::capture(&vault);

    // Pisado tras el snapshot sin marcar F8 ni dejar .bak.
    write(
        &vault.join(OPENCODE_JSON),
        b"{\"mcp\":{\"servers\":{\"otro\":{}}}}\n",
    );

    let report = rollback_install(&vault, &snapshot);

    assert!(!report.is_complete(), "{report:?}");
    assert!(
        report.leftovers.iter().any(|p| p == OPENCODE_JSON),
        "el opencode.json alterado se declara como resto: {report:?}"
    );
}

/// P0-1: el informe es honesto — si el runtime no se puede borrar, lo declara
/// incompleto en vez de afirmar que el vault quedó como estaba.
#[cfg(unix)]
#[test]
fn rollback_incompleto_cuando_el_runtime_no_se_puede_borrar() {
    use std::os::unix::fs::PermissionsExt as _;

    if helpers::running_as_root() {
        eprintln!("skipped: running as root (CAP_DAC_OVERRIDE)");
        return;
    }

    let dir = tmp();
    let vault = dir.path().join("vault");
    let snapshot = InstallSnapshot::capture(&vault);
    ensure_vault_dir(&vault).expect("vault nuevo");
    let runtime = vault.join(".tepochcalli");
    write(&runtime.join("bin/uv"), b"uv");
    std::fs::set_permissions(&runtime, std::fs::Permissions::from_mode(0o555))
        .expect("runtime de solo lectura");

    let report = rollback_install(&vault, &snapshot);

    // Restaurar permisos para que `tempfile` pueda limpiar su directorio.
    let _ = std::fs::set_permissions(&runtime, std::fs::Permissions::from_mode(0o755));

    assert!(
        runtime.is_dir(),
        "fixture: el runtime no se pudo borrar (0o555), así que sigue ahí"
    );
    assert!(
        !report.is_complete(),
        "un runtime que no se pudo borrar deja resto: {report:?}"
    );
    assert!(!report.leftovers.is_empty(), "{report:?}");
}
