//! Failure-log location + best-effort writer + vault-secret collector (T15).
//!
//! Logs live under the OS state dir (`$XDG_STATE_HOME/tepochcalli` on POSIX,
//! `%LOCALAPPDATA%/tepochcalli` on Windows) — never inside the vault. Reads
//! the vault config only to scrub the path-4 key from failure output.

use std::path::{Path, PathBuf};

use super::embedder_menu::config_path;

/// State-dir base scoped to the installer (never the vault). Per USER, not
/// per vault: every vault of the same user shares it.
#[must_use]
pub fn state_dir() -> PathBuf {
    #[cfg(windows)]
    {
        let local = std::env::var_os("LOCALAPPDATA").map(PathBuf::from);
        state_dir_from(None, local.as_deref(), &std::env::temp_dir())
    }
    #[cfg(not(windows))]
    {
        let home = std::env::var_os("HOME").map(PathBuf::from);
        let xdg = std::env::var_os("XDG_STATE_HOME").map(PathBuf::from);
        state_dir_from(home.as_deref(), xdg.as_deref(), &std::env::temp_dir())
    }
}

/// Pure state-dir decision (no env reads): `xdg` (`XDG_STATE_HOME` on Unix,
/// `LOCALAPPDATA` on Windows) → `home` (`~/.local/state`, Unix only) →
/// `tmp/tepochcalli-<pid>`. The tmp fallback is per process so two users
/// sharing a tmp can never collide; callers create it `0o700`, repair a
/// legacy `0755` dir and reject a symlink/non-dir.
#[must_use]
pub fn state_dir_from(home: Option<&Path>, xdg: Option<&Path>, tmp: &Path) -> PathBuf {
    if let Some(base) = xdg.filter(|path| !path.as_os_str().is_empty()) {
        return base.join("tepochcalli");
    }
    #[cfg(not(windows))]
    {
        if let Some(base) = home.filter(|path| !path.as_os_str().is_empty()) {
            return base.join(".local/state/tepochcalli");
        }
    }
    #[cfg(windows)]
    {
        let _ = home;
    }
    tmp.join(format!("tepochcalli-{}", std::process::id()))
}

/// Ensure `dir` is a user-private directory: create it `0700` on Unix
/// (default ACLs elsewhere), or repair a legacy `0755` dir to `0700` —
/// beta.1 created the state dir that way for its failure logs. A symlink or
/// a non-directory is refused (never chmod through a link); a chmod the
/// caller does not own surfaces as its own error.
pub(crate) fn ensure_private_dir(dir: &Path) -> std::io::Result<()> {
    match std::fs::symlink_metadata(dir) {
        Ok(meta) => {
            if meta.file_type().is_symlink() || !meta.is_dir() {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::PermissionDenied,
                    "state dir is a symlink or not a directory",
                ));
            }
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt as _;
                if meta.permissions().mode() & 0o077 != 0 {
                    // Repair, don't reject: the user's own beta.1 dir.
                    std::fs::set_permissions(dir, std::fs::Permissions::from_mode(0o700))?;
                }
            }
            Ok(())
        }
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            #[cfg(unix)]
            {
                use std::os::unix::fs::DirBuilderExt as _;
                std::fs::DirBuilder::new()
                    .recursive(true)
                    .mode(0o700)
                    .create(dir)
            }
            #[cfg(not(unix))]
            {
                std::fs::create_dir_all(dir)
            }
        }
        Err(e) => Err(e),
    }
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
        let _ = ensure_private_dir(parent);
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
    // Same file `embedder_menu::config_path` names (written by `write_config`).
    let body = match std::fs::read_to_string(config_path(vault)) {
        Ok(body) => body,
        Err(_) => return Vec::new(),
    };
    config_value(&body, "api_key").into_iter().collect()
}

/// The shared reader with the secret-specific contract on top: a blank value
/// is not a secret to redact (`domain::failure::redact` rightly refuses it),
/// so the `Some("")` the canonical reader returns becomes `None` here.
fn config_value(body: &str, key: &str) -> Option<String> {
    super::text::config_value(body, key).filter(|value| !value.is_empty())
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
