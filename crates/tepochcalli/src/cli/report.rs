//! Failure exits shared by install (T15) and the maintenance commands
//! (T17): best-effort redacted log under the OS state dir + redacted
//! stderr panel via the `Ui` port.

use std::path::Path;

use tepochcalli::application::failure::{
    log_path_in, now_secs, secrets_from_vault, state_dir, write_failure_log,
};
use tepochcalli::domain::failure::{failure_body, failure_body_usage, failure_title, redact};
use tepochcalli::domain::{Phase, WizardError};
use tepochcalli::ports::Ui;

/// T17 failure exit (reindex/uninstall): same shared `report()` shape
/// (panel on stderr + redacted log outside the vault), but the title/body
/// carry the real command — never the install retry line, which would point
/// at the wrong fix.
pub(crate) fn report_maintenance_failure(
    ui: &dyn Ui,
    command: &str,
    context: &str,
    err: WizardError,
    vault: Option<&Path>,
) -> u8 {
    let owned: Vec<String> = vault.map(secrets_from_vault).unwrap_or_default();
    let log_path = log_path_in(&state_dir(), now_secs());
    let title = format!("{command} failed");
    let mut body = format!("cause: {context}: {err}\n");
    if let Some(code) = err.e_star() {
        body.push_str(&format!("code: {code}\n"));
    }
    body.push_str(&format!("log: {}\n", log_path.display()));
    report(ui, &title, body, &owned, &log_path, err.exit_code())
}

/// Shared T15/T17 failure exit (S-3): best-effort redacted log under the OS
/// state dir (never the vault) + redacted stderr panel via the `Ui` port.
/// `title`/`body` arrive composed by the caller (install keeps the graded
/// `failure_title/failure_body` shapes; maintenance names its own command
/// and carries no install retry line); the typed exit code is returned
/// unchanged. `log_path` is the one the caller already computed for the
/// body — the panel and the written log can never diverge.
pub(crate) fn report(
    ui: &dyn Ui,
    title: &str,
    body: String,
    secrets: &[String],
    log_path: &Path,
    code: u8,
) -> u8 {
    let masked: Vec<&str> = secrets.iter().map(String::as_str).collect();
    write_failure_log(log_path, &redact(&format!("{title}\n{body}"), &masked));
    ui.panel(title, &redact(&body, &masked));
    code
}

/// Centralized install-failure exit (T15): log + `failure_*` panel shape.
pub(crate) fn report_failure(
    ui: &dyn Ui,
    phase: Option<Phase>,
    context: &str,
    err: WizardError,
    vault: Option<&Path>,
) -> u8 {
    let owned: Vec<String> = vault.map(secrets_from_vault).unwrap_or_default();
    let masked: Vec<&str> = owned.iter().map(String::as_str).collect();
    let log_path = log_path_in(&state_dir(), now_secs());
    let title = failure_title(phase);
    let body = failure_body(context, phase, err, &log_path, &masked);
    report(ui, &title, body, &owned, &log_path, err.exit_code())
}

/// Usage-failure exit (#10b, P0-2): mismo esqueleto compartido que
/// [`report_failure`] (log redactado bajo el state dir + panel vía el puerto
/// `Ui`), pero con [`failure_body_usage`] — un flag ausente en
/// `--non-interactive` es un fallo de USO, no una cancelación: sin línea
/// `estado:`, sin el Display de `UserAborted` y con el flag ausente como
/// correctivo (nunca `--resume`). El código de salida tipado del err se
/// conserva y el título lleva la fase entre paréntesis cuando se conoce.
#[allow(clippy::too_many_arguments)]
pub(crate) fn report_usage_failure(
    ui: &dyn Ui,
    command: &str,
    phase: Option<Phase>,
    context: &str,
    missing: &str,
    usage: &str,
    err: WizardError,
    vault: Option<&Path>,
) -> u8 {
    let owned: Vec<String> = vault.map(secrets_from_vault).unwrap_or_default();
    let masked: Vec<&str> = owned.iter().map(String::as_str).collect();
    let log_path = log_path_in(&state_dir(), now_secs());
    let title = match phase {
        Some(phase) => format!("{command}: uso incorrecto ({})", phase.name()),
        None => format!("{command}: uso incorrecto"),
    };
    let body = failure_body_usage(command, missing, usage, context, phase, &log_path, &masked);
    report(ui, &title, body, &owned, &log_path, err.exit_code())
}

/// Cancelación genuina (Esc / Ctrl-C en interactivo): nadie falló, así que el
/// panel no dice «failed» ni inventa un log. Devuelve el código de
/// `UserAborted`.
pub(crate) fn report_cancel(ui: &dyn Ui, command: &str) -> u8 {
    ui.panel(
        "Cancelado",
        &format!("{command}: cancelado por el usuario; no se modificó nada."),
    );
    WizardError::UserAborted.exit_code()
}
