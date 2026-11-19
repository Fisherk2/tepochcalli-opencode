//! H7 `update` end to end: the binary is spawned against a real vault.
//!
//! Pins the user-visible contract: exactly 5 scopes are overwritten (with
//! `.bak`), `.obsidian/`, `00-resources/`, `10-templates/` and the runtime
//! artifacts survive, a second run is a no-op, and a mid-flight failure
//! leaves the vault with its ORIGINAL bytes (rollback).

use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

fn bin() -> Command {
    Command::new(env!("CARGO_BIN_EXE_tepochcalli"))
}

fn tmp() -> tempfile::TempDir {
    tempfile::tempdir().expect("tempdir for the H7 fixtures")
}

fn write(root: &Path, rel: &str, body: &str) {
    let path = root.join(rel);
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).expect("fixture parent dir");
    }
    std::fs::write(path, body).expect("fixture write");
}

fn read(root: &Path, rel: &str) -> String {
    std::fs::read_to_string(root.join(rel)).expect("fixture read")
}

/// Payload fixture: the 5 scopes plus out-of-scope trees the update must
/// never copy (`00-resources/`, `10-templates/`, `.obsidian/`).
fn payload_fixture() -> tempfile::TempDir {
    let dir = tmp();
    write(dir.path(), ".opencode/agents/itzamna.md", "nuevo agente\n");
    write(
        dir.path(),
        ".tepochcalli/pyproject.toml",
        "version = \"0.1.0\"\n",
    );
    write(dir.path(), ".gitignore", "*.bak\n");
    write(dir.path(), "opencode.json", "{\"nuevo\": true}\n");
    write(dir.path(), "AGENTS.md", "# AGENTS nuevo\n");
    write(dir.path(), "00-resources/ejemplo.md", "# placeholder\n");
    write(dir.path(), "10-templates/base.md", "# plantilla\n");
    write(dir.path(), ".obsidian/app.json", "{}\n");
    dir
}

/// Vault fixture: old payload files + user material + runtime artifacts.
fn vault_fixture() -> tempfile::TempDir {
    let dir = tmp();
    write(dir.path(), ".opencode/agents/itzamna.md", "viejo agente\n");
    write(dir.path(), ".opencode/skills/vieja/SKILL.md", "solo aquí\n");
    write(
        dir.path(),
        ".tepochcalli/pyproject.toml",
        "version = \"0.0.9\"\n",
    );
    write(dir.path(), ".tepochcalli/venv/bin/python", "fake-python\n");
    write(dir.path(), ".tepochcalli/db/chunks.lance", "indice\n");
    write(dir.path(), ".gitignore", "/venv\n");
    write(dir.path(), "opencode.json", "{\"viejo\": true}\n");
    write(dir.path(), "AGENTS.md", "# AGENTS viejo\n");
    write(dir.path(), "00-resources/nota.md", "# mi nota\n");
    write(dir.path(), "10-templates/mia.md", "# mi plantilla\n");
    write(dir.path(), ".obsidian/app.json", "{\"theme\": \"dark\"}\n");
    dir
}

fn snapshot(root: &Path) -> Vec<(String, Vec<u8>)> {
    fn walk(dir: &Path, root: &Path, out: &mut Vec<(String, Vec<u8>)>) {
        let mut names: Vec<PathBuf> = std::fs::read_dir(dir)
            .expect("read fixture tree")
            .map(|entry| entry.expect("dir entry").path())
            .collect();
        names.sort();
        for path in names {
            if path.is_dir() {
                walk(&path, root, out);
            } else {
                let rel = path
                    .strip_prefix(root)
                    .expect("rel path")
                    .to_string_lossy()
                    .into_owned();
                out.push((rel, std::fs::read(&path).expect("read file")));
            }
        }
    }
    let mut out = Vec::new();
    walk(root, root, &mut out);
    out
}

fn run_update(vault: &Path, payload: &Path) -> std::process::Output {
    bin()
        .args([
            "update",
            "--vault",
            vault.to_str().expect("utf8 tmp"),
            "--payload",
            payload.to_str().expect("utf8 tmp"),
            "--non-interactive",
        ])
        .stdin(Stdio::null())
        .output()
        .expect("spawn binary")
}

#[test]
fn update_overwrites_the_five_scopes_and_keeps_everything_else() {
    let vault = vault_fixture();
    let payload = payload_fixture();

    let out = run_update(vault.path(), payload.path());
    assert_eq!(
        out.status.code(),
        Some(0),
        "stderr:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );

    // 1. Los 5 alcances quedan con el contenido del payload.
    assert_eq!(read(vault.path(), "AGENTS.md"), "# AGENTS nuevo\n");
    assert_eq!(read(vault.path(), "opencode.json"), "{\"nuevo\": true}\n");
    assert_eq!(read(vault.path(), ".gitignore"), "*.bak\n");
    assert_eq!(
        read(vault.path(), ".opencode/agents/itzamna.md"),
        "nuevo agente\n"
    );
    assert_eq!(
        read(vault.path(), ".tepochcalli/pyproject.toml"),
        "version = \"0.1.0\"\n"
    );

    // 2. Backup obligatorio del contenido anterior.
    assert_eq!(read(vault.path(), "AGENTS.md.bak"), "# AGENTS viejo\n");
    assert_eq!(
        read(vault.path(), "opencode.json.bak"),
        "{\"viejo\": true}\n"
    );
    assert_eq!(read(vault.path(), ".gitignore.bak"), "/venv\n");

    // 3. Un fichero que no viaja en el payload NO se borra (el update pisa
    //    ficheros, no sincroniza árboles): el runtime y las skills del usuario
    //    siguen ahí.
    assert_eq!(
        read(vault.path(), ".tepochcalli/venv/bin/python"),
        "fake-python\n"
    );
    assert_eq!(
        read(vault.path(), ".tepochcalli/db/chunks.lance"),
        "indice\n"
    );
    assert_eq!(
        read(vault.path(), ".opencode/skills/vieja/SKILL.md"),
        "solo aquí\n"
    );

    // 4. Fuera de alcance, intacto; y lo que el payload trae fuera de alcance
    //    no se copia.
    assert_eq!(read(vault.path(), "00-resources/nota.md"), "# mi nota\n");
    assert_eq!(
        read(vault.path(), "10-templates/mia.md"),
        "# mi plantilla\n"
    );
    assert_eq!(
        read(vault.path(), ".obsidian/app.json"),
        "{\"theme\": \"dark\"}\n"
    );
    assert!(!vault.path().join("00-resources/ejemplo.md").exists());
    assert!(!vault.path().join("10-templates/base.md").exists());

    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(
        stdout.contains("update:"),
        "el resumen sale en stdout:\n{stdout}"
    );
}

#[test]
fn second_update_is_a_noop() {
    let vault = vault_fixture();
    let payload = payload_fixture();
    assert_eq!(
        run_update(vault.path(), payload.path()).status.code(),
        Some(0)
    );
    let before = snapshot(vault.path());

    let out = run_update(vault.path(), payload.path());
    assert_eq!(
        out.status.code(),
        Some(0),
        "stderr:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
    assert_eq!(
        snapshot(vault.path()),
        before,
        "un segundo update idéntico no escribe nada (ni .bak nuevos)"
    );
    assert!(
        String::from_utf8_lossy(&out.stdout).contains("0"),
        "el resumen declara cero escrituras:\n{}",
        String::from_utf8_lossy(&out.stdout)
    );
}

#[test]
fn midway_failure_restores_the_original_vault() {
    let vault = vault_fixture();
    let payload = payload_fixture();
    // Trampa determinista: el payload trae `.opencode/agents/itzamna.md` como
    // fichero y el vault ya lo tiene como DIRECTORIO (fs::copy falla EISDIR).
    std::fs::remove_file(vault.path().join(".opencode/agents/itzamna.md"))
        .expect("remove fixture file");
    std::fs::create_dir_all(vault.path().join(".opencode/agents/itzamna.md")).expect("trap dir");
    write(
        vault.path(),
        ".opencode/agents/itzamna.md/hijo.md",
        "trampa\n",
    );
    let before = snapshot(vault.path());

    let out = run_update(vault.path(), payload.path());
    assert!(
        out.status.code().unwrap_or(0) != 0,
        "el update fallido no puede salir 0"
    );
    assert!(
        String::from_utf8_lossy(&out.stderr).contains("update"),
        "el panel nombra el comando:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
    assert_eq!(
        snapshot(vault.path()),
        before,
        "rollback: el vault queda byte a byte como estaba"
    );
}

#[test]
fn update_help_documents_its_flags() {
    let out = bin()
        .args(["update", "--help"])
        .output()
        .expect("spawn binary");
    assert_eq!(out.status.code(), Some(0));
    let text = String::from_utf8_lossy(&out.stdout);
    for flag in ["--vault", "--payload", "--payload-url", "--non-interactive"] {
        assert!(
            text.contains(flag),
            "update --help debe documentar `{flag}`:\n{text}"
        );
    }
}

#[test]
fn update_payload_flag_conflicts_are_usage_errors() {
    let out = bin()
        .args([
            "update",
            "--payload",
            "/tmp/x",
            "--payload-url",
            "http://127.0.0.1:1/dl",
            "--payload-sha256",
            "0",
        ])
        .stdin(Stdio::null())
        .output()
        .expect("spawn binary");
    assert_eq!(out.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&out.stderr).contains("--payload"));

    // URL sin SHA-256 (o al revés) tampoco se adivina.
    let out = bin()
        .args(["update", "--payload-url", "http://127.0.0.1:1/dl"])
        .stdin(Stdio::null())
        .output()
        .expect("spawn binary");
    assert_eq!(out.status.code(), Some(2));
}
