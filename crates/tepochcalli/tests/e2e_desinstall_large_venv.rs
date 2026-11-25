//! T19: desinstall sobre un venv sintético grande (muchas entradas anidadas y
//! un symlink que sale del vault). RED-first: los contadores deterministas
//! `entries_removed`/`workers_used` no existen todavía en `UninstallReport`.
//!
//! Dos pruebas complementarias: el binario real completa H8 sin tocar el
//! material del usuario ni el destino externo, y la llamada de biblioteca
//! expone la evidencia numérica del borrado acotado.

mod common;

use std::path::{Path, PathBuf};
use std::process::Stdio;

use common::helpers::{bin, stderr_text};
use common::TapUi;
use tepochcalli::application::maintenance::run_uninstall;

const BACKUP_PREFIX: &str = ".tepochcalli-backup-";

/// Vault con tres scopes, un venv sintético de cientos de entradas y un
/// symlink saliente; devuelve también el material que debe quedar intacto.
struct Fixture {
    vault: tempfile::TempDir,
    outside: tempfile::TempDir,
    outside_bytes: Vec<u8>,
    user_files: Vec<(String, Vec<u8>)>,
    scope_entries: u64,
}

/// Cuenta entradas reales sin seguir symlinks (un enlace cuenta como una).
fn count_entries(path: &Path) -> u64 {
    let kind = std::fs::symlink_metadata(path)
        .expect("entrada del fixture")
        .file_type();
    if !kind.is_dir() {
        return 1;
    }
    std::fs::read_dir(path)
        .expect("lectura del fixture")
        .map(|entry| count_entries(&entry.expect("dir entry").path()))
        .sum::<u64>()
        + 1
}

/// Instantánea ordenada de los ficheros del usuario (nada de scopes ni backup).
fn user_snapshot(vault: &Path) -> Vec<(String, Vec<u8>)> {
    let watched = [
        "AGENTS.md",
        "00-resources/nota.md",
        "00-resources/paper.pdf",
        ".obsidian/app.json",
        "10-templates/mia.md",
    ];
    watched
        .iter()
        .map(|rel| {
            let path = vault.join(rel);
            (
                rel.to_string(),
                std::fs::read(&path).expect("fichero de usuario"),
            )
        })
        .collect()
}

fn backup_dir(vault: &Path) -> PathBuf {
    std::fs::read_dir(vault)
        .expect("vault legible")
        .filter_map(|entry| entry.ok())
        .map(|entry| entry.path())
        .find(|path| {
            path.file_name()
                .is_some_and(|name| name.to_string_lossy().starts_with(BACKUP_PREFIX))
        })
        .expect("el backup con nombre se crea antes de borrar")
}

fn fixture() -> Fixture {
    let vault = tempfile::tempdir().expect("vault temporal");
    let outside = tempfile::tempdir().expect("destino externo al vault");
    let outside_bytes = b"material externo: no se toca\n".to_vec();
    std::fs::write(outside.path().join("secreto.txt"), &outside_bytes).expect("destino externo");

    // .opencode/ con anidamiento.
    let agents = vault.path().join(".opencode/agents");
    std::fs::create_dir_all(&agents).expect("fixture .opencode");
    for name in ["itzamna.md", "tlacuilo.md"] {
        std::fs::write(agents.join(name), "# agente\n").expect("agente");
    }

    // .tepochcalli/ con venv sintético: 4 paquetes × 8 módulos × 8 ficheros.
    let runtime = vault.path().join(".tepochcalli");
    let config = runtime.join("config");
    std::fs::create_dir_all(&config).expect("fixture config");
    std::fs::write(
        config.join("tepochcalli.toml"),
        "[embedding]\nprovider = \"none\"\n",
    )
    .expect("config fixture");
    std::fs::write(runtime.join("pyproject.toml"), "version = \"0.1.0\"\n")
        .expect("manifest fixture");
    let packages = runtime.join("venv/lib/python3.12/site-packages");
    for package in 0..4 {
        for module in 0..8 {
            let dir = packages.join(format!("pkg{package}/mod{module}"));
            std::fs::create_dir_all(&dir).expect("fixture venv");
            for file in 0..8 {
                std::fs::write(dir.join(format!("f{file}.py")), b"# modulo\n")
                    .expect("fichero venv");
            }
        }
    }
    #[cfg(unix)]
    std::os::unix::fs::symlink(outside.path(), runtime.join("venv/enlace-saliente"))
        .expect("symlink saliente");

    std::fs::write(vault.path().join("opencode.json"), "{}\n").expect("opencode.json");

    // Material del usuario: jamás entra en el alcance de H8.
    std::fs::create_dir_all(vault.path().join("00-resources")).expect("resources");
    std::fs::write(vault.path().join("00-resources/nota.md"), "# nota\n").expect("nota");
    std::fs::write(
        vault.path().join("00-resources/paper.pdf"),
        b"%PDF-1.4\npaper binario\n",
    )
    .expect("pdf");
    std::fs::create_dir_all(vault.path().join(".obsidian")).expect("obsidian");
    std::fs::write(vault.path().join(".obsidian/app.json"), "{}\n").expect("app.json");
    std::fs::write(vault.path().join("AGENTS.md"), "# AGENTS\n").expect("AGENTS");
    std::fs::create_dir_all(vault.path().join("10-templates")).expect("templates");
    std::fs::write(vault.path().join("10-templates/mia.md"), "# plantilla\n").expect("plantilla");

    let user_files = user_snapshot(vault.path());
    let scope_entries =
        count_entries(vault.path().join(".opencode").as_path()) + count_entries(runtime.as_path());
    Fixture {
        vault,
        outside,
        outside_bytes,
        user_files,
        scope_entries,
    }
}

fn assert_aftermath(fixture: &Fixture) {
    let vault = fixture.vault.path();
    for scope in [".opencode", ".tepochcalli", "opencode.json"] {
        assert!(!vault.join(scope).exists(), "{scope} debe desaparecer");
    }
    assert_eq!(
        user_snapshot(vault),
        fixture.user_files,
        "notas, PDF, .obsidian/ y AGENTS.md byte-idénticos"
    );
    assert_eq!(
        std::fs::read(fixture.outside.path().join("secreto.txt")).expect("destino externo intacto"),
        fixture.outside_bytes,
        "el symlink saliente nunca se sigue"
    );
    let backup = backup_dir(vault);
    assert!(
        backup.join(".opencode/agents/itzamna.md").is_file()
            && backup
                .join(".tepochcalli/config/tepochcalli.toml")
                .is_file()
            && backup.join("opencode.json").is_file(),
        "el backup conserva lo irreemplazable"
    );
    assert!(
        !backup.join(".tepochcalli/venv").exists(),
        "venv es regenerable: no viaja al backup"
    );
    assert_eq!(
        std::fs::read_to_string(backup.join(".gitignore")).expect("auto-ignore"),
        "*\n"
    );
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt as _;
        let mode = std::fs::metadata(&backup)
            .expect("backup")
            .permissions()
            .mode();
        assert_eq!(mode & 0o077, 0, "backup 0700, got {mode:o}");
        let marker = std::fs::metadata(backup.join(".gitignore"))
            .expect("marker")
            .permissions()
            .mode();
        assert_eq!(marker & 0o077, 0, "marker 0600, got {marker:o}");
    }
}

#[test]
fn e2e_desinstall_large_venv_through_binary_keeps_user_and_external_files() {
    let fixture = fixture();
    let vault = fixture.vault.path().to_str().expect("utf8 tmp");
    let out = bin()
        .args([
            "uninstall",
            "--vault",
            vault,
            "--confirm",
            "--non-interactive",
        ])
        .stdin(Stdio::null())
        .output()
        .expect("spawn del binario");
    assert_eq!(out.status.code(), Some(0), "{}", stderr_text(&out));
    assert_aftermath(&fixture);
}

#[test]
fn e2e_desinstall_large_venv_reports_deterministic_removal_counters() {
    let fixture = fixture();
    let ui = TapUi::new(vec![], vec![]);
    let report = run_uninstall(&ui, fixture.vault.path()).expect("uninstall triunfa");
    assert!(report.removed);
    assert_aftermath(&fixture);
    assert_eq!(
        report.entries_removed, fixture.scope_entries,
        "contador determinista de entradas borradas en los dos scopes directorio"
    );
    assert_eq!(
        report.workers_used, 8,
        "paralelismo acotado a 8 workers con trabajo de sobra"
    );
}
