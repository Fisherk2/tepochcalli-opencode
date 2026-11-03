//! F8 `mcp.servers` merge (T13): backup, conservative merge, verification.
//!
//! Single-responsibility orchestrator over the `CommandRunner` port plus
//! `domain` — never `adapters/`. Three steps, in order:
//!
//! 1. **Backup:** byte-copy `opencode.json` → `opencode.json.bak` (only when
//!    the file pre-exists; a backup failure aborts BEFORE any mutation, so
//!    there is nothing to compensate).
//! 2. **Merge:** conservative JSON merge — every unrelated user server is
//!    preserved byte-for-value; only `tepochcalli-rag` is (re)written (its
//!    `environment` keeps every key the user added, imposing only
//!    `TEPOCHCALLI_ROOT`), and a stale `markitdown` entry is removed (D19).
//!    The merged doc keeps key order (`preserve_order`) and the payload's
//!    2-space form, and lands
//!    atomically (temp + rename in the same dir). A byte-identical entry is
//!    left untouched (`changed: false`).
//! 3. **Verify:** run the vault venv python with the registered cwd + env
//!    (`TEPOCHCALLI_ROOT=.`) calling the raw `rag_status` handler — the
//!    stdio transport the `CommandRunner` port cannot speak (no stdin seam;
//!    T4 froze the port) is bypassed, but interpreter, cwd and env are
//!    exactly the harness's. Any failure compensates (restore `.bak`).

use std::path::Path;

use crate::domain::WizardError;
use crate::ports::CommandRunner;

use super::flow_cli::run_flow_cli;
use super::text::json_raw;

/// The only `mcp.servers` key F8 owns (spec-installer-wizard §Merge, D19).
pub const MANAGED_RAG: &str = "tepochcalli-rag";
/// Stale entry F8 removes when the user still has it (D19: conversion is
/// in-process via `add_source`, no standalone server since `ee26073`).
pub const STALE_MARKITDOWN: &str = "markitdown";
/// Vault-top config file F8 merges.
pub const OPENCODE_JSON: &str = "opencode.json";
/// Byte backup taken before any write; compensation restores from it.
pub const OPENCODE_BAK: &str = "opencode.json.bak";
/// Temp file for the atomic rename (same dir ⇒ same filesystem).
const OPENCODE_TMP: &str = "opencode.json.tmp";
/// Contract env var (spec-mcp-server §Carga de configuración).
const CONTRACT_ROOT_ENV: &str = "TEPOCHCALLI_ROOT";

/// Probe argv[1]: calls the raw `rag_status` handler through the vault venv
/// and prints its payload as one JSON line. Couples to `server.py` seam
/// names (`_vault_config`/`_meta_seam`/`_config_valid`); the one-version
/// rule keeps wizard and payload in lockstep, and the composition root —
/// not this probe — owns the backend wiring (ADR-005).
pub const RAG_STATUS_PROBE: &str = "import asyncio, json; \
 from tepochcalli_mcp.server import _vault_config, _meta_seam, _config_valid, \
 _last_refresh_roots_seam, _available_roots_seam; \
 from tepochcalli_mcp.tools import rag_status as _rs; \
 print(json.dumps(asyncio.run(_rs.rag_status(\
 config_factory=_vault_config, index_meta=_meta_seam, config_valid=_config_valid, \
 last_refresh_roots=_last_refresh_roots_seam, available_roots=_available_roots_seam))))";

/// `rag_status` health, the only F8 outcome the install summary needs.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RagHealth {
    /// Embedder configured and index consistent.
    Ok,
    /// `provider = "none"` (or mismatch): install is complete, RAG degraded.
    Degraded,
}

impl RagHealth {
    /// Lowercase spec literal (`"ok"` / `"degraded"`) for the summary line.
    #[must_use]
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Ok => "ok",
            Self::Degraded => "degraded",
        }
    }
}

/// What F8 established: whether the file changed plus the verified health.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Phase8Report {
    /// `true` when the merge wrote (new/rewrote entry or removed markitdown).
    pub changed: bool,
    /// End-to-end `rag_status` health through the registered registration.
    pub health: RagHealth,
}

/// Venv interpreter path, relative to the vault, portable by OS (D20).
#[must_use]
pub fn mcp_python_command_for(windows: bool) -> &'static str {
    if windows {
        ".tepochcalli/venv/Scripts/python.exe"
    } else {
        ".tepochcalli/venv/bin/python"
    }
}

/// This host's portable command (`cfg!(windows)` picks at compile time).
#[must_use]
pub fn mcp_python_command() -> &'static str {
    mcp_python_command_for(cfg!(windows))
}

/// The exact entry F8 manages (spec-installer-wizard §Merge): key order is
/// the payload's (`type/command/cwd/environment/disabled`), preserved by
/// the `preserve_order` serializer on both write and comparison.
fn expected_rag_entry(
    environment: serde_json::Map<String, serde_json::Value>,
) -> serde_json::Value {
    serde_json::json!({
        "type": "local",
        "command": [mcp_python_command(), "-m", "tepochcalli_mcp"],
        "cwd": ".",
        "environment": serde_json::Value::Object(environment),
        "disabled": false
    })
}

/// Environment of the managed entry: every key the user already put there
/// survives (D32 — `INDEXER_DIR`, `TEPOCHCALLI_TOP_K`…), and only the
/// contract root is imposed. Insertion order is the user's, so pointing
/// `TEPOCHCALLI_ROOT` at its existing position keeps a rerun byte-equal.
fn merged_environment(
    current: Option<&serde_json::Value>,
) -> Result<serde_json::Map<String, serde_json::Value>, WizardError> {
    let mut environment = match current {
        // Present-but-not-an-object is a safe typed failure (never a guess),
        // same criterion as `servers_mut`.
        Some(value) => value.as_object().ok_or(WizardError::PhaseFailed)?.clone(),
        None => serde_json::Map::new(),
    };
    environment.insert(
        CONTRACT_ROOT_ENV.to_string(),
        serde_json::Value::String(".".to_string()),
    );
    Ok(environment)
}

/// The `mcp.servers` object, creating `mcp`/`servers` when absent; a
/// present-but-not-an-object shape is a safe typed failure (never a guess).
fn servers_mut(
    doc: &mut serde_json::Value,
) -> Result<&mut serde_json::Map<String, serde_json::Value>, WizardError> {
    let root = doc.as_object_mut().ok_or(WizardError::PhaseFailed)?;
    let mcp = root
        .entry("mcp")
        .or_insert_with(|| serde_json::Value::Object(serde_json::Map::new()));
    let mcp_obj = mcp.as_object_mut().ok_or(WizardError::PhaseFailed)?;
    let servers = mcp_obj
        .entry("servers")
        .or_insert_with(|| serde_json::Value::Object(serde_json::Map::new()));
    servers.as_object_mut().ok_or(WizardError::PhaseFailed)
}

/// Conservative merge: drop the stale entry, (re)write the managed one only
/// when it differs. Returns whether the doc changed.
fn merge_servers(doc: &mut serde_json::Value) -> Result<bool, WizardError> {
    let servers = servers_mut(doc)?;
    // shortcut: strict JSON only (no comments); a comment-laden opencode.json
    // fails safe in `run_phase8` — upgrade to a JSONC parser if users hit it.
    let mut changed = false;
    if servers.shift_remove(STALE_MARKITDOWN).is_some() {
        changed = true;
    }
    let expected = expected_rag_entry(merged_environment(
        servers.get(MANAGED_RAG).and_then(|e| e.get("environment")),
    )?);
    match servers.get(MANAGED_RAG) {
        Some(current) if current == &expected => {}
        _ => {
            servers.insert(MANAGED_RAG.to_string(), expected);
            changed = true;
        }
    }
    Ok(changed)
}

/// Temp file + rename in the same dir: a failed write never leaves half an
/// `opencode.json` (same pattern as the F6 config and F7 metadata writes).
fn atomic_write(target: &Path, body: &[u8]) -> Result<(), WizardError> {
    // shortcut: every fs failure maps to `PermissionDenied` (T7 convention).
    let tmp = target
        .parent()
        .map(|dir| dir.join(OPENCODE_TMP))
        .ok_or(WizardError::PermissionDenied)?;
    std::fs::write(&tmp, body).map_err(|_| WizardError::PermissionDenied)?;
    std::fs::rename(&tmp, target).map_err(|_| {
        let _ = std::fs::remove_file(&tmp);
        WizardError::PermissionDenied
    })
}

/// The four frozen `rag_status` blocks plus the health semantics of
/// spec-mcp-server §rag_status: `degraded` needs an `E_*` reason and a
/// non-empty `fix_hint`; `ok` needs both null; a guard error envelope is a
/// handler failure, never a health verdict.
fn parse_rag_status(body: &str) -> Result<RagHealth, WizardError> {
    if json_raw(body, "error").is_some() {
        return Err(WizardError::PhaseFailed);
    }
    for block in ["embedder", "index", "config", "health"] {
        if json_raw(body, block).is_none() {
            return Err(WizardError::PhaseFailed);
        }
    }
    match json_raw(body, "mode") {
        Some("local" | "api" | "none") => {}
        _ => return Err(WizardError::PhaseFailed),
    }
    match json_raw(body, "state") {
        Some("ok") => match (json_raw(body, "reason"), json_raw(body, "fix_hint")) {
            (Some("null"), Some("null")) => Ok(RagHealth::Ok),
            _ => Err(WizardError::PhaseFailed),
        },
        Some("degraded") => match (json_raw(body, "reason"), json_raw(body, "fix_hint")) {
            (Some(reason), Some(hint))
                if reason.starts_with("E_") && !hint.is_empty() && hint != "null" =>
            {
                Ok(RagHealth::Degraded)
            }
            _ => Err(WizardError::PhaseFailed),
        },
        _ => Err(WizardError::PhaseFailed),
    }
}

/// Run the registered registration's interpreter with its cwd + env and
/// validate the `rag_status` shape end to end (spec-mcp-server §rag_status).
/// The contract env rides `extra_env`: the probe speaks `TEPOCHCALLI_ROOT`,
/// not the flow sandbox.
fn verify_rag_status(proc: &dyn CommandRunner, vault: &Path) -> Result<RagHealth, WizardError> {
    let out = run_flow_cli(
        proc,
        vault,
        &["-c", RAG_STATUS_PROBE],
        &[(CONTRACT_ROOT_ENV, ".")],
        None,
        super::flow_cli::PROBE_TIMEOUT,
    )?;
    parse_rag_status(out.stdout.trim())
}

/// F8: backup → conservative merge (atomic, only when different) → `rag_status`
/// end-to-end. A backup failure aborts before any mutation; any later
/// failure compensates (the user file is restored byte-identical).
pub fn run_phase8(proc: &dyn CommandRunner, vault: &Path) -> Result<Phase8Report, WizardError> {
    // shortcut: every fs failure maps to `PermissionDenied` (T7 convention).
    let target = vault.join(OPENCODE_JSON);
    let original: Option<Vec<u8>> = if target.is_file() {
        Some(std::fs::read(&target).map_err(|_| WizardError::PermissionDenied)?)
    } else {
        None
    };
    if let Some(bytes) = &original {
        std::fs::write(vault.join(OPENCODE_BAK), bytes)
            .map_err(|_| WizardError::PermissionDenied)?;
    }
    let outcome = merge_and_verify(proc, vault, &target, original.as_deref());
    if outcome.is_err() {
        compensate_phase8(vault);
    }
    outcome
}

fn merge_and_verify(
    proc: &dyn CommandRunner,
    vault: &Path,
    target: &Path,
    original: Option<&[u8]>,
) -> Result<Phase8Report, WizardError> {
    let mut doc: serde_json::Value = match original {
        Some(bytes) => serde_json::from_slice(bytes).map_err(|_| WizardError::PhaseFailed)?,
        None => serde_json::json!({ "mcp": { "servers": {} } }),
    };
    let changed = merge_servers(&mut doc)?;
    if changed {
        let mut body = serde_json::to_string_pretty(&doc).map_err(|_| WizardError::PhaseFailed)?;
        body.push('\n');
        atomic_write(target, body.as_bytes())?;
    }
    let health = verify_rag_status(proc, vault)?;
    Ok(Phase8Report { changed, health })
}

/// F8 compensation: restore the pre-merge bytes (or remove the file F8
/// created when none pre-existed); the backup is removed ONLY when the
/// restore succeeded — a failed write keeps the `.bak` as the last good
/// copy (mailing user data is never the compensation's outcome). Missing
/// backup + missing file is a no-op.
pub fn compensate_phase8(vault: &Path) {
    let target = vault.join(OPENCODE_JSON);
    let backup = vault.join(OPENCODE_BAK);
    match std::fs::read(&backup) {
        Ok(bytes) => {
            if std::fs::write(&target, &bytes).is_ok() {
                let _ = std::fs::remove_file(&backup);
            }
        }
        Err(_) => {
            // No backup ⇒ F8 created the file (absent at entry); remove it.
            // A pre-existing user file always leaves a backup, so this never
            // deletes user data (single-threaded installer, seconds apart).
            let _ = std::fs::remove_file(&target);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_rag_status_rejects_error_envelopes() {
        // El envoltorio de error del guard es un fallo de handler, nunca un
        // veredicto de salud (cubre el `json_raw` compartido en el camino).
        assert_eq!(
            parse_rag_status(r#"{"error":"E_X","reason":"boom"}"#),
            Err(WizardError::PhaseFailed)
        );
    }

    /// L2-3: si la restauración del `.bak` falla (destino ocupado por un
    /// directorio ⇒ EISDIR con cualquier uid), el backup SOBREVIVE: nunca
    /// queda una copia de los bytes del usuario sola en un write que falló.
    #[test]
    fn failed_restore_keeps_the_backup() {
        let Ok(vault) = tempfile::tempdir() else {
            panic!("tempdir");
        };
        let backup = vault.path().join(OPENCODE_BAK);
        if let Err(err) = std::fs::write(&backup, b"# original\n") {
            panic!("fixture .bak: {err}");
        }
        let target = vault.path().join(OPENCODE_JSON);
        if let Err(err) = std::fs::create_dir(&target) {
            panic!("fixture target dir (IEID saboteado): {err}");
        }

        compensate_phase8(vault.path());

        match std::fs::read(&backup) {
            Ok(bytes) => assert_eq!(bytes, b"# original\n", "el .bak sobrevive"),
            Err(err) => panic!("el .bak no puede perderse: {err}"),
        }
    }
}
