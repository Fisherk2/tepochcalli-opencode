//! `Ui` adapters (T6/T8): [`TtyUi`] renders the H5 menu with ratatui on a
//! real TTY and falls back to `dialoguer` otherwise; [`HeadlessUi`] answers
//! from a script for `--non-interactive` (CI/pipes).
//!
//! Both keep messages on stderr; the panel uses color only on a terminal.

use std::cell::RefCell;
use std::collections::VecDeque;
use std::io::IsTerminal;

use crate::domain::{CancelToken, MenuAction, WizardError};
use crate::ports::{MenuView, Progress, ProgressSpec, Ui};

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

    fn run_cancellable(&self, title: &str, cancel: &CancelToken, work: &mut dyn FnMut()) {
        // Pantalla completa solo con un TTY real (misma guarda que `menu`):
        // sin él no hay a quién preguntar y `work` corre en línea.
        if std::io::stdout().is_terminal() && std::io::stdin().is_terminal() {
            super::ui_ratatui::run_progress(title, cancel, work);
        } else {
            work();
        }
    }

    fn run_stages(
        &self,
        spec: &ProgressSpec,
        cancel: &CancelToken,
        work: &mut dyn FnMut(&Progress),
    ) {
        // Misma guarda que `menu`/`run_cancellable`: sin TTY la operación corre
        // en línea y el default del puerto no escribe nada.
        if std::io::stdout().is_terminal() && std::io::stdin().is_terminal() {
            super::ui_ratatui::run_stages(spec, cancel, work);
        } else {
            work(&Progress::new(spec.steps));
        }
    }

    fn wait_key(&self) {
        super::ui_ratatui::wait_any_key();
    }
}

impl TtyUi {
    /// Fallback sin full-screen: cabecera con las versiones y el embedder,
    /// razones de los deshabilitados, luego un `Select` que ofrece solo los
    /// habilitados.
    fn line_menu(&self, view: &MenuView<'_>) -> Result<MenuAction, WizardError> {
        let Some(plan) = line_menu_plan(view) else {
            return Err(WizardError::UserAborted);
        };
        render_panel("Tepochcalli", plan.body.trim_end());

        let items: Vec<&str> = plan.labels.iter().map(String::as_str).collect();
        let picked = dialoguer::Select::new()
            .with_prompt("What do you want to do?")
            .items(&items)
            .default(0)
            .interact()
            .map_err(|_| WizardError::UserAborted)?;
        super::ui_ratatui::choose(view.spec, plan.enabled[picked])
    }
}

/// What the line-based fallback shows: the rows the `Select` offers (only
/// enabled buttons, in spec order) plus the panel text printed before asking
/// — the header, every disabled reason and the state notice. `None` when
/// nothing is enabled: there is nothing to offer, so nothing is drawn.
struct LineMenuPlan {
    /// Indices into `spec.buttons`, in spec order.
    enabled: Vec<usize>,
    /// `icon label` per enabled button, in the same order.
    labels: Vec<String>,
    /// Header + disabled reasons + notice, as the panel prints it.
    body: String,
}

/// Header line shared by the full-screen menu and the line fallback.
#[must_use]
pub fn header_line(view: &MenuView<'_>) -> String {
    format!(
        "Tepochcalli {} · instalada: {} · embedder: {}",
        view.wizard,
        view.installed.unwrap_or("—"),
        view.embedder
    )
}

fn line_menu_plan(view: &MenuView<'_>) -> Option<LineMenuPlan> {
    let spec = view.spec;
    let enabled: Vec<usize> = spec
        .buttons
        .iter()
        .enumerate()
        .filter(|(_, button)| button.enabled)
        .map(|(index, _)| index)
        .collect();
    if enabled.is_empty() {
        return None;
    }

    let mut body = header_line(view);
    body.push('\n');
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

    let labels = enabled
        .iter()
        .map(|&index| {
            let action = spec.buttons[index].action;
            format!("{} {}", action.icon(), action.label())
        })
        .collect();
    Some(LineMenuPlan {
        enabled,
        labels,
        body,
    })
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
    /// param was dead: the vault comes from `--vault` or the process cwd,
    /// so no queue entry ever helped.
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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::domain::{menu_spec, InstalledState, MenuButton, MenuSpec};

    fn view(spec: &MenuSpec) -> MenuView<'_> {
        MenuView {
            spec,
            wizard: "0.1.0",
            installed: Some("0.1.0"),
            embedder: "sin configurar",
        }
    }

    #[test]
    fn offers_the_select_only_the_enabled_buttons_in_spec_order() {
        // Outdated: Update/Change Embedder/Desinstall/Exit enabled, Install off.
        let spec = menu_spec(InstalledState::Outdated);
        let plan = line_menu_plan(&view(&spec)).expect("Exit keeps the menu alive");

        assert_eq!(
            plan.labels,
            vec![
                "🟢 Update",
                "🟣 Change Embedder",
                "🔴 Desinstall",
                "🟠 Exit"
            ],
            "the Select must not offer the disabled Install row"
        );
        for (index, label) in plan.enabled.iter().zip(&plan.labels) {
            let button = &spec.buttons[*index];
            assert!(button.enabled, "only enabled rows are offered");
            assert_eq!(
                *label,
                format!("{} {}", button.action.icon(), button.action.label())
            );
        }
    }

    #[test]
    fn prints_every_disabled_reason_before_asking() {
        // NotInstalled: three disabled buttons, each with its own reason.
        let spec = menu_spec(InstalledState::NotInstalled);
        let plan = line_menu_plan(&view(&spec)).expect("Install keeps the menu alive");

        for button in spec.buttons.iter().filter(|button| !button.enabled) {
            let reason = button
                .reason
                .expect("a disabled button always carries a reason");
            let line = format!(
                "{} {}: {reason}",
                button.action.icon(),
                button.action.label()
            );
            assert!(
                plan.body.contains(&line),
                "the panel must print `{line}` before asking:\n{}",
                plan.body
            );
        }
    }

    #[test]
    fn carries_the_header_and_the_state_notice_to_the_panel() {
        let spec = menu_spec(InstalledState::NotInstalled);
        let plan = line_menu_plan(&view(&spec)).expect("Install keeps the menu alive");

        assert!(
            plan.body
                .starts_with("Tepochcalli 0.1.0 · instalada: 0.1.0 · embedder: sin configurar"),
            "header first:\n{}",
            plan.body
        );
        assert!(
            plan.body.contains("directorio listo para instalar"),
            "the notice reaches the panel:\n{}",
            plan.body
        );
    }

    #[test]
    fn a_menu_with_nothing_enabled_has_no_plan() {
        // The typed abort behind an empty `Select`: nothing to offer, nothing
        // to ask — the panel is never drawn either.
        let spec = MenuSpec {
            buttons: vec![MenuButton {
                action: MenuAction::Exit,
                enabled: false,
                reason: Some("nada habilitado"),
            }],
            notice: None,
        };
        assert!(line_menu_plan(&view(&spec)).is_none());
    }
}
