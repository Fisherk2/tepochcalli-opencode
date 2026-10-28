//! F8 `mcp.servers` merge (T13): backup, conservative merge, verification.
//!
//! Single-responsibility orchestrator over the `CommandRunner` port plus
//! `domain` — never `adapters/`. Three steps, in order:
//!
//! 1. **Backup:** byte-copy `opencode.json` → `opencode.json.bak` (only when
//!    the file pre-exists; a backup failure aborts BEFORE any mutation, so
//!    there is nothing to compensate).
//! 2. **Merge:** conservative JSON merge — every unrelated user server is
//!    preserved byte-for-value; only `tepochcalli-rag` is (re)written and a
//!    stale `markitdown` entry is removed (D19). The merged doc keeps key
//!    order (`preserve_order`) and the payload's 2-space form, and lands
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

use super::installer::{venv_python, RUNTIME_DIR, VENV_DIR_NAME};

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
 from tepochcalli_mcp.server import _vault_config, _meta_seam, _config_valid; \
 from tepochcalli_mcp.tools import rag_status as _rs; \
 print(json.dumps(asyncio.run(_rs.rag_status(\
 config_factory=_vault_config, index_meta=_meta_seam, config_valid=_config_valid))))";

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
fn expected_rag_entry() -> serde_json::Value {
    serde_json::json!({
        "type": "local",
        "command": [mcp_python_command(), "-m", "tepochcalli_mcp"],
        "cwd": ".",
        "environment": { CONTRACT_ROOT_ENV: "." },
        "disabled": false
    })
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
    let expected = expected_rag_entry();
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

/// Minimal readers for the one-line `rag_status` payload (same hand-rolled
/// shape as the F6 gate and F7 refresh parsers: flat top-level keys).
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
fn verify_rag_status(proc: &dyn CommandRunner, vault: &Path) -> Result<RagHealth, WizardError> {
    // shortcut: a vault without the venv interpreter means F5 never ran;
    // same class as F5's missing-`uv` and F7's missing-interpreter checks.
    let python = venv_python(&vault.join(RUNTIME_DIR).join(VENV_DIR_NAME));
    if !python.is_file() {
        return Err(WizardError::Internal);
    }
    let program = python.to_str().ok_or(WizardError::Internal)?.to_string();
    let out = proc.run(
        &program,
        &["-c", RAG_STATUS_PROBE],
        vault,
        &[(CONTRACT_ROOT_ENV, ".")],
    )?;
    if out.status != 0 {
        return Err(WizardError::PhaseFailed);
    }
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
/// created when none pre-existed); the backup is removed so a compensated
/// run leaves no residue. Missing backup + missing file is a no-op.
pub fn compensate_phase8(vault: &Path) {
    let target = vault.join(OPENCODE_JSON);
    let backup = vault.join(OPENCODE_BAK);
    match std::fs::read(&backup) {
        Ok(bytes) => {
            let _ = std::fs::write(&target, &bytes);
            let _ = std::fs::remove_file(&backup);
        }
        Err(_) => {
            // No backup ⇒ F8 created the file (absent at entry); remove it.
            // A pre-existing user file always leaves a backup, so this never
            // deletes user data (single-threaded installer, seconds apart).
            let _ = std::fs::remove_file(&target);
        }
    }
}
