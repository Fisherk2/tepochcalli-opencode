//! Helpers de fixtures y del binario compartidos por los targets (T19).
//!
//! `common/` no es un target de Cargo: el guard `int_architecture` no lo ve.

use std::path::Path;
use std::process::{Command, Output};

use sha2::Digest as _;

/// `true` bajo root en Linux (`/proc/self/status`): los tests que dependen de
/// que `0o555` impida borrar deben saltarse. Sin dependencias nuevas.
pub fn running_as_root() -> bool {
    std::fs::read_to_string("/proc/self/status")
        .ok()
        .and_then(|s| s.lines().find(|l| l.starts_with("Uid:")).map(str::to_owned))
        .and_then(|l| l.split_whitespace().nth(1).map(str::to_owned))
        .is_some_and(|uid| uid == "0")
}

/// Hash hex SHA-256 de `bytes` (fixtures de payload/checksum).
pub fn sha256_hex(bytes: &[u8]) -> String {
    format!("{:x}", sha2::Sha256::digest(bytes))
}

/// Binario real del wizard para los e2e.
pub fn bin() -> Command {
    Command::new(env!("CARGO_BIN_EXE_tepochcalli"))
}

pub fn stdout_text(output: &Output) -> String {
    String::from_utf8_lossy(&output.stdout).into_owned()
}

pub fn stderr_text(output: &Output) -> String {
    String::from_utf8_lossy(&output.stderr).into_owned()
}

/// Escribe `body` en `root/rel`, creando los padres.
pub fn write_rel(root: &Path, rel: &str, body: &str) {
    let path = root.join(rel);
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).expect("fixture parent dir");
    }
    std::fs::write(path, body).expect("fixture write");
}

/// Escribe `body` en `path`, creando los padres.
pub fn write_path(path: &Path, body: &str) {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).expect("fixture parents");
    }
    std::fs::write(path, body).expect("fixture write");
}

/// Texto plano del buffer de ratatui (filas unidas por '\n').
pub fn buffer_text(buffer: &ratatui::buffer::Buffer) -> String {
    let area = buffer.area();
    (area.top()..area.bottom())
        .map(|y| {
            (area.left()..area.right())
                .map(|x| {
                    buffer
                        .cell((x, y))
                        .and_then(|cell| cell.symbol().chars().next())
                        .unwrap_or(' ')
                })
                .collect::<String>()
        })
        .collect::<Vec<_>>()
        .join("\n")
}
