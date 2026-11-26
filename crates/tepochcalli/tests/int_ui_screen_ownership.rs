//! T1 — un único dueño de la terminal en F6: con la barra activa el watcher
//! pinta y lee; `select`/`input`/`panel` delegan en él sin abrir un segundo
//! prompt ni una segunda pantalla. Sin barra, el comportamiento en línea
//! (`dialoguer`) sigue intacto.

mod common;

use std::sync::Arc;
use std::time::Duration;

use common::helpers::buffer_text;
use crossterm::event::{KeyCode, KeyModifiers};
use ratatui::backend::TestBackend;
use ratatui::buffer::Buffer;
use ratatui::Terminal;

use tepochcalli::adapters::{ui_ratatui, TtyUi};
use tepochcalli::domain::CancelToken;
use tepochcalli::ports::{
    advance_active_stage, has_active_dialog, has_active_progress, set_active_dialog,
    set_active_progress, Dialog, DialogHandle, DialogKey, DialogOutcome, Progress, ProgressSpec,
    Ui,
};

fn stage_spec() -> ProgressSpec {
    ProgressSpec {
        title: "Instalando".to_string(),
        steps: 7,
        eta: None,
    }
}

fn dialog_frame(handle: &DialogHandle, tick: u64) -> Buffer {
    let spec = stage_spec();
    let progress = Progress::new(spec.steps);
    let mut terminal = Terminal::new(TestBackend::new(90, 24)).expect("in-memory test backend");
    terminal
        .draw(|frame| {
            ui_ratatui::render_stages_with_dialog(
                frame,
                &spec,
                &progress,
                Duration::ZERO,
                tick,
                handle.snapshot().as_ref(),
            )
        })
        .expect("draw into the test buffer");
    terminal.backend().buffer().clone()
}

#[test]
fn int_ui_screen_ownership_con_barra_activa_no_hay_un_segundo_dueño() {
    // Espejo de int_progress_spec.rs:161-184: el gate cede el frame con la
    // barra activa y el hito anidado cuenta en el contador exterior.
    let handle = Arc::new(DialogHandle::default());
    let progress = Progress::new(7);
    set_active_progress(Some(&progress));
    set_active_dialog(Some(&handle));
    assert!(has_active_progress());
    assert!(has_active_dialog(), "el watcher publicó su diálogo");
    advance_active_stage();
    assert_eq!(progress.done(), 1);

    let mut gate_ran = false;
    ui_ratatui::run_progress("Descargando modelo", &CancelToken::new(), &mut || {
        gate_ran = true
    });
    assert!(gate_ran, "el gate corre sin tomar una segunda pantalla");

    // `select` responde desde el watcher: bajo cargo test no hay TTY, así que
    // un `dialoguer::Select` devolvería `UserAborted`. La respuesta tipada
    // prueba que no se abrió un segundo prompt.
    let ui = TtyUi;
    let cancel = CancelToken::new();
    let picked = std::thread::scope(|scope| {
        let watcher = scope.spawn(|| {
            let request = handle
                .wait_for_request()
                .expect("el watcher ve la petición");
            assert!(matches!(request, Dialog::Select { .. }));
            handle.handle(DialogKey::Next, &cancel);
            handle.handle(DialogKey::Confirm, &cancel);
        });
        let picked = ui.select("Embedding provider", &["MiniLM", "bge-m3"], 0);
        watcher.join().expect("watcher");
        picked
    });
    assert_eq!(
        picked.expect("respuesta tipada"),
        1,
        "↓ + Enter elige bge-m3"
    );

    // `input` y `panel` también ceden el TTY al watcher.
    let typed = std::thread::scope(|scope| {
        let watcher = scope.spawn(|| {
            let request = handle.wait_for_request().expect("el watcher ve el texto");
            assert!(matches!(request, Dialog::Input { .. }));
            for ch in "hf-id".chars() {
                handle.handle(DialogKey::Char(ch), &cancel);
            }
            handle.handle(DialogKey::Confirm, &cancel);
        });
        let typed = ui.input("HF id", None);
        watcher.join().expect("watcher");
        typed
    });
    assert_eq!(typed.expect("respuesta tipada"), "hf-id");

    ui.panel("E_MODEL_INVALID", "vuelve al menú");
    assert!(
        matches!(handle.snapshot(), Some(Dialog::Notice { .. })),
        "el panel se pinta en el frame, no se escribe en el TTY"
    );

    handle.clear();
    set_active_dialog(None);
    set_active_progress(None);
    assert!(!has_active_progress(), "el guard se limpia al terminar");
    assert!(!has_active_dialog());
    assert!(handle.snapshot().is_none(), "no queda estado de diálogo");
}

#[test]
fn int_ui_screen_ownership_la_seleccion_se_pinta_y_una_tecla_del_watcher_responde() {
    let handle = Arc::new(DialogHandle::default());
    let cancel = CancelToken::new();
    handle.request(Dialog::Select {
        prompt: "Embedding provider".to_string(),
        options: vec!["MiniLM".to_string(), "bge-m3".to_string()],
        cursor: 0,
    });

    let text = buffer_text(&dialog_frame(&handle, 0));
    assert!(
        text.contains("Embedding provider"),
        "prompt en la zona central:\n{text}"
    );
    assert!(
        text.contains("› MiniLM"),
        "fila preseleccionada visible:\n{text}"
    );
    assert!(text.contains("bge-m3"), "segunda opción ofrecida:\n{text}");

    assert!(
        handle.handle(DialogKey::Next, &cancel),
        "↓ la consume el watcher"
    );
    let text = buffer_text(&dialog_frame(&handle, 1));
    assert!(
        text.contains("› bge-m3"),
        "el cursor sigue la tecla:\n{text}"
    );

    assert!(
        handle.handle(DialogKey::Confirm, &cancel),
        "Enter la consume el watcher"
    );
    assert_eq!(handle.wait(), DialogOutcome::Index(1), "respuesta tipada");
    assert!(handle.snapshot().is_none(), "el frame vuelve a la barra");
    assert!(!cancel.is_cancelled(), "elegir no cancela la instalación");
}

#[test]
fn int_ui_screen_ownership_esc_y_ctrl_c_abortan_y_limpian_el_estado() {
    let handle = Arc::new(DialogHandle::default());
    let cancel = CancelToken::new();

    assert!(ui_ratatui::is_cancel_key(KeyCode::Esc, KeyModifiers::NONE));
    assert!(ui_ratatui::is_cancel_key(
        KeyCode::Char('c'),
        KeyModifiers::CONTROL
    ));

    handle.request(Dialog::Select {
        prompt: "Embedding provider".to_string(),
        options: vec!["MiniLM".to_string()],
        cursor: 0,
    });
    assert!(handle.handle(DialogKey::Cancel, &cancel));
    assert!(cancel.is_cancelled(), "la cancelación sigue compartida");
    assert_eq!(handle.wait(), DialogOutcome::Aborted);
    assert!(
        handle.snapshot().is_none(),
        "Esc limpia el estado del frame"
    );

    // Salida del watcher con una petición pendiente: nadie se queda esperando.
    let cancel_2 = CancelToken::new();
    handle.request(Dialog::Input {
        prompt: "HF id".to_string(),
        value: String::new(),
        secret: false,
    });
    handle.clear();
    assert_eq!(
        handle.wait(),
        DialogOutcome::Aborted,
        "clear despierta a select"
    );
    assert!(handle.snapshot().is_none());
    assert!(
        !cancel_2.is_cancelled(),
        "clear del watcher no inventa cancelación"
    );
}
