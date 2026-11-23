//! Swap atómico D8.4 (T16): caminos del flujo que acaban en éxito o en
//! rollback a estado cero. Fakes y fixtures en `common/swap_support.rs`.

mod common;

use common::swap_support::{
    assert_gc_outcome, assert_no_spawns, assert_old_slug_dirs_gone, assert_zero_state, bodies,
    config_inode, confirmed, db_listing, deps, empty_http, installed_vault, installed_vault_with,
    refresh_ok, run_swap_case, snapshot, titles, CheckingProc, NEW_MODEL, OLD_MODEL, OLD_MODEL_ST,
};
use common::{gate_ok, host_16gb, DeadNetwork, RecordingProc, TapUi};
use tepochcalli::application::swap::{run_swap, SwapOptions};
use tepochcalli::domain::WizardError;
use tepochcalli::ports::CommandOutput;

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

/// R-offline-2/3 (T14/T15): cancelar el gate (descarga abortada por el
/// usuario) no deja un snapshot de modelo nuevo — ni config conmutada.
#[test]
fn swap_cancelado_en_el_gate_no_deja_modelo_parcial() {
    // Solo el modelo viejo cacheado: cualquier dir del nuevo sería un parcial.
    let vault = installed_vault_with(OLD_MODEL, &[]);
    let before = snapshot(vault.path());
    let models = vault.path().join(".tepochcalli").join("models");
    let listing = || {
        let mut names: Vec<String> = std::fs::read_dir(&models)
            .expect("models legible")
            .map(|entry| {
                entry
                    .expect("entrada legible")
                    .file_name()
                    .to_string_lossy()
                    .into_owned()
            })
            .collect();
        names.sort();
        names
    };
    let names_before = listing();

    // Fila 1 (bge-m3, local) y el gate devuelve `UserAborted`: la descarga
    // se corta antes de materializar el snapshot.
    let (result, _ui, _proc) = run_swap_case(
        vault.path(),
        vec![1, 0],
        vec![],
        vec![Err(WizardError::UserAborted)],
        empty_http(),
        &confirmed(),
    );
    assert_eq!(
        result.expect_err("la cancelación del gate debe abortar el swap"),
        WizardError::UserAborted
    );

    assert_zero_state(vault.path(), &before);
    assert_eq!(listing(), names_before, "no queda ningún modelo parcial");
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
