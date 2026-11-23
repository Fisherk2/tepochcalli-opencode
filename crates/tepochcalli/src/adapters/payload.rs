//! F3 payload adapters (T8): [`LocalPayload`] copies a dev/test tree,
//! [`ReleasePayload`] fetches the versioned asset with SHA-256 and extracts
//! it. Both merge WITHOUT overwrite and never write outside the vault.
//!
//! Second Writing-Outside-Dir surface after T2 (`archive.rs`): the merge
//! itself is join-checked against the canonical vault, and payload symlinks
//! are never followed — only regular files are copied as plain files.

use std::fs;
use std::io::ErrorKind;
use std::path::{Component, Path, PathBuf};

use crate::adapters::archive::extract_tar_gz;
use crate::domain::{CancelToken, WizardError};
use crate::ports::{HttpClient, MergeReport, OverwriteJournal, PayloadSource};

use super::http::UreqHttpClient;

/// `.obsidian/` never crosses the merge, in either direction (user settings
/// win unconditionally; a payload copy would clobber them).
const OBSIDIAN_DIR: &str = ".obsidian";
/// Scratch dir for release extraction, inside the vault so no cross-device
/// move is needed; removed after the merge (best-effort).
const STAGE_DIR: &str = ".tepochcalli/.payload-stage";

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

/// Host de una URL form: `scheme://host[:port]/path`. Devuelve `""` cuando
/// no lo sabe parsear (los callers tratan lo desconocido como NO loopback).
fn host_of(url: &str) -> String {
    let rest = url.split_once("://").map(|(_, rest)| rest).unwrap_or(url);
    let authority = rest.split(['/', '?', '#']).next().unwrap_or_default();
    // IPv6 entre corchetes antes del split de port; bare host, port fuera.
    if let Some(stripped) = authority.strip_prefix('[') {
        return stripped.split(']').next().unwrap_or_default().to_string();
    }
    authority.split(':').next().unwrap_or_default().to_string()
}

/// `true` cuando el host de `url` es loopback (127.x/::1/localhost):
/// la única familia http PermitSpool sin confirmación (dev/tests — el
/// operador es el propio mirror).
#[must_use]
pub fn is_loopback_base(url: &str) -> bool {
    matches!(host_of(url).as_str(), "127.0.0.1" | "::1" | "localhost")
        || host_of(url).ends_with(".localhost")
}

/// `true` cuando la base pide http sin ser loopback: exigirá sesame
/// TUI antes del transporte (L4-2).
#[must_use]
pub fn mirror_http_non_loopback(url: &str) -> bool {
    url.split_once("://")
        .map(|(scheme, _)| scheme.eq_ignore_ascii_case("http"))
        .unwrap_or(false)
        && !is_loopback_base(url)
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
    fn materialize_report(&self, dest: &Path) -> Result<MergeReport, WizardError> {
        merge_tree(&self.src, dest)
    }

    fn materialize_overwrite(
        &self,
        dest: &Path,
        scopes: &[&str],
        journal: &mut OverwriteJournal,
        cancel: Option<&CancelToken>,
    ) -> Result<(), WizardError> {
        overwrite_tree(&self.src, dest, scopes, journal, cancel)
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

    fn stage_and_overwrite(
        &self,
        stage: &Path,
        dest: &Path,
        scopes: &[&str],
        journal: &mut OverwriteJournal,
        cancel: Option<&CancelToken>,
    ) -> Result<(), WizardError> {
        let asset = stage.join("asset.tar.gz");
        UreqHttpClient::new().download(&self.url, &asset, &self.expected_sha256)?;
        let file = fs::File::open(&asset).map_err(|_| WizardError::PayloadCorrupt)?;
        let extract_outcome = extract_tar_gz(file, stage).map_err(|_| WizardError::PayloadCorrupt);
        let _ = fs::remove_file(&asset);
        extract_outcome?;
        overwrite_tree(stage, dest, scopes, journal, cancel)?;
        // Best-effort: residue is harmless (T14 resume clears it).
        let _ = fs::remove_dir_all(stage);
        Ok(())
    }
}

impl PayloadSource for ReleasePayload {
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

    fn materialize_overwrite(
        &self,
        dest: &Path,
        scopes: &[&str],
        journal: &mut OverwriteJournal,
        cancel: Option<&CancelToken>,
    ) -> Result<(), WizardError> {
        let stage = dest.join(STAGE_DIR);
        reset_dir(&stage)?;
        let outcome = self.stage_and_overwrite(&stage, dest, scopes, journal, cancel);
        if outcome.is_err() {
            let _ = fs::remove_dir_all(&stage);
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
///
/// L4-2: el sidecar VA SIEMPRE del origin oficial de GitHub — un mirror
/// no puede aliñar el hash que decide la confianza (solo roerce el
/// transporte). La seam loopback queda (dev/tests: el mismo operador).
pub fn fetch_release_payload(
    http: &dyn HttpClient,
    version: &str,
) -> Result<ReleasePayload, WizardError> {
    let base = release_base_url();
    let sidecar = http.get(&sidecar_url_for(&base, version))?;
    release_payload_from_sidecar(version, &sidecar)
}

/// URL del sidecar SHA-256 para la base de release `base` (L4-2): SIEMPRE
/// del origin oficial de GitHub salvo base loopback (dev/tests — el mirror
/// no puede aliñar el hash que decide la confianza).
#[must_use]
pub fn sidecar_url_for(base: &str, version: &str) -> String {
    if is_loopback_base(base) {
        format!("{}.sha256", payload_asset_url_from(base, version))
    } else {
        format!(
            "https://github.com/{PAYLOAD_RELEASE_REPO}/releases/download/{}/{}.sha256",
            payload_release_tag(version),
            payload_asset_name(version)
        )
    }
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
    // `starts_with` is a component-prefix test, so `root/..` still passes it:
    // the escape is rejected at the component, not at the joined path.
    let has_escape = rel
        .components()
        .any(|c| !matches!(c, Component::Normal(_) | Component::CurDir));
    let target = root.join(rel);
    if has_escape || !target.starts_with(root) {
        Err(WizardError::PayloadCorrupt)
    } else {
        Ok(target)
    }
}

/// Rechaza cualquier componente de `rel` que ya exista como symlink bajo
/// `root`: `join_checked` es léxico y `fs::copy`/`create_dir_all` siguen
/// enlaces, así que un destino enlazado escribiría fuera del vault (L2-8).
fn reject_symlink_ancestors(root: &Path, rel: &Path) -> Result<(), WizardError> {
    let mut current = root.to_path_buf();
    for component in rel.components() {
        let Component::Normal(part) = component else {
            continue;
        };
        current.push(part);
        match fs::symlink_metadata(&current) {
            Ok(meta) if meta.file_type().is_symlink() => return Err(WizardError::PayloadCorrupt),
            Ok(_) => {}
            Err(err) if err.kind() == ErrorKind::NotFound => return Ok(()),
            Err(_) => return Err(WizardError::PayloadCorrupt),
        }
    }
    Ok(())
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
            // Lectura de la entrada SIN seguir enlaces (fs::symlink_metadata
            // bajo el path de la entrada): un symlink colgante llega aquí
            // como entrada y va por la rama de skip — nunca como "file" que
            // copy debería materializar, jamás fuera del vault (L2-8).
            let kind = std::fs::symlink_metadata(entry.path())
                .map_err(|_| WizardError::PayloadCorrupt)?
                .file_type();
            if kind.is_symlink() {
                report.skipped.push(root.join(&rel));
                continue;
            }
            if kind.is_dir() {
                let target = join_checked(&root, &rel)?;
                reject_symlink_ancestors(&root, &rel)?;
                fs::create_dir_all(&target).map_err(map_io)?;
                stack.push(entry.path());
                continue;
            }
            if kind.is_file() {
                let target = join_checked(&root, &rel)?;
                reject_symlink_ancestors(&root, &rel)?;
                if target.exists() {
                    report.skipped.push(target);
                } else {
                    if let Some(parent) = target.parent() {
                        fs::create_dir_all(parent).map_err(map_io)?;
                    }
                    fs::copy(entry.path(), &target).map_err(map_io)?;
                    // Si el walk muere después, este report se pierde: un
                    // parcial de F3 lo detecta la verificación de
                    // `rollback_install` contra el snapshot, no el intent.
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

/// `<ruta>.bak`: the byte backup taken before an overwrite (H7).
fn backup_path(target: &Path) -> PathBuf {
    let mut name = target.as_os_str().to_os_string();
    name.push(".bak");
    PathBuf::from(name)
}

/// `true` when both files hold the same bytes (idempotent update: an
/// unchanged file is neither rewritten nor backed up).
fn same_bytes(left: &Path, right: &Path) -> bool {
    // Lengths differ ⇒ contents differ: never read multi-GB files to see it.
    let len = |path: &Path| fs::metadata(path).map(|meta| meta.len()).ok();
    if len(left) != len(right) || len(left).is_none() {
        return false;
    }
    fs::read(left).is_ok_and(|a| fs::read(right).is_ok_and(|b| a == b))
}

/// Copy `src` over `root/rel`, saving the previous bytes as `<ruta>.bak`
/// and journaling both halves. Identical content is a no-op.
fn overwrite_file(
    src: &Path,
    root: &Path,
    rel: &Path,
    journal: &mut OverwriteJournal,
) -> Result<(), WizardError> {
    let target = join_checked(root, rel)?;
    reject_symlink_ancestors(root, rel)?;
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent).map_err(map_io)?;
    }
    if target.exists() {
        if same_bytes(src, &target) {
            return Ok(());
        }
        let backup = backup_path(&target);
        fs::copy(&target, &backup).map_err(map_io)?;
        journal.backed_up.push(target.clone());
    }
    // Journal BEFORE the copy: a copy that dies half-way still leaves the
    // partial deletable by `rollback_overwrite`.
    journal.written.push(target.clone());
    fs::copy(src, &target).map_err(map_io)?;
    Ok(())
}

/// Overwrite ONLY the entries under `scopes` (H7 `update`): every replaced
/// file is backed up as `<ruta>.bak` first, identical content is a no-op,
/// and nothing outside the scopes is even visited. Same defenses as
/// [`merge_tree`] (join-checked against the canonical `dest`, symlinks never
/// followed, `.obsidian/` never crossed). An error leaves `journal` with
/// what was already done, for [`rollback_overwrite`]. A cancelled `cancel`
/// aborts at the next entry with [`WizardError::UserAborted`] (journal intact,
/// rollback restores the bytes already replaced).
pub fn overwrite_tree(
    src: &Path,
    dest: &Path,
    scopes: &[&str],
    journal: &mut OverwriteJournal,
    cancel: Option<&CancelToken>,
) -> Result<(), WizardError> {
    fs::create_dir_all(dest).map_err(map_io)?;
    let root = dest
        .canonicalize()
        .map_err(|_| WizardError::PermissionDenied)?;
    let mut stack = vec![src.to_path_buf()];
    while let Some(dir) = stack.pop() {
        let entries = fs::read_dir(&dir).map_err(|_| WizardError::PayloadCorrupt)?;
        for entry in entries {
            if cancel.is_some_and(CancelToken::is_cancelled) {
                return Err(WizardError::UserAborted);
            }
            let entry = entry.map_err(|_| WizardError::PayloadCorrupt)?;
            let rel = entry
                .path()
                .strip_prefix(src)
                .map_err(|_| WizardError::PayloadCorrupt)?
                .to_path_buf();
            // Scope is the FIRST component, compared whole: `.opencode-evil/`
            // is not `.opencode/`, and everything else is ignored silently.
            let Some(Component::Normal(first)) = rel.components().next() else {
                continue;
            };
            if first == std::ffi::OsStr::new(OBSIDIAN_DIR)
                || !scopes
                    .iter()
                    .any(|scope| first == std::ffi::OsStr::new(scope))
            {
                continue;
            }
            let kind = fs::symlink_metadata(entry.path())
                .map_err(|_| WizardError::PayloadCorrupt)?
                .file_type();
            if kind.is_symlink() {
                continue; // never followed, never materialized
            }
            if kind.is_dir() {
                let target = join_checked(&root, &rel)?;
                reject_symlink_ancestors(&root, &rel)?;
                fs::create_dir_all(&target).map_err(map_io)?;
                stack.push(entry.path());
                continue;
            }
            if kind.is_file() {
                overwrite_file(&entry.path(), &root, &rel, journal)?;
            }
        }
    }
    Ok(())
}

/// Undo [`overwrite_tree`]: restore every `<ruta>.bak` over its original and
/// delete every written file that had no backup. Best-effort — a rollback
/// never panics on a vanished temp file.
// shortcut: directories created for new files stay (possibly empty) — the
// journal is file-scoped; upgrade only if an empty-dir residue ever matters.
pub fn rollback_overwrite(journal: &OverwriteJournal) {
    for original in &journal.backed_up {
        let backup = backup_path(original);
        // Keep the .bak when the restore failed: it is the last good copy.
        if fs::copy(&backup, original).is_ok() {
            let _ = fs::remove_file(&backup);
        }
    }
    for written in &journal.written {
        if !journal.backed_up.contains(written) {
            let _ = fs::remove_file(written);
        }
    }
}

#[cfg(test)]
mod tests {
    //! Tier 1: the asset names are the wire contract with `release.yml`, and
    //! `join_checked` is the private gate that keeps a payload entry inside the
    //! vault — both are unreachable or redundant from `tests/`.

    use super::{
        join_checked, overwrite_file, parse_sha256_sidecar, payload_asset_name,
        payload_asset_url_from, payload_checksum_name, payload_release_tag, release_base_url_from,
        PAYLOAD_RELEASE_REPO,
    };
    use crate::domain::WizardError;
    use std::path::{Path, PathBuf};

    const VERSION: &str = "0.3.0";

    #[test]
    fn asset_names_match_the_published_release() {
        // Exactly what `release.yml` uploads: no tag prefix on the file, tag
        // prefix on the release.
        assert_eq!(payload_release_tag(VERSION), "tepochcalli-v0.3.0");
        assert_eq!(
            payload_asset_name(VERSION),
            "tepochcalli-workspace-0.3.0.tar.gz"
        );
        assert_eq!(
            payload_checksum_name(VERSION),
            "tepochcalli-workspace-0.3.0.tar.gz.sha256"
        );
    }

    #[test]
    fn release_base_precedence_empty_counts_as_unset() {
        let default = format!("https://github.com/{PAYLOAD_RELEASE_REPO}/releases/download");
        assert_eq!(release_base_url_from(None), default);
        assert_eq!(release_base_url_from(Some("")), default);
        assert_eq!(release_base_url_from(Some("   ")), default);
        assert_eq!(
            release_base_url_from(Some(" http://127.0.0.1:1/dl/ ")),
            "http://127.0.0.1:1/dl",
            "an override is honoured with its edges trimmed"
        );
        assert_eq!(
            release_base_url_from(Some("https://mirror.test/dl///")),
            "https://mirror.test/dl",
            "every trailing slash goes, so the join cannot double it"
        );
    }

    #[test]
    fn asset_url_never_doubles_the_separator() {
        let expected =
            "https://mirror.test/dl/tepochcalli-v0.3.0/tepochcalli-workspace-0.3.0.tar.gz";
        for base in ["https://mirror.test/dl", "https://mirror.test/dl/"] {
            assert_eq!(payload_asset_url_from(base, VERSION), expected);
        }
    }

    #[test]
    fn sidecar_parser_accepts_both_documented_forms() {
        let hex = "a".repeat(64);
        for sidecar in [
            format!("{hex}  {}\n", payload_asset_name(VERSION)),
            format!("{hex} *{}\n", payload_asset_name(VERSION)),
            format!("{hex}\n"),
        ] {
            assert_eq!(
                parse_sha256_sidecar(sidecar.as_bytes()),
                Ok(hex.clone()),
                "valid sidecar must parse: {sidecar:?}"
            );
        }
    }

    #[test]
    fn sidecar_parser_rejects_garbage_as_payload_corrupt() {
        for bad in [
            String::new(),
            "\n".to_string(),
            "not-a-hash  asset.tar.gz\n".to_string(),
            format!("{}  asset.tar.gz\n", "0".repeat(63)),
            format!("{}  asset.tar.gz\n", "g".repeat(64)),
        ] {
            assert_eq!(
                parse_sha256_sidecar(bad.as_bytes()),
                Err(WizardError::PayloadCorrupt),
                "garbage must fail clean: {bad:?}"
            );
        }
        assert_eq!(
            parse_sha256_sidecar(&[0xff, 0xfe]),
            Err(WizardError::PayloadCorrupt),
            "non-UTF-8 sidecar must not panic"
        );
    }

    #[test]
    fn join_checked_builds_targets_inside_the_root() {
        let root = Path::new("/vault");
        assert_eq!(
            join_checked(root, Path::new("notes/day1.md")),
            Ok(PathBuf::from("/vault/notes/day1.md"))
        );
        assert_eq!(
            join_checked(root, Path::new("")),
            Ok(PathBuf::from("/vault"))
        );
    }

    #[test]
    fn join_checked_rejects_absolute_entries() {
        // An absolute entry replaces the root in `Path::join`; every variant
        // of it must map to `PayloadCorrupt`, never to a path outside the vault.
        let root = Path::new("/vault");
        for escape in ["/etc/passwd", "/vault-evil/x", "/"] {
            assert_eq!(
                join_checked(root, Path::new(escape)),
                Err(WizardError::PayloadCorrupt),
                "{escape} escapes the root"
            );
        }
    }

    #[test]
    fn join_checked_rejects_parent_dir_entries() {
        // `Path::join` keeps `..` as a component, so `root/..` still starts
        // with `root`: `starts_with` alone cannot see the escape.
        let root = Path::new("/vault");
        for escape in ["..", "../etc/passwd", "notes/../../etc/passwd"] {
            assert_eq!(
                join_checked(root, Path::new(escape)),
                Err(WizardError::PayloadCorrupt),
                "{escape} escapes the root"
            );
        }
    }

    /// Si el copy falla, el journal debe permitir a `rollback_overwrite`
    /// borrar el parcial: sin entrada, el fichero a medias (o el destino
    /// recién creado) quedaría huérfano tras un rollback de H7.
    #[test]
    fn overwrite_file_journals_the_target_before_copying() {
        let Ok(root) = tempfile::tempdir() else {
            panic!("tempdir");
        };
        let missing = root.path().join("no-existe.md");
        let mut journal = crate::ports::OverwriteJournal::default();

        let outcome = overwrite_file(&missing, root.path(), Path::new("x.md"), &mut journal);

        assert!(outcome.is_err(), "copiar un src inexistente falla");
        assert_eq!(
            journal.written,
            vec![root.path().join("x.md")],
            "el destino entra al journal ANTES del copy"
        );
    }

    #[test]
    fn overwrite_file_rejects_escape_entries() {
        // Escritura: un `rel` con `..` (inalcanzable desde un walk real, pero
        // defensa en profundidad) jamás escribe fuera del vault.
        let src = std::env::temp_dir().join("tepochcalli-overwrite-escape");
        let _ = std::fs::remove_dir_all(&src);
        std::fs::create_dir_all(&src).expect("src fixture");
        std::fs::write(src.join("evil.md"), b"x").expect("fixture write");
        let root = std::env::temp_dir().join("tepochcalli-overwrite-root");
        std::fs::create_dir_all(&root).expect("root fixture");
        let mut journal = crate::ports::OverwriteJournal::default();
        for rel in ["../evil.md", "/etc/passwd"] {
            assert_eq!(
                overwrite_file(&src.join("evil.md"), &root, Path::new(rel), &mut journal),
                Err(WizardError::PayloadCorrupt),
                "{rel} escapes the vault"
            );
        }
        assert!(journal.written.is_empty() && journal.backed_up.is_empty());
        let _ = std::fs::remove_dir_all(&src);
        let _ = std::fs::remove_dir_all(&root);
    }
}
