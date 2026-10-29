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
