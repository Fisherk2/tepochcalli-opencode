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
