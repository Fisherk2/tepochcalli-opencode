//! #9: `run_progress` promete degradar a `work()` ante cualquier fallo de
//! terminal, pero `ratatui::init()` paniquea. El hijo corre bajo `setsid`
//! (sesión sin terminal de control) con stdin null ⇒ `tty_fd()` falla en
//! `/dev/tty` ⇒ `init()` espera y revienta HOY; con `try_init()` degrada.

#[cfg(target_os = "linux")] // setsid es de util-linux; Windows/macOS: deuda declarada
#[test]
fn run_progress_sin_terminal_de_control_degrada_a_work() {
    if std::env::var_os("TEPOCHCALLI_PROGRESS_CHILD").is_some() {
        // --- hijo (bajo setsid, stdin null) ---
        let cancel = tepochcalli::domain::CancelToken::new();
        let mut ran = false;
        tepochcalli::adapters::ui_ratatui::run_progress("hijo", &cancel, &mut || ran = true);
        assert!(ran, "work() debe ejecutarse aunque la terminal falle");
        println!("WORK_RAN"); // marcador de éxito para el padre
        return;
    }
    // --- padre: sesión nueva sin ctty, stdin null, filtrando SOLO este test ---
    let out = std::process::Command::new("setsid")
        .args([
            "-w",
            std::env::current_exe()
                .expect("test bin")
                .to_str()
                .expect("utf8"),
            "run_progress_sin_terminal_de_control_degrada_a_work",
            "--exact",
            "--nocapture",
        ])
        .env("TEPOCHCALLI_PROGRESS_CHILD", "1")
        .stdin(std::process::Stdio::null())
        .output();
    let out = match out {
        Ok(out) => out,
        Err(err) => {
            eprintln!("skipped: `setsid` not available (TD-64): {err}");
            return;
        }
    };
    // El hijo sin ctty igual escupe el escape de restore (ESC[?1049l) por su
    // stdout capturado: se filtra el byte ESC para que el mensaje del assert
    // no lo reenvíe a la terminal del padre.
    let stdout: String = String::from_utf8_lossy(&out.stdout)
        .chars()
        .filter(|c| *c != '\u{1b}')
        .collect();
    let stderr: String = String::from_utf8_lossy(&out.stderr)
        .chars()
        .filter(|c| *c != '\u{1b}')
        .collect();
    assert!(
        out.status.success(),
        "el hijo debe degradar a work(), no paniquear.\nstdout:\n{stdout}\nstderr:\n{stderr}"
    );
    assert!(stdout.contains("WORK_RAN"), "work() no corrió:\n{stdout}");
}
