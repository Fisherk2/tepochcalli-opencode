//! F6b: 5-exit embedder menu + test-embed gate + atomic config (T11).
//!
//! Single-responsibility orchestrator over ports only (`Ui`, `HostProbe`,
//! `CommandRunner`, `HttpClient`) plus `domain` + `config` — never
//! `adapters/`. The menu order is [`EMBEDDER_PATHS`]; the gate contract
//! (`venv python -m tepochcalli_flow embed-check --model <id>` returning
//! `{ok,…}`) is implemented by the flow in T12 — here `FakeProc` stands in.

use std::path::Path;

use crate::config::{badge_for, parse_presets, Preset};
use crate::domain::{Badge, EmbedderChoice, WizardError};
use crate::ports::{CommandRunner, HostProbe, HttpClient, Ui};

use super::installer::{venv_python, RUNTIME_DIR, VENV_DIR_NAME};

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
/// Model cache dir the gate sandboxes via `HF_HOME` (spec-embeddings).
const MODELS_DIR: &str = "models";
/// Gate probe phrase is flow-side (T12); the wizard only passes `--model`.
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
    /// Menu path taken.
    pub choice: EmbedderChoice,
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
    let default = presets
        .iter()
        .find(|preset| preset.recommended_flag)
        .ok_or(WizardError::Internal)?;
    let large = presets
        .iter()
        .find(|preset| !preset.recommended_flag)
        .ok_or(WizardError::Internal)?;
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

fn badge_label(badge: Badge) -> &'static str {
    match badge {
        Badge::Recommended => "recomendado",
        Badge::Viable => "viable",
        Badge::NotRecommended => "no recomendado",
        Badge::Unknown => "sin datos",
    }
}

fn preset_option(preset: &Preset, host: &dyn HostProbe) -> String {
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
fn build_options(default: &Preset, large: &Preset, host: &dyn HostProbe) -> Vec<String> {
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
fn ask_non_empty(ui: &dyn Ui, prompt: &str) -> Result<String, WizardError> {
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

fn toml_escape(raw: &str) -> String {
    raw.replace('\\', "\\\\").replace('"', "\\\"")
}

fn local_config(model: &str) -> String {
    format!(
        "# generado por `tepochcalli install` (F6) — re-entrada: `tepochcalli config embedder`\n\
         [embedding]\n\
         provider = \"local\"\n\
         model = \"{}\"\n\
         device = \"cpu\"\n",
        toml_escape(model)
    )
}

fn external_config(model: &str, api_key: &str) -> String {
    format!(
        "# generado por `tepochcalli install` (F6) — gitignored, nunca commitear\n\
         [embedding]\n\
         provider = \"litellm\"\n\
         model = \"{}\"\n\
         api_key = \"{}\"\n",
        toml_escape(model),
        toml_escape(api_key)
    )
}

fn none_config() -> String {
    "# generado por `tepochcalli install` (F6, salida 5) — re-entrada: `tepochcalli config embedder`\n\
     [embedding]\n\
     provider = \"none\"\n"
        .to_string()
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

/// Runs `venv python -m tepochcalli_flow embed-check --model <id>` with the
/// model cache sandboxed under the vault. `ok:false` is the portero verdict
/// (`E_MODEL_INVALID`); a crashed/garbled gate is `PhaseFailed`.
fn run_gate(
    proc: &dyn CommandRunner,
    vault: &Path,
    model_id: &str,
    token: Option<&str>,
) -> Result<GateOk, WizardError> {
    let venv = vault.join(RUNTIME_DIR).join(VENV_DIR_NAME);
    let python = venv_python(&venv);
    let models = venv
        .parent()
        .map(|runtime| runtime.join(MODELS_DIR).to_string_lossy().into_owned())
        .unwrap_or_default();
    let program = python.to_str().ok_or(WizardError::Internal)?.to_string();
    let mut env: Vec<(&str, &str)> = vec![
        ("HF_HOME", &models),
        ("SENTENCE_TRANSFORMERS_HOME", &models),
    ];
    if let Some(secret) = token {
        // shortcut: the token travels only in the child env (T11g redacts all
        // UI/log surfaces; a generic env-scrubber is T15 scope).
        env.push(("HF_TOKEN", secret));
    }
    let out = proc.run(
        &program,
        &["-m", GATE_MODULE, GATE_SUBCOMMAND, "--model", model_id],
        vault,
        &env,
    )?;
    if out.status != 0 {
        return Err(WizardError::PhaseFailed);
    }
    parse_gate(&out.stdout)
}

fn json_raw<'a>(body: &'a str, key: &str) -> Option<&'a str> {
    let needle = format!("\"{key}\"");
    let after_key = body.find(&needle).map(|i| &body[i + needle.len()..])?;
    let value = after_key.trim_start().strip_prefix(':')?.trim_start();
    if let Some(quoted) = value.strip_prefix('"') {
        let mut end = None;
        let mut escaped = false;
        for (i, c) in quoted.char_indices() {
            if escaped {
                escaped = false;
            } else if c == '\\' {
                escaped = true;
            } else if c == '"' {
                end = Some(i);
                break;
            }
        }
        return end.map(|i| quoted[..i].trim());
    }
    Some(value.split([',', '}']).next().unwrap_or_default().trim())
}

fn json_bool(body: &str, key: &str) -> Option<bool> {
    match json_raw(body, key)? {
        "true" => Some(true),
        "false" => Some(false),
        _ => None,
    }
}

fn json_u64(body: &str, key: &str) -> Option<u64> {
    json_raw(body, key)?.parse().ok()
}

fn json_u32(body: &str, key: &str) -> Option<u32> {
    json_raw(body, key)?.parse().ok()
}

fn json_string(body: &str, key: &str) -> Option<String> {
    json_raw(body, key).map(|raw| raw.replace("\\\"", "\"").replace("\\\\", "\\"))
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
struct HfEstimate {
    gated: bool,
    embedding_tag: Option<bool>,
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

fn parse_hf_metadata(body: &[u8]) -> HfEstimate {
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
    write_config(vault, &local_config(&preset.hf_id))?;
    Ok(Phase6Report {
        choice: if preset.recommended_flag {
            EmbedderChoice::PresetDefault
        } else {
            EmbedderChoice::PresetLarge
        },
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
    write_config(vault, &local_config(&id))?;
    Ok(Phase6Report {
        choice: EmbedderChoice::HuggingFaceId,
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
    write_config(vault, &external_config(&model, &api_key))?;
    Ok(Phase6Report {
        choice: EmbedderChoice::ExternalApi,
        provider: "litellm".to_string(),
        model: Some(model),
        dims: None,
        rss_peak_bytes: None,
    })
}

fn finish_later(vault: &Path) -> Result<Phase6Report, WizardError> {
    write_config(vault, &none_config())?;
    Ok(Phase6Report {
        choice: EmbedderChoice::ConfigureLater,
        provider: "none".to_string(),
        model: None,
        dims: None,
        rss_peak_bytes: None,
    })
}

#[cfg(test)]
mod tests {
    use super::{
        estimate_row, json_bool, json_string, json_u32, json_u64, parse_gate, parse_hf_metadata,
    };

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

    #[test]
    fn json_helpers_read_quoted_and_bare_values() {
        let body = "{\"name\":\"a\\\"b\",\"n\":42,\"ok\":true}";
        assert_eq!(json_string(body, "name").as_deref(), Some("a\"b"));
        assert_eq!(json_u64(body, "n"), Some(42));
        assert_eq!(json_u32(body, "n"), Some(42));
        assert_eq!(json_bool(body, "ok"), Some(true));
        assert_eq!(json_bool(body, "missing"), None);
    }
}
