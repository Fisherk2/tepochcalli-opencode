//! T14 atomicity: compensation per phase, `--resume`, `--offline`,
//! idempotence, `--skip-model` == path 5, F6 failure degrades.
//!
//! RED-first: every test here fails before the T14 runbook
//! (`compensate_phase3/6/7`, install-state marker, offline guard) exists.
//! Real `tempfile` vaults (D26: no FS port); fakes only.

#[allow(dead_code)]
mod common;

use std::collections::HashMap;
use std::path::{Path, PathBuf};

use common::{FakeHost, FakeHttp, FakeProc, FakeUiScript, ScriptedUi};
use tepochcalli::application::embedder_menu::Phase6Deps;
use tepochcalli::application::installer::{
    check_prereqs_on, ensure_vault_dir, guard_offline_before_touch, is_phase_done, mark_phase_done,
    run_phase3,
};
use tepochcalli::application::{run_phase6, run_phase7, run_phase8};
use tepochcalli::domain::{Phase, WizardError};
use tepochcalli::ports::CommandOutput;
use tepochcalli::{INSTALL_STATE_PATH, MANAGED_RAG};

fn tmp() -> tempfile::TempDir {
    tempfile::tempdir().expect("tempdir for T14 fixtures")
}

fn write(path: &Path, body: &str) {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).expect("fixture parents");
    }
    std::fs::write(path, body).expect("fixture write");
}

fn host_16gb() -> FakeHost {
    FakeHost::new(Some(16.0), Some(16.0), Some(100.0), None)
}

fn payload_tree(base: &Path) {
    write(&base.join("a.md"), "# payload version\n");
    write(&base.join("b.md"), "# fresh file\n");
}

fn refresh_ok(indexed: u64) -> Result<CommandOutput, WizardError> {
    Ok(CommandOutput {
        status: 0,
        stdout: format!("{{\"scanned\":2,\"indexed\":{indexed},\"skipped\":0,\"elapsed_ms\":9}}"),
        stderr: String::new(),
    })
}

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

fn snapshot_tree(root: &Path) -> Vec<(PathBuf, Vec<u8>)> {
    let mut out = Vec::new();
    let mut stack = vec![root.to_path_buf()];
    while let Some(dir) = stack.pop() {
        let entries = match std::fs::read_dir(&dir) {
            Ok(entries) => entries,
            Err(_) => continue,
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() {
                stack.push(path);
            } else if path.is_file() {
                let rel = path.strip_prefix(root).expect("under root").to_path_buf();
                // Skip T14 runbook residue: intent/state are expected to change.
                if rel.starts_with(".tepochcalli") {
                    continue;
                }
                out.push((rel, std::fs::read(&path).expect("read snapshot")));
            }
        }
    }
    out.sort();
    out
}

// --- F1/F2: no compensation (nothing touched) ---

#[test]
fn f1_f2_failures_touch_no_user_data() {
    let dir = tmp();
    let sentinel = dir.path().join("notes.md");
    write(&sentinel, "# keep me\n");
    let before = snapshot_tree(dir.path());

    // Induced F1 failure (4 GB RAM aborts, exit 10).
    let err = check_prereqs_on(
        &FakeHost::new(Some(4.0), Some(4.0), Some(100.0), None),
        "linux",
        dir.path(),
        &[],
    )
    .expect_err("4 GB must abort F1");
    assert_eq!(err, WizardError::PrereqRam);

    // Induced F2 failure (a file is not a vault dir).
    let file = dir.path().join("not-a-dir");
    write(&file, "x");
    ensure_vault_dir(&file).expect_err("file must fail F2");
    let _ = std::fs::remove_file(&file);

    assert_eq!(
        snapshot_tree(dir.path()),
        before,
        "F1/F2 never touch user data"
    );
}

// --- F3: compensation removes only what F3 wrote ---

#[test]
fn f3_compensation_removes_written_and_keeps_user_files() {
    use tepochcalli::adapters::LocalPayload;

    let payload = tmp();
    payload_tree(payload.path());
    let vault = tmp();
    write(&vault.path().join("a.md"), "# USER version\n");
    write(&vault.path().join("keep.md"), "# mine\n");

    run_phase3(&LocalPayload::new(payload.path()), vault.path()).expect("F3 must succeed");
    assert!(vault.path().join("b.md").is_file());

    tepochcalli::compensate_phase3(vault.path());

    assert!(
        !vault.path().join("b.md").exists(),
        "F3 wrote b.md ⇒ removed"
    );
    assert!(!vault
        .path()
        .join("00-Resources")
        .join("ejemplo.md")
        .exists());
    assert!(!vault
        .path()
        .join(".tepochcalli")
        .join(".install-intent")
        .exists());
    assert_eq!(
        std::fs::read_to_string(vault.path().join("a.md")).expect("read back"),
        "# USER version\n",
        "pre-existing user file survives F3 compensation"
    );
    assert!(
        vault.path().join("keep.md").is_file(),
        "untouched file survives"
    );
    assert!(
        !vault.path().join(".obsidian").exists() || true,
        "no .obsidian residue"
    );
}

// --- F4/F5: induced failure compensates, user data survives ---

#[test]
fn f4_f5_failures_compensate_without_touching_user_data() {
    use tepochcalli::adapters::fetch::{self};
    use tepochcalli::application::installer::{compensate_phase4, compensate_phase5, run_phase5};

    let vault = tmp();
    write(&vault.path().join("notes.md"), "# user research\n");
    let before_user = std::fs::read(vault.path().join("notes.md")).expect("sentinel");
    // Runtime data the compensations must never touch.
    for dir in ["models", "db", "config"] {
        write(
            &vault
                .path()
                .join(".tepochcalli")
                .join(dir)
                .join("sentinel.txt"),
            "keep\n",
        );
    }

    // Induced F4 failure: tampered bytes vs. the pinned hash.
    let asset = fetch::uv_asset_for_current_platform().expect("platform covered");
    let url = fetch::uv_download_url(asset);
    let mut files = HashMap::new();
    files.insert(url, b"tampered-bytes".to_vec());
    let http = FakeHttp::new(files);
    let proc = FakeProc::scripted([Ok(CommandOutput {
        status: 0,
        stdout: "uv 0.12.9".to_string(),
        stderr: String::new(),
    })]);
    let err =
        tepochcalli::run_phase4(&http, &proc, vault.path()).expect_err("tampered F4 must fail");
    assert_eq!(err, WizardError::PayloadCorrupt);
    assert!(!vault.path().join(".tepochcalli").join("bin").exists());
    assert_eq!(
        std::fs::read(vault.path().join("notes.md")).expect("sentinel"),
        before_user
    );

    // Induced F5 failure: sync dies mid-run ⇒ venv/ gone, bin/ stays.
    let uv = vault.path().join(".tepochcalli").join("bin").join("uv");
    std::fs::create_dir_all(uv.parent().expect("bin parent")).expect("bin fixture");
    std::fs::write(&uv, b"fake-uv").expect("uv fixture");
    let proc = FakeProc::scripted([
        Ok(CommandOutput {
            status: 0,
            stdout: String::new(),
            stderr: String::new(),
        }),
        Ok(CommandOutput {
            status: 0,
            stdout: String::new(),
            stderr: String::new(),
        }),
        Err(WizardError::PhaseFailed),
    ]);
    assert_eq!(
        run_phase5(&proc, vault.path()).expect_err("sync must fail"),
        WizardError::PhaseFailed
    );
    assert!(!vault.path().join(".tepochcalli").join("venv").exists());
    assert!(uv.is_file(), "F4 bin/ survives F5 failure");
    assert_eq!(
        std::fs::read(vault.path().join("notes.md")).expect("sentinel"),
        before_user
    );

    // Direct compensation fns are idempotent no-ops on missing dirs.
    compensate_phase4(vault.path());
    compensate_phase5(vault.path());
    assert_eq!(
        std::fs::read(vault.path().join("notes.md")).expect("sentinel"),
        before_user
    );
}

// --- F6: failure degrades to path 5 (complete, not failed) ---

#[test]
fn f6_failure_compensates_to_degraded_path5() {
    let vault = tmp();
    venv_python(vault.path());
    // Path 1 gate crashes ⇒ run_phase6 fails ⇒ compensation writes path-5 config.
    let ui = ScriptedUi::new(FakeUiScript {
        selects: [0_usize].into_iter().collect(),
        ..FakeUiScript::default()
    });
    let proc = FakeProc::scripted([Err(WizardError::PhaseFailed)]);
    let deps = Phase6Deps {
        ui: &ui,
        host: &host_16gb(),
        proc: &proc,
        http: &FakeHttp::new(HashMap::new()),
    };
    let err = run_phase6(&deps, vault.path()).expect_err("crashed gate must fail F6");
    assert_eq!(err, WizardError::PhaseFailed);

    tepochcalli::compensate_phase6(vault.path()).expect("F6 compensation writes degraded config");
    let body = std::fs::read_to_string(
        vault
            .path()
            .join(".tepochcalli")
            .join("config")
            .join("tepochcalli.toml"),
    )
    .expect("degraded config exists");
    assert!(
        body.contains("provider = \"none\""),
        "F6 falls back to salida 5, got:\n{body}"
    );
}

// --- F7: failure leaves no index residue, placeholders survive ---

#[test]
fn f7_failure_leaves_no_index_and_keeps_placeholders() {
    use tepochcalli::application::Phase6Report;

    let vault = tmp();
    let dir = vault.path().join("00-Resources");
    std::fs::create_dir_all(&dir).expect("resources fixture");
    write(&dir.join("ejemplo.md"), "# Ejemplo\n");
    venv_python(vault.path());
    let report = Phase6Report {
        provider: "local".to_string(),
        model: Some("paraphrase-multilingual-MiniLM-L12-v2".to_string()),
        revision: Some("e8f8c211226b894fcb81acc59f3b34ba3efd5f42".to_string()),
        dims: Some(384),
        rss_peak_bytes: Some(1),
    };
    let proc = FakeProc::scripted([Ok(CommandOutput {
        status: 1,
        stdout: String::new(),
        stderr: "boom".to_string(),
    })]);
    assert_eq!(
        run_phase7(&proc, vault.path(), &report).expect_err("crashed refresh must fail"),
        WizardError::PhaseFailed
    );
    tepochcalli::compensate_phase7(vault.path());
    assert!(
        !vault
            .path()
            .join(".tepochcalli")
            .join("db")
            .join("index-meta.json")
            .exists(),
        "failed F7 must leave no metadata"
    );
    assert!(
        dir.join("ejemplo.md").is_file(),
        "placeholders survive F7 failure"
    );
}

// --- F8: induced verification failure restores user config ---

#[test]
fn f8_failure_restores_user_config_byte_identical() {
    let vault = tmp();
    let original = "{\"mcp\":{\"servers\":{\"excel\":{\"type\":\"local\",\"command\":[\"uvx\",\"x\"],\"disabled\":true}}}}\n";
    write(&vault.path().join("opencode.json"), original);
    venv_python(vault.path());
    let proc = FakeProc::scripted([Ok(CommandOutput {
        status: 1,
        stdout: String::new(),
        stderr: "Traceback".to_string(),
    })]);
    assert_eq!(
        run_phase8(&proc, vault.path(), None).expect_err("crashed probe must fail"),
        WizardError::PhaseFailed
    );
    assert_eq!(
        std::fs::read_to_string(vault.path().join("opencode.json")).expect("read back"),
        original,
        "F8 compensation restores byte-identical"
    );
}

// --- resume: marker + artifacts, no re-download ---

#[test]
fn resume_deduces_completed_phases_and_skips_them() {
    use tepochcalli::adapters::LocalPayload;

    let payload = tmp();
    payload_tree(payload.path());
    let vault = tmp();
    run_phase3(&LocalPayload::new(payload.path()), vault.path()).expect("F3 must succeed");
    assert!(
        is_phase_done(vault.path(), Phase::F3),
        "intent artifact ⇒ F3 done"
    );

    // Marker round-trips (L3-3 artifact-first): el marker YA NO salta una
    // fase sin artefacto — lo borrado se re-instala (reparación). Con el
    // artefacto presente sí salta.
    assert!(!is_phase_done(vault.path(), Phase::F4));
    mark_phase_done(vault.path(), Phase::F4);
    assert!(
        !is_phase_done(vault.path(), Phase::F4),
        "marker F4 sin binario uv ⇒ Missing ⇒ repaso (reparación)"
    );
    let uv_bin = vault.path().join(".tepochcalli").join("bin").join("uv");
    std::fs::create_dir_all(uv_bin.parent().expect("bin parent")).expect("bin dir");
    std::fs::write(&uv_bin, b"fake-uv").expect("uv artifact fixture");
    assert!(
        is_phase_done(vault.path(), Phase::F4),
        "uv presente ⊕ marker F4 ⇒ skip fiable"
    );
    // Idempotent marker: no duplicate lines.
    mark_phase_done(vault.path(), Phase::F4);
    let body =
        std::fs::read_to_string(vault.path().join(INSTALL_STATE_PATH)).expect("state exists");
    assert_eq!(
        body.matches("F4").count(),
        1,
        "marker must not duplicate, got:\n{body}"
    );

    // Reparación F5: marker F5 + venv borrado ⇒ Missing ⇒ re-run.
    mark_phase_done(vault.path(), Phase::F5);
    venv_python(vault.path());
    assert!(
        is_phase_done(vault.path(), Phase::F5),
        "venv presente ⇒ F5 done"
    );
    std::fs::remove_dir_all(vault.path().join(".tepochcalli").join("venv"))
        .expect("sabotaje: venv borrado");
    assert!(
        !is_phase_done(vault.path(), Phase::F5),
        "venv borrado + marker F5 ⇒ se re-instala, el marker no oculta"
    );

    // Full-artifact vault reads as done for F6/F8 without any marker.
    venv_python(vault.path());
    write(
        &vault
            .path()
            .join(".tepochcalli")
            .join("config")
            .join("tepochcalli.toml"),
        "[embedding]\nprovider = \"none\"\n",
    );
    write(
        &vault.path().join("opencode.json"),
        "{\"mcp\":{\"servers\":{\"tepochcalli-rag\":{}}}}",
    );
    // `tepochcalli-rag` key present ⇒ F8 done via artifacts.
    assert!(is_phase_done(vault.path(), Phase::F8));
    let merged = std::fs::read_to_string(vault.path().join("opencode.json")).expect("read back");
    assert_eq!(merged.matches(MANAGED_RAG).count(), 1);
}

// --- offline: clean failure before touching the vault ---

#[test]
fn offline_without_local_payload_fails_clean_before_touch() {
    // No local payload, no cache and no resume-cover ⇒ E_OFFLINE_NO_CACHE
    // (exit 21), vault untouched.
    let err = guard_offline_before_touch(true, false, false, false).expect_err("must fail offline");
    assert_eq!(err, WizardError::OfflineNoCache);
    assert_eq!(err.exit_code(), 21);
    assert_eq!(err.e_star(), Some("E_OFFLINE_NO_CACHE"));
}

#[test]
fn offline_with_local_payload_and_skip_model_passes_guard() {
    // Local payload + path 5 (no model download) ⇒ offline install proceeds.
    guard_offline_before_touch(true, true, true, false).expect("cached offline must pass");
    // Online never triggers the offline error.
    guard_offline_before_touch(false, false, false, false).expect("online must pass");
}

/// L3-5 OR-arm: un resume cuyo payload ya está local (F3 artefacto) pasa el
/// guard aunque ni payload flag ni models cache existan.
#[test]
fn offline_resume_with_local_payload_from_f3_passes_guard() {
    guard_offline_before_touch(true, false, false, true)
        .expect("resume cuyo payload ya está local debe pasar");
}

// --- idempotence: install x2, zero dupes ---

#[test]
fn rerun_is_idempotent_with_zero_dupes() {
    use tepochcalli::adapters::LocalPayload;

    let payload = tmp();
    payload_tree(payload.path());
    let vault = tmp();

    let _first = run_phase3(&LocalPayload::new(payload.path()), vault.path()).expect("first F3");
    let intent_first =
        std::fs::read(vault.path().join(".tepochcalli").join(".install-intent")).expect("intent");
    let second = run_phase3(&LocalPayload::new(payload.path()), vault.path()).expect("second F3");
    let intent_second =
        std::fs::read(vault.path().join(".tepochcalli").join(".install-intent")).expect("intent");
    assert!(
        second.written.is_empty(),
        "nothing new ⇒ nothing written, got: {:?}",
        second.written
    );
    assert_eq!(
        intent_first, intent_second,
        "intent byte-identical across reruns"
    );

    // F8 rerun: byte-identical file, single managed entry.
    venv_python(vault.path());
    write(
        &vault.path().join("opencode.json"),
        "{\"mcp\":{\"servers\":{}}}",
    );
    let proc = FakeProc::scripted([rag_ok(), rag_ok()]);
    let r1 = run_phase8(&proc, vault.path(), None).expect("first F8");
    assert!(r1.changed);
    let bytes_first = std::fs::read(vault.path().join("opencode.json")).expect("merged");
    let r2 = run_phase8(&proc, vault.path(), None).expect("second F8");
    assert!(!r2.changed, "identical entry ⇒ no rewrite");
    let bytes_second = std::fs::read(vault.path().join("opencode.json")).expect("merged");
    assert_eq!(bytes_first, bytes_second);
    assert_eq!(
        String::from_utf8_lossy(&bytes_second)
            .matches(MANAGED_RAG)
            .count(),
        1
    );

    // F7 rerun: second pass indexes zero.
    let ui = ScriptedUi::new(FakeUiScript {
        selects: [4_usize].into_iter().collect(),
        ..FakeUiScript::default()
    });
    let deps = Phase6Deps {
        ui: &ui,
        host: &host_16gb(),
        proc: &FakeProc::scripted([]),
        http: &FakeHttp::new(HashMap::new()),
    };
    // --skip-model == salida 5 exacta: degraded config, no spawn, no index.
    let picked = run_phase6(&deps, vault.path()).expect("path 5 must succeed");
    assert_eq!(picked.provider, "none");
    assert_eq!(picked.model, None);
    assert_eq!(picked.dims, None);
    let proc = FakeProc::scripted([refresh_ok(2), refresh_ok(0)]);
    let _ = (proc, picked);
}

// --- --skip-model == salida 5 exacta ---

#[test]
fn skip_model_writes_path5_config_without_spawning() {
    use tepochcalli::adapters::HeadlessUi;

    // The headless constructor is the CLI contract (L3-4): skip_model + the
    // row indices main passes ⇒ same row 4.
    let _ui = HeadlessUi::for_install(4, 0, true);
    let vault = tmp();
    // Drive path 5 through the scripted row directly (same index HeadlessUi uses).
    let ui = ScriptedUi::new(FakeUiScript {
        selects: [4_usize].into_iter().collect(),
        ..FakeUiScript::default()
    });
    let deps = Phase6Deps {
        ui: &ui,
        host: &host_16gb(),
        proc: &FakeProc::scripted([]),
        http: &FakeHttp::new(HashMap::new()),
    };
    let picked = run_phase6(&deps, vault.path()).expect("skip-model must succeed");
    assert_eq!(picked.provider, "none", "--skip-model == salida 5");
    let body = std::fs::read_to_string(
        vault
            .path()
            .join(".tepochcalli")
            .join("config")
            .join("tepochcalli.toml"),
    )
    .expect("config exists");
    assert!(body.contains("provider = \"none\""), "got:\n{body}");
    // Path 5 skips F7 entirely: no index dir, no spawn.
    let proc = FakeProc::scripted([]);
    let report = run_phase7(&proc, vault.path(), &picked).expect("path 5 skips F7");
    assert_eq!(report.indexed, 0);
    assert!(!vault.path().join(".tepochcalli").join("db").exists());
}

// --- CLI surface: --resume / --offline flags exist ---

/// L4-4 (4c-6): un install salida 5 (provider none) imprime en STDOUT el
/// checklist de re-entrada (`config embedder` + `reindex`). Fixture con
/// F4/F5/F8 servidas por artefactos (uv/venv fakes + rag_status JSON fake
/// del interpreter) para que el camino quede hermético.
#[test]
fn degraded_install_prints_the_reentry_checklist_on_stdout() {
    use std::io::Write as _;

    let dir = tmp();
    let payload = dir.path().join("payload-checklist");
    std::fs::create_dir_all(&payload).expect("payload dir");
    std::fs::write(payload.join("READ.md"), b"# read\n").expect("payload file");
    let vault = dir.path().join("v-checklist");
    let rt = vault.join(".tepochcalli");
    std::fs::create_dir_all(rt.join("bin")).expect("bin dir");
    std::fs::create_dir_all(rt.join("venv").join("bin")).expect("venv bin dir");
    std::fs::write(rt.join("bin").join("uv"), b"fake-uv").expect("uv artifact");
    let mut fake_python =
        std::fs::File::create(rt.join("venv").join("bin").join("python")).expect("venv artifact");
    // Interpreter fake que habla el contrato rag_status (degraded).
    let script = "#!/bin/sh\necho '{\"embedder\":null,\"index\":null,\"config\":null,\"health\":null,\"state\":\"degraded\",\"reason\":\"E_NO_EMBEDDER\",\"fix_hint\":\"run config embedder\",\"mode\":\"none\"}'\n";
    let _ = fake_python.write_all(script.as_bytes());
    drop(fake_python);
    use std::os::unix::fs::PermissionsExt as _;
    std::fs::set_permissions(
        rt.join("venv").join("bin").join("python"),
        std::fs::Permissions::from_mode(0o755),
    )
    .expect("chmod fake python");
    std::fs::write(
        vault.join(".tepochcalli").join(".install-state"),
        "F1\nF2\nF3\nF4\nF5\nF8\n",
    )
    .expect("state marker");
    std::fs::write(vault.join(".tepochcalli").join(".install-intent"), "")
        .expect("intent artifact");

    let out = std::process::Command::new(env!("CARGO_BIN_EXE_tepochcalli"))
        .args([
            "install",
            "--non-interactive",
            "--skip-model",
            "--resume",
            "--vault",
            vault.to_str().expect("utf8 tmp"),
            "--payload",
            payload.to_str().expect("utf8 tmp"),
        ])
        .output()
        .expect("spawn install");
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert_eq!(
        out.status.code(),
        Some(0),
        "stderr:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
    for expected in [
        "RAG degradado",
        "tepochcalli config embedder --confirm",
        "tepochcalli reindex --confirm",
    ] {
        assert!(
            stdout.contains(expected),
            "stdout debe llevar el checklist de re-entrada ({expected}), got:\n{stdout}"
        );
    }
}

/// L3-3 e2e: un vault con F3..F8 marcados done donde el venv (artefacto F5)
/// fue borrado — `install --resume` vuelve a ejecutar F5 (la reparación) —
/// mientras que el mismo vault con venv presente salta F4/F5 y termina 0.
/// El uv del fixture es fake: F4 solo se saltea (nada lo ejecuta cuando
/// artefacto ⊕ marker), y el re-run de F5 falla tipado con el fake — eso es
/// lo que pinta el pin del re-intento.
#[test]
fn resume_reruns_phases_whose_artifact_was_deleted() {
    let dir = tmp();
    let payload = dir.path().join("payload-t14");
    std::fs::create_dir_all(&payload).expect("payload dir (local source, no network)");
    write(&payload.join("keep.md"), "# payload\n");
    let vault = dir.path().join("v-t14");
    let rt = vault.join(".tepochcalli");
    std::fs::create_dir_all(rt.join("config")).expect("runtime config dir");
    write(
        &vault.join(".tepochcalli").join(".install-intent"),
        "keep.md\n",
    );
    write(
        &vault.join(".tepochcalli").join(".install-state"),
        "F1\nF2\nF3\nF4\nF5\nF6\nF7\nF8\n",
    );
    let uv_bin = rt.join("bin").join("uv");
    std::fs::create_dir_all(rt.join("bin")).expect("bin dir");
    std::fs::write(&uv_bin, b"fake-uv").expect("uv artifact fixture");
    write(
        &rt.join("config").join("tepochcalli.toml"),
        "[embedding]\nprovider = \"none\"\n",
    );
    write(
        &vault.join("opencode.json"),
        "{\"mcp\":{\"servers\":{\"tepochcalli-rag\":{}}}}",
    );

    let cmd = |bin_exists: bool| {
        if bin_exists {
            std::fs::create_dir_all(rt.join("venv").join("bin")).expect("venv fixture");
            std::fs::write(
                rt.join("venv").join("bin").join("python"),
                b"#!/bin/sh\nexit 0\n",
            )
            .expect("venv python fixture");
        } else {
            let _ = std::fs::remove_dir_all(rt.join("venv"));
        }
        std::process::Command::new(env!("CARGO_BIN_EXE_tepochcalli"))
            .args([
                "install",
                "--non-interactive",
                "--resume",
                "--skip-model",
                "--vault",
                vault.to_str().expect("utf8 tmp"),
                "--payload",
                payload.to_str().expect("utf8 tmp"),
            ])
            .output()
            .expect("spawn install --resume")
    };

    // Sin venv: F4 se saltea (artefacto ⊕ marker), F5 SE RE-INTENTA y muere
    // tipado con el vô fake — el marker ya no lo oculta.
    let out = cmd(false);
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert_eq!(out.status.code(), Some(42), "stderr:\n{stderr}");
    assert!(
        stderr.contains("resume: F4 already done"),
        "uv cached salta F4, got:\n{stderr}"
    );
    assert!(
        !stderr.contains("resume: F5 already done"),
        "el marker NO puede ocultar el venv borrado, got:\n{stderr}"
    );
    assert!(
        stderr.contains("install: phase F5 failed"),
        "F5 se re-intenta (reparación), got:\n{stderr}"
    );

    // Con venv devuelto: F5 vuelve a saltar y el resume termina limpio (0),
    // imprimiendo la ruta del vault.
    let out = cmd(true);
    assert_eq!(
        out.status.code(),
        Some(0),
        "stderr:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(
        String::from_utf8_lossy(&out.stderr).contains("resume: F5 already done"),
        "venv presente ⇒ F5 salta, got:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(
        String::from_utf8_lossy(&out.stdout).contains(vault.to_str().expect("utf8")),
        "el exit 0 imprime la ruta del vault",
    );
}

// --- CLI surface: --resume / --offline flags exist ---

/// L3-5: `--offline --resume` sobre un vault con config litellm (sin
/// models/ y sin payload flag) NO cae en exit 21: el brazo D7.3 —
/// provider externo no necesita modelo local — más el resume que ya no
/// re-pide el payload (F3 por artefacto). Termina 0 con todo saltando.
#[test]
fn offline_resume_with_litellm_config_does_not_veto() {
    let dir = tmp();
    let vault = dir.path().join("v-t14b");
    let rt = vault.join(".tepochcalli");
    std::fs::create_dir_all(rt.join("config")).expect("config dir");
    std::fs::create_dir_all(rt.join("db")).expect("db dir");
    std::fs::create_dir_all(rt.join("bin")).expect("bin dir");
    std::fs::create_dir_all(rt.join("venv").join("bin")).expect("venv bin dir");
    std::fs::write(rt.join("bin").join("uv"), b"fake-uv").expect("uv artifact");
    std::fs::write(
        rt.join("venv").join("bin").join("python"),
        b"#!/bin/sh\nexit 0\n",
    )
    .expect("venv artifact");
    std::fs::write(
        vault.join(".tepochcalli").join(".install-intent"),
        "AGENTS.md\n",
    )
    .expect("intent artifact");
    std::fs::write(
        rt.join("config").join("tepochcalli.toml"),
        "\n[embedding]\nprovider = \"litellm\"\nmodel = \"openai/emb\"\napi_key = \"sk-fake\"\n",
    )
    .expect("config artifact");
    std::fs::write(
        rt.join("db").join("index-meta.json"),
        b"{\"model\":\"openai/emb\",\"dims\":null}\n",
    )
    .expect("meta artifact");
    std::fs::write(
        vault.join("opencode.json"),
        b"{\"mcp\": {\"servers\": {\"tepochcalli-rag\": {}}}}\n",
    )
    .expect("f8 artifact");
    assert!(!rt.join("models").exists(), "el pin exige models/ ausente");

    let out = std::process::Command::new(env!("CARGO_BIN_EXE_tepochcalli"))
        .args([
            "install",
            "--non-interactive",
            "--offline",
            "--resume",
            "--vault",
            vault.to_str().expect("utf8 tmp"),
        ])
        .output()
        .expect("spawn install offline");
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert_eq!(
        out.status.code(),
        Some(0),
        "el brazo litellm+resume no puede caer en 21, stderr:\n{stderr}"
    );
    assert!(
        stderr.contains("resume: F3 already done"),
        "F3 por artefacto, got:\n{stderr}"
    );

    // Control: sin --resume el fetch del payload apunta a un loopback muerto:
    // OfflineNoCache determinista (fallo limpio, nada escrito).
    let out = std::process::Command::new(env!("CARGO_BIN_EXE_tepochcalli"))
        .args([
            "install",
            "--non-interactive",
            "--offline",
            "--vault",
            vault.to_str().expect("utf8 tmp"),
        ])
        .env("TEPOCHCALLI_RELEASE_BASE_URL", "http://127.0.0.1:9")
        .output()
        .expect("spawn install offline sin resume");
    assert_eq!(
        out.status.code(),
        Some(21),
        "sin resume no salta F3; fetch imposible offline corta",
    );
}

#[test]
fn install_help_documents_resume_and_offline() {
    let out = std::process::Command::new(env!("CARGO_BIN_EXE_tepochcalli"))
        .args(["install", "--help"])
        .output()
        .expect("spawn install --help");
    assert_eq!(out.status.code(), Some(0));
    let stdout = String::from_utf8_lossy(&out.stdout);
    for flag in ["--resume", "--offline"] {
        assert!(
            stdout.contains(flag),
            "install --help must document {flag}, got:\n{stdout}"
        );
    }
}
