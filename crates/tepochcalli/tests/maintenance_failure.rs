//! T17 failure UX: `reindex`/`uninstall` share `main.rs::report_maintenance_failure`,
//! que hasta ahora no tenía ninguna aserción (solo el `report_failure` de
//! `install` estaba cubierto en `failure_ux.rs`). Aquí se fija contra el
//! binario real: título con el comando de verdad, log fuera del vault,
//! redacción de la clave path-4 en panel+log+ficheros, código de salida del
//! error tipado y ausencia de la línea de reintento de `install`.

use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

const API_KEY: &str = "sk-LEAK-TEST-7f3a9c2b-key-must-never-leak";
const INSTALL_RETRY: &str = "tepochcalli install --resume";
const MODEL: &str = "text-embedding-3-small";
/// Fichero del fixture que sí contiene la clave por construcción (config
/// gitignored donde `secrets_from_vault` la busca).
const CONFIG_REL: &str = ".tepochcalli/config/tepochcalli.toml";

fn bin() -> Command {
    Command::new(env!("CARGO_BIN_EXE_tepochcalli"))
}

fn stderr_text(output: &std::process::Output) -> String {
    String::from_utf8_lossy(&output.stderr).into_owned()
}

fn stdout_text(output: &std::process::Output) -> String {
    String::from_utf8_lossy(&output.stdout).into_owned()
}

/// Vault instalado con el proveedor externo (path 4): la clave vive en el
/// config gitignored, el sidecar conoce el modelo (sin drift, sin panel
/// `E_MODEL_MISMATCH` de ruido) y el refresh del flow revienta.
fn vault_with_api_key() -> tempfile::TempDir {
    let vault = tempfile::tempdir().expect("vault fixture");
    let rt = vault.path().join(".tepochcalli");
    for dir in ["config", "db", "models", "venv/bin"] {
        std::fs::create_dir_all(rt.join(dir)).expect("runtime dir fixture");
    }
    std::fs::write(
        rt.join("config").join("tepochcalli.toml"),
        format!(
            "[embedding]\nprovider = \"litellm\"\nmodel = \"{MODEL}\"\napi_key = \"{API_KEY}\"\n"
        ),
    )
    .expect("config fixture");
    std::fs::write(
        rt.join("db").join("index-meta.json"),
        format!("{{\"model\":\"{MODEL}\",\"dims\":1536}}\n"),
    )
    .expect("index-meta fixture");
    std::fs::write(rt.join("db").join("chunks.lance"), b"live-index-bytes")
        .expect("live index fixture");
    write_failing_python(&rt.join("venv").join("bin").join("python"));
    vault
}

/// Intérprete falso que siempre falla: el `refresh` del flow muere sin red,
/// sin Python real y sin descargar nada (determinista).
#[cfg(unix)]
fn write_failing_python(path: &Path) {
    use std::os::unix::fs::PermissionsExt as _;
    std::fs::write(path, "#!/bin/sh\nexit 1\n").expect("fake python fixture");
    std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o755))
        .expect("fake python executable");
}

/// Ruta del log tal como la imprime el panel (`log: <ruta>`).
fn log_path_from(stderr: &str) -> PathBuf {
    stderr
        .lines()
        .find_map(|line| line.trim().strip_prefix("log: "))
        .map(PathBuf::from)
        .unwrap_or_else(|| panic!("el panel debe llevar la ruta del log:\n{stderr}"))
}

/// Ficheros (relativos) cuyo contenido contiene `needle`; sirve para probar
/// que el fallo no escribe ningún artefacto nuevo con la clave.
fn files_containing(root: &Path, needle: &str) -> Vec<String> {
    fn walk(dir: &Path, root: &Path, needle: &str, out: &mut Vec<String>) {
        let entries = match std::fs::read_dir(dir) {
            Ok(entries) => entries,
            Err(_) => return,
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() {
                walk(&path, root, needle, out);
            } else if let Ok(body) = std::fs::read(&path) {
                if String::from_utf8_lossy(&body).contains(needle) {
                    out.push(
                        path.strip_prefix(root)
                            .expect("rel path")
                            .to_string_lossy()
                            .into_owned(),
                    );
                }
            }
        }
    }
    let mut out = Vec::new();
    walk(root, root, needle, &mut out);
    out.sort();
    out
}

#[cfg(unix)]
#[test]
fn reindex_failure_panel_names_reindex_and_never_leaks_api_key() {
    let vault = vault_with_api_key();
    let state = tempfile::tempdir().expect("state home fixture");
    let before = files_containing(vault.path(), API_KEY);
    assert_eq!(
        before,
        vec![CONFIG_REL.to_string()],
        "el fixture solo tiene la clave en su config"
    );

    let out = bin()
        .args([
            "reindex",
            "--confirm",
            "--non-interactive",
            "--vault",
            vault.path().to_str().expect("utf8 tmp"),
        ])
        .env("XDG_STATE_HOME", state.path())
        .env("LOCALAPPDATA", state.path())
        .stdin(Stdio::null())
        .output()
        .expect("spawn binary");

    // El refresh caído es `PhaseFailed` → 42, dentro del rango 40+ de §5.4.
    assert_eq!(
        out.status.code(),
        Some(42),
        "stderr:\n{}",
        stderr_text(&out)
    );
    let stderr = stderr_text(&out);
    assert!(
        stderr.contains("reindex failed"),
        "el panel debe nombrar el comando real:\n{stderr}"
    );
    assert!(
        stderr.contains("reindex"),
        "el panel debe nombrar `reindex`:\n{stderr}"
    );
    assert!(
        !stderr.contains(INSTALL_RETRY),
        "un fallo de reindex no puede ofrecer el reintento de install:\n{stderr}"
    );
    assert!(
        stdout_text(&out).is_empty(),
        "stdout debe quedar vacío en el fallo:\n{}",
        stdout_text(&out)
    );

    // Log fuera del vault, bajo el state base del hijo.
    let log = log_path_from(&stderr);
    assert!(
        log.starts_with(state.path()),
        "el log vive bajo el state dir del hijo, got: {}",
        log.display()
    );
    assert!(
        !log.starts_with(vault.path()),
        "el log nunca vive dentro del vault, got: {}",
        log.display()
    );
    assert!(log.is_file(), "el log debe existir: {}", log.display());

    // La clave no aparece en el panel ni en el log ni en ningún fichero del
    // vault más allá del config del fixture.
    assert!(!stderr.contains(API_KEY), "fuga en el panel:\n{stderr}");
    let logged = std::fs::read_to_string(&log).expect("log legible");
    assert!(!logged.contains(API_KEY), "fuga en el log:\n{logged}");
    assert_eq!(
        files_containing(vault.path(), API_KEY),
        before,
        "ningún artefacto nuevo puede contener la clave"
    );
}

#[test]
fn uninstall_failure_panel_names_uninstall_without_install_retry() {
    // `.tepochcalli` como fichero regular: `remove_dir_all` falla con
    // `NotADirectory` de forma determinista (también como root), sin depender
    // de permisos del sandbox.
    let vault = tempfile::tempdir().expect("vault fixture");
    let runtime = vault.path().join(".tepochcalli");
    std::fs::write(&runtime, b"not-a-directory").expect("runtime fixture");
    let state = tempfile::tempdir().expect("state home fixture");

    let out = bin()
        .args([
            "uninstall",
            "--non-interactive",
            "--vault",
            vault.path().to_str().expect("utf8 tmp"),
        ])
        .env("XDG_STATE_HOME", state.path())
        .env("LOCALAPPDATA", state.path())
        .stdin(Stdio::null())
        .output()
        .expect("spawn binary");

    // Fallo de fs → `PermissionDenied` → 31, dentro del rango 30-39 de §5.4.
    assert_eq!(
        out.status.code(),
        Some(31),
        "stderr:\n{}",
        stderr_text(&out)
    );
    let stderr = stderr_text(&out);
    assert!(
        stderr.contains("uninstall failed"),
        "el panel debe nombrar el comando real:\n{stderr}"
    );
    assert!(
        !stderr.contains(INSTALL_RETRY),
        "un fallo de uninstall no puede ofrecer el reintento de install:\n{stderr}"
    );
    assert!(
        stdout_text(&out).is_empty(),
        "stdout debe quedar vacío en el fallo:\n{}",
        stdout_text(&out)
    );

    let log = log_path_from(&stderr);
    assert!(
        log.starts_with(state.path()),
        "el log vive bajo el state dir del hijo, got: {}",
        log.display()
    );
    assert!(
        !log.starts_with(vault.path()),
        "el log nunca vive dentro del vault, got: {}",
        log.display()
    );
    assert!(log.is_file(), "el log debe existir: {}", log.display());

    // Cero efectos: el fichero que provocó el fallo sigue intacto.
    assert_eq!(
        std::fs::read(&runtime).expect("runtime legible"),
        b"not-a-directory"
    );
}
