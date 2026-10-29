//! F7 initial index (T12): run the flow CLI `refresh` and persist index metadata.
//!
//! Single-responsibility orchestrator over the `CommandRunner` port only —
//! never `adapters/`. Path 5 (`provider == "none"`, degraded install)
//! short-circuits before any process spawn: no index dir is created and no
//! metadata is written. Every other path runs `venv python -m
//! tepochcalli_flow refresh` (cwd = vault, model cache sandboxed under the
//! vault) and records `{model, dims}` in `.tepochcalli/db/index-meta.json`
//! (atomically, temp + rename) for the T17 mismatch guard to read back.
//!
//! The CLI JSON shapes (`{scanned, indexed, skipped, elapsed_ms}`,
//! gate-style `{ok: false, …}`) are parsed with the same hand-rolled minimal
//! readers the F6 gate uses; a refusal maps to the same typed
//! `ModelInvalid`, anything else unparseable to `PhaseFailed` — never an
//! `Ok` report built on garbage.

use std::path::{Path, PathBuf};

use crate::domain::WizardError;
use crate::ports::CommandRunner;

use super::embedder_menu::Phase6Report;
use super::installer::{venv_python, RUNTIME_DIR, VENV_DIR_NAME};

/// Flow CLI module invoked through the venv interpreter (D24).
const REFRESH_MODULE: &str = "tepochcalli_flow";
/// `refresh` indexes the vault and prints its `RefreshReport` as one JSON line.
const REFRESH_SUBCOMMAND: &str = "refresh";
/// Model cache dir, sandboxed under the vault via `HF_HOME` (same dir the
/// F6 gate passes: the download happens once, the index reuses it).
const MODELS_DIR: &str = "models";
/// Index dir holding LanceDB plus the metadata sidecar.
const DB_DIR: &str = "db";
/// Sidecar with the embedder that produced the index (T17 reads it back).
const INDEX_META_FILE: &str = "index-meta.json";

/// What F7 established: the refresh counts plus the embedder they belong to.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Phase7Report {
    /// Entries visited by the pass (placeholders + anything else indexed).
    pub scanned: u64,
    /// Files whose chunks were (re)written by this pass.
    pub indexed: u64,
    /// Visited entries that needed no rewrite.
    pub skipped: u64,
    /// Pass duration in milliseconds, measured inside the flow CLI.
    pub elapsed_ms: u64,
    /// Embedder that produced the index (`None` for the path-5 skip).
    pub model: Option<String>,
    /// Its vector width (`None` for path 5 and the external-API path).
    pub dims: Option<u32>,
}

/// F7: refresh the index, then persist `{model, dims}` next to it.
pub fn run_phase7(
    proc: &dyn CommandRunner,
    vault: &Path,
    phase6: &Phase6Report,
) -> Result<Phase7Report, WizardError> {
    // Path 5 short-circuits before any spawn: degraded install, no index.
    if phase6.provider == "none" {
        return Ok(Phase7Report {
            scanned: 0,
            indexed: 0,
            skipped: 0,
            elapsed_ms: 0,
            model: None,
            dims: None,
        });
    }
    // shortcut: a vault without the venv interpreter means F5 never ran;
    // same class as F5's missing-`uv` check (typed, never a spawn attempt).
    let python = venv_python(&vault.join(RUNTIME_DIR).join(VENV_DIR_NAME));
    if !python.is_file() {
        return Err(WizardError::Internal);
    }
    let models = vault
        .join(RUNTIME_DIR)
        .join(MODELS_DIR)
        .to_string_lossy()
        .into_owned();
    let program = python.to_str().ok_or(WizardError::Internal)?.to_string();
    let out = proc.run(
        &program,
        &["-m", REFRESH_MODULE, REFRESH_SUBCOMMAND],
        vault,
        &[
            ("HF_HOME", &models),
            ("SENTENCE_TRANSFORMERS_HOME", &models),
        ],
    )?;
    if out.status != 0 {
        return Err(WizardError::PhaseFailed);
    }
    match parse_refresh(&out.stdout)? {
        RefreshParsed::Refused => Err(WizardError::ModelInvalid),
        RefreshParsed::Ok {
            scanned,
            indexed,
            skipped,
            elapsed_ms,
        } => {
            write_index_meta(vault, phase6.model.as_deref(), phase6.dims)?;
            Ok(Phase7Report {
                scanned,
                indexed,
                skipped,
                elapsed_ms,
                model: phase6.model.clone(),
                dims: phase6.dims,
            })
        }
    }
}

#[derive(Debug, PartialEq, Eq)]
enum RefreshParsed {
    Ok {
        scanned: u64,
        indexed: u64,
        skipped: u64,
        elapsed_ms: u64,
    },
    /// Gate-style `{ok: false, …}`: the same portero verdict F6 maps to
    /// `ModelInvalid` (parity with the T11 `embed-check` fixture).
    Refused,
}

/// Minimal JSON readers for the one-line CLI contract (same hand-rolled
/// shape as the F6 gate parser: flat object, no nesting expected).
fn json_raw<'a>(body: &'a str, key: &str) -> Option<&'a str> {
    let needle = format!("\"{key}\"");
    let after_key = body.find(&needle).map(|i| &body[i + needle.len()..])?;
    let value = after_key.trim_start().strip_prefix(':')?.trim_start();
    if let Some(quoted) = value.strip_prefix('"') {
        // No trim inside the quotes: that whitespace is part of the value.
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
        return end.map(|i| &quoted[..i]);
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

fn parse_refresh(body: &str) -> Result<RefreshParsed, WizardError> {
    if json_bool(body, "ok") == Some(false) {
        return Ok(RefreshParsed::Refused);
    }
    match (
        json_u64(body, "scanned"),
        json_u64(body, "indexed"),
        json_u64(body, "skipped"),
        json_u64(body, "elapsed_ms"),
    ) {
        (Some(scanned), Some(indexed), Some(skipped), Some(elapsed_ms)) => Ok(RefreshParsed::Ok {
            scanned,
            indexed,
            skipped,
            elapsed_ms,
        }),
        _ => Err(WizardError::PhaseFailed),
    }
}

fn json_escape(raw: &str) -> String {
    raw.replace('\\', "\\\\").replace('"', "\\\"")
}

/// Vault-absolute metadata sidecar path (T14 artifact check + compensation).
#[must_use]
pub fn index_meta_path(vault: &Path) -> PathBuf {
    vault.join(RUNTIME_DIR).join(DB_DIR).join(INDEX_META_FILE)
}

/// F7 compensation (T14): remove the metadata sidecar (+ its temp). The index
/// dir itself stays when other passes wrote it; placeholders and user files
/// are never touched; missing files are a no-op.
pub fn compensate_phase7(vault: &Path) {
    let meta = index_meta_path(vault);
    let _ = std::fs::remove_file(&meta);
    let _ = std::fs::remove_file(meta.with_extension("json.tmp"));
}

/// Temp file + rename: a failed write never leaves half a sidecar, and an
/// interrupted F7 never corrupts the metadata a previous pass wrote.
fn write_index_meta(
    vault: &Path,
    model: Option<&str>,
    dims: Option<u32>,
) -> Result<(), WizardError> {
    // shortcut: every fs failure maps to `PermissionDenied` (T7 convention;
    // T15 refines the panel).
    let dir = vault.join(RUNTIME_DIR).join(DB_DIR);
    std::fs::create_dir_all(&dir).map_err(|_| WizardError::PermissionDenied)?;
    let model_json = model
        .map(|name| format!("\"{}\"", json_escape(name)))
        .unwrap_or_else(|| "null".to_string());
    let dims_json = dims
        .map(|width| width.to_string())
        .unwrap_or_else(|| "null".to_string());
    let body = format!("{{\"model\":{model_json},\"dims\":{dims_json}}}\n");
    let tmp = dir.join(format!("{INDEX_META_FILE}.tmp"));
    std::fs::write(&tmp, body).map_err(|_| WizardError::PermissionDenied)?;
    std::fs::rename(&tmp, dir.join(INDEX_META_FILE)).map_err(|_| WizardError::PermissionDenied)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn json_raw_keeps_whitespace_inside_quotes_and_trims_bare_values() {
        let body = "{\"model\":\"  padded  \",\"n\": 7 }";
        assert_eq!(json_raw(body, "model"), Some("  padded  "));
        assert_eq!(json_u64(body, "n"), Some(7));
        assert_eq!(json_bool(body, "n"), None, "un número no es un bool");
        assert_eq!(json_raw(body, "missing"), None);
    }

    #[test]
    fn parse_refresh_maps_the_three_verdicts() {
        match parse_refresh(
            "{\"ok\":true,\"scanned\":10,\"indexed\":3,\"skipped\":7,\"elapsed_ms\":120}",
        ) {
            Ok(RefreshParsed::Ok {
                scanned,
                indexed,
                skipped,
                elapsed_ms,
            }) => {
                assert_eq!((scanned, indexed, skipped, elapsed_ms), (10, 3, 7, 120));
            }
            other => panic!("refresh válido debe parsear, got: {other:?}"),
        }
        assert!(matches!(
            parse_refresh("{\"ok\":false,\"code\":\"E_MODEL_INVALID\"}"),
            Ok(RefreshParsed::Refused)
        ));
        assert_eq!(parse_refresh("garabato"), Err(WizardError::PhaseFailed));
        assert_eq!(
            parse_refresh("{\"ok\":true,\"scanned\":1}"),
            Err(WizardError::PhaseFailed)
        );
    }

    #[test]
    fn write_index_meta_escapes_the_model_and_writes_valid_json() {
        let Ok(vault) = tempfile::tempdir() else {
            panic!("tempdir");
        };
        const RAW: &str = "org/weird\"name\\v2";
        if let Err(err) = write_index_meta(vault.path(), Some(RAW), Some(384)) {
            panic!("write_index_meta: {err:?}");
        }
        let body = match std::fs::read_to_string(index_meta_path(vault.path())) {
            Ok(body) => body,
            Err(err) => panic!("leer el sidecar: {err}"),
        };
        assert_eq!(
            body,
            "{\"model\":\"org/weird\\\"name\\\\v2\",\"dims\":384}\n"
        );
        assert_eq!(json_raw(&body, "model"), Some("org/weird\\\"name\\\\v2"));
        assert_eq!(json_u64(&body, "dims"), Some(384));
    }
}
