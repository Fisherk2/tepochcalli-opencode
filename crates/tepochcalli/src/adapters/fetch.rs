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
    /// Transfer over the defensive cap (`MAX_TRANSFER_BYTES`): a hostile
    /// server cannot dictate allocation (payload real tens de MB).
    #[error("transfer of {url} exceeds the {max_bytes}-byte cap")]
    TooLarge { url: String, max_bytes: u64 },
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

/// Official release base (astral-sh/uv GitHub releases, no remote scripts).
pub const UV_RELEASE_BASE: &str = "https://github.com/astral-sh/uv/releases/download";

/// Pinned `uv` (repo canonical: Justfile + `phase1.yml` pin **0.12.9**).
pub const UV_VERSION: &str = "0.12.9";

pub const UV_ASSETS: &[UvAsset] = &[
    UvAsset {
        os: "linux",
        arch: "x86_64",
        filename: "uv-x86_64-unknown-linux-gnu.tar.gz",
        sha256_hex: "ec7a99cd05e0cd7f80243f135ce1361c76835cb0ee60055d14d20eba8eba1460",
    },
    UvAsset {
        os: "linux",
        arch: "aarch64",
        filename: "uv-aarch64-unknown-linux-gnu.tar.gz",
        sha256_hex: "c36fe17937ff6bd16dc42fc13854b5465999fcab2efe0af559381e945e3c6001",
    },
    UvAsset {
        os: "macos",
        arch: "x86_64",
        filename: "uv-x86_64-apple-darwin.tar.gz",
        sha256_hex: "e1ca175824f1056589ce9908f7631879ebc3c36535b5e63dc06510beb370b4c1",
    },
    UvAsset {
        os: "macos",
        arch: "aarch64",
        filename: "uv-aarch64-apple-darwin.tar.gz",
        sha256_hex: "301f72afaf54060f92da7016cb0115bd077f43a9c8e39c1d8170a0bac80fd398",
    },
    UvAsset {
        os: "windows",
        arch: "x86_64",
        filename: "uv-x86_64-pc-windows-msvc.zip",
        sha256_hex: "ddbfcee1ac615a0499f6aa97b5ec8ebdf3ee4a7714a48055ec2ba0030e3cf810",
    },
];

/// Asset for an explicit platform pair (test seam; production passes the
/// build's own `std::env::consts` values via [`uv_asset_for_current_platform`]).
#[must_use]
pub fn uv_asset_for(os: &str, arch: &str) -> Option<&'static UvAsset> {
    UV_ASSETS.iter().find(|a| a.os == os && a.arch == arch)
}

/// Asset matching this build's platform, if the table covers it.
#[must_use]
pub fn uv_asset_for_current_platform() -> Option<&'static UvAsset> {
    uv_asset_for(std::env::consts::OS, std::env::consts::ARCH)
}

/// Release download URL for `asset` (pinned version, official release).
#[must_use]
pub fn uv_download_url(asset: &UvAsset) -> String {
    format!("{UV_RELEASE_BASE}/{UV_VERSION}/{}", asset.filename)
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

/// Cap de la transferencia verificada (payload/`uv`): los assets reales
/// suman decenas de MB; 2 GiB deja margen x10 por cannon. Guarda de bomba:
/// un servidor hostil no dicta la asignación (L2-2).
pub const MAX_TRANSFER_BYTES: u64 = 2 * 1024 * 1024 * 1024;

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
    // Lectura por chunks con abort al vencer el cap: un cuerpo que miente
    // (o traita stream infinito) aborta sin componer una asignación del cap.
    let mut bytes = Vec::new();
    let mut chunk = [0u8; 1 << 16];
    let mut body = response.body_mut().as_reader();
    loop {
        let n = body.read(&mut chunk)?;
        if n == 0 {
            break;
        }
        if bytes.len() as u64 + n as u64 > MAX_TRANSFER_BYTES {
            return Err(FetchError::TooLarge {
                url: url.to_string(),
                max_bytes: MAX_TRANSFER_BYTES,
            });
        }
        bytes.extend_from_slice(&chunk[..n]);
    }
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
