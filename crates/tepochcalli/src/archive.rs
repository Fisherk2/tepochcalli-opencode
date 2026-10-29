//! OM-1 spike: extract `.tar.gz` / `.zip` with path-traversal defense.
//!
//! Two-phase design: phase 1 validates EVERY member (name + link target)
//! and buffers file bytes; phase 2 writes. A rejection therefore happens
//! BEFORE any disk write, so the destination stays intact.

use std::fs;
use std::io::{self, Read, Seek};
use std::path::{Component, Path, PathBuf};

use thiserror::Error;

#[derive(Debug, Error)]
pub enum ArchiveError {
    /// Bomba (L2-2): un miembro/total supera el cap defensivo.
    #[error("decompression bomb guard: member {member} exceeds the extraction cap")]
    TooLarge { member: String },
    #[error("member escapes destination: {member}")]
    Traversal { member: String },
    #[error("absolute member path rejected: {member}")]
    AbsolutePath { member: String },
    #[error("windows member path rejected: {member}")]
    WindowsPath { member: String },
    #[error("unsafe symlink {member} -> {target}")]
    UnsafeSymlink { member: String, target: String },
    #[error("unsupported entry {member}: {kind}")]
    UnsupportedEntry { member: String, kind: String },
    #[error("invalid member name (non-UTF8 or NUL)")]
    BadName,
    #[error("symlinks not supported on this platform")]
    SymlinksUnsupported,
    #[error(transparent)]
    Io(#[from] io::Error),
    #[error(transparent)]
    Zip(#[from] zip::result::ZipError),
}

/// Backslash is a separator on Windows, so any `\` makes a member name
/// platform-ambiguous (`..\x` escapes there). Our payloads never contain
/// it, so reject outright rather than guessing the author's OS.
fn is_windows_path(raw: &str) -> bool {
    raw.contains('\\')
        || raw
            .as_bytes()
            .first()
            .is_some_and(|b| b.is_ascii_alphabetic())
            && raw.as_bytes().get(1) == Some(&b':')
}

/// Shared gate for tar and zip member names: rejects `..`, absolute POSIX
/// paths and Windows paths BEFORE anything is written.
pub fn validate_member(raw: &str) -> Result<PathBuf, ArchiveError> {
    if raw.is_empty() || raw.contains('\0') {
        return Err(ArchiveError::BadName);
    }
    if is_windows_path(raw) {
        return Err(ArchiveError::WindowsPath {
            member: raw.to_string(),
        });
    }
    let path = Path::new(raw);
    if path.is_absolute() {
        return Err(ArchiveError::AbsolutePath {
            member: raw.to_string(),
        });
    }
    let mut out = PathBuf::new();
    for component in path.components() {
        match component {
            Component::Prefix(_) | Component::RootDir => {
                return Err(ArchiveError::AbsolutePath {
                    member: raw.to_string(),
                });
            }
            Component::ParentDir => {
                return Err(ArchiveError::Traversal {
                    member: raw.to_string(),
                });
            }
            Component::CurDir => {}
            Component::Normal(part) => out.push(part),
        }
    }
    Ok(out)
}

/// Validate a symlink/hardlink target without touching the filesystem:
/// absolute targets rejected, `..` resolved lexically against the member's
/// parent dir, escape (popping above dest root) rejected.
/// Returns the target resolved relative to the dest root (for hardlinks).
fn validate_link_target(member_rel: &Path, target_raw: &str) -> Result<PathBuf, ArchiveError> {
    let bad = |member: &Path| ArchiveError::UnsafeSymlink {
        member: member.display().to_string(),
        target: target_raw.to_string(),
    };
    if target_raw.is_empty() || target_raw.contains('\0') {
        return Err(bad(member_rel));
    }
    if is_windows_path(target_raw) || Path::new(target_raw).is_absolute() {
        return Err(bad(member_rel));
    }
    let target = Path::new(target_raw);
    if target.to_str().is_none() {
        return Err(bad(member_rel));
    }
    // Lexical resolve: member's parent dir + target, `..` pops one level.
    let mut stack: Vec<&str> = Vec::new();
    let base: PathBuf = member_rel
        .parent()
        .map_or_else(PathBuf::new, Path::to_path_buf);
    let joined = base.join(target);
    for component in joined.components() {
        match component {
            Component::Normal(part) => match part.to_str() {
                Some(s) => stack.push(s),
                None => return Err(bad(member_rel)),
            },
            Component::CurDir => {}
            Component::ParentDir => {
                stack.pop().ok_or_else(|| bad(member_rel))?;
            }
            Component::Prefix(_) | Component::RootDir => {
                return Err(bad(member_rel));
            }
        }
    }
    Ok(stack.iter().collect())
}

enum Action {
    Dir(PathBuf),
    File(PathBuf, Vec<u8>),
    Symlink(PathBuf, String),
    Hardlink(PathBuf, PathBuf),
}

/// Cap por miembro: un header mints sobre `size` y no dicta la asignación.
/// Los payloads reales (uv, workspace) tienen miembros de decenas de MB;
/// 512 MiB deja margen x10 por cannon.
const MAX_MEMBER_BYTES: u64 = 512 * 1024 * 1024;
/// Cap del total extraído (defense-in-depth, L2-9): 2 GiB por corrida.
const MAX_TOTAL_BYTES: u64 = 2 * 1024 * 1024 * 1024;

/// Cap for a single member's in-memory buffer: a corrupt `size` header must
/// not dictate allocation (decompression-bomb guard).
const MAX_BUFFER_PREALLOC: u64 = 8 * 1024 * 1024;

/// Cap de RAM: chunked read con abort al vencer el cap (un miembro mayor no
/// compone una asignación del tamaño del cap); el chequeo de quedan-bytes es
/// el `buf.len() > cap` posterior (take no se come el excedente).
fn buffered_read<R: Read>(reader: R, hint: u64, member: &str) -> Result<Vec<u8>, ArchiveError> {
    let mut buf = Vec::with_capacity(hint.min(MAX_BUFFER_PREALLOC) as usize);
    let mut limited = reader.take(MAX_MEMBER_BYTES + 1);
    let mut chunk = [0u8; 1 << 16];
    loop {
        let n = limited.read(&mut chunk)?;
        if n == 0 {
            break;
        }
        // Check de sobre-salto ANTES de extender: el buffer nunca llega al
        // cap en la rama de ataque (nunca OOM por cabecera mentirosa).
        if buf.len() as u64 + n as u64 > MAX_MEMBER_BYTES {
            return Err(ArchiveError::TooLarge {
                member: member.to_string(),
            });
        }
        buf.extend_from_slice(&chunk[..n]);
    }
    Ok(buf)
}

fn apply_actions(dest: &Path, actions: Vec<Action>) -> Result<(), ArchiveError> {
    for action in actions {
        match action {
            Action::Dir(path) => fs::create_dir_all(path)?,
            Action::File(path, bytes) => {
                if let Some(parent) = path.parent() {
                    fs::create_dir_all(parent)?;
                }
                fs::write(path, bytes)?;
            }
            Action::Symlink(path, target) => {
                if let Some(parent) = path.parent() {
                    fs::create_dir_all(parent)?;
                }
                #[cfg(unix)]
                std::os::unix::fs::symlink(&target, &path)?;
                #[cfg(not(unix))]
                {
                    let _ = (&target, &path);
                    return Err(ArchiveError::SymlinksUnsupported);
                }
            }
            Action::Hardlink(path, resolved) => {
                if let Some(parent) = path.parent() {
                    fs::create_dir_all(parent)?;
                }
                fs::hard_link(dest.join(resolved), path)?;
            }
        }
    }
    Ok(())
}

/// Extract a `.tar.gz` stream into `dest` (must exist). Validates the whole
/// archive before writing anything.
pub fn extract_tar_gz<R: Read>(reader: R, dest: &Path) -> Result<(), ArchiveError> {
    let gz = flate2::read::GzDecoder::new(reader);
    let mut archive = tar::Archive::new(gz);
    let mut actions = Vec::new();
    let mut total_bytes = 0u64;
    for entry in archive.entries()? {
        let mut entry = entry?;
        let raw = entry.path()?.into_owned();
        let raw_str = raw.to_str().ok_or(ArchiveError::BadName)?;
        let rel = validate_member(raw_str)?;
        let out = dest.join(&rel);
        let kind = entry.header().entry_type();
        if kind.is_dir() {
            actions.push(Action::Dir(out));
        } else if kind.is_file() {
            if rel.as_os_str().is_empty() {
                return Err(ArchiveError::BadName);
            }
            let size = entry.header().size()?;
            let bytes = buffered_read(&mut entry, size, raw_str)?;
            total_bytes += bytes.len() as u64;
            if total_bytes > MAX_TOTAL_BYTES {
                return Err(ArchiveError::TooLarge {
                    member: raw_str.to_string(),
                });
            }
            actions.push(Action::File(out, bytes));
        } else if kind.is_symlink() {
            let target = entry.link_name()?.ok_or(ArchiveError::BadName)?;
            let target_str = target.to_str().ok_or(ArchiveError::BadName)?;
            validate_link_target(&rel, target_str)?;
            if rel.as_os_str().is_empty() {
                return Err(ArchiveError::BadName);
            }
            actions.push(Action::Symlink(out, target_str.to_string()));
        } else if kind.is_hard_link() {
            let target = entry.link_name()?.ok_or(ArchiveError::BadName)?;
            let target_str = target.to_str().ok_or(ArchiveError::BadName)?;
            let resolved = validate_link_target(&rel, target_str)?;
            actions.push(Action::Hardlink(out, resolved));
        } else {
            // Device nodes, fifos, sockets: never materialize from a payload.
            return Err(ArchiveError::UnsupportedEntry {
                member: raw_str.to_string(),
                kind: format!("{kind:?}"),
            });
        }
    }
    apply_actions(dest, actions)
}

/// Extract a `.zip` stream into `dest` (must exist). Same two-phase guarantee.
pub fn extract_zip<R: Read + Seek>(reader: R, dest: &Path) -> Result<(), ArchiveError> {
    let mut archive = zip::ZipArchive::new(reader)?;
    let mut actions = Vec::new();
    let mut total_bytes = 0u64;
    for i in 0..archive.len() {
        let mut file = archive.by_index(i)?;
        let name = file.name().to_string();
        let rel = validate_member(&name)?;
        let out = dest.join(&rel);
        if file.is_dir() {
            actions.push(Action::Dir(out));
        } else if file.is_symlink() {
            let mut target = String::new();
            file.read_to_string(&mut target)
                .map_err(|_| ArchiveError::UnsafeSymlink {
                    member: name.clone(),
                    target: String::from("<unreadable>"),
                })?;
            validate_link_target(&rel, &target)?;
            if rel.as_os_str().is_empty() {
                return Err(ArchiveError::BadName);
            }
            actions.push(Action::Symlink(out, target));
        } else {
            if rel.as_os_str().is_empty() {
                return Err(ArchiveError::BadName);
            }
            let size = file.size();
            let bytes = buffered_read(&mut file, size, &name)?;
            total_bytes += bytes.len() as u64;
            if total_bytes > MAX_TOTAL_BYTES {
                return Err(ArchiveError::TooLarge {
                    member: name.clone(),
                });
            }
            actions.push(Action::File(out, bytes));
        }
    }
    apply_actions(dest, actions)
}
