//! `Ui`: the five interactions the installer needs (`TtyUi` with the
//! ratatui menu and its line-based fallback, `HeadlessUi` scripted, and the
//! `ScriptedUi`/`TapUi` fakes in tests).

use std::cell::RefCell;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::Duration;

use crate::domain::{CancelToken, MenuAction, MenuSpec, WizardError};

/// Everything the H5 menu renders, resolved by the caller: the pure spec plus
/// the three facts the header shows. `embedder` arrives as a ready label —
/// this port never reads the vault.
#[derive(Debug, Clone, Copy)]
pub struct MenuView<'a> {
    /// Buttons and state message (pure domain matrix).
    pub spec: &'a MenuSpec,
    /// Version this binary manages.
    pub wizard: &'a str,
    /// Canonical installed version (`None` = no runtime yet).
    pub installed: Option<&'a str>,
    /// Embedder state, already worded (`externo (API key)`/…).
    pub embedder: &'a str,
}

/// Etapas declaradas por el llamador para una operación con progreso real.
/// `eta` solo se rellena con una estimación declarada: `None` ⇒ `ETA —`.
#[derive(Debug, Clone)]
pub struct ProgressSpec {
    /// Título de la pantalla.
    pub title: String,
    /// Número de hitos; la barra avanza de 0 a `steps`.
    pub steps: usize,
    /// Estimación declarada por el llamador (nunca calculada por la UI).
    pub eta: Option<Duration>,
}

/// Contador de hitos compartido con el watcher de la UI. `advance()` es el
/// único mutador; la UI solo lee (`SeqCst`) y acota el valor al total.
#[derive(Debug, Clone)]
pub struct Progress {
    done: Arc<AtomicUsize>,
    total: usize,
}

impl Progress {
    /// Contador en cero para `total` hitos.
    #[must_use]
    pub fn new(total: usize) -> Self {
        Self {
            done: Arc::new(AtomicUsize::new(0)),
            total,
        }
    }

    /// Marca un hito completado; el acote al total ocurre al escribir, en el
    /// único mutador (el `min` de [`Progress::done`] sigue como defensa).
    pub fn advance(&self) {
        let _ = self
            .done
            .try_update(Ordering::SeqCst, Ordering::SeqCst, |v| {
                Some((v + 1).min(self.total))
            });
    }

    /// Hitos completados, nunca más de los declarados.
    #[must_use]
    pub fn done(&self) -> usize {
        self.done.load(Ordering::SeqCst).min(self.total)
    }
}

thread_local! {
    /// Barra activa en esta hebra: el código anidado bajo `run_stages`
    /// (gate de descarga, scopes de desinstall) marca hitos sin cambiar
    /// firmas; sin pantalla activa todo es no-op.
    static ACTIVE_PROGRESS: RefCell<Option<Progress>> = const { RefCell::new(None) };
}

/// Publica el contador de la pantalla de hitos en curso.
pub fn set_active_progress(progress: Option<&Progress>) {
    ACTIVE_PROGRESS.with(|cell| *cell.borrow_mut() = progress.cloned());
}

/// Marca un hito en la barra activa; sin barra, no-op.
pub fn advance_active_stage() {
    ACTIVE_PROGRESS.with(|cell| {
        if let Some(progress) = cell.borrow().as_ref() {
            progress.advance();
        }
    });
}

/// `true` mientras haya una pantalla de hitos en esta hebra.
#[must_use]
pub fn has_active_progress() -> bool {
    ACTIVE_PROGRESS.with(|cell| cell.borrow().is_some())
}

/// Installer dialogue. `panel` only renders (errors surface via `Result`
/// returns), and every answer method fails with a typed error instead of
/// guessing when input is missing.
pub trait Ui {
    /// Single-choice menu; `default_index` is the preselected row.
    /// Returns the chosen index into `options`.
    fn select(
        &self,
        prompt: &str,
        options: &[&str],
        default_index: usize,
    ) -> Result<usize, WizardError>;
    /// Free-text answer; `default` is used when the user enters nothing.
    fn input(&self, prompt: &str, default: Option<&str>) -> Result<String, WizardError>;
    /// Secret answer (api_key/HF_TOKEN): never echoed back on a terminal
    /// (L2-7). Headless rotates the same queue as `input` (scripted).
    fn input_secret(&self, prompt: &str) -> Result<String, WizardError>;
    /// Informational/error block (failure UX panel in T15).
    fn panel(&self, title: &str, body: &str);
    /// H5 menu over the caller-resolved [`MenuView`]. Returns the chosen
    /// action; a button disabled in the spec is never returned (typed abort
    /// instead).
    fn menu(&self, view: &MenuView<'_>) -> Result<MenuAction, WizardError>;
    /// R-offline-2: ejecuta `work` bajo una pantalla cuyo botón Cancelar está
    /// habilitado (Esc / Ctrl+C también) y que bloquea el resto con razón
    /// visible. `work` recibe el mismo `cancel`; la UI no decide el resultado.
    /// Default (sin TTY): `work()` en línea, sin pantalla.
    fn run_cancellable(&self, title: &str, cancel: &CancelToken, work: &mut dyn FnMut()) {
        let _ = (title, cancel);
        work();
    }
    /// Progreso por hitos: la UI dibuja la barra y el spinner mientras `work`
    /// avanza [`Progress`]. Default (sin TTY): `work` en línea,
    /// sin pantalla ni escritura — igual que `run_cancellable`.
    fn run_stages(
        &self,
        spec: &ProgressSpec,
        cancel: &CancelToken,
        work: &mut dyn FnMut(&Progress),
    ) {
        let _ = (spec, cancel);
        let progress = Progress::new(spec.steps);
        work(&progress);
    }
    /// H11: bloquea hasta una tecla; por defecto no-op (headless).
    fn wait_key(&self) {}
}
