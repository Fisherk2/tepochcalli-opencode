//! Embedder menu (D7.1): the 5 paths, hardware badges, resource facts.

/// The 5 menu exits from ADR-007 §D7.1, in menu order.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EmbedderChoice {
    /// Path 1: `paraphrase-multilingual-MiniLM-L12-v2` (preselected default).
    PresetDefault,
    /// Path 2: larger preset (`BAAI/bge-m3` / `all-MiniLM-L6-v2`).
    PresetLarge,
    /// Path 3: free HuggingFace model id (gate test-embed decides).
    HuggingFaceId,
    /// Path 4: external API via LiteLLM (key lives in gitignored config).
    ExternalApi,
    /// Path 5: configure later — degraded install, no initial index.
    ConfigureLater,
}

impl EmbedderChoice {
    /// All 5 paths in menu order (D7.1 fixes exactly these).
    #[must_use]
    pub fn all() -> [Self; 5] {
        [
            Self::PresetDefault,
            Self::PresetLarge,
            Self::HuggingFaceId,
            Self::ExternalApi,
            Self::ConfigureLater,
        ]
    }

    /// Preselected default (path 1).
    #[must_use]
    pub fn default_path() -> Self {
        Self::PresetDefault
    }
}

impl Default for EmbedderChoice {
    fn default() -> Self {
        Self::default_path()
    }
}

/// Hardware badge per menu row (D8.2; computed in T10, type frozen here).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Badge {
    /// Comfortable margin (≥50% headroom over declared `rec_ram_gb`).
    Recommended,
    /// Fits but tight.
    Viable,
    /// Exceeds RAM or needs a missing GPU — still selectable (D8.3).
    NotRecommended,
    /// Host probe failed; showing declared numbers without a badge.
    Unknown,
}

/// Numbers shown before selecting a row (D8.1); every figure carries its
/// provenance (`medido` | `estimado` | `declarado`) at render time (T11).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ResourceFacts {
    /// Disk footprint in MB.
    pub disk_mb: u64,
    /// RAM needed in MB.
    pub ram_mb: u64,
    /// Whether this path wants a GPU.
    pub gpu: bool,
}
