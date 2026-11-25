//! T18: el veredicto del `embed-check` conserva su causa real (código y
//! detalle del JSON) y deja de apropiarse de `ModelInvalid`, que pertenece al
//! pre-filtro de tags de HuggingFace (ruta 3). Sin red ni binario: el contrato
//! del gate se prueba en el parseo y en el texto que luego ve el panel.

use tepochcalli::application::flow_contract::{parse_gate, take_gate_cause, GateCause};
use tepochcalli::domain::WizardError;

/// Gate rechazado con la causa que el flow emite hoy (`__main__.py:135`).
fn gate_failure(code: &str, detail: &str) -> String {
    format!("{{\"ok\":false,\"error_code\":\"{code}\",\"detail\":\"{detail}\"}}")
}

#[test]
fn int_gate_errors_preserve_code_and_detail_without_truncation() {
    let detail = "cuda error: no kernel image is available for execution on the device (sm_90)";
    let body = gate_failure("E_MODEL_LOAD_FAILED", detail);
    let err = parse_gate(&body).expect_err("un gate rechazado debe fallar");
    assert_eq!(err, WizardError::ModelLoadFailed, "causa tipada nueva");

    let cause = take_gate_cause().expect("el portador debe sobrevivir al parseo");
    assert_eq!(cause.error, err);
    assert_eq!(cause.error_code.as_deref(), Some("E_MODEL_LOAD_FAILED"));
    assert_eq!(
        cause.detail.as_deref(),
        Some(detail),
        "sin truncar el detail"
    );
    assert!(
        cause.context().contains(detail),
        "el detalle llega al contexto del panel: {}",
        cause.context()
    );
    // El portador se consume una sola vez: ningún panel posterior hereda la causa.
    assert!(take_gate_cause().is_none());
}

#[test]
fn int_gate_errors_network_and_load_have_distinct_panel_codes() {
    // Fallo de red en el spawn: no hay JSON, el error tipado viaja tal cual.
    let net = GateCause::from(WizardError::NetDownload);
    let load_body = gate_failure("E_MODEL_LOAD_FAILED", "cuda: device not ready");
    parse_gate(&load_body).expect_err("gate rechazado");
    let load = take_gate_cause().expect("portador del gate");

    assert_ne!(net.error.exit_code(), load.error.exit_code());
    assert_ne!(
        net.context(),
        load.context(),
        "panel y log distinguen la causa"
    );
    assert!(
        load.context().contains("E_MODEL_LOAD_FAILED"),
        "el código del flow aparece en el panel: {}",
        load.context()
    );
    assert!(net.context().contains("download failed"));
}

#[test]
fn int_gate_errors_no_network_failure_is_model_invalid() {
    for code in ["E_MODEL_LOAD_FAILED", "E_NETWORK_ERROR", "E_MODEL_INVALID"] {
        let body = gate_failure(code, "detalle de carga");
        let err = parse_gate(&body).expect_err("gate rechazado");
        assert_ne!(
            err,
            WizardError::ModelInvalid,
            "un `ok:false` del gate nunca es el pre-filtro: {code}"
        );
        let cause = take_gate_cause().expect("portador del gate");
        assert!(
            !cause.context().contains("not an embedding model"),
            "el panel no puede mentir sobre la causa: {}",
            cause.context()
        );
    }
}

#[test]
fn int_gate_errors_unknown_or_absent_code_falls_back_to_load_failed() {
    // Códigos nuevos (o su ausencia) no pueden caer en el pre-filtro HF: el
    // fallback tipado es `ModelLoadFailed`, con o sin portador de causa.
    for body in [
        "{\"ok\":false,\"error_code\":\"E_FUTURO\",\"detail\":\"causa imprevista\"}",
        "{\"ok\":false,\"detail\":\"sin código\"}",
    ] {
        let err = parse_gate(body).expect_err("gate rechazado");
        assert_eq!(err, WizardError::ModelLoadFailed, "fallback: {body}");
        assert_ne!(err, WizardError::ModelInvalid, "nunca el pre-filtro");
        let cause = take_gate_cause().expect("portador del gate");
        assert_eq!(cause.error, WizardError::ModelLoadFailed);
    }
}

#[test]
fn int_gate_errors_garbled_gate_is_phase_failed_without_carrier() {
    let err = parse_gate("not json at all").expect_err("gate ilegible");
    assert_eq!(err, WizardError::PhaseFailed);
    assert!(
        take_gate_cause().is_none(),
        "un gate roto no tiene veredicto que portar"
    );
}
