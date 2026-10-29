//! F6b: 5-exit embedder menu + test-embed gate + atomic config (T11).
//!
//! Single-responsibility orchestrator over ports only (`Ui`, `HostProbe`,
//! `CommandRunner`, `HttpClient`) plus `domain` + `config` — never
//! `adapters/`. The menu order is [`EMBEDDER_PATHS`]; the gate contract
//! (`venv python -m tepochcalli_flow embed-check --model <id>` returning
//! `{ok,…}`) is implemented by the flow in T12 — here `FakeProc` stands in.

use std::path::{Path, PathBuf};

use crate::config::{badge_for, default_and_large, parse_presets, Preset};
use crate::domain::{Badge, EmbedderChoice, WizardError};
use crate::ports::{CommandRunner, HostProbe, HttpClient, Ui};

use super::installer::RUNTIME_DIR;
use super::text::{
    config_value, json_bool, json_raw, json_string, json_u32, json_u64, toml_escape,
};

/// Menu order = UI index contract (D7.1, ADR-007).
///
/// Index anchor: 0 = `PresetDefault` (MiniLM, preselected default), …,
/// 4 = `ConfigureLater`. [`crate::adapters::HeadlessUi::for_install`]
/// hardcodes this same contract (`skip_model` → 4, otherwise → 0), and
/// `tests/ui.rs` pins the 5-row shape — reordering rows here without
/// updating that constructor silently remaps `--skip-model` to a download
/// path. The `TtyUi` default highlight is index 0 of this array.
pub const EMBEDDER_PATHS: [EmbedderChoice; 5] = [
    EmbedderChoice::PresetDefault,
    EmbedderChoice::PresetLarge,
    EmbedderChoice::HuggingFaceId,
    EmbedderChoice::ExternalApi,
    EmbedderChoice::ConfigureLater,
];

/// Figure provenance shown on every menu row (D8.1: never present an
/// estimate as a promise).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Provenance {
    /// Sampled RSS peak during the gate test-embed on this host.
    Measured,
    /// Formula over HF API metadata (`params × 4 B × 1.3`).
    Estimated,
    /// Curated `presets.toml` fields (fallback when host/net fail).
    Declared,
}

impl Provenance {
    /// Spanish label rendered next to the figure it qualifies.
    #[must_use]
    pub fn label(self) -> &'static str {
        match self {
            Self::Measured => "medido",
            Self::Estimated => "estimado",
            Self::Declared => "declarado",
        }
    }
}

/// HF API base for pre-download estimates (D8.1).
const HF_API_BASE: &str = "https://huggingface.co/api/models/";
/// Config dir under the vault runtime dir (gitignored, never committed).
const CONFIG_DIR: &str = "config";
/// Config file name; written via temp + rename (never half-written).
const CONFIG_FILE: &str = "tepochcalli.toml";
/// Gate contract is flow-side (T12); the wizard only passes `--model`.
const GATE_MODULE: &str = "tepochcalli_flow";
const GATE_SUBCOMMAND: &str = "embed-check";
/// fp32 resident estimate: params × 4 B × 1.3 overhead, shown in MB.
const BYTES_PER_PARAM: f64 = 4.0;
const RESIDENT_OVERHEAD: f64 = 1.3;
const BYTES_PER_MB: f64 = 1_000_000.0;
/// Tags that mark an HF repo as an embedding model (D8.1 pre-filter).
const EMBEDDING_TAGS: &[&str] = &[
    "sentence-similarity",
    "feature-extraction",
    "sentence-transformers",
];

/// Borrowed collaborators for F6 (ports only — the orchestrator owns no I/O).
pub struct Phase6Deps<'a> {
    /// Menu, inputs, failure panels.
    pub ui: &'a dyn Ui,
    /// RAM/GPU facts for badges (D8.2).
    pub host: &'a dyn HostProbe,
    /// Runs the venv `embed-check` gate (T12 implements the CLI).
    pub proc: &'a dyn CommandRunner,
    /// HF API estimates for free ids (D8.1).
    pub http: &'a dyn HttpClient,
}

/// What F6 established: the `[embedding]` choice plus gate evidence.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Phase6Report {
    /// `"local"` | `"litellm"` | `"none"`.
    pub provider: String,
    /// HF id or external model name (`None` for path 5).
    pub model: Option<String>,
    /// Gate-measured dims (`None` for paths 4-5).
    pub dims: Option<u32>,
    /// Gate-measured RSS peak in bytes (`None` for paths 4-5).
    pub rss_peak_bytes: Option<u64>,
}

/// F6b: menu → gate → atomic config. Path 3 rejections (`E_MODEL_INVALID`
/// from the tag pre-filter or the gate) return to the menu without writing
/// anything; every other failure propagates typed (§5.4).
pub fn run_phase6(deps: &Phase6Deps<'_>, vault: &Path) -> Result<Phase6Report, WizardError> {
    let presets = parse_presets().map_err(|_| WizardError::Internal)?;
    let (default, large) = default_and_large(&presets).ok_or(WizardError::Internal)?;
    loop {
        let options = build_options(default, large, deps.host);
        let shown: Vec<&str> = options.iter().map(String::as_str).collect();
        let index = deps.ui.select("Embedding provider", &shown, 0)?;
        let choice = EMBEDDER_PATHS
            .get(index)
            .copied()
            .ok_or(WizardError::UserAborted)?;
        match choice {
            EmbedderChoice::PresetDefault => return finish_local(deps, vault, default),
            EmbedderChoice::PresetLarge => return finish_local(deps, vault, large),
            EmbedderChoice::HuggingFaceId => match finish_free_id(deps, vault) {
                Err(WizardError::ModelInvalid) => {
                    deps.ui.panel(
                        "E_MODEL_INVALID",
                        "Ese ID no es un modelo de embeddings; vuelve al menú sin escribir config.",
                    );
                    continue;
                }
                outcome => return outcome,
            },
            EmbedderChoice::ExternalApi => return finish_external(deps, vault),
            EmbedderChoice::ConfigureLater => return finish_later(vault),
        }
    }
}

pub(super) fn badge_label(badge: Badge) -> &'static str {
    match badge {
        Badge::Recommended => "recomendado",
        Badge::Viable => "viable",
        Badge::NotRecommended => "no recomendado",
        Badge::Unknown => "sin datos",
    }
}

pub(super) fn preset_option(preset: &Preset, host: &dyn HostProbe) -> String {
    let (badge, facts) = badge_for(preset, host);
    let gpu = if preset.gpu_recommended {
        "requerida"
    } else {
        "no requerida"
    };
    let provenance = Provenance::Declared.label();
    format!(
        "{} [{}] 💾 {}MB ({provenance}) · 🧠 {}MB ({provenance}) · 🎮 {gpu}",
        preset.name,
        badge_label(badge),
        facts.disk_mb,
        facts.ram_mb
    )
}

/// The 5 rows in [`EMBEDDER_PATHS`] order; preset rows carry badges +
/// declared figures, the free-id row is static (its estimate arrives after
/// the user types the id).
pub(super) fn build_options(default: &Preset, large: &Preset, host: &dyn HostProbe) -> Vec<String> {
    vec![
        preset_option(default, host),
        preset_option(large, host),
        "ID libre de HuggingFace — estima vía API + gate test-embed".to_string(),
        "API externa vía LiteLLM (clave solo en config gitignored)".to_string(),
        "Configurar después (sin índice, RAG degraded)".to_string(),
    ]
}

/// Re-ask until the answer is non-blank; an exhausted script surfaces
/// `UserAborted` (never a guess).
pub(super) fn ask_non_empty(ui: &dyn Ui, prompt: &str) -> Result<String, WizardError> {
    loop {
        let raw = ui.input(prompt, None)?;
        let value = raw.trim().to_string();
        if !value.is_empty() {
            return Ok(value);
        }
        ui.panel(
            "Falta un dato",
            "El valor no puede estar vacío; pulsa Ctrl-C para volver al menú.",
        );
    }
}

/// Header line of `[embedding]` configs this wizard writes — provenance is
/// caller-specific and stays byte-identical per artifact (trazabilidad):
/// install paths carry the F6 blurb, the swap path the D8.4 one. The whole
/// line is the parameter; the builders never invent its text.
const F6_LOCAL_HEADER: &str =
    "generado por `tepochcalli install` (F6) — re-entrada: `tepochcalli config embedder`";
const F6_EXTERNAL_HEADER: &str =
    "generado por `tepochcalli install` (F6) — gitignored, nunca commitear";
const F6_NONE_HEADER: &str =
    "generado por `tepochcalli install` (F6, salida 5) — re-entrada: `tepochcalli config embedder`";

pub(super) fn local_config(header: &str, model: &str) -> String {
    format!(
        "# {header}\n\
         [embedding]\n\
         provider = \"local\"\n\
         model = \"{}\"\n\
         device = \"cpu\"\n",
        toml_escape(model)
    )
}

pub(super) fn external_config(header: &str, model: &str, api_key: &str) -> String {
    format!(
        "# {header}\n\
         [embedding]\n\
         provider = \"litellm\"\n\
         model = \"{}\"\n\
         api_key = \"{}\"\n",
        toml_escape(model),
        toml_escape(api_key)
    )
}

pub(super) fn none_config(header: &str) -> String {
    format!(
        "# {header}\n\
         [embedding]\n\
         provider = \"none\"\n"
    )
}

/// Temp file + rename: a failed write never leaves half a config, and a
/// preexisting config stays byte-identical unless the gate passed.
fn write_config(vault: &Path, body: &str) -> Result<(), WizardError> {
    // shortcut: every fs failure maps to `PermissionDenied` (T7 convention;
    // T15 refines the panel).
    let dir = vault.join(RUNTIME_DIR).join(CONFIG_DIR);
    std::fs::create_dir_all(&dir).map_err(|_| WizardError::PermissionDenied)?;
    let tmp = dir.join(format!("{CONFIG_FILE}.tmp"));
    std::fs::write(&tmp, body).map_err(|_| WizardError::PermissionDenied)?;
    std::fs::rename(&tmp, dir.join(CONFIG_FILE)).map_err(|_| WizardError::PermissionDenied)?;
    Ok(())
}

/// Gate success payload (T12 programs the flow CLI against this shape).
#[derive(Debug)]
struct GateOk {
    model: String,
    dims: u32,
    rss_peak_bytes: u64,
}

/// Runs `venv python -m tepochcalli_flow embed-check --model <id>` (shared
/// spawn trunk). `ok:false` is the portero verdict (`E_MODEL_INVALID`); a
/// crashed/garbled gate is `PhaseFailed`.
fn run_gate(
    proc: &dyn CommandRunner,
    vault: &Path,
    model_id: &str,
    token: Option<&str>,
) -> Result<GateOk, WizardError> {
    let out = super::flow_cli::run_flow_cli(
        proc,
        vault,
        &["-m", GATE_MODULE, GATE_SUBCOMMAND, "--model", model_id],
        &[],
        token,
    )?;
    parse_gate(&out.stdout)
}

fn parse_gate(body: &str) -> Result<GateOk, WizardError> {
    match json_bool(body, "ok") {
        Some(true) => Ok(GateOk {
            model: json_string(body, "model").ok_or(WizardError::Internal)?,
            dims: json_u32(body, "dims").ok_or(WizardError::Internal)?,
            rss_peak_bytes: json_u64(body, "rss_peak_bytes").ok_or(WizardError::Internal)?,
        }),
        Some(false) => Err(WizardError::ModelInvalid),
        None => Err(WizardError::PhaseFailed),
    }
}

/// HF metadata reading for the free-id estimate (D8.1). `embedding_tag` is
/// `None` when the metadata carries no tag signal at all (the gate then
/// decides); `Some(false)` with a positive tag signal rejects before any
/// download. Missing fetch degrades to "sin dato", never an install failure.
pub(super) struct HfEstimate {
    pub(super) gated: bool,
    pub(super) embedding_tag: Option<bool>,
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
        ram_mb,
        disk_mb,
    }
}

fn estimate_row(estimate: &HfEstimate) -> String {
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

fn finish_local(
    deps: &Phase6Deps<'_>,
    vault: &Path,
    preset: &Preset,
) -> Result<Phase6Report, WizardError> {
    let gate = run_gate(deps.proc, vault, &preset.hf_id, None)?;
    deps.ui.panel(
        "Embedding OK",
        &format!(
            "modelo {} · dims {} · RSS pico {}MB ({})",
            gate.model,
            gate.dims,
            gate.rss_peak_bytes / BYTES_PER_MB as u64,
            Provenance::Measured.label()
        ),
    );
    write_config(vault, &local_config(F6_LOCAL_HEADER, &preset.hf_id))?;
    Ok(Phase6Report {
        provider: "local".to_string(),
        model: Some(preset.hf_id.clone()),
        dims: Some(gate.dims),
        rss_peak_bytes: Some(gate.rss_peak_bytes),
    })
}

fn finish_free_id(deps: &Phase6Deps<'_>, vault: &Path) -> Result<Phase6Report, WizardError> {
    let id = ask_non_empty(deps.ui, "HuggingFace model id")?;
    let estimate = match deps.http.get(&format!("{HF_API_BASE}{id}")) {
        Ok(body) => Some(parse_hf_metadata(&body)),
        Err(_) => None,
    };
    let mut token: Option<String> = None;
    if let Some(estimate) = &estimate {
        if estimate.embedding_tag == Some(false) {
            return Err(WizardError::ModelInvalid);
        }
        let row = estimate_row(estimate);
        deps.ui.panel("Estimación HuggingFace", &row);
        if estimate.gated {
            deps.ui.panel(
                "Modelo gated",
                "La API marca este repo como gated: la descarga pedirá HF_TOKEN.",
            );
            let raw = deps
                .ui
                .input("HF_TOKEN (opcional, solo para esta descarga)", None)?;
            let value = raw.trim().to_string();
            token = if value.is_empty() { None } else { Some(value) };
        }
    } else {
        deps.ui.panel(
            "Sin estimación",
            "La API de HF no responde (sin red): se intenta la descarga directa.",
        );
    }
    let gate = run_gate(deps.proc, vault, &id, token.as_deref())?;
    deps.ui.panel(
        "Embedding OK",
        &format!(
            "modelo {} · dims {} · RSS pico {}MB ({})",
            gate.model,
            gate.dims,
            gate.rss_peak_bytes / BYTES_PER_MB as u64,
            Provenance::Measured.label()
        ),
    );
    write_config(vault, &local_config(F6_LOCAL_HEADER, &id))?;
    Ok(Phase6Report {
        provider: "local".to_string(),
        model: Some(id),
        dims: Some(gate.dims),
        rss_peak_bytes: Some(gate.rss_peak_bytes),
    })
}

fn finish_external(deps: &Phase6Deps<'_>, vault: &Path) -> Result<Phase6Report, WizardError> {
    let model = ask_non_empty(
        deps.ui,
        "Modelo externo (p. ej. openai/text-embedding-3-small)",
    )?;
    // shortcut: no provider-wide key check exists; a mistyped key surfaces as
    // E_API_AUTH at first embed (spec-embeddings edge table). Re-ask loop is
    // the retry-without-continuing the spec asks for.
    let api_key = ask_non_empty(deps.ui, "API key (solo se guarda en config gitignored)")?;
    write_config(
        vault,
        &external_config(F6_EXTERNAL_HEADER, &model, &api_key),
    )?;
    Ok(Phase6Report {
        provider: "litellm".to_string(),
        model: Some(model),
        dims: None,
        rss_peak_bytes: None,
    })
}

fn finish_later(vault: &Path) -> Result<Phase6Report, WizardError> {
    write_config(vault, &none_config(F6_NONE_HEADER))?;
    Ok(Phase6Report::configure_later())
}

impl Phase6Report {
    /// Path-5 report (degraded, no embedder): the exact value `finish_later`
    /// writes, reused by the T14 F6 compensation and `--resume` reconstruction.
    #[must_use]
    pub fn configure_later() -> Self {
        Self {
            provider: "none".to_string(),
            model: None,
            dims: None,
            rss_peak_bytes: None,
        }
    }
}

/// Vault-absolute config path (single source for the T14 artifact check).
#[must_use]
pub fn config_path(vault: &Path) -> PathBuf {
    vault.join(RUNTIME_DIR).join(CONFIG_DIR).join(CONFIG_FILE)
}

/// Rebuild the F6 report from an existing config (for `--resume`: skip the
/// menu, keep the recorded provider/model). `None` when no config exists.
#[must_use]
pub fn read_completed_report(vault: &Path) -> Option<Phase6Report> {
    let body = std::fs::read_to_string(config_path(vault)).ok()?;
    let provider = config_value(&body, "provider")?;
    if provider == "none" {
        return Some(Phase6Report::configure_later());
    }
    let model = config_value(&body, "model");
    Some(Phase6Report {
        provider,
        model,
        dims: None,
        rss_peak_bytes: None,
    })
}

/// F6 compensation (T14): fall back to salida 5 — a COMPLETE degraded
/// install (`provider = "none"`), never a failed one. Only the config is
/// written; `models/`, `db/` and user files are untouched.
pub fn compensate_phase6(vault: &Path) -> Result<(), WizardError> {
    write_config(vault, &none_config(F6_NONE_HEADER))
}

#[cfg(test)]
mod tests {
    use super::{
        badge_label, estimate_row, external_config, local_config, none_config, parse_gate,
        parse_hf_metadata, EMBEDDER_PATHS, F6_EXTERNAL_HEADER, F6_LOCAL_HEADER, F6_NONE_HEADER,
    };
    use crate::domain::{Badge, EmbedderChoice};

    /// Fuente única del orden del menú (tras retirar `EmbedderChoice::all()`):
    /// el array ES el contrato D7.1; un reorden silencioso rompe esta igualdad.
    #[test]
    fn menu_order_is_the_adr_numbering() {
        assert_eq!(
            EMBEDDER_PATHS,
            [
                EmbedderChoice::PresetDefault,
                EmbedderChoice::PresetLarge,
                EmbedderChoice::HuggingFaceId,
                EmbedderChoice::ExternalApi,
                EmbedderChoice::ConfigureLater,
            ]
        );
    }

    #[test]
    fn config_bodies_combine_the_caller_header_byte_identically() {
        // Trazabilidad del artefacto: la cabecera es del caller, el cuerpo lo
        // ponen los generadores. Comillas/barras van en medio del escape.
        let body = local_config(F6_LOCAL_HEADER, "BAAI/bge-m3");
        assert_eq!(
            body,
            "# generado por `tepochcalli install` (F6) — re-entrada: `tepochcalli config embedder`\n\
             [embedding]\n\
             provider = \"local\"\n\
             model = \"BAAI/bge-m3\"\n\
             device = \"cpu\"\n"
        );
        assert_eq!(
            external_config(F6_EXTERNAL_HEADER, "m\"a\\b", "sk-1"),
            "# generado por `tepochcalli install` (F6) — gitignored, nunca commitear\n\
             [embedding]\n\
             provider = \"litellm\"\n\
             model = \"m\\\"a\\\\b\"\n\
             api_key = \"sk-1\"\n"
        );
        assert_eq!(
            none_config(F6_NONE_HEADER),
            "# generado por `tepochcalli install` (F6, salida 5) — re-entrada: `tepochcalli config embedder`\n\
             [embedding]\n\
             provider = \"none\"\n"
        );
    }

    #[test]
    fn badge_label_covers_every_variant() {
        assert_eq!(badge_label(Badge::Recommended), "recomendado");
        assert_eq!(badge_label(Badge::Viable), "viable");
        assert_eq!(badge_label(Badge::NotRecommended), "no recomendado");
        assert_eq!(badge_label(Badge::Unknown), "sin datos");
    }

    #[test]
    fn gate_ok_parses_model_dims_and_rss() {
        match parse_gate("{\"ok\":true,\"model\":\"m\",\"dims\":384,\"rss_peak_bytes\":650000000}")
        {
            Ok(gate) => {
                assert_eq!(gate.model, "m");
                assert_eq!(gate.dims, 384);
                assert_eq!(gate.rss_peak_bytes, 650_000_000);
            }
            Err(err) => panic!("valid gate must parse, got: {err:?}"),
        }
    }

    #[test]
    fn gate_false_is_model_invalid_and_garbage_is_phase_failed() {
        match parse_gate("{\"ok\":false,\"code\":\"E_MODEL_INVALID\"}") {
            Err(crate::domain::WizardError::ModelInvalid) => {}
            other => panic!("portero must reject, got: {other:?}"),
        }
        match parse_gate("not json at all") {
            Err(crate::domain::WizardError::PhaseFailed) => {}
            other => panic!("garbled gate must fail the phase, got: {other:?}"),
        }
    }

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
