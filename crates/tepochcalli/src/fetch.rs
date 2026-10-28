//! `uv` bootstrap spike: download the official release binary with SHA-256
//! verification. Never executes remote scripts (`install.sh`/`install.ps1`):
//! only released artifacts with checksums (OM-5).

use std::fs;
use std::io::Read as _;
use std::path::Path;
use std::time::Duration;

use sha2::{Digest, Sha256};
use thiserror::Error;

#[derive(Debug, Error)]
pub enum FetchError {
    #[error("checksum mismatch for {url}: expected {expected}, got {actual}")]
    ChecksumMismatch {
        url: String,
        expected: String,
        actual: String,
    },
    #[error("bad sha256 hex (want 64 hex chars)")]
    BadChecksumFormat,
    #[error("running {bin}: {source}")]
    VersionCheck {
        bin: String,
        #[source]
        source: std::io::Error,
    },
    #[error("non-UTF8 --version output from {0}")]
    BadVersionOutput(String),
    #[error(transparent)]
    Http(#[from] ureq::Error),
    #[error(transparent)]
    Io(#[from] std::io::Error),
}

pub struct UvAsset {
    pub os: &'static str,
    pub arch: &'static str,
    pub filename: &'static str,
    pub sha256_hex: &'static str,
}

/// Real pins land in T9/T18; placeholders are deliberate, not oversights.
pub const UV_VERSION: &str = "0.9.0";

pub const UV_ASSETS: &[UvAsset] = &[
    UvAsset {
        os: "linux",
        arch: "x86_64",
        filename: "uv-x86_64-unknown-linux-gnu.tar.gz",
        sha256_hex: "PLACEHOLDER_T9_LINUX_X86_64",
    },
    UvAsset {
        os: "linux",
        arch: "aarch64",
        filename: "uv-aarch64-unknown-linux-gnu.tar.gz",
        sha256_hex: "PLACEHOLDER_T9_LINUX_AARCH64",
    },
    UvAsset {
        os: "macos",
        arch: "x86_64",
        filename: "uv-x86_64-apple-darwin.tar.gz",
        sha256_hex: "PLACEHOLDER_T9_MACOS_X86_64",
    },
    UvAsset {
        os: "macos",
        arch: "aarch64",
        filename: "uv-aarch64-apple-darwin.tar.gz",
        sha256_hex: "PLACEHOLDER_T9_MACOS_AARCH64",
    },
];

/// Asset matching this build's platform, if the table covers it.
#[must_use]
pub fn uv_asset_for_current_platform() -> Option<&'static UvAsset> {
    let (os, arch) = (std::env::consts::OS, std::env::consts::ARCH);
    UV_ASSETS.iter().find(|a| a.os == os && a.arch == arch)
}

fn decode_sha256(hex: &str) -> Result<[u8; 32], FetchError> {
    if hex.len() != 64 || !hex.bytes().all(|b| b.is_ascii_hexdigit()) {
        return Err(FetchError::BadChecksumFormat);
    }
    let mut out = [0u8; 32];
    for (i, chunk) in hex.as_bytes().chunks(2).enumerate() {
        let s = std::str::from_utf8(chunk).map_err(|_| FetchError::BadChecksumFormat)?;
        out[i] = u8::from_str_radix(s, 16).map_err(|_| FetchError::BadChecksumFormat)?;
    }
    Ok(out)
}

/// GET `url`, verify SHA-256, then write `dest`. The file is written ONLY
/// after the hash matches, so a corrupt download never lands on disk.
/// Redirects follow the client's bounded default; never runs scripts.
pub fn fetch_verified(url: &str, dest: &Path, expected_sha256_hex: &str) -> Result<(), FetchError> {
    let expected = decode_sha256(expected_sha256_hex)?;
    let config = ureq::Agent::config_builder()
        .timeout_global(Some(Duration::from_secs(120)))
        .build();
    let agent = ureq::Agent::new_with_config(config);
    let mut response = agent.get(url).call()?;
    let mut bytes = Vec::new();
    response.body_mut().as_reader().read_to_end(&mut bytes)?;
    let digest = Sha256::digest(&bytes);
    if digest[..] != expected {
        return Err(FetchError::ChecksumMismatch {
            url: url.to_string(),
            expected: expected_sha256_hex.to_string(),
            actual: format!("{digest:x}"),
        });
    }
    if let Some(parent) = dest.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(dest, &bytes)?;
    Ok(())
}

/// `chmod 755` on Unix; no-op where the bit doesn't exist (Windows).
pub fn make_executable(path: &Path) -> std::io::Result<()> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt as _;
        let mut perms = fs::metadata(path)?.permissions();
        perms.set_mode(0o755);
        fs::set_permissions(path, perms)
    }
    #[cfg(not(unix))]
    {
        let _ = path;
        Ok(())
    }
}

/// Run `bin --version`, return stdout. Proves the fetched binary executes.
pub fn run_version(bin: &Path) -> Result<String, FetchError> {
    let bin_str = bin.display().to_string();
    let out = std::process::Command::new(bin)
        .arg("--version")
        .output()
        .map_err(|source| FetchError::VersionCheck {
            bin: bin_str.clone(),
            source,
        })?;
    if !out.status.success() {
        return Err(FetchError::VersionCheck {
            bin: bin_str,
            source: std::io::Error::other(format!("exit status {}", out.status)),
        });
    }
    String::from_utf8(out.stdout).map_err(|_| FetchError::BadVersionOutput(bin_str))
}
