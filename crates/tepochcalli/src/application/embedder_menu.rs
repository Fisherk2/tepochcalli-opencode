//! F6b: 5-exit embedder menu + test-embed gate + materialización verificada
//! del snapshot + atomic config (T11, T6/D59).
//!
//! Single-responsibility orchestrator over ports only (`Ui`, `HostProbe`,
//! `CommandRunner`, `HttpClient`) plus `domain` + `config` — never
//! `adapters/`. The menu order is [`EMBEDDER_PATHS`]; the gate contract
//! (`venv python -m tepochcalli_flow embed-check --model <id> --revision
//! <sha>` returning `{ok,…}`) is implemented by the flow in T12 — aquí
//! `FakeProc` stands in. El wizard NO descarga modelos (D25): invoca el CLI
//! del flow y luego **verifica** que `<models>/<slug>@<sha>/` existe y no
//! está vacío antes de escribir la config.
//!
//! Este módulo es el orquestador y el modelo de datos; las cuatro
//! responsabilidades que antes vivían aquí siguen al lado, por tema:
//! `embedder_gate` (gate + snapshot), `embedder_estimate` (estimación HF),
//! `embedder_options` (filas del menú e inputs) y `embedder_config`
//! (artefactos `[embedding]` y escritura atómica). Los `pub use` de abajo
//! conservan los caminos que ya consumían `swap`, `installer` y `main`.

use std::path::Path;

use crate::config::{default_and_large, parse_presets, Preset};
use crate::domain::{CancelToken, EmbedderChoice, WizardError};
use crate::ports::{CommandRunner, HostFacts, HostProbe, HttpClient, Ui};

use super::embedder_config::{F6_EXTERNAL_HEADER, F6_LOCAL_HEADER, F6_NONE_HEADER};
use super::embedder_estimate::{estimate_row, BYTES_PER_MB, HF_API_BASE};
use super::embedder_gate::{run_gate_cancellable, verify_materialized};
use super::text::is_plausible_hf_id;

pub use super::embedder_config::{
    compensate_phase6, config_path, litellm_config_present, read_completed_report,
};
pub(super) use super::embedder_config::{external_config, local_config, none_config, write_config};
pub(super) use super::embedder_estimate::parse_hf_metadata;
pub(super) use super::embedder_options::{
    ask_non_empty, ask_secret_non_empty, build_options, choose_device,
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
    /// Cancelación de la descarga en curso (R-offline-2; T16 la dispara).
    /// Clon del token de la corrida.
    pub cancel: CancelToken,
}

/// What F6 established: the `[embedding]` choice plus gate evidence.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Phase6Report {
    /// `"local"` | `"litellm"` | `"none"`.
    pub provider: String,
    /// HF id or external model name (`None` for path 5).
    pub model: Option<String>,
    /// SHA de la revisión pineada (`[embedding].revision`, D59): es la que el
    /// gate materializó y la que el read path necesita para resolver el MISMO
    /// snapshot. `None` cuando no se conoce (la API de HF no respondió) o no
    /// aplica (paths 4-5).
    pub revision: Option<String>,
    /// Dispositivo escrito en `[embedding].device` (H9, ADR-015): `None` para
    /// los paths 4-5, que no llevan embedder local.
    pub device: Option<String>,
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
        // El snapshot va fuera del loop (L5-1): un re-enter del menú por id
        // inválido NO re-prueba RAM/GPU por fila — un probe real por corrida.
        let facts = deps.host.snapshot();
        let options = build_options(default, large, &facts);
        let shown: Vec<&str> = options.iter().map(String::as_str).collect();
        let index = deps.ui.select("Embedding provider", &shown, 0)?;
        let choice = EMBEDDER_PATHS
            .get(index)
            .copied()
            .ok_or(WizardError::UserAborted)?;
        match choice {
            EmbedderChoice::PresetDefault => return finish_local(deps, vault, default, &facts),
            EmbedderChoice::PresetLarge => return finish_local(deps, vault, large, &facts),
            EmbedderChoice::HuggingFaceId => match finish_free_id(deps, vault, &facts) {
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

fn finish_local(
    deps: &Phase6Deps<'_>,
    vault: &Path,
    preset: &Preset,
    facts: &HostFacts,
) -> Result<Phase6Report, WizardError> {
    let revision = Some(preset.revision.as_str());
    let device = choose_device(deps.ui, facts, &preset.device)?;
    let gate = run_gate_cancellable(
        deps.ui,
        deps.proc,
        vault,
        &preset.hf_id,
        revision,
        None,
        &deps.cancel,
    )?;
    verify_materialized(vault, &preset.hf_id, revision)?;
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
    write_config(
        vault,
        &local_config(F6_LOCAL_HEADER, &preset.hf_id, revision, &device),
    )?;
    Ok(Phase6Report {
        provider: "local".to_string(),
        model: Some(preset.hf_id.clone()),
        revision: Some(preset.revision.clone()),
        device: Some(device),
        dims: Some(gate.dims),
        rss_peak_bytes: Some(gate.rss_peak_bytes),
    })
}

fn finish_free_id(
    deps: &Phase6Deps<'_>,
    vault: &Path,
    facts: &HostFacts,
) -> Result<Phase6Report, WizardError> {
    let id = ask_non_empty(deps.ui, "HuggingFace model id")?;
    if !is_plausible_hf_id(&id) {
        return Err(WizardError::ModelInvalid);
    }
    let estimate = match deps.http.get(&format!("{HF_API_BASE}{id}")) {
        Ok(body) => Some(parse_hf_metadata(&body)),
        Err(_) => None,
    };
    // La revisión pineada es el `sha` del repo (provenance del snapshot); sin
    // API es `None` y el CLI hereda el default del vault (como el read path).
    let revision = estimate.as_ref().and_then(|estimate| estimate.sha.clone());
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
                .input_secret("HF_TOKEN (opcional, solo para esta descarga)")?;
            let value = raw.trim().to_string();
            token = if value.is_empty() { None } else { Some(value) };
        }
    } else {
        deps.ui.panel(
            "Sin estimación",
            "La API de HF no responde (sin red): se intenta la descarga directa.",
        );
    }
    // El dispositivo se pregunta tras validar el id y antes de descargar: un
    // `cuda` elegido en un host sin GPU falla al cargar el modelo, no al
    // configurar (D8.3).
    let device = choose_device(deps.ui, facts, "cpu")?;
    let gate = run_gate_cancellable(
        deps.ui,
        deps.proc,
        vault,
        &id,
        revision.as_deref(),
        token.as_deref(),
        &deps.cancel,
    )?;
    verify_materialized(vault, &id, revision.as_deref())?;
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
    write_config(
        vault,
        &local_config(F6_LOCAL_HEADER, &id, revision.as_deref(), &device),
    )?;
    Ok(Phase6Report {
        provider: "local".to_string(),
        model: Some(id),
        revision,
        device: Some(device),
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
    let api_key = ask_secret_non_empty(deps.ui, "API key (solo se guarda en config gitignored)")?;
    write_config(
        vault,
        &external_config(F6_EXTERNAL_HEADER, &model, &api_key),
    )?;
    Ok(Phase6Report {
        provider: "litellm".to_string(),
        model: Some(model),
        revision: None,
        device: None,
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
            revision: None,
            device: None,
            dims: None,
            rss_peak_bytes: None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::EMBEDDER_PATHS;
    use crate::domain::EmbedderChoice;

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
}
