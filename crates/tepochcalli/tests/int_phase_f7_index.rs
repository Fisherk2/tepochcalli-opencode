//! F7 initial index (T12): `run_phase7` shells out to the flow CLI.
//!
//! RED-first: every behavior here failed before
//! `application::phase7::run_phase7` existed. Real `tempfile` vaults
//! (D26: no FS port); fakes only (`FakeProc` plus a local `RecordingProc`
//! that pins the exact argv + cwd + env — the same seam `phases_f4f5.rs`
//! uses for the `uv` invocations). No model is ever downloaded: the gate
//! fixtures (`gate_ok`-style JSON) stand in for the flow, exactly like the
//! T11 `FakeProc` stands in for `embed-check` before the CLI existed.

#[allow(dead_code)]
mod common;

use std::cell::RefCell;
use std::collections::VecDeque;
use std::path::{Path, PathBuf};

use common::FakeProc;
use tepochcalli::application::phase7::{run_phase7, Phase7Report};
use tepochcalli::application::Phase6Report;
use tepochcalli::domain::WizardError;
use tepochcalli::ports::{CommandOutput, CommandRunner};

fn tmp() -> tempfile::TempDir {
    tempfile::tempdir().expect("tempdir for T12 fixtures")
}

/// Vault with the two F3 placeholders (D22): the refresh under test is
/// supposed to cover exactly these.
fn vault_with_placeholders() -> tempfile::TempDir {
    let vault = tmp();
    let dir = vault.path().join("00-Resources");
    std::fs::create_dir_all(&dir).expect("00-Resources fixture");
    std::fs::write(dir.join("ejemplo.md"), "# Ejemplo\n").expect("md placeholder fixture");
    std::fs::write(dir.join("ejemplo.pdf"), b"%PDF-1.4 placeholder\n").expect("pdf placeholder");
    vault
}

/// Venv interpreter fixture: F7 refuses to spawn anything without it.
fn venv_python(vault: &Path) -> PathBuf {
    let python = vault
        .join(".tepochcalli")
        .join("venv")
        .join("bin")
        .join("python");
    std::fs::create_dir_all(python.parent().expect("venv bin parent")).expect("venv fixture dir");
    std::fs::write(&python, b"fake-python").expect("venv python fixture");
    python
}

fn path1_report() -> Phase6Report {
    Phase6Report {
        provider: "local".to_string(),
        model: Some("paraphrase-multilingual-MiniLM-L12-v2".to_string()),
        dims: Some(384),
        rss_peak_bytes: Some(650_000_000),
    }
}

fn path5_report() -> Phase6Report {
    Phase6Report {
        provider: "none".to_string(),
        model: None,
        dims: None,
        rss_peak_bytes: None,
    }
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

/// `CommandRunner` fake that records program + argv + cwd + env: pins the
/// T12 contract (`venv python -m tepochcalli_flow refresh`, cwd = vault,
/// model cache sandboxed under the vault).
type RecordedCall = (String, Vec<String>, PathBuf, Vec<(String, String)>);

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

fn index_meta(vault: &Path) -> PathBuf {
    vault
        .join(".tepochcalli")
        .join("db")
        .join("index-meta.json")
}

#[test]
fn f7_post_path1_indexes_both_placeholders_and_persists_metadata() {
    let vault = vault_with_placeholders();
    let python = venv_python(vault.path());
    let proc = RecordingProc::scripted([refresh_ok(2, 2, 0)]);

    let report: Phase7Report =
        run_phase7(&proc, vault.path(), &path1_report()).expect("F7 must succeed post-path-1");

    // Observable contract (skill: elapsed_ms + chunks indexed in the output).
    assert_eq!(report.scanned, 2, "both placeholders must be scanned");
    assert_eq!(report.indexed, 2);
    assert_eq!(report.skipped, 0);
    assert_eq!(
        report.model.as_deref(),
        Some("paraphrase-multilingual-MiniLM-L12-v2")
    );
    assert_eq!(report.dims, Some(384));

    // Exact subprocess shape: venv interpreter, flow CLI, cwd = vault.
    let calls = proc.calls();
    assert_eq!(calls.len(), 1, "exactly one refresh call, got: {calls:?}");
    let (program, args, cwd, env) = &calls[0];
    assert_eq!(*program, python.to_str().expect("utf8 tmp"));
    assert_eq!(args, &["-m", "tepochcalli_flow", "refresh"]);
    assert_eq!(cwd, &vault.path().to_path_buf());
    for key in ["HF_HOME", "SENTENCE_TRANSFORMERS_HOME"] {
        assert!(
            env.iter()
                .any(|(k, v)| k == key && v.contains(".tepochcalli")),
            "{key} must sandbox the model cache under the vault, got: {env:?}"
        );
    }

    // Model + dims land in the index metadata (T17 reads them back).
    let meta = std::fs::read_to_string(index_meta(vault.path())).expect("index metadata written");
    assert!(
        meta.contains("paraphrase-multilingual-MiniLM-L12-v2"),
        "got:\n{meta}"
    );
    assert!(meta.contains("384"), "got:\n{meta}");

    // The placeholders survive the index pass untouched.
    assert!(vault
        .path()
        .join("00-Resources")
        .join("ejemplo.md")
        .is_file());
    assert!(vault
        .path()
        .join("00-Resources")
        .join("ejemplo.pdf")
        .is_file());
}

#[test]
fn f7_second_run_reports_zero_indexed_without_dupes() {
    let vault = vault_with_placeholders();
    venv_python(vault.path());
    let proc = FakeProc::scripted([refresh_ok(2, 2, 0), refresh_ok(2, 0, 2)]);

    let first: Phase7Report =
        run_phase7(&proc, vault.path(), &path1_report()).expect("first F7 must succeed");
    assert_eq!(first.indexed, 2);
    let meta_first = std::fs::read(index_meta(vault.path())).expect("metadata after first run");

    let second: Phase7Report =
        run_phase7(&proc, vault.path(), &path1_report()).expect("second F7 must succeed");
    assert_eq!(
        second.indexed, 0,
        "nothing changed ⇒ indexed: 0 (idempotence)"
    );
    assert_eq!(second.scanned, 2);

    // Zero dupes: the metadata sidecar is rewritten identically, never
    // appended to, and no stray temp file leaks from the atomic write.
    let meta_second = std::fs::read(index_meta(vault.path())).expect("metadata after second run");
    assert_eq!(meta_first, meta_second, "metadata must be byte-identical");
    assert!(
        !vault
            .path()
            .join(".tepochcalli")
            .join("db")
            .join("index-meta.json.tmp")
            .exists(),
        "no temp file may leak after the atomic rename"
    );
}

#[test]
fn f7_path5_skips_everything_without_spawning() {
    let vault = vault_with_placeholders();
    // Empty script: any gate call returns `Internal` and fails the test, so
    // `Ok` here proves path 5 never spawns a process.
    let proc = RecordingProc::scripted([]);

    let report: Phase7Report =
        run_phase7(&proc, vault.path(), &path5_report()).expect("path 5 must skip F7 cleanly");

    assert_eq!(report.indexed, 0);
    assert_eq!(report.model, None);
    assert_eq!(report.dims, None);
    assert!(proc.calls().is_empty(), "path 5 must not spawn any process");
    assert!(
        !vault.path().join(".tepochcalli").join("db").exists(),
        "skipped F7 must not create any index dir"
    );
}

#[test]
fn f7_missing_venv_python_is_typed_error_without_index() {
    let vault = vault_with_placeholders();
    // No venv fixture on purpose: F5 never ran on this vault.
    let proc = FakeProc::scripted([refresh_ok(2, 2, 0)]);

    let err = run_phase7(&proc, vault.path(), &path1_report())
        .expect_err("missing interpreter must fail F7");
    assert_eq!(err, WizardError::Internal);
    assert!(
        !vault.path().join(".tepochcalli").join("db").exists(),
        "failed F7 must not leave an index dir behind"
    );
}

#[test]
fn f7_gate_style_refusal_maps_to_model_invalid() {
    // Parity with the T11 `embed-check` fixture: `ok:false` + the portero
    // code surfaces as the same typed error here, never as an index report.
    let vault = vault_with_placeholders();
    venv_python(vault.path());
    let proc = FakeProc::scripted([Ok(CommandOutput {
        status: 0,
        stdout: "{\"ok\":false,\"code\":\"E_MODEL_INVALID\"}".to_string(),
        stderr: String::new(),
    })]);

    let err = run_phase7(&proc, vault.path(), &path1_report()).expect_err("ok:false must fail F7");
    assert_eq!(err, WizardError::ModelInvalid);
    assert!(
        !index_meta(vault.path()).exists(),
        "a refused refresh must not write metadata"
    );
}

#[test]
fn f7_crashed_or_garbled_refresh_is_phase_failed() {
    let vault = vault_with_placeholders();
    venv_python(vault.path());

    // Non-zero status: the CLI died mid-index.
    let crashed = FakeProc::scripted([Ok(CommandOutput {
        status: 1,
        stdout: String::new(),
        stderr: "Traceback (most recent call last): ...".to_string(),
    })]);
    assert_eq!(
        run_phase7(&crashed, vault.path(), &path1_report()).expect_err("crashed refresh must fail"),
        WizardError::PhaseFailed
    );

    // Exit 0 with unparseable stdout: never trust it as an index report.
    let garbled = FakeProc::scripted([Ok(CommandOutput {
        status: 0,
        stdout: "not json at all".to_string(),
        stderr: String::new(),
    })]);
    assert_eq!(
        run_phase7(&garbled, vault.path(), &path1_report()).expect_err("garbled refresh must fail"),
        WizardError::PhaseFailed
    );

    assert!(
        !index_meta(vault.path()).exists(),
        "a failed refresh must not write metadata"
    );
}

#[test]
fn f7_external_provider_persists_model_with_null_dims() {
    // Path 4 (`litellm`) has no gate-measured dims: F7 still indexes via the
    // flow CLI and records the model with `dims: null` for the T17 mismatch
    // guard to interpret.
    let vault = vault_with_placeholders();
    venv_python(vault.path());
    let proc = FakeProc::scripted([refresh_ok(2, 2, 0)]);
    let path4 = Phase6Report {
        provider: "litellm".to_string(),
        model: Some("openai/text-embedding-3-small".to_string()),
        dims: None,
        rss_peak_bytes: None,
    };

    let report: Phase7Report =
        run_phase7(&proc, vault.path(), &path4).expect("path 4 must index through F7");
    assert_eq!(report.indexed, 2);
    assert_eq!(report.dims, None);

    let meta = std::fs::read_to_string(index_meta(vault.path())).expect("index metadata written");
    assert!(
        meta.contains("openai/text-embedding-3-small"),
        "got:\n{meta}"
    );
    assert!(
        meta.contains("null"),
        "dims must be explicit null, got:\n{meta}"
    );
}
