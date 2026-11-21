//! Hueco #12 (heredado del swap) — la URL exacta del preflight de H9 y los
//! caminos que NO sondean (R-offline-4: sin red no se sondea).
//!
//! `swap.rs` solo llama a `HttpClient::probe` con `provider == "local"` y
//! DESPUÉS de `--confirm`; aquí esas llamadas se GRABAN con un double que
//! registra las URLs (hoy `FakeHttp::probe` solo devuelve `Ok` y no deja
//! rastro). Sin red real: fakes y fixtures de `swap_support`.

// Shared fakes: this target reuses the swap fixtures and four of them.
#[allow(dead_code)]
mod common;

use std::cell::RefCell;
use std::collections::HashMap;
use std::path::Path;

use common::swap_support::{
    assert_no_spawns, confirmed, deps, installed_vault, refresh_ok, EXTERNAL_MODEL, FAKE_KEY,
    GATED_ID, GATED_TOKEN, HF_API,
};
use common::{host_16gb, FakeHttp, RecordingProc, TapUi};
use tepochcalli::ports::HttpClient;
use tepochcalli::WizardError;

/// `HttpClient` fake que GRABA las URLs de `probe` (R-offline-1: qué se
/// sondea y con qué URL exacta) y delega el veredicto en `FakeHttp`, que
/// sigue mandando si la sonda pasa o falla. Un double local en vez de
/// tocar `FakeHttp`: sus 20+ constructores existentes no cambian.
struct RecordingHttp {
    inner: FakeHttp,
    probes: RefCell<Vec<String>>,
}

impl RecordingHttp {
    fn new(inner: FakeHttp) -> Self {
        Self {
            inner,
            probes: RefCell::new(Vec::new()),
        }
    }

    /// URLs de `probe`, en orden de llamada.
    fn probes(&self) -> Vec<String> {
        self.probes.borrow().clone()
    }
}

impl HttpClient for RecordingHttp {
    fn get(&self, url: &str) -> Result<Vec<u8>, WizardError> {
        self.inner.get(url)
    }

    fn download(&self, url: &str, dest: &Path, expected_sha256: &str) -> Result<(), WizardError> {
        self.inner.download(url, dest, expected_sha256)
    }

    fn probe(&self, url: &str) -> Result<(), WizardError> {
        self.probes.borrow_mut().push(url.to_string());
        self.inner.probe(url)
    }
}

/// Metadata HF mínima de un id GATED de embeddings (D8.1): `gated:true`
/// hace que el swap pida `HF_TOKEN`, y el tag la clasifica como embedder.
fn gated_meta(sha: &str) -> Vec<u8> {
    format!(
        "{{\"gated\":true,\"sha\":\"{sha}\",\"pipeline_tag\":\"sentence-similarity\",\
         \"tags\":[\"sentence-transformers\"],\
         \"safetensors\":{{\"parameters\":{{\"total\":117600000}}}},\
         \"siblings\":[{{\"rfilename\":\"model.safetensors\",\"size\":470000000}}]}}"
    )
    .into_bytes()
}

/// Hueco #12(a) — provider `local` (id libre gated): la sonda del preflight
/// es EXACTAMENTE `https://huggingface.co/api/models/<id>` — sin clave,
/// sin `\0`, sin query, y una sola.
///
/// Regresión que detecta: si la URL se construyera con el `model` crudo (o
/// con cualquier sufijo), el `assert_eq!` contra la lista COMPLETA sale en
/// rojo. El `HF_TOKEN` del id gated viaja por su canal (env del hijo del
/// gate, nunca la URL) y el aserto de no-fuga lo fija.
///
/// Límite declarado (auditoría): el `split_once('\u{0}')` de `swap.rs:172`
/// es DEFENSIVO para `provider == "local"` — ningún pick local empaqueta
/// una clave en `model` (el id libre pasa por `is_plausible_hf_id`, que
/// rechaza caracteres de control, y el token viaja aparte), así que el caso
/// «local + model con `\0`» NO es alcanzable por la API pública y no se
/// inventa un test que lo simule. Aquí se fija la URL que sí se emite.
#[test]
fn preflight_local_sondea_exactamente_la_url_del_id() {
    let vault = installed_vault();
    let mut files = HashMap::new();
    files.insert(format!("{HF_API}{GATED_ID}"), gated_meta("0000sha-gated"));
    let http = RecordingHttp::new(FakeHttp::new(files));
    let ui = TapUi::new(
        vec![2, 0],
        vec![GATED_ID.to_string(), GATED_TOKEN.to_string()],
    );
    let host = host_16gb();
    // El gate falla DESPUÉS del preflight: el swap aborta y solo importa
    // qué se sondeó (y en qué orden).
    let proc = RecordingProc::scripted([Err(WizardError::PhaseFailed)]);

    let got = tepochcalli::run_swap(&deps(&ui, &host, &proc, &http), vault.path(), &confirmed());

    assert_eq!(
        got,
        Err(WizardError::PhaseFailed),
        "el gate aborta después de sondear: el preflight corre primero"
    );
    let probes = http.probes();
    assert_eq!(
        probes,
        vec![format!("{HF_API}{GATED_ID}")],
        "una única sonda, con la URL EXACTA del id"
    );
    assert!(
        !probes[0].contains('\u{0}'),
        "el separador empaquetado jamás llega a la URL: {}",
        probes[0]
    );
    assert!(
        !probes[0].contains(GATED_TOKEN),
        "la clave jamás entra en la URL: {}",
        probes[0]
    );
}

/// Hueco #12(b) — path 5 (`provider = "none"`, fila «configurar más
/// tarde»): CERO URLs sondeadas. La ruta 5 no descarga nada, así que no
/// hay red que comprobar (R-offline-4).
///
/// Regresión que detecta: si el guard `provider == "local"` del preflight
/// desapareciera (o la ruta 5 llegara a pedir red), aparecería una URL
/// grabada y el `is_empty()` sale en rojo. `assert_no_spawns` refuerza que
/// tampoco hay gate ni refresh.
#[test]
fn path5_no_sondea_ninguna_url() {
    let vault = installed_vault();
    let http = RecordingHttp::new(FakeHttp::new(HashMap::new()));
    let ui = TapUi::new(vec![4], vec![]);
    let host = host_16gb();
    let proc = RecordingProc::scripted([]);

    let got = tepochcalli::run_swap(&deps(&ui, &host, &proc, &http), vault.path(), &confirmed());

    assert!(got.is_ok(), "la ruta 5 cierra el swap degradado: {got:?}");
    assert!(
        http.probes().is_empty(),
        "R-offline-4: la ruta 5 no sondea nada, got: {:?}",
        http.probes()
    );
    assert_no_spawns(&proc, "la ruta 5 no descarga ni re-indexa");
}

/// Hueco #12(c) — provider `litellm` (externo): CERO URLs sondeadas. El
/// TOML no declara endpoint (LiteLLM deriva el proveedor del prefijo de
/// `model`), así que el preflight —que solo corre para `local`— no aplica.
///
/// Regresión que detecta: si el guard `provider == "local"` desapareciera,
/// el preflight sondearía con el `model` empaquetado (`model\0api_key`) y
/// el `is_empty()` sale en rojo.
#[test]
fn provider_externo_no_sondea_ninguna_url() {
    let vault = installed_vault();
    let http = RecordingHttp::new(FakeHttp::new(HashMap::new()));
    let ui = TapUi::new(
        vec![3],
        vec![EXTERNAL_MODEL.to_string(), FAKE_KEY.to_string()],
    );
    let host = host_16gb();
    let proc = RecordingProc::scripted([refresh_ok(1)]);

    let got = tepochcalli::run_swap(&deps(&ui, &host, &proc, &http), vault.path(), &confirmed());

    assert!(got.is_ok(), "el swap externo cierra con refresh: {got:?}");
    assert!(
        http.probes().is_empty(),
        "el provider externo no sondea: el TOML no declara endpoint, got: {:?}",
        http.probes()
    );
}
