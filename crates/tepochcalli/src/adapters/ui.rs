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

    /// Answers derived from `install` flags: `skip_model` preselects the
    /// "configure later" row, `vault` answers the directory question.
    #[must_use]
    pub fn for_install(skip_model: bool, vault: Option<String>) -> Self {
        Self {
            selects: RefCell::new(VecDeque::from([if skip_model { 4 } else { 0 }])),
            inputs: RefCell::new(vault.into_iter().collect()),
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
