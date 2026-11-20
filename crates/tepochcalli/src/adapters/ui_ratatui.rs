//! H5 menu, full-screen (ratatui 0.30 + crossterm 0.29): real buttons with a
//! visible disabled state and the reason next to every blocked action.
//!
//! [`render_menu`] is pure (no I/O, no file reads) so tests can drive it with
//! `TestBackend`; [`run_menu`] owns the terminal and restores it on every
//! exit path.

use std::io::IsTerminal;

use crossterm::event::{self, Event, KeyCode, KeyModifiers};
use ratatui::layout::{Constraint, Layout};
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span, Text};
use ratatui::widgets::{List, ListItem, ListState, Paragraph, Wrap};
use ratatui::Frame;

use crate::domain::{MenuAction, MenuSpec, WizardError};
use crate::ports::MenuView;

/// Contact shown at the bottom of the menu (H5).
const REPO: &str = "https://github.com/Fisherk2/tepochcalli-opencode";
const CONTACT: &str = "dev@fisherk2.com";

/// Maps a chosen button index to its action. A disabled or out-of-range
/// index is a typed abort: the wizard never invents a selection.
pub fn choose(spec: &MenuSpec, index: usize) -> Result<MenuAction, WizardError> {
    match spec.buttons.get(index) {
        Some(button) if button.enabled => Ok(button.action),
        _ => Err(WizardError::UserAborted),
    }
}

/// Draws the whole menu into `frame`. Every fact comes resolved in `view`
/// (this function never touches the disk).
pub fn render_menu(frame: &mut Frame, view: &MenuView<'_>, selected: usize) {
    let spec = view.spec;
    let notice_rows = if spec.notice.is_some() { 3 } else { 0 };
    let [header_area, list_area, notice_area, contact_area] = Layout::vertical([
        Constraint::Length(1),
        Constraint::Min(1),
        Constraint::Length(notice_rows),
        Constraint::Length(3),
    ])
    .areas(frame.area());

    let header = Paragraph::new(Line::from(format!(
        "Tepochcalli {} · instalada: {} · embedder: {}",
        view.wizard,
        view.installed.unwrap_or("—"),
        view.embedder
    )))
    .style(Style::new().add_modifier(Modifier::BOLD));
    frame.render_widget(header, header_area);

    let items: Vec<ListItem> = spec
        .buttons
        .iter()
        .map(|button| {
            let mut line = Line::from(vec![
                Span::raw(format!("{} ", button.action.icon())),
                Span::raw(button.action.label()),
            ]);
            if let Some(reason) = button.reason {
                line.push_span(Span::raw(format!("  — {reason}")));
            }
            let style = if button.enabled {
                Style::new()
            } else {
                Style::new().add_modifier(Modifier::DIM)
            };
            ListItem::new(line).style(style)
        })
        .collect();
    let list = List::new(items)
        .highlight_symbol("› ")
        .highlight_style(Style::new().add_modifier(Modifier::REVERSED));
    let mut state = ListState::default().with_selected(Some(selected));
    frame.render_stateful_widget(list, list_area, &mut state);

    if let Some(notice) = spec.notice {
        // El comando entre backticks va en su propia línea para poder
        // copiarlo entero aunque el ancho lo partiese a la mitad.
        let (before, tail) = notice.split_once('`').unwrap_or((notice, ""));
        let body = if tail.is_empty() {
            Text::from(notice)
        } else {
            Text::from(vec![Line::from(before), Line::from(format!("`{tail}"))])
        };
        let paragraph = Paragraph::new(body)
            .style(Style::new().add_modifier(Modifier::BOLD))
            .wrap(Wrap { trim: true });
        frame.render_widget(paragraph, notice_area);
    }

    let contact = Paragraph::new(Text::from(vec![Line::from(REPO), Line::from(CONTACT)]))
        .style(Style::new().add_modifier(Modifier::DIM))
        .wrap(Wrap { trim: true });
    frame.render_widget(contact, contact_area);
}

/// Restores raw mode and the alternate screen on every exit path — including
/// a `?` return from the event loop (panics are covered by the hook that
/// `ratatui::init` installs).
struct RestoreOnDrop;

impl Drop for RestoreOnDrop {
    fn drop(&mut self) {
        ratatui::restore();
    }
}

/// Runs the menu until the user picks an enabled button, types `q`/Esc
/// (`Exit`) or sends Ctrl-C (`UserAborted`). `view` carries the facts the
/// caller resolved: the header shows the real installed version and the
/// embedder state, never a guess.
pub fn run_menu(view: &MenuView<'_>) -> Result<MenuAction, WizardError> {
    let spec = view.spec;
    let mut selected = first_enabled(spec);
    let mut terminal = ratatui::init();
    let _restore = RestoreOnDrop;
    loop {
        terminal
            .draw(|frame| render_menu(frame, view, selected))
            // Sin terminal usable el wizard aborta tipado (nunca adivina).
            .map_err(|_| WizardError::UserAborted)?;
        if let Event::Key(key) = event::read().map_err(|_| WizardError::UserAborted)? {
            match key.code {
                KeyCode::Up | KeyCode::BackTab | KeyCode::Char('k') => {
                    selected = step(spec, selected, false);
                }
                KeyCode::Down | KeyCode::Tab | KeyCode::Char('j') => {
                    selected = step(spec, selected, true);
                }
                KeyCode::Enter => {
                    if spec.buttons.get(selected).is_some_and(|b| b.enabled) {
                        return choose(spec, selected);
                    }
                }
                KeyCode::Esc | KeyCode::Char('q') => return Ok(MenuAction::Exit),
                KeyCode::Char('c') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                    return Err(WizardError::UserAborted);
                }
                _ => {}
            }
        }
        // Resize/mouse: redraw on the next iteration.
    }
}

fn first_enabled(spec: &MenuSpec) -> usize {
    spec.buttons
        .iter()
        .position(|button| button.enabled)
        .unwrap_or(0)
}

/// Next enabled button from `from`, wrapping; disabled rows are never
/// selectable. Falls back to `from` when nothing is enabled.
fn step(spec: &MenuSpec, from: usize, forward: bool) -> usize {
    let len = spec.buttons.len();
    if len == 0 {
        return 0;
    }
    let mut index = from;
    for _ in 0..len {
        index = if forward {
            (index + 1) % len
        } else {
            (index + len - 1) % len
        };
        if spec.buttons.get(index).is_some_and(|b| b.enabled) {
            return index;
        }
    }
    from
}

/// H11 close: waits for any key. Without a TTY (pipes/CI) it is a silent
/// no-op — a read nobody can answer must never block the exit.
pub fn wait_any_key() {
    if !std::io::stdin().is_terminal() {
        return;
    }
    // Raw mode so a single key closes (cooked mode would need Enter).
    if crossterm::terminal::enable_raw_mode().is_err() {
        return;
    }
    let _ = event::read();
    let _ = crossterm::terminal::disable_raw_mode();
}
