//! H5 decision without a terminal (T9): `choose_action` over a real temp
//! vault and a `ScriptedUi` — one test per scenario of the spec matrix, the
//! typed abort on a disabled button, and H10 (`Exit` touches nothing).
//!
//! In-process by design (`int_`): no TTY, no child process. The button order
//! is read from the spec, never hardcoded here.

// `common` es módulo compartido: este target no toca los fakes de fases.
mod common;

use std::collections::VecDeque;
use std::path::{Path, PathBuf};

use tempfile::TempDir;

use common::{FakeUiScript, ScriptedUi};
use tepochcalli::adapters::HeadlessUi;
use tepochcalli::application::{
    choose_action, embedder_label, home_view, wizard_version, EmbedderPresence, RUNTIME_DIR,
};
use tepochcalli::domain::{MenuAction, WizardError};
use tepochcalli::ports::Ui;

/// Vault fixture: `None` = no `.tepochcalli/pyproject.toml` (NotInstalled).
fn vault(version: Option<&str>) -> TempDir {
    let dir = tempfile::tempdir().expect("tempdir");
    if let Some(version) = version {
        let runtime = dir.path().join(RUNTIME_DIR);
        std::fs::create_dir_all(&runtime).expect("runtime dir");
        std::fs::write(
            runtime.join("pyproject.toml"),
            format!("[project]\nname = \"tepochcalli-flow\"\nversion = \"{version}\"\n"),
        )
        .expect("pyproject fixture");
    }
    dir
}

/// Asks the menu for `action`, scripting its real index from the spec.
fn ask(vault: &Path, action: MenuAction) -> Result<MenuAction, WizardError> {
    let spec = home_view(vault).spec;
    let index = spec
        .buttons
        .iter()
        .position(|button| button.action == action)
        .expect("H5 always has the five buttons");
    let ui = ScriptedUi::new(FakeUiScript {
        selects: VecDeque::from([index]),
        inputs: VecDeque::new(),
    });
    choose_action(&ui, vault)
}

/// `(relative path, file bytes)` for the whole tree, sorted; directories keep
/// `None` so a created empty dir is also a difference.
fn snapshot(root: &Path) -> Vec<(PathBuf, Option<Vec<u8>>)> {
    fn walk(root: &Path, dir: &Path, out: &mut Vec<(PathBuf, Option<Vec<u8>>)>) {
        let Ok(entries) = std::fs::read_dir(dir) else {
            return;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            let rel = path
                .strip_prefix(root)
                .expect("walked path lives under the root")
                .to_path_buf();
            if path.is_dir() {
                out.push((rel, None));
                walk(root, &path, out);
            } else {
                out.push((rel, std::fs::read(&path).ok()));
            }
        }
    }
    let mut out = Vec::new();
    walk(root, root, &mut out);
    out.sort();
    out
}

#[test]
fn not_installed_offers_only_install() {
    let dir = vault(None);
    assert_eq!(
        ask(dir.path(), MenuAction::Install),
        Ok(MenuAction::Install)
    );
    for blocked in [
        MenuAction::Update,
        MenuAction::ChangeEmbedder,
        MenuAction::Desinstall,
    ] {
        assert_eq!(
            ask(dir.path(), blocked),
            Err(WizardError::UserAborted),
            "{blocked:?} is disabled with no installation"
        );
    }
}

#[test]
fn up_to_date_blocks_install_and_update() {
    let dir = vault(Some(wizard_version()));
    assert_eq!(
        ask(dir.path(), MenuAction::ChangeEmbedder),
        Ok(MenuAction::ChangeEmbedder)
    );
    assert_eq!(
        ask(dir.path(), MenuAction::Desinstall),
        Ok(MenuAction::Desinstall)
    );
    assert_eq!(
        ask(dir.path(), MenuAction::Update),
        Err(WizardError::UserAborted)
    );
    assert_eq!(
        ask(dir.path(), MenuAction::Install),
        Err(WizardError::UserAborted)
    );
}

#[test]
fn outdated_offers_update_and_blocks_install() {
    let dir = vault(Some("0.0.1"));
    assert_eq!(ask(dir.path(), MenuAction::Update), Ok(MenuAction::Update));
    assert_eq!(
        ask(dir.path(), MenuAction::Install),
        Err(WizardError::UserAborted)
    );
}

#[test]
fn ahead_allows_only_exit() {
    let dir = vault(Some("99.0.0"));
    for blocked in [
        MenuAction::Install,
        MenuAction::Update,
        MenuAction::ChangeEmbedder,
        MenuAction::Desinstall,
    ] {
        assert_eq!(
            ask(dir.path(), blocked),
            Err(WizardError::UserAborted),
            "{blocked:?} must stay disabled when the installed version is ahead"
        );
    }
    assert_eq!(ask(dir.path(), MenuAction::Exit), Ok(MenuAction::Exit));
}

#[test]
fn exit_touches_nothing_on_disk() {
    for dir in [vault(Some("0.0.1")), vault(None)] {
        let before = snapshot(dir.path());
        assert_eq!(ask(dir.path(), MenuAction::Exit), Ok(MenuAction::Exit));
        assert_eq!(before, snapshot(dir.path()), "H10: Exit writes nothing");
    }
}

#[test]
fn home_view_carries_the_real_versions_and_the_embedder_state() {
    let dir = vault(Some("0.1.0"));
    std::fs::create_dir_all(dir.path().join(RUNTIME_DIR).join("models").join("hub"))
        .expect("models fixture");

    let view = home_view(dir.path());
    assert_eq!(view.installed.as_deref(), Some("0.1.0"));
    assert_eq!(view.wizard, wizard_version());
    assert_eq!(view.embedder, EmbedderPresence::LocalModel);
    assert!(
        view.spec
            .buttons
            .iter()
            .any(|b| b.action == MenuAction::Update),
        "the spec is the H5 matrix"
    );
}

#[test]
fn embedder_label_follows_the_real_vault_state() {
    // Pure mapping first: the three H5 words, no I/O.
    assert_eq!(
        embedder_label(EmbedderPresence::ExternalApi),
        "externo (API key)"
    );
    assert_eq!(
        embedder_label(EmbedderPresence::LocalModel),
        "local (.tepochcalli/models/)"
    );
    assert_eq!(embedder_label(EmbedderPresence::None), "sin configurar");

    // Then the real detection: litellm config / models/ with content / neither.
    let external = vault(Some("0.1.0"));
    let config = external
        .path()
        .join(RUNTIME_DIR)
        .join("config")
        .join("tepochcalli.toml");
    std::fs::create_dir_all(config.parent().expect("config parent")).expect("config dir");
    std::fs::write(&config, "[embedding]\nprovider = \"litellm\"\n").expect("config fixture");

    let local = vault(None);
    std::fs::create_dir_all(local.path().join(RUNTIME_DIR).join("models").join("hub"))
        .expect("models fixture");

    let bare = vault(None);

    assert_eq!(
        home_view(external.path()).menu_view().embedder,
        "externo (API key)"
    );
    assert_eq!(
        home_view(local.path()).menu_view().embedder,
        "local (.tepochcalli/models/)"
    );
    assert_eq!(
        home_view(bare.path()).menu_view().embedder,
        "sin configurar"
    );
}

#[test]
fn an_exhausted_script_is_a_typed_abort_never_a_hang() {
    // `--non-interactive` without a script: the menu answer queue is empty.
    let dir = vault(None);
    let ui = HeadlessUi::new(VecDeque::new(), VecDeque::new());
    assert_eq!(
        choose_action(&ui, dir.path()),
        Err(WizardError::UserAborted)
    );
    // The trait object form is the one `cli/home.rs` uses.
    let boxed: Box<dyn Ui> = Box::new(HeadlessUi::new(VecDeque::new(), VecDeque::new()));
    assert_eq!(
        choose_action(&*boxed, dir.path()),
        Err(WizardError::UserAborted)
    );
}
