//! R-offline-2 progress screen (T16, sin onda desde T20): the pure
//! `render_progress` drawn into a `TestBackend` (Cancelar enabled, the five
//! menu rows blocked with a visible reason, the no-destruction notice), the
//! key classifier, the inline default the headless UI inherits (no screen, no
//! token fired) and the same inline fallback behind `TtyUi`'s no-TTY guard.

mod common;

use std::cell::Cell;
use std::io::IsTerminal;

use crossterm::event::{KeyCode, KeyModifiers};
use ratatui::backend::TestBackend;
use ratatui::buffer::Buffer;
use ratatui::style::Modifier;
use ratatui::Terminal;

use common::helpers::buffer_text;
use tepochcalli::adapters::ui_ratatui::{is_cancel_key, render_progress};
use tepochcalli::adapters::{HeadlessUi, TtyUi};
use tepochcalli::domain::CancelToken;
use tepochcalli::ports::Ui;

fn draw_at(width: u16, height: u16, tick: u64) -> Buffer {
    let mut terminal =
        Terminal::new(TestBackend::new(width, height)).expect("in-memory test backend");
    terminal
        .draw(|frame| render_progress(frame, "Descargando modelo de embeddings", tick))
        .expect("draw into the test buffer");
    terminal.backend().buffer().clone()
}

fn draw(width: u16, height: u16) -> Buffer {
    draw_at(width, height, 0)
}

#[test]
fn progress_shows_the_title_and_the_enabled_cancel_row() {
    let text = buffer_text(&draw(80, 24));
    assert!(
        text.contains("Tepochcalli · Descargando modelo de embeddings"),
        "header must carry the title:\n{text}"
    );
    assert!(
        text.contains("Cancelar") && text.contains("Esc / Ctrl+C"),
        "the enabled cancel row states both triggers:\n{text}"
    );
}

#[test]
fn ui_progress_bloquea_las_acciones_y_no_finge_porcentaje() {
    let text = buffer_text(&draw(80, 24));
    for label in ["Install", "Update", "Change Embedder", "Desinstall", "Exit"] {
        assert!(text.contains(label), "missing blocked row {label}:\n{text}");
    }
    assert_eq!(
        text.matches("operación en curso").count(),
        5,
        "each of the five actions needs its visible reason:\n{text}"
    );
    assert!(
        text.contains("Cancelar revierte lo aplicado"),
        "the no-destruction notice must be visible:\n{text}"
    );
    assert!(
        text.contains("Sin etapas declaradas: la barra no simula avance."),
        "sin hitos declarados no se finge un porcentaje:\n{text}"
    );
    assert!(
        text.contains("trabajando…"),
        "la barra queda fija hasta que el llamador declara etapas:\n{text}"
    );
}

#[test]
fn ui_progress_el_spinner_se_mueve_entre_ticks_sin_mover_la_barra() {
    let start = buffer_text(&draw_at(80, 24, 0));
    let next = buffer_text(&draw_at(80, 24, 1));
    assert_ne!(start, next, "el spinner ASCII debe moverse con el tick");
    for text in [&start, &next] {
        assert!(
            text.contains("trabajando…"),
            "la barra no debe fingir avance:\n{text}"
        );
    }
}

#[test]
fn blocked_rows_are_dimmed_in_the_buffer() {
    let buffer = draw(80, 24);
    let area = buffer.area();
    let mut checked = 0;
    for y in area.top()..area.bottom() {
        let row: String = (area.left()..area.right())
            .filter_map(|x| buffer.cell((x, y)).and_then(|c| c.symbol().chars().next()))
            .collect();
        if row.contains("operación en curso") {
            let dim = (area.left()..area.right()).any(|x| {
                buffer
                    .cell((x, y))
                    .is_some_and(|cell| cell.modifier.contains(Modifier::DIM))
            });
            assert!(dim, "blocked row must be attenuated: {row:?}");
            checked += 1;
        }
    }
    assert_eq!(checked, 5, "the five blocked rows must be dimmed");
}

#[test]
fn cancel_keys_are_esc_and_ctrl_c_only() {
    assert!(is_cancel_key(KeyCode::Esc, KeyModifiers::NONE));
    assert!(is_cancel_key(KeyCode::Char('c'), KeyModifiers::CONTROL));
    assert!(
        !is_cancel_key(KeyCode::Char('c'), KeyModifiers::NONE),
        "a bare `c` types, it does not cancel"
    );
    assert!(!is_cancel_key(KeyCode::Char('q'), KeyModifiers::NONE));
    assert!(!is_cancel_key(KeyCode::Enter, KeyModifiers::NONE));
}

#[test]
fn headless_ui_runs_work_inline_without_touching_the_token() {
    let ui = HeadlessUi::default();
    let cancel = CancelToken::new();
    let ran = Cell::new(false);
    ui.run_cancellable("Descargando", &cancel, &mut || ran.set(true));
    assert!(ran.get(), "the default must run `work`");
    assert!(
        !cancel.is_cancelled(),
        "nobody can answer without a TTY: the token stays alive"
    );
}

/// Hueco #8 — guarda no-TTY de `TtyUi`: sin terminal, `run_cancellable`
/// ejecuta `work` en línea y el token NO se dispara (no hay a quién
/// preguntar, igual que en el default del puerto que hereda `HeadlessUi`).
///
/// Regresión que detecta: si `TtyUi::run_cancellable` perdiera (o
/// invertiera) la guarda `stdout().is_terminal() && stdin().is_terminal()`,
/// correría `run_progress` → `ratatui::init()` sobre un proceso sin
/// terminal: `try_init` falla en `enable_raw_mode` y `init()` pánica
/// (medido en este entorno, sin `/dev/tty`), o en un host con TTY
/// secuestraría la pantalla — el test sale en rojo en cualquiera de los dos
/// casos.
///
/// Deuda TTY declarada: si AMBOS descriptores son terminales este test se
/// omite al principio (una pantalla real no es suyo que secuestrar); en CI y
/// en cualquier corrida por pipe —que es donde gatea— corre siempre.
#[test]
fn tty_ui_sin_terminal_ejecuta_work_en_linea_sin_tocar_el_token() {
    if std::io::stdout().is_terminal() && std::io::stdin().is_terminal() {
        // Este test solo ejercita la rama SIN TTY: con un TTY real
        // `run_progress` tomaría la pantalla y el atajo no aplicaría.
        return;
    }
    let ui = TtyUi;
    let cancel = CancelToken::new();
    let ran = Cell::new(false);
    ui.run_cancellable("Descargando", &cancel, &mut || ran.set(true));
    assert!(ran.get(), "sin TTY `work` corre en línea, sin pantalla");
    assert!(
        !cancel.is_cancelled(),
        "sin TTY no hay quien cancele: el token sigue vivo"
    );
}
