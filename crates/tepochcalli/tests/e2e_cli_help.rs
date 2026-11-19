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
    for sub in ["install", "update", "config", "reindex", "uninstall"] {
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
        vec!["update", "--help"],
        vec!["config", "--help"],
        vec!["reindex", "--help"],
        vec!["uninstall", "--help"],
        vec!["install", "--version"],
        vec!["update", "--version"],
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
fn uninstall_without_confirm_is_usage_error_not_stub() {
    // L4-3: bare `uninstall` es usage error (exit 2) — el gate `--confirm`
    // corre antes del check TTY (patrón reindex) y `Stdio::null` mantiene
    // el resultado determinista.
    let out = bin()
        .arg("uninstall")
        .stdin(Stdio::null())
        .output()
        .expect("spawn binary");
    assert_eq!(out.status.code(), Some(2));
    assert!(
        stderr_text(&out).contains("--confirm"),
        "bare `uninstall` debe explicar el flag, got:\n{}",
        stderr_text(&out)
    );
    assert!(
        !stderr_text(&out).contains("not yet implemented"),
        "the T7 stub is gone; T17 owns this subcommand"
    );

    // Con `--confirm` y sin TTY vuelve el abort tipado de siempre (41).
    let out = bin()
        .args(["uninstall", "--confirm"])
        .stdin(Stdio::null())
        .output()
        .expect("spawn binary");
    assert_eq!(out.status.code(), Some(41));
}

#[test]
fn empty_payload_override_values_are_a_usage_error_not_a_network_install() {
    // GAP 7: `--payload-url "$URL"` with an empty `$URL` (or `--payload ""`)
    // used to be filtered out as "flag absent", so the install silently fell
    // through to the versioned release asset — a network install born of a
    // shell typo. Empty must be a usage error (exit 2) instead.
    //
    // Mechanism proving "no HTTP client was ever constructed": the release
    // base points at a dead loopback port, so any fall-through can only end in
    // a network exit (20) or a typed failure — never 2 with this message. The
    // client is built later, inside `run_phases`, after F1/F2.
    let dir = tempfile::tempdir().expect("tempdir");
    let vault = dir.path().join("v");
    let vault = vault.to_str().expect("utf8 tmp");
    for (flag, args) in [
        ("--payload-url", vec!["--payload-url="]),
        ("--payload-url", vec!["--payload-url", ""]),
        ("--payload-sha256", vec!["--payload-sha256="]),
        ("--payload-sha256", vec!["--payload-sha256", ""]),
        ("--payload", vec!["--payload="]),
        ("--payload", vec!["--payload", ""]),
    ] {
        let out = bin()
            .args(["install", "--non-interactive", "--vault", vault])
            .args(&args)
            .env("TEPOCHCALLI_RELEASE_BASE_URL", "http://127.0.0.1:9")
            .output()
            .expect("spawn install");
        let err = stderr_text(&out);
        assert_eq!(
            out.status.code(),
            Some(2),
            "args {args:?} must be a usage error, stderr:\n{err}"
        );
        assert!(
            err.contains(flag),
            "the failure must name `{flag}` for {args:?}, got:\n{err}"
        );
        assert!(
            err.contains("empty"),
            "the failure must say the value is empty for {args:?}, got:\n{err}"
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
