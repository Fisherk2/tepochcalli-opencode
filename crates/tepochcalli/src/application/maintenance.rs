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
use super::installer::{venv_python, RUNTIME_DIR, VENV_DIR_NAME};
use super::phase7::index_meta_path;

/// Flow CLI module invoked through the venv interpreter (D24, T12 contract).
const FLOW_MODULE: &str = "tepochcalli_flow";
/// `embed-check` measures the dims of a freshly configured model (T11 gate).
const GATE_SUBCOMMAND: &str = "embed-check";
/// `refresh` rebuilds the index and prints its `RefreshReport` (T12 contract).
const REFRESH_SUBCOMMAND: &str = "refresh";
/// Model cache dir, sandboxed under the vault via `HF_HOME` (same dir the
/// F6 gate and F7 pass: the download happens once, every pass reuses it).
const MODELS_DIR: &str = "models";

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
            if raw_config.contains("provider = \"none\"") {
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
                json_u32(&raw_meta, "dims")
                    .map(|dims| dims.to_string())
                    .unwrap_or_else(|| "(sin dato)".to_string()),
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
    write_index_meta(vault, &model, dims)?;
    ui.panel(
        "Reindex completo",
        &format!(
            "modelo {model} · dims {} · scanned {} · indexed {} ({} ms){}",
            dims.map(|dims| dims.to_string())
                .unwrap_or_else(|| "(sin dato)".to_string()),
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
struct GateOk {
    dims: u32,
}

/// `venv python -m tepochcalli_flow embed-check --model <id>` with the model
/// cache sandboxed under the vault. `ok:false` is the portero verdict
/// (`E_MODEL_INVALID`); a crashed/garbled gate is `PhaseFailed`.
fn run_gate(proc: &dyn CommandRunner, vault: &Path, model: &str) -> Result<GateOk, WizardError> {
    let python = venv_python(&vault.join(RUNTIME_DIR).join(VENV_DIR_NAME));
    let models = vault
        .join(RUNTIME_DIR)
        .join(MODELS_DIR)
        .to_string_lossy()
        .into_owned();
    let program = python.to_str().ok_or(WizardError::Internal)?.to_string();
    let out = proc.run(
        &program,
        &["-m", FLOW_MODULE, GATE_SUBCOMMAND, "--model", model],
        vault,
        &[
            ("HF_HOME", &models),
            ("SENTENCE_TRANSFORMERS_HOME", &models),
        ],
    )?;
    if out.status != 0 {
        return Err(WizardError::PhaseFailed);
    }
    parse_gate(&out.stdout)
}

/// Replacement `refresh` (T12 contract). `ok:false` maps to `ModelInvalid`,
/// matching the F7 portero parity; anything else unparseable is `PhaseFailed`.
struct Refreshed {
    scanned: u64,
    indexed: u64,
    skipped: u64,
    elapsed_ms: u64,
}

fn run_refresh(proc: &dyn CommandRunner, vault: &Path) -> Result<Refreshed, WizardError> {
    let python = venv_python(&vault.join(RUNTIME_DIR).join(VENV_DIR_NAME));
    let models = vault
        .join(RUNTIME_DIR)
        .join(MODELS_DIR)
        .to_string_lossy()
        .into_owned();
    let program = python.to_str().ok_or(WizardError::Internal)?.to_string();
    let out = proc.run(
        &program,
        &["-m", FLOW_MODULE, REFRESH_SUBCOMMAND],
        vault,
        &[
            ("HF_HOME", &models),
            ("SENTENCE_TRANSFORMERS_HOME", &models),
        ],
    )?;
    if out.status != 0 {
        return Err(WizardError::PhaseFailed);
    }
    parse_refresh(&out.stdout)
}

/// Temp file + rename: a failed write never leaves half a sidecar, and a
/// failed reindex never corrupts the metadata the previous pass wrote.
fn write_index_meta(vault: &Path, model: &str, dims: Option<u32>) -> Result<(), WizardError> {
    // shortcut: every fs failure maps to `PermissionDenied` (T7 convention;
    // T15 refines the panel).
    let dir = vault.join(RUNTIME_DIR).join("db");
    std::fs::create_dir_all(&dir).map_err(|_| WizardError::PermissionDenied)?;
    let dims_json = dims
        .map(|width| width.to_string())
        .unwrap_or_else(|| "null".to_string());
    let body = format!(
        "{{\"model\":\"{}\",\"dims\":{dims_json}}}\n",
        json_escape(model)
    );
    let tmp = dir.join("index-meta.json.tmp");
    std::fs::write(&tmp, body).map_err(|_| WizardError::PermissionDenied)?;
    std::fs::rename(&tmp, dir.join("index-meta.json"))
        .map_err(|_| WizardError::PermissionDenied)?;
    Ok(())
}

/// Minimal `key = "value"` reader for the wizard-written config (the file is
/// always produced by the F6 writer, never hand-edited TOML).
fn config_value(body: &str, key: &str) -> Option<String> {
    body.lines().find_map(|line| {
        let rest = line
            .trim()
            .strip_prefix(key)?
            .trim_start()
            .strip_prefix('=')?;
        let value = rest.trim().strip_prefix('"')?.strip_suffix('"')?;
        Some(value.to_string())
    })
}

/// Minimal JSON readers for the one-line flow contracts (same hand-rolled
/// shape as the F6 gate and F7 refresh parsers).
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

fn json_escape(raw: &str) -> String {
    raw.replace('\\', "\\\\").replace('"', "\\\"")
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
