//! T17: `reindex --confirm` + `uninstall`.
//!
//! RED-first: todo aquí fallaba antes de que existieran
//! `application::maintenance::{run_reindex, run_uninstall}` y su cableado en
//! `main.rs`. Vaults `tempfile` reales (D26: sin puerto FS); solo fakes
//! (`TapUi` local que graba paneles, `RecordingProc` que fija argv + cwd +
//! env). Ningún modelo se descarga: los fixtures `gate_ok`/`refresh_ok`
//! replican los contratos T11/T12. El gate `--confirm` y los flags
//! `--vault`/`--non-interactive` se prueban contra el binario real.

#[allow(dead_code)]
mod common;

use std::cell::RefCell;
use std::collections::VecDeque;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

use common::FakeProc;
use tepochcalli::application::maintenance::{run_reindex, run_uninstall};
use tepochcalli::domain::WizardError;
use tepochcalli::ports::{CommandOutput, CommandRunner, Ui};

const OLD_MODEL: &str = "paraphrase-multilingual-MiniLM-L12-v2";
const NEW_MODEL: &str = "BAAI/bge-m3";

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
    let rt = vault.path().join(".tepochcalli");
    for dir in ["config", "db", "models", "bin", "venv/bin"] {
        std::fs::create_dir_all(rt.join(dir)).expect("runtime dir fixture");
    }
    std::fs::write(
        rt.join("config").join("tepochcalli.toml"),
        format!("[embedding]\nprovider = \"local\"\nmodel = \"{config_model}\"\n"),
    )
    .expect("config fixture");
    std::fs::write(
        rt.join("db").join("index-meta.json"),
        format!("{{\"model\":\"{meta_model}\",\"dims\":384}}\n"),
    )
    .expect("index-meta fixture");
    std::fs::write(rt.join("db").join("chunks.lance"), b"live-index-bytes")
        .expect("live index fixture");
    std::fs::write(rt.join("venv").join("bin").join("python"), b"fake-python")
        .expect("venv python fixture");
    // Ficheros del usuario: fuera de `.tepochcalli/`, intocables.
    std::fs::create_dir_all(vault.path().join("00-Resources")).expect("resources fixture");
    std::fs::write(
        vault.path().join("00-Resources").join("ejemplo.md"),
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
    std::fs::create_dir_all(vault.path().join(".obsidian")).expect("obsidian fixture");
    std::fs::write(vault.path().join(".obsidian").join("app.json"), "{}\n")
        .expect("obsidian fixture");
    vault
}

fn gate_ok(model: &str, dims: u32) -> Result<CommandOutput, WizardError> {
    Ok(CommandOutput {
        status: 0,
        stdout: format!(
            "{{\"ok\":true,\"model\":\"{model}\",\"dims\":{dims},\"rss_peak_bytes\":999}}"
        ),
        stderr: String::new(),
    })
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

/// `Ui` fake: sin respuestas (todo `select`/`input` es `UserAborted`) +
/// captura ordenada de paneles (aquí vive la prueba del `E_MODEL_MISMATCH`
/// explicado, nunca silencioso).
struct TapUi {
    panels: RefCell<Vec<(String, String)>>,
}

impl TapUi {
    fn new() -> Self {
        Self {
            panels: RefCell::new(Vec::new()),
        }
    }

    fn bodies(&self) -> String {
        self.panels
            .borrow()
            .iter()
            .map(|(_, body)| body.clone())
            .collect::<Vec<_>>()
            .join("\n")
    }
}

impl Ui for TapUi {
    fn select(
        &self,
        _prompt: &str,
        _options: &[&str],
        _default_index: usize,
    ) -> Result<usize, WizardError> {
        Err(WizardError::UserAborted)
    }

    fn input(&self, _prompt: &str, _default: Option<&str>) -> Result<String, WizardError> {
        Err(WizardError::UserAborted)
    }

    fn confirm(&self, _prompt: &str, _default: bool) -> Result<bool, WizardError> {
        Err(WizardError::UserAborted)
    }

    fn panel(&self, title: &str, body: &str) {
        self.panels
            .borrow_mut()
            .push((title.to_string(), body.to_string()));
    }
}

type RecordedCall = (String, Vec<String>, PathBuf, Vec<(String, String)>);

/// `CommandRunner` fake que fija programa + argv + cwd + env (el contrato
/// T12: intérprete del venv, `tepochcalli_flow refresh`, cwd = vault, caché
/// bajo el vault). Guion vacío ⇒ `Internal`, luego `Ok` prueba cero spawns.
struct RecordingProc {
    calls: RefCell<Vec<RecordedCall>>,
    script: RefCell<VecDeque<Result<CommandOutput, WizardError>>>,
}

impl RecordingProc {
    fn scripted(script: impl IntoIterator<Item = Result<CommandOutput, WizardError>>) -> Self {
        Self {
            calls: RefCell::new(Vec::new()),
            script: RefCell::new(script.into_iter().collect()),
        }
    }

    fn calls(&self) -> Vec<RecordedCall> {
        self.calls.borrow().clone()
    }
}

impl CommandRunner for RecordingProc {
    fn run(
        &self,
        program: &str,
        args: &[&str],
        cwd: &Path,
        env: &[(&str, &str)],
    ) -> Result<CommandOutput, WizardError> {
        self.calls.borrow_mut().push((
            program.to_string(),
            args.iter().map(ToString::to_string).collect(),
            cwd.to_path_buf(),
            env.iter()
                .map(|(k, v)| (k.to_string(), v.to_string()))
                .collect(),
        ));
        self.script
            .borrow_mut()
            .pop_front()
            .unwrap_or(Err(WizardError::Internal))
    }
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

fn bin() -> Command {
    Command::new(env!("CARGO_BIN_EXE_tepochcalli"))
}

fn stderr_text(output: &std::process::Output) -> String {
    String::from_utf8_lossy(&output.stderr).into_owned()
}

fn stdout_text(output: &std::process::Output) -> String {
    String::from_utf8_lossy(&output.stdout).into_owned()
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
    let ui = TapUi::new();
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
    let (program, args, cwd, env) = &calls[0];
    assert!(
        program.ends_with("python"),
        "vía el intérprete del venv, got: {program}"
    );
    assert_eq!(args, &["-m", "tepochcalli_flow", "refresh"]);
    assert_eq!(cwd, &vault.path().to_path_buf());
    for key in ["HF_HOME", "SENTENCE_TRANSFORMERS_HOME"] {
        assert!(
            env.iter()
                .any(|(k, v)| k == key && v.contains(".tepochcalli")),
            "{key} debe sandboxear la caché bajo el vault, got: {env:?}"
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
        .join("00-Resources")
        .join("ejemplo.md")
        .is_file());
}

#[test]
fn reindex_explains_model_mismatch_then_rebuilds() {
    // Drift manual (spec-embeddings: `model` editado en config sin reindexar).
    let vault = installed_vault_with(NEW_MODEL, OLD_MODEL);
    let ui = TapUi::new();
    // Modelo distinto al del sidecar: gate (mide las dims nuevas) + refresh.
    let proc = RecordingProc::scripted([gate_ok(NEW_MODEL, 1024), refresh_ok(2, 2, 0)]);

    let report = run_reindex(&proc, &ui, vault.path()).expect("el drift se cura reindexando");

    assert!(report.mismatch, "el drift debe marcarse en el reporte");
    assert_eq!(report.model.as_str(), NEW_MODEL);
    assert_eq!(report.dims, Some(1024));

    let bodies = ui.bodies();
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
        calls[0].1,
        vec![
            "-m",
            "tepochcalli_flow",
            "embed-check",
            "--model",
            NEW_MODEL
        ]
    );
    assert_eq!(calls[1].1, vec!["-m", "tepochcalli_flow", "refresh"]);

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
    let ui = TapUi::new();
    // Guion vacío: cualquier spawn revienta el test.
    let proc = FakeProc::scripted([]);

    let err = run_reindex(&proc, &ui, vault.path())
        .expect_err("sin embedder no hay nada que reconstruir");
    assert_eq!(err, WizardError::PhaseFailed);
    assert_eq!(err.exit_code(), 42);
    let bodies = ui.bodies();
    assert!(
        bodies.contains("config embedder"),
        "debe decir cómo salir del degraded, got:\n{bodies}"
    );
}

#[test]
fn reindex_without_config_fails_without_creating_anything() {
    let vault = tmp();
    std::fs::create_dir_all(vault.path().join("notes")).expect("notes fixture");
    let ui = TapUi::new();
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
    let ui = TapUi::new();
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
    let ui = TapUi::new();
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
    let ui = TapUi::new();
    let proc = FakeProc::scripted([]);

    let err =
        run_reindex(&proc, &ui, vault.path()).expect_err("sin intérprete no hay refresh posible");
    assert_eq!(err, WizardError::Internal);
}

#[test]
fn uninstall_removes_only_the_runtime() {
    let vault = installed_vault();
    let before: Vec<(String, Vec<u8>)> = tree_snapshot(vault.path())
        .into_iter()
        .filter(|(rel, _)| !rel.starts_with(".tepochcalli/"))
        .collect();
    assert!(!before.is_empty(), "el fixture trae ficheros de usuario");

    let report = run_uninstall(vault.path()).expect("uninstall debe triunfar");
    assert!(report.removed, "había runtime que quitar");

    assert!(
        !vault.path().join(".tepochcalli").exists(),
        "el runtime desaparece entero"
    );
    let after = tree_snapshot(vault.path());
    assert_eq!(
        after, before,
        "notas, payload, opencode.json y 00-Resources intactos"
    );
    // Cinturón y tirantes: los testigos individuales.
    for witness in [
        "00-Resources/ejemplo.md",
        "notes/diaria.md",
        "opencode.json",
        ".obsidian/app.json",
    ] {
        assert!(
            vault.path().join(witness).is_file(),
            "{witness} debe sobrevivir al uninstall"
        );
    }
}

#[test]
fn uninstall_without_runtime_is_noop_ok() {
    let vault = tmp();
    std::fs::write(vault.path().join("nota.md"), "# mía\n").expect("note fixture");

    let report = run_uninstall(vault.path()).expect("sin runtime es no-op, no error");
    assert!(!report.removed);
    assert_eq!(
        std::fs::read(vault.path().join("nota.md")).expect("note survives"),
        "# mía\n".as_bytes()
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
fn reindex_confirm_without_vault_in_non_interactive_fails_typed() {
    let out = bin()
        .args(["reindex", "--confirm", "--non-interactive"])
        .stdin(Stdio::null())
        .output()
        .expect("spawn binary");
    assert!(
        out.status.code().unwrap_or(0) != 0,
        "sin --vault no hay respuesta que adivinar"
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
                "--non-interactive".to_string(),
            ]
        } else {
            vec![
                "uninstall".to_string(),
                arg,
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
        assert!(
            !vault.path().join(".tepochcalli").exists(),
            "args {args:?}: el runtime desaparece"
        );
        for witness in [
            "00-Resources/ejemplo.md",
            "notes/diaria.md",
            "opencode.json",
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
        .args(["uninstall", "--non-interactive", "--vault"])
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
    for flag in ["--vault", "--non-interactive"] {
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
