//! Artefactos `[embedding]` del wizard: cuerpos de config, escritura atómica
//! e lectura de vuelta (F6).
//!
//! La cabecera es del caller y el cuerpo lo ponen los builders: así el
//! artefacto que escribe el swap conserva sus bytes (trazabilidad).

use std::path::{Path, PathBuf};

use crate::domain::WizardError;

use super::embedder_menu::Phase6Report;
use super::installer::{set_user_private, RUNTIME_DIR};
use super::text::{config_value, provider_is_none, toml_escape};

/// Config dir under the vault runtime dir (gitignored, never committed).
const CONFIG_DIR: &str = "config";
/// Config file name; written via temp + rename (never half-written).
const CONFIG_FILE: &str = "tepochcalli.toml";

/// Header line of `[embedding]` configs this wizard writes — provenance is
/// caller-specific and stays byte-identical per artifact (trazabilidad):
/// install paths carry the F6 blurb, the swap path the D8.4 one. The whole
/// line is the parameter; the builders never invent its text.
pub(super) const F6_LOCAL_HEADER: &str =
    "generado por `tepochcalli install` (F6) — re-entrada: `tepochcalli config embedder`";
pub(super) const F6_EXTERNAL_HEADER: &str =
    "generado por `tepochcalli install` (F6) — gitignored, nunca commitear";
pub(super) const F6_NONE_HEADER: &str =
    "generado por `tepochcalli install` (F6, salida 5) — re-entrada: `tepochcalli config embedder`";

/// `provider = "local"` con el modelo y, cuando se conoce, su `revision` (SHA):
/// sin esa clave el read path cae al default del flow y puede no coincidir con
/// el snapshot materializado (D59).
pub(super) fn local_config(header: &str, model: &str, revision: Option<&str>) -> String {
    let mut body = format!(
        "# {header}\n[embedding]\nprovider = \"local\"\nmodel = \"{}\"\n",
        toml_escape(model)
    );
    if let Some(sha) = revision {
        body.push_str(&format!("revision = \"{}\"\n", toml_escape(sha)));
    }
    body.push_str("device = \"cpu\"\n");
    body
}

pub(super) fn external_config(header: &str, model: &str, api_key: &str) -> String {
    format!(
        "# {header}\n\
         [embedding]\n\
         provider = \"litellm\"\n\
         model = \"{}\"\n\
         api_key = \"{}\"\n",
        toml_escape(model),
        toml_escape(api_key)
    )
}

pub(super) fn none_config(header: &str) -> String {
    format!(
        "# {header}\n\
         [embedding]\n\
         provider = \"none\"\n"
    )
}

/// Temp file + rename: a failed write never leaves half a config, and a
/// preexisting config stays byte-identical unless the gate passed. Ambas
/// ramas de fallo limpian el `.tmp` best-effort (L2-5): el vacío no queda
/// como residuo del config dir (usuario lo ve en Obsidian).
pub(super) fn write_config(vault: &Path, body: &str) -> Result<(), WizardError> {
    // shortcut: every fs failure maps to `PermissionDenied` (T7 convention;
    // T15 refines the panel).
    let dir = vault.join(RUNTIME_DIR).join(CONFIG_DIR);
    std::fs::create_dir_all(&dir).map_err(|_| WizardError::PermissionDenied)?;
    let tmp = dir.join(format!("{CONFIG_FILE}.tmp"));
    std::fs::write(&tmp, body).map_err(|_| WizardError::PermissionDenied)?;
    set_user_private(&tmp)?;
    match std::fs::rename(&tmp, dir.join(CONFIG_FILE)) {
        Ok(()) => Ok(()),
        Err(_) => {
            let _ = std::fs::remove_file(&tmp);
            Err(WizardError::PermissionDenied)
        }
    }
}

/// Vault-absolute config path (single source for the T14 artifact check).
#[must_use]
pub fn config_path(vault: &Path) -> PathBuf {
    vault.join(RUNTIME_DIR).join(CONFIG_DIR).join(CONFIG_FILE)
}

/// `true` cuando la config del vault delega el embedding en un API externo
/// (provider = "litellm"): brazo D7.3 del guard offline (L3-5) — esa
/// configuración no necesita modelos locales. Best-effort: config ausente
/// o ilegible ⇒ false (el guard cae en los demás brazos).
#[must_use]
pub fn litellm_config_present(vault: &Path) -> bool {
    std::fs::read_to_string(config_path(vault))
        .map(|body| config_value(&body, "provider").as_deref() == Some("litellm"))
        .unwrap_or(false)
}

/// Rebuild the F6 report from an existing config (for `--resume`: skip the
/// menu, keep the recorded provider/model/revision). `None` when no config exists.
#[must_use]
pub fn read_completed_report(vault: &Path) -> Option<Phase6Report> {
    let body = std::fs::read_to_string(config_path(vault)).ok()?;
    if provider_is_none(&body) {
        return Some(Phase6Report::configure_later());
    }
    let provider = config_value(&body, "provider")?;
    let model = config_value(&body, "model");
    let revision = config_value(&body, "revision");
    Some(Phase6Report {
        provider,
        model,
        revision,
        dims: None,
        rss_peak_bytes: None,
    })
}

/// F6 compensation (T14): fall back to salida 5 — a COMPLETE degraded
/// install (`provider = "none"`), never a failed one. Only the config is
/// written; `models/`, `db/` and user files are untouched.
pub fn compensate_phase6(vault: &Path) -> Result<(), WizardError> {
    write_config(vault, &none_config(F6_NONE_HEADER))
}

#[cfg(test)]
mod tests {
    use super::{
        config_path, external_config, local_config, none_config, write_config, F6_EXTERNAL_HEADER,
        F6_LOCAL_HEADER, F6_NONE_HEADER,
    };

    #[test]
    fn config_bodies_combine_the_caller_header_byte_identically() {
        // Trazabilidad del artefacto: la cabecera es del caller, el cuerpo lo
        // ponen los generadores. Comillas/barras van en medio del escape.
        let body = local_config(F6_LOCAL_HEADER, "BAAI/bge-m3", None);
        assert_eq!(
            body,
            "# generado por `tepochcalli install` (F6) — re-entrada: `tepochcalli config embedder`\n\
             [embedding]\n\
             provider = \"local\"\n\
             model = \"BAAI/bge-m3\"\n\
             device = \"cpu\"\n"
        );
        // Con SHA, `revision` va entre `model` y `device` (D59).
        let pinned = local_config(F6_LOCAL_HEADER, "BAAI/bge-m3", Some("5617a9f"));
        assert_eq!(
            pinned,
            "# generado por `tepochcalli install` (F6) — re-entrada: `tepochcalli config embedder`\n\
             [embedding]\n\
             provider = \"local\"\n\
             model = \"BAAI/bge-m3\"\n\
             revision = \"5617a9f\"\n\
             device = \"cpu\"\n"
        );
        assert_eq!(
            external_config(F6_EXTERNAL_HEADER, "m\"a\\b", "sk-1"),
            "# generado por `tepochcalli install` (F6) — gitignored, nunca commitear\n\
             [embedding]\n\
             provider = \"litellm\"\n\
             model = \"m\\\"a\\\\b\"\n\
             api_key = \"sk-1\"\n"
        );
        assert_eq!(
            none_config(F6_NONE_HEADER),
            "# generado por `tepochcalli install` (F6, salida 5) — re-entrada: `tepochcalli config embedder`\n\
             [embedding]\n\
             provider = \"none\"\n"
        );
    }

    /// L2-5: un rename que falla (destino ocupado por un dir) limpia el
    /// `.tmp` best-effort — el config dir no queda con residuo.
    #[test]
    fn failed_rename_cleans_the_config_tmp() {
        let Ok(vault) = tempfile::tempdir() else {
            panic!("tempdir");
        };
        let live = config_path(vault.path());
        if let Err(err) = std::fs::create_dir_all(&live) {
            panic!("sabotage: live config como dir: {err}");
        }
        assert_eq!(
            write_config(vault.path(), "[embedding]\nprovider = \"local\"\n"),
            Err(crate::domain::WizardError::PermissionDenied)
        );
        let tmp = live.with_extension("tmp");
        assert!(
            !tmp.exists(),
            "el .tmp debe quedarse limpio tras el fallo, no como residuo"
        );
    }

    /// La config lleva la clave de la ruta 4 en claro: usuario-privado
    /// aunque la umask del proceso sea abierta (L2-1).
    #[cfg(unix)]
    #[test]
    fn write_config_leaves_the_config_user_private() {
        use std::os::unix::fs::PermissionsExt;
        let Ok(vault) = tempfile::tempdir() else {
            panic!("tempdir");
        };
        if let Err(err) = write_config(vault.path(), "[embedding]\nprovider = \"litellm\"\n") {
            panic!("write_config: {err:?}");
        }
        let Ok(meta) = std::fs::metadata(config_path(vault.path())) else {
            panic!("config debe existir tras write_config");
        };
        let mode = meta.permissions().mode();
        assert_eq!(mode & 0o077, 0, "sin rwx para grupo/otros, mode {mode:o}");
    }
}
