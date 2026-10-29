//! Swap atómico D8.4 (T16): `tepochcalli config embedder` sobre un vault
//! ya instalado.
//!
//! RED-first: todo aquí fallaba antes de que existiera
//! `application::swap::run_swap`. Vaults `tempfile` reales (D26: sin puerto
//! FS); solo fakes (`TapUi` local que graba paneles, `FakeProc`, `FakeHost`,
//! `FakeHttp`). Ningún modelo se descarga: los fixtures `gate_ok`/`refresh_ok`
//! replican los contratos T11/T12.

#[allow(dead_code)]
mod common;

use std::cell::RefCell;
use std::collections::{HashMap, VecDeque};
use std::path::{Path, PathBuf};

use common::{FakeHost, FakeHttp, FakeProc};
use tepochcalli::application::swap::{run_swap, SwapDeps, SwapOptions};
use tepochcalli::domain::WizardError;
use tepochcalli::ports::{CommandOutput, CommandRunner, Ui};
use tepochcalli::RagHealth;

const OLD_MODEL: &str = "paraphrase-multilingual-MiniLM-L12-v2";
const NEW_MODEL: &str = "BAAI/bge-m3";
/// sentence-transformers-qualified twin of the default old model.
const OLD_MODEL_ST: &str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2";
/// Unrelated third-party cache no swap may ever touch.
const OTHER_MODEL_DIR: &str = "models--sentence-transformers--all-MiniLM-L6-v2";

fn tmp() -> tempfile::TempDir {
    tempfile::tempdir().expect("tempdir for T16 fixtures")
}

/// Vault ya instalado: config local + sidecar de índice + índice vivo +
/// caches realistas del modelo viejo (slug dirs HF bajo `models/` y
/// `models/hub/`) + decoy con el nombre del esquema antiguo (debe sobrevivir:
/// el GC viejo lo purgaba por error) + cache no relacionada + caché del
/// modelo nuevo (ya descargada por el gate; debe sobrevivir) + intérprete.
fn installed_vault() -> tempfile::TempDir {
    installed_vault_with(OLD_MODEL, &[NEW_MODEL])
}

fn installed_vault_with(old_model: &str, extra_cached: &[&str]) -> tempfile::TempDir {
    let vault = tmp();
    let rt = vault.path().join(".tepochcalli");
    std::fs::create_dir_all(rt.join("config")).expect("config dir fixture");
    std::fs::create_dir_all(rt.join("db")).expect("db dir fixture");
    std::fs::create_dir_all(rt.join("models")).expect("models dir fixture");
    std::fs::write(
        rt.join("config").join("tepochcalli.toml"),
        format!("[embedding]\nprovider = \"local\"\nmodel = \"{old_model}\"\n"),
    )
    .expect("config fixture");
    std::fs::write(
        rt.join("db").join("index-meta.json"),
        format!("{{\"model\":\"{old_model}\",\"dims\":384}}\n"),
    )
    .expect("index-meta fixture");
    std::fs::write(rt.join("db").join("chunks.lance"), b"live-index-bytes")
        .expect("live index fixture");
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
    let python = rt.join("venv").join("bin").join("python");
    std::fs::create_dir_all(python.parent().expect("venv bin parent")).expect("venv fixture dir");
    std::fs::write(&python, b"fake-python").expect("venv python fixture");
    vault
}

/// Esquema antiguo (erróneo) de nombre plano: no alfanumérico → `_`.
/// Solo vive en los tests como decoy que debe sobrevivir al GC.
fn legacy_decoy_name(model: &str) -> String {
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
fn slug_dirs(model: &str) -> Vec<String> {
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
fn cache_roots(vault: &Path) -> [PathBuf; 2] {
    let base = vault.join(".tepochcalli").join("models");
    [base.clone(), base.join("hub")]
}

fn assert_old_slug_dirs_present(vault: &Path, model: &str) {
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

fn assert_old_slug_dirs_gone(vault: &Path, model: &str) {
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

fn assert_survivors_intact(vault: &Path, old_model: &str, new_model: &str) {
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

fn gate_ok(model: &str, dims: u32, rss: u64) -> Result<CommandOutput, WizardError> {
    Ok(CommandOutput {
        status: 0,
        stdout: format!(
            "{{\"ok\":true,\"model\":\"{model}\",\"dims\":{dims},\"rss_peak_bytes\":{rss}}}"
        ),
        stderr: String::new(),
    })
}

fn refresh_ok(indexed: u64) -> Result<CommandOutput, WizardError> {
    Ok(CommandOutput {
        status: 0,
        stdout: format!("{{\"scanned\":2,\"indexed\":{indexed},\"skipped\":0,\"elapsed_ms\":9}}"),
        stderr: String::new(),
    })
}

/// `Ui` fake: respuestas guionadas + captura ordenada de paneles (la
/// secuencia de títulos prueba los 6 pasos de D8.4 en orden).
struct TapUi {
    selects: RefCell<VecDeque<usize>>,
    inputs: RefCell<VecDeque<String>>,
    panels: RefCell<Vec<(String, String)>>,
}

impl TapUi {
    fn new(selects: Vec<usize>, inputs: Vec<String>) -> Self {
        Self {
            selects: RefCell::new(selects.into()),
            inputs: RefCell::new(inputs.into()),
            panels: RefCell::new(Vec::new()),
        }
    }

    fn titles(&self) -> Vec<String> {
        self.panels
            .borrow()
            .iter()
            .map(|(title, _)| title.clone())
            .collect()
    }

    fn bodies(&self) -> Vec<String> {
        self.panels
            .borrow()
            .iter()
            .map(|(_, body)| body.clone())
            .collect()
    }
}

impl Ui for TapUi {
    fn select(
        &self,
        prompt: &str,
        _options: &[&str],
        _default_index: usize,
    ) -> Result<usize, WizardError> {
        self.panels
            .borrow_mut()
            .push(("MENU".to_string(), prompt.to_string()));
        self.selects
            .borrow_mut()
            .pop_front()
            .ok_or(WizardError::UserAborted)
    }

    fn input(&self, prompt: &str, _default: Option<&str>) -> Result<String, WizardError> {
        self.panels
            .borrow_mut()
            .push(("INPUT".to_string(), prompt.to_string()));
        self.inputs
            .borrow_mut()
            .pop_front()
            .ok_or(WizardError::UserAborted)
    }

    fn confirm(&self, prompt: &str, _default: bool) -> Result<bool, WizardError> {
        self.panels
            .borrow_mut()
            .push(("CONFIRM".to_string(), prompt.to_string()));
        Err(WizardError::UserAborted)
    }

    fn panel(&self, title: &str, body: &str) {
        self.panels
            .borrow_mut()
            .push((title.to_string(), body.to_string()));
    }
}

fn host_16gb() -> FakeHost {
    FakeHost::new(Some(16.0), Some(16.0), Some(100.0), None)
}

fn empty_http() -> FakeHttp {
    FakeHttp::new(HashMap::new())
}

fn deps<'a>(
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

fn confirmed() -> SwapOptions {
    SwapOptions {
        confirm: true,
        keep_previous: false,
    }
}

/// Config + sidecar + índice vivo + marker de caché vieja + decoy.
type FileSnapshot = (Vec<u8>, Vec<u8>, Vec<u8>, Vec<u8>, Vec<u8>);

fn snapshot(vault: &Path) -> FileSnapshot {
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

fn assert_byte_identical(vault: &Path, before: &FileSnapshot) {
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

fn no_stray_temps(vault: &Path) {
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

#[test]
fn swap_success_runs_six_steps_in_order_and_purges_old_model() {
    let vault = installed_vault();
    let ui = TapUi::new(vec![1], vec![]);
    let host = host_16gb();
    let proc = FakeProc::scripted([gate_ok(NEW_MODEL, 1024, 3_000_000_000), refresh_ok(2)]);
    let http = empty_http();

    let report = run_swap(&deps(&ui, &host, &proc, &http), vault.path(), &confirmed())
        .expect("el swap confirmado con gate+refresh OK debe triunfar");

    assert_eq!(report.model.as_str(), NEW_MODEL);
    assert_eq!(report.dims, Some(1024));

    // Paso 1→3→6: estado actual, menú, advertencia y cierre, en orden.
    let titles = ui.titles();
    let pos = |needle: &str| {
        titles
            .iter()
            .position(|t| t.contains(needle))
            .unwrap_or_else(|| panic!("falta el paso «{needle}», títulos: {titles:?}"))
    };
    assert!(
        pos("Estado actual") < pos("MENU"),
        "el estado actual precede al menú, títulos: {titles:?}"
    );
    assert!(
        pos("MENU") < pos("re-index"),
        "la advertencia sigue al menú, títulos: {titles:?}"
    );
    assert!(
        pos("re-index") < pos("Swap completo"),
        "el cierre sigue a la advertencia, títulos: {titles:?}"
    );
    // El estado actual muestra modelo, dims y tamaño; la advertencia nombra
    // el re-index completo y exige --confirm con tiempo estimado.
    let bodies = ui.bodies().join("\n");
    assert!(
        bodies.contains(OLD_MODEL),
        "el estado muestra el modelo viejo"
    );
    assert!(bodies.contains("384"), "el estado muestra las dims viejas");
    assert!(
        bodies.contains("--confirm"),
        "la advertencia exige --confirm"
    );

    // Conmutación atómica: config + sidecar nuevos, índice vivo intacto.
    let rt = vault.path().join(".tepochcalli");
    let config = std::fs::read_to_string(rt.join("config").join("tepochcalli.toml"))
        .expect("config tras el swap");
    assert!(
        config.contains(NEW_MODEL),
        "config conmutada, got:\n{config}"
    );
    let meta = std::fs::read_to_string(rt.join("db").join("index-meta.json"))
        .expect("sidecar tras el swap");
    assert!(
        meta.contains(NEW_MODEL) && meta.contains("1024"),
        "got:\n{meta}"
    );
    assert_eq!(
        std::fs::read(rt.join("db").join("chunks.lance")).expect("índice vivo"),
        b"live-index-bytes",
        "el índice viejo sigue servible tras el éxito"
    );
    // Auto-GC: solo los slug dirs HF del modelo viejo se purgan (ambas
    // raíces); el decoy del esquema antiguo, la caché no relacionada y la
    // caché del modelo nuevo sobreviven. Sin fugas de temporales.
    assert_old_slug_dirs_gone(vault.path(), OLD_MODEL);
    assert_survivors_intact(vault.path(), OLD_MODEL, NEW_MODEL);
    no_stray_temps(vault.path());
}

#[test]
fn swap_missing_confirm_explains_and_mutates_nothing() {
    let vault = installed_vault();
    let before = snapshot(vault.path());
    let ui = TapUi::new(vec![1], vec![]);
    let host = host_16gb();
    // Guion vacío: cualquier spawn devuelve `Internal` y revienta el test,
    // luego `Ok` aquí prueba que sin --confirm nada se descarga ni reindexa.
    let proc = FakeProc::scripted([]);
    let http = empty_http();

    let err = run_swap(
        &deps(&ui, &host, &proc, &http),
        vault.path(),
        &SwapOptions {
            confirm: false,
            keep_previous: false,
        },
    )
    .expect_err("sin --confirm el swap no debe correr");
    assert_eq!(err, WizardError::UserAborted);

    let bodies = ui.bodies().join("\n");
    assert!(
        bodies.contains("--confirm"),
        "debe explicar que el re-index exige --confirm, got:\n{bodies}"
    );
    assert!(
        bodies.to_lowercase().contains("irreversible"),
        "debe advertir que el re-index es irreversible, got:\n{bodies}"
    );
    assert_byte_identical(vault.path(), &before);
    no_stray_temps(vault.path());
}

#[test]
fn swap_interrupted_download_rolls_back_to_zero_state() {
    let vault = installed_vault();
    let before = snapshot(vault.path());
    let ui = TapUi::new(vec![1], vec![]);
    let host = host_16gb();
    let proc = FakeProc::scripted([Err(WizardError::NetDownload)]);
    let http = empty_http();

    let err = run_swap(&deps(&ui, &host, &proc, &http), vault.path(), &confirmed())
        .expect_err("la descarga interrumpida debe fallar el swap");
    assert_eq!(err, WizardError::NetDownload);

    // Cambio de estado cero: config/índice/modelo byte-idénticos, índice
    // viejo legible (servable) y sin temporales.
    assert_byte_identical(vault.path(), &before);
    no_stray_temps(vault.path());
}

#[test]
fn swap_failed_refresh_rolls_back_to_zero_state() {
    let vault = installed_vault();
    let before = snapshot(vault.path());
    let ui = TapUi::new(vec![1], vec![]);
    let host = host_16gb();
    let proc = FakeProc::scripted([
        gate_ok(NEW_MODEL, 1024, 3_000_000_000),
        Err(WizardError::PhaseFailed),
    ]);
    let http = empty_http();

    let err = run_swap(&deps(&ui, &host, &proc, &http), vault.path(), &confirmed())
        .expect_err("el refresh fallido debe fallar el swap");
    assert_eq!(err, WizardError::PhaseFailed);

    assert_byte_identical(vault.path(), &before);
    no_stray_temps(vault.path());
}

#[test]
fn swap_rejected_gate_rolls_back_to_zero_state() {
    let vault = installed_vault();
    let before = snapshot(vault.path());
    let ui = TapUi::new(vec![1], vec![]);
    let host = host_16gb();
    let proc = FakeProc::scripted([Ok(CommandOutput {
        status: 0,
        stdout: "{\"ok\":false,\"code\":\"E_MODEL_INVALID\"}".to_string(),
        stderr: String::new(),
    })]);
    let http = empty_http();

    let err = run_swap(&deps(&ui, &host, &proc, &http), vault.path(), &confirmed())
        .expect_err("el gate rechazado debe fallar el swap");
    assert_eq!(err, WizardError::ModelInvalid);

    assert_byte_identical(vault.path(), &before);
    no_stray_temps(vault.path());
}

#[test]
fn swap_keep_previous_retains_old_model() {
    let vault = installed_vault();
    let ui = TapUi::new(vec![1], vec![]);
    let host = host_16gb();
    let proc = FakeProc::scripted([gate_ok(NEW_MODEL, 1024, 3_000_000_000), refresh_ok(2)]);
    let http = empty_http();

    let report = run_swap(
        &deps(&ui, &host, &proc, &http),
        vault.path(),
        &SwapOptions {
            confirm: true,
            keep_previous: true,
        },
    )
    .expect("--keep-previous debe triunfar igual");

    assert_eq!(report.model.as_str(), NEW_MODEL);
    assert_old_slug_dirs_present(vault.path(), OLD_MODEL);
    assert_survivors_intact(vault.path(), OLD_MODEL, NEW_MODEL);
    let config = std::fs::read_to_string(
        vault
            .path()
            .join(".tepochcalli")
            .join("config")
            .join("tepochcalli.toml"),
    )
    .expect("config tras el swap");
    assert!(
        config.contains(NEW_MODEL),
        "la conmutación ocurre igual, got:\n{config}"
    );
    no_stray_temps(vault.path());
}

fn _db_size_probe(vault: &Path) -> PathBuf {
    vault.join(".tepochcalli").join("db").join("chunks.lance")
}

/// Live-file snapshot the mid-flight check compares against.
type LiveSnapshot = (PathBuf, Vec<u8>, Vec<u8>, Vec<u8>, Vec<u8>, Vec<u8>);

/// `CommandRunner` fake that proves the D8.4 servability invariant mid-flight:
/// every proc call (gate, refresh) runs while the live config, sidecar, index
/// and model cache are still byte-identical to the pre-swap snapshot. A swap
/// that switched config early or rebuilt the live db in place fails here.
struct CheckingProc {
    script: RefCell<VecDeque<Result<CommandOutput, WizardError>>>,
    expected: RefCell<Option<LiveSnapshot>>,
}

impl CheckingProc {
    fn scripted(script: impl IntoIterator<Item = Result<CommandOutput, WizardError>>) -> Self {
        Self {
            script: RefCell::new(script.into_iter().collect()),
            expected: RefCell::new(None),
        }
    }

    fn expect_live(
        &self,
        vault: &Path,
        config: &[u8],
        meta: &[u8],
        index: &[u8],
        model: &[u8],
        decoy: &[u8],
    ) {
        *self.expected.borrow_mut() = Some((
            vault.to_path_buf(),
            config.to_vec(),
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
        let (vault, config, meta, index, model, decoy) =
            guard.as_ref().expect("expect_live must be armed first");
        let rt = vault.join(".tepochcalli");
        assert_eq!(
            std::fs::read(rt.join("config").join("tepochcalli.toml"))
                .expect("live config readable"),
            *config,
            "la config viva no se toca durante el reemplazo"
        );
        assert_eq!(
            std::fs::read(rt.join("db").join("index-meta.json")).expect("live meta readable"),
            *meta,
            "el sidecar vivo no se toca durante el reemplazo"
        );
        assert_eq!(
            std::fs::read(rt.join("db").join("chunks.lance")).expect("live index readable"),
            *index,
            "el índice viejo sigue servable durante el reemplazo"
        );
        assert_eq!(
            std::fs::read(
                rt.join("models")
                    .join("models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2")
                    .join("snapshots")
                    .join("marker")
            )
            .expect("live model readable"),
            *model,
            "el modelo viejo no se toca durante el reemplazo"
        );
        assert_eq!(
            std::fs::read(rt.join("models").join(legacy_decoy_name(OLD_MODEL)))
                .expect("live decoy readable"),
            *decoy,
            "el decoy no se toca durante el reemplazo"
        );
        drop(guard);
        self.script
            .borrow_mut()
            .pop_front()
            .unwrap_or(Err(WizardError::Internal))
    }
}

#[test]
fn swap_live_files_untouched_while_replacement_runs() {
    let vault = installed_vault();
    let (config, meta, index, model, decoy) = snapshot(vault.path());
    let ui = TapUi::new(vec![1], vec![]);
    let host = host_16gb();
    let proc = CheckingProc::scripted([gate_ok(NEW_MODEL, 1024, 3_000_000_000), refresh_ok(2)]);
    proc.expect_live(vault.path(), &config, &meta, &index, &model, &decoy);
    let http = empty_http();

    run_swap(&deps(&ui, &host, &proc, &http), vault.path(), &confirmed())
        .expect("el swap debe triunfar con el índice viejo servable");
}

#[test]
fn swap_gc_maps_org_qualified_id_to_slug_dirs() {
    // RED: el GC viejo sanitizaba `BAAI/bge-m3` a `BAAI_bge-m3` y nunca
    // tocaba `models--BAAI--bge-m3/`; este test falla hasta el fix.
    let vault = installed_vault_with(NEW_MODEL, &[OLD_MODEL]);
    let ui = TapUi::new(vec![0], vec![]);
    let host = host_16gb();
    let proc = FakeProc::scripted([gate_ok(OLD_MODEL, 384, 1_000_000_000), refresh_ok(2)]);
    let http = empty_http();

    let report = run_swap(&deps(&ui, &host, &proc, &http), vault.path(), &confirmed())
        .expect("el swap desde un id con org debe triunfar");

    assert_eq!(report.model.as_str(), OLD_MODEL);
    assert_old_slug_dirs_gone(vault.path(), NEW_MODEL);
    assert_survivors_intact(vault.path(), NEW_MODEL, OLD_MODEL);
    no_stray_temps(vault.path());
}

#[test]
fn swap_gc_maps_st_qualified_id_to_both_slug_variants() {
    // Un id `sentence-transformers/...` comparte caché con su forma escueta:
    // el GC debe purgar ambas variantes bajo ambas raíces.
    let vault = installed_vault_with(OLD_MODEL_ST, &[NEW_MODEL]);
    let ui = TapUi::new(vec![1], vec![]);
    let host = host_16gb();
    let proc = FakeProc::scripted([gate_ok(NEW_MODEL, 1024, 3_000_000_000), refresh_ok(2)]);
    let http = empty_http();

    let report = run_swap(&deps(&ui, &host, &proc, &http), vault.path(), &confirmed())
        .expect("el swap desde un id sentence-transformers debe triunfar");

    assert_eq!(report.model.as_str(), NEW_MODEL);
    assert_old_slug_dirs_gone(vault.path(), OLD_MODEL_ST);
    // La variante escueta pertenece a la misma familia: también se purga.
    assert_old_slug_dirs_gone(vault.path(), OLD_MODEL);
    assert_survivors_intact(vault.path(), OLD_MODEL_ST, NEW_MODEL);
    no_stray_temps(vault.path());
}

/// GAP 12: `config embedder` comparte el contrato de `--vault` con el resto de
/// subcomandos — `--vault X` ≡ `--vault=X`, y un `--vault` sin valor es error
/// de uso (exit 2) sin efectos. El vault del fixture no tiene intérprete
/// ejecutable: el gate muere con `PhaseFailed` (42), lo que prueba que el
/// directorio se resolvió desde el flag (sin él sería `UserAborted`, 41).
#[test]
fn config_embedder_accepts_both_vault_forms_and_rejects_valueless_flag() {
    let state = tempfile::tempdir().expect("state home fixture");
    for form in ["--vault", "--vault="] {
        let vault = installed_vault();
        let path = vault.path().to_str().expect("utf8 tmp").to_string();
        let args: Vec<String> = if form == "--vault" {
            vec![
                "config".to_string(),
                "embedder".to_string(),
                "--non-interactive".to_string(),
                "--confirm".to_string(),
                "--vault".to_string(),
                path,
            ]
        } else {
            vec![
                "config".to_string(),
                "embedder".to_string(),
                "--non-interactive".to_string(),
                "--confirm".to_string(),
                format!("--vault={path}"),
            ]
        };
        let out = std::process::Command::new(env!("CARGO_BIN_EXE_tepochcalli"))
            .args(&args)
            .env("XDG_STATE_HOME", state.path())
            .env("LOCALAPPDATA", state.path())
            .stdin(std::process::Stdio::null())
            .output()
            .expect("spawn binary");
        let stderr = String::from_utf8_lossy(&out.stderr);
        assert_eq!(out.status.code(), Some(42), "args {args:?}:\n{stderr}");
        assert!(
            stderr.contains("config embedder failed"),
            "el swap debe haber corrido con el vault del flag, args {args:?}:\n{stderr}"
        );
        assert!(
            !stderr.contains("vault selection failed"),
            "el flag no debe ignorarse, args {args:?}:\n{stderr}"
        );
    }

    // `--vault` sin valor: error de uso explicado, cero efectos.
    let vault = installed_vault();
    let before = snapshot(vault.path());
    let out = std::process::Command::new(env!("CARGO_BIN_EXE_tepochcalli"))
        .args([
            "config",
            "embedder",
            "--non-interactive",
            "--confirm",
            "--vault",
        ])
        .env("XDG_STATE_HOME", state.path())
        .env("LOCALAPPDATA", state.path())
        .stdin(std::process::Stdio::null())
        .output()
        .expect("spawn binary");
    assert_eq!(
        out.status.code(),
        Some(2),
        "un --vault sin valor es error de uso:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(
        stderr.contains("--vault") && stderr.contains("needs a value"),
        "explica el flag sin valor, got:\n{stderr}"
    );
    assert!(
        out.stdout.is_empty(),
        "un error de uso no imprime nada en stdout"
    );
    assert_byte_identical(vault.path(), &before);
    no_stray_temps(vault.path());
}

/// Una invocación hija registrada: argv + env (copias propias).
#[derive(Debug, Clone)]
struct Call {
    args: Vec<String>,
    env: Vec<(String, String)>,
}

/// `CommandRunner` fake que REGISTRA cada llamada antes de repertir el guion:
/// única forma de afirmar «no se lanzó el gate» / «HF_TOKEN llegó solo al
/// env de un hijo» (FakeProc de `common` no guarda argv/env).
struct RecordingProc {
    script: RefCell<VecDeque<Result<CommandOutput, WizardError>>>,
    calls: RefCell<Vec<Call>>,
}

impl RecordingProc {
    fn scripted(script: impl IntoIterator<Item = Result<CommandOutput, WizardError>>) -> Self {
        Self {
            script: RefCell::new(script.into_iter().collect()),
            calls: RefCell::new(Vec::new()),
        }
    }

    fn calls(&self) -> Vec<Call> {
        self.calls.borrow().clone()
    }

    fn argv(&self) -> Vec<Vec<String>> {
        self.calls().into_iter().map(|call| call.args).collect()
    }

    /// ¿Corrió el gate test-embed (`embed-check --model`)?
    fn gated(&self) -> bool {
        self.calls()
            .iter()
            .any(|call| call.args.iter().any(|arg| arg == "embed-check"))
    }

    /// ¿Corrió el re-index (`refresh`)?
    fn refreshed(&self) -> bool {
        self.calls()
            .iter()
            .any(|call| call.args.iter().any(|arg| arg == "refresh"))
    }
}

impl CommandRunner for RecordingProc {
    fn run(
        &self,
        _program: &str,
        args: &[&str],
        _cwd: &Path,
        env: &[(&str, &str)],
    ) -> Result<CommandOutput, WizardError> {
        self.calls.borrow_mut().push(Call {
            args: args.iter().map(|arg| (*arg).to_string()).collect(),
            env: env
                .iter()
                .map(|(key, value)| ((*key).to_string(), (*value).to_string()))
                .collect(),
        });
        self.script
            .borrow_mut()
            .pop_front()
            .unwrap_or(Err(WizardError::Internal))
    }
}

/// HF API base del pre-chequeo D8.1 (contrato de `pending_free_id`).
const HF_API: &str = "https://huggingface.co/api/models/";

/// `FakeHttp` sirviendo exactamente la metadata de ese id.
fn http_serving(id: &str, body: &str) -> FakeHttp {
    FakeHttp::new(HashMap::from([(
        format!("{HF_API}{id}"),
        body.as_bytes().to_vec(),
    )]))
}

const EXTERNAL_MODEL: &str = "openai/text-embedding-3-small";
/// Clave señuelo: si aparece fuera de la config gitignored, el test lo delata.
const FAKE_KEY: &str = "sk-LEAK-TEST-0123456789abcdef";

/// GAP 2: el camino de API externa (índice 3) nunca se ejercitaba. La clave
/// viaja empaquetada como `model\0api_key` y solo `picked_config_body` la
/// separa; aquí se prueba que (a) cae exactamente una vez en la config, (b)
/// no sale por ningún panel, (c) no hay descarga/gate de dims y (d) el
/// sidecar conserva la forma documentada con `dims: null`.
#[test]
fn external_api_swap_writes_key_once_and_never_in_panel() {
    let vault = installed_vault();
    let rt = vault.path().join(".tepochcalli");
    let ui = TapUi::new(
        vec![3],
        vec![EXTERNAL_MODEL.to_string(), FAKE_KEY.to_string()],
    );
    let host = host_16gb();
    let proc = RecordingProc::scripted([refresh_ok(2)]);
    let http = empty_http();

    let report = run_swap(&deps(&ui, &host, &proc, &http), vault.path(), &confirmed())
        .expect("el swap a API externa debe triunfar sin descarga local");

    // (a) config: provider litellm, modelo y clave exactamente una vez.
    let config = std::fs::read_to_string(rt.join("config").join("tepochcalli.toml"))
        .expect("config tras el swap");
    assert!(
        config.contains("provider = \"litellm\""),
        "provider externo, got:\n{config}"
    );
    assert_eq!(
        config.matches(EXTERNAL_MODEL).count(),
        1,
        "el modelo aparece exactamente una vez, got:\n{config}"
    );
    assert_eq!(
        config.matches(FAKE_KEY).count(),
        1,
        "la clave aparece exactamente una vez, got:\n{config}"
    );
    assert_eq!(report.model, EXTERNAL_MODEL, "el reporte no lleva la clave");
    assert_eq!(report.dims, None, "el externo no tiene dims medidas");
    assert_eq!(report.health, RagHealth::Ok);

    // (b) la clave nunca sale por la UI (títulos, cuerpos ni prompts).
    let visible = format!("{}\n{}", ui.titles().join("\n"), ui.bodies().join("\n"));
    assert!(
        !visible.contains(FAKE_KEY),
        "la clave nunca puede aparecer en un panel (títulos/cuerpos/prompts)"
    );

    // (c) sin gate de dims: el externo no descarga; el re-index sí corre y
    // su hijo no recibe la clave (ni por env ni por argv).
    assert!(
        !proc.gated(),
        "el camino externo no corre el gate test-embed/dims, argv: {:?}",
        proc.argv()
    );
    assert!(
        proc.refreshed(),
        "el re-index corre para el externo, argv: {:?}",
        proc.argv()
    );
    for call in proc.calls() {
        assert!(
            call.env.iter().all(|(key, value)| key != "HF_TOKEN"
                && key != "TEPOCHCALLI_EMBED_API_KEY"
                && value != FAKE_KEY),
            "la clave no viaja en el env del hijo, got: {:?}",
            call.env
        );
    }
    assert!(
        !format!("{:?}", proc.argv()).contains(FAKE_KEY),
        "la clave no viaja en argv"
    );

    // (d) forma documentada del sidecar para proveedor externo:
    // `{"model":<id>,"dims":null}` (misma que escribe F7/reindex, sin dims).
    let meta = std::fs::read_to_string(rt.join("db").join("index-meta.json"))
        .expect("sidecar tras el swap");
    assert_eq!(
        meta,
        format!("{{\"model\":\"{EXTERNAL_MODEL}\",\"dims\":null}}\n"),
        "forma del sidecar para provider externo"
    );
    no_stray_temps(vault.path());
}

/// GAP 2 (seguridad): una clave vacía no se escribe nunca. `ask_non_empty`
/// re-pregunta; con el guion agotado el swap aborta tipado antes de tocar
/// config, sidecar o lanzar gate/refresh.
#[test]
fn external_api_swap_with_empty_key_is_refused_before_writing() {
    let vault = installed_vault();
    let before = snapshot(vault.path());
    let ui = TapUi::new(vec![3], vec![EXTERNAL_MODEL.to_string(), "   ".to_string()]);
    let host = host_16gb();
    // Guion de procesos vacío: cualquier spawn devolvería Internal y delataría
    // que el swap siguió adelante sin clave.
    let proc = RecordingProc::scripted([]);
    let http = empty_http();

    let err = run_swap(&deps(&ui, &host, &proc, &http), vault.path(), &confirmed())
        .expect_err("sin clave el swap no puede escribir config");

    assert_eq!(
        err,
        WizardError::UserAborted,
        "el rechazo es tipado (re-pregunta agotada), nunca un half-swap"
    );
    assert!(
        ui.titles()
            .iter()
            .any(|title| title.contains("Falta un dato")),
        "explica que el valor no puede ir vacío, títulos: {:?}",
        ui.titles()
    );
    assert_byte_identical(vault.path(), &before);
    assert!(
        proc.calls().is_empty(),
        "sin clave válida no se lanza gate ni refresh, argv: {:?}",
        proc.argv()
    );
    no_stray_temps(vault.path());
}

/// GAP 3: «Configurar después» (índice 4) nunca se ejercitaba en el swap.
///
/// Estado que deja, pineado explícitamente: **no** hay gate ni refresh (el
/// índice vivo queda byte-idéntico, servible), la config pasa a
/// `provider = "none"` y el sidecar `index-meta.json` SIGUE describiendo el
/// índice viejo (modelo y dims). Eso es deliberado y correcto: el sidecar
/// describe las filas que hay en disco, que nadie reconstruyó; quien decide
/// el estado RAG es la config (`none` ⇒ `rag_status` degraded / E_NO_EMBEDDER),
/// así que un lector no lee el sidecar como si hubiera un embedder activo.
#[test]
fn swap_to_configure_later_keeps_meta_describing_the_old_index_and_never_refreshes() {
    let vault = installed_vault();
    let rt = vault.path().join(".tepochcalli");
    let before = snapshot(vault.path());
    let ui = TapUi::new(vec![4], vec![]);
    let host = host_16gb();
    let proc = RecordingProc::scripted([]);
    let http = empty_http();

    let report = run_swap(&deps(&ui, &host, &proc, &http), vault.path(), &confirmed())
        .expect("«Configurar después» debe completarse sin índice");

    // (a) nada se descarga ni se reindexa: el índice vivo queda intacto.
    assert!(
        proc.calls().is_empty(),
        "la salida 5 no lanza gate ni refresh, argv: {:?}",
        proc.argv()
    );
    assert!(!proc.gated() && !proc.refreshed());
    assert_eq!(
        std::fs::read(rt.join("db").join("chunks.lance")).expect("índice vivo"),
        before.2,
        "el índice vivo no se toca"
    );

    // (b) la config refleja la salida 5: sin provider local y sin modelo.
    let config = std::fs::read_to_string(rt.join("config").join("tepochcalli.toml"))
        .expect("config tras el swap");
    assert!(
        config.contains("provider = \"none\""),
        "config en modo none, got:\n{config}"
    );
    assert!(
        !config.contains("model ="),
        "ningún modelo a medias en la config, got:\n{config}"
    );
    assert_eq!(report.health, RagHealth::Degraded);
    assert_eq!(report.dims, None);
    assert_eq!(report.model, "", "la salida 5 no nombra modelo");
    assert_eq!(
        report.rows, 2,
        "sin re-index el conteo sigue siendo el del db previo (2 ficheros)"
    );

    // (c) el sidecar sigue describiendo el índice viejo (pin del estado real).
    let meta = std::fs::read_to_string(rt.join("db").join("index-meta.json"))
        .expect("sidecar tras el swap");
    assert_eq!(
        meta,
        String::from_utf8(before.1).expect("meta utf8"),
        "sin re-index el sidecar sigue describiendo el índice viejo (modelo y dims): \
         la config `none` es la que manda para rag_status"
    );
    assert!(
        meta.contains(OLD_MODEL) && meta.contains("384"),
        "pin explícito del estado que un lector de rag_status encontraría, got:\n{meta}"
    );
    no_stray_temps(vault.path());
}

const GATED_ID: &str = "org/gated-embed-model";
/// Token señuelo: solo puede aparecer en el env del hijo del gate.
const GATED_TOKEN: &str = "hf_LEAK-TEST-gated-token-0987";

/// GAP 5a: un repo de HF que no es de embeddings se rechaza ANTES de tocar
/// disco (pre-filtro D8.1 por `pipeline_tag`/tags ⇒ `E_MODEL_INVALID`).
#[test]
fn free_id_non_embedding_repo_aborts_with_model_invalid() {
    let vault = installed_vault();
    let before = snapshot(vault.path());
    let id = "microsoft/phi-3-mini-4k-instruct";
    let ui = TapUi::new(vec![2], vec![id.to_string()]);
    let host = host_16gb();
    let proc = RecordingProc::scripted([]);
    let http = http_serving(
        id,
        "{\"tags\":[\"text-generation\"],\"pipeline_tag\":\"text-generation\"}",
    );

    let err = run_swap(&deps(&ui, &host, &proc, &http), vault.path(), &confirmed())
        .expect_err("un repo no-embeddings debe abortar el swap");

    assert_eq!(err, WizardError::ModelInvalid);
    assert!(
        ui.titles()
            .iter()
            .any(|title| title.contains("E_MODEL_INVALID")),
        "el código público se muestra al usuario, títulos: {:?}",
        ui.titles()
    );
    assert!(
        proc.calls().is_empty(),
        "ni descarga ni gate: el rechazo ocurre antes, argv: {:?}",
        proc.argv()
    );
    assert_byte_identical(vault.path(), &before);
    no_stray_temps(vault.path());
}

/// GAP 5b: repo `gated` ⇒ se pide HF_TOKEN y viaja SOLO en el env del hijo
/// del gate (spec-embeddings §HF_TOKEN: nunca se loggea ni se persiste).
#[test]
fn free_id_gated_repo_passes_hf_token_only_to_child_env() {
    let vault = installed_vault();
    let rt = vault.path().join(".tepochcalli");
    let ui = TapUi::new(vec![2], vec![GATED_ID.to_string(), GATED_TOKEN.to_string()]);
    let host = host_16gb();
    let proc = RecordingProc::scripted([gate_ok(GATED_ID, 768, 1_500_000_000), refresh_ok(2)]);
    let http = http_serving(
        GATED_ID,
        "{\"tags\":[\"sentence-similarity\"],\"gated\":true}",
    );

    let report = run_swap(&deps(&ui, &host, &proc, &http), vault.path(), &confirmed())
        .expect("un id gated con token debe completar el swap");

    assert_eq!(report.model, GATED_ID);
    assert_eq!(report.dims, Some(768));

    // El token llega al env del gate y a ningún otro hijo.
    let calls = proc.calls();
    assert_eq!(calls.len(), 2, "gate + refresh, argv: {:?}", proc.argv());
    let gate = &calls[0];
    assert!(
        gate.args.iter().any(|arg| arg == "embed-check"),
        "la primera llamada es el gate, got: {:?}",
        gate.args
    );
    assert!(
        gate.env
            .contains(&("HF_TOKEN".to_string(), GATED_TOKEN.to_string())),
        "el gate recibe HF_TOKEN en su env, got: {:?}",
        gate.env
    );
    let refresh = &calls[1];
    assert!(
        refresh.env.iter().all(|(key, _)| key != "HF_TOKEN"),
        "el refresh no necesita el token, got: {:?}",
        refresh.env
    );

    // Ni panel, ni argv, ni config/sidecar: la única salida es el env del hijo.
    let visible = format!("{}\n{}", ui.titles().join("\n"), ui.bodies().join("\n"));
    assert!(
        !visible.contains(GATED_TOKEN),
        "el token no aparece en ningún panel"
    );
    assert!(
        !format!("{:?}", proc.argv()).contains(GATED_TOKEN),
        "el token nunca viaja en argv"
    );
    for file in ["config/tepochcalli.toml", "db/index-meta.json"] {
        let body = std::fs::read_to_string(rt.join(file)).expect("fichero escrito por el swap");
        assert!(
            !body.contains(GATED_TOKEN),
            "{file} no puede persistir el HF_TOKEN (solo la API key de la salida 4 se persiste)"
        );
    }
    assert!(
        std::fs::read_to_string(rt.join("config").join("tepochcalli.toml"))
            .expect("config")
            .contains(GATED_ID),
        "la config sí nombra el modelo elegido"
    );
    no_stray_temps(vault.path());
}

/// GAP 4: la ventana entre los dos renames del `commit`. La config ya
/// conmutada no puede sobrevivir a un fallo del segundo rename: `run_swap`
/// hace rollback y la config vuelve byte-idéntica (el índice y los modelos ni
/// se tocaron, así que siguen intactos por construcción).
///
/// Fallo forzado elegido: el destino del sidecar es un **directorio no vacío**
/// ⇒ `rename(2)` devuelve `EISDIR` y la operación falla igual como uid 1000 y
/// como root (un `chmod 0555` no vale: root lo atraviesa; y montar un FS de
/// solo lectura no es portable en CI).
#[test]
fn swap_meta_rename_failure_restores_config_byte_identical() {
    let vault = installed_vault();
    let rt = vault.path().join(".tepochcalli");
    let config_before = std::fs::read(rt.join("config").join("tepochcalli.toml")).expect("config");
    let index_before = std::fs::read(rt.join("db").join("chunks.lance")).expect("índice vivo");
    // El sidecar pasa a ser un directorio con contenido: el rename final muere.
    let meta_path = rt.join("db").join("index-meta.json");
    std::fs::remove_file(&meta_path).expect("sidecar fixture removible");
    std::fs::create_dir_all(&meta_path).expect("sidecar como directorio");
    std::fs::write(meta_path.join("marker"), b"unreadable-sidecar").expect("marker del sidecar");

    let ui = TapUi::new(vec![1], vec![]);
    let host = host_16gb();
    let proc = FakeProc::scripted([gate_ok(NEW_MODEL, 1024, 3_000_000_000), refresh_ok(2)]);
    let http = empty_http();

    let err = run_swap(&deps(&ui, &host, &proc, &http), vault.path(), &confirmed())
        .expect_err("un fallo en el segundo rename debe fallar el swap");
    assert_eq!(
        err,
        WizardError::PermissionDenied,
        "error tipado, no un Ok a medias"
    );
    assert!(
        (30..=39).contains(&err.exit_code()),
        "un fallo de FS cae en el rango 30-39, got {}",
        err.exit_code()
    );

    // Cero cambio de estado en lo vivo: config byte-idéntica, índice servable.
    assert_eq!(
        std::fs::read(rt.join("config").join("tepochcalli.toml")).unwrap_or_default(),
        config_before,
        "la config debe volver byte-idéntica al snapshot pre-swap (ausente ⇒ difiere)"
    );
    assert_eq!(
        std::fs::read(rt.join("db").join("chunks.lance")).expect("índice tras el fallo"),
        index_before,
        "el índice viejo sigue servable"
    );
    assert_eq!(
        std::fs::read(meta_path.join("marker")).expect("sidecar tras el fallo"),
        b"unreadable-sidecar",
        "el rollback no destruye lo que no pudo fotografiar"
    );
    assert_old_slug_dirs_present(vault.path(), OLD_MODEL);
    no_stray_temps(vault.path());
}

/// Mismo fallo del segundo rename, pero con la config **ausente** de partida
/// (vault degradado al que se le añade por primera vez un embedder): el rollback
/// no puede inventarse un fichero. Estado final: sin config, sidecar intacto y
/// cero `.swap` en el vault.
#[test]
fn swap_meta_rename_failure_keeps_an_absent_config_absent() {
    let vault = installed_vault();
    let rt = vault.path().join(".tepochcalli");
    std::fs::remove_file(rt.join("config").join("tepochcalli.toml")).expect("config fuera");
    let meta_path = rt.join("db").join("index-meta.json");
    std::fs::remove_file(&meta_path).expect("sidecar fixture removible");
    std::fs::create_dir_all(&meta_path).expect("sidecar como directorio");
    std::fs::write(meta_path.join("marker"), b"unreadable-sidecar").expect("marker del sidecar");

    let ui = TapUi::new(vec![1], vec![]);
    let host = host_16gb();
    let proc = FakeProc::scripted([gate_ok(NEW_MODEL, 1024, 3_000_000_000), refresh_ok(2)]);
    let http = empty_http();

    let err = run_swap(&deps(&ui, &host, &proc, &http), vault.path(), &confirmed())
        .expect_err("un fallo en el segundo rename debe fallar el swap");
    assert_eq!(err, WizardError::PermissionDenied);
    assert!(
        !rt.join("config").join("tepochcalli.toml").exists(),
        "config ausente antes del swap debe seguir ausente"
    );
    assert_eq!(
        std::fs::read(meta_path.join("marker")).expect("sidecar tras el fallo"),
        b"unreadable-sidecar",
        "el rollback no destruye lo que no pudo fotografiar"
    );
    no_stray_temps(vault.path());
}

/// Model id hostil pero plausible: comilla doble y barra invertida dentro del
/// valor. Ambos escritores tienen que escaparlos o el fichero queda corrupto.
const HOSTILE_MODEL: &str = "org/weird\"name\\v2";
/// El mismo id escapado para JSON (forma en que el gate lo devuelve).
const HOSTILE_MODEL_JSON: &str = r#"org/weird\"name\\v2"#;

/// Des-escapado mínimo (`\x` ⇒ `x`) para leer de vuelta ambos formatos.
fn unescape(raw: &str) -> String {
    let mut out = String::with_capacity(raw.len());
    let mut chars = raw.chars();
    while let Some(current) = chars.next() {
        if current == '\\' {
            if let Some(escaped) = chars.next() {
                out.push(escaped);
            }
        } else {
            out.push(current);
        }
    }
    out
}

/// Lector mínimo `key = "valor"` (des-escapa TOML básico).
fn toml_string(body: &str, key: &str) -> Option<String> {
    body.lines().find_map(|line| {
        let rest = line
            .trim()
            .strip_prefix(key)?
            .trim_start()
            .strip_prefix('=')?;
        let value = rest.trim().strip_prefix('"')?;
        let end = value.rfind('"')?;
        Some(unescape(&value[..end]))
    })
}

/// Lector mínimo `"key":"valor"` (des-escapa JSON básico).
fn json_string(body: &str, key: &str) -> Option<String> {
    let needle = format!("\"{key}\":");
    let after = &body[body.find(&needle)? + needle.len()..];
    let value = after.trim_start().strip_prefix('"')?;
    let mut escaped = false;
    for (index, character) in value.char_indices() {
        if escaped {
            escaped = false;
        } else if character == '\\' {
            escaped = true;
        } else if character == '"' {
            return Some(unescape(&value[..index]));
        }
    }
    None
}

/// GAP 10: un id con `"` o `\` tiene que sobrevivir `toml_escape` y
/// `json_escape` y leerse de vuelta idéntico en config y sidecar. Sin el
/// escapado, la config queda con una cadena TOML truncada y el sidecar con
/// JSON inválido.
#[test]
fn model_id_with_quotes_and_backslashes_round_trips() {
    let vault = installed_vault();
    let rt = vault.path().join(".tepochcalli");
    let ui = TapUi::new(vec![2], vec![HOSTILE_MODEL.to_string()]);
    let host = host_16gb();
    let proc = FakeProc::scripted([gate_ok(HOSTILE_MODEL_JSON, 768, 900_000_000), refresh_ok(2)]);
    // Sin metadatos del id: la API falla y el gate queda como fuente de verdad.
    let http = empty_http();

    let report = run_swap(&deps(&ui, &host, &proc, &http), vault.path(), &confirmed())
        .expect("un id con comillas y barras debe completar el swap");
    assert_eq!(
        report.model, HOSTILE_MODEL,
        "el reporte conserva el id crudo"
    );

    // (a) config: forma escapada exacta + round-trip al id original.
    let config = std::fs::read_to_string(rt.join("config").join("tepochcalli.toml"))
        .expect("config tras el swap");
    assert!(
        config.contains(r#"model = "org/weird\"name\\v2""#),
        "TOML escapado (\\\" y \\\\), got:\n{config}"
    );
    assert_eq!(
        toml_string(&config, "model").as_deref(),
        Some(HOSTILE_MODEL),
        "leer la config devuelve el id original, got:\n{config}"
    );

    // (b) sidecar: forma escapada exacta + round-trip al id original.
    let meta = std::fs::read_to_string(rt.join("db").join("index-meta.json"))
        .expect("sidecar tras el swap");
    assert_eq!(
        meta, "{\"model\":\"org/weird\\\"name\\\\v2\",\"dims\":768}\n",
        "JSON escapado y válido"
    );
    assert_eq!(
        json_string(&meta, "model").as_deref(),
        Some(HOSTILE_MODEL),
        "leer el sidecar devuelve el id original, got:\n{meta}"
    );
    no_stray_temps(vault.path());
}

/// GAP 11a: swap al MISMO modelo (el preset default ya vigente y cacheado).
/// Intencionado: `docs/APPFLOW.md` journey (f) paso 5 y
/// `specs/spec-embeddings.md` §Procedimiento de swap purgan el modelo
/// **anterior** tras un re-index exitoso; si el "anterior" es el vigente,
/// borrarlo dejaría el índice vivo sin embedder de consulta (otra descarga de
/// 470MB, o `E_OFFLINE_NO_CACHE` sin red).
#[test]
fn swap_to_the_same_model_does_not_purge_models() {
    let vault = installed_vault();
    let rt = vault.path().join(".tepochcalli");
    let ui = TapUi::new(vec![0], vec![]);
    let host = host_16gb();
    let proc = FakeProc::scripted([gate_ok(OLD_MODEL, 384, 1_000_000_000), refresh_ok(2)]);
    let http = empty_http();

    let report = run_swap(&deps(&ui, &host, &proc, &http), vault.path(), &confirmed())
        .expect("re-elegir el mismo modelo debe completar el swap");

    assert_eq!(report.model, OLD_MODEL);
    // El swap se completa igual (conmutación), solo se salta la purga.
    assert_old_slug_dirs_present(vault.path(), OLD_MODEL);
    assert_survivors_intact(vault.path(), OLD_MODEL, OLD_MODEL);
    assert!(
        std::fs::read_to_string(rt.join("config").join("tepochcalli.toml"))
            .expect("config tras el swap")
            .contains(OLD_MODEL),
        "el swap se completa igual (conmutación, no purga)"
    );
    no_stray_temps(vault.path());
}

/// GAP 11b: swap a `none` («Configurar después»). Intencionado que la caché
/// del modelo viejo sobreviva: el journey (f) de `docs/APPFLOW.md` y
/// `specs/spec-embeddings.md` §Procedimiento de swap solo purgan tras un
/// re-index exitoso con el modelo nuevo, y aquí no hubo re-index
/// (`swap_to_configure_later_...` pinea que el sidecar sigue describiendo el
/// índice viejo). `models/` sigue siendo el embedder que `search` necesita
/// para embeber consultas: purgarlo rompería las lecturas del índice vivo.
#[test]
fn swap_to_none_keeps_the_previous_model_cache() {
    let vault = installed_vault();
    let ui = TapUi::new(vec![4], vec![]);
    let host = host_16gb();
    let proc = RecordingProc::scripted([]);
    let http = empty_http();

    let report = run_swap(&deps(&ui, &host, &proc, &http), vault.path(), &confirmed())
        .expect("«Configurar después» debe completarse sin índice");
    assert_eq!(report.health, RagHealth::Degraded);
    assert_old_slug_dirs_present(vault.path(), OLD_MODEL);
    assert_survivors_intact(vault.path(), OLD_MODEL, OLD_MODEL);
    no_stray_temps(vault.path());
}

/// GAP 5c: metadata inalcanzable (404) degrada la estimación a «sin dato» —
/// nunca bloquea. Comportamiento intencionado (D8.1): la instalación no falla
/// por falta de red y el gate test-embed queda como única fuente de verdad.
#[test]
fn free_id_missing_metadata_proceeds_to_download() {
    let vault = installed_vault();
    let id = "acme/unlisted-embed";
    let ui = TapUi::new(vec![2], vec![id.to_string()]);
    let host = host_16gb();
    let proc = RecordingProc::scripted([gate_ok(id, 512, 900_000_000), refresh_ok(2)]);
    // Sin entradas: cualquier GET devuelve NetDownload (404/API caída).
    let http = empty_http();

    let report = run_swap(&deps(&ui, &host, &proc, &http), vault.path(), &confirmed())
        .expect("sin metadatos de la API el swap sigue por el gate");

    assert_eq!(report.model, id);
    assert_eq!(report.dims, Some(512), "las dims las mide el gate");
    assert!(
        ui.titles()
            .iter()
            .any(|title| title.contains("Sin estimación")),
        "explica que la estimación no llegó, títulos: {:?}",
        ui.titles()
    );
    let calls = proc.calls();
    assert!(
        calls[0].args.iter().any(|arg| arg == "embed-check"),
        "la descarga se intenta igual, argv: {:?}",
        proc.argv()
    );
    assert!(
        calls
            .iter()
            .flat_map(|call| call.env.iter())
            .all(|(key, _)| key != "HF_TOKEN"),
        "sin dato `gated` no se pide token, envs: {:?}",
        calls.iter().map(|call| &call.env).collect::<Vec<_>>()
    );
    no_stray_temps(vault.path());
}
