//! F1 (prereqs) + F2 (vault dir). No compensation: neither phase touches
//! user data, so there is nothing to roll back (todo T7).
//!
//! F3 (T8): merge the payload without overwrite, create `00-resources/`
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

use crate::adapters::archive::{extract_tar_gz, extract_zip};
use crate::adapters::fetch::{self, UvAsset};
use crate::domain::{VaultPath, WizardError};
use crate::ports::{
    CommandOutput, CommandRunner, HostProbe, HttpClient, MergeReport, PayloadSource, Ui,
};

use super::embedder_menu::config_path;
use super::phase7::index_meta_path;
use super::text::provider_is_none;

/// Minimum machine RAM in GiB (below aborts, exit 10 — never half-installs).
pub const MIN_RAM_GB: f64 = 8.0;
/// Minimum free disk in GiB at the probe path (below aborts, exit 11).
pub const MIN_DISK_FREE_GB: f64 = 4.0;
/// OS values (`std::env::consts::OS`) the wizard supports (else exit 12).
pub const SUPPORTED_OS: &[&str] = &["linux", "macos", "windows"];
/// F2 default when `--vault` is absent, resolved under the caller cwd.
pub const DEFAULT_VAULT_DIR: &str = "./tepochcalli-vault";
/// Canonical resources dir (exact case the flow indexes:
/// `citation.py: RESOURCES_DIR = "00-resources"`).
pub const RESOURCES_DIR: &str = "00-resources";
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
Escribe tus notas de investigación en `00-resources/`; el índice RAG las\n\
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
/// Delega en la única lookup del crate (adapters::host) para no duplicar la
/// regla `.exe`; el caller mantiene la firma histórica (prereqs + tests).
#[must_use]
pub fn tool_present_in(name: &str, dirs: &[PathBuf]) -> bool {
    crate::adapters::find_tool_in(name, dirs).is_some()
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

/// F1 with explicit seams (OS value + disk probe path + PATH dirs) for
/// `FakeHost` tests (S-4/L4-5): los dirs vienen del caller (`main` pasa la
/// lectura real de `PATH` vía `adapters::host::path_dirs`) — la misma lista
/// alimenta el chequeo de obsidian/opencode y, en el adapter, la sonda GPU
/// cross-OS (una única fuente del `PATH`).
pub fn check_prereqs_on(
    host: &dyn HostProbe,
    os: &str,
    disk_probe_path: &Path,
    path_dirs: &[PathBuf],
) -> Result<PrereqReport, WizardError> {
    if !is_supported_os(os) {
        return Err(WizardError::PrereqPlatform);
    }
    let ram_gb = check_ram(host)?;
    let disk_free_gb = check_disk(host, disk_probe_path)?;
    Ok(PrereqReport {
        os: os.to_string(),
        ram_gb,
        disk_free_gb,
        obsidian_found: tool_present_in(OBSIDIAN_TOOL, path_dirs),
        opencode_found: tool_present_in(OPENCODE_TOOL, path_dirs),
    })
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

/// Ensure `00-resources/` + the 2 placeholders (D22): pre-existing files
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
    // Idempotence (T14): a rerun writes nothing new, but the intent must
    // stay the cumulative record — union with the previous listing so a
    // second pass never blanks what the first pass wrote.
    if let Ok(previous) = std::fs::read_to_string(vault.join(INSTALL_INTENT_PATH)) {
        for line in previous.lines() {
            let trimmed = line.trim().to_string();
            if !trimmed.is_empty() && !lines.contains(&trimmed) {
                lines.push(trimmed);
            }
        }
    }
    lines.sort();
    let dir = vault.join(".tepochcalli");
    std::fs::create_dir_all(&dir).map_err(|_| WizardError::PermissionDenied)?;
    let mut body = lines.join("\n");
    body.push('\n');
    std::fs::write(vault.join(INSTALL_INTENT_PATH), body).map_err(|_| WizardError::PermissionDenied)
}

/// F3: merge the payload without overwrite, create `00-resources/` with
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
/// R6 import check: the tools subpackage must import from the fresh venv, and
/// `markitdown` must be importable (the flow extracts documents with it, T4/D53).
pub const IMPORT_CHECK: &str = "import markitdown, tepochcalli_mcp.tools.search";

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

/// `0o600` (usuario-privado) en unix; no-op donde no existen POSIX perms.
/// Los artefactos que llevan modelo/clave en claro (`tepochcalli.toml`,
/// sidecar meta y sus stages `.tmp`/`.swap`) no pueden heredar umask abierto
/// (`0644` expondría la clave a grupo/otros).
pub(super) fn set_user_private(path: &Path) -> Result<(), WizardError> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt as _;
        let mut perms = std::fs::metadata(path)
            .map_err(|_| WizardError::PermissionDenied)?
            .permissions();
        perms.set_mode(0o600);
        std::fs::set_permissions(path, perms).map_err(|_| WizardError::PermissionDenied)
    }
    #[cfg(not(unix))]
    {
        let _ = path;
        Ok(())
    }
}

/// Run `program` with explicit argv + cwd + env; any non-zero status is a
/// compensated phase failure (exit codes, never text, cross the boundary).
/// Plazo de los spawns de F5 (L3-6): `uv python install` / `venv` /
/// `sync --frozen` son red + despaíquete; 600 s los guarda de colgados
/// (kill typed `PhaseFailed`, un instalación que no deja de colgar).
const F5_SYNC_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(600);

fn run_checked(
    proc: &dyn CommandRunner,
    program: &str,
    args: &[&str],
    cwd: &Path,
    env: &[(&str, &str)],
    timeout: std::time::Duration,
) -> Result<CommandOutput, WizardError> {
    let out = proc.run_with_timeout(program, args, cwd, env, timeout)?;
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
    let out = proc.run_with_timeout(
        &program,
        &["--version"],
        vault,
        &[],
        std::time::Duration::from_secs(120),
    )?;
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
        F5_SYNC_TIMEOUT,
    )?;
    // El venv es estado derivado: `--clear` hace la reinstalación idempotente
    // (la compensación F5 ya lo borra en fallo).
    run_checked(
        proc,
        program,
        &["venv", "--clear", VENV_DIR_NAME],
        project,
        &env,
        F5_SYNC_TIMEOUT,
    )?;
    run_checked(
        proc,
        program,
        &["sync", "--frozen"],
        project,
        &env,
        F5_SYNC_TIMEOUT,
    )?;
    let python = venv_python(venv);
    let interpreter = python.to_str().ok_or(WizardError::Internal)?;
    run_checked(
        proc,
        interpreter,
        &["-c", IMPORT_CHECK],
        project,
        &[],
        F5_SYNC_TIMEOUT,
    )?;
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

// --- T14: install state, compensation of F3/F6/F7, offline guard ---

use crate::domain::Phase;

/// Marker listing completed phases (`F3`.. one per line); D21 resolves
/// `--resume` as artifacts + this marker, never a re-download.
pub const INSTALL_STATE_PATH: &str = ".tepochcalli/.install-state";
/// F8 entry the resume check looks for in `opencode.json`.
const MANAGED_RAG_KEY: &str = "tepochcalli-rag";

/// F1 compensation: no-op — F1 never writes (T7).
pub fn compensate_phase1(_vault: &Path) {}

/// F2 compensation: no-op — F2 reuses the dir, never wipes (T7).
pub fn compensate_phase2(_vault: &Path) {}

/// F3 compensation: remove exactly the files `.install-intent` lists, then
/// the intent file itself. Pre-existing user files were never listed, so
/// they survive; missing entries are a no-op.
pub fn compensate_phase3(vault: &Path) {
    let intent = vault.join(INSTALL_INTENT_PATH);
    let body = std::fs::read_to_string(&intent).unwrap_or_default();
    for line in body.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        let mut target = vault.to_path_buf();
        for part in trimmed.split('/') {
            if part.is_empty() || part == "." || part == ".." {
                continue;
            }
            target.push(part);
        }
        let _ = std::fs::remove_file(&target);
    }
    let _ = std::fs::remove_file(&intent);
}

/// Record `phase` as done in the marker (idempotent: no duplicate lines).
pub fn mark_phase_done(vault: &Path, phase: Phase) {
    let state = vault.join(INSTALL_STATE_PATH);
    if let Some(parent) = state.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    let mut done = completed_from_marker(vault);
    if !done.contains(&phase) {
        done.push(phase);
        done.sort_by_key(|phase: &Phase| phase.order_index());
        let mut body = String::new();
        for phase in &done {
            body.push_str(phase.name());
            body.push('\n');
        }
        let _ = std::fs::write(&state, body);
    }
}

/// Phases the marker file records (never fails: missing file ⇒ empty).
fn completed_from_marker(vault: &Path) -> Vec<Phase> {
    let body = std::fs::read_to_string(vault.join(INSTALL_STATE_PATH)).unwrap_or_default();
    let mut out = Vec::new();
    for line in body.lines() {
        let phase = match line.trim() {
            "F1" => Phase::F1,
            "F2" => Phase::F2,
            "F3" => Phase::F3,
            "F4" => Phase::F4,
            "F5" => Phase::F5,
            "F6" => Phase::F6,
            "F7" => Phase::F7,
            "F8" => Phase::F8,
            _ => continue,
        };
        if !out.contains(&phase) {
            out.push(phase);
        }
    }
    out
}

fn venv_python_candidates(vault: &Path) -> [PathBuf; 2] {
    let runtime = runtime_dir(vault);
    [
        runtime.join(VENV_DIR_NAME).join("bin/python"),
        runtime.join(VENV_DIR_NAME).join("Scripts/python.exe"),
    ]
}

/// Verdict of the artifact check for one phase: `Done` skips (el artefacto
/// corrobora), `Indeterminate` defers to the marker (no decidible), `Missing`
/// FUERZA el re-run (L3-3: lo borrado se re-instala; el marker solo no salta).
enum ArtifactProbe {
    Done,
    Indeterminate,
    Missing,
}

/// Artifact check per phase (D21 + L3-3). F1/F2 have no artifact
/// (Indeterminate: the marker mandates). F8 distinguishes "el fichero no
/// existe" (Missing) de un JSON ilegible (Indeterminate).
fn phase_artifact_probe(vault: &Path, phase: Phase) -> ArtifactProbe {
    match phase {
        Phase::F1 | Phase::F2 => ArtifactProbe::Indeterminate,
        Phase::F3 => {
            if vault.join(INSTALL_INTENT_PATH).is_file() {
                ArtifactProbe::Done
            } else {
                ArtifactProbe::Missing
            }
        }
        Phase::F4 => {
            let runtime = runtime_dir(vault);
            let uv_present = runtime.join(UV_BIN_DIR).join("uv").is_file()
                || runtime.join(UV_BIN_DIR).join("uv.exe").is_file();
            if uv_present {
                ArtifactProbe::Done
            } else {
                ArtifactProbe::Missing
            }
        }
        Phase::F5 => {
            if venv_python_candidates(vault)
                .iter()
                .any(|candidate| candidate.is_file())
            {
                ArtifactProbe::Done
            } else {
                ArtifactProbe::Missing
            }
        }
        Phase::F6 => {
            if config_path(vault).is_file() {
                ArtifactProbe::Done
            } else {
                ArtifactProbe::Missing
            }
        }
        Phase::F7 => {
            if index_meta_path(vault).is_file() {
                return ArtifactProbe::Done;
            }
            // Path 5 leaves no index by design: config `none` ⇒ F7 is done.
            match std::fs::read_to_string(config_path(vault)) {
                Ok(body) if provider_is_none(&body) => ArtifactProbe::Done,
                _ => ArtifactProbe::Missing,
            }
        }
        Phase::F8 => match std::fs::read_to_string(vault.join("opencode.json")) {
            Ok(body) if body.contains(MANAGED_RAG_KEY) => ArtifactProbe::Done,
            Ok(_) => ArtifactProbe::Missing,
            Err(err) if err.kind() == std::io::ErrorKind::NotFound => ArtifactProbe::Missing,
            Err(_) => ArtifactProbe::Indeterminate,
        },
    }
}

/// Marker ∪ artifacts, in execution order: what `--resume` may skip.
#[must_use]
pub fn completed_phases(vault: &Path) -> Vec<Phase> {
    let mut done = completed_from_marker(vault);
    for phase in Phase::all() {
        if !done.contains(&phase)
            && matches!(phase_artifact_probe(vault, phase), ArtifactProbe::Done)
        {
            done.push(phase);
        }
    }
    done.sort_by_key(|phase: &Phase| phase.order_index());
    done
}

/// `true` when `--resume` may skip `phase` (L3-3 artifact-first):
/// - F1/F2 solo marker (sin artefacto que chequear).
/// - F3..F8: el artefacto presente salta; si el chequeo es indeterminable
///   manda el marker; si el artefacto falta NO hay skip (el marker ya no
///   oculta una fase cuyo producto se borró).
#[must_use]
pub fn is_phase_done(vault: &Path, phase: Phase) -> bool {
    let marker = completed_from_marker(vault).contains(&phase);
    match phase_artifact_probe(vault, phase) {
        ArtifactProbe::Done => true,
        ArtifactProbe::Indeterminate => marker,
        ArtifactProbe::Missing => false,
    }
}

/// Offline pre-check, BEFORE the vault is touched: without a local payload
/// and a usable cache there is nothing to install from, so fail clean with
/// `E_OFFLINE_NO_CACHE` (exit 21) instead of half-writing the vault.
/// Offline pre-check (D7.3 + L3-5 OR-arm), BEFORE the vault is touched:
/// sin nada con que trabajar offline es un fallo limpio
/// `E_OFFLINE_NO_CACHE` (exit 21), nunca un half-write. Tres brazos válidos:
/// 1. payload local + cache de modelo (o ruta artificial skip);
/// 2. un resume cuyo payload ya está local (F3 por artefacto: la descarga
///    no va a repetirse). El brazo 2 cubre el re-entry de un vault instalado
///    curse configuration externa/caché fuera de models/.
pub fn guard_offline_before_touch(
    offline: bool,
    payload_local_ready: bool,
    cache_ready: bool,
    resume_payload_local: bool,
) -> Result<(), WizardError> {
    if offline && !(payload_local_ready && cache_ready) && !resume_payload_local {
        return Err(WizardError::OfflineNoCache);
    }
    Ok(())
}

/// `true` when `flag` points at an existing local payload tree
/// (`--payload <ruta>` for dev/tests; the T19 release asset is the online path).
#[must_use]
pub fn payload_local_ready(flag: Option<&str>) -> bool {
    match flag {
        Some(raw) if !raw.trim().is_empty() => Path::new(raw.trim()).is_dir(),
        _ => false,
    }
}
