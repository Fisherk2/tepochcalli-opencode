//! F8 `mcp.servers` merge + `.bak` + portable command + `rag_status` e2e (T13).
//!
//! RED-first: every behavior here failed before
//! `application::phase8::run_phase8` existed. Real `tempfile` vaults
//! (D26: no FS port); fakes only (`RecordingProc`, which pins the exact
//! program + argv + cwd + env — the same seam `phases_f7.rs` uses for the
//! flow CLI). No model is ever downloaded: scripted `rag_status` payloads
//! (spec literals) stand in for the venv, exactly like the T12 `FakeProc`
//! stands in for `refresh` before the flow CLI existed.
//!
//! The last test is a REAL loopback (not a fake): it symlinks the repo dev
//! venv into a `tempfile` vault and runs the unmodified `run_phase8`
//! through `StdCommandRunner`, first bare (healthy `ok`, `rows: 0`) and
//! then with `provider = "none"` (`degraded` + `E_NO_EMBEDDER`). Unix-only
//! and skipped without the repo venv — loudly, naming `just python-sync`:
//! a full `uv sync` per cargo run would be the T14/T18 matrix job, not a
//! unit gate. The probe↔`server.py` seam is guarded statically instead by
//! `f8_probe_seams_exist_in_payload_server_py`, which runs everywhere (no
//! Python) and fails if a seam the probe imports is renamed. The
//! `ok`-with-rows>0 state (indexed vault) is covered by the Python e2e
//! contract tests (`tests/e2e/test_mcp_contract.py`), which own the wire
//! shape.

mod common;

use std::cell::RefCell;
use std::collections::VecDeque;
use std::path::{Path, PathBuf};

use common::RecordingProc;

use tepochcalli::application::phase8::{
    compensate_phase8, mcp_python_command, mcp_python_command_for, run_phase8, Phase8Report,
    RagHealth, MANAGED_RAG, OPENCODE_BAK, OPENCODE_JSON, RAG_STATUS_PROBE, STALE_MARKITDOWN,
};
use tepochcalli::domain::WizardError;
use tepochcalli::ports::{CommandOutput, CommandRunner};

fn tmp() -> tempfile::TempDir {
    tempfile::tempdir().expect("tempdir for T13 fixtures")
}

/// Minimal user `opencode.json`: two unrelated servers, no managed keys.
fn user_config() -> String {
    "{\"mcp\":{\"servers\":{\
     \"excel\":{\"type\":\"local\",\"command\":[\"uvx\",\"excel-mcp-server\",\"stdio\"],\"disabled\":true},\
     \"jupyter\":{\"type\":\"local\",\"command\":[\"uvx\",\"mcp-jupyter-notebook\"],\"disabled\":true}}}\
     ,\"model\":\"opencode/big-pickle\"}\n"
        .to_string()
}

fn write_config(vault: &Path, body: &str) -> PathBuf {
    let target = vault.join(OPENCODE_JSON);
    std::fs::write(&target, body).expect("fixture opencode.json");
    target
}

/// FakeUi for the I11a consent gate: scripted `select` answers (1 = confirm,
/// 0 = decline) plus a count of the warning panels shown.
struct ConsentUi {
    select_answers: RefCell<VecDeque<usize>>,
    panels: RefCell<Vec<(String, String)>>,
}

/// Errors that should never happen in these scripts surface as UserAborted
/// (the adapters' prompt-failure invariant).
impl ConsentUi {
    fn confirming() -> Self {
        Self::new([1])
    }

    fn declining() -> Self {
        Self::new([0])
    }

    fn new(answers: impl IntoIterator<Item = usize>) -> Self {
        Self {
            select_answers: RefCell::new(answers.into_iter().collect()),
            panels: RefCell::new(Vec::new()),
        }
    }

    fn panels(&self) -> Vec<(String, String)> {
        self.panels.borrow().clone()
    }
}

impl tepochcalli::ports::Ui for ConsentUi {
    fn select(
        &self,
        _prompt: &str,
        _options: &[&str],
        _default_index: usize,
    ) -> Result<usize, WizardError> {
        self.select_answers
            .borrow_mut()
            .pop_front()
            .ok_or(WizardError::UserAborted)
    }

    fn input(&self, _prompt: &str, _default: Option<&str>) -> Result<String, WizardError> {
        Err(WizardError::UserAborted)
    }

    fn input_secret(&self, _prompt: &str) -> Result<String, WizardError> {
        Err(WizardError::UserAborted)
    }

    fn panel(&self, title: &str, body: &str) {
        self.panels
            .borrow_mut()
            .push((title.to_string(), body.to_string()));
    }

    fn menu(
        &self,
        _view: &tepochcalli::ports::MenuView<'_>,
    ) -> Result<tepochcalli::domain::MenuAction, WizardError> {
        Err(WizardError::UserAborted)
    }
}

/// Venv interpreter fixture: F8 refuses to verify without it (same rule as
/// F7 — no F5 on the vault means no spawn, typed error instead).
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

/// Spec-literal healthy payload (spec-mcp-server §rag_status, salida 1).
fn rag_ok() -> Result<CommandOutput, WizardError> {
    Ok(CommandOutput {
        status: 0,
        stdout: "{\"embedder\":{\"mode\":\"local\",\
         \"model\":\"paraphrase-multilingual-MiniLM-L12-v2\",\"dims\":384,\"provider\":null},\
         \"index\":{\"rows\":0,\"model_matches_config\":true,\"last_refresh\":null,\"db_size_bytes\":0},\
         \"config\":{\"path\":\".tepochcalli/config/tepochcalli.toml\",\"valid\":true},\
         \"health\":{\"state\":\"ok\",\"reason\":null,\"fix_hint\":null}}"
            .to_string(),
        stderr: String::new(),
    })
}

/// Spec-literal degraded payload (salida 5, `provider = "none"`).
fn rag_degraded() -> Result<CommandOutput, WizardError> {
    Ok(CommandOutput {
        status: 0,
        stdout: "{\"embedder\":{\"mode\":\"none\",\"model\":null,\"dims\":null,\"provider\":null},\
         \"index\":{\"rows\":0,\"model_matches_config\":true,\"last_refresh\":null,\"db_size_bytes\":0},\
         \"config\":{\"path\":\".tepochcalli/config/tepochcalli.toml\",\"valid\":true},\
         \"health\":{\"state\":\"degraded\",\"reason\":\"E_NO_EMBEDDER\",\
         \"fix_hint\":\"Ejecuta `tepochcalli config embedder` y luego `index_refresh()`\"}}"
            .to_string(),
        stderr: String::new(),
    })
}

fn occurrences(haystack: &str, needle: &str) -> usize {
    haystack.matches(needle).count()
}

/// The managed entry exactly as F8 writes it, with a caller-supplied
/// `environment` (so a test can pre-seed user keys).
fn managed_entry(environment: serde_json::Value) -> String {
    serde_json::json!({"mcp": {"servers": {MANAGED_RAG: {
        "type": "local",
        "command": [mcp_python_command(), "-m", "tepochcalli_mcp"],
        "cwd": ".",
        "environment": environment,
        "disabled": false
    }}}})
    .to_string()
}

#[test]
fn f8_backup_before_write_and_compensation_restores_byte_identical() {
    let vault = tmp();
    let original = user_config();
    write_config(vault.path(), &original);
    venv_python(vault.path());
    let proc = RecordingProc::scripted([rag_ok()]);

    let report: Phase8Report =
        run_phase8(&proc, vault.path(), None).expect("F8 must succeed on a user config");
    assert!(report.changed, "new entry ⇒ changed");

    // I11b: success means the merge is verified, so the `.bak`'s protection
    // window is closed and the cleanup removes it.
    assert!(
        !vault.path().join(OPENCODE_BAK).exists(),
        "successful run cleans its own .bak"
    );

    // Compensation semantics stay pinned separately (a run that dies before
    // success): a `.bak` present restores the user file byte-identical and
    // leaves no residue.
    std::fs::write(vault.path().join(OPENCODE_BAK), &original).expect("fixture .bak");
    std::fs::write(vault.path().join(OPENCODE_JSON), b"{\"trashed\":true}")
        .expect("trash the merged file");
    compensate_phase8(vault.path());
    let restored =
        std::fs::read(vault.path().join(OPENCODE_JSON)).expect("config must exist again");
    assert_eq!(
        restored,
        original.as_bytes(),
        "compensation restores byte-identical"
    );
    assert!(
        !vault.path().join(OPENCODE_BAK).exists(),
        "compensated run leaves no backup residue"
    );
}

#[test]
fn f8_preserves_unrelated_servers_and_manages_only_rag() {
    let vault = tmp();
    let original = user_config();
    write_config(vault.path(), &original);
    venv_python(vault.path());
    let proc = RecordingProc::scripted([rag_ok()]);

    run_phase8(&proc, vault.path(), None).expect("F8 must succeed");

    let merged = std::fs::read_to_string(vault.path().join(OPENCODE_JSON)).expect("merged config");
    let doc: serde_json::Value = serde_json::from_str(&merged).expect("merged must parse");
    // Unrelated servers survive with values and (disabled) flags intact.
    assert_eq!(doc["mcp"]["servers"]["excel"]["disabled"], true);
    assert_eq!(
        doc["mcp"]["servers"]["excel"]["command"][0],
        serde_json::Value::String("uvx".to_string())
    );
    assert_eq!(doc["mcp"]["servers"]["jupyter"]["disabled"], true);
    assert_eq!(doc["model"], "opencode/big-pickle");
    // Only the managed entry was added: the rest is structurally identical.
    let mut current: serde_json::Value = serde_json::from_str(&merged).expect("re-parse");
    let mut before: serde_json::Value = serde_json::from_str(&original).expect("fixture parses");
    for key in [MANAGED_RAG, STALE_MARKITDOWN] {
        current["mcp"]["servers"]
            .as_object_mut()
            .expect("servers")
            .remove(key);
        before["mcp"]["servers"]
            .as_object_mut()
            .expect("servers")
            .remove(key);
    }
    assert_eq!(current, before, "conservative merge: the rest is untouched");
    // The managed entry has the exact payload shape (D17: `python -m`, never a console script).
    let entry = &doc["mcp"]["servers"][MANAGED_RAG];
    assert_eq!(entry["type"], "local");
    assert_eq!(entry["command"][1], "-m");
    assert_eq!(entry["command"][2], "tepochcalli_mcp");
    assert_eq!(entry["cwd"], ".");
    assert_eq!(entry["environment"]["TEPOCHCALLI_ROOT"], ".");
    assert_eq!(entry["disabled"], false);
}

#[test]
fn f8_rewrites_only_when_different_second_run_is_noop() {
    let vault = tmp();
    // Stale form: console-script command instead of `python -m` (D17).
    write_config(
        vault.path(),
        "{\"mcp\":{\"servers\":{\
         \"tepochcalli-rag\":{\"type\":\"local\",\
         \"command\":[\".tepochcalli/venv/bin/tepochcalli-mcp\"],\
         \"cwd\":\".\",\"environment\":{\"TEPOCHCALLI_ROOT\":\".\"},\"disabled\":false}}}}",
    );
    venv_python(vault.path());
    let proc = RecordingProc::scripted([rag_ok(), rag_ok()]);

    let first = run_phase8(&proc, vault.path(), None).expect("first F8 must succeed");
    assert!(first.changed, "stale entry must be rewritten");
    let after_first =
        std::fs::read(vault.path().join(OPENCODE_JSON)).expect("merged config exists");

    let second = run_phase8(&proc, vault.path(), None).expect("second F8 must succeed");
    assert!(!second.changed, "identical entry ⇒ no rewrite");
    let after_second =
        std::fs::read(vault.path().join(OPENCODE_JSON)).expect("config still exists");
    assert_eq!(
        after_first, after_second,
        "no-op rerun ⇒ byte-identical file"
    );
    assert_eq!(
        occurrences(&String::from_utf8_lossy(&after_second), MANAGED_RAG),
        1,
        "zero duplicate entries"
    );
}

#[test]
fn f8_keeps_user_environment_keys() {
    // User-added env vars (INDEXER_DIR, TEPOCHCALLI_TOP_K…) are data, not
    // drift: re-running the installer must not delete them.
    let vault = tmp();
    let original = managed_entry(serde_json::json!({
        "TEPOCHCALLI_ROOT": ".",
        "INDEXER_DIR": "00-resources,03-Citations",
        "TEPOCHCALLI_TOP_K": "9"
    }));
    write_config(vault.path(), &original);
    venv_python(vault.path());
    let proc = RecordingProc::scripted([rag_ok()]);

    let report = run_phase8(&proc, vault.path(), None).expect("F8 must succeed");
    assert!(!report.changed, "a satisfied entry is not a change");
    let merged =
        std::fs::read_to_string(vault.path().join(OPENCODE_JSON)).expect("config still exists");
    assert_eq!(merged, original, "changed == false ⇒ file not rewritten");

    let doc: serde_json::Value = serde_json::from_str(&merged).expect("merged parses");
    let env = doc["mcp"]["servers"][MANAGED_RAG]["environment"]
        .as_object()
        .expect("environment object");
    assert_eq!(env.len(), 3, "same three keys survive, got: {env:?}");
    assert_eq!(env["TEPOCHCALLI_ROOT"], ".");
    assert_eq!(env["INDEXER_DIR"], "00-resources,03-Citations");
    assert_eq!(env["TEPOCHCALLI_TOP_K"], "9");
}

#[test]
fn f8_environment_preservation_is_idempotent() {
    let vault = tmp();
    let original = managed_entry(serde_json::json!({
        "INDEXER_DIR": "00-resources,03-Citations",
        "TEPOCHCALLI_ROOT": "."
    }));
    write_config(vault.path(), &original);
    venv_python(vault.path());
    let proc = RecordingProc::scripted([rag_ok(), rag_ok()]);

    let first = run_phase8(&proc, vault.path(), None).expect("first pass must succeed");
    assert!(!first.changed, "already-canonical entry ⇒ no rewrite");
    let second = run_phase8(&proc, vault.path(), None).expect("second pass must succeed");
    assert!(!second.changed, "strict idempotency across reruns");
    assert_eq!(
        std::fs::read_to_string(vault.path().join(OPENCODE_JSON)).expect("config exists"),
        original,
        "neither pass rewrote the file"
    );
}

#[test]
fn f8_non_object_environment_fails_and_writes_nothing() {
    // Never guess: a malformed `environment` is a typed failure, and
    // compensation leaves the user file byte-identical.
    let vault = tmp();
    let original = managed_entry(serde_json::json!([]));
    write_config(vault.path(), &original);
    venv_python(vault.path());
    let proc = RecordingProc::scripted([rag_ok()]);

    assert_eq!(
        run_phase8(&proc, vault.path(), None).expect_err("non-object environment must fail"),
        WizardError::PhaseFailed
    );
    assert_eq!(
        std::fs::read(vault.path().join(OPENCODE_JSON)).expect("config exists"),
        original.as_bytes(),
        "nothing written, byte-identical"
    );
    assert!(
        proc.calls().is_empty(),
        "no probe spawn on a failed merge, got: {:?}",
        proc.calls()
    );
}

#[test]
fn f8_entry_without_environment_gains_only_the_contract_root() {
    let vault = tmp();
    let original = serde_json::json!({"mcp": {"servers": {MANAGED_RAG: {
        "type": "local",
        "command": [mcp_python_command(), "-m", "tepochcalli_mcp"],
        "cwd": ".",
        "disabled": false
    }}}})
    .to_string();
    write_config(vault.path(), &original);
    venv_python(vault.path());
    let proc = RecordingProc::scripted([rag_ok()]);

    let report = run_phase8(&proc, vault.path(), None).expect("F8 must succeed");
    assert!(report.changed, "adding the environment is a change");

    let merged = std::fs::read_to_string(vault.path().join(OPENCODE_JSON)).expect("merged config");
    let doc: serde_json::Value = serde_json::from_str(&merged).expect("merged parses");
    assert_eq!(
        doc["mcp"]["servers"][MANAGED_RAG]["environment"],
        serde_json::json!({ "TEPOCHCALLI_ROOT": "." }),
        "no invented keys"
    );
}

#[test]
fn f8_removes_stale_markitdown_and_never_registers_it() {
    let vault = tmp();
    write_config(
        vault.path(),
        "{\"mcp\":{\"servers\":{\
         \"excel\":{\"type\":\"local\",\"command\":[\"uvx\",\"x\"],\"disabled\":true},\
         \"markitdown\":{\"type\":\"local\",\"command\":[\"uvx\",\"markitdown-mcp\"],\"disabled\":false}}}}",
    );
    venv_python(vault.path());
    let proc = RecordingProc::scripted([rag_ok()]);

    let report = run_phase8(&proc, vault.path(), None).expect("F8 must succeed");
    assert!(
        report.changed,
        "removing the stale entry counts as a change"
    );

    let merged = std::fs::read_to_string(vault.path().join(OPENCODE_JSON)).expect("merged config");
    assert_eq!(
        occurrences(&merged, STALE_MARKITDOWN),
        0,
        "markitdown is gone (D19)"
    );
    assert_eq!(occurrences(&merged, MANAGED_RAG), 1);
    assert!(
        merged.contains("\"excel\""),
        "unrelated servers survive the removal"
    );
}

#[test]
fn f8_venv_command_is_portable_by_os() {
    // D20: POSIX vs Windows venv layout; `cfg!(windows)` picks at compile time.
    assert_eq!(
        mcp_python_command_for(false),
        ".tepochcalli/venv/bin/python"
    );
    assert_eq!(
        mcp_python_command_for(true),
        ".tepochcalli/venv/Scripts/python.exe"
    );
}

#[test]
fn f8_write_is_atomic_and_legible() {
    let vault = tmp();
    write_config(vault.path(), &user_config());
    venv_python(vault.path());
    let proc = RecordingProc::scripted([rag_ok()]);

    run_phase8(&proc, vault.path(), None).expect("F8 must succeed");

    assert!(
        !vault.path().join("opencode.json.tmp").exists(),
        "no temp file may leak from the atomic rename"
    );
    let merged = std::fs::read_to_string(vault.path().join(OPENCODE_JSON)).expect("merged config");
    assert!(
        merged.starts_with("{\n  \"mcp\""),
        "legible 2-space form like the payload, got:\n{merged}"
    );
    assert!(merged.ends_with("}\n"), "POSIX trailing newline");
}

#[test]
fn f8_probe_runs_venv_python_with_registered_cwd_and_env() {
    let vault = tmp();
    write_config(vault.path(), &user_config());
    venv_python(vault.path());
    let proc = RecordingProc::scripted([rag_ok()]);

    let report = run_phase8(&proc, vault.path(), None).expect("F8 must succeed");
    assert_eq!(report.health, RagHealth::Ok);

    // Exactly one verification call, shaped like the registered entry.
    let calls = proc.calls();
    assert_eq!(calls.len(), 1, "one rag_status probe, got: {calls:?}");
    let call = &calls[0];
    assert!(
        call.program.ends_with(".tepochcalli/venv/bin/python"),
        "vault venv interpreter, got: {}",
        call.program
    );
    assert_eq!(
        &call.args,
        &vec!["-c".to_string(), RAG_STATUS_PROBE.to_string()]
    );
    assert_eq!(call.cwd, vault.path().to_path_buf(), "cwd = vault");
    assert!(
        call.env
            .iter()
            .any(|(k, v)| k == "TEPOCHCALLI_ROOT" && v == "."),
        "contract env mirrors opencode.json, got: {:?}",
        call.env
    );
}

#[test]
fn f8_degraded_state_passes_with_fix_hint() {
    let vault = tmp();
    write_config(vault.path(), &user_config());
    venv_python(vault.path());
    let proc = RecordingProc::scripted([rag_degraded()]);

    let report = run_phase8(&proc, vault.path(), None).expect("degraded must still succeed");
    assert_eq!(report.health, RagHealth::Degraded);
    assert!(report.changed, "merge still applies in degraded installs");
}

#[test]
fn f8_rag_status_violations_fail_safe_with_compensation() {
    // Each payload violates the spec shape ⇒ `PhaseFailed`, and the merge
    // is rolled back so the user file is byte-identical to the original.
    let cases: &[(&str, &str)] = &[
        ("garbage is not JSON", "not json at all"),
        ("missing health block", "{\"embedder\":{\"mode\":\"local\"},\"index\":{},\"config\":{}}"),
        ("unknown state", "{\"embedder\":{\"mode\":\"local\"},\"index\":{},\"config\":{},\"health\":{\"state\":\"maybe\",\"reason\":null,\"fix_hint\":null}}"),
        ("degraded without reason", "{\"embedder\":{\"mode\":\"none\"},\"index\":{},\"config\":{},\"health\":{\"state\":\"degraded\",\"reason\":null,\"fix_hint\":null}}"),
        ("degraded without fix_hint", "{\"embedder\":{\"mode\":\"none\"},\"index\":{},\"config\":{},\"health\":{\"state\":\"degraded\",\"reason\":\"E_NO_EMBEDDER\",\"fix_hint\":null}}"),
        ("ok with stale reason", "{\"embedder\":{\"mode\":\"local\"},\"index\":{},\"config\":{},\"health\":{\"state\":\"ok\",\"reason\":\"E_NO_EMBEDDER\",\"fix_hint\":null}}"),
        ("guard error envelope", "{\"error\":{\"code\":\"INTERNAL\",\"message\":\"boom\",\"details\":null}}"),
        ("unknown embedder mode", "{\"embedder\":{\"mode\":\"remote\"},\"index\":{},\"config\":{},\"health\":{\"state\":\"ok\",\"reason\":null,\"fix_hint\":null}}"),
    ];
    for (name, stdout) in cases {
        let vault = tmp();
        let original = user_config();
        write_config(vault.path(), &original);
        venv_python(vault.path());
        let proc = RecordingProc::scripted([Ok(CommandOutput {
            status: 0,
            stdout: (*stdout).to_string(),
            stderr: String::new(),
        })]);

        let err = run_phase8(&proc, vault.path(), None).unwrap_err();
        assert_eq!(err, WizardError::PhaseFailed, "case: {name}");
        let current =
            std::fs::read(vault.path().join(OPENCODE_JSON)).expect("config must still exist");
        assert_eq!(
            current,
            original.as_bytes(),
            "case {name}: compensation restores byte-identical"
        );
    }

    // Non-zero status (the venv python died) fails the same way.
    let vault = tmp();
    let original = user_config();
    write_config(vault.path(), &original);
    venv_python(vault.path());
    let crashed = RecordingProc::scripted([Ok(CommandOutput {
        status: 1,
        stdout: String::new(),
        stderr: "Traceback (most recent call last): ...".to_string(),
    })]);
    assert_eq!(
        run_phase8(&crashed, vault.path(), None).expect_err("crashed probe must fail"),
        WizardError::PhaseFailed
    );
    assert_eq!(
        std::fs::read(vault.path().join(OPENCODE_JSON)).expect("config exists"),
        original.as_bytes()
    );
}

#[test]
fn f8_missing_opencode_json_is_created_and_compensated() {
    // F3 always lays the base, but a missing file must still install
    // (recovery, not a crash); compensation removes exactly what F8 made.
    let vault = tmp();
    assert!(!vault.path().join(OPENCODE_JSON).exists());
    venv_python(vault.path());
    let proc = RecordingProc::scripted([rag_ok(), rag_degraded()]);

    let report = run_phase8(&proc, vault.path(), None).expect("missing file must be created");
    assert!(report.changed);
    let merged = std::fs::read_to_string(vault.path().join(OPENCODE_JSON)).expect("created");
    assert_eq!(occurrences(&merged, MANAGED_RAG), 1);
    assert!(
        !vault.path().join(OPENCODE_BAK).exists(),
        "nothing pre-existed ⇒ no backup to restore from"
    );

    compensate_phase8(vault.path());
    assert!(
        !vault.path().join(OPENCODE_JSON).exists(),
        "compensation removes the file F8 created"
    );
}

/// REAL loopback (unix + repo dev venv only): the unmodified `run_phase8`
/// spawns the vault venv python and validates both spec states for real —
/// bare vault ⇒ `ok` (`rows: 0`), then `provider = "none"` ⇒ `degraded` +
/// `E_NO_EMBEDDER`, with the merge idempotent across the rerun.
#[cfg(unix)]
#[test]
fn f8_real_venv_loopback_ok_then_degraded() {
    use tepochcalli::adapters::StdCommandRunner;

    let repo_venv = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../obsidian-workspace/.tepochcalli/venv");
    let repo_python = repo_venv.join("bin/python");
    if !repo_python.is_file() {
        // Documented constraint: without the repo dev venv (T14/T18 matrix
        // job does full `uv sync` runs) there is nothing real to loop back
        // through — the scripted tests above own the shape. Never silent:
        // this is the only Rust test that executes the probe, so a skip
        // must say why and how to enable it (like `e2e_payload`).
        println!(
            "skip: repo dev venv missing at {} (the real Python↔Rust probe loopback needs it; run `just python-sync` to enable)",
            repo_python.display()
        );
        return;
    }
    let vault = tmp();
    let runtime = vault.path().join(".tepochcalli");
    std::fs::create_dir_all(&runtime).expect("runtime dir");
    std::os::unix::fs::symlink(&repo_venv, runtime.join("venv")).expect("venv symlink");
    write_config(vault.path(), &user_config());
    let proc = StdCommandRunner;

    // Warm-up (medido en corrida 2026-11-09/10): el repo vive en fuseblk (NTFS-3g) y la
    // importación en frío del venv bloquea al hijo en I/O FUSE
    // (`fuse_chan_send` / `folio_wait_bit_common`, CPU 7s en 40s de vida)
    // hasta >120 s: el PROBE_TIMEOUT lo mata y el gate se pone rojo sin que
    // el cableado esté mal. Este test verifica intérprete/cwd/env/JSON, no
    // latencia en frío — se calienta la caché con el mismo hijo, cwd y env
    // del probe real antes de cronometrar nada.
    let models = runtime.join("models").to_string_lossy().into_owned();
    let warm = proc
        .run_with_timeout(
            repo_python.to_str().expect("python path utf8"),
            &["-c", "import tepochcalli_mcp.server"],
            vault.path(),
            &[
                ("HF_HOME", models.as_str()),
                ("SENTENCE_TRANSFORMERS_HOME", models.as_str()),
                ("TEPOCHCALLI_ROOT", "."),
            ],
            std::time::Duration::from_secs(300),
        )
        .expect("warm-up import must complete (>300s en frío ⇒ montaje FUSE roto, no cableado)");
    assert_eq!(warm.status, 0, "warm-up import failed: {}", warm.stderr);

    let first = run_phase8(&proc, vault.path(), None).expect("real ok loopback must succeed");
    assert_eq!(first.health, RagHealth::Ok);
    assert!(first.changed);
    let merged = std::fs::read_to_string(vault.path().join(OPENCODE_JSON)).expect("merged");
    assert_eq!(occurrences(&merged, MANAGED_RAG), 1);

    std::fs::create_dir_all(runtime.join("config")).expect("config dir");
    std::fs::write(
        runtime.join("config/tepochcalli.toml"),
        "[embedding]\nprovider = \"none\"\n",
    )
    .expect("none config");
    let second =
        run_phase8(&proc, vault.path(), None).expect("real degraded loopback must succeed");
    assert_eq!(second.health, RagHealth::Degraded);
    assert!(!second.changed, "merge is idempotent across the rerun");
    let merged_again =
        std::fs::read_to_string(vault.path().join(OPENCODE_JSON)).expect("merged again");
    assert_eq!(occurrences(&merged_again, MANAGED_RAG), 1);
}

/// I11a consent fixtures: a user key whose value looks like a plaintext
/// secret inside the managed entry.
fn secret_config() -> String {
    managed_entry(serde_json::json!({
        "TEPOCHCALLI_EMBED_API_KEY": "sk-proj-this-would-be-a-real-literal-secret"
    }))
}

#[test]
fn f8_secret_environment_decline_fails_clean_and_writes_nothing() {
    let vault = tmp();
    let original = secret_config();
    write_config(vault.path(), &original);
    venv_python(vault.path());
    let proc = RecordingProc::scripted([rag_ok()]);
    let ui = ConsentUi::declining();

    assert_eq!(
        run_phase8(&proc, vault.path(), Some(&ui))
            .expect_err("a declined consent is a typed failure"),
        WizardError::PhaseFailed
    );
    assert_eq!(
        std::fs::read(vault.path().join(OPENCODE_JSON)).expect("config exists"),
        original.as_bytes(),
        "decline ⇒ nothing persisted, byte-identical"
    );
    assert!(
        !vault.path().join(OPENCODE_BAK).exists(),
        "compensation cleaned the backup of the failed run"
    );
    assert!(
        proc.calls().is_empty(),
        "no probe spawn without consent, got: {:?}",
        proc.calls()
    );
    let panels = ui.panels();
    assert!(
        !panels.is_empty(),
        "the risk is explained before the question"
    );
    for (_, body) in panels {
        assert!(
            !body.contains("sk-proj"),
            "values never travel to the panel, only key names: {body}"
        );
        assert!(
            body.contains("TEPOCHCALLI_EMBED_API_KEY"),
            "the panel names the affected keys"
        );
    }
}

#[test]
fn f8_secret_environment_confirm_persists_and_rerun_is_noop() {
    let vault = tmp();
    write_config(vault.path(), &secret_config());
    venv_python(vault.path());
    // Two passes: both confirm (every pass that would WRITE asks again).
    let proc = RecordingProc::scripted([rag_ok(), rag_ok()]);
    let ui = ConsentUi::confirming();

    let first = run_phase8(&proc, vault.path(), Some(&ui)).expect("consent ⇒ F8 succeeds");
    assert!(first.changed, "the confirmed merge is written");
    let after_first =
        std::fs::read(vault.path().join(OPENCODE_JSON)).expect("merged config exists");
    let doc: serde_json::Value =
        serde_json::from_str(&String::from_utf8_lossy(&after_first)).expect("merged parses");
    // The secret stays (D32: user keys are data) and gains only the contract root.
    assert_eq!(
        doc["mcp"]["servers"][MANAGED_RAG]["environment"]["TEPOCHCALLI_EMBED_API_KEY"],
        "sk-proj-this-would-be-a-real-literal-secret"
    );
    assert_eq!(
        doc["mcp"]["servers"][MANAGED_RAG]["environment"]["TEPOCHCALLI_ROOT"],
        "."
    );

    // Identical rerun: nothing to persist ⇒ no gate, byte-identical file.
    let second = run_phase8(&proc, vault.path(), Some(&ui)).expect("second F8");
    assert!(!second.changed, "idempotent rerun never re-asks");
    assert_eq!(second.health, RagHealth::Ok, "sanity: probe still verified");
    let after_second =
        std::fs::read(vault.path().join(OPENCODE_JSON)).expect("config still exists");
    assert_eq!(after_first, after_second, "no-op rerun ⇒ byte-identical");
    assert_eq!(proc.calls().len(), 2, "one probe per pass");
}

#[test]
fn f8_secret_environment_without_tui_fails_instead_of_persisting() {
    // Headless has no confirmation surface: fail typed, never persist the
    // secret silently (same rule as the mirror-http door in main).
    let vault = tmp();
    let original = secret_config();
    write_config(vault.path(), &original);
    venv_python(vault.path());
    let proc = RecordingProc::scripted([rag_ok()]);

    assert_eq!(
        run_phase8(&proc, vault.path(), None).expect_err("no TUI ⇒ no persistence of secrets"),
        WizardError::PhaseFailed
    );
    assert_eq!(
        std::fs::read(vault.path().join(OPENCODE_JSON)).expect("config exists"),
        original.as_bytes(),
        "headless never writes the secret entry"
    );
    assert!(
        proc.calls().is_empty(),
        "no probe spawn, got: {:?}",
        proc.calls()
    );
}

/// Static cross-language guard: the loopback above is the only Rust test that EXECUTES `RAG_STATUS_PROBE`, and it skips without the repo venv —
/// a seam renamed in `server.py` used to reach production as a `TypeError`
/// (`99d8b38` and earlier). This check runs on every `cargo test` (no
/// Python, no venv): every seam name the probe imports from
/// `tepochcalli_mcp.server` must exist literally in the payload's
/// `server.py`, so a rename fails here first.
#[test]
fn f8_probe_seams_exist_in_payload_server_py() {
    let server_py = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../obsidian-workspace/.tepochcalli/mcp/tepochcalli_mcp/server.py");
    let source = std::fs::read_to_string(&server_py).unwrap_or_else(|error| {
        panic!(
            "payload server.py must be readable at {}: {error}",
            server_py.display()
        )
    });

    // Seam list parsed straight out of the probe constant (no regex dep):
    // `from tepochcalli_mcp.server import A, B, …; from …` — one import
    // statement, so the first `;` after the marker closes the list.
    let import_marker = "from tepochcalli_mcp.server import ";
    let import_list = RAG_STATUS_PROBE
        .split_once(import_marker)
        .unwrap_or_else(|| panic!("probe must import seams from {import_marker}"))
        .1
        .split_once(';')
        .expect("probe import list ends at `;`")
        .0;
    let seams: Vec<&str> = import_list.split(',').map(str::trim).collect();
    assert!(!seams.is_empty(), "probe imports at least one seam");

    let missing: Vec<&str> = seams
        .iter()
        .copied()
        .filter(|seam| !source.contains(&format!("def {seam}")))
        .collect();
    assert!(
        missing.is_empty(),
        "RAG_STATUS_PROBE imports seams absent from {}: {missing:?}",
        server_py.display()
    );
}
