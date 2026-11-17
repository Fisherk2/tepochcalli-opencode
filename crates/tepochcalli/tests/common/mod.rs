//! Test fakes for the 5 ports (T4): scripted, in-memory, std-only
//! (plus `sha2`/`tempfile`, already crate deps — no new dependencies).

use std::cell::RefCell;
use std::collections::{HashMap, VecDeque};
use std::path::{Path, PathBuf};

use sha2::{Digest, Sha256};
use tepochcalli::ports::{
    CommandOutput, CommandRunner, GpuInfo, HostProbe, HttpClient, MergeReport, PayloadSource, Ui,
};
use tepochcalli::WizardError;

/// `CommandRunner` fake: replays a script of outputs/errors in order.
/// Exhausted script (or unexpected call count) is `Internal` — a test bug.
pub struct FakeProc {
    script: RefCell<VecDeque<Result<CommandOutput, WizardError>>>,
}

impl FakeProc {
    /// Build from any ordered script of results.
    pub fn scripted(script: impl IntoIterator<Item = Result<CommandOutput, WizardError>>) -> Self {
        Self {
            script: RefCell::new(script.into_iter().collect()),
        }
    }
}

impl CommandRunner for FakeProc {
    fn run(
        &self,
        _program: &str,
        _args: &[&str],
        _cwd: &Path,
        _env: &[(&str, &str)],
    ) -> Result<CommandOutput, WizardError> {
        self.script
            .borrow_mut()
            .pop_front()
            .unwrap_or(Err(WizardError::Internal))
    }
}

/// `HttpClient` fake: in-memory `url -> bytes` map; unknown urls are
/// `NetDownload`, and a SHA-256 mismatch on `download` is `PayloadCorrupt`.
pub struct FakeHttp {
    files: HashMap<String, Vec<u8>>,
}

impl FakeHttp {
    /// Serve exactly these urls.
    pub fn new(files: HashMap<String, Vec<u8>>) -> Self {
        Self { files }
    }
}

impl HttpClient for FakeHttp {
    fn get(&self, url: &str) -> Result<Vec<u8>, WizardError> {
        self.files.get(url).cloned().ok_or(WizardError::NetDownload)
    }

    fn download(&self, url: &str, dest: &Path, expected_sha256: &str) -> Result<(), WizardError> {
        let bytes = self.get(url)?;
        let actual = format!("{:x}", Sha256::digest(&bytes));
        if actual != expected_sha256 {
            return Err(WizardError::PayloadCorrupt);
        }
        std::fs::write(dest, &bytes).map_err(|_| WizardError::DiskFull)?;
        Ok(())
    }
}

/// `HostProbe` fake: fully configurable fixtures, `None` = probe failed.
/// Con contador de snapshots (L5-1): el menú debe capturar los facts UNA
/// vez por corrida, no re-probar por fila.
pub struct FakeHost {
    ram_total_gb: Option<f64>,
    ram_available_gb: Option<f64>,
    disk_free_gb: Option<f64>,
    gpu: Option<GpuInfo>,
    snapshots: RefCell<usize>,
}

impl FakeHost {
    /// Build with explicit fixture values (`None` = probe failed, D8.2).
    pub fn new(
        ram_total_gb: Option<f64>,
        ram_available_gb: Option<f64>,
        disk_free_gb: Option<f64>,
        gpu: Option<GpuInfo>,
    ) -> Self {
        Self {
            ram_total_gb,
            ram_available_gb,
            disk_free_gb,
            gpu,
            snapshots: RefCell::new(0),
        }
    }

    /// Snapshots servidos: 1 por corrida del menú (pin L5-1). `allow` porque
    /// targets sin este pin no lo tocan (common es módulo compartido).
    #[allow(dead_code)]
    pub fn snapshot_count(&self) -> usize {
        *self.snapshots.borrow()
    }
}

impl HostProbe for FakeHost {
    fn ram_total_gb(&self) -> Option<f64> {
        self.ram_total_gb
    }

    fn ram_available_gb(&self) -> Option<f64> {
        self.ram_available_gb
    }

    fn disk_free_gb(&self, _path: &Path) -> Option<f64> {
        self.disk_free_gb
    }

    fn gpu(&self) -> Option<GpuInfo> {
        self.gpu.clone()
    }

    fn snapshot(&self) -> tepochcalli::ports::HostFacts {
        *self.snapshots.borrow_mut() += 1;
        tepochcalli::ports::HostFacts {
            ram_total_gb: self.ram_total_gb,
            ram_available_gb: self.ram_available_gb,
            gpu: self.gpu.clone(),
        }
    }
}

/// `PayloadSource` fake: copies a fixture dir tree into `dest`.
pub struct FakePayload {
    src: PathBuf,
}

impl FakePayload {
    /// Serve copies of the fixture tree under `src`.
    pub fn new(src: &Path) -> Self {
        Self {
            src: src.to_path_buf(),
        }
    }
}

impl PayloadSource for FakePayload {
    fn materialize_report(&self, dest: &Path) -> Result<MergeReport, WizardError> {
        let mut written = Vec::new();
        let entries = std::fs::read_dir(&self.src).map_err(|_| WizardError::PayloadCorrupt)?;
        for entry in entries {
            let entry = entry.map_err(|_| WizardError::PayloadCorrupt)?;
            let name = entry.file_name();
            let target = dest.join(&name);
            std::fs::copy(entry.path(), &target).map_err(|_| WizardError::DiskFull)?;
            written.push(target);
        }
        Ok(MergeReport {
            written,
            skipped: Vec::new(),
        })
    }
}

/// Canned answers for `ScriptedUi`, consumed in call order.
#[derive(Default)]
pub struct FakeUiScript {
    /// Answers for successive `select` calls (chosen option index).
    pub selects: VecDeque<usize>,
    /// Answers for successive `input` calls.
    pub inputs: VecDeque<String>,
}

/// `Ui` fake: returns canned answers; exhausted script is `UserAborted`.
pub struct ScriptedUi {
    script: RefCell<FakeUiScript>,
}

impl ScriptedUi {
    /// Answer from this script, in call order.
    pub fn new(script: FakeUiScript) -> Self {
        Self {
            script: RefCell::new(script),
        }
    }
}

impl Ui for ScriptedUi {
    fn select(
        &self,
        _prompt: &str,
        _options: &[&str],
        _default_index: usize,
    ) -> Result<usize, WizardError> {
        self.script
            .borrow_mut()
            .selects
            .pop_front()
            .ok_or(WizardError::UserAborted)
    }

    fn input(&self, _prompt: &str, _default: Option<&str>) -> Result<String, WizardError> {
        self.script
            .borrow_mut()
            .inputs
            .pop_front()
            .ok_or(WizardError::UserAborted)
    }

    fn input_secret(&self, _prompt: &str) -> Result<String, WizardError> {
        // Misma cola que `input`: el script no especifica eco.
        self.script
            .borrow_mut()
            .inputs
            .pop_front()
            .ok_or(WizardError::UserAborted)
    }

    fn panel(&self, _title: &str, _body: &str) {}
}

// --- RecordingProc: CommandRunner fake que REGISTRA argv/env (T12/T16) ---

/// Una invocación hija registrada: programa, argv, cwd y env (copias propias).
#[derive(Debug, Clone)]
pub struct Call {
    /// Programa lanzado (intérprete del venv o binario).
    pub program: String,
    /// Argumentos, en orden.
    pub args: Vec<String>,
    /// Directorio de ejecución.
    pub cwd: PathBuf,
    /// Variables de entorno explícitas de la llamada.
    pub env: Vec<(String, String)>,
}

/// `CommandRunner` fake que REGISTRA cada llamada antes de repertir el
/// guion: única forma de afirmar «no se lanzó el gate» / «la clave llegó
/// solo al env de un hijo» (FakeProc no guarda argv/env). Guion agotado
/// (o llamada inesperada) es `Internal` — bug del test.
pub struct RecordingProc {
    script: RefCell<VecDeque<Result<CommandOutput, WizardError>>>,
    calls: RefCell<Vec<Call>>,
}

impl RecordingProc {
    /// Build from any ordered script of results.
    pub fn scripted(script: impl IntoIterator<Item = Result<CommandOutput, WizardError>>) -> Self {
        Self {
            script: RefCell::new(script.into_iter().collect()),
            calls: RefCell::new(Vec::new()),
        }
    }

    /// Calls registradas hasta ahora (copias propias).
    pub fn calls(&self) -> Vec<Call> {
        self.calls.borrow().clone()
    }
}

impl CommandRunner for RecordingProc {
    fn run(
        &self,
        program: &str,
        args: &[&str],
        cwd: &Path,
        env: &[(&str, &str)],
    ) -> Result<CommandOutput, WizardError> {
        self.calls.borrow_mut().push(Call {
            program: program.to_string(),
            args: args.iter().map(|arg| (*arg).to_string()).collect(),
            cwd: cwd.to_path_buf(),
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

// --- TapUi: Ui fake que graba todo y responde por guion (T11(g)) ---

/// Evento de UI grabado, en orden de llamada (la respuesta viene del script,
/// nunca del evento).
#[derive(Debug, Clone)]
pub enum UiEvent {
    /// `select`: prompt, opciones y fila preseleccionada.
    Select {
        /// Prompt mostrado.
        prompt: String,
        /// Opciones mostradas, en orden.
        options: Vec<String>,
        /// Fila preseleccionada.
        default: usize,
    },
    /// `input`: prompt (canal con eco).
    Input {
        /// Prompt mostrado.
        prompt: String,
    },
    /// `input_secret`: prompt (canal SIN eco).
    Secret {
        /// Prompt mostrado.
        prompt: String,
    },
    /// `panel`: título y cuerpo.
    Panel {
        /// Título del panel.
        title: String,
        /// Cuerpo del panel.
        body: String,
    },
}

/// `Ui` fake that records every prompt/panel (never the answers) and
/// answers from its script; exhausted script is `UserAborted` (same
/// invariant as `ScriptedUi`). `captured()` expone los formatos de captura
/// EXACTOS que aserta `int_embedder_menu`; `events()` da la secuencia
/// ordenada para los tests de orden de pasos y de paneles.
pub struct TapUi {
    selects: RefCell<VecDeque<usize>>,
    inputs: RefCell<VecDeque<String>>,
    events: RefCell<Vec<UiEvent>>,
}

impl TapUi {
    /// Answers from this script, in call order.
    pub fn new(selects: Vec<usize>, inputs: Vec<String>) -> Self {
        Self {
            selects: RefCell::new(selects.into()),
            inputs: RefCell::new(inputs.into()),
            events: RefCell::new(Vec::new()),
        }
    }

    /// Eventos grabados, en orden.
    pub fn events(&self) -> Vec<UiEvent> {
        self.events.borrow().clone()
    }

    /// Captura de texto con los formatos exactos del menú:
    /// `SELECT default={d} {prompt} :: {opts}` · `INPUT {p}` ·
    /// `SECRET INPUT {p}` · `PANEL {t} :: {b}`.
    pub fn captured(&self) -> Vec<String> {
        self.events
            .borrow()
            .iter()
            .map(|event| match event {
                UiEvent::Select {
                    prompt,
                    options,
                    default,
                } => format!(
                    "SELECT default={default} {prompt} :: {}",
                    options.join(" | ")
                ),
                UiEvent::Input { prompt } => format!("INPUT {prompt}"),
                UiEvent::Secret { prompt } => format!("SECRET INPUT {prompt}"),
                UiEvent::Panel { title, body } => format!("PANEL {title} :: {body}"),
            })
            .collect()
    }
}

impl Ui for TapUi {
    fn select(
        &self,
        prompt: &str,
        options: &[&str],
        default_index: usize,
    ) -> Result<usize, WizardError> {
        self.events.borrow_mut().push(UiEvent::Select {
            prompt: prompt.to_string(),
            options: options.iter().map(|o| (*o).to_string()).collect(),
            default: default_index,
        });
        self.selects
            .borrow_mut()
            .pop_front()
            .ok_or(WizardError::UserAborted)
    }

    fn input(&self, prompt: &str, _default: Option<&str>) -> Result<String, WizardError> {
        self.events.borrow_mut().push(UiEvent::Input {
            prompt: prompt.to_string(),
        });
        self.inputs
            .borrow_mut()
            .pop_front()
            .ok_or(WizardError::UserAborted)
    }

    fn input_secret(&self, prompt: &str) -> Result<String, WizardError> {
        self.events.borrow_mut().push(UiEvent::Secret {
            prompt: prompt.to_string(),
        });
        self.inputs
            .borrow_mut()
            .pop_front()
            .ok_or(WizardError::UserAborted)
    }

    fn panel(&self, title: &str, body: &str) {
        self.events.borrow_mut().push(UiEvent::Panel {
            title: title.to_string(),
            body: body.to_string(),
        });
    }
}
