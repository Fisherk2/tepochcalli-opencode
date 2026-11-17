//! Soporte específico del contrato del swap D8.4 (T16): fixtures de vault
//! instalado con caches HF realistas, familias de aserción del GC, snapshot
//! byte-idéntico, el fake `CheckingProc` del invariante de servabilidad y
//! los adaptadores de captura de la `TapUi`.
//!
//! Es soporte de test, no un target (Cargo solo compila `tests/*.rs`; lo
//! consume `e2e_swap.rs`).

use std::cell::RefCell;
use std::collections::{HashMap, VecDeque};
use std::path::{Path, PathBuf};

use super::{host_16gb, seed_runtime, FakeHost, FakeHttp, RecordingProc, TapUi, UiEvent};
use tepochcalli::application::swap::{run_swap, SwapDeps, SwapOptions, SwapReport};
use tepochcalli::domain::WizardError;
use tepochcalli::ports::{CommandOutput, CommandRunner, Ui};

pub const OLD_MODEL: &str = "paraphrase-multilingual-MiniLM-L12-v2";
pub const NEW_MODEL: &str = "BAAI/bge-m3";
/// sentence-transformers-qualified twin of the default old model.
pub const OLD_MODEL_ST: &str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2";
/// Unrelated third-party cache no swap may ever touch.
pub const OTHER_MODEL_DIR: &str = "models--sentence-transformers--all-MiniLM-L6-v2";

pub fn tmp() -> tempfile::TempDir {
    tempfile::tempdir().expect("tempdir for T16 fixtures")
}

/// Vault ya instalado: config local + sidecar de índice + índice vivo +
/// caches realistas del modelo viejo (slug dirs HF bajo `models/` y
/// `models/hub/`) + decoy con el nombre del esquema antiguo (debe sobrevivir:
/// el GC viejo lo purgaba por error) + cache no relacionada + caché del
/// modelo nuevo (ya descargada por el gate; debe sobrevivir) + intérprete.
pub fn installed_vault() -> tempfile::TempDir {
    installed_vault_with(OLD_MODEL, &[NEW_MODEL])
}

pub fn installed_vault_with(old_model: &str, extra_cached: &[&str]) -> tempfile::TempDir {
    let vault = tmp();
    seed_runtime(vault.path(), old_model, old_model);
    let rt = vault.path().join(".tepochcalli");
    let mut cached = vec![old_model];
    cached.extend_from_slice(extra_cached);
    for model in cached {
        for dir in slug_dirs(model) {
            for root in [rt.join("models"), rt.join("models").join("hub")] {
                let marker = root.join(&dir).join("snapshots").join("marker");
                std::fs::create_dir_all(marker.parent().expect("marker parent"))
                    .expect("model cache dir fixture");
                std::fs::write(&marker, b"old-model-cache-bytes").expect("model cache fixture");
            }
        }
    }
    // Decoy con el esquema antiguo de nombre plano: el GC correcto no lo toca.
    std::fs::write(
        rt.join("models").join(legacy_decoy_name(old_model)),
        b"decoy-bytes",
    )
    .expect("decoy fixture");
    let other = rt
        .join("models")
        .join(OTHER_MODEL_DIR)
        .join("snapshots")
        .join("marker");
    std::fs::create_dir_all(other.parent().expect("other parent")).expect("other dir fixture");
    std::fs::write(&other, b"other-model-cache-bytes").expect("other cache fixture");
    vault
}

/// Esquema antiguo (erróneo) de nombre plano: no alfanumérico → `_`.
/// Solo vive en los tests como decoy que debe sobrevivir al GC.
pub fn legacy_decoy_name(model: &str) -> String {
    model
        .chars()
        .map(|c| {
            if c.is_ascii_alphanumeric() || c == '.' || c == '-' {
                c
            } else {
                '_'
            }
        })
        .collect()
}

/// Slug dirs HF de un model id: `models--<id con / → -->`, más el gemelo
/// con prefijo `sentence-transformers` (en ambas direcciones). Replica el
/// contrato del GC; si divergen, estos tests lo delatan.
pub fn slug_dirs(model: &str) -> Vec<String> {
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

/// Todas las raíces donde el GC debe buscar: `models/` y `models/hub/`.
pub fn cache_roots(vault: &Path) -> [PathBuf; 2] {
    let base = vault.join(".tepochcalli").join("models");
    [base.clone(), base.join("hub")]
}

pub fn assert_old_slug_dirs_present(vault: &Path, model: &str) {
    for root in cache_roots(vault) {
        for dir in slug_dirs(model) {
            let marker = root.join(&dir).join("snapshots").join("marker");
            assert!(
                marker.is_file(),
                "la caché vieja debe seguir intacta: {}",
                marker.display()
            );
        }
    }
}

pub fn assert_old_slug_dirs_gone(vault: &Path, model: &str) {
    for root in cache_roots(vault) {
        for dir in slug_dirs(model) {
            let gone = root.join(&dir);
            assert!(
                !gone.exists(),
                "la caché vieja debe purgarse: {}",
                gone.display()
            );
        }
    }
}

pub fn assert_survivors_intact(vault: &Path, old_model: &str, new_model: &str) {
    let rt = vault.join(".tepochcalli");
    for dir in slug_dirs(new_model) {
        let marker = rt
            .join("models")
            .join(&dir)
            .join("snapshots")
            .join("marker");
        assert!(
            marker.is_file(),
            "la caché del modelo nuevo debe sobrevivir: {}",
            marker.display()
        );
    }
    assert_eq!(
        std::fs::read(
            rt.join("models")
                .join(OTHER_MODEL_DIR)
                .join("snapshots")
                .join("marker")
        )
        .expect("other cache readable"),
        b"other-model-cache-bytes",
        "la caché no relacionada debe sobrevivir"
    );
    assert_eq!(
        std::fs::read(rt.join("models").join(legacy_decoy_name(old_model)))
            .expect("decoy readable"),
        b"decoy-bytes",
        "el decoy del esquema antiguo debe sobrevivir"
    );
}

pub fn refresh_ok(indexed: u64) -> Result<CommandOutput, WizardError> {
    Ok(CommandOutput {
        status: 0,
        stdout: format!("{{\"scanned\":2,\"indexed\":{indexed},\"skipped\":0,\"elapsed_ms\":9}}"),
        stderr: String::new(),
    })
}

pub fn empty_http() -> FakeHttp {
    FakeHttp::new(HashMap::new())
}

pub fn deps<'a>(
    ui: &'a dyn Ui,
    host: &'a FakeHost,
    proc: &'a dyn CommandRunner,
    http: &'a FakeHttp,
) -> SwapDeps<'a> {
    SwapDeps {
        ui,
        host,
        proc,
        http,
    }
}

pub fn confirmed() -> SwapOptions {
    SwapOptions {
        confirm: true,
        keep_previous: false,
    }
}

/// Config + sidecar + índice vivo + marker de caché vieja + decoy.
pub type FileSnapshot = (Vec<u8>, Vec<u8>, Vec<u8>, Vec<u8>, Vec<u8>);

pub fn snapshot(vault: &Path) -> FileSnapshot {
    let rt = vault.join(".tepochcalli");
    (
        std::fs::read(rt.join("config").join("tepochcalli.toml")).expect("config snap"),
        std::fs::read(rt.join("db").join("index-meta.json")).expect("meta snap"),
        std::fs::read(rt.join("db").join("chunks.lance")).expect("index snap"),
        std::fs::read(
            rt.join("models")
                .join("models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2")
                .join("snapshots")
                .join("marker"),
        )
        .expect("model snap"),
        std::fs::read(rt.join("models").join(legacy_decoy_name(OLD_MODEL))).expect("decoy snap"),
    )
}

pub fn assert_byte_identical(vault: &Path, before: &FileSnapshot) {
    let after = snapshot(vault);
    assert_eq!(after.0, before.0, "la config debe quedar byte-idéntica");
    assert_eq!(
        after.1, before.1,
        "el sidecar del índice debe quedar byte-idéntico"
    );
    assert_eq!(after.2, before.2, "el índice vivo debe seguir servable");
    assert_eq!(after.3, before.3, "el modelo viejo debe seguir intacto");
    assert_eq!(after.4, before.4, "el decoy debe seguir intacto");
    assert_old_slug_dirs_present(vault, OLD_MODEL);
}

pub fn no_stray_temps(vault: &Path) {
    let rt = vault.join(".tepochcalli");
    for candidate in [
        rt.join("config").join("tepochcalli.toml.tmp"),
        rt.join("config").join("tepochcalli.toml.swap"),
        rt.join("db").join("index-meta.json.tmp"),
        rt.join("db").join("index-meta.json.swap"),
    ] {
        assert!(
            !candidate.exists(),
            "ningún temporal puede fugarse: {}",
            candidate.display()
        );
    }
}

/// Corrida estándar de swap (T16): vault dado, fila(s) del menú + respuestas
/// de `input`, guion de procesos e `HttpClient`; `opts` (los exitosos pasan
/// `confirmed()`). Devuelve el resultado y la UI/proceso para las aserciones
/// propias de cada caso.
pub fn run_swap_case(
    vault: &Path,
    selects: Vec<usize>,
    inputs: Vec<String>,
    script: Vec<Result<CommandOutput, WizardError>>,
    http: FakeHttp,
    opts: &SwapOptions,
) -> (Result<SwapReport, WizardError>, TapUi, RecordingProc) {
    let ui = TapUi::new(selects, inputs);
    let host = host_16gb();
    let proc = RecordingProc::scripted(script);
    let result = run_swap(&deps(&ui, &host, &proc, &http), vault, opts);
    (result, ui, proc)
}

/// El texto visible completo de la UI (títulos + cuerpos + prompts): la
/// superficie sobre la que se aserta que clave/token nunca salen.
pub fn visible_text(ui: &TapUi) -> String {
    format!("{}\n{}", titles(ui).join("\n"), bodies(ui).join("\n"))
}

/// Un título de panel/prompt menciona `needle` (los títulos llevan los
/// marcadores de canal de los prompts y los títulos reales de los paneles).
pub fn panel_mentions(ui: &TapUi, needle: &str) -> bool {
    titles(ui).iter().any(|line| line.contains(needle))
}

/// Sin spawns registrados; el mensaje explica por qué deben ser cero.
pub fn assert_no_spawns(proc: &RecordingProc, why: &str) {
    assert!(proc.calls().is_empty(), "{why}, argv: {:?}", argv(proc));
}

/// Cierre de rollback: byte-idéntico al snapshot previo + sin temporales.
pub fn assert_zero_state(vault: &Path, before: &FileSnapshot) {
    assert_byte_identical(vault, before);
    no_stray_temps(vault);
}

/// Cierre de un swap completado: slug dirs del modelo viejo según `purged`,
/// supervivientes intactos y cero temporales.
pub fn assert_gc_outcome(vault: &Path, old_model: &str, new_model: &str, purged: bool) {
    if purged {
        assert_old_slug_dirs_gone(vault, old_model);
    } else {
        assert_old_slug_dirs_present(vault, old_model);
    }
    assert_survivors_intact(vault, old_model, new_model);
    no_stray_temps(vault);
}

/// Sabotaje del segundo rename: el sidecar destino es un directorio no vacío
/// ⇒ `rename(2)` devuelve `EISDIR` y el commit muere (root incluido).
pub fn sidecar_becomes_nonempty_dir(rt: &Path) {
    let meta_path = rt.join("db").join("index-meta.json");
    std::fs::remove_file(&meta_path).expect("sidecar fixture removible");
    std::fs::create_dir_all(&meta_path).expect("sidecar como directorio");
    std::fs::write(meta_path.join("marker"), b"unreadable-sidecar").expect("marker del sidecar");
}

/// Títulos en orden (superset del `TapUi` local anterior): los prompts van
/// con su marcador de canal (`MENU`/`INPUT`/`SECRET INPUT`) y los paneles
/// con su título real — la secuencia prueba los 6 pasos de D8.4 en orden.
pub fn titles(ui: &TapUi) -> Vec<String> {
    ui.events()
        .iter()
        .map(|event| match event {
            UiEvent::Panel { title, .. } => title.clone(),
            UiEvent::Select { .. } => "MENU".to_string(),
            UiEvent::Input { .. } => "INPUT".to_string(),
            UiEvent::Secret { .. } => "SECRET INPUT".to_string(),
        })
        .collect()
}

/// Cuerpos/prompt en orden, alineados con `titles`.
pub fn bodies(ui: &TapUi) -> Vec<String> {
    ui.events()
        .iter()
        .map(|event| match event {
            UiEvent::Panel { body, .. } => body.clone(),
            UiEvent::Select { prompt, .. }
            | UiEvent::Input { prompt }
            | UiEvent::Secret { prompt } => prompt.clone(),
        })
        .collect()
}

/// argv de cada hijo registrado (una lista por llamada).
pub fn argv(proc: &RecordingProc) -> Vec<Vec<String>> {
    proc.calls().into_iter().map(|call| call.args).collect()
}

/// ¿Corrió el gate test-embed (`embed-check --model`)?
pub fn gated(proc: &RecordingProc) -> bool {
    proc.calls()
        .iter()
        .any(|call| call.args.iter().any(|arg| arg == "embed-check"))
}

/// ¿Corrió el re-index (`refresh`)?
pub fn refreshed(proc: &RecordingProc) -> bool {
    proc.calls()
        .iter()
        .any(|call| call.args.iter().any(|arg| arg == "refresh"))
}

/// HF API base del pre-chequeo D8.1 (contrato de `pending_free_id`).
pub const HF_API: &str = "https://huggingface.co/api/models/";

/// `FakeHttp` sirviendo exactamente la metadata de ese id.
pub fn http_serving(id: &str, body: &str) -> FakeHttp {
    FakeHttp::new(HashMap::from([(
        format!("{HF_API}{id}"),
        body.as_bytes().to_vec(),
    )]))
}

pub const EXTERNAL_MODEL: &str = "openai/text-embedding-3-small";
/// Clave señuelo: si aparece fuera de la config gitignored, el test lo delata.
pub const FAKE_KEY: &str = "sk-LEAK-TEST-0123456789abcdef";

pub const GATED_ID: &str = "org/gated-embed-model";
/// Token señuelo: solo puede aparecer en el env del hijo del gate.
pub const GATED_TOKEN: &str = "hf_LEAK-TEST-gated-token-0987";

/// Live-file snapshot the mid-flight check compares against. El campo 2
/// (config) es el FRAGMENTO que la config viva debe contener en cada spawn
/// (C1: la config elegida vive antes del gate/refresh).
pub type LiveSnapshot = (PathBuf, String, Vec<u8>, Vec<u8>, Vec<u8>, Vec<u8>);

/// `CommandRunner` fake that proves the D8.4 servability invariant mid-flight:
/// every proc call (gate, refresh) runs while the live sidecar, index and
/// model cache are still byte-identical to the pre-swap snapshot, y la config
/// viva ya lleva el nuevo embedder (captura + assert, pin del auditor).
/// A swap que reconstruyera la db viva in place falla aquí.
pub struct CheckingProc {
    script: RefCell<VecDeque<Result<CommandOutput, WizardError>>>,
    expected: RefCell<Option<LiveSnapshot>>,
    /// C1: la config viva capturada EN CADA spawn (gate/refresh).
    config_seen: RefCell<Vec<String>>,
}

impl CheckingProc {
    pub fn scripted(script: impl IntoIterator<Item = Result<CommandOutput, WizardError>>) -> Self {
        Self {
            script: RefCell::new(script.into_iter().collect()),
            expected: RefCell::new(None),
            config_seen: RefCell::new(Vec::new()),
        }
    }

    pub fn configs_seen(&self) -> Vec<String> {
        self.config_seen.borrow().clone()
    }

    pub fn expect_live(
        &self,
        vault: &Path,
        config_fragment: &str,
        meta: &[u8],
        index: &[u8],
        model: &[u8],
        decoy: &[u8],
    ) {
        *self.expected.borrow_mut() = Some((
            vault.to_path_buf(),
            config_fragment.to_string(),
            meta.to_vec(),
            index.to_vec(),
            model.to_vec(),
            decoy.to_vec(),
        ));
    }
}

impl CommandRunner for CheckingProc {
    fn run(
        &self,
        _program: &str,
        _args: &[&str],
        _cwd: &Path,
        _env: &[(&str, &str)],
    ) -> Result<CommandOutput, WizardError> {
        let guard = self.expected.borrow();
        let (vault, config_fragment, meta, index, model, decoy) =
            guard.as_ref().expect("expect_live must be armed first");
        let rt = vault.join(".tepochcalli");
        // C1: la config viva YA lleva el nuevo embedder durante el
        // gate/refresh — captura por spawn (pin del auditor).
        let live_config_bytes = std::fs::read(rt.join("config").join("tepochcalli.toml"))
            .expect("live config readable");
        let live_config = String::from_utf8_lossy(&live_config_bytes).into_owned();
        self.config_seen.borrow_mut().push(live_config.clone());
        assert!(
            live_config.contains(config_fragment),
            "la config viva en el spawn debe llevar el nuevo embedder, got:\n{live_config}"
        );
        // Lo vivo (sidecar, índice, modelo viejo, decoy) intacto en cada spawn.
        let read_eq = |path: std::path::PathBuf, expected: &[u8], why: &str| {
            assert_eq!(
                std::fs::read(path).expect("live file readable"),
                *expected,
                "{why}"
            );
        };
        read_eq(
            rt.join("db").join("index-meta.json"),
            meta,
            "el sidecar vivo no se toca durante el reemplazo",
        );
        read_eq(
            rt.join("db").join("chunks.lance"),
            index,
            "el índice viejo sigue servable durante el reemplazo",
        );
        read_eq(
            rt.join("models")
                .join("models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2")
                .join("snapshots")
                .join("marker"),
            model,
            "el modelo viejo no se toca durante el reemplazo",
        );
        read_eq(
            rt.join("models").join(legacy_decoy_name(OLD_MODEL)),
            decoy,
            "el decoy no se toca durante el reemplazo",
        );
        drop(guard);
        self.script
            .borrow_mut()
            .pop_front()
            .unwrap_or(Err(WizardError::Internal))
    }
}
