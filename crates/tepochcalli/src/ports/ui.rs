//! `Ui`: the five interactions the installer needs (`TtyUi` with the
//! ratatui menu and its line-based fallback, `HeadlessUi` scripted, and the
//! `ScriptedUi`/`TapUi` fakes in tests).

use std::cell::RefCell;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Condvar, Mutex, MutexGuard, PoisonError};
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

/// Tecla que el watcher reenvía al diálogo, ya traducida desde crossterm:
/// el puerto no depende de la librería de terminal.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DialogKey {
    /// Fila anterior (↑ / k / BackTab).
    Previous,
    /// Fila siguiente (↓ / j / Tab).
    Next,
    /// Confirmar fila o texto (Enter).
    Confirm,
    /// Borrar el último carácter de una entrada libre.
    Backspace,
    /// Carácter de una entrada libre.
    Char(char),
    /// Abortar (Esc / Ctrl+C), compartiendo el token de cancelación.
    Cancel,
}

/// Lo que el watcher pinta en la zona central mientras la barra está activa.
#[derive(Debug, Clone)]
pub enum Dialog {
    /// Lista de opciones; `cursor` es la fila resaltada.
    Select {
        /// Enunciado de la pregunta.
        prompt: String,
        /// Opciones ofrecidas, en orden.
        options: Vec<String>,
        /// Fila preseleccionada.
        cursor: usize,
    },
    /// Entrada libre.
    Input {
        /// Enunciado de la pregunta.
        prompt: String,
        /// Texto tecleado hasta ahora.
        value: String,
        /// `true` para secretos: el frame no hace eco del contenido.
        secret: bool,
    },
    /// Aviso que no espera respuesta (panel).
    Notice {
        /// Título del aviso.
        title: String,
        /// Cuerpo del aviso.
        body: String,
    },
}

/// Respuesta escrita por el watcher a un diálogo pendiente.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DialogOutcome {
    /// Índice elegido en un `select`.
    Index(usize),
    /// Texto introducido en un `input`.
    Text(String),
    /// Enter acusó recibo de un `Notice`: el frame ya se pintó.
    Noticed,
    /// El usuario abortó o el watcher cerró la pantalla.
    Aborted,
}

#[derive(Debug, Default)]
struct DialogState {
    active: Option<Dialog>,
    outcome: Option<DialogOutcome>,
}

/// Handshake entre `select`/`input`/`panel` y el watcher: una sola pantalla
/// pintada y una sola cola de teclas. `wait` despierta por `Condvar`, sin
/// espera activa; `clear` resuelve como aborto para no dejar a nadie colgado.
#[derive(Debug, Default)]
pub struct DialogHandle {
    state: Mutex<DialogState>,
    changed: Condvar,
}

impl DialogHandle {
    fn lock(&self) -> MutexGuard<'_, DialogState> {
        self.state.lock().unwrap_or_else(PoisonError::into_inner)
    }

    /// Publica un diálogo para el watcher, descartando respuestas anteriores.
    pub fn request(&self, dialog: Dialog) {
        let mut state = self.lock();
        state.outcome = None;
        state.active = Some(dialog);
        self.changed.notify_all();
    }

    /// Copia del diálogo en curso, para pintarlo sin retener el lock.
    #[must_use]
    pub fn snapshot(&self) -> Option<Dialog> {
        self.lock().active.clone()
    }

    /// Costura del watcher (y de sus fakes): espera la siguiente petición.
    #[must_use]
    pub fn wait_for_request(&self) -> Option<Dialog> {
        let mut state = self.lock();
        while state.active.is_none() {
            state = self
                .changed
                .wait(state)
                .unwrap_or_else(PoisonError::into_inner);
        }
        state.active.clone()
    }

    /// Enruta una tecla del watcher; `false` = no era para este diálogo.
    pub fn handle(&self, key: DialogKey, cancel: &CancelToken) -> bool {
        let mut state = self.lock();
        let Some(dialog) = state.active.as_mut() else {
            return false;
        };
        let outcome = match dialog {
            Dialog::Select {
                options, cursor, ..
            } => match key {
                DialogKey::Previous => {
                    if !options.is_empty() {
                        *cursor = (*cursor + options.len() - 1) % options.len();
                    }
                    None
                }
                DialogKey::Next => {
                    if !options.is_empty() {
                        *cursor = (*cursor + 1) % options.len();
                    }
                    None
                }
                DialogKey::Confirm => Some(DialogOutcome::Index(*cursor)),
                DialogKey::Cancel => Some(DialogOutcome::Aborted),
                _ => return false,
            },
            Dialog::Input { value, .. } => match key {
                DialogKey::Char(ch) => {
                    value.push(ch);
                    None
                }
                DialogKey::Backspace => {
                    value.pop();
                    None
                }
                DialogKey::Confirm => Some(DialogOutcome::Text(value.clone())),
                DialogKey::Cancel => Some(DialogOutcome::Aborted),
                _ => return false,
            },
            Dialog::Notice { .. } => match key {
                // El aviso retiene el frame hasta que Enter lo acusa; sin este
                // ack un `select` posterior borraría el texto sin ser leído.
                DialogKey::Confirm => Some(DialogOutcome::Noticed),
                _ => return false,
            },
        };
        if let Some(outcome) = outcome {
            if outcome == DialogOutcome::Aborted {
                cancel.cancel();
            }
            state.active = None;
            state.outcome = Some(outcome);
            self.changed.notify_all();
        }
        true
    }

    /// Bloquea hasta que el watcher resuelve o cierra el diálogo.
    #[must_use]
    pub fn wait(&self) -> DialogOutcome {
        let mut state = self.lock();
        while state.outcome.is_none() {
            state = self
                .changed
                .wait(state)
                .unwrap_or_else(PoisonError::into_inner);
        }
        state.outcome.take().unwrap_or(DialogOutcome::Aborted)
    }

    /// Cierra el diálogo y despierta a quien esperaba (mitigación del
    /// deadlock en todo exit del watcher).
    pub fn clear(&self) {
        let mut state = self.lock();
        if state.active.take().is_some() && state.outcome.is_none() {
            state.outcome = Some(DialogOutcome::Aborted);
        }
        self.changed.notify_all();
    }
}

thread_local! {
    /// Pantalla con watcher propio en esta hebra: las preguntas delegan en él
    /// en vez de abrir un segundo prompt sobre el mismo TTY.
    static ACTIVE_DIALOG: RefCell<Option<Arc<DialogHandle>>> = const { RefCell::new(None) };
}

/// Publica el diálogo del watcher en esta hebra.
pub fn set_active_dialog(handle: Option<&Arc<DialogHandle>>) {
    ACTIVE_DIALOG.with(|cell| *cell.borrow_mut() = handle.cloned());
}

/// Diálogo del watcher de esta hebra, si hay pantalla propia.
#[must_use]
pub fn active_dialog() -> Option<Arc<DialogHandle>> {
    ACTIVE_DIALOG.with(|cell| cell.borrow().clone())
}

/// `true` mientras el watcher sea el dueño de la pantalla en esta hebra.
#[must_use]
pub fn has_active_dialog() -> bool {
    ACTIVE_DIALOG.with(|cell| cell.borrow().is_some())
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
