//! Architecture guard (T4): `src/domain/` is pure — no I/O, no adapters,
//! no third-party infra crates. Mirrors the Phase 1 Python guard
//! (`tests/unit/test_architecture.py`).
//!
//! Fails if any `src/domain/*.rs` line opens a forbidden `use`.
//! (T4 also asserted `src/adapters/` did not exist yet; T5 owns it now.)
//!
//! Also guards the test tier (`tests_layout_uses_tier_prefix` and friends):
//! the tier is readable from the filename, so a misfiled target fails here
//! instead of a reviewer's memory.
//!
//! `application_has_no_infra_imports` (L3-1): tras el git mv de
//! `archive.rs`/`fetch.rs` a `src/adapters/`, la capa de aplicación ya solo
//! puede alcanzar la infra vía el módulo `adapters` — nunca `use
//! crate::archive|fetch` (módulos que ya no existen) ni los crates de infra
//! (`ureq`, `tar`, `zip`, `flate2`) por su cuenta.

use std::path::{Path, PathBuf};

const FORBIDDEN_USE_PREFIXES: &[&str] = &[
    "use std::fs",
    "use std::process",
    "use std::net",
    "use crate::adapters",
    "use crate::archive",
    "use crate::fetch",
    "use crate::ports",
    "use tar",
    "use zip",
    "use flate2",
    "use sha2",
    "use ureq",
    "use sysinfo",
    "use dialoguer",
    "use clap",
];

fn manifest_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

/// `tests/*.rs` (Cargo's plain auto-discovered targets). `tests/common/` is
/// support code, not a target, so it is out of scope by construction.
fn test_targets() -> Vec<PathBuf> {
    let tests = manifest_dir().join("tests");
    let mut files = std::fs::read_dir(&tests)
        .expect("tests/ must exist")
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| p.is_file() && p.extension().is_some_and(|e| e == "rs"))
        .collect::<Vec<_>>();
    files.sort();
    files
}

fn file_name(path: &Path) -> String {
    path.file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_default()
}

/// `^(int|e2e)_[a-z0-9_]+\.rs$` without pulling in a regex dependency.
fn has_tier_prefix(name: &str) -> bool {
    let Some(stem) = name.strip_suffix(".rs") else {
        return false;
    };
    let topic = stem
        .strip_prefix("int_")
        .or_else(|| stem.strip_prefix("e2e_"));
    match topic {
        Some(topic) => {
            !topic.is_empty()
                && topic
                    .chars()
                    .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_')
        }
        None => false,
    }
}

/// Built at compile time so this file does not contain the marker it forbids.
/// El spawn compartido de los e2e vive en `tests/common/helpers.rs`; un fichero
/// que importa ese `bin` lanza un proceso aunque no construya el suyo.
const SPAWN_MARKERS: &[&str] = &[
    concat!("Command", "::new"),
    concat!("std::process", "::Command"),
    concat!("helpers", "::bin"),
];

#[test]
fn tests_layout_uses_tier_prefix() {
    let files = test_targets();
    assert!(!files.is_empty(), "tests/ must contain .rs targets");
    let offenders = files
        .iter()
        .map(|f| file_name(f))
        .filter(|name| !has_tier_prefix(name))
        .collect::<Vec<_>>();
    assert!(
        offenders.is_empty(),
        "every tests/*.rs must be `int_<topic>.rs` (no subprocess) or \
         `e2e_<topic>.rs` (spawns the binary or a shell script):\n{}",
        offenders.join("\n")
    );
}

#[test]
fn e2e_tests_spawn_a_process() {
    let offenders = test_targets()
        .iter()
        .filter(|f| file_name(f).starts_with("e2e_"))
        .filter(|f| {
            let src = std::fs::read_to_string(f).expect("test target readable");
            !SPAWN_MARKERS.iter().any(|m| src.contains(m))
        })
        .map(|f| file_name(f))
        .collect::<Vec<_>>();
    assert!(
        offenders.is_empty(),
        "e2e_*.rs must spawn a real process ({}); these do not — file them as int_*:\n{}",
        SPAWN_MARKERS.join(" or "),
        offenders.join("\n")
    );
}

#[test]
fn int_tests_do_not_spawn_a_process() {
    let offenders = test_targets()
        .iter()
        .filter(|f| file_name(f).starts_with("int_"))
        .filter(|f| {
            let src = std::fs::read_to_string(f).expect("test target readable");
            SPAWN_MARKERS.iter().any(|m| src.contains(m))
        })
        .map(|f| file_name(f))
        .collect::<Vec<_>>();
    assert!(
        offenders.is_empty(),
        "int_*.rs must stay in-process; these spawn a process — file them as e2e_*:\n{}",
        offenders.join("\n")
    );
}

#[test]
fn application_has_no_infra_imports() {
    // `src/application/` monta los puertos y puede importar `adapters`
    // (composition-root parcial: installer usa los extractores movidos),
    // pero los módulos de infra y sus crates quedan detrás de `crate::adapters`.
    let dir = manifest_dir().join("src").join("application");
    let files = std::fs::read_dir(&dir)
        .expect("src/application must exist")
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| p.extension().is_some_and(|e| e == "rs"))
        .collect::<Vec<_>>();
    assert!(!files.is_empty(), "src/application must contain .rs files");

    const FORBIDDEN: &[&str] = &[
        "use crate::archive",
        "use crate::fetch",
        "use ureq",
        "use tar",
        "use zip",
        "use flate2",
    ];
    let mut violations = Vec::new();
    for file in &files {
        let src = std::fs::read_to_string(file).expect("application file readable");
        for (n, line) in src.lines().enumerate() {
            let trimmed = line.trim_start();
            if FORBIDDEN.iter().any(|p| trimmed.starts_with(p)) {
                violations.push(format!(
                    "{}:{}: infra import escapes `adapters`: {}",
                    file.display(),
                    n + 1,
                    trimmed
                ));
            }
        }
    }
    assert!(
        violations.is_empty(),
        "application/ no import lamenaje infra directamente:\n{}",
        violations.join("\n")
    );
}

#[test]
fn domain_has_no_infra_imports() {
    let domain = manifest_dir().join("src").join("domain");
    let mut files = std::fs::read_dir(&domain)
        .expect("src/domain must exist")
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| p.extension().is_some_and(|e| e == "rs"))
        .collect::<Vec<_>>();
    files.sort();
    assert!(!files.is_empty(), "src/domain must contain .rs files");

    let mut violations = Vec::new();
    for file in &files {
        let src = std::fs::read_to_string(file).expect("domain file readable");
        for (n, line) in src.lines().enumerate() {
            let trimmed = line.trim_start();
            if FORBIDDEN_USE_PREFIXES
                .iter()
                .any(|p| trimmed.starts_with(p))
            {
                violations.push(format!(
                    "{}:{}: forbidden import: {}",
                    file.display(),
                    n + 1,
                    trimmed
                ));
            }
        }
    }
    assert!(
        violations.is_empty(),
        "domain/ must stay pure (no I/O, adapters, or infra crates):\n{}",
        violations.join("\n")
    );
}
