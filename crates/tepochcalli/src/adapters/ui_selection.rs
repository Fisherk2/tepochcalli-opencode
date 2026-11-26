//! Costura del diálogo bajo el watcher: traduce teclas de crossterm al
//! puerto y pinta la zona central del frame. Módulo privado de `adapters`:
//! no añade interfaz pública ni dependencias; `ui_ratatui` reexporta los
//! renderizados que ya tenía y el test de propiedad usa esa misma costura.

use std::time::Duration;

use crossterm::event::{KeyCode, KeyModifiers};
use ratatui::layout::{Constraint, Layout};
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Text};
use ratatui::widgets::{Gauge, Paragraph, Wrap};
use ratatui::Frame;

use crate::domain::MenuAction;
use crate::ports::{Dialog, DialogKey, Progress, ProgressSpec};

use super::ui_ratatui::is_cancel_key;

/// ratatui 0.30.2 no trae widget `Spinner`: cuatro frames ASCII movidos por el
/// watcher de eventos existente, sin dependencias nuevas.
const SPINNER_FRAMES: [char; 4] = ['|', '/', '-', '\\'];

/// crossterm → tecla del puerto. Esc/Ctrl+C pasan por `is_cancel_key`, así
/// que la cancelación sigue siendo la misma que la de la barra exterior.
#[must_use]
pub(crate) fn dialog_key(code: KeyCode, modifiers: KeyModifiers) -> Option<DialogKey> {
    if is_cancel_key(code, modifiers) {
        return Some(DialogKey::Cancel);
    }
    match code {
        KeyCode::Up | KeyCode::BackTab | KeyCode::Char('k') => Some(DialogKey::Previous),
        KeyCode::Down | KeyCode::Tab | KeyCode::Char('j') => Some(DialogKey::Next),
        KeyCode::Enter => Some(DialogKey::Confirm),
        KeyCode::Backspace => Some(DialogKey::Backspace),
        KeyCode::Char(ch) => Some(DialogKey::Char(ch)),
        _ => None,
    }
}

/// Líneas de la zona central mientras hay un diálogo pendiente: la fila
/// Cancelar sigue visible y resaltada, como en la pantalla de hitos.
#[must_use]
pub(crate) fn dialog_lines(dialog: &Dialog) -> Vec<Line<'_>> {
    let cancel = Line::from("⏹ Cancelar — Esc / Ctrl+C")
        .style(Style::new().add_modifier(Modifier::BOLD | Modifier::REVERSED));
    let bold = Style::new().add_modifier(Modifier::BOLD);
    match dialog {
        Dialog::Select {
            prompt,
            options,
            cursor,
        } => {
            let mut lines = vec![cancel, Line::from(prompt.clone()).style(bold)];
            for (index, option) in options.iter().enumerate() {
                let (marker, style) = if index == *cursor {
                    ("› ", Style::new().add_modifier(Modifier::REVERSED))
                } else {
                    ("  ", Style::new())
                };
                lines.push(Line::from(format!("{marker}{option}")).style(style));
            }
            lines
        }
        Dialog::Input {
            prompt,
            value,
            secret,
        } => {
            // Un secreto nunca se hace eco: solo se indica que hay contenido.
            let shown = if *secret && !value.is_empty() {
                "<oculto>".to_string()
            } else {
                value.clone()
            };
            vec![
                cancel,
                Line::from(prompt.clone()).style(bold),
                Line::from(format!("> {shown}")),
            ]
        }
        Dialog::Notice { title, body } => {
            vec![
                Line::from(title.clone()).style(bold),
                Line::from(body.clone()),
            ]
        }
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
    render_stages_with_dialog(frame, spec, progress, elapsed, tick, None);
}

/// Variante con el diálogo del watcher en la zona central: es el único
/// pintor cuando F6 cede la pantalla al frame de hitos.
pub fn render_stages_with_dialog(
    frame: &mut Frame,
    spec: &ProgressSpec,
    progress: &Progress,
    elapsed: Duration,
    tick: u64,
    dialog: Option<&Dialog>,
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

    let lines = if let Some(dialog) = dialog {
        dialog_lines(dialog)
    } else {
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
            Line::from(
                "Cancelar revierte lo aplicado; si no es reversible, deja el backup nombrado.",
            )
            .style(Style::new().add_modifier(Modifier::DIM)),
        );
        lines
    };
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
