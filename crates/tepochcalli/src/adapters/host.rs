//! Real [`crate::ports::HostProbe`] over `sysinfo` plus a `PATH` GPU lookup.
//!
//! Never crashes the install (AC-e): every method returns `None` when the
//! probe fails, and the menu falls back to declared preset numbers (D8.2).
//! GPU absence is `None`, never an error (AC-d).

use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::Duration;

use sysinfo::{Disks, System};

use crate::ports::{GpuInfo, HostFacts, HostProbe};

/// Bytes per GiB; the port contract reports GiB floats.
const BYTES_PER_GIB: f64 = 1024.0 * 1024.0 * 1024.0;
/// Short leash for the GPU tools; a hung `*-smi` must not stall install.
const GPU_TIMEOUT: Duration = Duration::from_secs(5);
/// GPU tools in preference order, with args that print one name per line.
const GPU_TOOLS: &[(&str, &[&str])] = &[
    ("nvidia-smi", &["--query-gpu=name", "--format=csv,noheader"]),
    ("rocm-smi", &["--showproductname"]),
];

/// `sysinfo` reports 0 on failure; 0 bytes of RAM means "probe failed".
fn nonzero_gib(bytes: u64) -> Option<f64> {
    if bytes == 0 {
        None
    } else {
        Some(bytes as f64 / BYTES_PER_GIB)
    }
}

/// First `name` (or `name.exe`, for Windows layouts browsed from anywhere)
/// found under `dirs`, else `None`. Una sola lookup con una sola regla .exe:
/// `tool_present_in` y la sonda de GPU comparten esta función.
#[must_use]
pub fn find_tool_in(name: &str, dirs: &[PathBuf]) -> Option<PathBuf> {
    dirs.iter().find_map(|dir| {
        let bare = dir.join(name);
        let exe = dir.join(format!("{name}.exe"));
        if bare.is_file() {
            Some(bare)
        } else if exe.is_file() {
            Some(exe)
        } else {
            None
        }
    })
}

/// Los dirs reales del `PATH` del proceso (S-4/L4-5): única fuente para el
/// chequeo de prereqs (obsidian/opencode desde `main`) y para la sonda GPU
/// cross-OS (`gpu()` del probe).
#[must_use]
pub fn path_dirs() -> Vec<PathBuf> {
    std::env::var_os("PATH")
        .map(|paths| std::env::split_paths(&paths).collect())
        .unwrap_or_default()
}

/// Run `program` and take the first non-empty stdout line; `None` on
/// spawn failure, non-zero exit, non-UTF8 garbage, or `timeout`. A timed-out
/// child is orphaned (it exits on its own; `*-smi` tools are short-lived).
fn run_with_timeout(program: PathBuf, args: &[&str], timeout: Duration) -> Option<String> {
    let owned: Vec<String> = args.iter().map(ToString::to_string).collect();
    let (tx, rx) = std::sync::mpsc::channel();
    std::thread::spawn(move || {
        let out = Command::new(&program).args(&owned).output().ok();
        let _ = tx.send(out);
    });
    let out = rx.recv_timeout(timeout).ok()??;
    if !out.status.success() {
        return None;
    }
    String::from_utf8_lossy(&out.stdout)
        .lines()
        .map(str::trim)
        .find(|line| !line.is_empty())
        .map(str::to_string)
}

/// [`HostProbe`] over `sysinfo` (RAM/disk) and `nvidia-smi`/`rocm-smi` (GPU).
#[derive(Debug, Default, Clone, Copy)]
pub struct SysHostProbe;

impl HostProbe for SysHostProbe {
    fn ram_total_gb(&self) -> Option<f64> {
        Self::cached_facts().ram_total_gb
    }

    fn ram_available_gb(&self) -> Option<f64> {
        Self::cached_facts().ram_available_gb
    }

    fn disk_free_gb(&self, path: &Path) -> Option<f64> {
        // Canonicalize for the prefix match; fall back to the raw path.
        let probe = std::fs::canonicalize(path).unwrap_or_else(|_| path.to_path_buf());
        let disks = Disks::new_with_refreshed_list();
        let disk = disks
            .list()
            .iter()
            .filter(|d| probe.starts_with(d.mount_point()))
            .max_by_key(|d| d.mount_point().as_os_str().len())?;
        nonzero_gib(disk.available_space())
    }

    fn gpu(&self) -> Option<GpuInfo> {
        Self::cached_facts().gpu
    }

    /// Una sola `System::new_all()` por corrida (L5-1): el snapshot cachea
    /// RAM y GPU — la sonda GPU cross-OS viaja dentro del mismo snapshot.
    fn snapshot(&self) -> HostFacts {
        Self::cached_facts()
    }
}

impl SysHostProbe {
    /// Snapshot memoizado del proceso (los menús llaman 4+ veces).
    fn cached_facts() -> HostFacts {
        let cached = CACHE.lock().ok().and_then(|guard| guard.clone());
        match cached {
            Some(facts) => facts,
            None => {
                let mut sys = System::new_all();
                sys.refresh_memory();
                let facts = HostFacts {
                    ram_total_gb: nonzero_gib(sys.total_memory()),
                    ram_available_gb: nonzero_gib(sys.available_memory()),
                    gpu: gpu_probe(),
                };
                if let Ok(mut guard) = CACHE.lock() {
                    *guard = Some(facts.clone());
                }
                facts
            }
        }
    }
}

static CACHE: std::sync::Mutex<Option<HostFacts>> = std::sync::Mutex::new(None);

/// Sonda GPU cross-OS via `find_tool_in` (misma fuente de `PATH`, L4-5);
/// nunca crashea la instalación: fallo/ausencia ⇒ `None`.
fn gpu_probe() -> Option<GpuInfo> {
    let dirs = path_dirs();
    for (tool, args) in GPU_TOOLS {
        if let Some(program) = find_tool_in(tool, &dirs) {
            if let Some(name) = run_with_timeout(program, args, GPU_TIMEOUT) {
                return Some(GpuInfo { name });
            }
        }
    }
    None
}
