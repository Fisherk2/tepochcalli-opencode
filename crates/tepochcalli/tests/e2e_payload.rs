//! GAP 8: the default payload path (no `--payload*` flag at all) end-to-end.
//!
//! The binary must ask the release base for ITS OWN version's asset (never
//! `latest`), verify the `.sha256` sidecar, merge the tree and move on past F3.
//! Loopback only: `TEPOCHCALLI_RELEASE_BASE_URL` — the same seam
//! `installers/install.sh` documents for mirrors — points at a local server,
//! so nothing here touches the real network or a real release.

#[allow(dead_code)]
mod common;

use std::io::{BufRead, BufReader, Write};
use std::net::TcpListener;
use std::process::Command;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;
use std::time::Duration;

use common::helpers::sha256_hex;
use tepochcalli::adapters::payload::{
    payload_asset_name, payload_asset_url_from, payload_checksum_name, payload_release_tag,
    release_base_url_from,
};

const VERSION: &str = env!("CARGO_PKG_VERSION");

fn tar_gz(files: &[(&str, &[u8])]) -> Vec<u8> {
    let mut tar_buf = Vec::new();
    {
        let mut builder = tar::Builder::new(&mut tar_buf);
        for (name, body) in files {
            let mut header = tar::Header::new_gnu();
            header.set_size(body.len() as u64);
            header.set_mode(0o644);
            header.set_cksum();
            builder
                .append_data(&mut header, name, *body)
                .expect("tar fixture");
        }
        builder.into_inner().expect("finish tar");
    }
    let mut encoder = flate2::write::GzEncoder::new(Vec::new(), flate2::Compression::default());
    encoder.write_all(&tar_buf).expect("gzip fixture");
    encoder.finish().expect("finish gzip")
}

fn tool_available(tool: &str) -> bool {
    Command::new(tool)
        .arg("--version")
        .output()
        .is_ok_and(|out| out.status.success())
}

/// Loopback HTTP server for fixed routes, recording every requested path.
/// It serves one connection at a time (the installer fetches sequentially) and
/// stops when dropped.
struct Loopback {
    base: String,
    requests: Arc<Mutex<Vec<String>>>,
    stop: Arc<AtomicBool>,
    handle: Option<JoinHandle<()>>,
}

impl Loopback {
    fn serve(routes: Vec<(String, Vec<u8>)>) -> Self {
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind loopback");
        let port = listener.local_addr().expect("local addr").port();
        listener.set_nonblocking(true).expect("nonblocking");
        let requests = Arc::new(Mutex::new(Vec::new()));
        let stop = Arc::new(AtomicBool::new(false));
        let (seen, halted) = (Arc::clone(&requests), Arc::clone(&stop));
        let handle = std::thread::spawn(move || {
            while !halted.load(Ordering::Relaxed) {
                match listener.accept() {
                    Ok((stream, _)) => handle_request(stream, &routes, &seen),
                    Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                        std::thread::sleep(Duration::from_millis(2));
                    }
                    Err(_) => break,
                }
            }
        });
        Self {
            base: format!("http://127.0.0.1:{port}/releases/download"),
            requests,
            stop,
            handle: Some(handle),
        }
    }

    fn requested_paths(&self) -> Vec<String> {
        self.requests.lock().expect("request log").clone()
    }
}

impl Drop for Loopback {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Relaxed);
        if let Some(handle) = self.handle.take() {
            let _ = handle.join();
        }
    }
}

fn handle_request(
    mut stream: std::net::TcpStream,
    routes: &[(String, Vec<u8>)],
    seen: &Mutex<Vec<String>>,
) {
    let mut reader = BufReader::new(&stream);
    let mut request_line = String::new();
    if reader.read_line(&mut request_line).is_err() {
        return;
    }
    loop {
        let mut header = String::new();
        match reader.read_line(&mut header) {
            Ok(0) => break,
            Ok(_) if header.trim().is_empty() => break,
            Ok(_) => {}
            Err(_) => break,
        }
    }
    let path = request_line
        .split_whitespace()
        .nth(1)
        .unwrap_or("")
        .to_string();
    seen.lock().expect("record").push(path.clone());
    let body = routes
        .iter()
        .find(|(route, _)| *route == path)
        .map(|(_, body)| body.as_slice());
    let (status, payload) = match body {
        Some(body) => ("200 OK", body),
        None => ("404 Not Found", &[][..]),
    };
    let _ = write!(
        stream,
        "HTTP/1.1 {status}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
        payload.len()
    );
    let _ = stream.write_all(payload);
    let _ = stream.flush();
}

#[test]
fn default_install_fetches_own_version_payload_from_loopback() {
    if !tool_available("sh") || !tool_available("curl") {
        // The install phases shell out (uv/venv) on the real path; on an image
        // without the POSIX toolchain this e2e cannot mean anything.
        println!("skip: sh and/or curl unavailable (POSIX toolchain the install phases need)");
        return;
    }
    // L3-3 artifact-first: el opencode.json del peso trae ya la entrada
    // gestionada — es el artefacto F8 que el probe exige para saltar la
    // fase (el marker sol no vale ya). Con eso el re-run no se superpone:
    // F3 copia el fichero byte-idéntico y F8 lo ve como artefacto hecho.
    let payload_files: [(&str, &[u8]); 2] = [
        ("AGENTS.md", b"# vault agent rules\n"),
        (
            "opencode.json",
            b"{\"mcp\": {\"servers\": {\"tepochcalli-rag\": {}}}}\n",
        ),
    ];
    let asset = tar_gz(&payload_files);
    let hex = sha256_hex(&asset);
    let tag = payload_release_tag(VERSION);
    let asset_path = format!("/releases/download/{tag}/{}", payload_asset_name(VERSION));
    let sidecar_path = format!(
        "/releases/download/{tag}/{}",
        payload_checksum_name(VERSION)
    );
    let sidecar = format!("{hex}  {}\n", payload_asset_name(VERSION));
    let server = Loopback::serve(vec![
        (sidecar_path.clone(), sidecar.into_bytes()),
        (asset_path.clone(), asset),
    ]);

    let dir = tempfile::tempdir().expect("tempdir");
    let vault = dir.path().join("vault");
    // F4/F5/F8 need the real network and a venv; pre-marking them done keeps
    // this run hermetic. F3 stays unmarked: it is the phase under test.
    // L3-3 artifact-first: el marker ya no salta una fase sin artefacto, así
    // que el fixture los sirve (uv fake — F4 se saltea sin ejecutarlo — y
    // interpreter fake del venv para el probe de F5).
    std::fs::create_dir_all(vault.join(".tepochcalli")).expect("state dir");
    std::fs::write(
        vault.join(".tepochcalli").join(".install-state"),
        "F1\nF2\nF4\nF5\nF8\n",
    )
    .expect("state marker");
    std::fs::create_dir_all(vault.join(".tepochcalli").join("bin")).expect("uv bin dir");
    std::fs::write(
        vault.join(".tepochcalli").join("bin").join("uv"),
        b"fake-uv",
    )
    .expect("uv artifact");
    std::fs::create_dir_all(vault.join(".tepochcalli").join("venv").join("bin"))
        .expect("venv bin dir");
    std::fs::write(
        vault
            .join(".tepochcalli")
            .join("venv")
            .join("bin")
            .join("python"),
        b"#!/bin/sh\nexit 0\n",
    )
    .expect("venv python artifact");
    let out = Command::new(env!("CARGO_BIN_EXE_tepochcalli"))
        .args([
            "install",
            "--non-interactive",
            "--skip-model",
            "--resume",
            "--vault",
        ])
        .arg(vault.to_str().expect("utf8 tmp"))
        .env("TEPOCHCALLI_RELEASE_BASE_URL", &server.base)
        .output()
        .expect("spawn install");
    let requests = server.requested_paths();
    let stderr = String::from_utf8_lossy(&out.stderr).into_owned();

    // One-version rule: both the sidecar and the asset came from this
    // binary's own tag — never `latest`.
    for path in [&sidecar_path, &asset_path] {
        assert!(
            requests.contains(path),
            "requested {requests:?}, missing {path}"
        );
        assert!(
            path.contains(VERSION),
            "must pin the binary version: {path}"
        );
        assert!(!path.contains("latest"), "no floating `latest`: {path}");
    }
    for path in &requests {
        assert!(!path.contains("latest"), "no floating `latest`: {path}");
    }
    // The default path completed (F3 + F6 degraded, later phases skipped),
    // so the install never stalled inside F3.
    assert_eq!(out.status.code(), Some(0), "stderr:\n{stderr}");
    // F3 merged the payload tree into the vault.
    for (name, body) in payload_files {
        assert_eq!(
            std::fs::read_to_string(vault.join(name)).expect("merged file"),
            String::from_utf8_lossy(body),
            "{name} must come from the fetched payload"
        );
    }
    assert!(
        stderr.contains("payload: release asset"),
        "the install must report the release asset it used, got:\n{stderr}"
    );
    assert!(
        stderr.contains(&format!("one-version {VERSION}")),
        "the install must name its own version, got:\n{stderr}"
    );
}

#[test]
fn release_base_url_defaults_to_https_and_plain_http_is_override_only() {
    // Decision, matching `installers/install.sh` (which documents
    // TEPOCHCALLI_RELEASE_BASE_URL as a mirror/loopback seam and drops the
    // https pin for a non-https base): plain http is NEVER the release base —
    // the default is https and never `latest` — but the explicit override may
    // be plain http, because 127.0.0.1 cannot present a TLS certificate and
    // the trust gate is the SHA-256 sidecar, not the transport.
    let default = release_base_url_from(None);
    assert!(
        default.starts_with("https://"),
        "the release base must be https: {default}"
    );
    assert!(
        !default.contains("latest"),
        "no floating `latest`: {default}"
    );
    let asset = payload_asset_url_from(&default, VERSION);
    assert!(asset.starts_with(&format!("{default}/")), "planned {asset}");
    assert!(
        asset.contains(VERSION) && !asset.contains("latest"),
        "planned {asset}"
    );
    // Empty counts as unset, exactly like the script's `[ -n "$BASE_URL" ]`.
    assert_eq!(release_base_url_from(Some("  ")), default);
    // The override is honoured verbatim (trailing slash trimmed), plain http
    // included — that is the loopback-mirror seam, and the only way to get it.
    let mirror = release_base_url_from(Some("http://127.0.0.1:1234/releases/download/"));
    assert_eq!(mirror, "http://127.0.0.1:1234/releases/download");
    assert!(payload_asset_url_from(&mirror, VERSION)
        .starts_with(&format!("{mirror}/{}/", payload_release_tag(VERSION))));
}
