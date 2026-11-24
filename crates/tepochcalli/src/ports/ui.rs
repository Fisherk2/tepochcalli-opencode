//! `Ui`: the five interactions the installer needs (`TtyUi` with the
//! ratatui menu and its line-based fallback, `HeadlessUi` scripted, and the
//! `ScriptedUi`/`TapUi` fakes in tests).

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
    /// H11: bloquea hasta una tecla; por defecto no-op (headless).
    fn wait_key(&self) {}
}
