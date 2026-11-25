//! T17: `reindex --confirm` + `uninstall`.
//!
//! RED-first: todo aquí fallaba antes de que existieran
//! `application::maintenance::{run_reindex, run_uninstall}` y su cableado en
//! `main.rs`. Vaults `tempfile` reales (D26: sin puerto FS); solo fakes
//! (`TapUi` de `common` que graba paneles, `RecordingProc` que fija argv +
//! cwd + env). Ningún modelo se descarga: los fixtures `gate_ok`/`refresh_ok`
//! replican los contratos T11/T12. El gate `--confirm` y los flags
//! `--vault`/`--non-interactive` se prueban contra el binario real.

mod common;

use std::path::{Path, PathBuf};
use std::process::Stdio;

use common::helpers::bin;
use common::helpers::{stderr_text, stdout_text};
use common::{gate_ok, seed_runtime, FakeProc, RecordingProc, TapUi, UiEvent};
use tepochcalli::application::maintenance::{run_reindex, run_uninstall};
use tepochcalli::domain::WizardError;
use tepochcalli::ports::CommandOutput;

const OLD_MODEL: &str = "paraphrase-multilingual-MiniLM-L12-v2";
const NEW_MODEL: &str = "BAAI/bge-m3";
/// Embedder externo vía LiteLLM: no hay nada local que descargar ni medir.
const EXTERNAL_MODEL: &str = "openai/text-embedding-3-small";

fn tmp() -> tempfile::TempDir {
    tempfile::tempdir().expect("tempdir for T17 fixtures")
}

/// Vault ya instalado: config local + sidecar + índice vivo + intérprete +
/// ficheros de usuario (notas, payload, `opencode.json`, `.obsidian`) que
/// ningún comando T17 puede tocar.
fn installed_vault() -> tempfile::TempDir {
    installed_vault_with(OLD_MODEL, OLD_MODEL)
}

/// Config con `config_model`, sidecar con `meta_model` (para forzar el
/// drift `E_MODEL_MISMATCH` basta pedirlos distintos).
fn installed_vault_with(config_model: &str, meta_model: &str) -> tempfile::TempDir {
    let vault = tmp();
    seed_runtime(vault.path(), config_model, meta_model);
    // Ficheros del usuario: fuera de `.tepochcalli/`, intocables.
    std::fs::create_dir_all(vault.path().join("00-resources")).expect("resources fixture");
    std::fs::write(
        vault.path().join("00-resources").join("ejemplo.md"),
        "# Ejemplo\n",
    )
    .expect("md fixture");
    std::fs::create_dir_all(vault.path().join("notes")).expect("notes fixture");
    std::fs::write(
        vault.path().join("notes").join("diaria.md"),
        "# nota del usuario\n",
    )
    .expect("note fixture");
    std::fs::write(
        vault.path().join("opencode.json"),
        "{\"mcp\": {\"servers\": {\"tepochcalli-rag\": {}}}}\n",
    )
    .expect("opencode.json fixture");
    // Payload del harness (H8: `.opencode/` + `AGENTS.md`) y una plantilla:
    // el uninstall borra el primero, jamás los segundos.
    std::fs::create_dir_all(vault.path().join(".opencode").join("agents"))
        .expect("opencode payload fixture");
    std::fs::write(
        vault
            .path()
            .join(".opencode")
            .join("agents")
            .join("itzamna.md"),
        "# agente\n",
    )
    .expect("agent fixture");
    std::fs::write(vault.path().join("AGENTS.md"), "# AGENTS del usuario\n")
        .expect("AGENTS fixture");
    // Manifest del runtime: también es irreemplazable (versión canónica, D-007).
    std::fs::write(
        vault.path().join(".tepochcalli").join("pyproject.toml"),
        "version = \"0.1.0\"\n",
    )
    .expect("pyproject fixture");
    std::fs::create_dir_all(vault.path().join("10-templates")).expect("templates fixture");
    std::fs::write(
        vault.path().join("10-templates").join("mia.md"),
        "# plantilla\n",
    )
    .expect("template fixture");
    std::fs::create_dir_all(vault.path().join(".obsidian")).expect("obsidian fixture");
    std::fs::write(vault.path().join(".obsidian").join("app.json"), "{}\n")
        .expect("obsidian fixture");
    vault
}

fn refresh_ok(scanned: u64, indexed: u64, skipped: u64) -> Result<CommandOutput, WizardError> {
    Ok(CommandOutput {
        status: 0,
        stdout: format!(
            "{{\"scanned\":{scanned},\"indexed\":{indexed},\
              \"skipped\":{skipped},\"elapsed_ms\":9}}"
        ),
        stderr: String::new(),
    })
}

/// Cuerpos de panel (en orden), como el antiguo `TapUi::bodies` local.
fn panel_bodies(ui: &TapUi) -> String {
    ui.events()
        .iter()
        .filter_map(|event| match event {
            UiEvent::Panel { body, .. } => Some(body.clone()),
            _ => None,
        })
        .collect::<Vec<_>>()
        .join("\n")
}

/// Instantánea ordenada `(ruta relativa, bytes)` de todo el árbol: la
/// prueba de alcance del `uninstall` y del gate `--confirm`.
fn tree_snapshot(root: &Path) -> Vec<(String, Vec<u8>)> {
    fn walk(dir: &Path, root: &Path, out: &mut Vec<(String, Vec<u8>)>) {
        let mut names: Vec<PathBuf> = std::fs::read_dir(dir)
            .expect("read fixture tree")
            .map(|entry| entry.expect("dir entry").path())
            .collect();
        names.sort();
        for path in names {
            if path.is_dir() {
                walk(&path, root, out);
            } else {
                let rel = path
                    .strip_prefix(root)
                    .expect("rel path")
                    .to_string_lossy()
                    .into_owned();
                out.push((rel, std::fs::read(&path).expect("read file")));
            }
        }
    }
    let mut out = Vec::new();
    walk(root, root, &mut out);
    out
}

fn no_stray_meta_temps(vault: &Path) {
    assert!(
        !vault
            .join(".tepochcalli")
            .join("db")
            .join("index-meta.json.tmp")
            .exists(),
        "ningún temporal puede fugarse tras el rename atómico"
    );
}

#[test]
fn reindex_rebuilds_index_and_rewrites_meta_atomically() {
    let vault = installed_vault();
    let ui = TapUi::new(vec![], vec![]);
    // Mismo modelo + dims en el sidecar: el gate se omite (un spawn extra
    // devolvería `Internal` y reventaría el test).
    let proc = RecordingProc::scripted([refresh_ok(2, 2, 0)]);

    let report = run_reindex(&proc, &ui, vault.path()).expect("reindex debe triunfar");

    assert_eq!(report.model.as_str(), OLD_MODEL);
    assert_eq!(report.dims, Some(384));
    assert_eq!(report.indexed, 2);
    assert!(!report.mismatch, "sin drift no hay mismatch que explicar");

    let calls = proc.calls();
    assert_eq!(calls.len(), 1, "un solo refresh, got: {calls:?}");
    let call = &calls[0];
    assert!(
        call.program.ends_with("python"),
        "vía el intérprete del venv, got: {}",
        call.program
    );
    assert_eq!(call.args, ["-m", "tepochcalli_flow", "refresh"]);
    assert_eq!(call.cwd, vault.path().to_path_buf());
    for key in ["HF_HOME", "SENTENCE_TRANSFORMERS_HOME"] {
        assert!(
            call.env
                .iter()
                .any(|(k, v)| k == key && v.contains(".tepochcalli")),
            "{key} debe sandboxear la caché bajo el vault, got: {:?}",
            call.env
        );
    }

    let meta = std::fs::read_to_string(
        vault
            .path()
            .join(".tepochcalli")
            .join("db")
            .join("index-meta.json"),
    )
    .expect("sidecar reescrito");
    assert!(
        meta.contains(OLD_MODEL) && meta.contains("384"),
        "got:\n{meta}"
    );
    no_stray_meta_temps(vault.path());
    // El índice vivo y los ficheros del usuario sobreviven al rebuild.
    assert_eq!(
        std::fs::read(
            vault
                .path()
                .join(".tepochcalli")
                .join("db")
                .join("chunks.lance")
        )
        .expect("índice vivo"),
        b"live-index-bytes"
    );
    assert!(vault
        .path()
        .join("00-resources")
        .join("ejemplo.md")
        .is_file());
}

#[test]
fn reindex_explains_model_mismatch_then_rebuilds() {
    // Drift manual (spec-embeddings: `model` editado en config sin reindexar).
    let vault = installed_vault_with(NEW_MODEL, OLD_MODEL);
    let ui = TapUi::new(vec![], vec![]);
    // Modelo distinto al del sidecar: gate (mide las dims nuevas) + refresh.
    let proc = RecordingProc::scripted([gate_ok(NEW_MODEL, 1024, 999), refresh_ok(2, 2, 0)]);

    let report = run_reindex(&proc, &ui, vault.path()).expect("el drift se cura reindexando");

    assert!(report.mismatch, "el drift debe marcarse en el reporte");
    assert_eq!(report.model.as_str(), NEW_MODEL);
    assert_eq!(report.dims, Some(1024));

    let bodies = panel_bodies(&ui);
    assert!(
        bodies.contains("E_MODEL_MISMATCH"),
        "el drift se explica con su código, got:\n{bodies}"
    );
    assert!(
        bodies.contains(OLD_MODEL) && bodies.contains(NEW_MODEL),
        "nombra ambos modelos, got:\n{bodies}"
    );
    let calls = proc.calls();
    assert_eq!(calls.len(), 2, "gate + refresh, got: {calls:?}");
    assert_eq!(
        calls[0].args,
        vec![
            "-m",
            "tepochcalli_flow",
            "embed-check",
            "--model",
            NEW_MODEL
        ]
    );
    assert_eq!(calls[1].args, ["-m", "tepochcalli_flow", "refresh"]);

    let meta = std::fs::read_to_string(
        vault
            .path()
            .join(".tepochcalli")
            .join("db")
            .join("index-meta.json"),
    )
    .expect("sidecar tras el rebuild");
    assert!(
        meta.contains(NEW_MODEL) && meta.contains("1024"),
        "got:\n{meta}"
    );
    no_stray_meta_temps(vault.path());
}

#[test]
fn reindex_degraded_vault_fails_without_spawning() {
    let vault = installed_vault();
    std::fs::write(
        vault
            .path()
            .join(".tepochcalli")
            .join("config")
            .join("tepochcalli.toml"),
        "[embedding]\nprovider = \"none\"\n",
    )
    .expect("degraded config fixture");
    let ui = TapUi::new(vec![], vec![]);
    // Guion vacío: cualquier spawn revienta el test.
    let proc = FakeProc::scripted([]);

    let err = run_reindex(&proc, &ui, vault.path())
        .expect_err("sin embedder no hay nada que reconstruir");
    assert_eq!(err, WizardError::PhaseFailed);
    assert_eq!(err.exit_code(), 42);
    let bodies = panel_bodies(&ui);
    assert!(
        bodies.contains("config embedder"),
        "debe decir cómo salir del degraded, got:\n{bodies}"
    );
}

#[test]
fn reindex_without_config_fails_without_creating_anything() {
    let vault = tmp();
    std::fs::create_dir_all(vault.path().join("notes")).expect("notes fixture");
    let ui = TapUi::new(vec![], vec![]);
    let proc = FakeProc::scripted([]);

    let err = run_reindex(&proc, &ui, vault.path())
        .expect_err("sin config no hay instalación que reindexar");
    assert_eq!(err, WizardError::PhaseFailed);
    assert!(
        !vault.path().join(".tepochcalli").exists(),
        "un reindex fallido no crea runtime"
    );
}

#[test]
fn reindex_failed_refresh_keeps_old_meta_byte_identical() {
    let vault = installed_vault();
    let before_meta = std::fs::read(
        vault
            .path()
            .join(".tepochcalli")
            .join("db")
            .join("index-meta.json"),
    )
    .expect("meta fixture");
    let ui = TapUi::new(vec![], vec![]);
    let proc = FakeProc::scripted([Ok(CommandOutput {
        status: 1,
        stdout: String::new(),
        stderr: "Traceback (most recent call last): ...".to_string(),
    })]);

    let err =
        run_reindex(&proc, &ui, vault.path()).expect_err("el refresh caído debe fallar el reindex");
    assert_eq!(err, WizardError::PhaseFailed);

    // Cambio de estado cero en el sidecar: el índice viejo sigue descrito.
    assert_eq!(
        std::fs::read(
            vault
                .path()
                .join(".tepochcalli")
                .join("db")
                .join("index-meta.json")
        )
        .expect("meta tras el fallo"),
        before_meta
    );
    no_stray_meta_temps(vault.path());
}

#[test]
fn reindex_gate_refusal_is_model_invalid_without_touching_meta() {
    let vault = installed_vault_with(NEW_MODEL, OLD_MODEL);
    let before_meta = std::fs::read(
        vault
            .path()
            .join(".tepochcalli")
            .join("db")
            .join("index-meta.json"),
    )
    .expect("meta fixture");
    let ui = TapUi::new(vec![], vec![]);
    let proc = FakeProc::scripted([Ok(CommandOutput {
        status: 0,
        stdout: "{\"ok\":false,\"code\":\"E_MODEL_INVALID\"}".to_string(),
        stderr: String::new(),
    })]);

    let err =
        run_reindex(&proc, &ui, vault.path()).expect_err("el portero rechazado falla el reindex");
    assert_eq!(err, WizardError::ModelInvalid);
    assert_eq!(
        std::fs::read(
            vault
                .path()
                .join(".tepochcalli")
                .join("db")
                .join("index-meta.json")
        )
        .expect("meta tras el rechazo"),
        before_meta,
        "el rechazo del gate no toca el sidecar"
    );
}

#[test]
fn reindex_missing_venv_is_internal_without_spawning() {
    let vault = installed_vault();
    std::fs::remove_file(
        vault
            .path()
            .join(".tepochcalli")
            .join("venv")
            .join("bin")
            .join("python"),
    )
    .expect("remove venv fixture");
    let ui = TapUi::new(vec![], vec![]);
    let proc = FakeProc::scripted([]);

    let err =
        run_reindex(&proc, &ui, vault.path()).expect_err("sin intérprete no hay refresh posible");
    assert_eq!(err, WizardError::Internal);
}

/// GAP 6: `reindex` con `provider = "litellm"`. El gate test-embed solo mide
/// modelos locales, así que se omite y el sidecar queda con `"dims": null` —
/// misma forma que escribe F7 en la instalación para un modelo sin dims
/// conocidas. `null` es legible por los lectores del repo (`json_u32` ⇒ sin
/// dato; `rag_status` deriva las dims del modelo pineado, no del sidecar).
#[test]
fn reindex_external_provider_writes_null_dims_without_gate() {
    // Drift a propósito: el sidecar describe el índice viejo (modelo local).
    let vault = installed_vault_with(EXTERNAL_MODEL, OLD_MODEL);
    std::fs::write(
        vault
            .path()
            .join(".tepochcalli")
            .join("config")
            .join("tepochcalli.toml"),
        format!("[embedding]\nprovider = \"litellm\"\nmodel = \"{EXTERNAL_MODEL}\"\n"),
    )
    .expect("config externa fixture");
    let ui = TapUi::new(vec![], vec![]);
    // Guion con un solo turno: un gate espurio caería en `Internal`.
    let proc = RecordingProc::scripted([refresh_ok(2, 2, 0)]);

    let report = run_reindex(&proc, &ui, vault.path()).expect("el reindex externo debe triunfar");

    // (a) sin gate: solo el refresh baja al venv.
    let calls = proc.calls();
    assert_eq!(calls.len(), 1, "solo el refresh, got: {calls:?}");
    assert_eq!(calls[0].args, ["-m", "tepochcalli_flow", "refresh"]);
    assert!(
        calls[0].args.iter().all(|arg| arg != "embed-check"),
        "el externo no corre el gate test-embed, got: {calls:?}"
    );

    // (b) forma del sidecar: dims null, modelo externo.
    let meta = std::fs::read_to_string(
        vault
            .path()
            .join(".tepochcalli")
            .join("db")
            .join("index-meta.json"),
    )
    .expect("sidecar reescrito");
    assert_eq!(
        meta,
        format!("{{\"model\":\"{EXTERNAL_MODEL}\",\"dims\":null}}\n"),
        "sin dims medidas el sidecar las declara null"
    );

    // (c) el refresh corre y su reporte se surfacea.
    assert_eq!(report.model, EXTERNAL_MODEL);
    assert_eq!(report.dims, None);
    assert_eq!(
        (
            report.scanned,
            report.indexed,
            report.skipped,
            report.elapsed_ms
        ),
        (2, 2, 0, 9)
    );
    assert!(report.mismatch, "el drift del sidecar se cura y se marca");
    assert!(
        panel_bodies(&ui).contains("indexed 2") && panel_bodies(&ui).contains("dims (sin dato)"),
        "el reporte del refresh se paneliza con sus conteos, got:\n{}",
        panel_bodies(&ui)
    );
    no_stray_meta_temps(vault.path());
}

#[test]
fn uninstall_removes_the_three_scopes_and_keeps_the_notes() {
    let vault = installed_vault();
    let user_files = |root: &Path| -> Vec<(String, Vec<u8>)> {
        tree_snapshot(root)
            .into_iter()
            .filter(|(rel, _)| {
                !rel.starts_with(".tepochcalli/")
                    && !rel.starts_with(".opencode/")
                    && !rel.starts_with(".tepochcalli-backup-")
                    && rel != "opencode.json"
            })
            .collect()
    };
    let before = user_files(vault.path());
    assert!(!before.is_empty(), "el fixture trae ficheros de usuario");

    let ui = TapUi::new(vec![], vec![]);
    let report = run_uninstall(&ui, vault.path()).expect("uninstall debe triunfar");
    assert!(report.removed, "había scopes que quitar");

    // Las 3 rutas del alcance desaparecen.
    for removed in [".tepochcalli", ".opencode", "opencode.json"] {
        assert!(
            !vault.path().join(removed).exists(),
            "{removed} es parte del alcance del uninstall"
        );
    }
    // `AGENTS.md` NO está en el alcance (US-H8) y sobrevive con sus bytes.
    assert_eq!(
        std::fs::read_to_string(vault.path().join("AGENTS.md")).expect("AGENTS intacto"),
        "# AGENTS del usuario\n"
    );
    assert_eq!(
        user_files(vault.path()),
        before,
        "notas, AGENTS.md, 10-templates/ y .obsidian/ intactos"
    );
    // Backup obligatorio: solo lo irreemplazable (decisión del dueño,
    // 2026-11-19), preservando su ruta relativa.
    let backup = report.backup_dir.expect("uninstall crea backup");
    assert!(
        backup.starts_with(vault.path()),
        "el backup vive junto al vault: {}",
        backup.display()
    );
    for kept in [
        ".opencode/agents/itzamna.md",
        "opencode.json",
        ".tepochcalli/config/tepochcalli.toml",
        ".tepochcalli/pyproject.toml",
    ] {
        assert!(
            backup.join(kept).is_file(),
            "{kept} es irreemplazable y debe estar en el backup"
        );
    }
    // venv/db/models/bin son regenerables (re-sync / re-index / re-descarga):
    // NO se copian — es la decisión explícita del dueño.
    for skipped in [
        ".tepochcalli/venv",
        ".tepochcalli/db",
        ".tepochcalli/models",
        ".tepochcalli/bin",
    ] {
        assert!(
            !backup.join(skipped).exists(),
            "{skipped} es regenerable: no viaja al backup"
        );
    }
    // Fuga de secreto cerrada: el directorio se auto-ignora sea cual sea el
    // .gitignore del vault.
    assert_eq!(
        std::fs::read_to_string(backup.join(".gitignore")).expect(".gitignore del backup"),
        "*\n"
    );
    assert_eq!(
        std::fs::read_to_string(backup.join("opencode.json")).expect("backup json"),
        "{\"mcp\": {\"servers\": {\"tepochcalli-rag\": {}}}}\n"
    );
}

#[cfg(unix)]
#[test]
fn uninstall_backup_dir_is_private_to_the_user() {
    use std::os::unix::fs::PermissionsExt as _;
    let vault = installed_vault();
    let ui = TapUi::new(vec![], vec![]);
    let report = run_uninstall(&ui, vault.path()).expect("uninstall");
    let backup = report.backup_dir.expect("backup");

    let mode = std::fs::metadata(&backup)
        .expect("backup metadata")
        .permissions()
        .mode();
    assert_eq!(
        mode & 0o077,
        0,
        "0700: ni grupo ni otros pueden leer el config (posible API key), got {mode:o}"
    );
    let marker = std::fs::metadata(backup.join(".gitignore"))
        .expect("marker metadata")
        .permissions()
        .mode();
    assert_eq!(marker & 0o077, 0, "el marker nace 0600, got {marker:o}");
}

#[test]
fn uninstall_without_scopes_is_noop_ok() {
    let vault = tmp();
    std::fs::write(vault.path().join("nota.md"), "# mía\n").expect("note fixture");
    std::fs::write(vault.path().join("AGENTS.md"), "# AGENTS\n").expect("AGENTS fixture");

    let ui = TapUi::new(vec![], vec![]);
    let report = run_uninstall(&ui, vault.path()).expect("sin scopes es no-op, no error");
    assert!(!report.removed);
    assert!(report.backup_dir.is_none(), "un no-op no crea backup vacío");
    assert_eq!(
        std::fs::read(vault.path().join("nota.md")).expect("note survives"),
        "# mía\n".as_bytes()
    );
    assert_eq!(
        std::fs::read(vault.path().join("AGENTS.md")).expect("AGENTS survives"),
        "# AGENTS\n".as_bytes()
    );
}

#[test]
fn second_uninstall_is_a_noop() {
    let vault = installed_vault();
    let ui = TapUi::new(vec![], vec![]);
    assert!(
        run_uninstall(&ui, vault.path())
            .expect("primer uninstall")
            .removed
    );
    let after_first = tree_snapshot(vault.path());

    let second = run_uninstall(&ui, vault.path()).expect("segundo uninstall");
    assert!(!second.removed, "ya no hay nada que quitar");
    assert!(second.backup_dir.is_none());
    assert_eq!(
        tree_snapshot(vault.path()),
        after_first,
        "el segundo uninstall no crea backup ni toca nada"
    );
}

#[test]
fn reindex_without_confirm_exits_2_and_mutates_nothing() {
    let vault = installed_vault();
    let before = tree_snapshot(vault.path());

    let out = bin()
        .args([
            "reindex",
            "--vault",
            vault.path().to_str().expect("utf8 tmp"),
        ])
        .stdin(Stdio::null())
        .output()
        .expect("spawn binary");
    assert_eq!(
        out.status.code(),
        Some(2),
        "sin --confirm es error de uso, no un stub"
    );
    let err = stderr_text(&out);
    assert!(
        err.contains("--confirm"),
        "explica el flag que falta, got:\n{err}"
    );
    assert!(
        !err.contains("not yet implemented"),
        "el stub de T17 ya no existe, got:\n{err}"
    );
    assert_eq!(
        tree_snapshot(vault.path()),
        before,
        "sin --confirm nada se toca"
    );
}

#[test]
fn reindex_confirm_without_vault_uses_cwd_and_fails_typed() {
    let cwd = tempfile::tempdir().expect("cwd fixture");
    let out = bin()
        .args(["reindex", "--confirm", "--non-interactive"])
        .current_dir(cwd.path())
        .stdin(Stdio::null())
        .output()
        .expect("spawn binary");
    assert_eq!(
        out.status.code(),
        Some(42),
        "el cwd es el vault, sin instalación ⇒ PhaseFailed:\n{}",
        stderr_text(&out)
    );
    assert!(
        stderr_text(&out).contains("Sin instalación"),
        "el panel debe explicar que el cwd no está instalado:\n{}",
        stderr_text(&out)
    );
    assert!(
        !stderr_text(&out).contains("not yet implemented"),
        "el stub de T17 ya no existe"
    );
}

#[test]
fn uninstall_vault_forms_remove_runtime_and_keep_user_files() {
    for form in ["--vault", "--vault="] {
        let vault = installed_vault();
        let arg = if form == "--vault" {
            vault.path().to_str().expect("utf8 tmp").to_string()
        } else {
            format!("--vault={}", vault.path().to_str().expect("utf8 tmp"))
        };
        let args = if form == "--vault" {
            vec![
                "uninstall".to_string(),
                "--vault".to_string(),
                arg,
                "--confirm".to_string(),
                "--non-interactive".to_string(),
            ]
        } else {
            vec![
                "uninstall".to_string(),
                arg,
                "--confirm".to_string(),
                "--non-interactive".to_string(),
            ]
        };
        let out = bin()
            .args(&args)
            .stdin(Stdio::null())
            .output()
            .expect("spawn binary");
        assert_eq!(
            out.status.code(),
            Some(0),
            "args {args:?}: {:?}",
            stderr_text(&out)
        );
        for removed in [".tepochcalli", ".opencode", "opencode.json"] {
            assert!(
                !vault.path().join(removed).exists(),
                "args {args:?}: {removed} desaparece"
            );
        }
        for witness in [
            "00-resources/ejemplo.md",
            "notes/diaria.md",
            "AGENTS.md",
            "10-templates/mia.md",
            ".obsidian/app.json",
        ] {
            assert!(
                vault.path().join(witness).is_file(),
                "args {args:?}: {witness} sobrevive"
            );
        }
        assert!(
            !stderr_text(&out).contains("not yet implemented"),
            "el stub de T17 ya no existe"
        );
    }
}

/// Intérprete falso que satisface el contrato T12 (`refresh`): imprime el
/// `RefreshReport` y sale 0, sin Python real ni red.
#[cfg(unix)]
fn write_fake_flow_python(vault: &Path) {
    use std::os::unix::fs::PermissionsExt as _;
    let python = vault
        .join(".tepochcalli")
        .join("venv")
        .join("bin")
        .join("python");
    std::fs::write(
        &python,
        "#!/bin/sh\nprintf '{\"scanned\":2,\"indexed\":2,\"skipped\":0,\"elapsed_ms\":9}\\n'\n",
    )
    .expect("fake python fixture");
    std::fs::set_permissions(&python, std::fs::Permissions::from_mode(0o755))
        .expect("fake python executable");
}

/// GAP 12: `--vault X` y `--vault=X` son idénticos para `reindex`; un `--vault`
/// sin valor es error de uso (exit 2) sin efectos.
#[cfg(unix)]
#[test]
fn reindex_accepts_both_vault_forms_and_rejects_valueless_flag() {
    for form in ["--vault", "--vault="] {
        let vault = installed_vault();
        write_fake_flow_python(vault.path());
        let path = vault.path().to_str().expect("utf8 tmp").to_string();
        let args: Vec<String> = if form == "--vault" {
            vec![
                "reindex".to_string(),
                "--confirm".to_string(),
                "--non-interactive".to_string(),
                "--vault".to_string(),
                path,
            ]
        } else {
            vec![
                "reindex".to_string(),
                "--confirm".to_string(),
                "--non-interactive".to_string(),
                format!("--vault={path}"),
            ]
        };
        let out = bin()
            .args(&args)
            .stdin(Stdio::null())
            .output()
            .expect("spawn binary");
        assert_eq!(
            out.status.code(),
            Some(0),
            "args {args:?}: {}",
            stderr_text(&out)
        );
        // El flag se honra de verdad: el refresh solo corre si el intérprete
        // vive bajo ESE vault (ignorado el flag, la resolución sería abortada).
        assert!(
            stdout_text(&out).contains("indexed 2"),
            "args {args:?}: {}",
            stdout_text(&out)
        );
    }

    // `--vault` sin valor: error de uso explicado, cero efectos.
    let vault = installed_vault();
    let before = tree_snapshot(vault.path());
    let out = bin()
        .args(["reindex", "--confirm", "--non-interactive", "--vault"])
        .stdin(Stdio::null())
        .output()
        .expect("spawn binary");
    assert_eq!(
        out.status.code(),
        Some(2),
        "un --vault sin valor es error de uso:\n{}",
        stderr_text(&out)
    );
    let err = stderr_text(&out);
    assert!(
        err.contains("--vault") && err.contains("needs a value"),
        "explica el flag sin valor, got:\n{err}"
    );
    assert!(
        stdout_text(&out).is_empty(),
        "un error de uso no imprime nada en stdout"
    );
    assert_eq!(
        tree_snapshot(vault.path()),
        before,
        "un error de uso no toca el vault"
    );
}

/// Mismo contrato para `uninstall`: `--vault` sin valor es exit 2 (las dos
/// formas con valor ya están fijadas en el test anterior).
#[test]
fn uninstall_rejects_valueless_vault_flag() {
    let vault = installed_vault();
    let before = tree_snapshot(vault.path());
    let out = bin()
        .args(["uninstall", "--confirm", "--non-interactive", "--vault"])
        .stdin(Stdio::null())
        .output()
        .expect("spawn binary");
    assert_eq!(
        out.status.code(),
        Some(2),
        "un --vault sin valor es error de uso:\n{}",
        stderr_text(&out)
    );
    let err = stderr_text(&out);
    assert!(
        err.contains("--vault") && err.contains("needs a value"),
        "explica el flag sin valor, got:\n{err}"
    );
    assert!(
        stdout_text(&out).is_empty(),
        "un error de uso no imprime nada en stdout"
    );
    assert_eq!(
        tree_snapshot(vault.path()),
        before,
        "un error de uso no toca el vault"
    );
}

#[test]
fn reindex_and_uninstall_help_document_their_flags() {
    let out = bin()
        .args(["reindex", "--help"])
        .output()
        .expect("spawn binary");
    assert_eq!(out.status.code(), Some(0));
    let text = stdout_text(&out);
    for flag in ["--confirm", "--vault", "--non-interactive"] {
        assert!(
            text.contains(flag),
            "reindex --help debe documentar `{flag}`:\n{text}"
        );
    }
    let out = bin()
        .args(["uninstall", "--help"])
        .output()
        .expect("spawn binary");
    assert_eq!(out.status.code(), Some(0));
    let text = stdout_text(&out);
    for flag in ["--confirm", "--vault", "--non-interactive"] {
        assert!(
            text.contains(flag),
            "uninstall --help debe documentar `{flag}`:\n{text}"
        );
    }
    for args in [vec!["reindex", "--bogus"], vec!["uninstall", "--bogus"]] {
        let out = bin().args(&args).output().expect("spawn binary");
        assert_eq!(
            out.status.code(),
            Some(2),
            "args {args:?} deben seguir siendo error de uso"
        );
    }
}
