//! D8.4 atomic embedder swap (T16): `tepochcalli config embedder` on a vault
//! that already has an embedder.
//!
//! Six steps in order: (1) current-state display (model, dims, db usage,
//! `rag_status` shape); (2) the same D7.1 menu with D8.1 figures and D8.2
//! badges; (3) explicit full-reindex warning + time estimate with mandatory
//! `--confirm`; (4) new-model download + test-embed gate (measured RSS) then
//! re-index; (5) atomic config/metadata switch; (6) auto-GC of the previous
//! model cache unless `--keep-previous`.
//!
//! Single-responsibility orchestrator over ports only — never `adapters/`.
//! C1 (D7.3): la config ELEGIDA escribe VIVA (via tmp+rename) ANTES del
//! gate/refresh — el refresh reconstruye ya con el nuevo embedder — y el
//! commit final conmuta SOLO el index-meta. El índice (los ficheros de db/)
//! no se toca antes del commit, así cualquier fallo se arrolla con el
//! snapshot byte-identical (rollback + temps fuera, cero estado).

use std::path::{Path, PathBuf};

use crate::config::{default_and_large, parse_presets, Preset};
use crate::domain::{EmbedderChoice, WizardError};
use crate::ports::{CommandRunner, HostProbe, HttpClient, Ui};

use super::embedder_menu::{
    ask_non_empty, ask_secret_non_empty, build_options, config_path, external_config, local_config,
    none_config, parse_hf_metadata, write_config, Phase6Report, Provenance, EMBEDDER_PATHS,
};
use super::installer::{set_user_private, RUNTIME_DIR};
use super::phase7::index_meta_path;
use super::phase8::RagHealth;
use super::text::{
    config_value, is_plausible_hf_id, json_bool, json_escape, json_string, json_u32, json_u64,
    or_fallback,
};

/// Header lines of the swap-written `[embedding]` configs (D8.4): identical
/// shape to the F6 ones via the shared builders — the bytes stay the ones
/// the swap has always written (trazabilidad del artefacto).
const SWAP_LOCAL_HEADER: &str = "generado por `tepochcalli config embedder` (swap D8.4)";
const SWAP_EXTERNAL_HEADER: &str =
    "generado por `tepochcalli config embedder` (swap D8.4) — gitignored, nunca commitear";
const SWAP_NONE_HEADER: &str =
    "generado por `tepochcalli config embedder` (swap D8.4, salida 5) — re-entrada con el mismo comando";

/// Model cache dir, sandboxed under the vault (same dir the F6 gate uses).
const MODELS_DIR: &str = "models";
/// Gate + refresh run through the vault venv (T11/T12 contracts, D24/D25).
const GATE_MODULE: &str = "tepochcalli_flow";
const GATE_SUBCOMMAND: &str = "embed-check";
const REFRESH_SUBCOMMAND: &str = "refresh";
/// HF API base for the free-id pre-check (D8.1; the gate stays ground truth).
const HF_API_BASE: &str = "https://huggingface.co/api/models/";
const BYTES_PER_MB: f64 = 1_000_000.0;
/// Staged sidecar (not yet live): renamed into place only on success.
const META_SWAP_SUFFIX: &str = "index-meta.json.swap";

/// Los cuatro collaborators que el swap pide prestados (ports; ellos hacen
/// el I/O, el swap solo orquesta).
pub struct SwapDeps<'a> {
    /// Menu, inputs, failure panels.
    pub ui: &'a dyn Ui,
    /// RAM/GPU facts for badges (D8.2).
    pub host: &'a dyn HostProbe,
    /// Runs the venv `embed-check` gate and `refresh` (T11/T12).
    pub proc: &'a dyn CommandRunner,
    /// HF API pre-check for free ids (D8.1).
    pub http: &'a dyn HttpClient,
}

/// Swap flags (`tepochcalli config embedder [--confirm] [--keep-previous]`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct SwapOptions {
    /// Mandatory: without it the swap explains itself and mutates nothing.
    pub confirm: bool,
    /// When true the previous model cache survives (no auto-GC).
    pub keep_previous: bool,
}

/// What the swap established: the new embedder plus the replaced index size.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SwapReport {
    /// New HF id or external model name.
    pub model: String,
    /// Gate-measured dims (`None` for the external-API path).
    pub dims: Option<u32>,
    /// Gate-measured RSS peak in bytes (`None` for external-API/`none` paths).
    pub rss_peak_bytes: Option<u64>,
    /// Index rows after the re-index (`scanned` of the replacement pass).
    pub rows: u64,
    /// Live db size in bytes at swap time (basis of the time estimate).
    pub db_bytes: u64,
    /// Post-swap health in `rag_status` terms.
    pub health: RagHealth,
}

/// Live files read before anything is staged (basis of the zero-state rollback).
struct Snapshot {
    config: Option<Vec<u8>>,
    meta: Option<Vec<u8>>,
}

/// Current embedder + index facts for step 1 (all `None`/zero when absent).
struct CurrentState {
    provider: Option<String>,
    model: Option<String>,
    dims: Option<u32>,
    /// Ficheros de datos bajo `db/` (`db_usage`); no son filas del índice.
    db_file_count: u64,
    db_bytes: u64,
}

impl CurrentState {
    fn describe(&self) -> String {
        let (state, mode): (String, String) = match self.provider.as_deref() {
            Some("local") => ("ok".to_string(), "local".to_string()),
            // Contrato real de phase8 (§rag_status): el provider interno es
            // `litellm`, el modo público es `api`.
            Some("litellm") => ("ok".to_string(), "api".to_string()),
            _ => ("degraded".to_string(), "none".to_string()),
        };
        format!(
            "model: {}\ndims: {}\nficheros en db/: {}\ntamaño de db: {} bytes\n\
             rag_status: {{\"state\":\"{state}\",\"mode\":\"{mode}\"}}",
            self.model.as_deref().unwrap_or("(sin configurar)"),
            or_fallback(self.dims),
            self.db_file_count,
            self.db_bytes,
        )
    }
}

/// D8.4 six-step swap with zero-state rollback on any failure.
pub fn run_swap(
    deps: &SwapDeps<'_>,
    vault: &Path,
    opts: &SwapOptions,
) -> Result<SwapReport, WizardError> {
    let before = snapshot(vault);
    // (1) Show the current state (reads only — never a mutation).
    let current = current_state(vault);
    deps.ui
        .panel("Estado actual del embedder", &current.describe());
    // (2) Pick the new embedder: the same D7.1 menu with D8 badges.
    // The optional HF token travels alongside (never in a panel or file).
    let (picked, token) = pick_embedder(deps)?;
    // (3) Explicit full-reindex warning + estimate; `--confirm` is mandatory.
    deps.ui
        .panel("Advertencia de re-index", &warning(&picked, &current));
    if !opts.confirm {
        deps.ui.panel(
            "Falta --confirm",
            "El swap exige un re-index completo (irreversible: LanceDB no mezcla \
             dimensiones, el índice se reconstruye con el nuevo embedder). \
             Re-ejecuta con `--confirm` para proceder; sin ese flag no se cambia nada.",
        );
        return Err(WizardError::UserAborted);
    }
    // C1 (D7.3): la config ELEGIDA queda VIVA (tmp+rename, mismo tramo del
    // write_config de F6) ANTES del gate/refresh — el refresh reconstruye ya
    // con el nuevo embedder. La guarda E1-S3: un fallo aquí comparte el mismo
    // abort del resto de ramas (rollback a los bytes previos del snapshot).
    if let Err(err) = write_config(vault, &picked_config_body(&picked)) {
        abort_swap(vault, &before);
        return Err(err);
    }
    let outcome = download_gate_and_reindex(deps, vault, &picked, token.as_deref(), &current);
    match outcome {
        Err(err) => {
            abort_swap(vault, &before);
            Err(err)
        }
        Ok(partial) => {
            if commit_meta(vault, &picked).is_err() {
                abort_swap(vault, &before);
                return Err(WizardError::PermissionDenied);
            }
            cleanup_staged(vault);
            // (6) Auto-GC, only after the atomic switch — and only then.
            gc_old_model(
                vault,
                before.model_name(),
                picked.model.as_deref(),
                opts.keep_previous,
            );
            let health = if picked.provider == "none" {
                RagHealth::Degraded
            } else {
                RagHealth::Ok
            };
            deps.ui.panel(
                "Swap completo",
                &format!(
                    "modelo {} · dims {} · RSS pico {}MB ({})\n\
                     config y metadatos conmutados atómicamente{}",
                    partial.model,
                    or_fallback(partial.dims),
                    or_fallback(
                        partial
                            .rss_peak_bytes
                            .map(|rss| (rss as f64 / BYTES_PER_MB) as u64)
                    ),
                    Provenance::Measured.label(),
                    if opts.keep_previous {
                        "; modelo anterior retenido (--keep-previous)"
                    } else {
                        "; modelo anterior purgado de models/"
                    },
                ),
            );
            Ok(SwapReport {
                model: partial.model,
                dims: partial.dims,
                rss_peak_bytes: partial.rss_peak_bytes,
                rows: partial.rows,
                db_bytes: current.db_bytes,
                health,
            })
        }
    }
}

impl Snapshot {
    fn model_name(&self) -> Option<String> {
        let body = String::from_utf8_lossy(self.config.as_ref()?);
        config_value(&body, "model")
    }
}

fn snapshot(vault: &Path) -> Snapshot {
    Snapshot {
        config: std::fs::read(config_path(vault)).ok(),
        meta: std::fs::read(index_meta_path(vault)).ok(),
    }
}

/// Live config + index sidecar + db usage (missing files ⇒ degraded zeros).
fn current_state(vault: &Path) -> CurrentState {
    let raw_config = std::fs::read_to_string(config_path(vault)).unwrap_or_default();
    let raw_meta = std::fs::read_to_string(index_meta_path(vault)).unwrap_or_default();
    let (db_file_count, db_bytes) = db_usage(vault);
    CurrentState {
        provider: config_value(&raw_config, "provider"),
        model: config_value(&raw_config, "model").or_else(|| json_string(&raw_meta, "model")),
        dims: json_u32(&raw_meta, "dims"),
        db_file_count,
        db_bytes,
    }
}

/// File count + byte size of the live db dir (missing dir ⇒ zeros, e.g. a
/// degraded vault that never indexed).
fn db_usage(vault: &Path) -> (u64, u64) {
    let mut file_count = 0u64;
    let mut bytes = 0u64;
    let entries = match std::fs::read_dir(vault.join(RUNTIME_DIR).join("db")) {
        Ok(entries) => entries,
        Err(_) => return (0, 0),
    };
    for entry in entries.flatten() {
        if let Ok(meta) = entry.metadata() {
            if meta.is_file() {
                file_count += 1;
                bytes += meta.len();
            }
        }
    }
    (file_count, bytes)
}

/// ≈2 s per MB of live index, at least 1 s (display-only figure, D8.1).
fn estimate_secs(db_bytes: u64) -> u64 {
    (db_bytes / 1_000_000).saturating_mul(2).max(1)
}

fn warning(picked: &Phase6Report, current: &CurrentState) -> String {
    // El externo empaqueta `model\0api_key`: la forma empaquetada no se
    // paneliza nunca (la clave solo vive en la config gitignored).
    let name = picked.model.as_deref().unwrap_or("(sin modelo)");
    let name = name.split_once('\u{0}').map_or(name, |(model, _)| model);
    format!(
        "El swap a {} exige un re-index COMPLETO (LanceDB no mezcla dimensiones).\n\
         Tiempo estimado: ≈{} s (ficheros en db/: {}, {} bytes).\n\
         Durante el proceso el índice viejo sigue servable; al triunfar, config y \
         metadatos conmutan atómicamente y el modelo anterior se purga de models/.\n\
         Requiere --confirm explícito.",
        name,
        estimate_secs(current.db_bytes),
        current.db_file_count,
        current.db_bytes,
    )
}

/// Step 2: the D7.1 menu with D8.1 figures and D8.2 badges. Selection only —
/// nothing is written here; the gate (step 4) decides. Returns the pick plus
/// an optional HF token for a gated free id (child-env only, never logged).
fn pick_embedder(deps: &SwapDeps<'_>) -> Result<(Phase6Report, Option<String>), WizardError> {
    let presets = parse_presets().map_err(|_| WizardError::Internal)?;
    let (default, large) = default_and_large(&presets).ok_or(WizardError::Internal)?;
    // L5-1: un snapshot de facts por corrida — el menú deja de re-probar
    // RAM/GPU por fila.
    let facts = deps.host.snapshot();
    let options = build_options(default, large, &facts);
    let shown: Vec<&str> = options.iter().map(String::as_str).collect();
    let index = deps.ui.select("Embedding provider", &shown, 0)?;
    let choice = EMBEDDER_PATHS
        .get(index)
        .copied()
        .ok_or(WizardError::UserAborted)?;
    // shortcut: single-shot menu (no T11 retry loop) — an invalid free id
    // fails the swap with zero state instead of re-asking.
    match choice {
        EmbedderChoice::PresetDefault => Ok((pending_local(default), None)),
        EmbedderChoice::PresetLarge => Ok((pending_local(large), None)),
        EmbedderChoice::HuggingFaceId => pending_free_id(deps),
        EmbedderChoice::ExternalApi => pending_external(deps).map(|report| (report, None)),
        EmbedderChoice::ConfigureLater => Ok((Phase6Report::configure_later(), None)),
    }
}

/// Local pick before the gate: dims/RSS arrive in step 4 (measured, D8.1).
fn pending_local(preset: &Preset) -> Phase6Report {
    Phase6Report {
        provider: "local".to_string(),
        model: Some(preset.hf_id.clone()),
        revision: Some(preset.revision.clone()),
        dims: None,
        rss_peak_bytes: None,
    }
}

fn pending_free_id(deps: &SwapDeps<'_>) -> Result<(Phase6Report, Option<String>), WizardError> {
    let id = ask_non_empty(deps.ui, "HuggingFace model id")?;
    if !is_plausible_hf_id(&id) {
        deps.ui.panel(
            "E_MODEL_INVALID",
            "Ese ID no es plausible como modelo de HuggingFace; el swap se aborta sin escribir nada.",
        );
        return Err(WizardError::ModelInvalid);
    }
    let estimate = match deps.http.get(&format!("{HF_API_BASE}{id}")) {
        Ok(body) => Some(parse_hf_metadata(&body)),
        Err(_) => {
            deps.ui.panel(
                "Sin estimación",
                "La API de HF no responde (sin red): se intenta la descarga directa.",
            );
            None
        }
    };
    // La revisión pineada es el `sha` del repo (D59): el gate materializa ese
    // snapshot y la config lo registra. Sin API queda `None` (default del flow).
    let revision = estimate.as_ref().and_then(|estimate| estimate.sha.clone());
    let report_for = |model: String, revision: Option<String>| Phase6Report {
        provider: "local".to_string(),
        model: Some(model),
        revision,
        dims: None,
        rss_peak_bytes: None,
    };
    // Misma lectura que el menú F6: la decisión vive en `HfEstimate`
    // (`embedding_tag`/`gated`), con HF real (`"gated":"auto"`) el swap ya
    // ofrece el token — el viejo `contains("\"gated\":true")` no lo veía.
    if let Some(estimate) = &estimate {
        if estimate.embedding_tag == Some(false) {
            deps.ui.panel(
                "E_MODEL_INVALID",
                "Ese ID no es un modelo de embeddings; el swap se aborta sin escribir nada.",
            );
            return Err(WizardError::ModelInvalid);
        }
        if estimate.gated {
            deps.ui.panel(
                "Modelo gated",
                "La API marca este repo como gated: la descarga pedirá HF_TOKEN.",
            );
            // shortcut: the token travels only in the gate child env (never
            // in a panel, log or file — same redaction rule as T11g).
            let raw = deps
                .ui
                .input_secret("HF_TOKEN (opcional, solo para esta descarga)")?;
            let token = raw.trim().to_string();
            if token.is_empty() {
                return Ok((report_for(id, revision), None));
            }
            return Ok((report_for(id, revision), Some(token)));
        }
    }
    Ok((report_for(id, revision), None))
}

fn pending_external(deps: &SwapDeps<'_>) -> Result<Phase6Report, WizardError> {
    let model = ask_non_empty(
        deps.ui,
        "Modelo externo (p. ej. openai/text-embedding-3-small)",
    )?;
    // shortcut: the key is asked WITHOUT echo (input_secret, L2-7 — the
    // comment "never echoed" is now literally true); a mistyped key
    // surfaces as E_API_AUTH at first embed (same edge-table rule as T11
    // path 4).
    let api_key = ask_secret_non_empty(deps.ui, "API key (solo se guarda en config gitignored)")?;
    Ok(Phase6Report {
        provider: "litellm".to_string(),
        model: Some(format!("{model}\u{0}{api_key}")),
        revision: None,
        dims: None,
        rss_peak_bytes: None,
    })
}

/// The arm of both failure branches: live bytes back to the snapshot first
/// (rollback), then the staged temps go away — zero-state, in that order.
fn abort_swap(vault: &Path, before: &Snapshot) {
    rollback(vault, before);
    cleanup_staged(vault);
}

/// Config body for the pick. The external path carries `model\0api_key`
/// internally so the key never crosses a panel; it is split here, at the
/// only place that writes the file.
fn picked_config_body(picked: &Phase6Report) -> String {
    if picked.provider == "litellm" {
        let (model, key) = picked
            .model
            .as_deref()
            .and_then(|packed| packed.split_once('\u{0}'))
            .unwrap_or(("", ""));
        external_config(SWAP_EXTERNAL_HEADER, model, key)
    } else if picked.provider == "none" {
        none_config(SWAP_NONE_HEADER)
    } else {
        local_config(
            SWAP_LOCAL_HEADER,
            picked.model.as_deref().unwrap_or_default(),
            picked.revision.as_deref(),
        )
    }
}

/// Step 4: download + test-embed gate (measured RSS) then re-index with the
/// new embedder. The live index stays servable: the replacement metadata is
/// staged on a `.swap` temp, never written live here.
struct PartialReport {
    model: String,
    dims: Option<u32>,
    rss_peak_bytes: Option<u64>,
    rows: u64,
}

fn download_gate_and_reindex(
    deps: &SwapDeps<'_>,
    vault: &Path,
    picked: &Phase6Report,
    token: Option<&str>,
    current: &CurrentState,
) -> Result<PartialReport, WizardError> {
    let Some(model) = picked.model.clone() else {
        // Path 5 (`none`): no download, no gate, no re-index — degraded.
        return Ok(PartialReport {
            model: String::new(),
            dims: None,
            rss_peak_bytes: None,
            rows: current.db_file_count,
        });
    };
    let (model_name, _api_key) = model
        .split_once('\u{0}')
        .map(|(name, key)| (name.to_string(), Some(key.to_string())))
        .unwrap_or((model, None));
    let (dims, rss) = if picked.provider == "local" {
        let gate = run_gate(
            deps.proc,
            vault,
            &model_name,
            picked.revision.as_deref(),
            token,
        )?;
        deps.ui.panel(
            "Embedding OK",
            &format!(
                "modelo {} · dims {} · RSS pico {}MB ({})",
                gate.model,
                gate.dims,
                (gate.rss_peak_bytes as f64 / BYTES_PER_MB) as u64,
                Provenance::Measured.label()
            ),
        );
        (Some(gate.dims), Some(gate.rss_peak_bytes))
    } else {
        (None, None)
    };
    let report_model = model_name.clone();
    let rows = run_refresh(deps.proc, vault)?;
    // Stage the replacement sidecar (live meta untouched until the commit).
    let body = format!(
        "{{\"model\":\"{}\",\"dims\":{}}}\n",
        json_escape(&model_name),
        dims.map(|dims| dims.to_string())
            .unwrap_or_else(|| "null".to_string())
    );
    let dir = vault.join(RUNTIME_DIR).join("db");
    std::fs::create_dir_all(&dir).map_err(|_| WizardError::PermissionDenied)?;
    let staged_meta = dir.join(META_SWAP_SUFFIX);
    std::fs::write(&staged_meta, body).map_err(|_| WizardError::PermissionDenied)?;
    set_user_private(&staged_meta)?;
    Ok(PartialReport {
        model: report_model,
        dims,
        rss_peak_bytes: rss,
        rows,
    })
}

/// Step 5: conmutar SOLO el sidecar (C1: la config ya vive desde antes del
/// refresh). La meta staged via rename en el mismo dir. A meta-rename fallido
/// el caller clama el abortSwap (config al snapshot, temps fuera).
fn commit_meta(vault: &Path, picked: &Phase6Report) -> Result<(), WizardError> {
    // shortcut: every fs failure maps to `PermissionDenied` (T7 convention).
    if picked.provider != "none" {
        let meta_live = index_meta_path(vault);
        let staged_meta = vault.join(RUNTIME_DIR).join("db").join(META_SWAP_SUFFIX);
        std::fs::rename(&staged_meta, &meta_live).map_err(map_fs_err)?;
    }
    Ok(())
}

fn map_fs_err(_: std::io::Error) -> WizardError {
    WizardError::PermissionDenied
}

/// Step 6: purge the previous model cache — only after the atomic switch, and
/// never with `--keep-previous`, never when old == new. Targets the HF slug
/// dirs (`models--<id con / → -->`, más el gemelo `sentence-transformers`)
/// bajo `models/` y `models/hub/`; los nombres planos del esquema antiguo son
/// decoys y se conservan. Las candidatas del modelo nuevo nunca se tocan.
fn gc_old_model(vault: &Path, old: Option<String>, new: Option<&str>, keep_previous: bool) {
    if keep_previous {
        return;
    }
    let (Some(old_model), Some(new_model)) = (old, new) else {
        return;
    };
    if old_model == new_model || new_model.is_empty() {
        return;
    }
    let protected = gc_candidate_dirs(new_model);
    for root in model_cache_roots(vault) {
        for name in gc_candidate_dirs(&old_model) {
            if protected.contains(&name) {
                continue;
            }
            remove_cache_entry(&root.join(name));
        }
    }
}

/// Slug dirs HF de un model id: `models--<id con / → -->`, más el gemelo con
/// prefijo `sentence-transformers` (en ambas direcciones: un id escueto
/// comparte caché con su forma `sentence-transformers/...` y viceversa).
fn gc_candidate_dirs(model: &str) -> Vec<String> {
    let slug = model.replace('/', "--");
    let mut out = vec![format!("models--{slug}")];
    const ST: &str = "sentence-transformers--";
    if let Some(rest) = slug.strip_prefix(ST) {
        let bare = format!("models--{rest}");
        if bare != out[0] {
            out.push(bare);
        }
    } else {
        out.push(format!("models--{ST}{slug}"));
    }
    out
}

/// Raíces del cache de modelos bajo el vault (`HF_HOME`/`SENTENCE_TRANSFORMERS_HOME`).
fn model_cache_roots(vault: &Path) -> [PathBuf; 2] {
    let base = vault.join(RUNTIME_DIR).join(MODELS_DIR);
    [base.clone(), base.join("hub")]
}

/// Borra una entrada de caché (dir slug HF o archivo suelto); ausente ⇒ nada.
fn remove_cache_entry(path: &Path) {
    match std::fs::symlink_metadata(path) {
        Ok(meta) if meta.is_dir() => {
            let _ = std::fs::remove_dir_all(path);
        }
        Ok(_) => {
            let _ = std::fs::remove_file(path);
        }
        Err(_) => {}
    }
}

/// Zero-state rollback: staged temps are removed by the caller; live config
/// and sidecar return to their snapshotted bytes (absent stays absent). The
/// live index and model caches were never touched before the commit, so they
/// need no restore.
fn rollback(vault: &Path, before: &Snapshot) {
    restore_or_remove(&config_path(vault), before.config.as_deref());
    restore_or_remove(&index_meta_path(vault), before.meta.as_deref());
}

fn restore_or_remove(target: &Path, before: Option<&[u8]>) {
    match before {
        Some(bytes) => {
            let _ = std::fs::write(target, bytes);
        }
        None => {
            let _ = std::fs::remove_file(target);
        }
    }
}

fn cleanup_staged(vault: &Path) {
    let _ = std::fs::remove_file(vault.join(RUNTIME_DIR).join("db").join(META_SWAP_SUFFIX));
    let _ = std::fs::remove_file(config_path(vault).with_extension("toml.tmp"));
    let _ = std::fs::remove_file(index_meta_path(vault).with_extension("json.tmp"));
}

/// Gate success payload (T12 programs the flow CLI against this shape).
#[derive(Debug, PartialEq, Eq)]
struct GateOk {
    model: String,
    dims: u32,
    rss_peak_bytes: u64,
}

/// `venv python -m tepochcalli_flow embed-check --model <id>` (shared spawn
/// trunk). Gate payload parsing stays local to the swap.
fn run_gate(
    proc: &dyn CommandRunner,
    vault: &Path,
    model_id: &str,
    revision: Option<&str>,
    token: Option<&str>,
) -> Result<GateOk, WizardError> {
    let mut args: Vec<&str> = vec!["-m", GATE_MODULE, GATE_SUBCOMMAND, "--model", model_id];
    if let Some(sha) = revision {
        args.push("--revision");
        args.push(sha);
    }
    let out = super::flow_cli::run_flow_cli(
        proc,
        vault,
        &args,
        &[],
        token,
        super::flow_cli::GATE_TIMEOUT,
    )?;
    parse_gate(&out.stdout)
}

/// `venv python -m tepochcalli_flow refresh` (T12 contract): returns the
/// replacement `scanned` count. `ok:false` maps to `ModelInvalid`, matching
/// the F7 portero parity.
fn run_refresh(proc: &dyn CommandRunner, vault: &Path) -> Result<u64, WizardError> {
    let out = super::flow_cli::run_flow_cli(
        proc,
        vault,
        &["-m", GATE_MODULE, REFRESH_SUBCOMMAND],
        &[],
        None,
        super::flow_cli::REFRESH_TIMEOUT,
    )?;
    parse_refresh(&out.stdout)
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

fn parse_refresh(body: &str) -> Result<u64, WizardError> {
    if json_bool(body, "ok") == Some(false) {
        return Err(WizardError::ModelInvalid);
    }
    match (
        json_u64(body, "scanned"),
        json_u64(body, "indexed"),
        json_u64(body, "skipped"),
        json_u64(body, "elapsed_ms"),
    ) {
        (Some(scanned), Some(_), Some(_), Some(_)) => Ok(scanned),
        _ => Err(WizardError::PhaseFailed),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_vault() -> tempfile::TempDir {
        match tempfile::tempdir() {
            Ok(dir) => dir,
            Err(err) => panic!("tempdir: {err}"),
        }
    }

    // ---- CLI contract parsers -------------------------------------------

    #[test]
    fn parse_gate_ok_yields_measured_fields() {
        match parse_gate("{\"ok\":true,\"model\":\"m\",\"dims\":384,\"rss_peak_bytes\":650000000}")
        {
            Ok(gate) => {
                assert_eq!(gate.model, "m");
                assert_eq!(gate.dims, 384);
                assert_eq!(gate.rss_peak_bytes, 650_000_000);
            }
            Err(err) => panic!("gate válido debe parsear, got: {err:?}"),
        }
    }

    #[test]
    fn parse_gate_refuses_aborts_and_missing_fields() {
        assert_eq!(
            parse_gate("{\"ok\":false,\"code\":\"E_MODEL_INVALID\"}"),
            Err(WizardError::ModelInvalid)
        );
        assert_eq!(parse_gate("garabato"), Err(WizardError::PhaseFailed));
        assert_eq!(
            parse_gate("{\"ok\":true,\"model\":\"m\",\"rss_peak_bytes\":1}"),
            Err(WizardError::Internal),
            "campo faltante no puede inventarse las dims"
        );
    }

    #[test]
    fn parse_refresh_returns_scanned_and_types_its_failures() {
        assert_eq!(
            parse_refresh(
                "{\"ok\":true,\"scanned\":10,\"indexed\":3,\"skipped\":7,\"elapsed_ms\":120}"
            ),
            Ok(10)
        );
        // `ok` ausente con los cuatro contadores: el contrato T12 lo admite.
        assert_eq!(
            parse_refresh("{\"scanned\":1,\"indexed\":0,\"skipped\":1,\"elapsed_ms\":5}"),
            Ok(1)
        );
        assert_eq!(
            parse_refresh("{\"ok\":false,\"code\":\"E_MODEL_INVALID\"}"),
            Err(WizardError::ModelInvalid)
        );
        assert_eq!(
            parse_refresh("{\"scanned\":1,\"indexed\":0,\"elapsed_ms\":5}"),
            Err(WizardError::PhaseFailed),
            "sin `skipped` no hay reporte"
        );
    }

    // ---- display helpers -------------------------------------------------

    #[test]
    fn estimate_secs_has_a_floor_and_grows_with_the_index() {
        assert_eq!(estimate_secs(0), 1);
        assert_eq!(estimate_secs(999_999), 1);
        assert_eq!(estimate_secs(1_000_000), 2);
        assert_eq!(estimate_secs(5_000_000), 10);
        assert_eq!(estimate_secs(10_000_000), 20);
        let monotonic = [0, 1_000_000, 2_500_000, 9_999_999, 10_000_000]
            .iter()
            .map(|bytes| estimate_secs(*bytes))
            .collect::<Vec<_>>();
        assert!(monotonic.windows(2).all(|pair| pair[0] <= pair[1]));
    }

    #[test]
    fn warning_names_the_model_and_the_estimate_without_the_api_key() {
        let picked = Phase6Report {
            provider: "litellm".to_string(),
            model: Some("openai/text-embedding-3-small\u{0}sk-SECRETO".to_string()),
            revision: None,
            dims: None,
            rss_peak_bytes: None,
        };
        let current = CurrentState {
            provider: Some("local".to_string()),
            model: Some("viejo".to_string()),
            dims: Some(384),
            db_file_count: 7,
            db_bytes: 4_000_000,
        };
        let text = warning(&picked, &current);
        assert!(
            !text.contains("sk-SECRETO"),
            "la clave no puede llegar a un panel:\n{text}"
        );
        assert!(
            text.contains("openai/text-embedding-3-small"),
            "got:\n{text}"
        );
        assert!(text.contains("≈8 s"), "4MB ⇒ 8 s, got:\n{text}");
        assert!(text.contains("ficheros en db/: 7"), "got:\n{text}");
    }

    // ---- model cache GC --------------------------------------------------

    #[test]
    fn gc_candidate_dirs_covers_slash_and_flat_ids() {
        assert_eq!(
            gc_candidate_dirs("org/model"),
            vec![
                "models--org--model".to_string(),
                "models--sentence-transformers--org--model".to_string()
            ]
        );
        assert_eq!(
            gc_candidate_dirs("all-MiniLM-L6-v2"),
            vec![
                "models--all-MiniLM-L6-v2".to_string(),
                "models--sentence-transformers--all-MiniLM-L6-v2".to_string()
            ]
        );
    }

    #[test]
    fn gc_candidate_dirs_maps_the_sentence_transformers_twin_both_ways() {
        let st = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2";
        let dirs = gc_candidate_dirs(st);
        assert_eq!(
            dirs,
            vec![
                "models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2".to_string(),
                "models--paraphrase-multilingual-MiniLM-L12-v2".to_string()
            ]
        );
        // El gemelo inverso: un id escueto protege también su forma ST.
        let bare = gc_candidate_dirs("paraphrase-multilingual-MiniLM-L12-v2");
        assert_eq!(bare.len(), 2);
        assert_eq!(
            bare[1],
            format!(
                "models--sentence-transformers--{}",
                bare[0].trim_start_matches("models--")
            )
        );
    }

    #[test]
    fn model_cache_roots_point_at_models_and_its_hub() {
        let vault = Path::new("/v");
        let roots = model_cache_roots(vault);
        assert_eq!(roots[0], vault.join(".tepochcalli").join("models"));
        assert_eq!(
            roots[1],
            vault.join(".tepochcalli").join("models").join("hub")
        );
    }

    // ---- commit: estado final tras un fallo ------------------------------

    fn picked_local() -> Phase6Report {
        Phase6Report {
            provider: "local".to_string(),
            model: Some("BAAI/bge-m3".to_string()),
            revision: Some("5617a9f61b028005a4858fdac845db406aefb181".to_string()),
            dims: Some(1024),
            rss_peak_bytes: None,
        }
    }

    /// Config staged lista y destino del sidecar ocupado por un directorio no
    /// vacío: el segundo rename del `commit` falla con cualquier uid (`EISDIR`;
    /// un `chmod 0555` no vale porque root lo atraviesa).
    fn vault_with_failing_meta_rename(config: Option<&[u8]>) -> tempfile::TempDir {
        let vault = temp_vault();
        let runtime = vault.path().join(RUNTIME_DIR);
        for dir in ["config", "db"] {
            if let Err(err) = std::fs::create_dir_all(runtime.join(dir)) {
                panic!("fixture {dir}: {err}");
            }
        }
        if let Some(bytes) = config {
            if let Err(err) = std::fs::write(config_path(vault.path()), bytes) {
                panic!("fixture config: {err}");
            }
        }
        if let Err(err) = std::fs::write(
            runtime.join("db").join(META_SWAP_SUFFIX),
            b"{\"model\":\"m\",\"dims\":1}\n",
        ) {
            panic!("fixture staged meta: {err}");
        }
        let meta = index_meta_path(vault.path());
        if let Err(err) = std::fs::create_dir_all(meta.join("occupied")) {
            panic!("fixture meta dir: {err}");
        }
        if let Err(err) = std::fs::write(meta.join("marker"), b"sidecar-ilegible") {
            panic!("fixture marker: {err}");
        }
        vault
    }

    /// C1: el commit solo conmuta la meta. Un rename de meta que falla
    /// devuelve el tipado y NO toca la config viva (el rollback es labor del
    /// caller via abort_swap — más arriba en run_swap).
    #[test]
    fn failed_meta_commit_types_the_failure_and_leaves_the_live_config() {
        let previous: &[u8] = b"# previa\n[embedding]\nprovider = \"local\"\n";
        let vault = vault_with_failing_meta_rename(Some(previous));
        assert_eq!(
            commit_meta(vault.path(), &picked_local()),
            Err(WizardError::PermissionDenied)
        );
        assert_eq!(
            std::fs::read(config_path(vault.path())).ok().as_deref(),
            Some(previous),
            "el commit_meta no toca la config viva"
        );
        assert_eq!(
            std::fs::read(index_meta_path(vault.path()).join("marker")).ok(),
            Some(b"sidecar-ilegible".to_vec()),
            "el rollback no destruye lo que no conmutó"
        );
    }
}
