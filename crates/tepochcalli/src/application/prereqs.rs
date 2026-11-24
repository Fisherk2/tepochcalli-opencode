//! F1 (prereqs) + F2 (vault dir). No compensation: neither phase touches
//! user data, so there is nothing to roll back (todo T7).
//!
//! Re-exported through `application::installer` — the historical public
//! paths (`application::installer::check_prereqs_on`, …) do not change.

use std::path::{Path, PathBuf};

use crate::domain::{VaultPath, WizardError};
use crate::ports::{HostProbe, Ui};

/// Minimum machine RAM in GiB (below aborts, exit 10 — never half-installs).
pub const MIN_RAM_GB: f64 = 8.0;
/// Minimum free disk in GiB at the probe path (below aborts, exit 11).
pub const MIN_DISK_FREE_GB: f64 = 4.0;
/// OS values (`std::env::consts::OS`) the wizard supports (else exit 12).
pub const SUPPORTED_OS: &[&str] = &["linux", "macos", "windows"];
/// F2 default when `--vault` is absent, resolved under the caller cwd.
pub const DEFAULT_VAULT_DIR: &str = "./tepochcalli-vault";
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
    // `--vault` como enlace (x -> /) escribiría el probe fuera del vault: se
    // rechaza. Un ancestro enlazado (p. ej. /tmp) sí es legítimo.
    if path.exists() && std::fs::symlink_metadata(path).is_ok_and(|m| m.file_type().is_symlink()) {
        return Err(WizardError::PermissionDenied);
    }
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
