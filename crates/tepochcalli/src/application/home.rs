//! H5 decision without a terminal: the facts of the target vault, the pure
//! menu they produce, and the ask to the [`Ui`].
//!
//! Choosing is read-only: `home_view` and `choose_action` never write, so
//! H10 (`Exit`) is "leave touching nothing" by construction. Each action is
//! routed to its use-case by `cli/`.

use std::path::Path;

use crate::domain::{installed_state, menu_spec, MenuAction, MenuSpec, WizardError};
use crate::ports::{MenuView, Ui};

use super::installed::{embedder_presence, installed_version, wizard_version, EmbedderPresence};

/// Everything the H5 header needs: the pure menu plus the two versions (real,
/// never `—` guesses) and how the embedder is installed.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HomeView {
    /// Buttons and state message derived from the two versions.
    pub spec: MenuSpec,
    /// Version this binary manages (the one `uvx` serves).
    pub wizard: String,
    /// Canonical installed version (`None` = no `.tepochcalli/pyproject.toml`).
    pub installed: Option<String>,
    /// External API, local model in `.tepochcalli/models/`, or neither.
    pub embedder: EmbedderPresence,
}

impl HomeView {
    /// What the port receives: the same facts, with the embedder already
    /// worded for display (the render never reads the vault).
    #[must_use]
    pub fn menu_view(&self) -> MenuView<'_> {
        MenuView {
            spec: &self.spec,
            wizard: &self.wizard,
            installed: self.installed.as_deref(),
            embedder: embedder_label(self.embedder),
        }
    }
}

/// H5 wording for the embedder state.
#[must_use]
pub fn embedder_label(presence: EmbedderPresence) -> &'static str {
    match presence {
        EmbedderPresence::ExternalApi => "externo (API key)",
        EmbedderPresence::LocalModel => "local (.tepochcalli/models/)",
        EmbedderPresence::None => "sin configurar",
    }
}

/// Reads the vault facts and derives the menu. No writes, no prompts.
#[must_use]
pub fn home_view(vault: &Path) -> HomeView {
    let installed = installed_version(vault);
    let wizard = wizard_version().to_string();
    let spec = menu_spec(installed_state(installed.as_deref(), &wizard));
    let embedder = embedder_presence(vault);
    HomeView {
        spec,
        wizard,
        installed,
        embedder,
    }
}

/// H5: builds the view and asks the `Ui` for a button. A disabled button or
/// an exhausted script is the typed `UserAborted` — never a guess.
pub fn choose_action(ui: &dyn Ui, vault: &Path) -> Result<MenuAction, WizardError> {
    ui.menu(&home_view(vault).menu_view())
}
