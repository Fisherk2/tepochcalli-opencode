//! One version: the wizard crate and the materialized payload cannot diverge.
//!
//! The H5 menu compares `CARGO_PKG_VERSION` against `.tepochcalli/pyproject.toml`,
//! so a bump in only one of them would show a wrong state forever.

use std::path::PathBuf;

fn payload_pyproject() -> String {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../obsidian-workspace/.tepochcalli/pyproject.toml");
    std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("{}: {e}", path.display()))
}

/// First `version = "…"` line: `[project]` is the only table carrying that key.
fn project_version(text: &str) -> String {
    text.lines()
        .find_map(|line| line.strip_prefix("version = \""))
        .and_then(|rest| rest.split('"').next())
        .map(str::to_string)
        .expect("pyproject without `version = \"…\"`")
}

#[test]
fn payload_version_matches_the_wizard() {
    assert_eq!(
        project_version(&payload_pyproject()),
        env!("CARGO_PKG_VERSION")
    );
}

#[test]
fn version_parses_with_the_wizard_comparator() {
    let raw = env!("CARGO_PKG_VERSION");
    let parsed = tepochcalli::domain::Version::parse(raw).expect("unparsable wizard version");
    assert_eq!(parsed.to_string(), raw);
}
