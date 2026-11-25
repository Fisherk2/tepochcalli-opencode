//! T19: borrado bottom-up de un scope de H8 con paralelismo acotado y `std`
//! exclusivamente. Módulo profundo: una única entrada pública ([`remove_scope`])
//! esconde el recorrido, la verificación de frontera, la cola de workers y los
//! contadores. Nunca sigue symlinks: canonicaliza el directorio padre y usa
//! `DirEntry::file_type()`; el destino de un enlace jamás se canoniza.
//!
//! `std::fs::canonicalize` + `starts_with(vault)` acotan cada directorio que se
//! va a vaciar. Los hijos se construyen como `directorio_canónico.join(nombre)`
//! (un solo componente), así que ninguna entrada puede escapar del vault.

use std::collections::VecDeque;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Mutex, PoisonError};

use crate::domain::{CancelToken, WizardError};

use super::maintenance::{map_fs, Removal};

/// Techo de workers por fase (decisión T19; sin dependencias).
const WORKERS: usize = 8;

#[derive(Clone, Copy)]
enum Op {
    File,
    Dir,
}

/// Borra `scope` (directorio bajo `vault`) sin seguir symlinks. `NotFound` es
/// no-op; un fichero corrupted en lugar de directorio falla tipado. Cualquier
/// error de worker se propaga: nunca se informa éxito parcial.
pub fn remove_scope(
    vault: &Path,
    scope: &Path,
    cancel: &CancelToken,
) -> Result<Removal, WizardError> {
    let kind = match std::fs::symlink_metadata(scope) {
        Ok(metadata) => metadata.file_type(),
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => return Ok(Removal::default()),
        Err(err) => return Err(map_fs(err)),
    };
    if !kind.is_dir() {
        return Err(WizardError::PermissionDenied);
    }
    let vault_root = vault.canonicalize().map_err(map_fs)?;
    let root = scope.canonicalize().map_err(map_fs)?;
    if !root.starts_with(&vault_root) {
        return Err(WizardError::PermissionDenied);
    }

    let (mut files, mut dirs) = (Vec::new(), Vec::new());
    collect(&root, &vault_root, 0, cancel, &mut files, &mut dirs)?;
    files.sort();
    dirs.sort_by(|a, b| b.0.cmp(&a.0).then_with(|| a.1.cmp(&b.1)));

    let mut total = accumulate(Removal::default(), run_batch(&files, Op::File, cancel)?);
    let mut start = 0;
    while start < dirs.len() {
        let depth = dirs[start].0;
        let end = dirs[start..]
            .iter()
            .position(|(entry_depth, _)| *entry_depth != depth)
            .map_or(dirs.len(), |offset| start + offset);
        // Los niveles más profundos se vacían primero: ningún `remove_dir`
        // ve un hijo vivo, aunque los workers corran en paralelo en el nivel.
        let level: Vec<PathBuf> = dirs[start..end]
            .iter()
            .map(|(_, path)| path.clone())
            .collect();
        total = accumulate(total, run_batch(&level, Op::Dir, cancel)?);
        start = end;
    }
    match std::fs::remove_dir(&root) {
        Ok(()) => total.entries_removed += 1,
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => {}
        Err(err) => return Err(map_fs(err)),
    }
    Ok(total)
}

/// Recorrido previo (un solo hilo): clasifica rutas Canónicas y comprueba la
/// frontera antes de que cualquier worker desvincule algo.
fn collect(
    dir: &Path,
    vault_root: &Path,
    depth: usize,
    cancel: &CancelToken,
    files: &mut Vec<PathBuf>,
    dirs: &mut Vec<(usize, PathBuf)>,
) -> Result<(), WizardError> {
    let canonical = match dir.canonicalize() {
        Ok(path) => path,
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Err(err) => return Err(map_fs(err)),
    };
    if !canonical.starts_with(vault_root) {
        return Err(WizardError::PermissionDenied);
    }
    let entries = match std::fs::read_dir(&canonical) {
        Ok(entries) => entries,
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Err(err) => return Err(map_fs(err)),
    };
    for entry in entries {
        if cancel.is_cancelled() {
            return Err(WizardError::UserAborted);
        }
        let entry = entry.map_err(map_fs)?;
        let path = canonical.join(entry.file_name());
        if !path.starts_with(vault_root) {
            return Err(WizardError::PermissionDenied);
        }
        // `file_type`, NUNCA `metadata`: un symlink a directorio se desvincula
        // como fichero y su destino (puede estar fuera del vault) no se toca.
        if entry.file_type().map_err(map_fs)?.is_dir() {
            dirs.push((depth + 1, path.clone()));
            collect(&path, vault_root, depth + 1, cancel, files, dirs)?;
        } else {
            files.push(path);
        }
    }
    Ok(())
}

/// Una cola compartida por `min(8, paths.len())` workers scoped. La barrera
/// implícita al cerrar el `thread::scope` garantiza que la siguiente fase no
/// empiece hasta que todas las entradas de ésta estén resueltas.
fn run_batch(paths: &[PathBuf], op: Op, cancel: &CancelToken) -> Result<Removal, WizardError> {
    if paths.is_empty() {
        return Ok(Removal::default());
    }
    let workers = WORKERS.min(paths.len());
    let queue = Mutex::new(VecDeque::from(paths.to_vec()));
    let removed = AtomicU64::new(0);
    let failed = AtomicBool::new(false);
    let error: Mutex<Option<WizardError>> = Mutex::new(None);

    std::thread::scope(|scope| {
        for _ in 0..workers {
            scope.spawn(|| loop {
                if cancel.is_cancelled() {
                    record(&error, &failed, WizardError::UserAborted);
                    break;
                }
                if failed.load(Ordering::Relaxed) {
                    break;
                }
                let Some(path) = queue
                    .lock()
                    .unwrap_or_else(PoisonError::into_inner)
                    .pop_front()
                else {
                    break;
                };
                let outcome = match op {
                    Op::File => std::fs::remove_file(&path),
                    Op::Dir => std::fs::remove_dir(&path),
                };
                match outcome {
                    Ok(()) => {
                        removed.fetch_add(1, Ordering::Relaxed);
                    }
                    Err(err) if err.kind() == std::io::ErrorKind::NotFound => {}
                    Err(err) => {
                        record(&error, &failed, map_fs(err));
                        break;
                    }
                }
            });
        }
    });

    match error.into_inner().unwrap_or_else(PoisonError::into_inner) {
        Some(err) => Err(err),
        None => Ok(Removal {
            entries_removed: removed.load(Ordering::Relaxed),
            workers_used: workers,
        }),
    }
}

fn record(error: &Mutex<Option<WizardError>>, failed: &AtomicBool, err: WizardError) {
    *error.lock().unwrap_or_else(PoisonError::into_inner) = Some(err);
    failed.store(true, Ordering::Relaxed);
}

fn accumulate(total: Removal, batch: Removal) -> Removal {
    Removal {
        entries_removed: total.entries_removed + batch.entries_removed,
        workers_used: total.workers_used.max(batch.workers_used),
    }
}
