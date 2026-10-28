//! `tepochcalli` entrypoint: hand-rolled argv dispatch (no clap until T6).
//!
//! T3 skeleton: only `--help`/`--version` work; every real subcommand is a
//! stub that exits 40 (`WizardError::Internal` range, plan §5.4) until T7+.

use std::process::ExitCode;

use tepochcalli::adapters::{HeadlessUi, TtyUi};
use tepochcalli::domain::WizardError;
use tepochcalli::ports::Ui;

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
    if command == "install" {
        return "Usage: tepochcalli install [options]\n\
         \nOptions:\n  \
         --non-interactive  never prompt; a missing answer is a typed error\n  \
         --skip-model       preselect \"configure later\" (degraded, no index)\n  \
         --vault <ruta>     vault directory (asked interactively if omitted)\n  \
         --help     print this help\n  \
         --version  print the version\n"
            .to_string();
    }
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

/// `install` flag parsing (T6): only `--non-interactive`, `--skip-model`
/// and `--vault <ruta>` exist so far; the phases behind them land in T7+,
/// so a parsed invocation still ends in the exit-40 stub. The `Ui` backend
/// is chosen for real already: flags-derived [`HeadlessUi`] (never stdin)
/// vs. [`TtyUi`].
fn run_install(
    args: Vec<&str>,
    stdout: &mut dyn std::io::Write,
    stderr: &mut dyn std::io::Write,
) -> u8 {
    let mut non_interactive = false;
    let mut skip_model = false;
    let mut vault: Option<String> = None;
    let mut i = 0;
    while i < args.len() {
        match args[i] {
            "--help" => {
                print_help(stdout, Some("install"));
                return 0;
            }
            "--version" => {
                print_version(stdout);
                return 0;
            }
            "--non-interactive" => non_interactive = true,
            "--skip-model" => skip_model = true,
            "--vault" => {
                i += 1;
                match args.get(i) {
                    Some(value) => vault = Some((*value).to_string()),
                    None => {
                        let _ = writeln!(stderr, "install: --vault needs a value");
                        return 2;
                    }
                }
            }
            flag if flag.starts_with("--vault=") => {
                vault = Some(flag["--vault=".len()..].to_string());
            }
            flag => {
                let _ = writeln!(stderr, "install: unknown flag: {flag}");
                return 2;
            }
        }
        i += 1;
    }
    // Backend choice is real; the install itself is still a T7+ stub.
    let _ui: Box<dyn Ui> = if non_interactive {
        Box::new(HeadlessUi::for_install(skip_model, vault))
    } else {
        Box::new(TtyUi)
    };
    stub(stderr, "install")
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
        "install" => run_install(it.collect(), stdout, stderr),
        "reindex" | "uninstall" => match it.next() {
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
