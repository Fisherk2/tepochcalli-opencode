//! Facts of an installed vault for the H5 menu (I/O side).
//!
//! The comparison lives in `domain::version` / `domain::menu`; this module
//! only reads the two inputs: the canonical version (ADR-014) and which
//! embedder arm the vault is configured with.

use std::path::Path;

use super::embedder_config::config_path;
use super::installer::RUNTIME_DIR;
use super::text::config_value;

/// Versión canónica instalada: `version` de `[project]` en
/// `.tepochcalli/pyproject.toml`. Fichero ausente o ilegible ⇒ `None`
/// (único caso que la spec llama «no hay pyproject en el destino»).
#[must_use]
pub fn installed_version(vault: &Path) -> Option<String> {
    let body = std::fs::read_to_string(vault.join(RUNTIME_DIR).join("pyproject.toml")).ok()?;
    config_value(&body, "version")
}

/// Versión que gestiona el wizard (la del paquete/release, D-007).
#[must_use]
pub fn wizard_version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

/// Cómo está instalado el embedder (H5).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EmbedderPresence {
    /// `provider = "litellm"` en `tepochcalli.toml` (API externa).
    ExternalApi,
    /// `.tepochcalli/models/` con al menos una entrada.
    LocalModel,
    /// Ni API externa ni modelos locales (instalación degradada o ajena).
    None,
}

#[must_use]
pub fn embedder_presence(vault: &Path) -> EmbedderPresence {
    let external = std::fs::read_to_string(config_path(vault))
        .ok()
        .and_then(|body| config_value(&body, "provider"))
        .is_some_and(|provider| provider == "litellm");
    if external {
        return EmbedderPresence::ExternalApi;
    }
    let models = vault.join(RUNTIME_DIR).join("models");
    if std::fs::read_dir(models).is_ok_and(|mut entries| entries.next().is_some()) {
        EmbedderPresence::LocalModel
    } else {
        EmbedderPresence::None
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    fn vault() -> TempDir {
        tempfile::tempdir().expect("tempdir")
    }

    #[test]
    fn reads_the_canonical_version_and_tolerates_a_missing_file() {
        let dir = vault();
        let runtime = dir.path().join(RUNTIME_DIR);
        fs::create_dir_all(&runtime).expect("create runtime");
        fs::write(
            runtime.join("pyproject.toml"),
            "[project]\nname = \"tepochcalli-flow\"\nversion = \"0.1.0\"\n",
        )
        .expect("write pyproject");

        assert_eq!(installed_version(dir.path()).as_deref(), Some("0.1.0"));
        assert_eq!(installed_version(&dir.path().join("elsewhere")), None);
    }

    #[test]
    fn wizard_version_is_a_parseable_semver() {
        assert!(crate::domain::Version::parse(wizard_version()).is_some());
    }

    #[test]
    fn litellm_config_means_external_api() {
        let dir = vault();
        let config = config_path(dir.path());
        fs::create_dir_all(config.parent().expect("config parent")).expect("create config dir");
        fs::write(&config, "[embedding]\nprovider = \"litellm\"\n").expect("write config");

        assert_eq!(embedder_presence(dir.path()), EmbedderPresence::ExternalApi);
    }

    #[test]
    fn models_dir_means_local_model() {
        let dir = vault();
        fs::create_dir_all(dir.path().join(RUNTIME_DIR).join("models").join("hub"))
            .expect("create models");

        assert_eq!(embedder_presence(dir.path()), EmbedderPresence::LocalModel);
    }

    #[test]
    fn empty_models_dir_or_absent_runtime_is_none() {
        let dir = vault();
        fs::create_dir_all(dir.path().join(RUNTIME_DIR).join("models")).expect("create models");
        assert_eq!(embedder_presence(dir.path()), EmbedderPresence::None);

        let bare = vault();
        assert_eq!(embedder_presence(bare.path()), EmbedderPresence::None);
    }
}
