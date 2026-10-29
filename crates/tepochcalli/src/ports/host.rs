//! `HostProbe`: RAM / disk / GPU facts for the badge table (D8.1/D8.2).

use std::path::Path;

/// A GPU the probe could see (`nvidia-smi` / `rocm-smi` in T5).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GpuInfo {
    /// Human-readable GPU name.
    pub name: String,
}

/// Snapshot de los facts RAM/GPU capturados UNA VEZ por corrida (L5-1):
/// `System::new_all()` + la sonda GPU son la parte cara del menú D8; el
/// snapshot deja de re-probar por fila — `badge_for` consume facts, el
/// probe se toca una vez (el disco se sonda aparte, es por-ruta).
#[derive(Debug, Clone, PartialEq)]
pub struct HostFacts {
    /// Total RAM in GiB (`None` = probe failed).
    pub ram_total_gb: Option<f64>,
    /// Available RAM in GiB (`None` = probe failed).
    pub ram_available_gb: Option<f64>,
    /// Detected GPU (`None` = absent or probe failed).
    pub gpu: Option<GpuInfo>,
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

    /// Snapshot RAM/GPU de una vez (L5-1). Default: llama a los tres métodos
    /// — una implementación puede memoizar internamente (el adapter real),
    /// los fakes cuentan probes aquí.
    fn snapshot(&self) -> HostFacts {
        HostFacts {
            ram_total_gb: self.ram_total_gb(),
            ram_available_gb: self.ram_available_gb(),
            gpu: self.gpu(),
        }
    }
}
