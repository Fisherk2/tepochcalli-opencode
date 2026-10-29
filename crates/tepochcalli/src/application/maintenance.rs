//! T17: `reindex --confirm` (destructive full re-index) + `uninstall`.
//!
//! Single-responsibility orchestrators over ports only — never `adapters/`.
//! `reindex` rebuilds the live index through the venv `refresh` CLI (the same
//! T12 contract F7 uses) and rewrites `{model, dims}` atomically; it never
//! clears the index first — the replacement pass completes before the sidecar
//! goes live, so the old index stays servable until the new one is proven. A
//! config/index model drift surfaces as an `E_MODEL_MISMATCH` panel, never a
//! silent rebuild. `uninstall` removes only `.tepochcalli/` and is idempotent.

use std::path::Path;

use crate::domain::WizardError;
use crate::ports::{CommandRunner, Ui};

use super::embedder_menu::config_path;
use super::flow_cli::run_flow_cli;
use super::installer::{venv_python, RUNTIME_DIR, VENV_DIR_NAME};
use super::phase7::{index_meta_path, write_index_meta};
use super::text::{
    config_value, json_bool, json_string, json_u32, json_u64, or_fallback, provider_is_none,
};

/// Flow CLI module invoked through the venv interpreter (D24, T12 contract).
const FLOW_MODULE: &str = "tepochcalli_flow";
/// `embed-check` measures the dims of a freshly configured model (T11 gate).
const GATE_SUBCOMMAND: &str = "embed-check";
/// `refresh` rebuilds the index and prints its `RefreshReport` (T12 contract).
const REFRESH_SUBCOMMAND: &str = "refresh";

/// What the confirmed rebuild established: the counts plus the embedder the
/// fresh sidecar now describes.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReindexReport {
    /// HF id or external model name the rebuilt index belongs to.
    pub model: String,
    /// Its vector width (`None` for the external-API path, F7 parity).
    pub dims: Option<u32>,
    /// Entries visited by the replacement pass.
    pub scanned: u64,
    /// Files whose chunks were (re)written by this pass.
    pub indexed: u64,
    /// Visited entries that needed no rewrite.
    pub skipped: u64,
    /// Pass duration in milliseconds, measured inside the flow CLI.
    pub elapsed_ms: u64,
    /// `true` when the pass cured a config/index drift (`E_MODEL_MISMATCH`).
    pub mismatch: bool,
}

/// What the removal established: whether there was a runtime to remove.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct UninstallReport {
    /// `true` when `.tepochcalli/` existed and is now gone; `false` is the
    /// idempotent no-op (nothing that was there could be lost).
    pub removed: bool,
}

/// Confirmed rebuild: mismatch check → gate (only when the dims are unknown)
/// → live `refresh` → atomic sidecar rewrite. Any failure leaves the old
/// sidecar byte-identical; the index itself is only ever touched by the
/// replacement `refresh`, never cleared beforehand.
pub fn run_reindex(
    proc: &dyn CommandRunner,
    ui: &dyn Ui,
    vault: &Path,
) -> Result<ReindexReport, WizardError> {
    let raw_config = std::fs::read_to_string(config_path(vault)).unwrap_or_default();
    let (provider, model) = match (
        config_value(&raw_config, "provider"),
        config_value(&raw_config, "model"),
    ) {
        (Some(provider), Some(model)) if provider != "none" => (provider, model),
        _ => {
            if provider_is_none(&raw_config) {
                ui.panel(
                    "Sin embedder",
                    "Este vault no tiene embedder configurado (instalación degraded: provider = \"none\"). \
                     Ejecuta `tepochcalli config embedder` para elegir uno antes de reindexar; \
                     sin modelo no hay nada que reconstruir.",
                );
            } else {
                ui.panel(
                    "Sin instalación",
                    "Este vault no tiene `.tepochcalli/config/tepochcalli.toml` (nunca se instaló). \
                     Ejecuta `tepochcalli install` primero; reindexar la nada no reconstruye nada.",
                );
            }
            return Err(WizardError::PhaseFailed);
        }
    };
    let raw_meta = std::fs::read_to_string(index_meta_path(vault)).unwrap_or_default();
    let meta_model = json_string(&raw_meta, "model");
    // Drift manual (spec-embeddings §edge table): la config cambió sin
    // reindexar. Se explica con su código y el rebuild lo cura.
    let mismatch = meta_model.as_deref().is_some_and(|meta| meta != model);
    if mismatch {
        ui.panel(
            "E_MODEL_MISMATCH",
            &format!(
                "La config pide `{model}` pero el índice se construyó con `{}` \
                 (dims {}). LanceDB no mezcla dimensiones: el re-index completo lo \
                 reconstruye con el modelo actual.",
                meta_model.as_deref().unwrap_or("(desconocido)"),
                or_fallback(json_u32(&raw_meta, "dims")),
            ),
        );
    }
    // shortcut: a vault without the venv interpreter means F5 never ran;
    // same class as F5's missing-`uv` check (typed, never a spawn attempt).
    let python = venv_python(&vault.join(RUNTIME_DIR).join(VENV_DIR_NAME));
    if !python.is_file() {
        return Err(WizardError::Internal);
    }
    // Dims conocidas del sidecar cuando el modelo no cambió: el gate se
    // omite (no re-descarga lo ya medido). En otro caso el gate las mide.
    let dims = match (
        meta_model.as_deref() == Some(model.as_str()),
        json_u32(&raw_meta, "dims"),
    ) {
        (true, Some(dims)) => Some(dims),
        _ if provider == "local" => Some(run_gate(proc, vault, &model)?.dims),
        _ => None,
    };
    let refreshed = run_refresh(proc, vault)?;
    write_index_meta(vault, Some(&model), dims)?;
    ui.panel(
        "Reindex completo",
        &format!(
            "modelo {model} · dims {} · scanned {} · indexed {} ({} ms){}",
            or_fallback(dims),
            refreshed.scanned,
            refreshed.indexed,
            refreshed.elapsed_ms,
            if mismatch {
                " · E_MODEL_MISMATCH resuelto: el índice ya coincide con la config"
            } else {
                ""
            },
        ),
    );
    Ok(ReindexReport {
        model,
        dims,
        scanned: refreshed.scanned,
        indexed: refreshed.indexed,
        skipped: refreshed.skipped,
        elapsed_ms: refreshed.elapsed_ms,
        mismatch,
    })
}

/// Scope mínimo: solo `.tepochcalli/` (runtime: `venv/`, `bin/`, `db/`,
/// `models/`, `config/`). Notas, payload, `opencode.json`, `00-Resources/` y
/// `.obsidian/` sobreviven por construcción: nunca se enumeran, nunca se
/// tocan. Ausente ⇒ no-op `Ok` (idempotencia, T14).
pub fn run_uninstall(vault: &Path) -> Result<UninstallReport, WizardError> {
    match std::fs::remove_dir_all(vault.join(RUNTIME_DIR)) {
        Ok(()) => Ok(UninstallReport { removed: true }),
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => {
            Ok(UninstallReport { removed: false })
        }
        // shortcut: every fs failure maps to `PermissionDenied` (T7 convention;
        // T15 refines the panel).
        Err(_) => Err(WizardError::PermissionDenied),
    }
}

/// Gate success payload (T11 programs the flow CLI against this shape):
/// only the measured dims matter here — the model is the configured one.
#[derive(Debug, PartialEq, Eq)]
struct GateOk {
    dims: u32,
}

/// `venv python -m tepochcalli_flow embed-check --model <id>` (shared spawn
/// trunk). `ok:false` is the portero verdict (`E_MODEL_INVALID`); a
/// crashed/garbled gate is `PhaseFailed`.
fn run_gate(proc: &dyn CommandRunner, vault: &Path, model: &str) -> Result<GateOk, WizardError> {
    let out = run_flow_cli(
        proc,
        vault,
        &["-m", FLOW_MODULE, GATE_SUBCOMMAND, "--model", model],
        &[],
        None,
        super::flow_cli::GATE_TIMEOUT,
    )?;
    parse_gate(&out.stdout)
}

/// Replacement `refresh` (T12 contract). `ok:false` maps to `ModelInvalid`,
/// matching the F7 portero parity; anything else unparseable is `PhaseFailed`.
#[derive(Debug, PartialEq, Eq)]
struct Refreshed {
    scanned: u64,
    indexed: u64,
    skipped: u64,
    elapsed_ms: u64,
}

fn run_refresh(proc: &dyn CommandRunner, vault: &Path) -> Result<Refreshed, WizardError> {
    let out = run_flow_cli(
        proc,
        vault,
        &["-m", FLOW_MODULE, REFRESH_SUBCOMMAND],
        &[],
        None,
        super::flow_cli::REFRESH_TIMEOUT,
    )?;
    parse_refresh(&out.stdout)
}

fn parse_gate(body: &str) -> Result<GateOk, WizardError> {
    match json_bool(body, "ok") {
        Some(true) => Ok(GateOk {
            dims: json_u32(body, "dims").ok_or(WizardError::Internal)?,
        }),
        Some(false) => Err(WizardError::ModelInvalid),
        None => Err(WizardError::PhaseFailed),
    }
}

fn parse_refresh(body: &str) -> Result<Refreshed, WizardError> {
    if json_bool(body, "ok") == Some(false) {
        return Err(WizardError::ModelInvalid);
    }
    match (
        json_u64(body, "scanned"),
        json_u64(body, "indexed"),
        json_u64(body, "skipped"),
        json_u64(body, "elapsed_ms"),
    ) {
        (Some(scanned), Some(indexed), Some(skipped), Some(elapsed_ms)) => Ok(Refreshed {
            scanned,
            indexed,
            skipped,
            elapsed_ms,
        }),
        _ => Err(WizardError::PhaseFailed),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn config_value_returns_some_empty_for_an_empty_value() {
        // Divergencia deliberada con `failure::config_value` (que devuelve
        // `None` via filter): aquí el valor es el modelo/provider, no un
        // secreto a borrar.
        assert_eq!(config_value("model = \"\"\n", "model").as_deref(), Some(""));
    }

    #[test]
    fn parse_gate_returns_measured_dims_only() {
        match parse_gate("{\"ok\":true,\"model\":\"m\",\"dims\":384,\"rss_peak_bytes\":1}") {
            Ok(gate) => assert_eq!(gate.dims, 384),
            Err(err) => panic!("gate válido debe parsear, got: {err:?}"),
        }
        assert_eq!(
            parse_gate("{\"ok\":false,\"code\":\"E_MODEL_INVALID\"}"),
            Err(WizardError::ModelInvalid)
        );
        assert_eq!(parse_gate("garabato"), Err(WizardError::PhaseFailed));
        assert_eq!(
            parse_gate("{\"ok\":true,\"model\":\"m\"}"),
            Err(WizardError::Internal),
            "sin dims no hay medida que reportar"
        );
    }

    #[test]
    fn parse_refresh_keeps_all_four_counters() {
        match parse_refresh(
            "{\"ok\":true,\"scanned\":10,\"indexed\":3,\"skipped\":7,\"elapsed_ms\":120}",
        ) {
            Ok(refreshed) => {
                assert_eq!(refreshed.scanned, 10);
                assert_eq!(refreshed.indexed, 3);
                assert_eq!(refreshed.skipped, 7);
                assert_eq!(refreshed.elapsed_ms, 120);
            }
            Err(err) => panic!("refresh válido debe parsear, got: {err:?}"),
        }
    }

    #[test]
    fn parse_refresh_types_refusals_and_garbage() {
        assert_eq!(
            parse_refresh("{\"ok\":false,\"code\":\"E_MODEL_INVALID\"}"),
            Err(WizardError::ModelInvalid)
        );
        assert_eq!(parse_refresh("garabato"), Err(WizardError::PhaseFailed));
        assert_eq!(
            parse_refresh("{\"ok\":true,\"scanned\":1}"),
            Err(WizardError::PhaseFailed),
            "un contador ausente no se inventa"
        );
    }
}
