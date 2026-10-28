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

/// Minimal `key = "value"` reader for the wizard-written config.
fn config_value(body: &str, key: &str) -> Option<String> {
    body.lines().find_map(|line| {
        let rest = line
            .trim()
            .strip_prefix(key)?
            .trim_start()
            .strip_prefix('=')?;
        let value = rest.trim().strip_prefix('"')?.strip_suffix('"')?;
        if value.is_empty() {
            None
        } else {
            Some(value.to_string())
        }
    })
}
