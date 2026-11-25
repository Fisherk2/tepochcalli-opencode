//! T5: real adapters behind the T4 ports (`std_proc`, `http`, `host`).
//!
//! Proc and HTTP tests run against the real OS / loopback only — no
//! internet, no shell spawned by the adapter, no `unwrap` in `src/`.

mod common;

use std::io::{Read, Write};
use std::net::TcpListener;
use std::path::PathBuf;
use std::thread;

use common::helpers::sha256_hex;
use tepochcalli::adapters::{find_tool_in, StdCommandRunner, SysHostProbe, UreqHttpClient};
use tepochcalli::ports::{CommandRunner, HostProbe, HttpClient};
use tepochcalli::WizardError;

// --- `StdCommandRunner` (real `std::process`, no shell) ---

#[cfg(unix)]
#[test]
fn proc_passes_env_and_captures_split_streams() {
    let runner = StdCommandRunner;
    let dir = tempfile::tempdir().expect("tempdir");
    // `sh` is the *explicit* child program here; the adapter itself never
    // wraps anything in `sh -c` (AC-a: no shell unless the caller asks).
    let out = runner
        .run(
            "sh",
            &["-c", "echo $TEPOCHCALLI_PROBE; echo warn >&2"],
            dir.path(),
            &[("TEPOCHCALLI_PROBE", "hello-t5")],
        )
        .expect("sh runs");
    assert_eq!(out.status, 0);
    assert_eq!(out.stdout, "hello-t5\n");
    assert_eq!(out.stderr, "warn\n");
}

#[cfg(unix)]
#[test]
fn proc_reports_nonzero_exit_without_error() {
    let runner = StdCommandRunner;
    let dir = tempfile::tempdir().expect("tempdir");
    let out = runner
        .run("sh", &["-c", "exit 3"], dir.path(), &[])
        .expect("exit code is data, not failure");
    assert_eq!(out.status, 3);
}

#[test]
fn proc_missing_binary_is_typed_error() {
    let runner = StdCommandRunner;
    let dir = tempfile::tempdir().expect("tempdir");
    let err = runner
        .run("tepochcalli-no-such-binary-t5", &[], dir.path(), &[])
        .expect_err("spawn failure must surface typed");
    assert_eq!(err, WizardError::PhaseFailed);
}

// --- `UreqHttpClient` (real HTTP over loopback only) ---

/// Serve `body` once on 127.0.0.1; returns the URL to GET.
fn serve_once(body: Vec<u8>) -> (String, std::thread::JoinHandle<()>) {
    let listener = TcpListener::bind("127.0.0.1:0").expect("bind loopback");
    let port = listener.local_addr().expect("local addr").port();
    let handle = std::thread::spawn(move || {
        let (mut stream, _) = listener.accept().expect("accept one conn");
        let mut buf = vec![0u8; 4096];
        let _ = stream.read(&mut buf); // request headers; content irrelevant
        let header = format!(
            "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
            body.len()
        );
        stream.write_all(header.as_bytes()).expect("write header");
        stream.write_all(&body).expect("write body");
    });
    (format!("http://127.0.0.1:{port}/asset"), handle)
}

#[test]
fn http_get_returns_served_bytes() {
    let (url, handle) = serve_once(b"hello-adapter".to_vec());
    let http = UreqHttpClient::new();
    let got = http.get(&url).expect("loopback GET");
    handle.join().expect("server thread");
    assert_eq!(got, b"hello-adapter");
}

#[test]
fn http_download_verifies_sha_and_writes_file() {
    let body = b"uv-binary-bytes".to_vec();
    let (url, handle) = serve_once(body.clone());
    let http = UreqHttpClient::new();
    let dir = tempfile::tempdir().expect("tempdir");
    let dest = dir.path().join("uv.bin");
    http.download(&url, &dest, &sha256_hex(&body))
        .expect("matching sha");
    handle.join().expect("server thread");
    assert_eq!(std::fs::read(&dest).expect("read back"), body);
}

#[test]
fn http_download_wrong_sha_fails_and_leaves_no_file() {
    let body = b"corrupt-me".to_vec();
    let (url, handle) = serve_once(body);
    let http = UreqHttpClient::new();
    let dir = tempfile::tempdir().expect("tempdir");
    let dest = dir.path().join("uv.bin");
    let err = http
        .download(&url, &dest, &"0".repeat(64))
        .expect_err("mismatch must fail typed");
    handle.join().expect("server thread");
    assert_eq!(err, WizardError::PayloadCorrupt);
    assert!(!dest.exists(), "never leave a corrupt file");
}

#[test]
fn http_bad_sha_format_fails_before_touching_disk() {
    let http = UreqHttpClient::new();
    let dir = tempfile::tempdir().expect("tempdir");
    let dest = dir.path().join("uv.bin");
    // Unreachable host on purpose: `PayloadCorrupt` (not `NetDownload`)
    // proves the hex is validated before any fetch.
    let err = http
        .download("http://127.0.0.1:9/unreachable", &dest, "not-hex")
        .expect_err("bad hex must fail typed");
    assert_eq!(err, WizardError::PayloadCorrupt);
    assert!(!dest.exists());
}

#[test]
fn http_refused_connection_is_net_error() {
    // Bind then drop: guaranteed closed port, no network involved.
    let port = TcpListener::bind("127.0.0.1:0")
        .expect("bind")
        .local_addr()
        .expect("addr")
        .port();
    let http = UreqHttpClient::new();
    let err = http
        .get(&format!("http://127.0.0.1:{port}/"))
        .expect_err("refused must fail typed");
    assert_eq!(err, WizardError::NetDownload);
}

/// L2-2: un servidor de loopback que vert >1 MiB pierde el cap del `get` —
/// error tipado `NetDownload`, abortando la lectura (nunca OOM: solo casos
/// reales arman el buffer).
#[test]
fn http_get_aborts_beyond_the_1mib_cap() {
    let listener = TcpListener::bind("127.0.0.1:0").expect("bind");
    let addr = listener.local_addr().expect("addr").to_string();
    thread::spawn(move || {
        let (mut stream, _) = listener.accept().expect("accept");
        let mut req = vec![0u8; 4096];
        let _ = stream.read(&mut req);
        // Sin Content-Length (HTTP/1.0): EOF manda; el server vete más Millas
        // del cap para forzar el abort, no para paginar al cliente.
        stream
            .write_all(b"HTTP/1.0 200 OK\r\nConnection: close\r\n\r\n")
            .expect("head");
        let chunk = [0u8; 4096];
        for _ in 0..1024 {
            // 4 MiB de zeros: 4x el cap, todo por loopback.
            if stream.write_all(&chunk).is_err() {
                break; // el cliente abortó al vencer el cap: es lo esperado
            }
        }
    });
    let http = UreqHttpClient::new();
    let err = http
        .get(&format!("http://{addr}/big"))
        .expect_err("un cuerpo >1 MiB debe perder el cap");
    assert_eq!(err, WizardError::NetDownload);
}

// --- `SysHostProbe` (real sysinfo; never crashes, AC-e) ---

#[test]
fn host_reports_sane_ram_and_disk() {
    let probe = SysHostProbe;
    let total = probe.ram_total_gb().expect("real machine has RAM");
    assert!(total > 0.0, "total RAM must be positive, got {total}");
    let avail = probe.ram_available_gb().expect("real machine has RAM");
    assert!((0.0..=total).contains(&avail), "0 <= avail <= total");
    let dir = tempfile::tempdir().expect("tempdir");
    let free = probe
        .disk_free_gb(dir.path())
        .expect("tempdir lives on a real disk");
    assert!(free > 0.0, "free disk must be positive, got {free}");
}

#[test]
fn host_disk_probe_of_missing_path_does_not_panic() {
    let probe = SysHostProbe;
    // Either `None` or a value — the contract is "never crash" (AC-e).
    let _ = probe.disk_free_gb(std::path::Path::new("/tepochcalli-no-such-dir-t5"));
}

#[test]
fn host_gpu_probe_never_panics() {
    let probe = SysHostProbe;
    // `Some` on GPU machines, `None` elsewhere — both are correct (AC-d).
    let _ = probe.gpu();
}

#[test]
fn host_tool_search_finds_present_and_misses_absent() {
    let dir = tempfile::tempdir().expect("tempdir");
    assert_eq!(
        find_tool_in("tepochcalli-no-such-tool-t5", &[dir.path().to_path_buf()]),
        None
    );
    let fake = dir.path().join("fake-smi-t5");
    std::fs::write(&fake, b"#!/bin/sh\necho gpu\n").expect("write fake tool");
    assert_eq!(
        find_tool_in("fake-smi-t5", &[dir.path().to_path_buf()]),
        Some(fake)
    );
    // PATH lookup wrapper honors real `PATH` (empty dir list ⇒ `None`).
    let empty: Vec<PathBuf> = Vec::new();
    assert_eq!(find_tool_in("sh", &empty), None);
}

/// L2-8: symlinks del payload (reales y colgantes) NUNCA cruzan el merge —
/// skipped tampoco nada escrito fuera del vault. symlink_metadata lee la
/// entrada sin seguir el enlace, así que el colgante no muere en el
/// branch file/copy por error.
#[cfg(unix)]
#[test]
fn merge_tree_skips_symlinks_real_and_dangling() {
    use std::os::unix::fs::symlink;
    use tepochcalli::adapters::LocalPayload;
    use tepochcalli::ports::PayloadSource;

    let src = tempfile::tempdir().expect("src tempdir");
    let dest = tempfile::tempdir().expect("dest tempdir");
    std::fs::write(src.path().join("note.md"), "# real file").expect("fixture file");
    // Real: apunta FUERA del vault.
    let outside = dest.path().join("outside-target.txt");
    std::fs::write(&outside, b"outside bytes").expect("outside fixture");
    symlink(&outside, src.path().join("real-link")).expect("real symlink");
    // Colgante: el destino no existe en ningún lado.
    symlink(
        src.path().join("does-not-exist.md"),
        src.path().join("dangling-link"),
    )
    .expect("dangling symlink");

    let report = LocalPayload::new(src.path())
        .materialize_report(dest.path())
        .expect("el merge no puede fallar por un symlink");

    let written_names: Vec<String> = report
        .written
        .iter()
        .map(|p| {
            p.file_name()
                .map(|n| n.to_string_lossy().into_owned())
                .unwrap_or_default()
        })
        .collect();
    let skipped_names: Vec<String> = report
        .skipped
        .iter()
        .map(|p| {
            p.file_name()
                .map(|n| n.to_string_lossy().into_owned())
                .unwrap_or_default()
        })
        .collect();
    assert!(
        !written_names.iter().any(|n| n.contains("link")),
        "ningún symlink cruza el merge, escritos: {written_names:?}"
    );
    assert!(written_names.iter().any(|n| n == "note.md"));
    assert!(
        skipped_names.iter().any(|n| n == "real-link")
            && skipped_names.iter().any(|n| n == "dangling-link"),
        "ambos enlaces quedan en skip, skipped: {skipped_names:?}"
    );
    // El outside-target sigue con sus bytes originales (nada lo tocó).
    assert_eq!(
        std::fs::read(&outside).expect("outside intact"),
        b"outside bytes"
    );
}

/// L3-6: plazo de subprocess con kill — un hijo colgado muere tipado
/// (`PhaseFailed`) dentro del plazo, y sus pipes se apagan con él.
#[test]
fn run_with_timeout_kills_a_hanging_child_in_deadline() {
    let runner = StdCommandRunner;
    let dir = tempfile::tempdir().expect("tempdir");
    let started = std::time::Instant::now();
    let err = runner
        .run_with_timeout(
            "sh",
            &["-c", "sleep 30"],
            dir.path(),
            &[],
            std::time::Duration::from_millis(500),
        )
        .expect_err("un hijo colgado debe perder el plazo");
    assert_eq!(err, WizardError::PhaseFailed);
    assert!(
        started.elapsed() < std::time::Duration::from_secs(10),
        "kill dentro de plazo (pasados {:?})",
        started.elapsed()
    );
}

/// L3-6: la vía feliz conserva el output — el plazo no roba lo capturado.
#[test]
fn run_with_timeout_returns_output_of_prompt_children() {
    let runner = StdCommandRunner;
    let dir = tempfile::tempdir().expect("tempdir");
    let out = runner
        .run_with_timeout(
            "sh",
            &["-c", "echo hola-plazo"],
            dir.path(),
            &[],
            std::time::Duration::from_secs(10),
        )
        .expect("hijo ágil dentro del plazo");
    assert_eq!(out.status, 0);
    assert_eq!(out.stdout, "hola-plazo\n");
}

/// Restaura al soltar las variables que el test mutó en el proceso padre
/// (`set_var` es global a los tests del binario, así que no puede quedar pegado).
struct EnvRestore {
    previous: Vec<(&'static str, Option<std::ffi::OsString>)>,
}

impl EnvRestore {
    fn set(vars: &[(&'static str, &str)]) -> Self {
        let previous = vars
            .iter()
            .map(|(key, _)| (*key, std::env::var_os(key)))
            .collect();
        for (key, value) in vars {
            std::env::set_var(key, value);
        }
        Self { previous }
    }
}

impl Drop for EnvRestore {
    fn drop(&mut self) {
        for (key, previous) in self.previous.drain(..) {
            match previous {
                Some(value) => std::env::set_var(key, value),
                None => std::env::remove_var(key),
            }
        }
    }
}

/// L3-7 (4b-B): el env del hijo es allowlist — un PYTHONPATH hostil y un
/// HF_TOKEN fantasma del padre no viajan al hijo; lo benigno sí (PATH).
#[test]
fn child_env_is_allowlisted_hostile_vars_do_not_travel() {
    // Rellenado brutal de env hostil del proceso test (no hay fixtures —
    // set_var muta literalmente el padre; el hijo no puede heredarlo).
    let _env = EnvRestore::set(&[
        ("PYTHONPATH", "/tmp/tepochcalli-injection-4bb"),
        ("HF_TOKEN", "not-a-real-token-4bb"),
    ]);
    let runner = StdCommandRunner;
    let dir = tempfile::tempdir().expect("tempdir");
    let out = runner
        .run(
            "sh",
            &[
                "-c",
                "python3 -c 'import os, sys; \
                 print(int(\"PYTHONPATH\" in os.environ), int(\"HF_TOKEN\" in os.environ))'",
            ],
            dir.path(),
            &[],
        )
        .expect("sh/python run");
    assert_eq!(out.status, 0, "stderr: {}", out.stderr);
    assert_eq!(
        out.stdout.trim(),
        "0 0",
        "ni PYTHONPATH ni HF_TOKEN pueden heredar"
    );
}

/// L3-7: los pares explícitos del caller viven en el hijo (el allowlist no
/// se los come).
#[test]
fn child_env_keeps_explicit_pairs_beyond_the_allowlist() {
    let runner = StdCommandRunner;
    let dir = tempfile::tempdir().expect("tempdir");
    let out = runner
        .run(
            "sh",
            &["-c", "echo $TEPOCHCALLI_ROOT"],
            dir.path(),
            &[("TEPOCHCALLI_ROOT", ".")],
        )
        .expect("sh run");
    assert_eq!(out.stdout.trim(), ".");
    // Y PATH sigue: el toolchain necesita lookup de binarios.
    let out = runner
        .run(
            "sh",
            &["-c", "sh -c 'command -v ls >/dev/null'"],
            dir.path(),
            &[],
        )
        .expect("sh run");
    assert_eq!(out.status, 0, "PATH debe seguir heredado: {}", out.stderr);
}

/// L5-1 bench pin: el fail-path de F1 evaluado sobre el snapshot memoizado
/// es rápido — sin `System::new_all()` por fila, el gate completo corre en
/// < 400 ms. El presupuesto depende del host (fuseblk/NTFS-3G penaliza el
/// I/O): lo pineado es que no se re-proba, no la latencia exacta.
#[test]
fn real_f1_gate_is_fast_over_the_cached_snapshot() {
    use std::time::{Duration, Instant};

    let probe = SysHostProbe;
    // Warm-up: un snapshot servido (la corrida real lo hace en F1... y solo
    // una vez; aquí pinamos que repetir el gate NO paga de nuevo).
    let _ = probe.snapshot();
    let dir = tempfile::tempdir().expect("tempdir");
    let started = Instant::now();
    let _ = tepochcalli::application::check_prereqs_on(
        &probe,
        std::env::consts::OS,
        dir.path(),
        &tepochcalli::adapters::path_dirs(),
    );
    let elapsed = started.elapsed();
    assert!(
        elapsed < Duration::from_millis(400),
        "F1 sobre el snapshot cacheado debe correr < 400 ms (host-dependent: fuseblk/NTFS-3G), tomó {elapsed:?}"
    );
}

#[test]
fn host_tool_search_accepts_the_windows_exe_twin() {
    let dir = tempfile::tempdir().expect("tempdir");
    let exe = dir.path().join("notepad-plus-tool-t6.exe");
    std::fs::write(&exe, b"MZ").expect("write fake exe");
    assert_eq!(
        find_tool_in("notepad-plus-tool-t6", &[dir.path().to_path_buf()]),
        Some(exe.clone()),
        "busca name.exe cuando el bare no existe"
    );
    // existing_bare wins; existing_exe.gone: solo .exe cuenta, no .bare.
    assert_eq!(
        find_tool_in("notepad-plus-tool-t6.exe", &[dir.path().to_path_buf()]),
        Some(exe),
        "el id con sufijo también se encuentra"
    );
}
