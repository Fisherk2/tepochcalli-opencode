//! `config embedder` sobre el binario real: contrato de `--vault` (GAP 12).
//!
//! Único target del split del swap con spawn: el resto quedó en `int_swap_*`.
//! El hijo nace con la red tirada (ver `run_embedder_cli`).

mod common;

use std::path::Path;

use common::swap_support::{assert_zero_state, installed_vault, snapshot};

/// Spawn del binario real `config embedder` con `args` y el state home de
/// prueba (las 3 variantes del contrato `--vault` lo comparten).
///
/// El hijo nace con la red TIRADA: `ureq` lee el proxy del env
/// (`Proxy::try_from_env`, `ALL_PROXY` primero), el puerto es un loopback
/// cerrado y `NO_PROXY` se retira, así que la sonda HF del preflight de H9
/// (T13) —su primer uso de red— muere igual con o sin red en el host. Sin
/// eso el test pasaba «por casualidad» con red viva (exit 42) y fallaba en
/// `just rust-test-nonet` (exit 20).
fn run_embedder_cli(state: &Path, args: &[String]) -> std::process::Output {
    std::process::Command::new(env!("CARGO_BIN_EXE_tepochcalli"))
        .args(args)
        .env("XDG_STATE_HOME", state)
        .env("LOCALAPPDATA", state)
        .env("ALL_PROXY", "http://127.0.0.1:1")
        .env("HTTPS_PROXY", "http://127.0.0.1:1")
        .env_remove("NO_PROXY")
        .env_remove("no_proxy")
        .stdin(std::process::Stdio::null())
        .output()
        .expect("spawn binary")
}

/// GAP 12: `config embedder` comparte el contrato de `--vault` con el resto de
/// subcomandos — `--vault X` ≡ `--vault=X`, y un `--vault` sin valor es error
/// de uso (exit 2) sin efectos.
///
/// Hermeticidad: el hijo nace con la red tirada (`run_embedder_cli`), así que
/// la sonda HF del preflight de H9 (`swap.rs:173`) —su primer uso de red—
/// muere con `NetDownload` (20) ANTES de `write_config` y antes del gate. Por
/// eso el exit ya no es 42: el 42 lo daba el gate test-embed (el vault del
/// fixture no tiene intérprete ejecutable) y el preflight lo corta antes.
///
/// Regresión que detecta: si el preflight de H9 volviera a tocar la red viva,
/// este test dejaría de ser determinista —con red el hijo llegaría al gate y
/// saldría con 42 en vez de 20 (fallaría en `rust-ci`, pasaría en `nonet`).
///
/// Discriminador de GAP 12: 41-vs-no-41, no 42-vs-41. Si el flag `--vault` no
/// resolviera el directorio, aparecería el panel «vault selection failed» (41);
/// el exit 20 con «config embedder failed» prueba que el directorio llegó desde
/// el flag y el swap corrió (sin flag, el cwd tampoco pregunta nada).
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
        // Medido con proxies muertos: la sonda HF del preflight (T13) es el
        // primer uso de red y falla antes del gate ⇒ `NetDownload` (20).
        assert_eq!(out.status.code(), Some(20), "args {args:?}:\n{stderr}");
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
