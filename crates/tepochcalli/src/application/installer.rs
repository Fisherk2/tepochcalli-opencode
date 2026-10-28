//! F1 (prereqs) + F2 (vault dir). No compensation: neither phase touches
//! user data, so there is nothing to roll back (todo T7).
//!
//! F3 (T8): merge the payload without overwrite, create `00-Resources/`
//! with 2 placeholders, write `.install-intent` (basis of F3 compensation
//! in T14). Depends on `domain` + `ports` only — never on `adapters/`.
//!
//! F4 (T9): bootstrap the pinned `uv` release binary (SHA-256 verified,
//! executable bit, `uv --version` proves it runs). F5 (T9): `uv python
//! install`, `uv venv`, `uv sync --frozen` and the R6 import check — all via
//! the `CommandRunner` port with explicit argv + cwd + env (never `sh -c`,
//! never `std::env` globals). Compensations remove only what the phase
//! wrote (`bin/` for F4, `venv/` for F5); `models/`, `db/` and `config/`
//! are never touched (the full unwind is T14, not here).

use std::path::{Path, PathBuf};

use crate::archive::{extract_tar_gz, extract_zip};
use crate::domain::{VaultPath, WizardError};
use crate::fetch::{self, UvAsset};
use crate::ports::{
    CommandOutput, CommandRunner, HostProbe, HttpClient, MergeReport, PayloadSource, Ui,
};

/// Minimum machine RAM in GiB (below aborts, exit 10 — never half-installs).
pub const MIN_RAM_GB: f64 = 8.0;
/// Minimum free disk in GiB at the probe path (below aborts, exit 11).
pub const MIN_DISK_FREE_GB: f64 = 4.0;
/// OS values (`std::env::consts::OS`) the wizard supports (else exit 12).
pub const SUPPORTED_OS: &[&str] = &["linux", "macos", "windows"];
/// F2 default when `--vault` is absent, resolved under the caller cwd.
pub const DEFAULT_VAULT_DIR: &str = "./tepochcalli-vault";
/// Canonical resources dir (exact case the flow indexes:
/// `citation.py: RESOURCES_DIR = "00-Resources"`).
pub const RESOURCES_DIR: &str = "00-Resources";
/// F3 compensation basis (T14): exactly the files F3 wrote, one vault-
/// relative path per line. The intent file itself is NOT listed (its path
/// is this constant, so compensation removes it alongside the listing).
pub const INSTALL_INTENT_PATH: &str = ".tepochcalli/.install-intent";
/// Placeholder names: 1 `.md` + 1 `.pdf` (D22). Trays (`02-drafts/`…)
/// are Phase 5 scope (TD-8) and must NOT be created here.
pub const PLACEHOLDER_MD_NAME: &str = "ejemplo.md";
pub const PLACEHOLDER_PDF_NAME: &str = "ejemplo.pdf";
/// Placeholder markdown body (Spanish, like the payload docs).
const PLACEHOLDER_MD_BODY: &str = "# Ejemplo\n\
\n\
Este archivo es un marcador de posición creado por `tepochcalli install`.\n\
Escribe tus notas de investigación en `00-Resources/`; el índice RAG las\n\
recogerá en la próxima indexación.\n";
/// Placeholder PDF bytes, embedded in the crate (AC-e: NOT in the payload
/// repo). Hand-written minimal PDF (catalog/pages/page/contents/helvetica);
/// xref offsets computed by `gen_ejemplo_pdf.py`, verified parseable by
/// Docling (venv) in T8 — re-verify if the asset is ever regenerated.
const EJEMPLO_PDF: &[u8] = include_bytes!("../../assets/ejemplo.pdf");
/// Desktop tools the wizard warns about but never installs (Non-Goals).
const OBSIDIAN_TOOL: &str = "obsidian";
const OPENCODE_TOOL: &str = "opencode";
/// Writability probe (created + removed); absence afterwards is asserted.
const WRITE_PROBE: &str = ".tepochcalli-write-probe";

/// What F1 established: the gate inputs plus the best-effort tool sightings.
#[derive(Debug, Clone, PartialEq)]
pub struct PrereqReport {
    /// `std::env::consts::OS` value the gate ran on.
    pub os: String,
    /// RAM the gate judged (`total`, falling back to `available`).
    pub ram_gb: Option<f64>,
    /// Free disk the gate judged at the probe path.
    pub disk_free_gb: Option<f64>,
    /// `obsidian` found on `PATH` (missing only warns).
    pub obsidian_found: bool,
    /// `opencode` found on `PATH` (missing only warns).
    pub opencode_found: bool,
}

/// Whether the wizard supports this `std::env::consts::OS` value.
#[must_use]
pub fn is_supported_os(os: &str) -> bool {
    SUPPORTED_OS.contains(&os)
}

/// `true` when `name` (or `name.exe`) is an executable file under `dirs`.
#[must_use]
pub fn tool_present_in(name: &str, dirs: &[PathBuf]) -> bool {
    dirs.iter()
        .any(|dir| dir.join(name).is_file() || dir.join(format!("{name}.exe")).is_file())
}

fn path_dirs() -> Vec<PathBuf> {
    match std::env::var_os("PATH") {
        Some(paths) => std::env::split_paths(&paths).collect(),
        None => Vec::new(),
    }
}

fn check_ram(host: &dyn HostProbe) -> Result<Option<f64>, WizardError> {
    // shortcut: probe failure passes — a gate must not abort on unknown data (T10 refines UX).
    let ram = host.ram_total_gb().or_else(|| host.ram_available_gb());
    if ram.is_some_and(|gb| gb < MIN_RAM_GB) {
        return Err(WizardError::PrereqRam);
    }
    Ok(ram)
}

fn check_disk(host: &dyn HostProbe, at: &Path) -> Result<Option<f64>, WizardError> {
    let free = host.disk_free_gb(at);
    if free.is_some_and(|gb| gb < MIN_DISK_FREE_GB) {
        return Err(WizardError::PrereqDisk);
    }
    Ok(free)
}

/// F1 with explicit seams (OS value + disk probe path) for `FakeHost` tests.
pub fn check_prereqs_on(
    host: &dyn HostProbe,
    os: &str,
    disk_probe_path: &Path,
) -> Result<PrereqReport, WizardError> {
    if !is_supported_os(os) {
        return Err(WizardError::PrereqPlatform);
    }
    let ram_gb = check_ram(host)?;
    let disk_free_gb = check_disk(host, disk_probe_path)?;
    let dirs = path_dirs();
    Ok(PrereqReport {
        os: os.to_string(),
        ram_gb,
        disk_free_gb,
        obsidian_found: tool_present_in(OBSIDIAN_TOOL, &dirs),
        opencode_found: tool_present_in(OPENCODE_TOOL, &dirs),
    })
}

/// F1 against the real OS, probing free disk at the caller cwd (the vault is
/// unknown until F2, so F1 cannot probe it yet).
pub fn check_prereqs(host: &dyn HostProbe) -> Result<PrereqReport, WizardError> {
    let cwd = std::env::current_dir().map_err(|_| WizardError::PermissionDenied)?;
    check_prereqs_on(host, std::env::consts::OS, &cwd)
}

/// F2 choice: `--vault` wins; otherwise the Ui asks (default preselected).
/// A blank flag counts as absent — the Ui is asked instead of guessing.
pub fn resolve_vault_dir(ui: &dyn Ui, flag: Option<&str>) -> Result<String, WizardError> {
    match flag {
        Some(raw) if !raw.trim().is_empty() => Ok(raw.to_string()),
        _ => ui.input("Vault directory", Some(DEFAULT_VAULT_DIR)),
    }
}

/// F2 creation: missing dirs are made, existing ones reused as-is (never
/// wiped); a file at the path — or an unwritable dir — is a typed error.
// shortcut: every `create_dir_all` failure maps to `PermissionDenied`; T15 refines the panel.
pub fn ensure_vault_dir(path: &Path) -> Result<VaultPath, WizardError> {
    std::fs::create_dir_all(path).map_err(|_| WizardError::PermissionDenied)?;
    if !path.is_dir() {
        return Err(WizardError::PermissionDenied);
    }
    let probe = path.join(WRITE_PROBE);
    if std::fs::OpenOptions::new()
        .write(true)
        .create(true)
        .truncate(true)
        .open(&probe)
        .is_err()
    {
        return Err(WizardError::PermissionDenied);
    }
    let _ = std::fs::remove_file(&probe);
    VaultPath::new(&path.to_string_lossy()).ok_or(WizardError::PermissionDenied)
}

/// What F3 merged: payload files + placeholders, written vs. left intact.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Phase3Report {
    /// Files F3 newly wrote (payload + placeholders), absolute under vault.
    pub written: Vec<PathBuf>,
    /// Files left byte-intact ("ya estaba") or skipped by policy.
    pub skipped: Vec<PathBuf>,
}

/// Ensure `00-Resources/` + the 2 placeholders (D22): pre-existing files
/// are never overwritten, only recorded as skipped.
fn ensure_placeholders(vault: &Path) -> Result<MergeReport, WizardError> {
    // shortcut: every fs failure maps to `PermissionDenied` (T7 convention;
    // T15 refines the panel).
    let root = vault
        .canonicalize()
        .map_err(|_| WizardError::PermissionDenied)?;
    let dir = root.join(RESOURCES_DIR);
    std::fs::create_dir_all(&dir).map_err(|_| WizardError::PermissionDenied)?;
    let mut report = MergeReport::default();
    let md = dir.join(PLACEHOLDER_MD_NAME);
    if md.exists() {
        report.skipped.push(md);
    } else {
        std::fs::write(&md, PLACEHOLDER_MD_BODY).map_err(|_| WizardError::PermissionDenied)?;
        report.written.push(md);
    }
    let pdf = dir.join(PLACEHOLDER_PDF_NAME);
    if pdf.exists() {
        report.skipped.push(pdf);
    } else {
        std::fs::write(&pdf, EJEMPLO_PDF).map_err(|_| WizardError::PermissionDenied)?;
        report.written.push(pdf);
    }
    Ok(report)
}

/// Vault-relative path with `/` separators for the intent file.
fn intent_line(root: &Path, path: &Path) -> Result<String, WizardError> {
    let rel = path.strip_prefix(root).map_err(|_| WizardError::Internal)?;
    Ok(rel
        .components()
        .map(|c| c.as_os_str().to_string_lossy().into_owned())
        .collect::<Vec<_>>()
        .join("/"))
}

fn write_intent(vault: &Path, written: &[PathBuf]) -> Result<(), WizardError> {
    // shortcut: every fs failure maps to `PermissionDenied` (T7 convention).
    let root = vault
        .canonicalize()
        .map_err(|_| WizardError::PermissionDenied)?;
    let mut lines: Vec<String> = written
        .iter()
        .map(|p| intent_line(&root, p))
        .collect::<Result<_, _>>()?;
    lines.sort();
    let dir = vault.join(".tepochcalli");
    std::fs::create_dir_all(&dir).map_err(|_| WizardError::PermissionDenied)?;
    let mut body = lines.join("\n");
    body.push('\n');
    std::fs::write(vault.join(INSTALL_INTENT_PATH), body).map_err(|_| WizardError::PermissionDenied)
}

/// F3: merge the payload without overwrite, create `00-Resources/` with
/// its 2 placeholders, write `.install-intent` listing exactly the files
/// written. Pre-existing user files stay byte-intact.
pub fn run_phase3(payload: &dyn PayloadSource, vault: &Path) -> Result<Phase3Report, WizardError> {
    let mut merge = payload.materialize_report(vault)?;
    let placeholders = ensure_placeholders(vault)?;
    merge.written.extend(placeholders.written);
    merge.skipped.extend(placeholders.skipped);
    merge.written.sort();
    merge.skipped.sort();
    write_intent(vault, &merge.written)?;
    Ok(Phase3Report {
        written: merge.written,
        skipped: merge.skipped,
    })
}

// --- F4: `uv` bootstrap + F5: venv/`sync` (T9) ---

/// Runtime dir (D2: `.tepochcalli/` engine-neutral).
pub const RUNTIME_DIR: &str = ".tepochcalli";
/// F4 writes only here; its compensation removes exactly this dir.
pub const UV_BIN_DIR: &str = "bin";
/// F5 writes only here; its compensation removes exactly this dir.
pub const VENV_DIR_NAME: &str = "venv";
/// Scratch dir for the verified asset; removed after a successful F4 and by
/// the F4 compensation (hygiene, never user data).
pub const UV_STAGE_DIR: &str = ".uv-stage";
/// Quirk uv 0.12.9: the project venv location is ONLY honored via env var
/// (same quirk the repo's own Justfile + `phase1.yml` work around).
pub const UV_PROJECT_ENVIRONMENT: (&str, &str) = ("UV_PROJECT_ENVIRONMENT", "venv");
/// Managed CPython the installer boots (repo canonical: pyproject + workflow
/// pin the 3.12 series).
pub const UV_MANAGED_PYTHON: &str = "3.12";
/// R6 import check: the tools subpackage must import from the fresh venv.
pub const IMPORT_CHECK: &str = "import tepochcalli_mcp.tools.search";

/// What F4 established: where `uv` lives plus its reported version.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Phase4Report {
    /// Absolute path of the installed binary (`.tepochcalli/bin/uv`).
    pub uv: PathBuf,
    /// First line of `uv --version` (proves the binary executes).
    pub version: String,
}

/// What F5 established: where the project venv lives.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Phase5Report {
    /// Absolute path of the project environment (`.tepochcalli/venv/`).
    pub venv: PathBuf,
}

fn runtime_dir(vault: &Path) -> PathBuf {
    vault.join(RUNTIME_DIR)
}

fn uv_binary_name() -> &'static str {
    if cfg!(windows) {
        "uv.exe"
    } else {
        "uv"
    }
}

fn uv_binary_path(vault: &Path) -> PathBuf {
    runtime_dir(vault).join(UV_BIN_DIR).join(uv_binary_name())
}

/// Venv interpreter for gate subprocesses (F5 import check, F6 embed-check).
/// Platform layout mirrors the MCP command F8 will register (D20).
#[must_use]
pub fn venv_python(venv: &Path) -> PathBuf {
    venv.join(if cfg!(windows) {
        "Scripts/python.exe"
    } else {
        "bin/python"
    })
}

/// Empty `dir`, creating it (an interrupted F4 may leave a stale stage).
fn clear_dir(dir: &Path) -> Result<(), WizardError> {
    // shortcut: every fs failure maps to `PermissionDenied` (T7 convention;
    // T15 refines the panel).
    match std::fs::remove_dir_all(dir) {
        Ok(()) => {}
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
        Err(_) => return Err(WizardError::PermissionDenied),
    }
    std::fs::create_dir_all(dir).map_err(|_| WizardError::PermissionDenied)
}

/// Unpack the verified release asset (tar.gz on Unix, zip on Windows).
fn extract_uv_asset(archive: &Path, stage: &Path) -> Result<(), WizardError> {
    let is_zip = archive
        .file_name()
        .and_then(|name| name.to_str())
        .is_some_and(|name| name.ends_with(".zip"));
    let file = std::fs::File::open(archive).map_err(|_| WizardError::PayloadCorrupt)?;
    if is_zip {
        extract_zip(file, stage).map_err(|_| WizardError::PayloadCorrupt)
    } else {
        extract_tar_gz(file, stage).map_err(|_| WizardError::PayloadCorrupt)
    }
}

/// Locate the `uv` binary inside the extracted stage: either at the stage
/// root or one level deep (the released layout nests it as `<stem>/uv`).
fn find_uv_binary(stage: &Path) -> Option<PathBuf> {
    let want = uv_binary_name();
    let direct = stage.join(want);
    if direct.is_file() {
        return Some(direct);
    }
    let entries = std::fs::read_dir(stage).ok()?;
    for entry in entries.flatten() {
        let nested = entry.path().join(want);
        if nested.is_file() {
            return Some(nested);
        }
    }
    None
}

#[cfg(unix)]
fn set_executable(path: &Path) -> Result<(), WizardError> {
    use std::os::unix::fs::PermissionsExt as _;
    let mut perms = std::fs::metadata(path)
        .map_err(|_| WizardError::PermissionDenied)?
        .permissions();
    perms.set_mode(0o755);
    std::fs::set_permissions(path, perms).map_err(|_| WizardError::PermissionDenied)
}

#[cfg(not(unix))]
fn set_executable(_path: &Path) -> Result<(), WizardError> {
    Ok(())
}

/// Run `program` with explicit argv + cwd + env; any non-zero status is a
/// compensated phase failure (exit codes, never text, cross the boundary).
fn run_checked(
    proc: &dyn CommandRunner,
    program: &str,
    args: &[&str],
    cwd: &Path,
    env: &[(&str, &str)],
) -> Result<CommandOutput, WizardError> {
    let out = proc.run(program, args, cwd, env)?;
    if out.status == 0 {
        Ok(out)
    } else {
        Err(WizardError::PhaseFailed)
    }
}

fn install_uv(
    http: &dyn HttpClient,
    proc: &dyn CommandRunner,
    vault: &Path,
    asset: &UvAsset,
) -> Result<Phase4Report, WizardError> {
    let stage = runtime_dir(vault).join(UV_STAGE_DIR);
    clear_dir(&stage)?;
    let archive = stage.join(asset.filename);
    // SHA-256 verified BEFORE anything is trusted (the adapter enforces it).
    http.download(&fetch::uv_download_url(asset), &archive, asset.sha256_hex)?;
    extract_uv_asset(&archive, &stage)?;
    let staged = find_uv_binary(&stage).ok_or(WizardError::PayloadCorrupt)?;
    let target = uv_binary_path(vault);
    if let Some(parent) = target.parent() {
        std::fs::create_dir_all(parent).map_err(|_| WizardError::PermissionDenied)?;
    }
    std::fs::copy(&staged, &target).map_err(|_| WizardError::PermissionDenied)?;
    set_executable(&target)?;
    // Best-effort: the asset was verified, residue is harmless.
    let _ = std::fs::remove_dir_all(&stage);
    let program = target.to_str().ok_or(WizardError::Internal)?.to_string();
    let out = proc.run(&program, &["--version"], vault, &[])?;
    if out.status != 0 {
        return Err(WizardError::PayloadCorrupt);
    }
    Ok(Phase4Report {
        uv: target,
        version: out
            .stdout
            .lines()
            .next()
            .unwrap_or_default()
            .trim()
            .to_string(),
    })
}

/// F4: download the pinned `uv` asset, verify, install to
/// `.tepochcalli/bin/`, prove it runs. Failure compensates `bin/` + stage.
pub fn run_phase4(
    http: &dyn HttpClient,
    proc: &dyn CommandRunner,
    vault: &Path,
) -> Result<Phase4Report, WizardError> {
    let asset = fetch::uv_asset_for_current_platform().ok_or(WizardError::PrereqPlatform)?;
    run_phase4_with(http, proc, vault, asset)
}

/// F4 with an explicit asset (test seam: the table pins the official
/// release, so fakes carry their fixture's own hash — T7 precedent).
pub fn run_phase4_with(
    http: &dyn HttpClient,
    proc: &dyn CommandRunner,
    vault: &Path,
    asset: &UvAsset,
) -> Result<Phase4Report, WizardError> {
    let outcome = install_uv(http, proc, vault, asset);
    if outcome.is_err() {
        compensate_phase4(vault);
    }
    outcome
}

/// F4 compensation: remove `bin/` (+ the download stage). Never touches
/// `models/`, `db/` or `config/`; missing dirs are a no-op.
pub fn compensate_phase4(vault: &Path) {
    let root = runtime_dir(vault);
    let _ = std::fs::remove_dir_all(root.join(UV_BIN_DIR));
    let _ = std::fs::remove_dir_all(root.join(UV_STAGE_DIR));
}

fn sync_project(
    proc: &dyn CommandRunner,
    uv: &Path,
    project: &Path,
    venv: &Path,
) -> Result<Phase5Report, WizardError> {
    let program = uv.to_str().ok_or(WizardError::Internal)?;
    let env = [UV_PROJECT_ENVIRONMENT];
    run_checked(
        proc,
        program,
        &["python", "install", UV_MANAGED_PYTHON],
        project,
        &env,
    )?;
    run_checked(proc, program, &["venv", VENV_DIR_NAME], project, &env)?;
    run_checked(proc, program, &["sync", "--frozen"], project, &env)?;
    let python = venv_python(venv);
    let interpreter = python.to_str().ok_or(WizardError::Internal)?;
    run_checked(proc, interpreter, &["-c", IMPORT_CHECK], project, &[])?;
    Ok(Phase5Report {
        venv: venv.to_path_buf(),
    })
}

/// F5: managed Python + venv + frozen sync + R6 import check, all with
/// `UV_PROJECT_ENVIRONMENT=venv` in the project dir. Failure compensates
/// `venv/` only — `bin/` (F4) stays (the total unwind is T14, not here).
pub fn run_phase5(proc: &dyn CommandRunner, vault: &Path) -> Result<Phase5Report, WizardError> {
    let uv = uv_binary_path(vault);
    if !uv.is_file() {
        return Err(WizardError::Internal);
    }
    let project = runtime_dir(vault);
    std::fs::create_dir_all(&project).map_err(|_| WizardError::PermissionDenied)?;
    let venv = project.join(VENV_DIR_NAME);
    std::fs::create_dir_all(&venv).map_err(|_| WizardError::PermissionDenied)?;
    let outcome = sync_project(proc, &uv, &project, &venv);
    if outcome.is_err() {
        compensate_phase5(vault);
    }
    outcome
}

/// F5 compensation: remove `venv/` only. `bin/` stays; `models/`, `db/` and
/// `config/` are never touched; missing dirs are a no-op.
pub fn compensate_phase5(vault: &Path) {
    let _ = std::fs::remove_dir_all(runtime_dir(vault).join(VENV_DIR_NAME));
}
