//! `tepochcalli` with no subcommand: the H5 menu, each button routed to its
//! use-case, plus the H11 close.
//!
//! Choosing is read-only; `Exit` returns 0 without creating or writing
//! anything (H10). Every other action delegates to the existing command
//! implementation with the vault already resolved, so nothing is asked twice.

use std::path::Path;

use tepochcalli::adapters::{HeadlessUi, TtyUi};
use tepochcalli::application::choose_action;
use tepochcalli::domain::{MenuAction, WizardError};
use tepochcalli::ports::Ui;

use super::commands::{
    resolve_vault_or_report, run_config_embedder, run_uninstall_cmd, run_update_cmd,
};
use super::flags::{parse_flags, tty_ok, FlagSpec};
use super::install::{run_install, validate_payload_flags};
use super::report::{report_cancel, report_maintenance_failure, report_usage_failure};

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
    let raw = match resolve_vault_or_report(
        &*ui,
        non_interactive,
        vault.as_deref(),
        "tepochcalli",
        "tepochcalli --vault <directorio> --non-interactive <subcomando>",
    ) {
        Ok(raw) => raw,
        Err(code) => return code,
    };
    let path = Path::new(&raw);
    let action = match choose_action(&*ui, path) {
        Ok(action) => action,
        Err(err) if non_interactive => {
            return report_usage_failure(
                &*ui,
                "tepochcalli",
                None,
                "menu selection failed",
                "un subcomando",
                "tepochcalli install|update|uninstall|config embedder …",
                err,
                Some(path),
            );
        }
        Err(WizardError::UserAborted) => return report_cancel(&*ui, "tepochcalli"),
        Err(err) => {
            return report_maintenance_failure(
                &*ui,
                "tepochcalli",
                "menu selection failed",
                err,
                Some(path),
            )
        }
    };
    let forward = Forwarded {
        vault: &raw,
        non_interactive,
        payload: payload.as_deref(),
        url: payload_url.as_deref(),
        sha: payload_sha256.as_deref(),
    };
    let code = match route(action, &forward) {
        // H10: `Exit` dispatches nothing.
        None => 0,
        Some((target, args)) => match target {
            Target::Install => run_install(args, stdout, stderr),
            Target::Update => run_update_cmd(args, stdout, stderr),
            // The menu click is the consent; the swap still shows its own warning
            // panel and option summary before touching anything.
            Target::ConfigEmbedder => run_config_embedder(args, stdout, stderr),
            Target::Uninstall => run_uninstall_cmd(args, stdout, stderr),
        },
    };
    // H11: any action but Exit closes on any key, whatever its outcome.
    if write_farewell(action, stdout) {
        ui.wait_key();
    }
    code
}

/// H11: the thank-you closes every action but `Exit`, which leaves without a
/// word (H10). Returns whether it was written, so the caller waits for a key
/// only on that path.
fn write_farewell(action: MenuAction, stdout: &mut dyn std::io::Write) -> bool {
    if action == MenuAction::Exit {
        return false;
    }
    let _ = writeln!(
        stdout,
        "Gracias por usar Tepochcalli. Pulsa cualquier tecla para salir."
    );
    true
}

/// The subcommand a menu button routes to (H6..H9). `Exit` has none (H10).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Target {
    Install,
    Update,
    ConfigEmbedder,
    Uninstall,
}

/// The dispatch glue: a chosen button becomes the subcommand it runs plus the
/// argv it re-sends (the vault already resolved, never asked twice). `None`
/// for `Exit` — it dispatches nothing and touches nothing (H10).
fn route<'a>(action: MenuAction, forward: &'a Forwarded<'_>) -> Option<(Target, Vec<&'a str>)> {
    match action {
        MenuAction::Exit => None,
        MenuAction::Install => Some((Target::Install, forward.payload_args())),
        MenuAction::Update => Some((Target::Update, forward.payload_args())),
        MenuAction::ChangeEmbedder => Some((Target::ConfigEmbedder, forward.confirm_args())),
        MenuAction::Desinstall => Some((Target::Uninstall, forward.confirm_args())),
    }
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

#[cfg(test)]
mod tests {
    use std::io::IsTerminal;

    use super::*;

    fn forwarded(non_interactive: bool) -> Forwarded<'static> {
        Forwarded {
            vault: "/vault",
            non_interactive,
            payload: None,
            url: None,
            sha: None,
        }
    }

    #[test]
    fn install_and_update_re_send_the_resolved_vault_and_the_payload_overrides() {
        let forward = Forwarded {
            vault: "/vault",
            non_interactive: false,
            payload: Some("/payload"),
            url: Some("https://example.test/p.tar.gz"),
            sha: Some("deadbeef"),
        };
        let expected = vec![
            "--vault",
            "/vault",
            "--payload",
            "/payload",
            "--payload-url",
            "https://example.test/p.tar.gz",
            "--payload-sha256",
            "deadbeef",
        ];
        for (action, target) in [
            (MenuAction::Install, Target::Install),
            (MenuAction::Update, Target::Update),
        ] {
            let (routed, args) = route(action, &forward).expect("the menu click dispatches");
            assert_eq!(routed, target, "{action:?} must route to its subcommand");
            assert_eq!(args, expected, "{action:?} argv");
        }
    }

    #[test]
    fn change_embedder_and_desinstall_add_the_confirm_the_menu_click_answered() {
        let forward = forwarded(false);
        for (action, target) in [
            (MenuAction::ChangeEmbedder, Target::ConfigEmbedder),
            (MenuAction::Desinstall, Target::Uninstall),
        ] {
            let (routed, args) = route(action, &forward).expect("the menu click dispatches");
            assert_eq!(routed, target, "{action:?} must route to its subcommand");
            assert_eq!(
                args,
                vec!["--vault", "/vault", "--confirm"],
                "{action:?} argv"
            );
        }
    }

    #[test]
    fn exit_dispatches_nothing() {
        // H10: leaving touches nothing, so there is no argv to re-send.
        let forward = forwarded(false);
        assert_eq!(route(MenuAction::Exit, &forward), None);
    }

    #[test]
    fn the_non_interactive_flag_travels_with_every_dispatch() {
        // The subcommand must never ask again what the menu already resolved.
        let forward = forwarded(true);
        let (routed, args) =
            route(MenuAction::Desinstall, &forward).expect("the menu click dispatches");
        assert_eq!(routed, Target::Uninstall);
        assert_eq!(
            args,
            vec!["--vault", "/vault", "--non-interactive", "--confirm"]
        );
    }

    #[test]
    fn every_action_but_exit_closes_with_the_farewell() {
        // H11: whichever button was clicked — whatever its outcome — the
        // wizard thanks the user before closing.
        for action in [
            MenuAction::Install,
            MenuAction::Update,
            MenuAction::ChangeEmbedder,
            MenuAction::Desinstall,
        ] {
            let mut out = Vec::new();
            assert!(
                write_farewell(action, &mut out),
                "{action:?} must close with the H11 thank-you"
            );
            let text = String::from_utf8(out).expect("utf8 farewell");
            assert!(
                text.contains("Gracias por usar Tepochcalli"),
                "{action:?} farewell must thank the user, got: {text:?}"
            );
            assert!(
                text.contains("Pulsa cualquier tecla para salir"),
                "{action:?} farewell must mention the any-key close, got: {text:?}"
            );
        }
    }

    #[test]
    fn exit_leaves_without_the_farewell() {
        // H10: leaving touches nothing — not even a goodbye line.
        let mut out = Vec::new();
        assert!(!write_farewell(MenuAction::Exit, &mut out));
        assert!(out.is_empty(), "Exit must write nothing, got: {out:?}");
    }

    #[test]
    fn wait_key_returns_when_there_is_no_terminal() {
        // Smoke guard (no RED possible: the no-op is already the behaviour).
        // Sin TTY la sonda es no-op; con TTY esperaría una tecla real y
        // colgaría la suite, así que solo se ejercita el camino sin terminal.
        if std::io::stdin().is_terminal() {
            return;
        }
        TtyUi.wait_key();
    }
}
