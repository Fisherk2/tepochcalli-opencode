//! `Ui`: the four interactions the installer needs (`TtyUi` vs
//! `HeadlessUi` in T6; `ScriptedUi` fake in tests).

use crate::domain::WizardError;

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
    /// Yes/no question; `default` is used when the user enters nothing.
    fn confirm(&self, prompt: &str, default: bool) -> Result<bool, WizardError>;
    /// Informational/error block (failure UX panel in T15).
    fn panel(&self, title: &str, body: &str);
}
