//! Failure-log location + best-effort writer + vault-secret collector (T15).
//!
//! Logs live under the OS state dir (`$XDG_STATE_HOME/tepochcalli` on POSIX,
//! `%LOCALAPPDATA%/tepochcalli` on Windows) — never inside the vault. Reads
//! the vault config only to scrub the path-4 key from failure output.

use std::path::{Path, PathBuf};

/// State-dir base scoped to the installer (never the vault).
#[must_use]
pub fn state_dir() -> PathBuf {
    if cfg!(windows) {
        if let Some(base) = std::env::var_os("LOCALAPPDATA") {
            let base = PathBuf::from(base);
            if !base.as_os_str().is_empty() {
                return base.join("tepochcalli");
            }
        }
    } else {
        if let Some(base) = std::env::var_os("XDG_STATE_HOME") {
            let base = PathBuf::from(base);
            if !base.as_os_str().is_empty() {
                return base.join("tepochcalli");
            }
        }
        if let Some(home) = std::env::var_os("HOME") {
            let home = PathBuf::from(home);
            if !home.as_os_str().is_empty() {
                return home.join(".local/state/tepochcalli");
            }
        }
    }
    std::env::temp_dir().join("tepochcalli")
}

/// Timestamped log path under `base`: `install-<unix-secs>.log`.
#[must_use]
pub fn log_path_in(base: &Path, now_secs: u64) -> PathBuf {
    base.join(format!("install-{now_secs}.log"))
}

/// Current Unix time in seconds; `0` when the clock is unavailable.
#[must_use]
pub fn now_secs() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|elapsed| elapsed.as_secs())
        .unwrap_or(0)
}

/// Best-effort append of one failure entry; never fails the install further.
pub fn write_failure_log(path: &Path, entry: &str) {
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    if let Ok(mut file) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
    {
        use std::io::Write as _;
        let _ = writeln!(file, "{entry}");
    }
}

/// Secrets to scrub: the path-4 `api_key` when the vault config holds one.
/// Best-effort: a missing/unreadable config yields no secrets.
#[must_use]
pub fn secrets_from_vault(vault: &Path) -> Vec<String> {
    // Same file `embedder_menu::write_config` writes (literal here to avoid
    // a cross-module import for one path).
    let body = match std::fs::read_to_string(vault.join(".tepochcalli/config/tepochcalli.toml")) {
        Ok(body) => body,
        Err(_) => return Vec::new(),
    };
    config_value(&body, "api_key").into_iter().collect()
}

/// Minimal `key = "value"` reader for the wizard-written config. Undoes the
/// writer's escaping (`\"` first, then `\\`); an empty value yields no secret
/// on purpose — the other readers return `Some("")`, but a blank secret here
/// would be handed to `domain::failure::redact`, which (rightly) refuses it.
fn config_value(body: &str, key: &str) -> Option<String> {
    body.lines().find_map(|line| {
        let rest = line
            .trim()
            .strip_prefix(key)?
            .trim_start()
            .strip_prefix('=')?;
        let value = rest.trim().strip_prefix('"')?.strip_suffix('"')?;
        let value = value.replace("\\\"", "\"").replace("\\\\", "\\");
        if value.is_empty() {
            None
        } else {
            Some(value)
        }
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn config_value_unescapes_what_the_writer_escaped() {
        // Forma que `embedder_menu::external_config` produce para una clave
        // con comilla y barra: el secreto tiene que leerse exacto para que el
        // redactor pueda borrarlo entero (un fragmento sobrevive al log).
        let body = "[embedding]\nprovider = \"litellm\"\n\
                    model = \"openai/text-embedding-3-small\"\n\
                    api_key = \"sk-\\\"a\\\\b\"\n";
        assert_eq!(
            config_value(body, "api_key").as_deref(),
            Some("sk-\"a\\b"),
            "leer la clave debe devolver el valor original"
        );
    }

    #[test]
    fn config_value_returns_none_for_an_empty_secret() {
        // Divergencia deliberada con las otras tres copias (que devuelven
        // `Some("")`): una clave vacía no es un secreto que borrar.
        assert_eq!(config_value("api_key = \"\"\n", "api_key"), None);
        assert_eq!(config_value("provider = \"none\"\n", "api_key"), None);
    }
}
