//! T20 — progreso por etapas: la barra avanza de 0 a 100 por hito, el
//! spinner ASCII vive en su propia fila y el cronómetro/ETA se inyectan como
//! `Duration` (sin `sleep` ni reloj de pared en el test).

mod common;

use std::cell::Cell;
use std::time::Duration;

use common::helpers::buffer_text;
use ratatui::backend::TestBackend;
use ratatui::buffer::Buffer;
use ratatui::Terminal;

use tepochcalli::adapters::HeadlessUi;
use tepochcalli::domain::CancelToken;
use tepochcalli::ports::{
    advance_active_stage, has_active_progress, set_active_progress, Progress, ProgressSpec, Ui,
};

fn stage_spec(steps: usize, eta: Option<Duration>) -> ProgressSpec {
    ProgressSpec {
        title: "Cambiando embedder".to_string(),
        steps,
        eta,
    }
}

fn draw_stages(spec: &ProgressSpec, progress: &Progress, elapsed: Duration, tick: u64) -> Buffer {
    let mut terminal = Terminal::new(TestBackend::new(90, 24)).expect("in-memory test backend");
    terminal
        .draw(|frame| {
            tepochcalli::adapters::ui_ratatui::render_stages(frame, spec, progress, elapsed, tick)
        })
        .expect("draw into the test buffer");
    terminal.backend().buffer().clone()
}

#[test]
fn int_progress_spec_seis_hitos_monotonos_llenan_la_barra_en_el_ultimo() {
    let spec = stage_spec(6, Some(Duration::from_secs(12)));
    let progress = Progress::new(spec.steps);
    let mut percents = Vec::new();
    let mut fills = Vec::new();

    for done in 0..=6 {
        let text = buffer_text(&draw_stages(&spec, &progress, Duration::ZERO, 0));
        let percent = done * 100 / 6;
        assert!(
            text.contains(&format!("{done}/6 · {percent}%")),
            "hito {done} debe mostrar su porcentaje real:\n{text}"
        );
        percents.push(percent);
        fills.push(text.matches('█').count());
        if done < 6 {
            progress.advance();
        }
    }

    assert!(
        percents.windows(2).all(|pair| pair[0] <= pair[1]),
        "la barra nunca debe retroceder: {percents:?}"
    );
    assert_eq!(percents.last(), Some(&100), "el sexto hito es el 100 %");
    assert!(
        fills.windows(2).all(|pair| pair[0] <= pair[1]),
        "el relleno nunca debe decrecer: {fills:?}"
    );
    assert!(fills.last().is_some_and(|&last| last > 0));
    assert_eq!(progress.done(), 6, "advance() se acota al total declarado");
}

#[test]
fn int_progress_spec_sin_estimacion_declarada_la_eta_es_literal() {
    let spec = stage_spec(6, None);
    let progress = Progress::new(spec.steps);
    let text = buffer_text(&draw_stages(&spec, &progress, Duration::ZERO, 0));

    assert!(
        text.contains("ETA —"),
        "sin base no se inventa un tiempo:\n{text}"
    );
    assert!(
        !text.contains("ETA 00:") && !text.contains("ETA ≈"),
        "los MB del index no se convierten en segundos:\n{text}"
    );

    let with_eta = stage_spec(6, Some(Duration::from_secs(12)));
    let text = buffer_text(&draw_stages(&with_eta, &progress, Duration::ZERO, 0));
    assert!(
        text.contains("ETA 00:12"),
        "la ETA declarada se muestra:\n{text}"
    );
}

#[test]
fn int_progress_spec_el_spinner_ascii_esta_en_su_propia_fila_y_cambia_con_el_tick() {
    let spec = stage_spec(6, Some(Duration::from_secs(12)));
    let progress = Progress::new(spec.steps);
    let mut frames = Vec::new();

    for tick in 0..4 {
        let text = buffer_text(&draw_stages(&spec, &progress, Duration::ZERO, tick));
        let spinner_rows: Vec<&str> = text
            .lines()
            .filter(|line| {
                line.trim_start()
                    .chars()
                    .next()
                    .is_some_and(|first| matches!(first, '|' | '/' | '-' | '\\'))
            })
            .collect();
        assert_eq!(
            spinner_rows.len(),
            1,
            "un único spinner, en su propia fila (tick {tick}):\n{text}"
        );
        frames.push(
            spinner_rows[0]
                .trim_start()
                .chars()
                .next()
                .expect("spinner row is not empty"),
        );
    }

    assert_eq!(frames, vec!['|', '/', '-', '\\'], "frames ASCII |/-\\");
}

#[test]
fn int_progress_spec_el_cronometro_usa_la_duracion_inyectada() {
    let spec = stage_spec(6, None);
    let progress = Progress::new(spec.steps);
    let text = buffer_text(&draw_stages(&spec, &progress, Duration::from_secs(125), 0));

    assert!(
        text.contains("transcurrido 02:05"),
        "mm:ss del cronómetro sin reloj de pared:\n{text}"
    );
}

#[test]
fn int_progress_spec_el_default_del_puerto_ejecuta_el_trabajo_sin_pantalla() {
    let ui = HeadlessUi::default();
    let spec = stage_spec(6, None);
    let cancel = CancelToken::new();
    let ran = Cell::new(false);

    ui.run_stages(&spec, &cancel, &mut |progress| {
        progress.advance();
        ran.set(true);
    });

    assert!(ran.get(), "el default no-op corre el trabajo en línea");
    assert!(
        !cancel.is_cancelled(),
        "la UI por defecto no dispara cancelación"
    );
}

#[test]
fn int_progress_spec_el_gate_no_toma_una_segunda_pantalla_con_la_barra_activa() {
    // El gate llama a `run_cancellable` DENTRO de `run_stages`: con la barra
    // exterior activa, esa pantalla debe ceder (work en línea) para no sacar
    // el frame exterior de la alternate screen. `TestBackend` no observa
    // `try_init`, así que se aserta el guard, no un frame.
    let progress = Progress::new(7);
    set_active_progress(Some(&progress));
    assert!(has_active_progress());
    advance_active_stage();
    assert_eq!(
        progress.done(),
        1,
        "el hito anidado cuenta en la barra activa"
    );
    let mut ran = false;
    tepochcalli::adapters::ui_ratatui::run_progress(
        "Descargando modelo de embeddings",
        &CancelToken::new(),
        &mut || ran = true,
    );
    set_active_progress(None);
    assert!(ran, "el trabajo del gate corre aunque ceda la pantalla");
    assert!(!has_active_progress(), "el guard se limpia al terminar");

    // El hito anidado (gate del install / scope del desinstall) solo cuenta
    // mientras hay una corrida con barra; fuera de ella es no-op.
    advance_active_stage();
    assert_eq!(
        progress.done(),
        1,
        "sin barra activa no se inventan hitos (sigue el único aviso de arriba)"
    );
}
