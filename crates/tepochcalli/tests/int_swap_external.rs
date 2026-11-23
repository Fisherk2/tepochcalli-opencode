//! Swap atómico D8.4 (T16): proveedor de API externa e ids libres de
//! HuggingFace (metadata, `gated`, no-embeddings). Fakes y fixtures en
//! `common/swap_support.rs`.

#[allow(dead_code)]
mod common;

use common::gate_ok;
use common::swap_support::{
    argv, assert_byte_identical, assert_no_spawns, bodies, confirmed, empty_http, gated,
    http_serving, installed_vault, no_stray_temps, panel_mentions, refresh_ok, refreshed,
    run_swap_case, snapshot, titles, visible_text, EXTERNAL_MODEL, FAKE_KEY, GATED_ID, GATED_TOKEN,
};
use tepochcalli::domain::WizardError;
use tepochcalli::RagHealth;

/// GAP 2: el camino de API externa (índice 3) nunca se ejercitaba. La clave
/// viaja empaquetada como `model\0api_key` y solo `picked_config_body` la
/// separa; aquí se prueba que (a) cae exactamente una vez en la config, (b)
/// no sale por ningún panel, (c) no hay descarga/gate de dims y (d) el
/// sidecar conserva la forma documentada con `dims: null`.
#[test]
fn external_api_swap_writes_key_once_and_never_in_panel() {
    let vault = installed_vault();
    let rt = vault.path().join(".tepochcalli");
    let (result, ui, proc) = run_swap_case(
        vault.path(),
        vec![3],
        vec![EXTERNAL_MODEL.to_string(), FAKE_KEY.to_string()],
        vec![refresh_ok(2)],
        empty_http(),
        &confirmed(),
    );
    let report = result.expect("el swap a API externa debe triunfar sin descarga local");

    // (a) config: provider litellm, modelo y clave exactamente una vez.
    let config = std::fs::read_to_string(rt.join("config").join("tepochcalli.toml"))
        .expect("config tras el swap");
    assert!(
        config.contains("provider = \"litellm\""),
        "provider externo, got:\n{config}"
    );
    assert_eq!(
        config.matches(EXTERNAL_MODEL).count(),
        1,
        "el modelo aparece exactamente una vez, got:\n{config}"
    );
    assert_eq!(
        config.matches(FAKE_KEY).count(),
        1,
        "la clave aparece exactamente una vez, got:\n{config}"
    );
    assert_eq!(report.model, EXTERNAL_MODEL, "el reporte no lleva la clave");
    assert_eq!(report.dims, None, "el externo no tiene dims medidas");
    assert_eq!(report.health, RagHealth::Ok);

    // (b) la clave nunca sale por la UI (títulos, cuerpos ni prompts), y el
    // prompt en sí va por el canal sin eco (L2-7): la entrada de la API key
    // se registra como SECRET INPUT, no como INPUT.
    assert!(
        !visible_text(&ui).contains(FAKE_KEY),
        "la clave nunca puede aparecer en un panel (títulos/cuerpos/prompts)"
    );
    let secret_prompts = bodies(&ui)
        .iter()
        .enumerate()
        .filter(|(index, _)| titles(&ui)[*index].contains("SECRET INPUT"))
        .map(|(_, body)| body.clone())
        .collect::<Vec<_>>();
    assert!(
        secret_prompts
            .iter()
            .any(|body| body.contains("API key")),
        "el prompt de la API key debe ir por el canal sin eco (SECRET INPUT), prompts: {secret_prompts:?}"
    );
    assert!(
        !titles(&ui)
            .iter()
            .any(|t| t.starts_with("INPUT") && t.contains("API key")),
        "el prompt de la API key no puede ir por el canal con eco"
    );

    // (c) sin gate de dims: el externo no descarga; el re-index sí corre y
    // su hijo no recibe la clave (ni por env ni por argv).
    assert!(
        !gated(&proc),
        "el camino externo no corre el gate test-embed/dims, argv: {:?}",
        argv(&proc)
    );
    assert!(
        refreshed(&proc),
        "el re-index corre para el externo, argv: {:?}",
        argv(&proc)
    );
    for call in proc.calls() {
        assert!(
            call.env.iter().all(|(key, value)| key != "HF_TOKEN"
                && key != "TEPOCHCALLI_EMBED_API_KEY"
                && value != FAKE_KEY),
            "la clave no viaja en el env del hijo, got: {:?}",
            call.env
        );
    }
    assert!(
        !format!("{:?}", argv(&proc)).contains(FAKE_KEY),
        "la clave no viaja en argv"
    );

    // (d) forma documentada del sidecar para proveedor externo:
    // `{"model":<id>,"dims":null}` (misma que escribe F7/reindex, sin dims).
    let meta = std::fs::read_to_string(rt.join("db").join("index-meta.json"))
        .expect("sidecar tras el swap");
    assert_eq!(
        meta,
        format!("{{\"model\":\"{EXTERNAL_MODEL}\",\"dims\":null}}\n"),
        "forma del sidecar para provider externo"
    );
    no_stray_temps(vault.path());
}

/// GAP 2 (seguridad): una clave vacía no se escribe nunca. `ask_non_empty`
/// re-pregunta; con el guion agotado el swap aborta tipado antes de tocar
/// config, sidecar o lanzar gate/refresh.
#[test]
fn external_api_swap_with_empty_key_is_refused_before_writing() {
    let vault = installed_vault();
    let before = snapshot(vault.path());
    // Guion de procesos vacío: cualquier spawn devolvería Internal y delataría
    // que el swap siguió adelante sin clave.
    let (result, ui, proc) = run_swap_case(
        vault.path(),
        vec![3],
        vec![EXTERNAL_MODEL.to_string(), "   ".to_string()],
        vec![],
        empty_http(),
        &confirmed(),
    );
    let err = result.expect_err("sin clave el swap no puede escribir config");

    assert_eq!(
        err,
        WizardError::UserAborted,
        "el rechazo es tipado (re-pregunta agotada), nunca un half-swap"
    );
    assert!(
        panel_mentions(&ui, "Falta un dato"),
        "explica que el valor no puede ir vacío, títulos: {:?}",
        titles(&ui)
    );
    assert_byte_identical(vault.path(), &before);
    assert_no_spawns(&proc, "sin clave válida no se lanza gate ni refresh");
    no_stray_temps(vault.path());
}

/// GAP 5a: un repo de HF que no es de embeddings se rechaza ANTES de tocar
/// disco (pre-filtro D8.1 por `pipeline_tag`/tags ⇒ `E_MODEL_INVALID`).
#[test]
fn free_id_non_embedding_repo_aborts_with_model_invalid() {
    let vault = installed_vault();
    let before = snapshot(vault.path());
    let id = "microsoft/phi-3-mini-4k-instruct";
    let (result, ui, proc) = run_swap_case(
        vault.path(),
        vec![2],
        vec![id.to_string()],
        vec![],
        http_serving(
            id,
            "{\"tags\":[\"text-generation\"],\"pipeline_tag\":\"text-generation\"}",
        ),
        &confirmed(),
    );
    let err = result.expect_err("un repo no-embeddings debe abortar el swap");

    assert_eq!(err, WizardError::ModelInvalid);
    assert!(
        panel_mentions(&ui, "E_MODEL_INVALID"),
        "el código público se muestra al usuario, títulos: {:?}",
        titles(&ui)
    );
    assert_no_spawns(&proc, "ni descarga ni gate: el rechazo ocurre antes");
    assert_byte_identical(vault.path(), &before);
    no_stray_temps(vault.path());
}

/// GAP 5b: repo `gated` ⇒ se pide HF_TOKEN y viaja SOLO en el env del hijo
/// del gate (spec-embeddings §HF_TOKEN: nunca se loggea ni se persiste).
#[test]
fn free_id_gated_repo_passes_hf_token_only_to_child_env() {
    let vault = installed_vault();
    let rt = vault.path().join(".tepochcalli");
    let (result, ui, proc) = run_swap_case(
        vault.path(),
        vec![2, 0],
        vec![GATED_ID.to_string(), GATED_TOKEN.to_string()],
        vec![gate_ok(GATED_ID, 768, 1_500_000_000), refresh_ok(2)],
        http_serving(
            GATED_ID,
            "{\"tags\":[\"sentence-similarity\"],\"gated\":true}",
        ),
        &confirmed(),
    );
    let report = result.expect("un id gated con token debe completar el swap");

    assert_eq!(report.model, GATED_ID);
    assert_eq!(report.dims, Some(768));

    // El token llega al env del gate y a ningún otro hijo.
    let calls = proc.calls();
    assert_eq!(calls.len(), 2, "gate + refresh, argv: {:?}", argv(&proc));
    let gate = &calls[0];
    assert!(
        gate.args.iter().any(|arg| arg == "embed-check"),
        "la primera llamada es el gate, got: {:?}",
        gate.args
    );
    assert!(
        gate.env
            .contains(&("HF_TOKEN".to_string(), GATED_TOKEN.to_string())),
        "el gate recibe HF_TOKEN en su env, got: {:?}",
        gate.env
    );
    let refresh = &calls[1];
    assert!(
        refresh.env.iter().all(|(key, _)| key != "HF_TOKEN"),
        "el refresh no necesita el token, got: {:?}",
        refresh.env
    );

    // Ni panel, ni argv, ni config/sidecar: la única salida es el env del hijo.
    assert!(
        !visible_text(&ui).contains(GATED_TOKEN),
        "el token no aparece en ningún panel"
    );
    assert!(
        !format!("{:?}", argv(&proc)).contains(GATED_TOKEN),
        "el token nunca viaja en argv"
    );
    for file in ["config/tepochcalli.toml", "db/index-meta.json"] {
        let body = std::fs::read_to_string(rt.join(file)).expect("fichero escrito por el swap");
        assert!(
            !body.contains(GATED_TOKEN),
            "{file} no puede persistir el HF_TOKEN (solo la API key de la salida 4 se persiste)"
        );
    }
    assert!(
        std::fs::read_to_string(rt.join("config").join("tepochcalli.toml"))
            .expect("config")
            .contains(GATED_ID),
        "la config sí nombra el modelo elegido"
    );
    no_stray_temps(vault.path());
}

/// GAP 5c: metadata inalcanzable (404) degrada la estimación a «sin dato» —
/// nunca bloquea. Comportamiento intencionado (D8.1): la instalación no falla
/// por falta de red y el gate test-embed queda como única fuente de verdad.
#[test]
fn free_id_missing_metadata_proceeds_to_download() {
    let vault = installed_vault();
    let id = "acme/unlisted-embed";
    // Sin entradas: cualquier GET devuelve NetDownload (404/API caída).
    let (result, ui, proc) = run_swap_case(
        vault.path(),
        vec![2, 0],
        vec![id.to_string()],
        vec![gate_ok(id, 512, 900_000_000), refresh_ok(2)],
        empty_http(),
        &confirmed(),
    );
    let report = result.expect("sin metadatos de la API el swap sigue por el gate");

    assert_eq!(report.model, id);
    assert_eq!(report.dims, Some(512), "las dims las mide el gate");
    assert!(
        panel_mentions(&ui, "Sin estimación"),
        "explica que la estimación no llegó, títulos: {:?}",
        titles(&ui)
    );
    let calls = proc.calls();
    assert!(
        calls[0].args.iter().any(|arg| arg == "embed-check"),
        "la descarga se intenta igual, argv: {:?}",
        argv(&proc)
    );
    assert!(
        calls
            .iter()
            .flat_map(|call| call.env.iter())
            .all(|(key, _)| key != "HF_TOKEN"),
        "sin dato `gated` no se pide token, envs: {:?}",
        calls.iter().map(|call| &call.env).collect::<Vec<_>>()
    );
    no_stray_temps(vault.path());
}
