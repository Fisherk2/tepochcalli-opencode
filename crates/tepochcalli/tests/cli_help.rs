//! CLI surface tests (T3): `--help`/`--version` per subcommand,
//! usage errors, and the T7+ "not yet implemented" stub behavior.

use std::process::{Command, Stdio};

fn bin() -> Command {
    Command::new(env!("CARGO_BIN_EXE_tepochcalli"))
}

fn stdout_text(output: &std::process::Output) -> String {
    String::from_utf8_lossy(&output.stdout).into_owned()
}

fn stderr_text(output: &std::process::Output) -> String {
    String::from_utf8_lossy(&output.stderr).into_owned()
}

#[test]
fn top_level_help_mentions_all_subcommands() {
    let out = bin().arg("--help").output().expect("spawn binary");
    assert_eq!(out.status.code(), Some(0));
    let text = stdout_text(&out);
    for sub in ["install", "config", "reindex", "uninstall"] {
        assert!(text.contains(sub), "help must mention `{sub}`:\n{text}");
    }
}

#[test]
fn top_level_version_reports_crate_version() {
    let out = bin().arg("--version").output().expect("spawn binary");
    assert_eq!(out.status.code(), Some(0));
    let text = stdout_text(&out);
    assert!(
        text.contains(env!("CARGO_PKG_VERSION")),
        "version must report crate version:\n{text}"
    );
}

#[test]
fn each_subcommand_supports_help_and_version() {
    for args in [
        vec!["install", "--help"],
        vec!["config", "--help"],
        vec!["reindex", "--help"],
        vec!["uninstall", "--help"],
        vec!["install", "--version"],
        vec!["config", "--version"],
        vec!["reindex", "--version"],
        vec!["uninstall", "--version"],
    ] {
        let out = bin().args(&args).output().expect("spawn binary");
        assert_eq!(out.status.code(), Some(0), "args {args:?} must exit 0");
    }
}

#[test]
fn config_without_subcommand_fails_with_usage() {
    let out = bin().arg("config").output().expect("spawn binary");
    assert!(
        out.status.code().unwrap_or(0) != 0,
        "`config` bare must exit non-zero"
    );
    let combined = stdout_text(&out) + &stderr_text(&out);
    assert!(
        combined.to_lowercase().contains("usage"),
        "`config` bare must print usage, got:\n{combined}"
    );
}

#[test]
fn unimplemented_stubs_exit_40_with_stderr_marker() {
    for args in [vec!["reindex"], vec!["uninstall"]] {
        let out = bin().args(&args).output().expect("spawn binary");
        assert_eq!(
            out.status.code(),
            Some(40),
            "args {args:?} must exit 40 (E_INTERNAL range)"
        );
        let err = stderr_text(&out);
        assert!(
            err.contains("not yet implemented"),
            "args {args:?} must print the stub marker on stderr, got:\n{err}"
        );
    }
}

#[test]
fn config_embedder_is_implemented_not_a_stub() {
    // T16: `--help` documents the real swap flags (no T3 stub marker).
    let out = bin()
        .args(["config", "embedder", "--help"])
        .output()
        .expect("spawn binary");
    assert_eq!(out.status.code(), Some(0));
    let text = stdout_text(&out);
    for flag in [
        "--vault",
        "--non-interactive",
        "--confirm",
        "--keep-previous",
    ] {
        assert!(text.contains(flag), "help must document `{flag}`:\n{text}");
    }
    // No TTY + no `--non-interactive` ⇒ typed abort (41), never a hang and
    // never the old stub. `Stdio::null` keeps this deterministic with or
    // without a terminal attached.
    let out = bin()
        .args(["config", "embedder"])
        .stdin(Stdio::null())
        .output()
        .expect("spawn binary");
    assert_eq!(out.status.code(), Some(41));
    assert!(
        !stderr_text(&out).contains("not yet implemented"),
        "the stub is gone; T16 owns this subcommand"
    );
    // `--non-interactive` without `--vault` ⇒ typed failure (missing answer
    // is never guessed), still on the failure-panel path.
    let out = bin()
        .args(["config", "embedder", "--non-interactive", "--confirm"])
        .stdin(Stdio::null())
        .output()
        .expect("spawn binary");
    assert!(
        out.status.code().unwrap_or(0) != 0,
        "`--non-interactive` without `--vault` must fail, not hang"
    );
}
