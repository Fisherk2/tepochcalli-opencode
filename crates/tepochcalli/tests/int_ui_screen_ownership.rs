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

#[test]
fn int_ui_screen_ownership_input_secret_no_hace_eco_del_valor_bajo_el_watcher() {
    const SECRET: &str = "sk-NO-ECO-9f3a7b";
    let handle = Arc::new(DialogHandle::default());
    let cancel = CancelToken::new();
    let progress = Progress::new(7);
    set_active_progress(Some(&progress));
    set_active_dialog(Some(&handle));

    // Los frames se recogen en el watcher y se asertan en la hebra principal:
    // un fallo allí no debe dejar a `input_secret` esperando una respuesta.
    let mut frames: Vec<String> = Vec::new();
    let answered = std::thread::scope(|scope| {
        let watcher = scope.spawn(|| {
            let request = handle
                .wait_for_request()
                .expect("el watcher ve la petición");
            assert!(
                matches!(request, Dialog::Input { secret: true, .. }),
                "input_secret debe pedir un diálogo sin eco: {request:?}"
            );
            for ch in SECRET.chars() {
                assert!(handle.handle(DialogKey::Char(ch), &cancel));
                frames.push(buffer_text(&dialog_frame(&handle, 0)));
            }
            assert!(handle.handle(DialogKey::Confirm, &cancel));
        });
        let answered = TtyUi.input_secret("HF_TOKEN");
        watcher.join().expect("watcher");
        answered
    });
    let mut typed = String::new();
    for (index, ch) in SECRET.chars().enumerate() {
        typed.push(ch);
        let text = frames.get(index).expect("un frame por carácter tecleado");
        assert!(
            typed.len() < 4 || !text.contains(&typed),
            "el secreto nunca debe aparecer en el frame, ni parcialmente:\n{text}"
        );
        assert!(
            text.contains("<oculto>"),
            "el frame debe avisar de que hay contenido:\n{text}"
        );
        assert!(
            text.contains("HF_TOKEN"),
            "el enunciado sigue visible:\n{text}"
        );
    }
    assert_eq!(answered.expect("respuesta tipada"), SECRET);
    assert!(!cancel.is_cancelled(), "confirmar un secreto no cancela");
    handle.clear();
    set_active_dialog(None);
    set_active_progress(None);
}

#[test]
fn int_ui_screen_ownership_las_teclas_del_puerto_mueven_el_cursor_y_borran_texto() {
    // `dialog_key` (ui_selection.rs) es privado: crossterm no alcanza aquí.
    // Se ejerce el contrato del puerto que alimenta: ↑/k/BackTab → Previous,
    // ↓/j/Tab → Next, Enter → Confirm, Backspace → Backspace (documentado en
    // `DialogKey`). El watcher real solo corre bajo TTY y este target no lo
    // arranca: el mapeo crossterm→DialogKey queda sin cubrir.
    let handle = Arc::new(DialogHandle::default());
    let cancel = CancelToken::new();
    handle.request(Dialog::Select {
        prompt: "Embedding provider".to_string(),
        options: vec![
            "MiniLM".to_string(),
            "bge-m3".to_string(),
            "Configure later".to_string(),
        ],
        cursor: 0,
    });

    assert!(handle.handle(DialogKey::Previous, &cancel));
    let text = buffer_text(&dialog_frame(&handle, 0));
    assert!(
        text.contains("› Configure later"),
        "Previous envuelve a la última fila:\n{text}"
    );

    assert!(handle.handle(DialogKey::Next, &cancel));
    let text = buffer_text(&dialog_frame(&handle, 1));
    assert!(
        text.contains("› MiniLM"),
        "Next envuelve a la primera fila:\n{text}"
    );
    assert!(handle.handle(DialogKey::Confirm, &cancel));
    assert_eq!(handle.wait(), DialogOutcome::Index(0));

    handle.request(Dialog::Input {
        prompt: "HF id".to_string(),
        value: String::new(),
        secret: false,
    });
    for ch in "hf-k".chars() {
        assert!(handle.handle(DialogKey::Char(ch), &cancel));
    }
    let text = buffer_text(&dialog_frame(&handle, 0));
    assert!(
        text.contains("> hf-k"),
        "las teclas de texto llegan al valor:\n{text}"
    );
    assert!(handle.handle(DialogKey::Backspace, &cancel));
    let text = buffer_text(&dialog_frame(&handle, 1));
    assert!(
        text.contains("> hf-"),
        "Backspace quita el último carácter:\n{text}"
    );
    assert!(
        !text.contains("hf-k"),
        "el carácter borrado desaparece:\n{text}"
    );
    assert!(handle.handle(DialogKey::Confirm, &cancel));
    assert_eq!(handle.wait(), DialogOutcome::Text("hf-".to_string()));
    assert!(!cancel.is_cancelled(), "editar y confirmar no cancela");
}

#[test]
fn int_ui_screen_ownership_clear_del_watcher_despierta_al_esperador_y_no_cancela() {
    let handle = Arc::new(DialogHandle::default());
    let cancel = CancelToken::new();
    handle.request(Dialog::Input {
        prompt: "HF id".to_string(),
        value: "parcial".to_string(),
        secret: false,
    });

    // `ClearDialogOnDrop::drop` (ui_ratatui.rs) llama a este `clear`. Es privado
    // y solo vive en el watcher TTY: aquí se comprueba el contrato que invoca.
    handle.clear();
    assert!(
        handle.snapshot().is_none(),
        "clear (lo que hace el Drop del watcher) retira el diálogo"
    );
    assert_eq!(handle.wait(), DialogOutcome::Aborted);
    assert!(
        !cancel.is_cancelled(),
        "clear del watcher no inventa cancelación"
    );
    let text = buffer_text(&dialog_frame(&handle, 0));
    assert!(
        !text.contains("HF id"),
        "el frame ya no pinta el diálogo:\n{text}"
    );
    assert!(
        !text.contains("parcial"),
        "el valor pendiente no queda en el frame:\n{text}"
    );

    // Un clear no envenena la cola: el siguiente diálogo se responde igual.
    handle.request(Dialog::Select {
        prompt: "Embedding provider".to_string(),
        options: vec!["MiniLM".to_string()],
        cursor: 0,
    });
    assert!(handle.handle(DialogKey::Confirm, &cancel));
    assert_eq!(handle.wait(), DialogOutcome::Index(0));
}
