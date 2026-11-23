//! Helpers de fixtures y del binario compartidos por los targets (T19).
//!
//! `common/` no es un target de Cargo: el guard `int_architecture` no lo ve.

use std::path::Path;
use std::process::{Command, Output};

use sha2::Digest as _;

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
