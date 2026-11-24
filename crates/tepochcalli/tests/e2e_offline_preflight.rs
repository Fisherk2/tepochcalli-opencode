//! R-offline-1 (T13) e2e: sin red el wizard sale tipado ANTES de tocar el
//! vault — cero ficheros, ni `.tepochcalli/`.

use std::net::TcpListener;
use std::process::Command;

use tepochcalli::WizardError;

/// Un puerto loopback cerrado como base de releases: sin red real, sin DNS.
fn dead_base_url() -> String {
    let port = TcpListener::bind("127.0.0.1:0")
        .expect("bind a port to close")
        .local_addr()
        .expect("loopback addr")
        .port();
    format!("http://127.0.0.1:{port}")
}

/// Los proxies del entorno no deben interceptar el loopback de los tests
/// (misma regla que los tests hermanos de este fichero, en forma de helper):
/// `NO_PROXY` cubre todo y el resto de `*PROXY` se retira del hijo.
fn scrub_proxies(cmd: &mut Command) {
    cmd.env("NO_PROXY", "*");
    for var in [
        "ALL_PROXY",
        "all_proxy",
        "HTTPS_PROXY",
        "https_proxy",
        "HTTP_PROXY",
        "http_proxy",
    ] {
        cmd.env_remove(var);
    }
}

#[test]
fn install_sin_red_no_escribe_nada() {
    let dir = tempfile::tempdir().expect("tempdir");
    let vault = dir.path().join("vault");
    std::fs::create_dir_all(&vault).expect("vault vacío");

    let mut cmd = Command::new(env!("CARGO_BIN_EXE_tepochcalli"));
    cmd.args([
        "install",
        "--non-interactive",
        "--vault",
        vault.to_str().expect("utf8 tmp"),
    ])
    .env("TEPOCHCALLI_RELEASE_BASE_URL", dead_base_url());
    // Los proxies del entorno no deben interceptar el loopback muerto.
    scrub_proxies(&mut cmd);
    let out = cmd.output().expect("spawn install");

    let stderr = String::from_utf8_lossy(&out.stderr);
    assert_eq!(
        out.status.code(),
        Some(i32::from(WizardError::NetDownload.exit_code())),
        "stderr:\n{stderr}"
    );
    assert!(
        stderr.contains("preflight") && stderr.contains("download failed"),
        "el fallo debe nombrar el preflight y la causa de red, got:\n{stderr}"
    );
    let entries = std::fs::read_dir(&vault).expect("vault readable").count();
    assert_eq!(
        entries, 0,
        "sin red no se escribe nada: ni .tepochcalli/ ni marcas, got {entries} entradas"
    );
}

/// R-offline-1 (T13) en H7: el override `--payload-url` es la única rama del
/// update sin preflight de facto, así que su sonda corta antes del write.
#[test]
fn update_sin_red_no_escribe_nada() {
    let dir = tempfile::tempdir().expect("tempdir");
    let vault = dir.path().join("vault");
    std::fs::create_dir_all(&vault).expect("vault vacío");
    // H7 solo actualiza un workspace instalado: el runtime es el gate de uso.
    std::fs::create_dir_all(vault.join(".tepochcalli")).expect("runtime");
    std::fs::write(
        vault.join(".tepochcalli/pyproject.toml"),
        "version = \"0.0.9\"\n",
    )
    .expect("runtime fixture");
    let url = format!("{}/p.tar.gz", dead_base_url());
    let sha = "0".repeat(64);

    let mut cmd = Command::new(env!("CARGO_BIN_EXE_tepochcalli"));
    cmd.args([
        "update",
        "--non-interactive",
        "--vault",
        vault.to_str().expect("utf8 tmp"),
        "--payload-url",
        &url,
        "--payload-sha256",
        &sha,
    ]);
    scrub_proxies(&mut cmd);
    let out = cmd.output().expect("spawn update");

    let stderr = String::from_utf8_lossy(&out.stderr);
    assert_eq!(
        out.status.code(),
        Some(i32::from(WizardError::NetDownload.exit_code())),
        "stderr:\n{stderr}"
    );
    assert!(
        stderr.contains("preflight") && stderr.contains("download failed"),
        "el fallo debe nombrar el preflight y la causa de red, got:\n{stderr}"
    );
    let entries = std::fs::read_dir(&vault).expect("vault readable").count();
    assert_eq!(
        entries, 1,
        "sin red el update no escribe nada: ni .bak, ni .opencode/, ni opencode.json; \
         got {entries} entradas"
    );
    assert!(!vault.join("AGENTS.md.bak").exists());
    assert!(!vault.join(".gitignore").exists());
}

/// Hueco #2 — R-offline-1 (T13) en H6: el override `--payload-url` es la
/// rama de `install` que alcanzaría su primer write sin red por otro lado,
/// así que su sonda corta en el preflight ANTES de tocar el vault.
///
/// Regresión que detecta: si el wiring del preflight de H6 desapareciera
/// (o `payload_endpoint` dejara de devolver el override), el fallo llegaría
/// en F3 con contexto `phase F3` — no `preflight` — tras haber entrado en
/// la fase que escribe. El exit 20 por sí solo no basta: F3 moriría con el
/// mismo código.
#[test]
fn install_con_payload_url_muerto_corta_en_preflight_sin_tocar_el_vault() {
    let dir = tempfile::tempdir().expect("tempdir");
    let vault = dir.path().join("vault");
    std::fs::create_dir_all(&vault).expect("vault vacío");
    let url = format!("{}/p.tar.gz", dead_base_url());
    let sha = "0".repeat(64);

    let mut cmd = Command::new(env!("CARGO_BIN_EXE_tepochcalli"));
    cmd.args([
        "install",
        "--non-interactive",
        "--vault",
        vault.to_str().expect("utf8 tmp"),
        "--payload-url",
        &url,
        "--payload-sha256",
        &sha,
    ]);
    scrub_proxies(&mut cmd);
    let out = cmd.output().expect("spawn install");

    let stderr = String::from_utf8_lossy(&out.stderr);
    assert_eq!(
        out.status.code(),
        Some(i32::from(WizardError::NetDownload.exit_code())),
        "stderr:\n{stderr}"
    );
    assert!(
        stderr.contains("preflight") && stderr.contains("download failed"),
        "el fallo debe nombrar el preflight y la causa de red, got:\n{stderr}"
    );
    let entries = std::fs::read_dir(&vault).expect("vault readable").count();
    assert_eq!(
        entries, 0,
        "sin red el install no escribe nada: ni .tepochcalli/ ni marcas, got {entries} entradas"
    );
}

/// Hueco #11(a) — R-offline-1 (T13) en H7: `--payload` local NO sondea —
/// el update aplica el payload con la red totalmente caída (base de
/// releases apuntando a un puerto muerto + proxies muertos).
///
/// Regresión que detecta: si la rama local de `update` empezara a resolver
/// el payload de release (o a sondear con la release URL), moriría en el
/// preflight (contexto `preflight`, exit 20) en vez de aplicar el payload;
/// la base de releases muerta hace determinista que cualquier intento de
/// red falle en lugar de pasar por accidente en una máquina con red.
#[test]
fn update_con_payload_local_y_red_muerta_lo_aplica() {
    let dir = tempfile::tempdir().expect("tempdir");
    let vault = dir.path().join("vault");
    let payload = dir.path().join("payload");
    std::fs::create_dir_all(&vault).expect("vault");
    std::fs::create_dir_all(&payload).expect("payload");
    // H7 solo actualiza un workspace instalado: el runtime es el gate de uso.
    std::fs::create_dir_all(vault.join(".tepochcalli")).expect("runtime");
    std::fs::write(
        vault.join(".tepochcalli/pyproject.toml"),
        "version = \"0.0.9\"\n",
    )
    .expect("runtime fixture");
    std::fs::write(vault.join("AGENTS.md"), "# AGENTS viejo\n").expect("vault fixture");
    std::fs::write(payload.join("AGENTS.md"), "# AGENTS nuevo\n").expect("payload fixture");

    let mut cmd = Command::new(env!("CARGO_BIN_EXE_tepochcalli"));
    cmd.args([
        "update",
        "--non-interactive",
        "--vault",
        vault.to_str().expect("utf8 tmp"),
        "--payload",
        payload.to_str().expect("utf8 tmp"),
    ])
    .env("TEPOCHCALLI_RELEASE_BASE_URL", dead_base_url());
    scrub_proxies(&mut cmd);
    let out = cmd.output().expect("spawn update");

    let stderr = String::from_utf8_lossy(&out.stderr);
    assert_eq!(
        out.status.code(),
        Some(0),
        "un payload local no necesita red, stderr:\n{stderr}"
    );
    assert!(
        !stderr.contains("preflight"),
        "la rama local no puede sondear, got:\n{stderr}"
    );
    assert_eq!(
        std::fs::read_to_string(vault.join("AGENTS.md")).expect("AGENTS aplicado"),
        "# AGENTS nuevo\n",
        "el payload local se aplica aunque la red esté caída"
    );
    assert_eq!(
        std::fs::read_to_string(vault.join("AGENTS.md.bak")).expect("backup del update"),
        "# AGENTS viejo\n",
        "el update respalda antes de pisar"
    );
}

/// Hueco #1 — R-offline-1 (T13): `--offline` OMITE la sonda. La ventana
/// con endpoint `Some` es un `--offline --resume` cuyo F3 está resuelto
/// por artefacto y SIN `--payload`/`--payload-url`: el endpoint es la
/// release URL (aquí, un puerto muerto), el guard pasa por el brazo
/// resume y el install completa en 0.
///
/// Regresión que detecta: si el término `!offline` desapareciera de la
/// condición del preflight (`cli/install.rs`), la sonda mataría el install
/// con contexto `preflight` y exit 20 en vez de terminar en 0 — con la
/// base de releases muerta el fallo sería determinista.
///
/// Fixture: el de `offline_resume_with_litellm_config_does_not_veto`
/// (`e2e_install_atomicity.rs`) — litellm + artefactos F3..F8 ⇒ guard en
/// verde y todas las fases saltan.
#[test]
fn install_offline_con_endpoint_de_release_no_sondea() {
    let dir = tempfile::tempdir().expect("tempdir");
    let vault = dir.path().join("vault");
    let rt = vault.join(".tepochcalli");
    std::fs::create_dir_all(rt.join("config")).expect("config dir");
    std::fs::create_dir_all(rt.join("db")).expect("db dir");
    std::fs::create_dir_all(rt.join("bin")).expect("bin dir");
    std::fs::create_dir_all(rt.join("venv").join("bin")).expect("venv bin dir");
    std::fs::write(rt.join("bin").join("uv"), b"fake-uv").expect("uv artifact");
    std::fs::write(
        rt.join("venv").join("bin").join("python"),
        b"#!/bin/sh\nexit 0\n",
    )
    .expect("venv artifact");
    std::fs::write(rt.join(".install-intent"), b"AGENTS.md\n").expect("intent artifact");
    std::fs::write(
        rt.join("config").join("tepochcalli.toml"),
        "[embedding]\nprovider = \"litellm\"\nmodel = \"openai/emb\"\napi_key = \"sk-fake\"\n",
    )
    .expect("config artifact");
    std::fs::write(
        rt.join("db").join("index-meta.json"),
        b"{\"model\":\"openai/emb\",\"dims\":null}\n",
    )
    .expect("meta artifact");
    std::fs::write(
        vault.join("opencode.json"),
        b"{\"mcp\": {\"servers\": {\"tepochcalli-rag\": {}}}}\n",
    )
    .expect("f8 artifact");
    assert!(!rt.join("models").exists(), "el pin exige models/ ausente");

    let mut cmd = Command::new(env!("CARGO_BIN_EXE_tepochcalli"));
    cmd.args([
        "install",
        "--non-interactive",
        "--offline",
        "--resume",
        "--vault",
        vault.to_str().expect("utf8 tmp"),
    ])
    // Endpoint = release URL: si la sonda corriera, moriría en este puerto.
    .env("TEPOCHCALLI_RELEASE_BASE_URL", dead_base_url());
    scrub_proxies(&mut cmd);
    let out = cmd.output().expect("spawn install --offline --resume");

    let stderr = String::from_utf8_lossy(&out.stderr);
    assert_eq!(
        out.status.code(),
        Some(0),
        "--offline con el guard en verde no puede fallar, stderr:\n{stderr}"
    );
    assert!(
        !stderr.contains("preflight"),
        "`--offline` debe omitir la sonda, got:\n{stderr}"
    );
    assert!(
        stderr.contains("resume: F3 already done"),
        "F3 por artefacto ⇒ endpoint Some pero sin sonda, got:\n{stderr}"
    );
}
