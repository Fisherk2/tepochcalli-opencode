//! CLI surface tests (T3): `--help`/`--version` per subcommand,
//! usage errors, and the T17 ownership of `reindex`/`uninstall`
//! (the old T7+ stubs are gone: each explains its own usage now).

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
fn reindex_without_confirm_is_usage_error_not_stub() {
    // T17: bare `reindex` is a usage error (exit 2), never the old stub.
    // The `--confirm` gate runs before any TTY check, so no stdin setup is
    // needed for a deterministic result.
    let out = bin().arg("reindex").output().expect("spawn binary");
    assert_eq!(
        out.status.code(),
        Some(2),
        "bare `reindex` must exit 2 (needs --confirm)"
    );
    let err = stderr_text(&out);
    assert!(
        err.contains("--confirm"),
        "bare `reindex` must explain the missing flag, got:\n{err}"
    );
    assert!(
        !err.contains("not yet implemented"),
        "the T7 stub is gone; T17 owns this subcommand"
    );
}

#[test]
fn uninstall_without_tty_is_typed_abort_not_stub() {
    // T17: bare `uninstall` with no TTY is a typed abort (41), never a hang
    // and never the old stub. `Stdio::null` keeps this deterministic with or
    // without a terminal attached.
    let out = bin()
        .arg("uninstall")
        .stdin(Stdio::null())
        .output()
        .expect("spawn binary");
    assert_eq!(out.status.code(), Some(41));
    assert!(
        !stderr_text(&out).contains("not yet implemented"),
        "the T7 stub is gone; T17 owns this subcommand"
    );
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
