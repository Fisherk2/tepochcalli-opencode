//! Architecture guard (T4): `src/domain/` is pure — no I/O, no adapters,
//! no third-party infra crates. Mirrors the Phase 1 Python guard
//! (`tests/unit/test_architecture.py`).
//!
//! Fails if any `src/domain/*.rs` line opens a forbidden `use`, and fails if
//! `src/adapters/` exists (T5 owns it).

use std::path::PathBuf;

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

#[test]
fn adapters_dir_does_not_exist_yet() {
    // T5 owns `src/adapters/`; T4 must not create it.
    assert!(
        !manifest_dir().join("src").join("adapters").exists(),
        "src/adapters/ belongs to T5 and must not exist in T4"
    );
}
