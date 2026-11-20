//! `Ui` adapters (T6/T8): [`TtyUi`] renders the H5 menu with ratatui on a
//! real TTY and falls back to `dialoguer` otherwise; [`HeadlessUi`] answers
//! from a script for `--non-interactive` (CI/pipes).
//!
//! Both keep messages on stderr; the panel uses color only on a terminal.

use std::cell::RefCell;
use std::collections::VecDeque;
use std::io::IsTerminal;

use crate::domain::{MenuAction, WizardError};
use crate::ports::{MenuView, Ui};

/// Interactive dialogue: full-screen ratatui menu on a TTY, `dialoguer`
/// line-based fallback when there is none.
///
/// Every prompt failure (no TTY, EOF, Esc, Ctrl-C) is
/// [`WizardError::UserAborted`]: without a terminal the caller must use
/// [`HeadlessUi`] instead.
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

    fn menu(&self, view: &MenuView<'_>) -> Result<MenuAction, WizardError> {
        // Pantalla completa solo con un TTY real; sin él, el mismo contenido
        // en line-based. `ratatui::init` no devuelve error (entra en pánico):
        // no hay init fallido que capturar, solo el aborto tipado del bucle.
        if std::io::stdout().is_terminal() && std::io::stdin().is_terminal() {
            return super::ui_ratatui::run_menu(view);
        }
        self.line_menu(view)
    }
}

impl TtyUi {
    /// Fallback sin full-screen: cabecera con las versiones y el embedder,
    /// razones de los deshabilitados, luego un `Select` que ofrece solo los
    /// habilitados.
    fn line_menu(&self, view: &MenuView<'_>) -> Result<MenuAction, WizardError> {
        let spec = view.spec;
        let enabled: Vec<usize> = spec
            .buttons
            .iter()
            .enumerate()
            .filter(|(_, button)| button.enabled)
            .map(|(index, _)| index)
            .collect();
        if enabled.is_empty() {
            return Err(WizardError::UserAborted);
        }

        let mut body = format!(
            "Tepochcalli {} · instalada: {} · embedder: {}\n",
            view.wizard,
            view.installed.unwrap_or("—"),
            view.embedder
        );
        for button in spec.buttons.iter().filter(|button| !button.enabled) {
            if let Some(reason) = button.reason {
                body.push_str(&format!(
                    "{} {}: {reason}\n",
                    button.action.icon(),
                    button.action.label()
                ));
            }
        }
        if let Some(notice) = spec.notice {
            body.push_str(notice);
        }
        render_panel("Tepochcalli", body.trim_end());

        let labels: Vec<String> = enabled
            .iter()
            .map(|&index| {
                let action = spec.buttons[index].action;
                format!("{} {}", action.icon(), action.label())
            })
            .collect();
        let items: Vec<&str> = labels.iter().map(String::as_str).collect();
        let picked = dialoguer::Select::new()
            .with_prompt("What do you want to do?")
            .items(&items)
            .default(0)
            .interact()
            .map_err(|_| WizardError::UserAborted)?;
        super::ui_ratatui::choose(spec, enabled[picked])
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

    fn menu(&self, view: &MenuView<'_>) -> Result<MenuAction, WizardError> {
        // El guion elige por índice de botón: un índice deshabilitado o una
        // cola agotada aborta tipado — nunca se adivina. Las versiones y el
        // embedder solo alimentan el header del render, que aquí no se dibuja.
        let index = self
            .selects
            .borrow_mut()
            .pop_front()
            .ok_or(WizardError::UserAborted)?;
        super::ui_ratatui::choose(view.spec, index)
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
