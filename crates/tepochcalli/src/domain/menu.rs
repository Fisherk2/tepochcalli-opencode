//! H5 menu as a pure state machine: which button is enabled and why.
//!
//! The matrix is pinned by specs/spec-installer-wizard.md §TUI full-screen.
//! No I/O here: T8 renders this contract, T9 wires each action to its
//! use-case. `Exit` is enabled in every state — H10 is "leave touching
//! nothing", never a blocked action.

use super::version;

/// One of the five H5 buttons.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MenuAction {
    Install,
    Update,
    ChangeEmbedder,
    Desinstall,
    Exit,
}

impl MenuAction {
    /// The five H5 buttons in menu order (single source for every renderer).
    pub const ALL: [MenuAction; 5] = [
        MenuAction::Install,
        MenuAction::Update,
        MenuAction::ChangeEmbedder,
        MenuAction::Desinstall,
        MenuAction::Exit,
    ];

    #[must_use]
    pub fn label(self) -> &'static str {
        match self {
            MenuAction::Install => "Install",
            MenuAction::Update => "Update",
            MenuAction::ChangeEmbedder => "Change Embedder",
            MenuAction::Desinstall => "Desinstall",
            MenuAction::Exit => "Exit",
        }
    }

    #[must_use]
    pub fn icon(self) -> &'static str {
        match self {
            MenuAction::Install => "🔵",
            MenuAction::Update => "🟢",
            MenuAction::ChangeEmbedder => "🟣",
            MenuAction::Desinstall => "🔴",
            MenuAction::Exit => "🟠",
        }
    }
}

/// Installed version vs wizard version, as drawn by the spec's stateDiagram.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InstalledState {
    NotInstalled,
    UpToDate,
    Outdated,
    Ahead,
}

/// A rendered button: `reason` is `Some` exactly when it is disabled.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct MenuButton {
    pub action: MenuAction,
    pub enabled: bool,
    pub reason: Option<&'static str>,
}

/// The whole menu: buttons in spec order, plus the state message.
#[must_use]
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MenuSpec {
    pub buttons: Vec<MenuButton>,
    pub notice: Option<&'static str>,
}

const NO_INSTALL: &str = "no hay instalación aún";
const UP_TO_DATE: &str = "versión al día";
const ALREADY_INSTALLED: &str = "ya existe instalación";
const AHEAD: &str = "versión instalada mayor que la del wizard";
const AHEAD_NOTICE: &str =
    "versión instalada mayor que la del wizard: refresca la caché de uvx con `uvx --refresh tepochcalli`";
const READY_NOTICE: &str = "directorio listo para instalar";

type Button = (bool, Option<&'static str>);

const ON: Button = (true, None);

const fn off(reason: &'static str) -> Button {
    (false, Some(reason))
}

/// Derives the state from the two versions. `None` (no
/// `.tepochcalli/pyproject.toml`) is the only "not installed" case; a vault
/// that has the file but an unparsable version is treated as `UpToDate` —
/// conservative, so the menu never offers Install over an existing runtime.
#[must_use]
pub fn installed_state(installed: Option<&str>, wizard: &str) -> InstalledState {
    use std::cmp::Ordering;
    let Some(installed) = installed else {
        return InstalledState::NotInstalled;
    };
    match version::compare(installed, wizard) {
        Some(Ordering::Less) => InstalledState::Outdated,
        Some(Ordering::Greater) => InstalledState::Ahead,
        _ => InstalledState::UpToDate,
    }
}

/// The matrix, literally as the spec draws it.
pub fn menu_spec(state: InstalledState) -> MenuSpec {
    let (update, embedder, desinstall, install, notice) = match state {
        InstalledState::NotInstalled => (
            off(NO_INSTALL),
            off(NO_INSTALL),
            off(NO_INSTALL),
            ON,
            Some(READY_NOTICE),
        ),
        InstalledState::UpToDate => (off(UP_TO_DATE), ON, ON, off(UP_TO_DATE), None),
        InstalledState::Outdated => (ON, ON, ON, off(ALREADY_INSTALLED), None),
        InstalledState::Ahead => (
            off(AHEAD),
            off(AHEAD),
            off(AHEAD),
            off(AHEAD),
            Some(AHEAD_NOTICE),
        ),
    };

    let buttons = [
        (MenuAction::Update, update),
        (MenuAction::ChangeEmbedder, embedder),
        (MenuAction::Desinstall, desinstall),
        (MenuAction::Install, install),
        (MenuAction::Exit, ON),
    ]
    .into_iter()
    .map(|(action, (enabled, reason))| MenuButton {
        action,
        enabled,
        reason,
    })
    .collect();

    MenuSpec { buttons, notice }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn exit_stays_enabled_in_every_state() {
        for state in [
            InstalledState::NotInstalled,
            InstalledState::UpToDate,
            InstalledState::Outdated,
            InstalledState::Ahead,
        ] {
            let exit = menu_spec(state)
                .buttons
                .into_iter()
                .find(|b| b.action == MenuAction::Exit);
            assert!(
                exit.is_some_and(|b| b.enabled && b.reason.is_none()),
                "{state:?} must keep Exit enabled"
            );
        }
    }

    #[test]
    fn labels_and_icons_match_the_spec_vocabulary() {
        assert_eq!(MenuAction::ChangeEmbedder.label(), "Change Embedder");
        assert_eq!(MenuAction::Install.icon(), "🔵");
        assert_eq!(MenuAction::Update.icon(), "🟢");
        assert_eq!(MenuAction::ChangeEmbedder.icon(), "🟣");
        assert_eq!(MenuAction::Desinstall.icon(), "🔴");
        assert_eq!(MenuAction::Exit.icon(), "🟠");
    }
}
