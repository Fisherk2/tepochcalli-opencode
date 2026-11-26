//! T3 — layout de tres zonas con aserciones POSICIONALES sobre el buffer de
//! `TestBackend`: ARRIBA (banner/progreso/spinner/ETA), CENTRO (mensajes y
//! selección) y ABAJO (menú H5 + contacto), en los cuatro tamaños acordados.
//! No hay TTY, reloj de pared ni hitos fingidos: todo se inyecta.

mod common;

use std::time::Duration;

use common::helpers::buffer_text;
use ratatui::backend::TestBackend;
use ratatui::buffer::Buffer;
use ratatui::Terminal;

use tepochcalli::adapters::ui_ratatui::{render_menu, render_stages, render_stages_with_dialog};
use tepochcalli::domain::{menu_spec, InstalledState};
use tepochcalli::ports::{Dialog, MenuView, Progress, ProgressSpec};

const SIZES: [(u16, u16); 4] = [(80, 24), (40, 12), (30, 8), (20, 6)];

/// Fila y columna de la primera aparición de `needle` en el buffer.
fn position(buffer: &Buffer, needle: &str) -> Option<(usize, usize)> {
    buffer_text(buffer)
        .lines()
        .enumerate()
        .find_map(|(y, row)| row.find(needle).map(|x| (y, x)))
}

fn draw_stages(width: u16, height: u16) -> Buffer {
    let spec = ProgressSpec {
        title: "Cambiando embedder".to_string(),
        steps: 7,
        eta: Some(Duration::from_secs(12)),
    };
    let progress = Progress::new(spec.steps);
    let mut terminal =
        Terminal::new(TestBackend::new(width, height)).expect("in-memory test backend");
    terminal
        .draw(|frame| render_stages(frame, &spec, &progress, Duration::ZERO, 0))
        .expect("draw into the test buffer");
    terminal.backend().buffer().clone()
}

fn draw_dialog(width: u16, height: u16, dialog: &Dialog) -> Buffer {
    let spec = ProgressSpec {
        title: "Instalando".to_string(),
        steps: 7,
        eta: None,
    };
    let progress = Progress::new(spec.steps);
    let mut terminal =
        Terminal::new(TestBackend::new(width, height)).expect("in-memory test backend");
    terminal
        .draw(|frame| {
            render_stages_with_dialog(frame, &spec, &progress, Duration::ZERO, 0, Some(dialog));
        })
        .expect("draw into the test buffer");
    terminal.backend().buffer().clone()
}

fn draw_menu(width: u16, height: u16, selected: usize) -> Buffer {
    let spec = menu_spec(InstalledState::Ahead);
    let view = MenuView {
        spec: &spec,
        wizard: "0.1.0",
        installed: Some("0.1.0"),
        embedder: "local (.tepochcalli/models/)",
    };
    let mut terminal =
        Terminal::new(TestBackend::new(width, height)).expect("in-memory test backend");
    terminal
        .draw(|frame| render_menu(frame, &view, selected))
        .expect("draw into the test buffer");
    terminal.backend().buffer().clone()
}

#[test]
fn int_ui_layout_eta_va_en_la_columna_derecha_en_los_cuatro_tamanos() {
    for &(width, height) in &SIZES {
        let buffer = draw_stages(width, height);
        let eta = position(&buffer, "ETA 00:12")
            .unwrap_or_else(|| panic!("sin ETA a {width}x{height}:\n{}", buffer_text(&buffer)));
        let clock = position(&buffer, "00:00").unwrap_or_else(|| {
            panic!(
                "sin cronómetro a {width}x{height}:\n{}",
                buffer_text(&buffer)
            )
        });
        assert_eq!(
            eta.0,
            clock.0,
            "ETA y cronómetro comparten la fila de estado a {width}x{height}:\n{}",
            buffer_text(&buffer)
        );
        assert!(
            eta.1 > clock.1,
            "la ETA debe estar a la derecha del cronómetro a {width}x{height}: clock={}, eta={}:\n{}",
            clock.1,
            eta.1,
            buffer_text(&buffer)
        );
        assert!(
            eta.1 >= usize::from(width / 2),
            "la ETA debe ocupar la columna derecha a {width}x{height}: eta={}:\n{}",
            eta.1,
            buffer_text(&buffer)
        );
    }
}

#[test]
fn int_ui_layout_tres_zonas_ordenadas_en_los_cuatro_tamanos() {
    for &(width, height) in &SIZES {
        let buffer = draw_stages(width, height);
        let header = position(&buffer, "Tepochcalli")
            .unwrap_or_else(|| panic!("sin banner a {width}x{height}:\n{}", buffer_text(&buffer)));
        let cancel = position(&buffer, "Cancelar").unwrap_or_else(|| {
            panic!("sin Cancelar a {width}x{height}:\n{}", buffer_text(&buffer))
        });
        let install = position(&buffer, "Install")
            .unwrap_or_else(|| panic!("sin Install a {width}x{height}:\n{}", buffer_text(&buffer)));
        let exit = position(&buffer, "Exit")
            .unwrap_or_else(|| panic!("sin Exit a {width}x{height}:\n{}", buffer_text(&buffer)));
        assert!(
            header.0 < cancel.0,
            "ARRIBA debe preceder al CENTRO a {width}x{height}:\n{}",
            buffer_text(&buffer)
        );
        assert!(
            cancel.0 < install.0 && install.0 <= exit.0,
            "el CENTRO debe preceder al ABAJO con el H5 completo a {width}x{height}: cancel={}, install={}, exit={}:\n{}",
            cancel.0,
            install.0,
            exit.0,
            buffer_text(&buffer)
        );
    }
}

#[test]
fn int_ui_layout_cancelar_sigue_visible_con_dialog_en_los_cuatro_tamanos() {
    let select = Dialog::Select {
        prompt: "Embedding provider".to_string(),
        options: vec!["MiniLM".to_string(), "bge-m3".to_string()],
        cursor: 0,
    };
    let notice = Dialog::Notice {
        title: "E_MODEL_INVALID".to_string(),
        body: "vuelve al menú".to_string(),
    };
    for &(width, height) in &SIZES {
        for dialog in [&select, &notice] {
            let buffer = draw_dialog(width, height, dialog);
            assert!(
                position(&buffer, "Cancelar").is_some(),
                "la fila Cancelar no debe desaparecer a {width}x{height} con {dialog:?}:\n{}",
                buffer_text(&buffer)
            );
        }
    }
}

#[test]
fn int_ui_layout_el_menu_tambien_reserva_tres_zonas() {
    for &(width, height) in &SIZES {
        let buffer = draw_menu(width, height, 0);
        let header = position(&buffer, "Tepochcalli")
            .unwrap_or_else(|| panic!("sin banner a {width}x{height}:\n{}", buffer_text(&buffer)));
        let install = position(&buffer, "Install")
            .unwrap_or_else(|| panic!("sin Install a {width}x{height}:\n{}", buffer_text(&buffer)));
        let exit = position(&buffer, "Exit")
            .unwrap_or_else(|| panic!("sin Exit a {width}x{height}:\n{}", buffer_text(&buffer)));
        assert!(
            header.0 < install.0 && install.0 <= exit.0,
            "banner arriba y H5 abajo a {width}x{height}:\n{}",
            buffer_text(&buffer)
        );
        if height >= 12 {
            let contact = position(&buffer, "dev@fisherk2.com").unwrap_or_else(|| {
                panic!("sin contacto a {width}x{height}:\n{}", buffer_text(&buffer))
            });
            assert!(
                contact.0 > exit.0,
                "el contacto va debajo del H5 a {width}x{height}:\n{}",
                buffer_text(&buffer)
            );
        }
    }
}

#[test]
fn int_ui_layout_el_foco_compacto_precede_a_la_fila_activa_a_20x6() {
    // 20x6 no caben cinco filas: `render_h5` usa el fallback compacto sin
    // `ListState`, así que el foco solo puede delatarse con el prefijo en la
    // propia etiqueta (y las filas bloqueadas con `off`).
    let spec = menu_spec(InstalledState::Ahead);
    let selected = spec
        .buttons
        .iter()
        .position(|button| button.enabled)
        .expect("Exit siempre habilitado");
    let buffer = draw_menu(20, 6, selected);
    let text = buffer_text(&buffer);
    let marker =
        position(&buffer, "›").unwrap_or_else(|| panic!("sin marcador de foco a 20x6:\n{text}"));
    let exit = position(&buffer, "Exit")
        .unwrap_or_else(|| panic!("sin Exit en el H5 compacto a 20x6:\n{text}"));
    assert_eq!(
        marker.0, exit.0,
        "el marcador debe estar en la fila de la opción activa:\n{text}"
    );
    assert!(
        marker.1 < exit.1,
        "el marcador debe preceder a la etiqueta activa: marcador={}, Exit={}:\n{text}",
        marker.1,
        exit.1
    );
    assert!(
        text.contains("off"),
        "las filas deshabilitadas deben marcarse `off` en el modo compacto:\n{text}"
    );
}

#[test]
fn int_ui_layout_la_leyenda_de_teclas_aparece_en_menu_y_dialogos() {
    let notice = Dialog::Notice {
        title: "E_MODEL_INVALID".to_string(),
        body: "vuelve al menú".to_string(),
    };
    // El diálogo solo reserva dos filas centrales a 40x12: ahí mandan el
    // aviso y Cancelar, la leyenda aparece en la terminal de 80x24.
    for (width, height, text) in [
        (80, 24, buffer_text(&draw_menu(80, 24, 0))),
        (40, 12, buffer_text(&draw_menu(40, 12, 0))),
        (80, 24, buffer_text(&draw_dialog(80, 24, &notice))),
    ] {
        assert!(
            text.contains("↑/↓/k/j/Tab = mover"),
            "sin leyenda de movimiento a {width}x{height}:\n{text}"
        );
        assert!(
            text.contains("Enter = elegir"),
            "sin leyenda de confirmación a {width}x{height}:\n{text}"
        );
    }
}
