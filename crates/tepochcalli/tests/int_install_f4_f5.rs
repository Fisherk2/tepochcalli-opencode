//! F4 `uv` bootstrap + F5 `uv venv`/`uv sync` + R6 (T9).
//!
//! RED-first: every behavior here failed before `installer::run_phase4` and
//! `run_phase5` existed. Real `tempfile` vaults (D26: no FS port); fakes only
//! (`FakeProc`/`FakeHttp` plus the `common::RecordingProc` that pins the exact
//! argv + cwd + env — no `sh -c` anywhere). The single real-network test is
//! `#[ignore]`d and never syncs (torch would be ~1 GB).

// Shared fakes: this target only needs two of them.
mod common;

use std::collections::HashMap;
use std::io::Write as _;
use std::path::Path;

use common::helpers::sha256_hex;
use common::{FakeHttp, FakeProc, RecordingProc};
use tepochcalli::adapters::fetch::{self, UvAsset};
use tepochcalli::adapters::{StdCommandRunner, UreqHttpClient};
use tepochcalli::application::installer::{
    compensate_phase4_in, compensate_phase5, run_phase4, run_phase4_with_state, run_phase5,
    UV_STAGE_DIR,
};
use tepochcalli::ports::CommandOutput;
use tepochcalli::WizardError;

fn tmp() -> tempfile::TempDir {
    let dir = tempfile::tempdir().expect("tempdir for T9 fixtures");
    // Keep fixtures private; the wizard also repairs a legacy 0755 root.
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt as _;
        std::fs::set_permissions(dir.path(), std::fs::Permissions::from_mode(0o700))
            .expect("private fixture");
    }
    dir
}

/// Minimal `.tar.gz` with a single `member` file (mirrors `phases_f3.rs`).
fn uv_tar_gz(member: &str, body: &[u8]) -> Vec<u8> {
    let mut tar_buf = Vec::new();
    {
        let mut builder = tar::Builder::new(&mut tar_buf);
        let mut header = tar::Header::new_gnu();
        header.set_size(body.len() as u64);
        header.set_mode(0o755);
        header.set_cksum();
        builder
            .append_data(&mut header, member, body)
            .expect("tar fixture");
        builder.into_inner().expect("finish tar");
    }
    let mut encoder = flate2::write::GzEncoder::new(Vec::new(), flate2::Compression::default());
    encoder.write_all(&tar_buf).expect("gzip fixture");
    encoder.finish().expect("finish gzip")
}

#[cfg(not(windows))]
const UV_BIN: &str = "uv";
#[cfg(windows)]
const UV_BIN: &str = "uv.exe";

/// `run_phase4_with` seam asset: the real table pins the official release, so
/// a fake asset carries the fixture's own hash (same seam idea as T7's
/// `check_prereqs_on`).
fn fake_asset(filename: &'static str, body: &[u8]) -> UvAsset {
    UvAsset {
        os: "linux",
        arch: "x86_64",
        filename,
        sha256_hex: Box::leak(sha256_hex(body).into_boxed_str()),
    }
}

fn fake_uv_download_url(asset: &UvAsset) -> String {
    format!(
        "https://github.com/astral-sh/uv/releases/download/{}/{}",
        fetch::UV_VERSION,
        asset.filename
    )
}

fn ok_version() -> Result<CommandOutput, WizardError> {
    Ok(CommandOutput {
        status: 0,
        stdout: format!("uv {} (test fake)\n", fetch::UV_VERSION),
        stderr: String::new(),
    })
}

fn ok_status() -> Result<CommandOutput, WizardError> {
    Ok(CommandOutput {
        status: 0,
        stdout: String::new(),
        stderr: String::new(),
    })
}

fn runtime_sentinels(vault: &Path) {
    // models/ + db/ + config/ fixtures: F4/F5 compensations must never touch
    // them (the unwind-total is T14, not here).
    for dir in ["models", "db", "config"] {
        let file = vault.join(".tepochcalli").join(dir).join("sentinel.txt");
        std::fs::create_dir_all(file.parent().expect("sentinel parent"))
            .expect("sentinel fixture dir");
        std::fs::write(&file, format!("keep {dir}\n")).expect("sentinel fixture");
    }
}

fn assert_sentinels_intact(vault: &Path) {
    for dir in ["models", "db", "config"] {
        let file = vault.join(".tepochcalli").join(dir).join("sentinel.txt");
        assert_eq!(
            std::fs::read_to_string(&file).expect("sentinel readable"),
            format!("keep {dir}\n"),
            "{dir} must survive F4/F5"
        );
    }
}

/// Per-invocation stages under `dir`; `install_uv` must leave none behind.
fn stage_residue(dir: &Path) -> Vec<String> {
    let Ok(entries) = std::fs::read_dir(dir) else {
        return Vec::new();
    };
    entries
        .flatten()
        .map(|entry| entry.file_name().to_string_lossy().into_owned())
        .filter(|name| name.starts_with(UV_STAGE_DIR))
        .collect()
}

#[test]
fn uv_asset_table_covers_all_platforms_with_real_pins() {
    assert_eq!(fetch::UV_VERSION, "0.12.9");
    for (os, arch, filename) in [
        ("linux", "x86_64", "uv-x86_64-unknown-linux-gnu.tar.gz"),
        ("linux", "aarch64", "uv-aarch64-unknown-linux-gnu.tar.gz"),
        ("macos", "x86_64", "uv-x86_64-apple-darwin.tar.gz"),
        ("macos", "aarch64", "uv-aarch64-apple-darwin.tar.gz"),
        ("windows", "x86_64", "uv-x86_64-pc-windows-msvc.zip"),
    ] {
        let asset =
            fetch::uv_asset_for(os, arch).unwrap_or_else(|| panic!("{os}/{arch} must be covered"));
        assert_eq!(asset.filename, filename);
        assert!(
            asset.sha256_hex.len() == 64 && asset.sha256_hex.bytes().all(|b| b.is_ascii_hexdigit()),
            "{os}/{arch} pin must be 64 hex chars, got: {}",
            asset.sha256_hex
        );
        assert!(
            !asset.sha256_hex.contains("PLACEHOLDER"),
            "{os}/{arch} pin must be real, not a placeholder"
        );
    }
    assert!(
        fetch::uv_asset_for_current_platform().is_some(),
        "this build's platform must be covered"
    );
}

#[test]
fn f4_ok_leaves_executable_uv_and_reports_version() {
    let body = uv_tar_gz(UV_BIN, b"fake-uv-binary");
    let asset = fake_asset("uv-test.tar.gz", &body);
    let mut files = HashMap::new();
    files.insert(fake_uv_download_url(&asset), body.clone());
    let http = FakeHttp::new(files);
    let proc = FakeProc::scripted([ok_version()]);

    let vault = tmp();
    let state = tmp();
    runtime_sentinels(vault.path());
    let report = run_phase4_with_state(&http, &proc, vault.path(), &asset, state.path())
        .expect("F4 must succeed");

    let link = vault.path().join(".tepochcalli").join("bin").join(UV_BIN);
    // Public report and resume artifact stay vault-based (F5 resolves the link).
    assert_eq!(report.uv, link);
    // The scripted `--version` output is the only source of the version, so
    // the report proves the version check ran.
    assert!(
        report.version.contains(fetch::UV_VERSION),
        "report must carry `uv --version`, got: {}",
        report.version
    );
    #[cfg(unix)]
    {
        let external = state.path().join("bin").join(UV_BIN);
        let target = std::fs::read_link(&link).expect("vault uv must be a symlink");
        assert_eq!(target, external, "the link must point into the state root");
        use std::os::unix::fs::PermissionsExt as _;
        let mode = std::fs::metadata(&external)
            .expect("external uv metadata")
            .permissions()
            .mode();
        assert!(mode & 0o111 != 0, "the external uv must be executable");
    }
    assert_eq!(
        std::fs::read(&link).expect("uv readable through the vault link"),
        b"fake-uv-binary"
    );
    assert!(
        !vault.path().join(".tepochcalli").join(".uv-stage").exists(),
        "the download stage must not leak into the vault"
    );
    assert_eq!(
        stage_residue(state.path()),
        Vec::<String>::new(),
        "no .uv-stage* residue after a successful install_uv"
    );
    assert_sentinels_intact(vault.path());
}

#[test]
fn f4_corrupt_asset_fails_typed_and_leaves_no_bin() {
    // Real table pin vs. garbage bytes: `FakeHttp` maps it to `PayloadCorrupt`
    // exactly like the real adapter maps a checksum mismatch.
    let asset = fetch::uv_asset_for_current_platform().expect("platform covered");
    let url = fetch::uv_download_url(asset);
    let mut files = HashMap::new();
    files.insert(url, b"tampered-bytes".to_vec());
    let http = FakeHttp::new(files);
    let proc = FakeProc::scripted([ok_version()]);

    let vault = tmp();
    let state = tmp();
    runtime_sentinels(vault.path());
    let err = run_phase4_with_state(&http, &proc, vault.path(), asset, state.path())
        .expect_err("tampered asset must fail");
    assert_eq!(err, WizardError::PayloadCorrupt);
    assert!(
        !vault.path().join(".tepochcalli").join("bin").exists(),
        "a corrupt asset must leave no bin/"
    );
    assert!(
        !state.path().join("bin").exists(),
        "a corrupt asset must leave no external bin/"
    );
    assert_sentinels_intact(vault.path());
}

#[test]
fn f4_version_check_failure_compensates_bin() {
    let body = uv_tar_gz(UV_BIN, b"fake-uv-binary");
    let asset = fake_asset("uv-test.tar.gz", &body);
    let mut files = HashMap::new();
    files.insert(fake_uv_download_url(&asset), body);
    let http = FakeHttp::new(files);
    // The binary landed but does not run (non-zero status): the asset is
    // unusable, so F4 compensates instead of leaving a dead `bin/`.
    let proc = FakeProc::scripted([Ok(CommandOutput {
        status: 1,
        stdout: String::new(),
        stderr: "exec format error".to_string(),
    })]);

    let vault = tmp();
    let state = tmp();
    runtime_sentinels(vault.path());
    let err = run_phase4_with_state(&http, &proc, vault.path(), &asset, state.path())
        .expect_err("dead binary must fail");
    assert_eq!(err, WizardError::PayloadCorrupt);
    assert!(
        !vault.path().join(".tepochcalli").join("bin").exists(),
        "failed F4 must compensate bin/"
    );
    assert!(
        state.path().join("bin").join(UV_BIN).is_file(),
        "the shared state bin/ is per user and survives F4 compensation"
    );
    assert_eq!(
        stage_residue(state.path()),
        Vec::<String>::new(),
        "no .uv-stage* residue after a failed install_uv"
    );
    assert_sentinels_intact(vault.path());
}

#[test]
fn f4_spawn_failure_propagates_typed_and_compensates() {
    let body = uv_tar_gz(UV_BIN, b"fake-uv-binary");
    let asset = fake_asset("uv-test.tar.gz", &body);
    let mut files = HashMap::new();
    files.insert(fake_uv_download_url(&asset), body);
    let http = FakeHttp::new(files);
    let proc = FakeProc::scripted([Err(WizardError::PhaseFailed)]);

    let vault = tmp();
    let state = tmp();
    let err = run_phase4_with_state(&http, &proc, vault.path(), &asset, state.path())
        .expect_err("spawn failure must fail");
    assert_eq!(err, WizardError::PhaseFailed);
    assert!(
        !vault.path().join(".tepochcalli").join("bin").exists(),
        "failed F4 must compensate bin/"
    );
    assert!(
        state.path().join("bin").join(UV_BIN).is_file(),
        "the shared state bin/ is per user and survives F4 compensation"
    );
}

#[test]
fn f5_ok_runs_sync_frozen_with_project_env() {
    let vault = tmp();
    let project = vault.path().join(".tepochcalli");
    let uv = project.join("bin").join(UV_BIN);
    std::fs::create_dir_all(uv.parent().expect("bin parent")).expect("bin fixture");
    std::fs::write(&uv, b"fake-uv-binary").expect("uv fixture");
    runtime_sentinels(vault.path());

    let proc = RecordingProc::scripted([ok_status(), ok_status(), ok_status(), ok_status()]);
    let report = run_phase5(&proc, vault.path()).expect("F5 must succeed");

    let venv = project.join("venv");
    assert_eq!(report.venv, venv);
    assert!(venv.is_dir(), "F5 must leave the venv dir behind");

    let calls = proc.calls();
    assert_eq!(
        calls.len(),
        4,
        "python-install + venv + sync + import check, got: {calls:?}"
    );
    let uv_str = uv.to_str().expect("utf8 tmp").to_string();
    // Every `uv` call runs in the project dir (pyproject.toml + uv.lock live
    // there) with the uv 0.12.9 quirk env (the venv location is ONLY honored
    // via `UV_PROJECT_ENVIRONMENT`, same as the repo's own Justfile).
    for call in &calls[..3] {
        assert_eq!(
            call.program, uv_str,
            "uv runs from .tepochcalli/bin, got: {}",
            call.program
        );
        assert_eq!(call.cwd, project, "uv cwd must be the project dir");
        assert!(
            call.env
                .iter()
                .any(|(k, v)| k == "UV_PROJECT_ENVIRONMENT" && v == "venv"),
            "missing project env in {:?}",
            call.env
        );
    }
    assert_eq!(calls[0].args, ["python", "install", "3.12"]);
    assert_eq!(calls[1].args, ["venv", "--clear", "venv"]);
    assert_eq!(calls[2].args, ["sync", "--frozen"]);
    // The import check runs the venv interpreter (R6/T4: the tools subpackage
    // and the flow's document extractor must import), never the system python.
    let import_call = &calls[3];
    let (python, import_args) = (&import_call.program, &import_call.args);
    assert!(
        python.ends_with("python") || python.ends_with("python.exe"),
        "import check must use the venv interpreter, got: {python}"
    );
    assert_eq!(import_args.len(), 2);
    assert_eq!(import_args[0], "-c");
    assert!(
        import_args[1].contains("import markitdown")
            && import_args[1].contains("tepochcalli_mcp.tools.search"),
        "R6/T4: markitdown and the tools subpackage must import, got: {}",
        import_args[1]
    );
    assert_sentinels_intact(vault.path());
}

#[test]
fn f5_sync_failure_removes_venv_but_keeps_f4_bin() {
    let vault = tmp();
    let project = vault.path().join(".tepochcalli");
    let uv = project.join("bin").join(UV_BIN);
    std::fs::create_dir_all(uv.parent().expect("bin parent")).expect("bin fixture");
    std::fs::write(&uv, b"fake-uv-binary").expect("uv fixture");
    runtime_sentinels(vault.path());

    let proc = FakeProc::scripted([ok_status(), ok_status(), Err(WizardError::PhaseFailed)]);
    let err = run_phase5(&proc, vault.path()).expect_err("sync failure must fail");
    assert_eq!(err, WizardError::PhaseFailed);
    assert!(
        !project.join("venv").exists(),
        "failed F5 must compensate venv/"
    );
    // F4 stays: unwinding the whole runtime is T14, not F5.
    assert_eq!(
        std::fs::read(&uv).expect("F4 uv must survive F5 failure"),
        b"fake-uv-binary"
    );
    assert_sentinels_intact(vault.path());
}

#[test]
fn compensate_fns_are_idempotent_and_never_touch_runtime_data() {
    let vault = tmp();
    let state = tmp();
    runtime_sentinels(vault.path());
    let log = state.path().join("install-1.log");
    std::fs::write(&log, "failure log").expect("state log fixture");

    // Missing dirs: compensation is a no-op, never an error.
    compensate_phase4_in(vault.path(), state.path());
    compensate_phase5(vault.path());

    let bin = vault.path().join(".tepochcalli").join("bin");
    let venv = vault.path().join(".tepochcalli").join("venv");
    let state_bin = state.path().join("bin");
    std::fs::create_dir_all(&bin).expect("bin fixture");
    std::fs::create_dir_all(&venv).expect("venv fixture");
    std::fs::create_dir_all(&state_bin).expect("state bin fixture");
    let keep = state_bin.join("keep");
    std::fs::write(&keep, "shared").expect("state bin sentinel");
    compensate_phase4_in(vault.path(), state.path());
    compensate_phase5(vault.path());
    assert!(!bin.exists());
    assert!(!venv.exists());
    assert!(
        keep.is_file(),
        "shared state bin/ is per user: compensation must not remove it"
    );
    assert!(state.path().is_dir(), "the state root itself must survive");
    assert_eq!(
        std::fs::read_to_string(&log).expect("state log survives"),
        "failure log"
    );
    assert_sentinels_intact(vault.path());
}

/// Real download of the pinned uv 0.12.9 asset for this platform + `uv
/// --version` through the real adapters. Ignored by default: needs network
/// and ~19 MB. Never runs `sync` (torch would be ~1 GB).
#[test]
#[ignore = "real network: downloads the uv 0.12.9 release asset and runs `uv --version` (no sync)"]
fn real_uv_asset_downloads_and_reports_version() {
    let asset = fetch::uv_asset_for_current_platform().expect("platform covered");
    let vault = tmp();
    let http = UreqHttpClient::new();
    let proc = StdCommandRunner;
    let report = run_phase4(&http, &proc, vault.path()).expect("real F4");
    assert!(
        report.version.contains(fetch::UV_VERSION),
        "unexpected version: {}",
        report.version
    );
    assert!(report.uv.is_file());
    let _ = asset;
}

/// Guard de orden del install (Solution 4). El `cli` es privado al binario: la
/// secuencia se fija aquí como guard textual, igual que `int_architecture.rs`
/// fija las fronteras de capas. La selección va dentro de `run_stages`, antes
/// de F3; el gate sigue dentro de F6, después de F5.
fn install_phases_source() -> String {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("src/cli/install_phases.rs");
    std::fs::read_to_string(path).expect("install_phases.rs legible")
}

#[test]
fn install_pregunta_el_embedder_antes_de_f3_y_deja_el_gate_tras_f5() {
    let src = install_phases_source();
    let select_at = src
        .find("preselect_embedder(ui")
        .expect("la selección debe ser la primera interacción del install");
    let f3_at = src
        .find("let skip_f3 =")
        .expect("F3 sigue en install_phases");
    assert!(
        select_at < f3_at,
        "el embedder se elige antes de F3, no durante F6: {select_at} vs {f3_at}"
    );
    let f5_at = src
        .find("hito 3/7: F5 venv")
        .expect("el hito 3/7 marca F5 terminado");
    let gate_at = src
        .find("match run_f6_or_degraded(")
        .expect("el gate se invoca desde F6");
    assert!(
        f5_at < gate_at,
        "el gate test-embed va tras el venv (ADR-015): {f5_at} vs {gate_at}"
    );
}

#[test]
fn resume_con_f6_hecha_no_roba_la_respuesta_del_embedder() {
    let src = install_phases_source();
    let guard_at = src
        .find("f6_cached")
        .expect("debe haber una guarda de resume antes de preguntar");
    let select_at = src
        .find("preselect_embedder(ui")
        .expect("la selección debe estar en install_phases");
    assert!(
        guard_at < select_at,
        "con F6 ya hecha no se consume la cola de respuestas: {guard_at} vs {select_at}"
    );
}
