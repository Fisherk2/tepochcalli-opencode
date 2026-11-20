//! `tepochcalli` with no subcommand: the H5 menu, each button routed to its
//! use-case, plus the H11 close.
//!
//! Choosing is read-only; `Exit` returns 0 without creating or writing
//! anything (H10). Every other action delegates to the existing command
//! implementation with the vault already resolved, so nothing is asked twice.

use std::path::Path;

use tepochcalli::adapters::ui_ratatui::wait_any_key;
use tepochcalli::adapters::{HeadlessUi, TtyUi};
use tepochcalli::application::{choose_action, resolve_vault_dir};
use tepochcalli::domain::{MenuAction, WizardError};
use tepochcalli::ports::Ui;

use super::commands::{run_config_embedder, run_uninstall_cmd, run_update_cmd};
use super::flags::{parse_flags, tty_ok, FlagSpec};
use super::install::{run_install, validate_payload_flags};
use super::report::report_maintenance_failure;

const HOME_SPEC: FlagSpec = FlagSpec {
    prefix: "tepochcalli",
    // Empty: `--help` here prints the top usage — there is no `home` command.
    help_command: "",
    takes_value: &["--vault", "--payload", "--payload-url", "--payload-sha256"],
    boolean: &["--non-interactive"],
};

/// H5 → H6..H11: resolve the vault, ask the menu, route the button.
/// `--non-interactive` without a script is a typed `UserAborted` (never a
/// hang); `Exit` touches nothing; any other action, whatever its outcome,
/// closes on any key with a thank-you (H11).
pub(crate) fn run_home_cmd(
    args: Vec<&str>,
    stdout: &mut dyn std::io::Write,
    stderr: &mut dyn std::io::Write,
) -> u8 {
    let flags = match parse_flags(&args, &HOME_SPEC, stdout, stderr) {
        Ok(Some(flags)) => flags,
        Ok(None) => return 0,
        Err(code) => return code,
    };
    let non_interactive = flags.is_set("--non-interactive");
    let vault = flags.value("--vault").map(str::to_string);
    let payload = flags.value("--payload").map(str::to_string);
    let payload_url = flags.value("--payload-url").map(str::to_string);
    let payload_sha256 = flags.value("--payload-sha256").map(str::to_string);
    if let Err(code) = validate_payload_flags(
        "tepochcalli",
        payload.as_deref(),
        payload_url.as_deref(),
        payload_sha256.as_deref(),
        stderr,
    ) {
        return code;
    }
    // T6 rule: no TTY means no prompts — fail fast instead of hanging.
    if !tty_ok(stderr, non_interactive, "tepochcalli") {
        return WizardError::UserAborted.exit_code();
    }
    let ui: Box<dyn Ui> = if non_interactive {
        // Sin guion no hay respuesta: el menú aborta tipado, nunca adivina.
        Box::new(HeadlessUi::new(Default::default(), Default::default()))
    } else {
        Box::new(TtyUi)
    };
    let raw = match resolve_vault_dir(&*ui, vault.as_deref()) {
        Ok(raw) => raw,
        Err(err) => {
            return report_maintenance_failure(
                &*ui,
                "tepochcalli",
                "vault selection failed",
                err,
                None,
            );
        }
    };
    let path = Path::new(&raw);
    let action = match choose_action(&*ui, path) {
        Ok(action) => action,
        Err(err) => {
            return report_maintenance_failure(
                &*ui,
                "tepochcalli",
                "menu selection failed",
                err,
                Some(path),
            );
        }
    };
    let forward = Forwarded {
        vault: &raw,
        non_interactive,
        payload: payload.as_deref(),
        url: payload_url.as_deref(),
        sha: payload_sha256.as_deref(),
    };
    let code = match action {
        MenuAction::Exit => return 0,
        MenuAction::Install => run_install(forward.payload_args(), stdout, stderr),
        MenuAction::Update => run_update_cmd(forward.payload_args(), stdout, stderr),
        // The menu click is the consent; the swap still shows its own warning
        // panel and option summary before touching anything.
        MenuAction::ChangeEmbedder => run_config_embedder(forward.confirm_args(), stdout, stderr),
        MenuAction::Desinstall => run_uninstall_cmd(forward.confirm_args(), stdout, stderr),
    };
    // H11: any action but Exit closes on any key, whatever its outcome.
    let _ = writeln!(
        stdout,
        "Gracias por usar Tepochcalli. Pulsa cualquier tecla para salir."
    );
    wait_any_key();
    code
}

/// The flags the menu forwards to the command it routes to: the vault it
/// already resolved (never asked twice) plus what the user typed.
struct Forwarded<'a> {
    vault: &'a str,
    non_interactive: bool,
    payload: Option<&'a str>,
    url: Option<&'a str>,
    sha: Option<&'a str>,
}

impl Forwarded<'_> {
    /// `install`/`update` argv: vault + payload overrides.
    fn payload_args(&self) -> Vec<&str> {
        let mut args = self.base();
        for (flag, value) in [
            ("--payload", self.payload),
            ("--payload-url", self.url),
            ("--payload-sha256", self.sha),
        ] {
            if let Some(value) = value {
                args.push(flag);
                args.push(value);
            }
        }
        args
    }

    /// `config embedder`/`uninstall` argv: vault + the mandatory `--confirm`
    /// the menu click already answered.
    fn confirm_args(&self) -> Vec<&str> {
        let mut args = self.base();
        args.push("--confirm");
        args
    }

    fn base(&self) -> Vec<&str> {
        let mut args = vec!["--vault", self.vault];
        if self.non_interactive {
            args.push("--non-interactive");
        }
        args
    }
}
