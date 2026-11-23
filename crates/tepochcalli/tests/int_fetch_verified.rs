//! Downloader spike tests: SHA-256 verified fetch, no remote scripts.
//! All traffic goes to a localhost TcpListener — no external network.

#[allow(dead_code)]
mod common;

use std::io::{Read, Write};
use std::net::TcpListener;
use std::thread;

use common::helpers::sha256_hex;
use tepochcalli::adapters::fetch::{fetch_verified, make_executable, run_version, FetchError};

/// Minimal HTTP server: serves `routes` once each, then exits.
/// Each route is (path, status_line, body). Unknown path -> 404.
fn serve(routes: Vec<(String, String, Vec<u8>)>) -> String {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let addr = listener.local_addr().unwrap().to_string();
    thread::spawn(move || {
        for (path, status, body) in routes {
            let (mut stream, _) = listener.accept().unwrap();
            let mut req = vec![0u8; 4096];
            let n = stream.read(&mut req).unwrap();
            let head = String::from_utf8_lossy(&req[..n]);
            let is_redirect_target = head.lines().next().is_some_and(|l| l.contains(&path));
            if !is_redirect_target {
                let resp =
                    "HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n";
                stream.write_all(resp.as_bytes()).unwrap();
                continue;
            }
            let resp = format!(
                "{status}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                body.len()
            );
            stream.write_all(resp.as_bytes()).unwrap();
            stream.write_all(&body).unwrap();
        }
    });
    format!("http://{addr}")
}

#[test]
fn fetch_verified_writes_file_when_hash_matches() {
    let payload = b"fake uv binary bytes";
    let url = serve(vec![(
        "/uv.tar.gz".to_string(),
        "HTTP/1.1 200 OK".to_string(),
        payload.to_vec(),
    )]);
    let dir = tempfile::tempdir().unwrap();
    let dest = dir.path().join("uv.tar.gz");
    fetch_verified(&format!("{url}/uv.tar.gz"), &dest, &sha256_hex(payload)).unwrap();
    assert_eq!(std::fs::read(&dest).unwrap(), payload);
}

#[test]
fn fetch_verified_rejects_mismatch_and_leaves_no_file() {
    let payload = b"fake uv binary bytes";
    let url = serve(vec![(
        "/uv.tar.gz".to_string(),
        "HTTP/1.1 200 OK".to_string(),
        payload.to_vec(),
    )]);
    let dir = tempfile::tempdir().unwrap();
    let dest = dir.path().join("uv.tar.gz");
    let err = fetch_verified(
        &format!("{url}/uv.tar.gz"),
        &dest,
        &"00".repeat(32), // wrong hash, valid hex shape
    )
    .unwrap_err();
    assert!(
        matches!(err, FetchError::ChecksumMismatch { .. }),
        "{err:?}"
    );
    assert!(!dest.exists(), "corrupt download must not remain on disk");
}

#[test]
fn fetch_verified_follows_bounded_redirect() {
    let payload = b"redirected bytes";
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let addr = listener.local_addr().unwrap().to_string();
    let redirect = format!("http://{addr}/real");
    thread::spawn(move || {
        // First request -> 302 to /real; second request -> 200 body.
        let (mut s1, _) = listener.accept().unwrap();
        let mut req = vec![0u8; 4096];
        let _ = s1.read(&mut req);
        let resp = format!(
            "HTTP/1.1 302 Found\r\nLocation: {redirect}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
        );
        s1.write_all(resp.as_bytes()).unwrap();
        let (mut s2, _) = listener.accept().unwrap();
        let _ = s2.read(&mut req);
        let resp = format!(
            "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
            payload.len()
        );
        s2.write_all(resp.as_bytes()).unwrap();
        s2.write_all(payload).unwrap();
    });
    let dir = tempfile::tempdir().unwrap();
    let dest = dir.path().join("uv.tar.gz");
    fetch_verified(&format!("http://{addr}/old"), &dest, &sha256_hex(payload)).unwrap();
    assert_eq!(std::fs::read(&dest).unwrap(), payload);
}

#[test]
#[cfg(unix)]
fn make_executable_then_version_runs() {
    use std::os::unix::fs::PermissionsExt as _;
    let dir = tempfile::tempdir().unwrap();
    let fake = dir.path().join("uv");
    std::fs::write(&fake, "#!/bin/sh\necho 'uv 0.9.0'\n").unwrap();
    make_executable(&fake).unwrap();
    let mode = std::fs::metadata(&fake).unwrap().permissions().mode();
    assert!(mode & 0o111 != 0, "executable bit must be set");
    let out = run_version(&fake).unwrap();
    assert!(out.contains("uv 0.9.0"), "unexpected output: {out}");
}

/// L2-2: un servidor de loopback que vierte un stream >2 GiB vence el cap
/// del transfer (nunca OOM: la lectura aborta por chunks al vencer el cap) —
/// `PayloadCorrupt` vía `TooLarge` (asset hostil, no transporte).
#[test]
fn fetch_verified_aborts_beyond_the_2gib_cap() {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let addr = listener.local_addr().unwrap().to_string();
    thread::spawn(move || {
        let (mut stream, _) = listener.accept().unwrap();
        let mut req = vec![0u8; 4096];
        let _ = stream.read(&mut req);
        stream
            .write_all(b"HTTP/1.0 200 OK\r\nConnection: close\r\n\r\n")
            .unwrap();
        let chunk = vec![0u8; 1 << 20]; // 1 MiB por write; 2 GiB + margen
        for _ in 0..2200 {
            if stream.write_all(&chunk).is_err() {
                break; // cliente abortó al vencer el cap: esperado
            }
        }
    });
    let dir = tempfile::tempdir().unwrap();
    let dest = dir.path().join("uv.tar.gz");
    let err = fetch_verified(&format!("http://{addr}/big"), &dest, &"0".repeat(64)).unwrap_err();
    assert!(matches!(err, FetchError::TooLarge { .. }), "{err:?}");
    assert!(!dest.exists(), "nada llega a disco tras el abort");
}
