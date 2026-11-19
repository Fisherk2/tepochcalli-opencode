//! `tepochcalli` entrypoint: hand-rolled argv dispatch (no clap until T6).
//!
//! `install` runs F1→F2 for real (T7) + F3 payload merge (T8) + F4 `uv`
//! bootstrap and F5 venv/`sync` (T9) + F6 embedder menu (T11) + F7 initial
//! index (T12); `config embedder` runs the D8.4 atomic swap (T16);
//! `reindex --confirm` rebuilds the index (T17), `update` overwrites the 5
//! payload scopes with `.bak` (H7) and `uninstall` removes them (H8).
//!
//! The command implementations live in the binary-private `cli/` modules
//! (usage/report/install/install_phases/commands); the `application::*`
//! public exports are untouched.

mod cli;

use std::process::ExitCode;

use cli::{
    bare_config, print_help, print_version, run_config_embedder, run_install, run_reindex_cmd,
    run_uninstall_cmd, run_update_cmd, unknown, usage_top,
};

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
        "update" => run_update_cmd(it.collect(), stdout, stderr),
        "reindex" => run_reindex_cmd(it.collect(), stdout, stderr),
        "uninstall" => run_uninstall_cmd(it.collect(), stdout, stderr),
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
            Some("embedder") => run_config_embedder(it.collect(), stdout, stderr),
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
