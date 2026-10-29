//! F3 payload adapters (T8): [`LocalPayload`] copies a dev/test tree,
//! [`ReleasePayload`] fetches the versioned asset with SHA-256 and extracts
//! it. Both merge WITHOUT overwrite and never write outside the vault.
//!
//! Second Writing-Outside-Dir surface after T2 (`archive.rs`): the merge
//! itself is join-checked against the canonical vault, and payload symlinks
//! are never followed — only regular files are copied as plain files.

use std::fs;
use std::io::ErrorKind;
use std::path::{Path, PathBuf};

use crate::archive::extract_tar_gz;
use crate::domain::WizardError;
use crate::ports::{HttpClient, MergeReport, PayloadSource};

use super::http::UreqHttpClient;

/// `.obsidian/` never crosses the merge, in either direction (user settings
/// win unconditionally; a payload copy would clobber them).
const OBSIDIAN_DIR: &str = ".obsidian";
/// Scratch dir for release extraction, inside the vault so no cross-device
/// move is needed; removed after the merge (best-effort).
const STAGE_DIR: &str = ".tepochcalli/.payload-stage";

/// T19 wires the real asset; until then this URL fails closed (unfetchable).
/// T19: still the fail-closed sentinel — the real asset comes from
/// [`payload_asset_url`] (one-version rule), never from this constant.
pub const RELEASE_ASSET_URL_PLACEHOLDER: &str = "PLACEHOLDER_T19_RELEASE_ASSET_URL";
/// T19 wires the real checksum; until then nothing can match it.
/// T19: still the fail-closed sentinel — the real checksum comes from the
/// `<asset>.sha256` sidecar via [`fetch_release_payload`], never from here.
pub const RELEASE_ASSET_SHA256_PLACEHOLDER: &str = "PLACEHOLDER_T19_RELEASE_ASSET_SHA256";

/// Release repo hosting the versioned payload asset (one-version rule: the
/// binary never follows a floating `latest` — it asks for its own version).
pub const PAYLOAD_RELEASE_REPO: &str = "Fisherk2/tepochcalli-opencode";
/// Asset stem: the published file is `{stem}-<ver>.tar.gz` + `.sha256`.
pub const PAYLOAD_ASSET_STEM: &str = "tepochcalli-workspace";
/// Release-base override: the same env var `installers/install.sh` documents
/// for mirrors and loopback tests.
pub const ENV_RELEASE_BASE_URL: &str = "TEPOCHCALLI_RELEASE_BASE_URL";

/// Release tag carrying the payload for `version` (canonical form; the
/// workflow publishes under this tag — see `release.yml`).
#[must_use]
pub fn payload_release_tag(version: &str) -> String {
    format!("tepochcalli-v{version}")
}

/// Versioned asset name: `tepochcalli-workspace-<ver>.tar.gz` (T19 AC-b).
#[must_use]
pub fn payload_asset_name(version: &str) -> String {
    format!("{PAYLOAD_ASSET_STEM}-{version}.tar.gz")
}

/// Checksum sidecar name (`sha256sum` format: `<hex>  <filename>`).
#[must_use]
pub fn payload_checksum_name(version: &str) -> String {
    format!("{}.sha256", payload_asset_name(version))
}

/// Release base URL for the payload assets: GitHub's download dir for
/// [`PAYLOAD_RELEASE_REPO`]'s tags, or the `TEPOCHCALLI_RELEASE_BASE_URL`
/// override (empty/blank counts as unset, like `install.sh`'s `[ -n ]`).
///
/// A plain-`http` base is allowed here and only here: loopback mirrors have no
/// TLS certificate, and the trust gate is the SHA-256 sidecar, never the
/// transport. The default stays `https` and never `latest`.
// shortcut: the scheme allowlist is `ureq`'s (http/https); a `file:` base
// cannot read local files — upgrade only if a non-http transport is added.
#[must_use]
pub fn release_base_url_from(env: Option<&str>) -> String {
    match env.map(str::trim) {
        Some(base) if !base.is_empty() => base.trim_end_matches('/').to_string(),
        _ => format!("https://github.com/{PAYLOAD_RELEASE_REPO}/releases/download"),
    }
}

/// [`release_base_url_from`] reading the real environment.
#[must_use]
pub fn release_base_url() -> String {
    release_base_url_from(std::env::var(ENV_RELEASE_BASE_URL).ok().as_deref())
}

/// Download URL of the versioned payload asset under `base` (pure).
#[must_use]
pub fn payload_asset_url_from(base: &str, version: &str) -> String {
    format!(
        "{}/{}/{}",
        base.trim_end_matches('/'),
        payload_release_tag(version),
        payload_asset_name(version)
    )
}

/// Download URL of the versioned payload asset (pinned to `version`,
/// never `latest` — T19 AC-c, one-version rule).
#[must_use]
pub fn payload_asset_url(version: &str) -> String {
    payload_asset_url_from(&release_base_url(), version)
}

/// Download URL of the asset's SHA-256 sidecar.
#[must_use]
pub fn payload_checksum_url(version: &str) -> String {
    format!("{}.sha256", payload_asset_url(version))
}

/// First token of a `sha256sum` sidecar; anything else is `PayloadCorrupt`
/// (clean failure, exit 32 — never a partial install).
pub fn parse_sha256_sidecar(sidecar: &[u8]) -> Result<String, WizardError> {
    let text = std::str::from_utf8(sidecar).map_err(|_| WizardError::PayloadCorrupt)?;
    let first = text
        .split_whitespace()
        .next()
        .ok_or(WizardError::PayloadCorrupt)?;
    if first.len() != 64 || !first.bytes().all(|b| b.is_ascii_hexdigit()) {
        return Err(WizardError::PayloadCorrupt);
    }
    Ok(first.to_string())
}

/// Copies a local dir tree — `--payload <ruta>`, for dev and tests.
#[derive(Debug, Clone)]
pub struct LocalPayload {
    src: PathBuf,
}

impl LocalPayload {
    /// Serve copies of the tree under `src` (checked at merge time).
    #[must_use]
    pub fn new(src: &Path) -> Self {
        Self {
            src: src.to_path_buf(),
        }
    }
}

impl PayloadSource for LocalPayload {
    fn materialize(&self, dest: &Path) -> Result<Vec<PathBuf>, WizardError> {
        Ok(merge_tree(&self.src, dest)?.written)
    }

    fn materialize_report(&self, dest: &Path) -> Result<MergeReport, WizardError> {
        merge_tree(&self.src, dest)
    }
}

/// Fetches `tepochcalli-workspace-<ver>.tar.gz` with SHA-256 verification
/// (URL + checksum are constructor inputs; T19 supplies the real values).
#[derive(Debug, Clone)]
pub struct ReleasePayload {
    url: String,
    expected_sha256: String,
}

impl ReleasePayload {
    /// Fetch `url`, fail unless its SHA-256 matches `expected_sha256`.
    #[must_use]
    pub fn new(url: &str, expected_sha256: &str) -> Self {
        Self {
            url: url.to_string(),
            expected_sha256: expected_sha256.to_string(),
        }
    }

    /// Release asset for an explicit version (one-version rule: callers pass
    /// the binary's own version, never `latest`).
    #[must_use]
    pub fn for_version(version: &str, expected_sha256: &str) -> Self {
        Self::new(&payload_asset_url(version), expected_sha256)
    }

    /// Release asset for this binary's own version (`CARGO_PKG_VERSION`):
    /// vX.Y.Z always installs payload vX.Y.Z (T19 AC-c).
    #[must_use]
    pub fn for_current_version(expected_sha256: &str) -> Self {
        Self::for_version(env!("CARGO_PKG_VERSION"), expected_sha256)
    }

    /// The asset URL this payload downloads (test seam for the one-version
    /// rule: requested version must equal the binary version).
    #[must_use]
    pub fn url(&self) -> &str {
        &self.url
    }

    /// Fail-closed sentinel (T8): the URL is unfetchable and the SHA matches
    /// nothing. The real asset comes from [`for_current_version`](Self::for_current_version).
    #[must_use]
    pub fn placeholder() -> Self {
        Self::new(
            RELEASE_ASSET_URL_PLACEHOLDER,
            RELEASE_ASSET_SHA256_PLACEHOLDER,
        )
    }

    /// `true` unless this is the fail-closed [`placeholder`](Self::placeholder).
    #[must_use]
    pub fn is_configured(&self) -> bool {
        self.url != RELEASE_ASSET_URL_PLACEHOLDER
            && self.expected_sha256 != RELEASE_ASSET_SHA256_PLACEHOLDER
    }

    fn stage_and_merge(&self, stage: &Path, dest: &Path) -> Result<MergeReport, WizardError> {
        let asset = stage.join("asset.tar.gz");
        UreqHttpClient::new().download(&self.url, &asset, &self.expected_sha256)?;
        let file = fs::File::open(&asset).map_err(|_| WizardError::PayloadCorrupt)?;
        let extract_outcome = extract_tar_gz(file, stage).map_err(|_| WizardError::PayloadCorrupt);
        // The asset file itself must not be merged into the vault.
        let _ = fs::remove_file(&asset);
        extract_outcome?;
        let report = merge_tree(stage, dest)?;
        // Best-effort: residue is harmless (T14 resume clears it).
        let _ = fs::remove_dir_all(stage);
        Ok(report)
    }
}

impl PayloadSource for ReleasePayload {
    fn materialize(&self, dest: &Path) -> Result<Vec<PathBuf>, WizardError> {
        Ok(self.materialize_report(dest)?.written)
    }

    fn materialize_report(&self, dest: &Path) -> Result<MergeReport, WizardError> {
        // Stage inside the vault: download (SHA-gated) → extract → merge →
        // remove stage, so a corrupt asset never touches the user's tree.
        // Any failure removes the stage again: rejection leaves the vault
        // exactly as it was (two-phase guarantee, same as `archive.rs`).
        let stage = dest.join(STAGE_DIR);
        reset_dir(&stage)?;
        let outcome = self.stage_and_merge(&stage, dest);
        if outcome.is_err() {
            let _ = fs::remove_dir_all(&stage);
            // Drop the runtime dir too if nothing else claimed it
            // (`remove_dir` only succeeds when empty — user files are safe).
            if let Some(parent) = stage.parent() {
                let _ = fs::remove_dir(parent);
            }
        }
        outcome
    }
}

/// Build the versioned payload from an already-fetched checksum sidecar
/// (pure: no network — the caller supplies the sidecar bytes).
pub fn release_payload_from_sidecar(
    version: &str,
    sidecar: &[u8],
) -> Result<ReleasePayload, WizardError> {
    Ok(ReleasePayload::for_version(
        version,
        &parse_sha256_sidecar(sidecar)?,
    ))
}

/// One-version online source: fetch the `<asset>.sha256` sidecar for
/// `version`, then download the asset SHA-gated. Unknown sidecar URL is
/// `NetDownload`; a bad sidecar or a SHA mismatch is `PayloadCorrupt`.
pub fn fetch_release_payload(
    http: &dyn HttpClient,
    version: &str,
) -> Result<ReleasePayload, WizardError> {
    let sidecar = http.get(&payload_checksum_url(version))?;
    release_payload_from_sidecar(version, &sidecar)
}

/// Empty `dir`, creating it (an interrupted F3 may leave a stale stage).
fn reset_dir(dir: &Path) -> Result<(), WizardError> {
    match fs::remove_dir_all(dir) {
        Ok(()) => {}
        Err(e) if e.kind() == ErrorKind::NotFound => {}
        Err(_) => return Err(WizardError::PermissionDenied),
    }
    fs::create_dir_all(dir).map_err(|_| WizardError::PermissionDenied)
}

fn map_io(error: std::io::Error) -> WizardError {
    if error.kind() == ErrorKind::PermissionDenied {
        WizardError::PermissionDenied
    } else {
        WizardError::DiskFull
    }
}

/// Join `rel` onto the canonical vault `root`; escape (defense-in-depth —
/// `rel` comes from a real walk so `..` cannot occur) is `PayloadCorrupt`.
fn join_checked(root: &Path, rel: &Path) -> Result<PathBuf, WizardError> {
    let target = root.join(rel);
    if target.starts_with(root) {
        Ok(target)
    } else {
        Err(WizardError::PayloadCorrupt)
    }
}

/// Merge the tree at `src` into `dest` without overwrite: pre-existing files
/// stay byte-intact (recorded in `skipped`), `.obsidian/` and symlinks never
/// cross, and every target is join-checked against the canonical `dest`.
// shortcut: unlinkable entries (sockets, fifos, devices) are skipped, never
// materialized; T14 owns the richer compensation policy.
pub fn merge_tree(src: &Path, dest: &Path) -> Result<MergeReport, WizardError> {
    fs::create_dir_all(dest).map_err(map_io)?;
    // Canonicalize once: every target below is checked against this root.
    let root = dest
        .canonicalize()
        .map_err(|_| WizardError::PermissionDenied)?;
    let mut report = MergeReport::default();
    let mut stack = vec![src.to_path_buf()];
    while let Some(dir) = stack.pop() {
        // Unreadable source (bad `--payload`, corrupt stage) is `PayloadCorrupt`,
        // same convention as the `FakePayload` T4 fake.
        let entries = fs::read_dir(&dir).map_err(|_| WizardError::PayloadCorrupt)?;
        for entry in entries {
            let entry = entry.map_err(|_| WizardError::PayloadCorrupt)?;
            let rel = entry
                .path()
                .strip_prefix(src)
                .map_err(|_| WizardError::PayloadCorrupt)?
                .to_path_buf();
            if rel
                .components()
                .next()
                .is_some_and(|c| c.as_os_str() == OBSIDIAN_DIR)
            {
                continue; // whole subtree skipped: its dirs are never pushed
            }
            let kind = entry.file_type().map_err(|_| WizardError::PayloadCorrupt)?;
            if kind.is_symlink() {
                report.skipped.push(root.join(&rel));
                continue;
            }
            if kind.is_dir() {
                let target = join_checked(&root, &rel)?;
                fs::create_dir_all(&target).map_err(map_io)?;
                stack.push(entry.path());
                continue;
            }
            if kind.is_file() {
                let target = join_checked(&root, &rel)?;
                if target.exists() {
                    report.skipped.push(target);
                } else {
                    if let Some(parent) = target.parent() {
                        fs::create_dir_all(parent).map_err(map_io)?;
                    }
                    fs::copy(entry.path(), &target).map_err(map_io)?;
                    report.written.push(target);
                }
                continue;
            }
            report.skipped.push(root.join(&rel));
        }
    }
    report.written.sort();
    report.skipped.sort();
    Ok(report)
}
