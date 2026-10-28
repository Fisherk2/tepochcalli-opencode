//! `tepochcalli` entrypoint: hand-rolled argv dispatch (no clap until T6).
//!
//! T3 skeleton: only `--help`/`--version` work; every real subcommand is a
//! stub that exits 40 (`WizardError::Internal` range, plan §5.4) until T7+.

use std::process::ExitCode;

use tepochcalli::domain::WizardError;

const VERSION: &str = env!("CARGO_PKG_VERSION");

/// Marker every stub prints on stderr (graded contract — keep exact).
const NOT_IMPLEMENTED: &str = "not yet implemented (T7+)";

fn usage_top() -> &'static str {
    "Usage: tepochcalli <command> [options]\n\
     \n\
     Commands:\n  \
     install            install a vault (T7+)\n  \
     config embedder    pick the embedding provider (T11+/T16)\n  \
     reindex            rebuild the index (T17)\n  \
     uninstall          remove the runtime (T17)\n\
     \n\
     Options:\n  \
     --help     print this help\n  \
     --version  print the version\n"
}

fn usage_for(command: &str) -> String {
    format!(
        "Usage: tepochcalli {command} [options]\n\
         \nOptions:\n  \
         --help     print this help\n  \
         --version  print the version\n"
    )
}

fn print_help(stdout: &mut dyn std::io::Write, command: Option<&str>) {
    match command {
        None => {
            let _ = stdout.write_all(usage_top().as_bytes());
        }
        Some(cmd) => {
            let _ = stdout.write_all(usage_for(cmd).as_bytes());
        }
    }
}

fn print_version(stdout: &mut dyn std::io::Write) {
    let _ = writeln!(stdout, "tepochcalli {VERSION}");
}

/// Stub for every unimplemented subcommand: stderr marker + exit 40.
fn stub(stderr: &mut dyn std::io::Write, command: &str) -> u8 {
    let _ = writeln!(stderr, "{command}: {NOT_IMPLEMENTED}");
    WizardError::Internal.exit_code()
}

fn unknown(stderr: &mut dyn std::io::Write, arg: &str) -> u8 {
    let _ = writeln!(stderr, "unknown subcommand: {arg}");
    let _ = stderr.write_all(usage_top().as_bytes());
    2
}

fn bare_config(stderr: &mut dyn std::io::Write) -> u8 {
    let _ = stderr.write_all(usage_top().as_bytes());
    let _ = writeln!(stderr, "Usage: tepochcalli config <embedder> [options]");
    2
}

/// Pure dispatch over argv (sans program name); returns the exit code.
fn run(args: &[String], stdout: &mut dyn std::io::Write, stderr: &mut dyn std::io::Write) -> u8 {
    let mut it = args.iter().map(String::as_str);
    let Some(first) = it.next() else {
        let _ = stderr.write_all(usage_top().as_bytes());
        return 2;
    };
    match first {
        "--help" => {
            print_help(stdout, None);
            0
        }
        "--version" => {
            print_version(stdout);
            0
        }
        "install" | "reindex" | "uninstall" => match it.next() {
            None => stub(stderr, first),
            Some("--help") => {
                print_help(stdout, Some(first));
                0
            }
            Some("--version") => {
                print_version(stdout);
                0
            }
            Some(flag) => {
                let _ = writeln!(stderr, "{first}: unknown flag: {flag}");
                2
            }
        },
        "config" => match it.next() {
            None => bare_config(stderr),
            Some("--help") => {
                print_help(stdout, Some("config"));
                0
            }
            Some("--version") => {
                print_version(stdout);
                0
            }
            Some("embedder") => match it.next() {
                None => stub(stderr, "config embedder"),
                Some("--help") => {
                    print_help(stdout, Some("config embedder"));
                    0
                }
                Some("--version") => {
                    print_version(stdout);
                    0
                }
                Some(flag) => {
                    let _ = writeln!(stderr, "config embedder: unknown flag: {flag}");
                    2
                }
            },
            Some(sub) => {
                let _ = writeln!(stderr, "config: unknown subcommand: {sub}");
                bare_config(stderr)
            }
        },
        other => unknown(stderr, other),
    }
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let code = run(&args, &mut std::io::stdout(), &mut std::io::stderr());
    if code != 0 {
        std::process::exit(code.into());
    }
    ExitCode::SUCCESS
}
