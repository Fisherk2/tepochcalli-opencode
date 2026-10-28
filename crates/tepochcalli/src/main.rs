//! `tepochcalli` entrypoint: hand-rolled argv dispatch (no clap until T6).
//!
//! `install` runs F1→F2 for real (T7) + F3 payload merge (T8); every other
//! subcommand is still a stub that exits 40 (`WizardError::Internal` range,
//! plan §5.4) until its task.

use std::io::IsTerminal;
use std::path::Path;
use std::process::ExitCode;

use tepochcalli::adapters::{HeadlessUi, LocalPayload, SysHostProbe, TtyUi};
use tepochcalli::application::{check_prereqs, ensure_vault_dir, resolve_vault_dir, run_phase3};
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
         --payload <ruta>   payload tree to merge (dev/tests; required until T19)\n  \
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

/// `install` flag parsing (T6) + F1→F2 execution (T7) + F3 merge (T8):
/// `--non-interactive`, `--skip-model`, `--vault <ruta>` and
/// `--payload <ruta>` select the [`HeadlessUi`] answers (never stdin) vs.
/// [`TtyUi`]; then F1 gates prereqs, F2 ensures the vault dir, F3 merges
/// the payload. Without `--payload` (and no release URL configured yet —
/// T19 wires the asset) install stops here with exit 2 (CLI usage error,
/// same class as `--vault` without a value).
fn run_install(
    args: Vec<&str>,
    stdout: &mut dyn std::io::Write,
    stderr: &mut dyn std::io::Write,
) -> u8 {
    let mut non_interactive = false;
    let mut skip_model = false;
    let mut vault: Option<String> = None;
    let mut payload: Option<String> = None;
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
            "--payload" => {
                i += 1;
                match args.get(i) {
                    Some(value) => payload = Some((*value).to_string()),
                    None => {
                        let _ = writeln!(stderr, "install: --payload needs a value");
                        return 2;
                    }
                }
            }
            flag if flag.starts_with("--vault=") => {
                vault = Some(flag["--vault=".len()..].to_string());
            }
            flag if flag.starts_with("--payload=") => {
                payload = Some(flag["--payload=".len()..].to_string());
            }
            flag => {
                let _ = writeln!(stderr, "install: unknown flag: {flag}");
                return 2;
            }
        }
        i += 1;
    }
    // T6 rule: no TTY means no prompts — fail fast instead of hanging or
    // resolving the default dir under an unintended cwd.
    if !non_interactive && !std::io::stdin().is_terminal() {
        let _ = writeln!(
            stderr,
            "install: no TTY detected; re-run with --non-interactive (and --vault <ruta>)"
        );
        return WizardError::UserAborted.exit_code();
    }
    let ui: Box<dyn Ui> = if non_interactive {
        Box::new(HeadlessUi::for_install(skip_model, vault.clone()))
    } else {
        Box::new(TtyUi)
    };
    // F1: prerequisites (RAM/disk/platform gate; missing tools only warn).
    let report = match check_prereqs(&SysHostProbe) {
        Ok(report) => report,
        Err(err) => {
            let _ = writeln!(stderr, "install: prerequisites failed: {err}");
            return err.exit_code();
        }
    };
    for (tool, found) in [
        ("obsidian", report.obsidian_found),
        ("opencode", report.opencode_found),
    ] {
        if !found {
            let _ = writeln!(
                stderr,
                "warning: `{tool}` not found in PATH (optional; continuing)"
            );
        }
    }
    // F2: vault directory (`--vault` wins; otherwise the Ui asks).
    let raw = match resolve_vault_dir(&*ui, vault.as_deref()) {
        Ok(raw) => raw,
        Err(err) => {
            let _ = writeln!(stderr, "install: vault selection failed: {err}");
            return err.exit_code();
        }
    };
    match ensure_vault_dir(Path::new(&raw)) {
        Ok(path) => {
            // F3: merge the payload without overwrite (placeholders + intent).
            let Some(payload_dir) = payload.filter(|p| !p.trim().is_empty()) else {
                let _ = writeln!(
                    stderr,
                    "install: no payload source: pass --payload <ruta> \
                     (local tree for dev/tests); the versioned release asset lands in T19"
                );
                return 2;
            };
            match run_phase3(&LocalPayload::new(Path::new(&payload_dir)), path.as_path()) {
                Ok(report) => {
                    for already in &report.skipped {
                        let _ = writeln!(
                            stderr,
                            "warning: ya estaba (sin cambios): {}",
                            already.display()
                        );
                    }
                    let _ = writeln!(stdout, "{}", path.as_path().display());
                    0
                }
                Err(err) => {
                    let _ = writeln!(stderr, "install: phase F3 failed: {err}");
                    err.exit_code()
                }
            }
        }
        Err(err) => {
            let _ = writeln!(stderr, "install: vault directory failed: {err}");
            err.exit_code()
        }
    }
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
