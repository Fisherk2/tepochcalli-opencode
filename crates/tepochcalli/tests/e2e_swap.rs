//! Swap atómico D8.4 (T16): `tepochcalli config embedder` sobre un vault
//! ya instalado.
//!
//! RED-first: todo aquí fallaba antes de que existiera
//! `application::swap::run_swap`. Vaults `tempfile` reales (D26: sin puerto
//! FS); solo fakes (`TapUi` de `common` que graba paneles, fakes de guion).
//! Ningún modelo se descarga: los fixtures `gate_ok`/`refresh_ok` replican
//! los contratos T11/T12. El soporte del contrato (vault con caches HF,
//! familias de aserción del GC, snapshot byte-idéntico, `CheckingProc`) vive
//! en `common/swap_support.rs`; aquí quedan solo los casos.

#[allow(dead_code)]
mod common;

use std::path::Path;

use common::swap_support::{
    argv, assert_byte_identical, assert_gc_outcome, assert_no_spawns, assert_old_slug_dirs_gone,
    assert_old_slug_dirs_present, assert_zero_state, bodies, config_inode, confirmed, db_listing,
    deps, empty_http, gated, http_serving, installed_vault, installed_vault_with, no_stray_temps,
    panel_mentions, refresh_ok, refreshed, run_swap_case, sidecar_becomes_nonempty_dir, snapshot,
    titles, visible_text, CheckingProc, EXTERNAL_MODEL, FAKE_KEY, GATED_ID, GATED_TOKEN, NEW_MODEL,
    OLD_MODEL, OLD_MODEL_ST,
};
use common::{gate_ok, host_16gb, DeadNetwork, RecordingProc, TapUi};
use tepochcalli::application::swap::{run_swap, SwapOptions};
use tepochcalli::domain::WizardError;
use tepochcalli::ports::CommandOutput;
use tepochcalli::RagHealth;

/// Spawn del binario real `config embedder` con `args` y el state home de
/// prueba (las 3 variantes del contrato `--vault` lo comparten).
fn run_embedder_cli(state: &Path, args: &[String]) -> std::process::Output {
    std::process::Command::new(env!("CARGO_BIN_EXE_tepochcalli"))
        .args(args)
        .env("XDG_STATE_HOME", state)
        .env("LOCALAPPDATA", state)
        .stdin(std::process::Stdio::null())
        .output()
        .expect("spawn binary")
}

#[test]
fn swap_success_runs_six_steps_in_order_and_purges_old_model() {
    let vault = installed_vault();
    let (result, ui, _proc) = run_swap_case(
        vault.path(),
        vec![1, 0],
        vec![],
        vec![gate_ok(NEW_MODEL, 1024, 3_000_000_000), refresh_ok(2)],
        empty_http(),
        &confirmed(),
    );
    let report = result.expect("el swap confirmado con gate+refresh OK debe triunfar");

    assert_eq!(report.model.as_str(), NEW_MODEL);
    assert_eq!(report.dims, Some(1024));

    // Paso 1→3→6: estado actual, menú, advertencia y cierre, en orden.
    let titles = titles(&ui);
    let pos = |needle: &str| {
        titles
            .iter()
            .position(|t| t.contains(needle))
            .unwrap_or_else(|| panic!("falta el paso «{needle}», títulos: {titles:?}"))
    };
    assert!(
        pos("Estado actual") < pos("MENU"),
        "el estado actual precede al menú, títulos: {titles:?}"
    );
    assert!(
        pos("MENU") < pos("re-index"),
        "la advertencia sigue al menú, títulos: {titles:?}"
    );
    assert!(
        pos("re-index") < pos("Swap completo"),
        "el cierre sigue a la advertencia, títulos: {titles:?}"
    );
    // El estado actual muestra modelo, dims y tamaño; la advertencia nombra
    // el re-index completo y exige --confirm con tiempo estimado.
    let bodies = bodies(&ui).join("\n");
    assert!(
        bodies.contains(OLD_MODEL),
        "el estado muestra el modelo viejo"
    );
    assert!(bodies.contains("384"), "el estado muestra las dims viejas");
    assert!(
        bodies.contains("--confirm"),
        "la advertencia exige --confirm"
    );

    // Conmutación atómica: config + sidecar nuevos, índice vivo intacto.
    let rt = vault.path().join(".tepochcalli");
    let config = std::fs::read_to_string(rt.join("config").join("tepochcalli.toml"))
        .expect("config tras el swap");
    assert!(
        config.contains(NEW_MODEL),
        "config conmutada, got:\n{config}"
    );
    // El swap pinea la revisión del preset (D59): sin ella el read path
    // resolvería otro snapshot que el que materializó el gate.
    assert!(
        config.contains("revision = \"5617a9f61b028005a4858fdac845db406aefb181\""),
        "la config debe pinear el SHA del preset, got:\n{config}"
    );
    let meta = std::fs::read_to_string(rt.join("db").join("index-meta.json"))
        .expect("sidecar tras el swap");
    assert!(
        meta.contains(NEW_MODEL) && meta.contains("1024"),
        "got:\n{meta}"
    );
    assert_eq!(
        std::fs::read(rt.join("db").join("chunks.lance")).expect("índice vivo"),
        b"live-index-bytes",
        "el índice viejo sigue servible tras el éxito"
    );
    // Auto-GC: solo los slug dirs HF del modelo viejo se purgan (ambas
    // raíces); el decoy del esquema antiguo, la caché no relacionada y la
    // caché del modelo nuevo sobreviven. Sin fugas de temporales.
    assert_gc_outcome(vault.path(), OLD_MODEL, NEW_MODEL, true);
}

#[test]
fn swap_missing_confirm_explains_and_mutates_nothing() {
    let vault = installed_vault();
    let before = snapshot(vault.path());
    // Guion vacío: cualquier spawn devuelve `Internal` y revienta el test,
    // luego `Ok` aquí prueba que sin --confirm nada se descarga ni reindexa.
    let (result, ui, _proc) = run_swap_case(
        vault.path(),
        vec![1, 0],
        vec![],
        vec![],
        empty_http(),
        &SwapOptions {
            confirm: false,
            keep_previous: false,
        },
    );
    let err = result.expect_err("sin --confirm el swap no debe correr");
    assert_eq!(err, WizardError::UserAborted);

    let bodies = bodies(&ui).join("\n");
    assert!(
        bodies.contains("--confirm"),
        "debe explicar que el re-index exige --confirm, got:\n{bodies}"
    );
    assert!(
        bodies.to_lowercase().contains("irreversible"),
        "debe advertir que el re-index es irreversible, got:\n{bodies}"
    );
    assert_zero_state(vault.path(), &before);
}

/// R-offline-1 (T13): sin red el preflight del swap corta ANTES de
/// `write_config` — ni la config elegida se escribe, ni se lanza el gate.
#[test]
fn swap_sin_red_no_escribe_ni_la_config() {
    let vault = installed_vault();
    let before = snapshot(vault.path());
    let db = db_listing(vault.path());
    let inode = config_inode(vault.path());
    let ui = TapUi::new(vec![1, 0], vec![]);
    let host = host_16gb();
    // Guion vacío: si el flujo llegara al gate, `RecordingProc` devolvería
    // `Internal` y el error no sería `NetDownload`.
    let proc = RecordingProc::scripted(vec![]);
    let result = run_swap(
        &deps(&ui, &host, &proc, &DeadNetwork),
        vault.path(),
        &confirmed(),
    );

    assert_eq!(
        result.expect_err("sin red no se escribe nada"),
        WizardError::NetDownload
    );
    // Cero escritura: config, índice, cache vieja, db/ y spawns intactos.
    assert_zero_state(vault.path(), &before);
    assert_eq!(db_listing(vault.path()), db, "db/ sin ficheros nuevos");
    assert_eq!(config_inode(vault.path()), inode, "config sin reescribir");
    assert_no_spawns(&proc, "sin red no se llega al gate test-embed");
}

#[test]
fn swap_interrupted_download_rolls_back_to_zero_state() {
    let vault = installed_vault();
    let before = snapshot(vault.path());
    let (result, _ui, _proc) = run_swap_case(
        vault.path(),
        vec![1, 0],
        vec![],
        vec![Err(WizardError::NetDownload)],
        empty_http(),
        &confirmed(),
    );
    let err = result.expect_err("la descarga interrumpida debe fallar el swap");
    assert_eq!(err, WizardError::NetDownload);

    // Cambio de estado cero: config/índice/modelo byte-idénticos, índice
    // viejo legible (servable) y sin temporales.
    assert_zero_state(vault.path(), &before);
}

#[test]
fn swap_failed_refresh_rolls_back_to_zero_state() {
    let vault = installed_vault();
    let before = snapshot(vault.path());
    let (result, _ui, _proc) = run_swap_case(
        vault.path(),
        vec![1, 0],
        vec![],
        vec![
            gate_ok(NEW_MODEL, 1024, 3_000_000_000),
            Err(WizardError::PhaseFailed),
        ],
        empty_http(),
        &confirmed(),
    );
    let err = result.expect_err("el refresh fallido debe fallar el swap");
    assert_eq!(err, WizardError::PhaseFailed);

    assert_zero_state(vault.path(), &before);
}

#[test]
fn swap_rejected_gate_rolls_back_to_zero_state() {
    let vault = installed_vault();
    let before = snapshot(vault.path());
    let (result, _ui, _proc) = run_swap_case(
        vault.path(),
        vec![1, 0],
        vec![],
        vec![Ok(CommandOutput {
            status: 0,
            stdout: "{\"ok\":false,\"code\":\"E_MODEL_INVALID\"}".to_string(),
            stderr: String::new(),
        })],
        empty_http(),
        &confirmed(),
    );
    let err = result.expect_err("el gate rechazado debe fallar el swap");
    assert_eq!(err, WizardError::ModelInvalid);

    assert_zero_state(vault.path(), &before);
}

#[test]
fn swap_keep_previous_retains_old_model() {
    let vault = installed_vault();
    let (result, _ui, _proc) = run_swap_case(
        vault.path(),
        vec![1, 0],
        vec![],
        vec![gate_ok(NEW_MODEL, 1024, 3_000_000_000), refresh_ok(2)],
        empty_http(),
        &SwapOptions {
            confirm: true,
            keep_previous: true,
        },
    );
    let report = result.expect("--keep-previous debe triunfar igual");

    assert_eq!(report.model.as_str(), NEW_MODEL);
    assert_gc_outcome(vault.path(), OLD_MODEL, NEW_MODEL, false);
    let config = std::fs::read_to_string(
        vault
            .path()
            .join(".tepochcalli")
            .join("config")
            .join("tepochcalli.toml"),
    )
    .expect("config tras el swap");
    assert!(
        config.contains(NEW_MODEL),
        "la conmutación ocurre igual, got:\n{config}"
    );
}

#[test]
fn swap_live_files_untouched_while_replacement_runs() {
    let vault = installed_vault();
    let (_, meta, index, model, decoy) = snapshot(vault.path());
    let ui = TapUi::new(vec![1, 0], vec![]);
    let host = host_16gb();
    let proc = CheckingProc::scripted([gate_ok(NEW_MODEL, 1024, 3_000_000_000), refresh_ok(2)]);
    proc.expect_live(vault.path(), NEW_MODEL, &meta, &index, &model, &decoy);

    run_swap(
        &deps(&ui, &host, &proc, &empty_http()),
        vault.path(),
        &confirmed(),
    )
    .expect("el swap debe triunfar con el índice viejo servable");

    // Pin del auditor (C1): la config capturada EN EL SPAWN del refresh
    // (segunda llamada) ya lleva el modelo nuevo; la vieja ya no está.
    let captured = proc.configs_seen();
    assert_eq!(captured.len(), 2, "gate + refresh, dos spawns");
    assert!(
        captured[1].contains(NEW_MODEL),
        "el spawn del refresh ve la config viva con el nuevo modelo, got:\n{}",
        captured[1]
    );
    assert!(
        !captured[1].contains(OLD_MODEL),
        "la config vieja ya no está mientras el refresh corre"
    );
}

#[test]
fn swap_gc_maps_org_qualified_id_to_slug_dirs() {
    // RED: el GC viejo sanitizaba `BAAI/bge-m3` a `BAAI_bge-m3` y nunca
    // tocaba `models--BAAI--bge-m3/`; este test falla hasta el fix.
    let vault = installed_vault_with(NEW_MODEL, &[OLD_MODEL]);
    let (result, _ui, _proc) = run_swap_case(
        vault.path(),
        vec![0, 0],
        vec![],
        vec![gate_ok(OLD_MODEL, 384, 1_000_000_000), refresh_ok(2)],
        empty_http(),
        &confirmed(),
    );
    let report = result.expect("el swap desde un id con org debe triunfar");

    assert_eq!(report.model.as_str(), OLD_MODEL);
    assert_gc_outcome(vault.path(), NEW_MODEL, OLD_MODEL, true);
}

#[test]
fn swap_gc_maps_st_qualified_id_to_both_slug_variants() {
    // Un id `sentence-transformers/...` comparte caché con su forma escueta:
    // el GC debe purgar ambas variantes bajo ambas raíces.
    let vault = installed_vault_with(OLD_MODEL_ST, &[NEW_MODEL]);
    let (result, _ui, _proc) = run_swap_case(
        vault.path(),
        vec![1, 0],
        vec![],
        vec![gate_ok(NEW_MODEL, 1024, 3_000_000_000), refresh_ok(2)],
        empty_http(),
        &confirmed(),
    );
    let report = result.expect("el swap desde un id sentence-transformers debe triunfar");

    assert_eq!(report.model.as_str(), NEW_MODEL);
    assert_old_slug_dirs_gone(vault.path(), OLD_MODEL_ST);
    // La variante escueta pertenece a la misma familia: también se purga.
    assert_old_slug_dirs_gone(vault.path(), OLD_MODEL);
    assert_gc_outcome(vault.path(), OLD_MODEL_ST, NEW_MODEL, true);
}

/// GAP 12: `config embedder` comparte el contrato de `--vault` con el resto de
/// subcomandos — `--vault X` ≡ `--vault=X`, y un `--vault` sin valor es error
/// de uso (exit 2) sin efectos. El vault del fixture no tiene intérprete
/// ejecutable: el gate muere con `PhaseFailed` (42), lo que prueba que el
/// directorio se resolvió desde el flag (sin él sería `UserAborted`, 41).
#[test]
fn config_embedder_accepts_both_vault_forms_and_rejects_valueless_flag() {
    let state = tempfile::tempdir().expect("state home fixture");
    for form in ["--vault", "--vault="] {
        let vault = installed_vault();
        let path = vault.path().to_str().expect("utf8 tmp").to_string();
        let mut args: Vec<String> = ["config", "embedder", "--non-interactive", "--confirm"]
            .iter()
            .map(|s| (*s).to_string())
            .collect();
        if form == "--vault" {
            args.push("--vault".to_string());
            args.push(path);
        } else {
            args.push(format!("--vault={path}"));
        }
        let out = run_embedder_cli(state.path(), &args);
        let stderr = String::from_utf8_lossy(&out.stderr);
        assert_eq!(out.status.code(), Some(42), "args {args:?}:\n{stderr}");
        assert!(
            stderr.contains("config embedder failed"),
            "el swap debe haber corrido con el vault del flag, args {args:?}:\n{stderr}"
        );
        assert!(
            !stderr.contains("vault selection failed"),
            "el flag no debe ignorarse, args {args:?}:\n{stderr}"
        );
    }

    // `--vault` sin valor: error de uso explicado, cero efectos.
    let vault = installed_vault();
    let before = snapshot(vault.path());
    let out = run_embedder_cli(
        state.path(),
        &[
            "config".to_string(),
            "embedder".to_string(),
            "--non-interactive".to_string(),
            "--confirm".to_string(),
            "--vault".to_string(),
        ],
    );
    assert_eq!(
        out.status.code(),
        Some(2),
        "un --vault sin valor es error de uso:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(
        stderr.contains("--vault") && stderr.contains("needs a value"),
        "explica el flag sin valor, got:\n{stderr}"
    );
    assert!(
        out.stdout.is_empty(),
        "un error de uso no imprime nada en stdout"
    );
    assert_zero_state(vault.path(), &before);
}

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

/// E1-S3 (C1): un sabotaje de la escritura VIVA de la config (el `.tmp`
/// ocupado por un directorio ⇒ rename falla) comparte el mismo abort del
/// resto de ramas: rollback a los bytes previos y cero estado, jamás un
/// half-swap.
#[test]
fn swap_live_config_write_failure_rolls_back_to_zero_state_like_the_other_branches() {
    let vault = installed_vault();
    let rt = vault.path().join(".tepochcalli");
    std::fs::create_dir(rt.join("config").join("tepochcalli.toml.tmp"))
        .expect("sabotaje del staging .tmp");
    let before = snapshot(vault.path());
    // Guion vacío: si el swap intentara gate/refresh, fallaría con Internal
    // y delataría que un write-config fallido no abortó a tiempo.
    let (result, _ui, proc) = run_swap_case(
        vault.path(),
        vec![0, 0],
        vec![],
        vec![],
        empty_http(),
        &confirmed(),
    );
    let err = result.expect_err("el staging saboteado debe abortar el swap");
    assert_eq!(err, WizardError::PermissionDenied);
    assert_byte_identical(vault.path(), &before);
    assert_no_spawns(&proc, "un stage que falla no llega a ningún spawn");
    // El dir saboteador sobrevive por construcción (`remove_file` no borra
    // dirs); los demás temporales no quedan.
    for candidate in [
        rt.join("db").join("index-meta.json").with_extension("tmp"),
        rt.join("db").join("index-meta.json.swap"),
    ] {
        assert!(
            !candidate.exists(),
            "temporal fugado: {}",
            candidate.display()
        );
    }
}

/// GAP 3: «Configurar después» (índice 4) nunca se ejercitaba en el swap.
///
/// Estado que deja, pineado explícitamente: **no** hay gate ni refresh (el
/// índice vivo queda byte-idéntico, servible), la config pasa a
/// `provider = "none"` y el sidecar `index-meta.json` SIGUE describiendo el
/// índice viejo (modelo y dims). Eso es deliberado y correcto: el sidecar
/// describe las filas que hay en disco, que nadie reconstruyó; quien decide
/// el estado RAG es la config (`none` ⇒ `rag_status` degraded / E_NO_EMBEDDER),
/// así que un lector no lee el sidecar como si hubiera un embedder activo.
#[test]
fn swap_to_configure_later_keeps_meta_describing_the_old_index_and_never_refreshes() {
    let vault = installed_vault();
    let rt = vault.path().join(".tepochcalli");
    let before = snapshot(vault.path());
    let (result, _ui, proc) = run_swap_case(
        vault.path(),
        vec![4],
        vec![],
        vec![],
        empty_http(),
        &confirmed(),
    );
    let report = result.expect("«Configurar después» debe completarse sin índice");

    // (a) nada se descarga ni se reindexa: el índice vivo queda intacto.
    assert_no_spawns(&proc, "la salida 5 no lanza gate ni refresh");
    assert!(!gated(&proc) && !refreshed(&proc));
    assert_eq!(
        std::fs::read(rt.join("db").join("chunks.lance")).expect("índice vivo"),
        before.2,
        "el índice vivo no se toca"
    );

    // (b) la config refleja la salida 5: sin provider local y sin modelo.
    let config = std::fs::read_to_string(rt.join("config").join("tepochcalli.toml"))
        .expect("config tras el swap");
    assert!(
        config.contains("provider = \"none\""),
        "config en modo none, got:\n{config}"
    );
    assert!(
        !config.contains("model ="),
        "ningún modelo a medias en la config, got:\n{config}"
    );
    assert_eq!(report.health, RagHealth::Degraded);
    assert_eq!(report.dims, None);
    assert_eq!(report.model, "", "la salida 5 no nombra modelo");
    assert_eq!(
        report.rows, 2,
        "sin re-index el conteo sigue siendo el del db previo (2 ficheros)"
    );

    // (c) el sidecar sigue describiendo el índice viejo (pin del estado real).
    let meta = std::fs::read_to_string(rt.join("db").join("index-meta.json"))
        .expect("sidecar tras el swap");
    assert_eq!(
        meta,
        String::from_utf8(before.1).expect("meta utf8"),
        "sin re-index el sidecar sigue describiendo el índice viejo (modelo y dims): \
         la config `none` es la que manda para rag_status"
    );
    assert!(
        meta.contains(OLD_MODEL) && meta.contains("384"),
        "pin explícito del estado que un lector de rag_status encontraría, got:\n{meta}"
    );
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

/// GAP 4: la ventana entre los dos renames del `commit`. La config ya
/// conmutada no puede sobrevivir a un fallo del segundo rename: `run_swap`
/// hace rollback y la config vuelve byte-idéntica (el índice y los modelos ni
/// se tocaron, así que siguen intactos por construcción).
///
/// Fallo forzado elegido: el destino del sidecar es un **directorio no vacío**
/// ⇒ `rename(2)` devuelve `EISDIR` y la operación falla igual como uid 1000 y
/// como root (un `chmod 0555` no vale: root lo atraviesa; y montar un FS de
/// solo lectura no es portable en CI).
#[test]
fn swap_meta_rename_failure_restores_config_byte_identical() {
    let vault = installed_vault();
    let rt = vault.path().join(".tepochcalli");
    let config_before = std::fs::read(rt.join("config").join("tepochcalli.toml")).expect("config");
    let index_before = std::fs::read(rt.join("db").join("chunks.lance")).expect("índice vivo");
    // El sidecar pasa a ser un directorio con contenido: el rename final muere.
    sidecar_becomes_nonempty_dir(&rt);
    let meta_path = rt.join("db").join("index-meta.json");

    let (result, _ui, _proc) = run_swap_case(
        vault.path(),
        vec![1, 0],
        vec![],
        vec![gate_ok(NEW_MODEL, 1024, 3_000_000_000), refresh_ok(2)],
        empty_http(),
        &confirmed(),
    );
    let err = result.expect_err("un fallo en el segundo rename debe fallar el swap");
    assert_eq!(
        err,
        WizardError::PermissionDenied,
        "error tipado, no un Ok a medias"
    );
    assert!(
        (30..=39).contains(&err.exit_code()),
        "un fallo de FS cae en el rango 30-39, got {}",
        err.exit_code()
    );

    // Cero cambio de estado en lo vivo: config byte-idéntica, índice servable.
    assert_eq!(
        std::fs::read(rt.join("config").join("tepochcalli.toml")).unwrap_or_default(),
        config_before,
        "la config debe volver byte-idéntica al snapshot pre-swap (ausente ⇒ difiere)"
    );
    assert_eq!(
        std::fs::read(rt.join("db").join("chunks.lance")).expect("índice tras el fallo"),
        index_before,
        "el índice viejo sigue servable"
    );
    assert_eq!(
        std::fs::read(meta_path.join("marker")).expect("sidecar tras el fallo"),
        b"unreadable-sidecar",
        "el rollback no destruye lo que no pudo fotografiar"
    );
    assert_old_slug_dirs_present(vault.path(), OLD_MODEL);
    no_stray_temps(vault.path());
}

/// Mismo fallo del segundo rename, pero con la config **ausente** de partida
/// (vault degradado al que se le añade por primera vez un embedder): el rollback
/// no puede inventarse un fichero. Estado final: sin config, sidecar intacto y
/// cero `.swap` en el vault.
#[test]
fn swap_meta_rename_failure_keeps_an_absent_config_absent() {
    let vault = installed_vault();
    let rt = vault.path().join(".tepochcalli");
    std::fs::remove_file(rt.join("config").join("tepochcalli.toml")).expect("config fuera");
    sidecar_becomes_nonempty_dir(&rt);
    let meta_path = rt.join("db").join("index-meta.json");

    let (result, _ui, _proc) = run_swap_case(
        vault.path(),
        vec![1, 0],
        vec![],
        vec![gate_ok(NEW_MODEL, 1024, 3_000_000_000), refresh_ok(2)],
        empty_http(),
        &confirmed(),
    );
    let err = result.expect_err("un fallo en el segundo rename debe fallar el swap");
    assert_eq!(err, WizardError::PermissionDenied);
    assert!(
        !rt.join("config").join("tepochcalli.toml").exists(),
        "config ausente antes del swap debe seguir ausente"
    );
    assert_eq!(
        std::fs::read(meta_path.join("marker")).expect("sidecar tras el fallo"),
        b"unreadable-sidecar",
        "el rollback no destruye lo que no pudo fotografiar"
    );
    no_stray_temps(vault.path());
}

/// GAP 11a: swap al MISMO modelo (el preset default ya vigente y cacheado).
/// Intencionado: `docs/APPFLOW.md` journey (f) paso 5 y
/// `specs/spec-embeddings.md` §Procedimiento de swap purgan el modelo
/// **anterior** tras un re-index exitoso; si el "anterior" es el vigente,
/// borrarlo dejaría el índice vivo sin embedder de consulta (otra descarga de
/// 470MB, o `E_OFFLINE_NO_CACHE` sin red).
#[test]
fn swap_to_the_same_model_does_not_purge_models() {
    let vault = installed_vault();
    let rt = vault.path().join(".tepochcalli");
    let (result, _ui, _proc) = run_swap_case(
        vault.path(),
        vec![0, 0],
        vec![],
        vec![gate_ok(OLD_MODEL, 384, 1_000_000_000), refresh_ok(2)],
        empty_http(),
        &confirmed(),
    );
    let report = result.expect("re-elegir el mismo modelo debe completar el swap");

    assert_eq!(report.model, OLD_MODEL);
    // El swap se completa igual (conmutación), solo se salta la purga.
    assert_gc_outcome(vault.path(), OLD_MODEL, OLD_MODEL, false);
    assert!(
        std::fs::read_to_string(rt.join("config").join("tepochcalli.toml"))
            .expect("config tras el swap")
            .contains(OLD_MODEL),
        "el swap se completa igual (conmutación, no purga)"
    );
}

/// GAP 11b: swap a `none` («Configurar después»). Intencionado que la caché
/// del modelo viejo sobreviva: el journey (f) de `docs/APPFLOW.md` y
/// `specs/spec-embeddings.md` §Procedimiento de swap solo purgan tras un
/// re-index exitoso con el modelo nuevo, y aquí no hubo re-index
/// (`swap_to_configure_later_...` pinea que el sidecar sigue describiendo el
/// índice viejo). `models/` sigue siendo el embedder que `search` necesita
/// para embeber consultas: purgarlo rompería las lecturas del índice vivo.
#[test]
fn swap_to_none_keeps_the_previous_model_cache() {
    let vault = installed_vault();
    let (result, _ui, _proc) = run_swap_case(
        vault.path(),
        vec![4],
        vec![],
        vec![],
        empty_http(),
        &confirmed(),
    );
    let report = result.expect("«Configurar después» debe completarse sin índice");
    assert_eq!(report.health, RagHealth::Degraded);
    assert_gc_outcome(vault.path(), OLD_MODEL, OLD_MODEL, false);
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

/// TD-47 / ADR-015 §4.4 (c): un `device` escrito a mano sobrevive a la
/// re-entrada `config embedder`. Aceptar la preselección reescribe el MISMO
/// valor — el swap deja de ser destructivo con la elección manual.
#[test]
fn swap_preserves_a_hand_written_device() {
    let vault = installed_vault();
    let config = vault
        .path()
        .join(".tepochcalli")
        .join("config")
        .join("tepochcalli.toml");
    // Elección manual fuera del catálogo (`cuda:N`): el caso que ADR-015 cita.
    std::fs::write(
        &config,
        "[embedding]\nprovider = \"local\"\nmodel = \"paraphrase-multilingual-MiniLM-L12-v2\"\ndevice = \"cuda:0\"\n",
    )
    .expect("config con device manual");
    let (result, ui, _proc) = run_swap_case(
        vault.path(),
        vec![0, 1],
        vec![],
        vec![gate_ok(OLD_MODEL, 384, 1_000_000_000), refresh_ok(2)],
        empty_http(),
        &confirmed(),
    );
    result.expect("el swap local debe completarse conservando el device");

    // Opciones ["cpu", "cuda:0"] con la elección manual preseleccionada.
    let select = ui
        .events()
        .into_iter()
        .find_map(|event| match event {
            common::UiEvent::Select {
                prompt,
                options,
                default,
            } if prompt.contains("Dispositivo") => Some((options, default)),
            _ => None,
        })
        .expect("la re-entrada pregunta el dispositivo");
    assert_eq!(select.0, vec!["cpu".to_string(), "cuda:0".to_string()]);
    assert_eq!(select.1, 1, "cuda:0 va preseleccionado");

    let after = std::fs::read_to_string(&config).expect("config tras el swap");
    assert!(
        after.contains("device = \"cuda:0\""),
        "el device manual sobrevive a la re-entrada, got:\n{after}"
    );
}
