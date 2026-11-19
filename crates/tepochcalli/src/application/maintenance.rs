//! T17: `reindex --confirm` (destructive full re-index) + `uninstall`.
//!
//! Single-responsibility orchestrators over ports only — never `adapters/`.
//! `reindex` rebuilds the live index through the venv `refresh` CLI (the same
//! T12 contract F7 uses) and rewrites `{model, dims}` atomically; it never
//! clears the index first — the replacement pass completes before the sidecar
//! goes live, so the old index stays servable until the new one is proven. A
//! config/index model drift surfaces as an `E_MODEL_MISMATCH` panel, never a
//! silent rebuild. `uninstall` removes `.opencode/`, `.tepochcalli/` and
//! `opencode.json` (H8), backing them up first, and is idempotent.

use std::path::{Path, PathBuf};

use crate::domain::WizardError;
use crate::ports::{CommandRunner, Ui};

use super::embedder_menu::config_path;
use super::flow_contract::{parse_gate_dims, parse_refresh, spawn_gate, spawn_refresh, Refreshed};
use super::installer::{venv_python, RUNTIME_DIR, VENV_DIR_NAME};
use super::phase7::{index_meta_path, write_index_meta};
use super::phase8::OPENCODE_JSON;
use super::text::{config_value, json_string, json_u32, or_fallback, provider_is_none};

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

/// `.tepochcalli/` (runtime) is one of the three H8 scopes; the two others
/// are the harness root and its registration file.
pub const UNINSTALL_SCOPES: [&str; 3] = [".opencode", ".tepochcalli", "opencode.json"];
/// What the backup keeps (owner's decision 2026-11-19): only the
/// irreplaceable. `venv/`, `db/`, `models/` and `bin/` are regenerable
/// (re-sync / re-index / re-download) and copying them can burn GB and abort
/// the desinstall on a full disk.
pub const UNINSTALL_BACKUP_SCOPES: [&str; 4] = [
    ".opencode",
    "opencode.json",
    ".tepochcalli/config",
    ".tepochcalli/pyproject.toml",
];
/// Backup folder prefix (sibling of the scopes, inside the vault).
const BACKUP_PREFIX: &str = ".tepochcalli-backup-";

/// What the removal established: whether there was a runtime to remove.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UninstallReport {
    /// `true` when at least one of the three scopes existed and is now gone;
    /// `false` is the idempotent no-op (nothing that was there could be lost).
    pub removed: bool,
    /// Backup folder holding the removed scopes (`None` on a no-op).
    pub backup_dir: Option<PathBuf>,
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

/// H8 scope: remove `.opencode/`, `.tepochcalli/` and `opencode.json` — and
/// NOTHING else (`AGENTS.md`, the notes, the trays, `10-templates/` and
/// `.obsidian/` survive by construction: they are never enumerated). Before
/// removing, the IRREPLACEABLE subset ([`UNINSTALL_BACKUP_SCOPES`]) is copied
/// to `<vault>/.tepochcalli-backup-<ts>/` preserving its relative path.
/// Absent scopes ⇒ no-op `Ok` (idempotencia).
pub fn run_uninstall(ui: &dyn Ui, vault: &Path) -> Result<UninstallReport, WizardError> {
    let present: Vec<(&str, PathBuf)> = UNINSTALL_SCOPES
        .iter()
        .map(|scope| (*scope, vault.join(scope)))
        .filter(|(_, path)| path.exists())
        .collect();
    if present.is_empty() {
        return Ok(UninstallReport {
            removed: false,
            backup_dir: None,
        });
    }
    ui.panel(
        "Desinstall (H8)",
        &format!(
            "Se eliminarán .opencode/, .tepochcalli/ y opencode.json de {}. AGENTS.md y tus \
             notas (00-resources/, 01-…05-, 10-templates/, .obsidian/) NO se tocan. Antes de \
             borrar se copia a una carpeta de backup junto al vault SOLO lo irreemplazable \
             (.opencode/, opencode.json, .tepochcalli/config/ y .tepochcalli/pyproject.toml); \
             venv/, db/, models/ y bin/ no se copian (son regenerables).",
            vault.display()
        ),
    );
    // Backup FIRST: a failed copy aborts with the vault still complete.
    let backup_dir = create_backup_dir(vault)?;
    if let Err(err) = copy_into_backup(vault, &backup_dir) {
        let _ = std::fs::remove_dir_all(&backup_dir);
        return Err(err);
    }
    for (scope, path) in &present {
        // Scope → kind is fixed: the two roots are dirs, `opencode.json` is a
        // file. A corrupted tree (a file named `.tepochcalli`) fails typed
        // instead of silently deleting the wrong thing.
        let outcome = if *scope == OPENCODE_JSON {
            std::fs::remove_file(path)
        } else {
            std::fs::remove_dir_all(path)
        };
        match outcome {
            Ok(()) => {}
            Err(err) if err.kind() == std::io::ErrorKind::NotFound => {}
            // shortcut: every fs failure maps to `PermissionDenied` (T7 convention;
            // T15 refines the panel).
            Err(_) => return Err(WizardError::PermissionDenied),
        }
    }
    ui.panel(
        "Desinstall completo",
        &format!(
            "backup en {} — contiene .tepochcalli/config/ (posible API key): no lo commitees",
            backup_dir.display()
        ),
    );
    Ok(UninstallReport {
        removed: true,
        backup_dir: Some(backup_dir),
    })
}

/// `<vault>/.tepochcalli-backup-<unix-ts>` (a `-N` suffix if that second is
/// already taken by a previous run), created 0700 and self-ignored by its own
/// `.gitignore` (`*`) — it holds `config/`, which may carry an API key.
fn create_backup_dir(vault: &Path) -> Result<PathBuf, WizardError> {
    let stamp = super::failure::now_secs();
    for seq in 0..100u32 {
        let name = if seq == 0 {
            format!("{BACKUP_PREFIX}{stamp}")
        } else {
            format!("{BACKUP_PREFIX}{stamp}-{seq}")
        };
        let dir = vault.join(name);
        match create_private_dir(&dir) {
            Ok(()) => {
                // `*` blocks the whole folder whatever the vault's .gitignore
                // says; the payload's .gitignore is frozen, this one is ours.
                let marker = dir.join(".gitignore");
                std::fs::write(&marker, "*\n").map_err(|_| WizardError::PermissionDenied)?;
                super::installer::set_user_private(&marker)?;
                return Ok(dir);
            }
            Err(err) if err.kind() == std::io::ErrorKind::AlreadyExists => {}
            Err(_) => return Err(WizardError::PermissionDenied),
        }
    }
    Err(WizardError::PermissionDenied)
}

/// `create_dir` with 0700 on Unix (0600 for files lives in
/// [`super::installer::set_user_private`]).
fn create_private_dir(dir: &Path) -> std::io::Result<()> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::DirBuilderExt as _;
        std::fs::DirBuilder::new().mode(0o700).create(dir)
    }
    #[cfg(not(unix))]
    {
        std::fs::create_dir(dir)
    }
}

/// Copy the irreplaceable scopes under `backup` preserving vault-relative
/// paths; a scope that does not exist is simply absent.
fn copy_into_backup(vault: &Path, backup: &Path) -> Result<(), WizardError> {
    for scope in UNINSTALL_BACKUP_SCOPES {
        let source = vault.join(scope);
        if !source.exists() {
            continue;
        }
        copy_tree(&source, &backup.join(scope))?;
    }
    Ok(())
}

/// Recursive copy that never follows symlinks (a symlinked model dir must
/// not drag the backup outside the vault).
fn copy_tree(source: &Path, target: &Path) -> Result<(), WizardError> {
    let kind = std::fs::symlink_metadata(source)
        .map_err(|_| WizardError::PermissionDenied)?
        .file_type();
    if kind.is_symlink() {
        return Ok(());
    }
    if kind.is_dir() {
        std::fs::create_dir_all(target).map_err(|_| WizardError::PermissionDenied)?;
        let entries = std::fs::read_dir(source).map_err(|_| WizardError::PermissionDenied)?;
        for entry in entries {
            let entry = entry.map_err(|_| WizardError::PermissionDenied)?;
            copy_tree(&entry.path(), &target.join(entry.file_name()))?;
        }
        return Ok(());
    }
    if let Some(parent) = target.parent() {
        std::fs::create_dir_all(parent).map_err(|_| WizardError::PermissionDenied)?;
    }
    std::fs::copy(source, target).map_err(|_| WizardError::PermissionDenied)?;
    Ok(())
}

/// Gate success payload of the reindex (variante reducida del contrato
/// compartido): only the measured dims matter here — the model is the
/// configured one.
#[derive(Debug, PartialEq, Eq)]
struct GateOk {
    dims: u32,
}

/// Gate del reindex (trunk compartido, T11): sin revisión ni token — las
/// variantes son parámetros explícitos de `spawn_gate`. `ok:false` is the
/// portero verdict (`E_MODEL_INVALID`); a crashed/garbled gate is
/// `PhaseFailed`.
fn run_gate(proc: &dyn CommandRunner, vault: &Path, model: &str) -> Result<GateOk, WizardError> {
    let out = spawn_gate(proc, vault, model, None, None)?;
    parse_gate(&out.stdout)
}

/// Replacement `refresh` (T12 contract, parser compartido). `ok:false` maps
/// to `ModelInvalid`, matching the F7 portero parity; anything else
/// unparseable is `PhaseFailed`.
fn run_refresh(proc: &dyn CommandRunner, vault: &Path) -> Result<Refreshed, WizardError> {
    let out = spawn_refresh(proc, vault)?;
    parse_refresh(&out.stdout)
}

fn parse_gate(body: &str) -> Result<GateOk, WizardError> {
    parse_gate_dims(body).map(|dims| GateOk { dims })
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
