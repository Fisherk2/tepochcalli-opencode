//! H5 menu, full-screen (ratatui 0.30 + crossterm 0.29): real buttons with a
//! visible disabled state and the reason next to every blocked action.
//!
//! [`render_menu`] is pure (no I/O, no file reads) so tests can drive it with
//! `TestBackend`; [`run_menu`] owns the terminal and restores it on every
//! exit path.

use std::io::IsTerminal;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use crossterm::event::{self, Event, KeyCode, KeyModifiers};
use ratatui::layout::{Constraint, Layout};
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span, Text};
use ratatui::widgets::{Gauge, List, ListItem, ListState, Paragraph, Wrap};
use ratatui::Frame;

use crate::domain::{CancelToken, MenuAction, MenuSpec, WizardError};
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

    let header =
        Paragraph::new(Line::from(view.header())).style(Style::new().add_modifier(Modifier::BOLD));
    frame.render_widget(header, header_area);

    let list = List::new(menu_items(spec))
        .highlight_symbol("› ")
        .highlight_style(Style::new().add_modifier(Modifier::REVERSED));
    let mut state = ListState::default().with_selected(Some(selected));
    frame.render_stateful_widget(list, list_area, &mut state);

    if let Some(notice) = spec.notice {
        let paragraph = Paragraph::new(notice_text(notice))
            .style(Style::new().add_modifier(Modifier::BOLD))
            .wrap(Wrap { trim: true });
        frame.render_widget(paragraph, notice_area);
    }

    let contact = Paragraph::new(Text::from(vec![Line::from(REPO), Line::from(CONTACT)]))
        .style(Style::new().add_modifier(Modifier::DIM))
        .wrap(Wrap { trim: true });
    frame.render_widget(contact, contact_area);
}

/// One row per button: icon, label, and the visible reason when disabled.
fn menu_items(spec: &MenuSpec) -> Vec<ListItem<'_>> {
    spec.buttons
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
        .collect()
}

fn notice_text(notice: &str) -> Text<'_> {
    // El comando entre backticks va en su propia línea para poder
    // copiarlo entero aunque el ancho lo partiese a la mitad.
    let (before, tail) = notice.split_once('`').unwrap_or((notice, ""));
    if tail.is_empty() {
        Text::from(notice)
    } else {
        Text::from(vec![Line::from(before), Line::from(format!("`{tail}"))])
    }
}

/// R-offline-2: the download screen. Pure (no I/O) like `render_menu`: only
/// the Cancel row is enabled; the five menu actions stay visible, dimmed and
/// with the reason, so a blocked action is never hidden (H5 rule).
///
/// The operation reports no bytes, so the bar is INDETERMINATE: `tick` only
/// moves a triangle and the screen says so. Never a fake percentage.
pub fn render_progress(frame: &mut Frame, title: &str, tick: u64) {
    let [header_area, gauge_area, detail_area] = Layout::vertical([
        Constraint::Length(1),
        Constraint::Length(3),
        Constraint::Min(3),
    ])
    .areas(frame.area());

    let header = Paragraph::new(Line::from(format!("Tepochcalli · {title}")))
        .style(Style::new().add_modifier(Modifier::BOLD));
    frame.render_widget(header, header_area);

    let gauge = Gauge::default()
        .ratio(indeterminate_ratio(tick))
        .label("trabajando…")
        .style(Style::new().add_modifier(Modifier::BOLD));
    frame.render_widget(gauge, gauge_area);

    let mut lines = vec![Line::from("⏹ Cancelar — Esc / Ctrl+C")
        .style(Style::new().add_modifier(Modifier::BOLD | Modifier::REVERSED))];
    for action in MenuAction::ALL {
        lines.push(
            Line::from(format!(
                "{} {}  — operación en curso",
                action.icon(),
                action.label()
            ))
            .style(Style::new().add_modifier(Modifier::DIM)),
        );
    }
    lines.push(
        Line::from("Progreso indeterminado: la operación no reporta bytes.")
            .style(Style::new().add_modifier(Modifier::DIM)),
    );
    lines.push(
        Line::from("Cancelar revierte lo aplicado; si no es reversible, deja el backup nombrado.")
            .style(Style::new().add_modifier(Modifier::DIM)),
    );
    frame.render_widget(
        Paragraph::new(Text::from(lines)).wrap(Wrap { trim: true }),
        detail_area,
    );
}

/// 0 → 1 → 0 over 40 ticks: the bar pulses without claiming progress it has
/// no way to know. Tick 20 is the full-bar phase.
fn indeterminate_ratio(tick: u64) -> f64 {
    let phase = (tick % 40) as f64;
    if phase < 20.0 {
        phase / 20.0
    } else {
        (40.0 - phase) / 20.0
    }
}

/// Esc or Ctrl+C cancel the download; any other key keeps waiting.
pub fn is_cancel_key(code: KeyCode, modifiers: KeyModifiers) -> bool {
    code == KeyCode::Esc
        || (code == KeyCode::Char('c') && modifiers.contains(KeyModifiers::CONTROL))
}

/// R-offline-2: draws the Cancel screen, runs `work` while a watcher thread
/// fires `cancel` on Esc/Ctrl+C and redraws the indeterminate bar every
/// 100 ms, then leaves the final frame (cancel notice, or the full bar). Any
/// terminal failure degrades to plain `work()`: a broken screen must never
/// break the operation.
pub fn run_progress(title: &str, cancel: &CancelToken, work: &mut dyn FnMut()) {
    // `try_init` (no `init`): el doc de esta función promete degradar ante
    // CUALQUIER fallo de terminal, y `init` paniquea (`expect`). `try_init`
    // instala el mismo panic hook antes de intentar (ratatui 0.30.2, init.rs).
    let mut terminal = match ratatui::try_init() {
        Ok(terminal) => terminal,
        Err(_) => {
            // El contrato de este doc: cualquier fallo de terminal degrada a
            // `work()` — nunca rompe la operación. `restore()` es idempotente
            // y cubre el caso de init a mitad (raw mode aplicado, alt screen no).
            ratatui::restore();
            work();
            return;
        }
    };
    // `_restore` solo tras un init exitoso: el brazo `Err` de arriba ya
    // restauró a mano y duplicarlo ahí sería inofensivo pero sucio.
    let _restore = RestoreOnDrop;
    if terminal
        .draw(|frame| render_progress(frame, title, 0))
        .is_err()
    {
        work();
        return;
    }
    // El receptor se comparte: el watcher anima y el hilo principal deja el
    // frame final después del join (nunca dos dibujos a la vez).
    let terminal = Arc::new(Mutex::new(terminal));
    let done = Arc::new(AtomicBool::new(false));
    let watcher = {
        let done = Arc::clone(&done);
        let cancel = cancel.clone();
        let terminal = Arc::clone(&terminal);
        let title = title.to_string();
        std::thread::spawn(move || {
            let mut tick = 0u64;
            while !done.load(Ordering::SeqCst) {
                match event::poll(Duration::from_millis(100)) {
                    Ok(true) => {
                        if let Ok(Event::Key(key)) = event::read() {
                            if is_cancel_key(key.code, key.modifiers) {
                                cancel.cancel();
                                return;
                            }
                        }
                    }
                    Ok(false) => {
                        tick += 1;
                        // Lock envenenado: la pantalla es decorativa, se
                        // ignora en vez de paniquear.
                        if let Ok(mut terminal) = terminal.lock() {
                            let _ = terminal.draw(|frame| render_progress(frame, &title, tick));
                        }
                    }
                    // Sin terminal legible no hay tecla que esperar: el
                    // watcher se retira y `work` sigue su curso.
                    Err(_) => return,
                }
            }
        })
    };
    work();
    done.store(true, Ordering::SeqCst);
    // El poll es de 100 ms: la espera está acotada, no hay join eterno.
    let _ = watcher.join();
    if let Ok(mut terminal) = terminal.lock() {
        if cancel.is_cancelled() {
            let _ = terminal.draw(|frame| {
                frame.render_widget(
                    Paragraph::new(Line::from("Cancelado — deshaciendo los cambios aplicados…"))
                        .style(Style::new().add_modifier(Modifier::BOLD)),
                    frame.area(),
                );
            });
        } else {
            // tick 20 es la fase de ratio 1.0 del triángulo: barra llena.
            let _ = terminal.draw(|frame| render_progress(frame, title, 20));
        }
    };
}

/// Restores raw mode and the alternate screen on every exit path — including
/// a `?` return from the event loop (panics are covered by the hook that
/// `ratatui::init`/`try_init` installs).
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
