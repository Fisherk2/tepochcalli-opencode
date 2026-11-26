//! Costura del diálogo bajo el watcher: traduce teclas de crossterm al
//! puerto y pinta el frame en tres zonas (ARRIBA/CENTRO/ABAJO). Módulo privado
//! de `adapters`: `ui_ratatui` reexporta los renderizados y comparte estas
//! costuras de layout, sin añadir interfaz pública ni dependencias.

use std::time::Duration;

use crossterm::event::{KeyCode, KeyModifiers};
use ratatui::layout::{Constraint, Layout, Rect};
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Text};
use ratatui::widgets::{Gauge, List, ListState, Paragraph, Wrap};
use ratatui::Frame;

use crate::domain::MenuAction;
use crate::ports::{Dialog, DialogKey, Progress, ProgressSpec};

use super::ui_ratatui::is_cancel_key;

/// ratatui 0.30.2 no trae widget `Spinner`: cuatro frames ASCII movidos por el
/// watcher de eventos existente, sin dependencias nuevas.
const SPINNER_FRAMES: [char; 4] = ['|', '/', '-', '\\'];

/// Contacto compartido por el menú y la pantalla de hitos (zona ABAJO).
pub(crate) const REPO: &str = "https://github.com/Fisherk2/tepochcalli-opencode";
pub(crate) const CONTACT: &str = "dev@fisherk2.com";

/// crossterm → tecla del puerto. Esc/Ctrl+C pasan por `is_cancel_key`, así
/// que la cancelación sigue siendo la misma que la de la barra exterior.
/// `dialog` es el diálogo en curso: solo una selección interpreta k/j como
/// navegación; en texto son caracteres.
#[must_use]
pub fn dialog_key(
    code: KeyCode,
    modifiers: KeyModifiers,
    dialog: Option<&Dialog>,
) -> Option<DialogKey> {
    if is_cancel_key(code, modifiers) {
        return Some(DialogKey::Cancel);
    }
    let navigation = matches!(dialog, Some(Dialog::Select { .. }));
    match code {
        KeyCode::Up | KeyCode::BackTab => Some(DialogKey::Previous),
        KeyCode::Down | KeyCode::Tab => Some(DialogKey::Next),
        KeyCode::Char('k') if navigation => Some(DialogKey::Previous),
        KeyCode::Char('j') if navigation => Some(DialogKey::Next),
        KeyCode::Enter => Some(DialogKey::Confirm),
        KeyCode::Backspace => Some(DialogKey::Backspace),
        KeyCode::Char(ch) => Some(DialogKey::Char(ch)),
        _ => None,
    }
}

/// Líneas de la zona central mientras hay un diálogo pendiente: la fila
/// Cancelar sigue visible y resaltada, también en los avisos.
#[must_use]
pub(crate) fn dialog_lines(dialog: &Dialog) -> Vec<Line<'_>> {
    let cancel = cancel_line();
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
            lines.push(help_line());
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
                help_line(),
            ]
        }
        Dialog::Notice { title, body } => vec![
            cancel,
            Line::from(title.clone()).style(bold),
            Line::from(body.clone()),
            help_line(),
        ],
    }
}

fn cancel_line() -> Line<'static> {
    Line::from("⏹ Cancelar — Esc / Ctrl+C")
        .style(Style::new().add_modifier(Modifier::BOLD | Modifier::REVERSED))
}

/// Leyenda compartida por menú y diálogos: sin ella el frame no enseña qué
/// tecla mueve, confirma o sale.
#[must_use]
pub(crate) fn help_line() -> Line<'static> {
    Line::from("↑/↓/k/j/Tab = mover · Enter = elegir · Esc = salir")
        .style(Style::new().add_modifier(Modifier::DIM))
}

/// Tres bandas compartidas: ARRIBA (`top_rows` fijas), CENTRO (`Min(1)`) y
/// ABAJO (`bottom` fijas). Las cotas se recortan antes de repartir para que el
/// centro nunca desaparezca en terminales de 6 u 8 filas.
#[must_use]
pub(crate) fn zones(area: Rect, top_rows: u16, bottom_wanted: u16) -> [Rect; 3] {
    let top = top_rows.min(area.height.saturating_sub(2));
    let bottom = bottom_wanted.min(area.height.saturating_sub(top + 1));
    Layout::vertical([
        Constraint::Length(top),
        Constraint::Min(1),
        Constraint::Length(bottom),
    ])
    .areas(area)
}

/// Separa las filas del H5 del contacto solo cuando caben las siete filas.
#[must_use]
pub(crate) fn bottom_areas(area: Rect) -> (Rect, Option<Rect>) {
    if area.height >= 7 {
        let [rows, contact] =
            Layout::vertical([Constraint::Length(area.height - 2), Constraint::Length(2)])
                .areas(area);
        (rows, Some(contact))
    } else {
        (area, None)
    }
}

/// H5 compacto para terminales donde no caben cinco filas: las etiquetas se
/// reparten entre las filas disponibles con `Wrap`, sin perder ninguna. Sin
/// `ListState` el foco se marca a mano y el grupo DIM se anuncia con `off:`.
#[must_use]
pub(crate) fn compact_labels(
    rows: &[Line<'_>],
    labels: &[&str],
    selected: Option<usize>,
) -> String {
    let mut parts: Vec<String> = Vec::new();
    if rows
        .iter()
        .any(|row| row.style.add_modifier.contains(Modifier::DIM))
    {
        // Un solo `off:` para el grupo: un sufijo por fila no cabe en las
        // tres filas de la pantalla de hitos a 20x6 y desplazaba `Exit`.
        parts.push("off:".to_string());
    }
    for (index, label) in labels.iter().enumerate() {
        parts.push(if Some(index) == selected {
            // Sin `ListState` el foco solo puede delatarse en la etiqueta.
            format!("› {label}")
        } else {
            (*label).to_string()
        });
    }
    parts.join(" ")
}

/// Header de una sola fila con elipsis cuando no cabe entero.
#[must_use]
pub(crate) fn fit_header(text: &str, width: u16) -> String {
    let limit = usize::from(width);
    if text.chars().count() <= limit {
        return text.to_string();
    }
    if limit == 0 {
        return String::new();
    }
    format!("{}…", text.chars().take(limit - 1).collect::<String>())
}

/// Contacto de la franja inferior, con el mismo estilo en ambas pantallas.
pub(crate) fn render_contact(frame: &mut Frame, area: Rect) {
    // En 40 columnas la URL completa ocuparía dos filas y empujaría el email
    // fuera de la franja: se acorta el esquema, no el dominio ni el contacto.
    let repo = if area.width < 48 {
        "github.com/Fisherk2/tepochcalli-opencode"
    } else {
        REPO
    };
    frame.render_widget(
        Paragraph::new(Text::from(vec![Line::from(repo), Line::from(CONTACT)]))
            .style(Style::new().add_modifier(Modifier::DIM))
            .wrap(Wrap { trim: true }),
        area,
    );
}

/// Filas del H5 en la franja inferior: lista completa si hay sitio, texto
/// envuelto si la terminal es demasiado baja.
pub(crate) fn render_h5<'a>(
    frame: &mut Frame,
    area: Rect,
    rows: Vec<Line<'a>>,
    labels: &[&str],
    selected: Option<usize>,
) {
    if area.height < 5 {
        frame.render_widget(
            Paragraph::new(compact_labels(&rows, labels, selected)).wrap(Wrap { trim: true }),
            area,
        );
        return;
    }
    let list = List::new(rows)
        .highlight_symbol("› ")
        .highlight_style(Style::new().add_modifier(Modifier::REVERSED));
    let mut state = ListState::default().with_selected(selected);
    frame.render_stateful_widget(list, area, &mut state);
}

/// Cronómetro a la izquierda y ETA en la columna derecha: dos widgets en un
/// `Layout::horizontal`, nunca interpolados en el mismo `format!`.
pub(crate) fn render_status(frame: &mut Frame, area: Rect, left: String, eta: String) {
    let eta_width =
        u16::try_from(eta.chars().count().min(usize::from(area.width))).unwrap_or(area.width);
    let [left_area, right_area] =
        Layout::horizontal([Constraint::Min(1), Constraint::Length(eta_width)]).areas(area);
    frame.render_widget(
        Paragraph::new(Line::from(left)).wrap(Wrap { trim: true }),
        left_area,
    );
    frame.render_widget(
        Paragraph::new(Line::from(eta)).wrap(Wrap { trim: true }),
        right_area,
    );
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
/// avanza solo con `Progress::advance()`, el spinner y la ETA se reparten la
/// fila de estado en columnas y el cronómetro se recibe ya calculado.
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
    let area = frame.area();
    let tiny = area.height < 8;
    let gauge_height = if area.height >= 14 { 3 } else { 1 };
    let [top, center, bottom] = zones(area, if tiny { 2 } else { gauge_height + 2 }, 7);

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
    let header = Paragraph::new(Line::from(fit_header(
        &format!("Tepochcalli · {}", spec.title),
        top.width,
    )))
    .style(Style::new().add_modifier(Modifier::BOLD))
    .wrap(Wrap { trim: true });
    let gauge = Gauge::default()
        .ratio(ratio)
        .label(label)
        .style(Style::new().add_modifier(Modifier::BOLD));

    let eta = spec
        .eta
        .map_or_else(|| "ETA —".to_string(), |d| format!("ETA {}", clock(d)));
    let short_status = top.width < 24;
    let left = if short_status {
        format!(
            "{} {} {}",
            spinner_frame(tick),
            if spec.steps == 0 {
                "…".to_string()
            } else {
                format!("{}/{}", progress.done(), spec.steps)
            },
            clock(elapsed)
        )
    } else {
        format!("{}  transcurrido {}", spinner_frame(tick), clock(elapsed))
    };
    if tiny {
        let [header_area, status_area] =
            Layout::vertical([Constraint::Length(1), Constraint::Length(1)]).areas(top);
        frame.render_widget(header, header_area);
        render_status(frame, status_area, left, eta);
    } else {
        let [header_area, gauge_area, status_area] = Layout::vertical([
            Constraint::Length(1),
            Constraint::Length(gauge_height),
            Constraint::Length(1),
        ])
        .areas(top);
        frame.render_widget(header, header_area);
        frame.render_widget(gauge, gauge_area);
        render_status(frame, status_area, left, eta);
    }

    let lines = if let Some(dialog) = dialog {
        dialog_lines(dialog)
    } else {
        let mut lines = vec![cancel_line()];
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
        lines.push(help_line());
        lines
    };
    frame.render_widget(
        Paragraph::new(Text::from(lines)).wrap(Wrap { trim: true }),
        center,
    );

    let (rows_area, contact_area) = bottom_areas(bottom);
    let labels: Vec<&str> = MenuAction::ALL
        .iter()
        .map(|action| action.label())
        .collect();
    let blocked: Vec<Line<'_>> = MenuAction::ALL
        .iter()
        .map(|action| {
            Line::from(format!(
                "{} {}  — operación en curso",
                action.icon(),
                action.label()
            ))
            .style(Style::new().add_modifier(Modifier::DIM))
        })
        .collect();
    render_h5(frame, rows_area, blocked, &labels, None);
    if let Some(contact_area) = contact_area {
        render_contact(frame, contact_area);
    }
}

/// Pantalla de `run_cancellable` (sin hitos declarados): barra fija, spinner
/// vivo y cronómetro; nunca una onda ni un porcentaje fingido. Sin ETA
/// declarada no se inventa un tiempo.
pub fn render_progress(frame: &mut Frame, title: &str, tick: u64) {
    let spec = ProgressSpec {
        title: title.to_string(),
        steps: 0,
        eta: None,
    };
    render_stages(frame, &spec, &Progress::new(0), Duration::ZERO, tick);
}
