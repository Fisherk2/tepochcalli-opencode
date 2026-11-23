//! H5 menu render (T8): the pure `render_menu` drawn into a `TestBackend`
//! buffer — no TTY, no child process. Asserts what a user would actually see:
//! every button, the reason of each disabled one, the uvx refresh command and
//! the contact block.

#[allow(dead_code)]
mod common;

use ratatui::backend::TestBackend;
use ratatui::buffer::Buffer;
use ratatui::style::Modifier;
use ratatui::Terminal;

use common::helpers::buffer_text;
use tepochcalli::adapters::ui_ratatui::render_menu;
use tepochcalli::domain::{menu_spec, InstalledState};
use tepochcalli::ports::MenuView;

fn draw(state: InstalledState, width: u16, height: u16) -> Buffer {
    draw_view(
        state,
        width,
        height,
        "0.1.0",
        Some("0.1.0"),
        "local (.tepochcalli/models/)",
    )
}

fn draw_view(
    state: InstalledState,
    width: u16,
    height: u16,
    wizard: &str,
    installed: Option<&str>,
    embedder: &str,
) -> Buffer {
    let spec = menu_spec(state);
    let view = MenuView {
        spec: &spec,
        wizard,
        installed,
        embedder,
    };
    let mut terminal =
        Terminal::new(TestBackend::new(width, height)).expect("in-memory test backend");
    terminal
        .draw(|frame| render_menu(frame, &view, 0))
        .expect("draw into the test buffer");
    terminal.backend().buffer().clone()
}

#[test]
fn header_shows_the_resolved_versions_and_embedder_never_a_placeholder() {
    // T9: the caller resolves every fact (`home_view`); the render only
    // paints what it is given. `None` is the single "not installed" case.
    let up_to_date = buffer_text(&draw_view(
        InstalledState::UpToDate,
        80,
        24,
        "0.1.0",
        Some("0.1.0"),
        "local (.tepochcalli/models/)",
    ));
    assert!(
        up_to_date.contains(
            "Tepochcalli 0.1.0 · instalada: 0.1.0 · embedder: local (.tepochcalli/models/)"
        ),
        "header must carry all three facts:\n{up_to_date}"
    );

    let absent = buffer_text(&draw_view(
        InstalledState::NotInstalled,
        80,
        24,
        "0.1.0",
        None,
        "sin configurar",
    ));
    assert!(
        absent.contains("instalada: — · embedder: sin configurar"),
        "absent runtime renders the dash and the unset embedder:\n{absent}"
    );
}

#[test]
fn header_paints_each_embedder_label_in_its_own_header() {
    // H5: API key externa, modelo local y sin configurar, los tres visibles.
    for label in [
        "externo (API key)",
        "local (.tepochcalli/models/)",
        "sin configurar",
    ] {
        let text = buffer_text(&draw_view(
            InstalledState::UpToDate,
            80,
            24,
            "0.1.0",
            Some("0.1.0"),
            label,
        ));
        let header = text.lines().next().unwrap_or_default();
        assert!(
            header.contains(&format!("embedder: {label}")),
            "header must carry `{label}`, got:\n{header}"
        );
    }
}

#[test]
fn ahead_shows_every_button_its_reason_the_uvx_command_and_contact() {
    let text = buffer_text(&draw(InstalledState::Ahead, 80, 24));
    for label in ["Update", "Change Embedder", "Desinstall", "Install", "Exit"] {
        assert!(text.contains(label), "missing button {label}:\n{text}");
    }
    assert!(
        text.contains("versión instalada mayor que la del wizard"),
        "Ahead must show the reason next to each disabled button:\n{text}"
    );
    assert!(
        text.contains("uvx --refresh tepochcalli"),
        "Ahead must show the exact refresh command:\n{text}"
    );
    assert!(text.contains("https://github.com/Fisherk2/tepochcalli-opencode"));
    assert!(text.contains("dev@fisherk2.com"));
}

#[test]
fn not_installed_shows_the_no_install_reason_and_the_ready_notice() {
    let text = buffer_text(&draw(InstalledState::NotInstalled, 80, 24));
    assert_eq!(
        text.matches("no hay instalación aún").count(),
        3,
        "Update/Change Embedder/Desinstall each need the reason:\n{text}"
    );
    assert!(text.contains("directorio listo para instalar"));
    assert!(text.contains("Install"));
}

#[test]
fn up_to_date_blocks_update_and_install_with_the_same_reason() {
    let text = buffer_text(&draw(InstalledState::UpToDate, 80, 24));
    assert_eq!(text.matches("versión al día").count(), 2, "{text}");
}

#[test]
fn disabled_rows_are_dimmed_in_the_buffer() {
    let buffer = draw(InstalledState::NotInstalled, 80, 24);
    let area = buffer.area();
    let mut checked = 0;
    for y in area.top()..area.bottom() {
        let row: String = (area.left()..area.right())
            .filter_map(|x| buffer.cell((x, y)).and_then(|c| c.symbol().chars().next()))
            .collect();
        if row.contains("Update") || row.contains("Desinstall") {
            let dim = (area.left()..area.right()).any(|x| {
                buffer
                    .cell((x, y))
                    .is_some_and(|cell| cell.modifier.contains(Modifier::DIM))
            });
            assert!(dim, "disabled row must be attenuated: {row:?}");
            checked += 1;
        }
    }
    assert_eq!(checked, 2, "both disabled rows must be found");
}

#[test]
fn narrow_terminal_still_shows_buttons_reason_and_contact() {
    // 40x12: the smallest supported width must keep the actionable content.
    let text = buffer_text(&draw(InstalledState::Ahead, 40, 12));
    for label in ["Update", "Change Embedder", "Desinstall", "Install", "Exit"] {
        assert!(text.contains(label), "missing {label} at 40x12:\n{text}");
    }
    assert!(
        text.contains("mayor que"),
        "reason must be visible:\n{text}"
    );
    assert!(
        text.contains("uvx --refresh tepochcalli"),
        "refresh command must survive the wrap:\n{text}"
    );
    assert!(text.contains("github.com/Fisherk2"));
    assert!(text.contains("dev@fisherk2.com"));
}
