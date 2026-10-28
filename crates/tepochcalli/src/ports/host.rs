//! `HostProbe`: RAM / disk / GPU facts for the badge table (D8.1/D8.2).

use std::path::Path;

/// A GPU the probe could see (`nvidia-smi` / `rocm-smi` in T5).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GpuInfo {
    /// Human-readable GPU name.
    pub name: String,
}

/// Hardware facts. Every method returns `None` when the probe fails —
/// the menu then falls back to declared preset numbers **without badge**
/// (D8.2) and installation never crashes on a probe error.
pub trait HostProbe {
    /// Total RAM in GiB, or `None` if the probe failed.
    fn ram_total_gb(&self) -> Option<f64>;
    /// Currently available RAM in GiB, or `None` if the probe failed.
    fn ram_available_gb(&self) -> Option<f64>;
    /// Free disk space at `path` in GiB, or `None` if the probe failed.
    fn disk_free_gb(&self, path: &Path) -> Option<f64>;
    /// Detected GPU, or `None` when absent **or** the probe failed.
    fn gpu(&self) -> Option<GpuInfo>;
}
