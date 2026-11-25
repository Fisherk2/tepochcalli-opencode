//! Contrato del CLI del flow compartido (T11/T12): `embed-check` y
//! `refresh` consumidos por F6, F7, reindex y swap.
//!
//! Los tres orquestadores repetían el mismo trunk de spawn y los mismos
//! parsers casi byte-idénticos (S5); este módulo los define UNA vez: los
//! literales del contrato (`FLOW_MODULE`, `GATE_SUBCOMMAND`,
//! `REFRESH_SUBCOMMAND`), los payloads tipados y los parsers. Los callers
//! componen `spawn_*` + su parser (reindex y swap reutilizan el gate/variante
//! completa; el swap solo lee `scanned` del refresh) — el trunk y la lógica de
//! veredicto ya no se copian.

use std::cell::RefCell;
use std::path::Path;

use crate::domain::{CancelToken, WizardError};
use crate::ports::{CommandOutput, CommandRunner};

use super::flow_cli::{run_flow_cli, GATE_TIMEOUT, REFRESH_TIMEOUT};
use super::text::{json_bool, json_string, json_u32, json_u64};

/// Flow CLI module invoked through the venv interpreter (D24).
pub(super) const FLOW_MODULE: &str = "tepochcalli_flow";
/// `embed-check` measures the dims of a freshly configured model (T11 gate).
pub(super) const GATE_SUBCOMMAND: &str = "embed-check";
/// `refresh` indexes the vault and prints its `RefreshReport` as one JSON line.
pub(super) const REFRESH_SUBCOMMAND: &str = "refresh";

/// Gate success payload (T12 programs the flow CLI against this shape).
#[derive(Debug, PartialEq, Eq)]
pub struct GateOk {
    pub(super) model: String,
    pub(super) dims: u32,
    pub(super) rss_peak_bytes: u64,
}

/// Causa real de un gate rechazado (T18). `WizardError` es `Copy` y no puede
/// llevar `String`: el `error_code`/`detail` del JSON viajan aquí, sin truncar,
/// hasta el panel del install degradado.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GateCause {
    pub error: WizardError,
    pub error_code: Option<String>,
    pub detail: Option<String>,
}

impl From<WizardError> for GateCause {
    /// Errores sin veredicto del gate (spawn, fs, cancelación): la causa es
    /// el propio error tipado, sin código ni detalle inventados.
    fn from(error: WizardError) -> Self {
        Self {
            error,
            error_code: None,
            detail: None,
        }
    }
}

impl GateCause {
    /// Causa para el panel y el log: código y detalle del flow, sin recortes.
    #[must_use]
    pub fn context(&self) -> String {
        let mut out = String::new();
        if let Some(code) = &self.error_code {
            out.push_str(code);
            out.push_str(": ");
        }
        if let Some(detail) = &self.detail {
            out.push_str(detail);
        }
        if out.is_empty() {
            out.push_str(&self.error.to_string());
        }
        out
    }
}

thread_local! {
    /// Buzón de una sola lectura para el veredicto del gate: las capas
    /// intermedias están tipadas a `WizardError` (`Copy`) y no pueden portar
    /// el `detail`; `install_phases` lo toma justo después del F6.
    static LAST_GATE_CAUSE: RefCell<Option<GateCause>> = const { RefCell::new(None) };
}

/// Toma y vacía la causa del último `embed-check` de esta hebra.
#[must_use]
pub fn take_gate_cause() -> Option<GateCause> {
    LAST_GATE_CAUSE.with(|cell| cell.borrow_mut().take())
}

fn stash_gate_cause(cause: Option<GateCause>) {
    LAST_GATE_CAUSE.with(|cell| {
        *cell.borrow_mut() = cause;
    });
}

/// Refresh success payload (T12 contract): the four counters of the pass.
#[derive(Debug, PartialEq, Eq)]
pub(super) struct Refreshed {
    pub(super) scanned: u64,
    pub(super) indexed: u64,
    pub(super) skipped: u64,
    pub(super) elapsed_ms: u64,
}

/// Spawn trunk del gate (T11): `venv python -m tepochcalli_flow embed-check
/// --model <id> [--revision <sha>]`. La revisión y el token son parámetros
/// explícitos: F7/reindex no conocen ninguna de las dos, F6/swap pueden.
pub(super) fn spawn_gate(
    proc: &dyn CommandRunner,
    vault: &Path,
    model_id: &str,
    revision: Option<&str>,
    token: Option<&str>,
    cancel: Option<&CancelToken>,
) -> Result<CommandOutput, WizardError> {
    let mut args: Vec<&str> = vec!["-m", FLOW_MODULE, GATE_SUBCOMMAND, "--model", model_id];
    if let Some(sha) = revision {
        args.push("--revision");
        args.push(sha);
    }
    run_flow_cli(proc, vault, &args, &[], token, cancel, GATE_TIMEOUT)
}

/// Spawn trunk del refresh (T12): `venv python -m tepochcalli_flow refresh`.
pub(super) fn spawn_refresh(
    proc: &dyn CommandRunner,
    vault: &Path,
) -> Result<CommandOutput, WizardError> {
    run_flow_cli(
        proc,
        vault,
        &["-m", FLOW_MODULE, REFRESH_SUBCOMMAND],
        &[],
        None,
        None,
        REFRESH_TIMEOUT,
    )
}

/// Gate completo (T12/T18): `ok:false` es un fallo de carga del modelo
/// (`ModelLoadFailed`, con su causa real en [`take_gate_cause`]); un gate roto
/// o ilegible es `PhaseFailed`; un campo ausente no se inventa (`Internal`).
pub fn parse_gate(body: &str) -> Result<GateOk, WizardError> {
    gate_verdict(body)?;
    Ok(GateOk {
        model: json_string(body, "model").ok_or(WizardError::Internal)?,
        dims: json_u32(body, "dims").ok_or(WizardError::Internal)?,
        rss_peak_bytes: json_u64(body, "rss_peak_bytes").ok_or(WizardError::Internal)?,
    })
}

/// `ok:true` ⇒ sigue el parser del caller; `ok:false` ⇒ fallo de carga, con
/// `error_code`/`detail` guardados en el portador; sin `ok` ⇒ fase rota.
fn gate_verdict(body: &str) -> Result<(), WizardError> {
    match json_bool(body, "ok") {
        Some(true) => {
            stash_gate_cause(None);
            Ok(())
        }
        Some(false) => {
            let error = WizardError::ModelLoadFailed;
            stash_gate_cause(Some(GateCause {
                error,
                error_code: json_string(body, "error_code"),
                detail: json_string(body, "detail"),
            }));
            Err(error)
        }
        None => {
            stash_gate_cause(None);
            Err(WizardError::PhaseFailed)
        }
    }
}

/// Refresh (T12): `{ok:false}` se mapea a `ModelInvalid` (paridad del
/// portero F7); cualquier otra cosa ilegible es `PhaseFailed`.
pub(super) fn parse_refresh(body: &str) -> Result<Refreshed, WizardError> {
    // unreachable: el flow CLI nunca emite {ok:false} (solo embed-check); los
    // tests lo pinnean como contrato defensivo.
    if json_bool(body, "ok") == Some(false) {
        return Err(WizardError::ModelInvalid);
    }
    match (
        json_u64(body, "scanned"),
        json_u64(body, "indexed"),
        json_u64(body, "skipped"),
        json_u64(body, "elapsed_ms"),
    ) {
        (Some(scanned), Some(indexed), Some(skipped), Some(elapsed_ms)) => Ok(Refreshed {
            scanned,
            indexed,
            skipped,
            elapsed_ms,
        }),
        _ => Err(WizardError::PhaseFailed),
    }
}
