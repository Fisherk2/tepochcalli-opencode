//! Swap atómico D8.4 (T16): el `commit` de la conmutación — fallos de
//! escritura/rename con rollback, salidas «Configurar después» y el mismo
//! modelo, y la conservación del `device` manual (TD-47/ADR-015).
//! Fakes y fixtures en `common/swap_support.rs`.

mod common;

use common::gate_ok;
use common::swap_support::{
    assert_byte_identical, assert_gc_outcome, assert_no_spawns, assert_old_slug_dirs_present,
    confirmed, empty_http, gated, installed_vault, no_stray_temps, refresh_ok, refreshed,
    run_swap_case, sidecar_becomes_nonempty_dir, snapshot, NEW_MODEL, OLD_MODEL,
};
use tepochcalli::domain::WizardError;
use tepochcalli::RagHealth;

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
