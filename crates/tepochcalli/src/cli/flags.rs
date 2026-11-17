//! Shared argv flag parser for the four commands (T6): one loop, messages
//! parametrized by command prefix, byte-identical to the previous per-command
//! loops (including the no-TTY rule and exit 2 on unknown flags).

use std::io::IsTerminal;

use super::usage::{print_help, print_version};

/// Flag spec for one command: `prefix` names the command in the error
/// messages and `--help`, `takes_value` are the value flags (also accepted
/// as `--flag=value`), `boolean` the bare flags.
pub(crate) struct FlagSpec {
    pub(crate) prefix: &'static str,
    pub(crate) help_command: &'static str,
    pub(crate) takes_value: &'static [&'static str],
    pub(crate) boolean: &'static [&'static str],
}

/// Result of parsing one command's argv: the value flags seen (both forms)
/// and the boolean flags seen.
pub(crate) struct ParsedFlags {
    values: Vec<(&'static str, String)>,
    set: Vec<&'static str>,
}

impl ParsedFlags {
    /// Value of a value flag (last occurrence wins, like the old loops).
    pub(crate) fn value(&self, flag: &str) -> Option<&str> {
        self.values
            .iter()
            .rev()
            .find(|(name, _)| *name == flag)
            .map(|(_, value)| value.as_str())
    }

    /// Whether a boolean flag was present.
    pub(crate) fn is_set(&self, flag: &str) -> bool {
        self.set.contains(&flag)
    }
}

/// Parse `args` against `spec`. `Ok(None)` means `--help`/`--version` was
/// printed to stdout (exit 0); `Err(code)` is a usage error (message on
/// stderr); `Ok(Some(..))` carries the flags.
pub(crate) fn parse_flags(
    args: &[&str],
    spec: &FlagSpec,
    stdout: &mut dyn std::io::Write,
    stderr: &mut dyn std::io::Write,
) -> Result<Option<ParsedFlags>, u8> {
    let mut values: Vec<(&'static str, String)> = Vec::new();
    let mut set: Vec<&'static str> = Vec::new();
    let mut i = 0;
    while i < args.len() {
        let arg = args[i];
        if arg == "--help" {
            print_help(stdout, Some(spec.help_command));
            return Ok(None);
        }
        if arg == "--version" {
            print_version(stdout);
            return Ok(None);
        }
        let mut handled = false;
        for &flag in spec.takes_value {
            let eq_form = format!("{flag}=");
            if arg == flag {
                i += 1;
                match args.get(i) {
                    Some(value) => values.push((flag, (*value).to_string())),
                    None => {
                        let _ = writeln!(stderr, "{}: {flag} needs a value", spec.prefix);
                        return Err(2);
                    }
                }
                handled = true;
                break;
            }
            if let Some(rest) = arg.strip_prefix(eq_form.as_str()) {
                values.push((flag, rest.to_string()));
                handled = true;
                break;
            }
        }
        if handled {
            i += 1;
            continue;
        }
        if let Some(&flag) = spec.boolean.iter().find(|&&f| f == arg) {
            set.push(flag);
            i += 1;
            continue;
        }
        let _ = writeln!(stderr, "{}: unknown flag: {arg}", spec.prefix);
        return Err(2);
    }
    Ok(Some(ParsedFlags { values, set }))
}

/// T6 rule: no TTY means no prompts — fail fast instead of hanging (or
/// resolving a default dir under an unintended cwd). `true` when prompts
/// are admissible; the caller maps `false` to the typed `UserAborted` exit.
pub(crate) fn tty_ok(stderr: &mut dyn std::io::Write, non_interactive: bool, prefix: &str) -> bool {
    if non_interactive || std::io::stdin().is_terminal() {
        return true;
    }
    let _ = writeln!(
        stderr,
        "{prefix}: no TTY detected; re-run with --non-interactive (and --vault <ruta>)"
    );
    false
}
