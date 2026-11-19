//! `Ui` adapters (T6): [`TtyUi`] over `dialoguer` for interactive runs,
//! [`HeadlessUi`] with scripted answers for `--non-interactive` (CI/pipes).
//!
//! Both keep messages on stderr; the panel uses color only on a terminal.

use std::cell::RefCell;
use std::collections::VecDeque;
use std::io::IsTerminal;

use crate::domain::WizardError;
use crate::ports::Ui;

/// Interactive dialogue over `dialoguer` (line-based, D23 — no ratatui).
///
/// Every prompt failure (no TTY, EOF, Esc) is [`WizardError::UserAborted`]:
/// without a terminal the caller must use [`HeadlessUi`] instead.
#[derive(Debug, Default, Clone, Copy)]
pub struct TtyUi;

impl Ui for TtyUi {
    fn select(
        &self,
        prompt: &str,
        options: &[&str],
        default_index: usize,
    ) -> Result<usize, WizardError> {
        if options.is_empty() || default_index >= options.len() {
            return Err(WizardError::UserAborted);
        }
        dialoguer::Select::new()
            .with_prompt(prompt)
            .items(options)
            .default(default_index)
            .interact()
            .map_err(|_| WizardError::UserAborted)
    }

    fn input(&self, prompt: &str, default: Option<&str>) -> Result<String, WizardError> {
        let mut asked = dialoguer::Input::<String>::new().with_prompt(prompt);
        if let Some(fallback) = default {
            asked = asked.default(fallback.to_string());
        }
        asked.interact_text().map_err(|_| WizardError::UserAborted)
    }

    fn input_secret(&self, prompt: &str) -> Result<String, WizardError> {
        // Password::interact no repite el secreto en el terminal (L2-7).
        dialoguer::Password::new()
            .with_prompt(prompt)
            .interact()
            .map_err(|_| WizardError::UserAborted)
    }

    fn panel(&self, title: &str, body: &str) {
        render_panel(title, body);
    }
}

/// Scripted dialogue for `--non-interactive`: answers come from flags, in
/// call order. An exhausted script is [`WizardError::UserAborted`] — never a
/// guess, never a stdin read.
#[derive(Debug, Default)]
pub struct HeadlessUi {
    selects: RefCell<VecDeque<usize>>,
    inputs: RefCell<VecDeque<String>>,
}

impl HeadlessUi {
    /// Answers in call order per question kind.
    #[must_use]
    pub fn new(selects: VecDeque<usize>, inputs: VecDeque<String>) -> Self {
        Self {
            selects: RefCell::new(selects),
            inputs: RefCell::new(inputs),
        }
    }

    /// Answers derived from `install` flags (L3-4): rows come from `main`
    /// as real EMBEDDER_PATHS indices — the constructor no longer hardcodes
    /// the D7.1 numbering. `skip_row` answers the single F6 menu row under
    /// `--skip-model`; `default_row` (MiniLM) otherwise, followed by the
    /// device row (`0` = `cpu`, H9/ADR-015). The former vault
    /// param was dead: `--vault` resolves by flag and an absent flag must
    /// abort typed (never guess), so no queue entry ever helped.
    #[must_use]
    pub fn for_install(skip_row: usize, default_row: usize, skip_model: bool) -> Self {
        // El menú de dispositivo solo se pregunta en los paths locales: `cpu`
        // es la fila 0 y la elección explícita sigue siendo del usuario.
        let rows = if skip_model {
            vec![skip_row]
        } else {
            vec![default_row, 0]
        };
        Self {
            selects: RefCell::new(VecDeque::from(rows)),
            inputs: RefCell::new(VecDeque::new()),
        }
    }
}

impl Ui for HeadlessUi {
    fn select(
        &self,
        _prompt: &str,
        options: &[&str],
        _default_index: usize,
    ) -> Result<usize, WizardError> {
        let chosen = self
            .selects
            .borrow_mut()
            .pop_front()
            .ok_or(WizardError::UserAborted)?;
        if chosen >= options.len() {
            return Err(WizardError::UserAborted);
        }
        Ok(chosen)
    }

    fn input(&self, _prompt: &str, _default: Option<&str>) -> Result<String, WizardError> {
        // The offered `default` is deliberately ignored: without a scripted
        // answer there is nothing to fall back to, and guessing is forbidden.
        self.inputs
            .borrow_mut()
            .pop_front()
            .ok_or(WizardError::UserAborted)
    }

    fn input_secret(&self, _prompt: &str) -> Result<String, WizardError> {
        // Misma cola que `input`: un script no distingue eco.
        self.inputs
            .borrow_mut()
            .pop_front()
            .ok_or(WizardError::UserAborted)
    }

    fn panel(&self, title: &str, body: &str) {
        render_panel(title, body);
    }
}

/// Error/failure block on stderr; ANSI only on a real terminal (and never
/// with `NO_COLOR` set), plain text otherwise so pipes stay parseable.
fn render_panel(title: &str, body: &str) {
    let color = std::io::stderr().is_terminal() && std::env::var_os("NO_COLOR").is_none();
    if color {
        eprintln!("\x1b[1;31m== {title} ==\x1b[0m\n{body}");
    } else {
        eprintln!("== {title} ==\n{body}");
    }
}
