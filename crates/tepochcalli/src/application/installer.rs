//! F1 (prereqs) + F2 (vault dir). No compensation: neither phase touches
//! user data, so there is nothing to roll back (todo T7).
//!
//! F3 (T8): merge the payload without overwrite, create `00-Resources/`
//! with 2 placeholders, write `.install-intent` (basis of F3 compensation
//! in T14). Depends on `domain` + `ports` only — never on `adapters/`.

use std::path::{Path, PathBuf};

use crate::domain::{VaultPath, WizardError};
use crate::ports::{HostProbe, MergeReport, PayloadSource, Ui};

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
