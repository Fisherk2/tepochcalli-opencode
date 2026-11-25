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
use ratatui::layout::{Constraint, Layout};
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span, Text};
use ratatui::widgets::{Gauge, List, ListItem, ListState, Paragraph, Wrap};
use ratatui::Frame;

use crate::domain::{CancelToken, MenuAction, MenuSpec, WizardError};
use crate::ports::{has_active_progress, set_active_progress, MenuView, Progress, ProgressSpec};

/// Contact shown at the bottom of the menu (H5).
const REPO: &str = "https://github.com/Fisherk2/tepochcalli-opencode";
const CONTACT: &str = "dev@fisherk2.com";

/// ratatui 0.30.2 no trae widget `Spinner`: cuatro frames ASCII movidos por el
/// watcher de eventos existente, sin dependencias nuevas.
const SPINNER_FRAMES: [char; 4] = ['|', '/', '-', '\\'];

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

    let header = Paragraph::new(Line::from(super::ui::header_line(view)))
        .style(Style::new().add_modifier(Modifier::BOLD));
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

/// Frames del spinner ASCII: el tick del watcher decide el frame, nunca la
/// barra (que solo refleja hitos completados).
fn spinner_frame(tick: u64) -> char {
    SPINNER_FRAMES[(tick % SPINNER_FRAMES.len() as u64) as usize]
}

/// Porcentaje de hitos completados, acotado a 100. Sin etapas declaradas no
/// se inventa avance.
fn stages_percent(done: usize, total: usize) -> u16 {
    if total == 0 {
        0
    } else {
        done.saturating_mul(100).div_euclid(total).min(100) as u16
    }
}

/// Cronómetro `mm:ss` a partir de una `Duration` inyectada (testeable sin
/// reloj de pared).
fn clock(elapsed: Duration) -> String {
    let secs = elapsed.as_secs();
    format!("{:02}:{:02}", secs / 60, secs % 60)
}

/// Pantalla de progreso por hitos. Pura (no I/O), como `render_menu`: la barra
/// avanza solo con `Progress::advance()`, el spinner va en su propia fila y el
/// cronómetro/ETA se reciben ya calculados. 100 % = trabajo terminado.
pub fn render_stages(
    frame: &mut Frame,
    spec: &ProgressSpec,
    progress: &Progress,
    elapsed: Duration,
    tick: u64,
) {
    let [header_area, gauge_area, spinner_area, detail_area] = Layout::vertical([
        Constraint::Length(1),
        Constraint::Length(3),
        Constraint::Length(1),
        Constraint::Min(3),
    ])
    .areas(frame.area());

    let header = Paragraph::new(Line::from(format!("Tepochcalli · {}", spec.title)))
        .style(Style::new().add_modifier(Modifier::BOLD));
    frame.render_widget(header, header_area);

    let (ratio, label) = if spec.steps == 0 {
        (0.0, "trabajando…".to_string())
    } else {
        let done = progress.done();
        let percent = stages_percent(done, spec.steps);
        (
            f64::from(percent) / 100.0,
            format!("{done}/{} · {percent}%", spec.steps),
        )
    };
    frame.render_widget(
        Gauge::default()
            .ratio(ratio)
            .label(label)
            .style(Style::new().add_modifier(Modifier::BOLD)),
        gauge_area,
    );

    let eta = spec.eta.map_or_else(|| "—".to_string(), clock);
    let spinner = Paragraph::new(Line::from(format!(
        "{}  transcurrido {} · ETA {}",
        spinner_frame(tick),
        clock(elapsed),
        eta
    )));
    frame.render_widget(spinner, spinner_area);

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
    let stage_notice = if spec.steps == 0 {
        "Sin etapas declaradas: la barra no simula avance."
    } else {
        "Progreso por etapas: el 100 % significa trabajo terminado."
    };
    lines.push(Line::from(stage_notice).style(Style::new().add_modifier(Modifier::DIM)));
    lines.push(
        Line::from("Cancelar revierte lo aplicado; si no es reversible, deja el backup nombrado.")
            .style(Style::new().add_modifier(Modifier::DIM)),
    );
    frame.render_widget(
        Paragraph::new(Text::from(lines)).wrap(Wrap { trim: true }),
        detail_area,
    );
}

/// Pantalla de `run_cancellable` (sin hitos declarados): barra fija, spinner
/// vivo y cronómetro; nunca una onda ni un porcentaje fingido.
pub fn render_progress(frame: &mut Frame, title: &str, tick: u64) {
    let spec = ProgressSpec {
        title: title.to_string(),
        steps: 0,
        eta: None,
    };
    render_stages(frame, &spec, &Progress::new(0), Duration::ZERO, tick);
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
    set_active_progress(Some(&progress));
    let start = Instant::now();
    if terminal
        .draw(|frame| render_stages(frame, &spec, &progress, Duration::ZERO, 0))
        .is_err()
    {
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
                        if let Ok(mut terminal) = terminal.lock() {
                            let _ = terminal.draw(|frame| {
                                render_stages(frame, &spec, &progress, start.elapsed(), tick);
                            });
                        }
                    }
                    Err(_) => return,
                }
            }
        })
    };
    work(&progress);
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
