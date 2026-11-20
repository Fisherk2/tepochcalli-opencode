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

#[test]
fn install_sin_red_no_escribe_nada() {
    let dir = tempfile::tempdir().expect("tempdir");
    let vault = dir.path().join("vault");
    std::fs::create_dir_all(&vault).expect("vault vacío");

    let out = Command::new(env!("CARGO_BIN_EXE_tepochcalli"))
        .args([
            "install",
            "--non-interactive",
            "--vault",
            vault.to_str().expect("utf8 tmp"),
        ])
        .env("TEPOCHCALLI_RELEASE_BASE_URL", dead_base_url())
        // Los proxies del entorno no deben interceptar el loopback muerto.
        .env("NO_PROXY", "*")
        .env_remove("ALL_PROXY")
        .env_remove("all_proxy")
        .env_remove("HTTPS_PROXY")
        .env_remove("https_proxy")
        .env_remove("HTTP_PROXY")
        .env_remove("http_proxy")
        .output()
        .expect("spawn install");

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
    let url = format!("{}/p.tar.gz", dead_base_url());
    let sha = "0".repeat(64);

    let out = Command::new(env!("CARGO_BIN_EXE_tepochcalli"))
        .args([
            "update",
            "--non-interactive",
            "--vault",
            vault.to_str().expect("utf8 tmp"),
            "--payload-url",
            &url,
            "--payload-sha256",
            &sha,
        ])
        .env("NO_PROXY", "*")
        .env_remove("ALL_PROXY")
        .env_remove("all_proxy")
        .env_remove("HTTPS_PROXY")
        .env_remove("https_proxy")
        .env_remove("HTTP_PROXY")
        .env_remove("http_proxy")
        .output()
        .expect("spawn update");

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
        "sin red el update no escribe nada: ni .bak, ni .opencode/, ni opencode.json; \
         got {entries} entradas"
    );
}
