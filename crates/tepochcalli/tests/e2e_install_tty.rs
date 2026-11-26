//! T5 — evidencia de la ruta TTY: con un PTY real el menú entra en full-screen
//! (`ratatui::try_init`); con pipes el binario aborta tipado y nunca dibuja.
//! El PTY lo provee `script(1)` de util-linux — sin dependencias Rust nuevas.

mod common;

use std::io::{Read, Write};
use std::path::Path;
use std::process::{Command, Stdio};
use std::sync::mpsc;
use std::time::{Duration, Instant};

/// Texto del banner que el frame full-screen dibuja (domain/menu.rs `READY_NOTICE`).
const SCREEN_MARKER: &str = "directorio listo para instalar";

/// Corre el menú bajo `script(1)`: la tecla de salida se envía cuando el frame
/// aparece, no tras un sleep. Sin frame, se mata el hijo y falla — nunca queda
/// un proceso huérfano esperando una tecla.
fn run_menu_in_pty(vault: &Path) -> (Option<i32>, String) {
    let mut child = Command::new("script")
        .args([
            "-qec",
            "stty rows 24 cols 80; exec \"$T5_BIN\" --vault \"$T5_VAULT\"",
            "/dev/null",
        ])
        .env("T5_BIN", env!("CARGO_BIN_EXE_tepochcalli"))
        .env("T5_VAULT", vault)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .expect("spawn script(1) PTY");

    let mut stdout = child.stdout.take().expect("stdout pipe");
    let (tx, rx) = mpsc::channel();
    let reader = std::thread::spawn(move || {
        let mut bytes = Vec::new();
        let mut buf = [0u8; 4096];
        let mut announced = false;
        loop {
            match stdout.read(&mut buf) {
                Ok(0) | Err(_) => break,
                Ok(n) => {
                    bytes.extend_from_slice(&buf[..n]);
                    if !announced && String::from_utf8_lossy(&bytes).contains(SCREEN_MARKER) {
                        announced = true;
                        let _ = tx.send(bytes.clone());
                    }
                }
            }
        }
        bytes
    });

    let mut stdin = child.stdin.take().expect("stdin pipe");
    let rendered = rx.recv_timeout(Duration::from_secs(15)).is_ok();
    if rendered {
        let _ = stdin.write_all(b"q");
    }
    drop(stdin);

    let deadline = Instant::now() + Duration::from_secs(10);
    let status = loop {
        match child.try_wait().expect("poll script") {
            Some(status) => break status.code(),
            None if Instant::now() < deadline => std::thread::sleep(Duration::from_millis(50)),
            None => {
                let _ = child.kill();
                let _ = child.wait();
                panic!("script(1) no terminó tras la tecla de salida");
            }
        }
    };
    let bytes = reader.join().expect("reader thread");
    (status, String::from_utf8_lossy(&bytes).into_owned())
}

#[test]
fn tty_menu_renders_full_screen_under_a_real_pty() {
    let vault = tempfile::tempdir().expect("vault fixture");
    let (status, output) = run_menu_in_pty(vault.path());

    assert!(
        output.contains(SCREEN_MARKER),
        "el frame full-screen debe dibujarse con TTY; salida: {output:?}"
    );
    assert!(
        output.contains("\u{1b}[?1049h"),
        "ratatui debe entrar en alternate screen (try_init); salida: {output:?}"
    );
    assert!(
        output.contains("Install") && output.contains("Exit"),
        "el menú H5 debe ofrecer Install y Exit; salida: {output:?}"
    );
    assert!(
        !output.contains("no TTY detected"),
        "la ruta PTY no debe caer en el fallback; salida: {output:?}"
    );
    assert_eq!(status, Some(0), "salir con `q` debe cerrar limpio");
}
