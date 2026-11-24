//! Top-level usage texts and the `--help`/`--version`/usage-error printers
//! (byte-exact strings, T6 contract).

pub(crate) const VERSION: &str = env!("CARGO_PKG_VERSION");

pub(crate) fn usage_top() -> &'static str {
    "Usage: tepochcalli [<command>] [options]\n\
     \n\
     Without a command, tepochcalli opens the H5 menu: install, update,\n\
     change embedder, desinstall or exit (choosing touches nothing).\n\
     \n\
     Commands:\n  \
     install            install a vault\n  \
     update             overwrite the payload files (with .bak backups)\n  \
     config embedder    pick the embedding provider\n  \
     reindex            rebuild the index\n  \
     uninstall          remove the runtime\n\
     \n\
     Options:\n  \
     --help     print this help\n  \
     --version  print the version\n"
}

pub(crate) fn usage_for(command: &str) -> String {
    // Empty command = the menu (`tepochcalli --help`): the top usage.
    if command.is_empty() {
        return usage_top().to_string();
    }
    if command == "install" {
        return "Usage: tepochcalli install [options]\n\
         \nOptions:\n  \
         --non-interactive  never prompt; a missing answer is a typed error\n  \
         --skip-model       preselect \"configure later\" (degraded, no index)\n  \
         --vault <ruta>     vault directory (asked interactively if omitted)\n  \
         --payload <ruta>   local payload tree (dev/tests; default: the\n  \
         versioned release asset for this binary (one-version rule))\n  \
         --payload-url <url>   override the release asset URL (dev/tests;\n  \
         needs --payload-sha256)\n  \
         --payload-sha256 <hex>  expected SHA-256 for --payload-url\n  \
         --resume           skip phases already done (artifacts + .install-state)\n  \
         --offline          no network: local payload + cached model only\n  \
         --help     print this help\n  \
         --version  print the version\n"
            .to_string();
    }
    if command == "config embedder" {
        return "Usage: tepochcalli config embedder [options]\n\
         \nOptions:\n  \
         --vault <ruta>      vault directory (asked interactively if omitted)\n  \
         --non-interactive  never prompt; a missing answer is a typed error\n  \
         --confirm          mandatory: the swap rebuilds the whole index\n  \
         --keep-previous    retain the previous model cache (no auto-GC)\n  \
         --help     print this help\n  \
         --version  print the version\n"
            .to_string();
    }
    if command == "reindex" {
        return "Usage: tepochcalli reindex [options]\n\
         \nOptions:\n  \
         --confirm          mandatory: the rebuild is destructive (full re-index)\n  \
         --vault <ruta>     vault directory (asked interactively if omitted)\n  \
         --non-interactive  never prompt; a missing answer is a typed error\n  \
         --help     print this help\n  \
         --version  print the version\n"
            .to_string();
    }
    if command == "update" {
        return "Usage: tepochcalli update [options]\n\
         \nOverwrites .opencode/, .tepochcalli/, .gitignore, opencode.json and AGENTS.md\n\
         in the target vault, saving every replaced file as `<ruta>.bak` first.\n\
         \nOptions:\n  \
         --vault <ruta>     vault directory (asked interactively if omitted)\n  \
         --payload <ruta>   local payload tree (dev/tests; default: the\n  \
         versioned release asset for this binary (one-version rule))\n  \
         --payload-url <url>   override the release asset URL (dev/tests;\n  \
         needs --payload-sha256)\n  \
         --payload-sha256 <hex>  expected SHA-256 for --payload-url\n  \
         --non-interactive  never prompt; a missing answer is a typed error\n  \
         --help     print this help\n  \
         --version  print the version\n"
            .to_string();
    }
    if command == "uninstall" {
        return "Usage: tepochcalli uninstall [options]\n\
         \nOptions:\n  \
         --vault <ruta>     vault directory (asked interactively if omitted)\n  \
         --confirm          mandatory: the uninstall removes the whole runtime\n  \
         --non-interactive  never prompt; a missing answer is a typed error\n  \
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

pub(crate) fn print_help(stdout: &mut dyn std::io::Write, command: Option<&str>) {
    match command {
        None => {
            let _ = stdout.write_all(usage_top().as_bytes());
        }
        Some(cmd) => {
            let _ = stdout.write_all(usage_for(cmd).as_bytes());
        }
    }
}

pub(crate) fn print_version(stdout: &mut dyn std::io::Write) {
    let _ = writeln!(stdout, "tepochcalli {VERSION}");
}

pub(crate) fn unknown(stderr: &mut dyn std::io::Write, arg: &str) -> u8 {
    let _ = writeln!(stderr, "unknown subcommand: {arg}");
    let _ = stderr.write_all(usage_top().as_bytes());
    2
}

pub(crate) fn bare_config(stderr: &mut dyn std::io::Write) -> u8 {
    let _ = stderr.write_all(usage_top().as_bytes());
    let _ = writeln!(stderr, "Usage: tepochcalli config <embedder> [options]");
    2
}
