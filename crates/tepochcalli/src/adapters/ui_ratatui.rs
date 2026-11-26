//! H5 menu, full-screen (ratatui 0.30 + crossterm 0.29): real buttons with a
//! visible disabled state and the reason next to every blocked action.
//!
//! [`render_menu`] is pure (no I/O, no file reads) so tests can drive it with
//! `TestBackend`; [`run_menu`] owns the terminal and restores it on every
//! exit path.

use std::io::IsTerminal;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use crossterm::event::{self, Event, KeyCode, KeyModifiers};
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span, Text};
use ratatui::widgets::{Paragraph, Wrap};
use ratatui::Frame;

use crate::domain::{CancelToken, MenuAction, MenuSpec, WizardError};
use crate::ports::{
    has_active_progress, set_active_dialog, set_active_progress, DialogHandle, MenuView, Progress,
    ProgressSpec,
};

use super::ui_selection::{bottom_areas, dialog_key, fit_header, render_contact, render_h5, zones};
// Reexporta los nombres que ya ofrecía este módulo: el render del frame vive
// en `ui_selection`, pero callers y tests siguen cruzando el mismo seam.
pub use super::ui_selection::{render_progress, render_stages, render_stages_with_dialog};

/// Maps a chosen button index to its action. A disabled or out-of-range
/// index is a typed abort: the wizard never invents a selection.
pub fn choose(spec: &MenuSpec, index: usize) -> Result<MenuAction, WizardError> {
    match spec.buttons.get(index) {
        Some(button) if button.enabled => Ok(button.action),
        _ => Err(WizardError::UserAborted),
    }
}

/// Draws the whole menu into `frame` with the shared three-zone layout:
/// banner arriba, avisos en el centro y H5 + contacto abajo. Every fact comes
/// resolved in `view` (this function never touches the disk).
pub fn render_menu(frame: &mut Frame, view: &MenuView<'_>, selected: usize) {
    let spec = view.spec;
    let [top, center, bottom] = zones(frame.area(), 1, 7);

    let header = Paragraph::new(Line::from(fit_header(
        &super::ui::header_line(view),
        top.width,
    )))
    .style(Style::new().add_modifier(Modifier::BOLD))
    .wrap(Wrap { trim: true });
    frame.render_widget(header, top);

    if let Some(notice) = spec.notice {
        let paragraph = Paragraph::new(notice_text(notice))
            .style(Style::new().add_modifier(Modifier::BOLD))
            .wrap(Wrap { trim: true });
        frame.render_widget(paragraph, center);
    }

    let (rows_area, contact_area) = bottom_areas(bottom);
    let labels: Vec<&str> = spec
        .buttons
        .iter()
        .map(|button| button.action.label())
        .collect();
    render_h5(frame, rows_area, menu_items(spec), &labels, Some(selected));
    if let Some(contact_area) = contact_area {
        render_contact(frame, contact_area);
    }
}

/// One row per button: icon, label, and the visible reason when disabled.
fn menu_items(spec: &MenuSpec) -> Vec<Line<'_>> {
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
            line.style(style)
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

/// Esc or Ctrl+C cancel the download; any other key keeps waiting.
pub fn is_cancel_key(code: KeyCode, modifiers: KeyModifiers) -> bool {
    code == KeyCode::Esc
        || (code == KeyCode::Char('c') && modifiers.contains(KeyModifiers::CONTROL))
}

/// R-offline-2: pantalla de Cancelar + watcher (100 ms); cualquier fallo de
/// terminal degrada a `work()` — una pantalla rota nunca rompe la operación.
pub fn run_progress(title: &str, cancel: &CancelToken, work: &mut dyn FnMut()) {
    // shortcut: con la barra exterior activa el watcher de `run_stages` ya
    // posee cancelación y frame final; un segundo `try_init` sacaría la
    // pantalla exterior de la alternate screen. TestBackend no lo observa.
    if has_active_progress() {
        work();
        return;
    }
    // `try_init` (no `init`): degrada ante cualquier fallo; `init` paniquea
    // (ratatui 0.30.2, init.rs).
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
    // `_restore` solo tras init exitoso: el brazo `Err` ya restauró a mano.
    let _restore = RestoreOnDrop;
    if terminal
        .draw(|frame| render_progress(frame, title, 0))
        .is_err()
    {
        work();
        return;
    }
    // El receptor se comparte: el watcher mueve el spinner y el hilo principal
    // deja el frame final después del join (nunca dos dibujos a la vez).
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
                        // Lock envenenado: pantalla decorativa, se ignora.
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
                    Paragraph::new(Line::from(
                        "Cancelación no disponible en esta fase — la operación continúa",
                    ))
                    .style(Style::new().add_modifier(Modifier::BOLD)),
                    frame.area(),
                );
            });
        } else {
            // Sin hitos no hay 100 % que fingir: se redibuja la última posición.
            let _ = terminal.draw(|frame| render_progress(frame, title, 0));
        }
    };
}

/// Progreso por hitos: misma pantalla y mismo watcher que `run_progress`, con
/// la barra alimentada por los `advance()` que `work` haga sobre [`Progress`].
/// El cronómetro nace aquí (`Instant::now()`); la ETA es solo la declarada en
/// `spec`. Ante cancelación el frame final es el panel de rollback, nunca un
/// 100 % falso. Cualquier fallo de terminal degrada a `work` en línea.
pub fn run_stages(spec: &ProgressSpec, cancel: &CancelToken, work: &mut dyn FnMut(&Progress)) {
    let mut terminal = match ratatui::try_init() {
        Ok(terminal) => terminal,
        Err(_) => {
            ratatui::restore();
            work(&Progress::new(spec.steps));
            return;
        }
    };
    let _restore = RestoreOnDrop;
    let spec = spec.clone();
    let progress = Progress::new(spec.steps);
    let dialog = Arc::new(DialogHandle::default());
    set_active_progress(Some(&progress));
    set_active_dialog(Some(&dialog));
    let start = Instant::now();
    if terminal
        .draw(|frame| render_stages(frame, &spec, &progress, Duration::ZERO, 0))
        .is_err()
    {
        dialog.clear();
        set_active_dialog(None);
        set_active_progress(None);
        work(&progress);
        return;
    }
    let terminal = Arc::new(Mutex::new(terminal));
    let done = Arc::new(AtomicBool::new(false));
    let watcher = {
        let done = Arc::clone(&done);
        let cancel = cancel.clone();
        let terminal = Arc::clone(&terminal);
        let spec = spec.clone();
        let progress = progress.clone();
        let dialog = Arc::clone(&dialog);
        std::thread::spawn(move || {
            // Cubre también los `return` anticipados: ninguna pregunta queda
            // esperando una respuesta que el watcher ya no va a escribir.
            let _clear_dialog = ClearDialogOnDrop(Arc::clone(&dialog));
            let mut tick = 0u64;
            while !done.load(Ordering::SeqCst) {
                match event::poll(Duration::from_millis(100)) {
                    Ok(true) => {
                        if let Ok(Event::Key(key)) = event::read() {
                            // El watcher es el único lector: traduce la tecla
                            // al diálogo en curso antes de mirar cancelación.
                            if dialog_key(key.code, key.modifiers)
                                .is_some_and(|key| dialog.handle(key, &cancel))
                            {
                                tick += 1;
                                let view = dialog.snapshot();
                                if let Ok(mut terminal) = terminal.lock() {
                                    let _ = terminal.draw(|frame| {
                                        render_stages_with_dialog(
                                            frame,
                                            &spec,
                                            &progress,
                                            start.elapsed(),
                                            tick,
                                            view.as_ref(),
                                        );
                                    });
                                }
                                continue;
                            }
                            if is_cancel_key(key.code, key.modifiers) {
                                cancel.cancel();
                                return;
                            }
                        }
                    }
                    Ok(false) => {
                        tick += 1;
                        let view = dialog.snapshot();
                        if let Ok(mut terminal) = terminal.lock() {
                            let _ = terminal.draw(|frame| {
                                render_stages_with_dialog(
                                    frame,
                                    &spec,
                                    &progress,
                                    start.elapsed(),
                                    tick,
                                    view.as_ref(),
                                );
                            });
                        }
                    }
                    Err(_) => return,
                }
            }
        })
    };
    work(&progress);
    dialog.clear();
    set_active_dialog(None);
    set_active_progress(None);
    done.store(true, Ordering::SeqCst);
    let _ = watcher.join();
    if let Ok(mut terminal) = terminal.lock() {
        if cancel.is_cancelled() {
            let _ = terminal.draw(|frame| {
                frame.render_widget(
                    Paragraph::new(Line::from(
                        "Cancelación registrada — se aplica el rollback (backup nombrado)",
                    ))
                    .style(Style::new().add_modifier(Modifier::BOLD)),
                    frame.area(),
                );
            });
        } else {
            let elapsed = start.elapsed();
            let _ = terminal.draw(|frame| render_stages(frame, &spec, &progress, elapsed, 0));
        }
    };
}

/// Resuelve como aborto cualquier diálogo pendiente cuando el watcher sale,
/// incluso por un `return` anticipado (mitigación del deadlock del handshake).
struct ClearDialogOnDrop(Arc<DialogHandle>);

impl Drop for ClearDialogOnDrop {
    fn drop(&mut self) {
        self.0.clear();
    }
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
    // `try_init` (como en `run_progress`): `init` paniquea; `restore()` es
    // idempotente y cubre el init a medias.
    let mut terminal = match ratatui::try_init() {
        Ok(terminal) => terminal,
        Err(_) => {
            ratatui::restore();
            return Err(WizardError::UserAborted);
        }
    };
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
