//! `tepochcalli` entrypoint: hand-rolled argv dispatch (no clap until T6).
//!
//! `install` runs F1→F2 for real (T7) + F3 payload merge (T8) + F4 `uv`
//! bootstrap and F5 venv/`sync` (T9) + F6 embedder menu (T11) + F7 initial
//! index (T12); every other subcommand is still a stub that exits 40
//! (`WizardError::Internal` range, plan §5.4) until its task.

use std::io::IsTerminal;
use std::path::Path;
use std::process::ExitCode;

use tepochcalli::adapters::UreqHttpClient;
use tepochcalli::adapters::{HeadlessUi, LocalPayload, StdCommandRunner, SysHostProbe, TtyUi};
use tepochcalli::application::{
    check_prereqs, compensate_phase6, ensure_vault_dir, guard_offline_before_touch, is_phase_done,
    mark_phase_done, payload_local_ready, read_completed_report, resolve_vault_dir, run_phase3,
    run_phase4, run_phase5, run_phase6, run_phase7, run_phase8, Phase6Deps, Phase6Report,
};
use tepochcalli::domain::{Phase, VaultPath, WizardError};
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
         --payload <ruta>   payload tree to merge (dev/tests; required until T19)\
          --resume           skip phases already done (artifacts + .install-state)\
          --offline          no network: local payload + cached model only\n  \
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

/// `install` flag parsing (T6) + F1→F2 execution (T7) + F3 merge (T8) +
/// F4 `uv` bootstrap, F5 venv/`sync` (T9), F6 embedder menu (T11) and F7
/// initial index (T12):
/// `--non-interactive`, `--skip-model`, `--vault <ruta>` and
/// `--payload <ruta>` select the [`HeadlessUi`] answers (never stdin) vs.
/// [`TtyUi`]; then F1 gates prereqs, F2 ensures the vault dir, F3 merges
/// the payload, F4 installs the pinned `uv`, F5 syncs the venv, F6 picks
/// the embedder (menu + gate + atomic config) and F7 indexes the vault
/// (path 5 skips it: degraded install, no index). Without
/// `--payload` (and no release URL configured yet — T19 wires the asset)
/// install stops here with exit 2 (CLI usage error, same class as `--vault`
/// without a value).
fn run_install(
    args: Vec<&str>,
    stdout: &mut dyn std::io::Write,
    stderr: &mut dyn std::io::Write,
) -> u8 {
    let mut non_interactive = false;
    let mut skip_model = false;
    let mut resume = false;
    let mut offline = false;
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
            "--resume" => resume = true,
            "--offline" => offline = true,
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
    // T14: offline pre-check BEFORE the vault is touched (exit 21, no writes).
    if offline {
        let cache_ready = skip_model || models_cached(Path::new(&raw));
        match guard_offline_before_touch(true, payload_local_ready(payload.as_deref()), cache_ready)
        {
            Ok(()) => {}
            Err(err) => {
                let _ = writeln!(
                    stderr,
                    "install: offline without local payload/cache: {err}"
                );
                return err.exit_code();
            }
        }
    }
    let vault_path = match ensure_vault_dir(Path::new(&raw)) {
        Ok(path) => path,
        Err(err) => {
            let _ = writeln!(stderr, "install: vault directory failed: {err}");
            return err.exit_code();
        }
    };
    mark_phase_done(vault_path.as_path(), Phase::F1);
    mark_phase_done(vault_path.as_path(), Phase::F2);
    run_phases(&vault_path, payload, resume, offline, &*ui, stdout, stderr)
}

/// `true` when the vault already holds downloaded models (offline resume).
fn models_cached(vault: &Path) -> bool {
    match std::fs::read_dir(vault.join(".tepochcalli/models")) {
        Ok(mut entries) => entries.next().is_some(),
        Err(_) => false,
    }
}

/// Offline mapping: a network failure under `--offline` is the typed offline
/// error (exit 21), never a generic download failure.
fn offline_map(offline: bool, err: WizardError) -> WizardError {
    if offline && err == WizardError::NetDownload {
        WizardError::OfflineNoCache
    } else {
        err
    }
}

/// F6 with T14(f) fallback: any failure but an explicit abort (or a missing
/// offline cache) compensates to salida 5 — a COMPLETE degraded install.
fn run_f6_or_degraded(
    deps: &Phase6Deps<'_>,
    path: &VaultPath,
    offline: bool,
    stderr: &mut dyn std::io::Write,
) -> Result<Phase6Report, u8> {
    match run_phase6(deps, path.as_path()) {
        Ok(picked) => {
            mark_phase_done(path.as_path(), Phase::F6);
            Ok(picked)
        }
        Err(err) => {
            let err = offline_map(offline, err);
            // shortcut: Internal/UserAborted/OfflineNoCache never degrade —
            // a bug, an explicit cancel and an empty cache stay failures.
            if err == WizardError::UserAborted
                || err == WizardError::Internal
                || err == WizardError::OfflineNoCache
            {
                let _ = writeln!(stderr, "install: phase F6 failed: {err}");
                return Err(err.exit_code());
            }
            match compensate_phase6(path.as_path()) {
                Ok(()) => {
                    mark_phase_done(path.as_path(), Phase::F6);
                    let _ = writeln!(
                        stderr,
                        "embedder: F6 failed ({err}); continuing degraded (configure later)"
                    );
                    Ok(Phase6Report::configure_later())
                }
                Err(comp_err) => {
                    let _ = writeln!(stderr, "install: phase F6 failed: {comp_err}");
                    Err(comp_err.exit_code())
                }
            }
        }
    }
}

/// F3..F8 with `--resume` skips (marker + artifacts, never a re-download).
fn run_phases(
    path: &VaultPath,
    payload: Option<String>,
    resume: bool,
    offline: bool,
    ui: &dyn Ui,
    stdout: &mut dyn std::io::Write,
    stderr: &mut dyn std::io::Write,
) -> u8 {
    // F3: merge the payload without overwrite (placeholders + intent).
    let Some(payload_dir) = payload.filter(|p| !p.trim().is_empty()) else {
        let _ = writeln!(
            stderr,
            "install: no payload source: pass --payload <ruta> \
             (local tree for dev/tests); the versioned release asset lands in T19"
        );
        return 2;
    };
    let skipped: Vec<std::path::PathBuf> = if resume && is_phase_done(path.as_path(), Phase::F3) {
        let _ = writeln!(stderr, "resume: F3 already done, skipping");
        Vec::new()
    } else {
        match run_phase3(&LocalPayload::new(Path::new(&payload_dir)), path.as_path()) {
            Ok(report) => {
                mark_phase_done(path.as_path(), Phase::F3);
                report.skipped
            }
            Err(err) => {
                let _ = writeln!(stderr, "install: phase F3 failed: {err}");
                return err.exit_code();
            }
        }
    };
    for already in &skipped {
        let _ = writeln!(
            stderr,
            "warning: ya estaba (sin cambios): {}",
            already.display()
        );
    }
    // F4: pinned `uv` into `.tepochcalli/bin/` (+ version proof).
    // Compensates itself on failure.
    let http = UreqHttpClient::new();
    let proc = StdCommandRunner;
    if resume && is_phase_done(path.as_path(), Phase::F4) {
        let _ = writeln!(stderr, "resume: F4 already done, skipping (uv cached)");
    } else {
        match run_phase4(&http, &proc, path.as_path()) {
            Ok(phase4) => {
                mark_phase_done(path.as_path(), Phase::F4);
                let _ = writeln!(stderr, "uv {} ready", phase4.version);
            }
            Err(err) => {
                let err = offline_map(offline, err);
                let _ = writeln!(stderr, "install: phase F4 failed: {err}");
                return err.exit_code();
            }
        }
    }
    // F5: venv + frozen sync + R6 import check. `bin/` stays when F5 fails
    // (each phase compensates only what it wrote).
    if resume && is_phase_done(path.as_path(), Phase::F5) {
        let _ = writeln!(stderr, "resume: F5 already done, skipping (venv cached)");
    } else {
        match run_phase5(&proc, path.as_path()) {
            Ok(_) => mark_phase_done(path.as_path(), Phase::F5),
            Err(err) => {
                let err = offline_map(offline, err);
                let _ = writeln!(stderr, "install: phase F5 failed: {err}");
                return err.exit_code();
            }
        }
    }
    // F6: embedder menu + test-embed gate + atomic config. `--skip-model`
    // preselects path 5 (configure later, degraded, no index).
    let deps = Phase6Deps {
        ui,
        host: &SysHostProbe,
        proc: &proc,
        http: &http,
    };
    let picked = if resume && is_phase_done(path.as_path(), Phase::F6) {
        match read_completed_report(path.as_path()) {
            Some(report) => {
                let _ = writeln!(stderr, "resume: F6 already done, skipping");
                report
            }
            None => match run_f6_or_degraded(&deps, path, offline, stderr) {
                Ok(picked) => picked,
                Err(code) => return code,
            },
        }
    } else {
        match run_f6_or_degraded(&deps, path, offline, stderr) {
            Ok(picked) => picked,
            Err(code) => return code,
        }
    };
    let _ = writeln!(
        stderr,
        "embedder: provider={} {}",
        picked.provider,
        picked.model.as_deref().unwrap_or("(none)")
    );
    // F7: initial index via the flow CLI. Path 5 short-circuits inside
    // `run_phase7` (no spawn, no index).
    if resume && is_phase_done(path.as_path(), Phase::F7) {
        let _ = writeln!(stderr, "resume: F7 already done, skipping");
    } else {
        match run_phase7(&proc, path.as_path(), &picked) {
            Ok(indexed) => {
                mark_phase_done(path.as_path(), Phase::F7);
                let _ = writeln!(
                    stderr,
                    "index: scanned={} indexed={} ({} ms)",
                    indexed.scanned, indexed.indexed, indexed.elapsed_ms
                );
            }
            Err(err) => {
                let err = offline_map(offline, err);
                let _ = writeln!(stderr, "install: phase F7 failed: {err}");
                return err.exit_code();
            }
        }
    }
    // F8: merge `mcp.servers` (+ `.bak`) and verify `rag_status` end to end.
    if resume && is_phase_done(path.as_path(), Phase::F8) {
        let _ = writeln!(stderr, "resume: F8 already done, skipping");
    } else {
        match run_phase8(&proc, path.as_path()) {
            Ok(f8) => {
                mark_phase_done(path.as_path(), Phase::F8);
                let _ = writeln!(
                    stderr,
                    "mcp: tepochcalli-rag {} (rag_status={})",
                    if f8.changed {
                        "registered"
                    } else {
                        "up to date"
                    },
                    f8.health.as_str()
                );
            }
            Err(err) => {
                let _ = writeln!(stderr, "install: phase F8 failed: {err}");
                return err.exit_code();
            }
        }
    }
    let _ = writeln!(stdout, "{}", path.as_path().display());
    0
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
