//! R-offline-2 progress screen (T16): the pure `render_progress` drawn into a
//! `TestBackend` (Cancelar enabled, the five menu rows blocked with a visible
//! reason, the no-destruction notice), the key classifier, and the inline
//! default the headless UI inherits (no screen, no token fired).

use std::cell::Cell;

use crossterm::event::{KeyCode, KeyModifiers};
use ratatui::backend::TestBackend;
use ratatui::buffer::Buffer;
use ratatui::style::Modifier;
use ratatui::Terminal;

use tepochcalli::adapters::ui_ratatui::{is_cancel_key, render_progress};
use tepochcalli::adapters::HeadlessUi;
use tepochcalli::domain::CancelToken;
use tepochcalli::ports::Ui;

fn draw(width: u16, height: u16) -> Buffer {
    let mut terminal =
        Terminal::new(TestBackend::new(width, height)).expect("in-memory test backend");
    terminal
        .draw(|frame| render_progress(frame, "Descargando modelo de embeddings"))
        .expect("draw into the test buffer");
    terminal.backend().buffer().clone()
}

/// Flattens the buffer grid into searchable text (one line per row).
fn text(buffer: &Buffer) -> String {
    let area = buffer.area();
    (area.top()..area.bottom())
        .map(|y| {
            (area.left()..area.right())
                .map(|x| {
                    buffer
                        .cell((x, y))
                        .and_then(|cell| cell.symbol().chars().next())
                        .unwrap_or(' ')
                })
                .collect::<String>()
        })
        .collect::<Vec<_>>()
        .join("\n")
}

#[test]
fn progress_shows_the_title_and_the_enabled_cancel_row() {
    let text = text(&draw(80, 24));
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
fn every_menu_action_is_blocked_with_the_download_reason() {
    let text = text(&draw(80, 24));
    for label in ["Install", "Update", "Change Embedder", "Desinstall", "Exit"] {
        assert!(text.contains(label), "missing blocked row {label}:\n{text}");
    }
    assert_eq!(
        text.matches("descarga en curso").count(),
        5,
        "each of the five actions needs its visible reason:\n{text}"
    );
    assert!(
        text.contains("El workspace no se tocará"),
        "the no-destruction notice must be visible:\n{text}"
    );
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
        if row.contains("descarga en curso") {
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
