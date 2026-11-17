//! F6b: 5-exit embedder menu + test-embed gate + materialización verificada
//! del snapshot + atomic config (T11, T6/D59).
//!
//! RED-first: every behavior here failed before
//! `application::embedder_menu::run_phase6` existed. Real `tempfile` vaults
//! (D26: no FS port); fakes only (`ScriptedUi`/local `TapUi`, `FakeProc`,
//! `FakeHttp`, `FakeHost`).

// Shared fakes: this target reuses three of them.
#[allow(dead_code)]
mod common;

use std::collections::HashMap;
use std::path::{Path, PathBuf};

use common::{FakeHost, FakeHttp, FakeProc, RecordingProc, TapUi};
use tepochcalli::application::embedder_menu::{Phase6Deps, EMBEDDER_PATHS};
use tepochcalli::domain::{EmbedderChoice, WizardError};
use tepochcalli::ports::{CommandOutput, CommandRunner, Ui};

/// Los dos presets embebidos y su SHA pineada (espejo de `presets.toml`).
const MINILM: &str = "paraphrase-multilingual-MiniLM-L12-v2";
const MINILM_SHA: &str = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42";
const BGE: &str = "BAAI/bge-m3";
const BGE_SHA: &str = "5617a9f61b028005a4858fdac845db406aefb181";
/// `sha` que la API de HF devuelve en los fixtures de id libre.
const HF_SHA: &str = "0000sha-for-the-free-id";

fn tmp() -> tempfile::TempDir {
    tempfile::tempdir().expect("tempdir for T11 fixtures")
}

/// Materializes the vault venv python (is_file guard of the shared flow CLI):
/// without it run_phase6 fails with `Internal` before the scripted gate.
fn create_venv_python(vault: &Path) {
    let python = vault
        .join(".tepochcalli")
        .join("venv")
        .join(if cfg!(windows) {
            "Scripts/python.exe"
        } else {
            "bin/python"
        });
    std::fs::create_dir_all(python.parent().expect("venv bin parent")).expect("venv fixture");
    std::fs::write(python, b"fake-python").expect("venv python fixture");
}

/// Materializa el snapshot que deja el gate real: `<models>/<slug>@<sha>/`
/// (la fórmula de `tepochcalli_flow.config.model_slug` + `embedding_model_path`).
fn materialize(vault: &Path, model: &str, revision: &str) {
    let dir = vault
        .join(".tepochcalli")
        .join("models")
        .join(format!("{}@{revision}", model.replace('/', "__")));
    std::fs::create_dir_all(&dir).expect("snapshot dir fixture");
    std::fs::write(dir.join("config.json"), b"{}").expect("snapshot file fixture");
}

fn host_16gb() -> FakeHost {
    FakeHost::new(Some(16.0), Some(16.0), Some(100.0), None)
}

fn gate_ok(model: &str, dims: u32, rss: u64) -> Result<CommandOutput, WizardError> {
    Ok(CommandOutput {
        status: 0,
        stdout: format!(
            "{{\"ok\":true,\"model\":\"{model}\",\"dims\":{dims},\"rss_peak_bytes\":{rss}}}"
        ),
        stderr: String::new(),
    })
}

fn gate_invalid() -> Result<CommandOutput, WizardError> {
    Ok(CommandOutput {
        status: 0,
        stdout: "{\"ok\":false,\"code\":\"E_MODEL_INVALID\"}".to_string(),
        stderr: String::new(),
    })
}

fn hf_meta(gated: bool, pipeline_tag: &str, tags: &[&str], params_total: u64) -> Vec<u8> {
    let tags_json = tags
        .iter()
        .map(|t| format!("\"{t}\""))
        .collect::<Vec<_>>()
        .join(",");
    format!(
        "{{\"gated\":{gated},\"sha\":\"{HF_SHA}\",\"pipeline_tag\":\"{pipeline_tag}\",\
         \"tags\":[{tags_json}],\
         \"safetensors\":{{\"parameters\":{{\"total\":{params_total}}}}},\
         \"siblings\":[{{\"rfilename\":\"model.safetensors\",\"size\":470000000}}]}}"
    )
    .into_bytes()
}

fn config_path(vault: &Path) -> PathBuf {
    vault
        .join(".tepochcalli")
        .join("config")
        .join("tepochcalli.toml")
}

fn deps<'a>(
    ui: &'a dyn Ui,
    host: &'a FakeHost,
    proc: &'a dyn CommandRunner,
    http: &'a FakeHttp,
) -> Phase6Deps<'a> {
    Phase6Deps {
        ui,
        host,
        proc,
        http,
    }
}

fn empty_http() -> FakeHttp {
    FakeHttp::new(HashMap::new())
}

#[test]
fn menu_offers_five_paths_with_minilm_default_first() {
    // Index contract: 0 = MiniLM preselect, 4 = "configure later" (mirrors
    // `HeadlessUi::for_install`: skip_model -> 4, otherwise -> 0).
    assert_eq!(
        EMBEDDER_PATHS,
        [
            EmbedderChoice::PresetDefault,
            EmbedderChoice::PresetLarge,
            EmbedderChoice::HuggingFaceId,
            EmbedderChoice::ExternalApi,
            EmbedderChoice::ConfigureLater,
        ]
    );
    let ui = TapUi::new(vec![4], vec![]);
    let host = host_16gb();
    let proc = FakeProc::scripted([]);
    let http = empty_http();
    let vault = tmp();
    let report = tepochcalli::application::embedder_menu::run_phase6(
        &deps(&ui, &host, &proc, &http),
        vault.path(),
    )
    .expect("path 5 must succeed without any gate");
    assert_eq!(report.provider, "none");
    let shown = ui.captured();
    let menu = shown
        .iter()
        .find(|line| line.starts_with("SELECT"))
        .expect("the menu must be shown once");
    assert!(
        menu.contains("default=0"),
        "MiniLM row must be preselected, got: {menu}"
    );
    assert_eq!(menu.split(" | ").count(), 5, "exactly 5 exits, got: {menu}");
    assert!(
        menu.to_lowercase().contains("minilm"),
        "first row must be MiniLM, got: {menu}"
    );
}

#[test]
fn path1_ok_writes_local_config_after_gate() {
    let ui = TapUi::new(vec![0], vec![]);
    let host = host_16gb();
    let proc = RecordingProc::scripted([gate_ok(MINILM, 384, 650_000_000)]);
    let http = empty_http();
    let vault = tmp();
    create_venv_python(vault.path());
    materialize(vault.path(), MINILM, MINILM_SHA);
    let report = tepochcalli::application::embedder_menu::run_phase6(
        &deps(&ui, &host, &proc, &http),
        vault.path(),
    )
    .expect("path 1 with a passing gate must succeed");
    assert_eq!(report.provider, "local");
    assert_eq!(report.model.as_deref(), Some(MINILM));
    assert_eq!(report.dims, Some(384));
    assert_eq!(report.rss_peak_bytes, Some(650_000_000));

    // Gate contract (T12 programs against it): venv python, explicit argv,
    // incluida la revisión pineada (el snapshot estable depende de ella).
    let calls = proc.calls();
    assert_eq!(calls.len(), 1, "exactly one gate call, got: {calls:?}");
    let call = &calls[0];
    assert!(
        call.program.ends_with("python") || call.program.ends_with("python.exe"),
        "gate must run the venv interpreter, got: {}",
        call.program
    );
    assert_eq!(
        &call.args,
        &[
            "-m",
            "tepochcalli_flow",
            "embed-check",
            "--model",
            MINILM,
            "--revision",
            MINILM_SHA
        ]
    );
    assert!(
        call.env
            .iter()
            .any(|(k, v)| k == "HF_HOME" && v.contains(".tepochcalli")),
        "gate must sandbox the model cache under the vault, got: {:?}",
        call.env
    );

    // Atomic config: exact expected body, provider local + model + revision.
    let body = std::fs::read_to_string(config_path(vault.path())).expect("config written");
    assert!(body.contains("provider = \"local\""), "got:\n{body}");
    assert!(
        body.contains(&format!("model = \"{MINILM}\"")),
        "got:\n{body}"
    );
    assert!(
        body.contains(&format!("revision = \"{MINILM_SHA}\"")),
        "la config debe pinear la misma revisión que el snapshot, got:\n{body}"
    );
    assert!(
        !vault
            .path()
            .join(".tepochcalli")
            .join("config")
            .join("tepochcalli.toml.tmp")
            .exists(),
        "no temp file may leak after the atomic rename"
    );
    // The measured RSS surfaces with its provenance label.
    assert!(
        ui.captured().iter().any(|line| line.contains("medido")),
        "gate RSS must surface as `medido`: {:?}",
        ui.captured()
    );
}

/// AC T6(c): un gate `ok` sin snapshot materializado NO es éxito — F6 falla y
/// no queda config escrita (ni siquiera la degradada: esa la escribe `main`).
#[test]
fn gate_ok_without_materialized_snapshot_fails_without_config() {
    let ui = TapUi::new(vec![0], vec![]);
    let host = host_16gb();
    let proc = RecordingProc::scripted([gate_ok(MINILM, 384, 650_000_000)]);
    let http = empty_http();
    let vault = tmp();
    create_venv_python(vault.path());
    // El CLI dijo ok pero no dejó `<models>/<slug>@<sha>/`: fallo de fase.
    let err = tepochcalli::application::embedder_menu::run_phase6(
        &deps(&ui, &host, &proc, &http),
        vault.path(),
    )
    .expect_err("un gate sin snapshot no puede cerrar F6");
    assert_eq!(err, WizardError::PhaseFailed);
    assert!(
        !config_path(vault.path()).exists(),
        "sin snapshot no se escribe media config"
    );
    assert!(
        !ui.captured()
            .iter()
            .any(|line| line.starts_with("PANEL Embedding OK")),
        "no se anuncia un modelo que no está en disco: {:?}",
        ui.captured()
    );
}

#[test]
fn path2_ok_writes_large_preset() {
    let ui = TapUi::new(vec![1], vec![]);
    let host = host_16gb();
    let proc = FakeProc::scripted([gate_ok(BGE, 1024, 3_000_000_000)]);
    let http = empty_http();
    let vault = tmp();
    create_venv_python(vault.path());
    materialize(vault.path(), BGE, BGE_SHA);
    let report = tepochcalli::application::embedder_menu::run_phase6(
        &deps(&ui, &host, &proc, &http),
        vault.path(),
    )
    .expect("path 2 with a passing gate must succeed");
    assert_eq!(report.provider, "local");
    assert_eq!(report.model.as_deref(), Some(BGE));
    assert_eq!(report.dims, Some(1024));
    let body = std::fs::read_to_string(config_path(vault.path())).expect("config written");
    assert!(body.contains(&format!("model = \"{BGE}\"")), "got:\n{body}");
    assert!(
        body.contains(&format!("revision = \"{BGE_SHA}\"")),
        "got:\n{body}"
    );
}

#[test]
fn path3_free_id_estimates_then_gates_ok() {
    let id = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2";
    let mut files = HashMap::new();
    files.insert(
        format!("https://huggingface.co/api/models/{id}"),
        hf_meta(
            false,
            "sentence-similarity",
            &["sentence-transformers"],
            117_600_000,
        ),
    );
    let ui = TapUi::new(vec![2], vec![id.to_string()]);
    let host = host_16gb();
    let proc = RecordingProc::scripted([gate_ok(id, 384, 650_000_000)]);
    let http = FakeHttp::new(files);
    let vault = tmp();
    create_venv_python(vault.path());
    materialize(vault.path(), id, HF_SHA);
    let report = tepochcalli::application::embedder_menu::run_phase6(
        &deps(&ui, &host, &proc, &http),
        vault.path(),
    )
    .expect("path 3 with estimate + passing gate must succeed");
    assert_eq!(report.model.as_deref(), Some(id));
    // 117.6M params x 4 B x 1.3 overhead ~= 611 MB, labelled `estimado`.
    assert!(
        ui.captured()
            .iter()
            .any(|line| line.contains("estimado") && line.contains("611")),
        "estimate row must show RAM with `estimado` provenance: {:?}",
        ui.captured()
    );
    // La revisión sale del `sha` de la API: gate y config la comparten.
    let args = &proc.calls()[0].args;
    assert_eq!(
        args,
        &[
            "-m",
            "tepochcalli_flow",
            "embed-check",
            "--model",
            id,
            "--revision",
            HF_SHA
        ]
    );
    let body = std::fs::read_to_string(config_path(vault.path())).expect("config written");
    assert!(body.contains(&format!("model = \"{id}\"")), "got:\n{body}");
    assert!(
        body.contains(&format!("revision = \"{HF_SHA}\"")),
        "got:\n{body}"
    );
}

#[test]
fn path3_non_embedding_returns_to_menu_without_config() {
    // Pre-filter rejection (tags) on the first pass, then path 5: proves the
    // menu loop continues and only the second choice writes config.
    let id = "org/not-an-embedder";
    let mut files = HashMap::new();
    files.insert(
        format!("https://huggingface.co/api/models/{id}"),
        hf_meta(false, "text-generation", &["text-generation"], 1_000_000),
    );
    let ui = TapUi::new(vec![2, 4], vec![id.to_string()]);
    let host = host_16gb();
    let proc = FakeProc::scripted([]);
    let http = FakeHttp::new(files);
    let vault = tmp();
    let report = tepochcalli::application::embedder_menu::run_phase6(
        &deps(&ui, &host, &proc, &http),
        vault.path(),
    )
    .expect("menu must recover after rejecting the non-embedding id");
    assert_eq!(report.provider, "none");
    assert!(
        ui.captured()
            .iter()
            .any(|line| line.contains("E_MODEL_INVALID")),
        "rejection must name the contract code: {:?}",
        ui.captured()
    );
    let body = std::fs::read_to_string(config_path(vault.path())).expect("config written");
    assert!(body.contains("provider = \"none\""), "got:\n{body}");
    assert!(
        !body.contains(id),
        "rejected id must never reach the config"
    );
}

#[test]
fn path3_gate_invalid_returns_to_menu_without_config() {
    // HF metadata unreachable (offline) so the gate decides: ok:false with
    // E_MODEL_INVALID sends the user back to the menu, writing nothing until
    // the second choice (path 5) lands.
    let ui = TapUi::new(vec![2, 4], vec!["org/mystery-model".to_string()]);
    let host = host_16gb();
    let proc = FakeProc::scripted([gate_invalid()]);
    let http = empty_http();
    let vault = tmp();
    create_venv_python(vault.path());
    let report = tepochcalli::application::embedder_menu::run_phase6(
        &deps(&ui, &host, &proc, &http),
        vault.path(),
    )
    .expect("menu must recover after the gate rejects the id");
    assert_eq!(report.provider, "none");
    let body = std::fs::read_to_string(config_path(vault.path())).expect("config written");
    assert!(body.contains("provider = \"none\""), "got:\n{body}");
}

#[test]
fn path3_gated_repo_asks_token_and_passes_it_to_gate_env() {
    let id = "org/gated-model";
    let mut files = HashMap::new();
    files.insert(
        format!("https://huggingface.co/api/models/{id}"),
        hf_meta(
            true,
            "sentence-similarity",
            &["sentence-transformers"],
            50_000_000,
        ),
    );
    let token = "hf-test-token-never-logged";
    let ui = TapUi::new(vec![2], vec![id.to_string(), token.to_string()]);
    let host = host_16gb();
    let proc = RecordingProc::scripted([gate_ok(id, 384, 300_000_000)]);
    let http = FakeHttp::new(files);
    let vault = tmp();
    create_venv_python(vault.path());
    materialize(vault.path(), id, HF_SHA);
    let report = tepochcalli::application::embedder_menu::run_phase6(
        &deps(&ui, &host, &proc, &http),
        vault.path(),
    )
    .expect("gated repo with token must pass the gate");
    assert_eq!(report.model.as_deref(), Some(id));
    let calls = proc.calls();
    assert_eq!(calls.len(), 1);
    assert!(
        calls[0]
            .env
            .iter()
            .any(|(k, v)| k == "HF_TOKEN" && v == token),
        "token must reach the download env, got: {:?}",
        calls[0].env
    );
    assert!(
        ui.captured().iter().any(|line| line.contains("gated")),
        "gated repos must warn before downloading: {:?}",
        ui.captured()
    );
    for line in ui.captured() {
        assert!(
            !line.contains(token),
            "redaction breach — token leaked into UI output: {line}"
        );
    }
}

#[test]
fn path4_key_lands_only_in_gitignored_config() {
    let secret = "sk-test-4f8a2c9e-key-must-never-leak";
    let ui = TapUi::new(
        vec![3],
        vec![
            "openai/text-embedding-3-small".to_string(),
            secret.to_string(),
        ],
    );
    let host = host_16gb();
    // Empty script: any gate call returns `Internal` and fails the test, so
    // `Ok` here proves path 4 never invokes the gate.
    let proc = FakeProc::scripted([]);
    let http = empty_http();
    let vault = tmp();
    let report = tepochcalli::application::embedder_menu::run_phase6(
        &deps(&ui, &host, &proc, &http),
        vault.path(),
    )
    .expect("path 4 must succeed without any gate");
    assert_eq!(report.provider, "litellm");
    let body = std::fs::read_to_string(config_path(vault.path())).expect("config written");
    assert!(body.contains("provider = \"litellm\""), "got:\n{body}");
    assert!(
        body.contains(secret),
        "the key must be persisted, got:\n{body}"
    );
    for line in ui.captured() {
        assert!(
            !line.contains(secret),
            "redaction breach — key leaked into UI output: {line}"
        );
    }
}

#[test]
fn path5_skips_gate_and_writes_none() {
    let ui = TapUi::new(vec![4], vec![]);
    let host = host_16gb();
    // Empty script: any gate call returns `Internal` and fails the test.
    let proc = FakeProc::scripted([]);
    let http = empty_http();
    let vault = tmp();
    let report = tepochcalli::application::embedder_menu::run_phase6(
        &deps(&ui, &host, &proc, &http),
        vault.path(),
    )
    .expect("path 5 must succeed without any gate");
    assert_eq!(report.provider, "none");
    assert_eq!(report.model, None);
    assert_eq!(report.dims, None);
    let body = std::fs::read_to_string(config_path(vault.path())).expect("config written");
    assert!(body.contains("provider = \"none\""), "got:\n{body}");
}

#[test]
fn failed_gate_leaves_preexisting_config_byte_identical() {
    let before = b"[embedding]\nprovider = \"local\"\nmodel = \"keep-me\"\n";
    let vault = tmp();
    let dir = vault.path().join(".tepochcalli").join("config");
    std::fs::create_dir_all(&dir).expect("config dir fixture");
    std::fs::write(dir.join("tepochcalli.toml"), before).expect("preexisting config");
    create_venv_python(vault.path());
    let ui = TapUi::new(vec![0], vec![]);
    let host = host_16gb();
    let proc = FakeProc::scripted([Err(WizardError::PhaseFailed)]);
    let http = empty_http();
    let err = tepochcalli::application::embedder_menu::run_phase6(
        &deps(&ui, &host, &proc, &http),
        vault.path(),
    )
    .expect_err("a failing gate must fail F6");
    assert_eq!(err, WizardError::PhaseFailed);
    let after = std::fs::read(dir.join("tepochcalli.toml")).expect("config still there");
    assert_eq!(
        after, before,
        "interrupted F6 must leave config byte-identical"
    );
    assert!(
        !dir.join("tepochcalli.toml.tmp").exists(),
        "no temp file may leak after a failed write"
    );
}
