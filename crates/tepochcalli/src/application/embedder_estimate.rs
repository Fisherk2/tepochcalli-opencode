//! Estimación pre-descarga vía API de HF (D8.1).
//!
//! El wizard NUNCA presenta una estimación como promesa: `Provenance` califica
//! la cifra y el gate sigue siendo la verdad de campo. Una API caída degrada a
//! «sin dato», jamás a un fallo de instalación.

use super::embedder_menu::Provenance;
use super::text::{json_raw, json_string};

/// HF API base for pre-download estimates (D8.1).
pub(super) const HF_API_BASE: &str = "https://huggingface.co/api/models/";
/// fp32 resident estimate: params × 4 B × 1.3 overhead, shown in MB.
const BYTES_PER_PARAM: f64 = 4.0;
const RESIDENT_OVERHEAD: f64 = 1.3;
pub(super) const BYTES_PER_MB: f64 = 1_000_000.0;
/// Tags that mark an HF repo as an embedding model (D8.1 pre-filter).
const EMBEDDING_TAGS: &[&str] = &[
    "sentence-similarity",
    "feature-extraction",
    "sentence-transformers",
];

/// HF metadata reading for the free-id estimate (D8.1). `embedding_tag` is
/// `None` when the metadata carries no tag signal at all (the gate then
/// decides); `Some(false)` with a positive tag signal rejects before any
/// download. Missing fetch degrades to "sin dato", never an install failure.
pub(super) struct HfEstimate {
    pub(super) gated: bool,
    pub(super) embedding_tag: Option<bool>,
    /// SHA de la revisión que sirve HF para este repo: el pin que F6 pasa al
    /// gate y escribe en `[embedding].revision` (D59).
    pub(super) sha: Option<String>,
    ram_mb: Option<u64>,
    disk_mb: Option<u64>,
}

fn after<'a>(text: &'a str, marker: &str) -> Option<&'a str> {
    text.find(marker).map(|i| &text[i + marker.len()..])
}

fn json_number_after(text: &str, marker: &str) -> Option<f64> {
    let value = after(text, marker)?
        .trim_start()
        .strip_prefix(':')?
        .trim_start();
    let digits: String = value
        .chars()
        .take_while(|c| {
            c.is_ascii_digit() || *c == '.' || *c == 'e' || *c == 'E' || *c == '+' || *c == '-'
        })
        .collect();
    digits.parse().ok()
}

pub(super) fn parse_hf_metadata(body: &[u8]) -> HfEstimate {
    // shortcut: substring match on the tag block; the gate stays the ground
    // truth, so a future HF shape change only costs an extra download.
    let text = String::from_utf8_lossy(body);
    let gated = !matches!(json_raw(&text, "gated"), None | Some("false"));
    let embedding_tag = if EMBEDDING_TAGS.iter().any(|tag| text.contains(*tag)) {
        Some(true)
    } else if text.contains("\"tags\"") || text.contains("\"pipeline_tag\"") {
        Some(false)
    } else {
        None
    };
    let ram_mb = after(&text, "\"parameters\"")
        .and_then(|params| json_number_after(params, "\"total\""))
        .map(|params| (params * BYTES_PER_PARAM * RESIDENT_OVERHEAD / BYTES_PER_MB) as u64);
    let disk_mb = after(&text, "\"siblings\"").and_then(|siblings| {
        let array = siblings.split(']').next().unwrap_or_default();
        let mut total = 0u64;
        let mut found = false;
        for chunk in array.split("\"size\"").skip(1) {
            let digits: String = chunk
                .trim_start()
                .strip_prefix(':')
                .map(str::trim_start)
                .unwrap_or_default()
                .chars()
                .take_while(|c| c.is_ascii_digit())
                .collect();
            if let Ok(size) = digits.parse::<u64>() {
                total += size;
                found = true;
            }
        }
        found.then_some((total as f64 / BYTES_PER_MB) as u64)
    });
    HfEstimate {
        gated,
        embedding_tag,
        sha: json_string(&text, "sha"),
        ram_mb,
        disk_mb,
    }
}

pub(super) fn estimate_row(estimate: &HfEstimate) -> String {
    let known = estimate.ram_mb.is_some() || estimate.disk_mb.is_some();
    let provenance = if known {
        Provenance::Estimated.label()
    } else {
        "sin dato"
    };
    let disk = estimate
        .disk_mb
        .map(|mb| format!("{mb}MB"))
        .unwrap_or_else(|| "sin dato".to_string());
    let ram = estimate
        .ram_mb
        .map(|mb| format!("{mb}MB"))
        .unwrap_or_else(|| "sin dato".to_string());
    format!("💾 {disk} ({provenance}) · 🧠 {ram} ({provenance}) · 🎮 sin dato")
}

#[cfg(test)]
mod tests {
    use super::{estimate_row, parse_hf_metadata};

    #[test]
    fn hf_metadata_yields_estimated_ram_and_gated_flag() {
        let estimate = parse_hf_metadata(
            br#"{"gated":false,"pipeline_tag":"sentence-similarity","tags":["sentence-transformers"],
                 "safetensors":{"parameters":{"total":117600000}},
                 "siblings":[{"rfilename":"model.safetensors","size":470000000}]}"#,
        );
        assert!(!estimate.gated);
        assert_eq!(estimate.embedding_tag, Some(true));
        assert_eq!(estimate.ram_mb, Some(611));
        assert_eq!(estimate.disk_mb, Some(470));
        let row = estimate_row(&estimate);
        assert!(row.contains("estimado"), "row: {row}");
        assert!(row.contains("611"), "row: {row}");
    }

    #[test]
    fn hf_metadata_detects_gated_and_non_embedding_tags() {
        let gated = parse_hf_metadata(br#"{"gated":true,"tags":["text-generation"]}"#);
        assert!(gated.gated);
        assert_eq!(gated.embedding_tag, Some(false));
        let tagless = parse_hf_metadata(br#"{"safetensors":{}}"#);
        assert_eq!(tagless.embedding_tag, None);
        assert_eq!(tagless.ram_mb, None);
    }

    /// HF real devuelve `"auto"`/`"manual"`, no solo `true`: cualquier valor
    /// distinto de `false` significa repo gated (el swap unificado leía el
    /// literal `"gated":true` y no ofrecía token en esos ids).
    #[test]
    fn hf_metadata_marks_auto_gated_repos() {
        assert!(parse_hf_metadata(br#"{"gated":"auto","tags":["text-generation"]}"#).gated);
        assert!(parse_hf_metadata(br#"{"gated":"manual","tags":["text-generation"]}"#).gated);
    }
}
