//! First automated check for the hand-written installers (T19).
//!
//! `installers/install.sh` and `installers/install.ps1` were the least verified
//! code in the crate: nothing in `tests/`, the Justfile or CI touched them.
//! These tests drive the real `install.sh` against a loopback HTTP mirror via
//! the `TEPOCHCALLI_RELEASE_BASE_URL` seam, and pin the PowerShell script
//! statically (it cannot execute on Linux).
//!
//! What the shell script actually does: download `<base>/tepochcalli-<target>.tar.gz`
//! and its `.sha256`, compare the digest, extract and `exec` the binary from a
//! temp dir. It installs nothing into `$HOME/.local/bin` — so "installs" below
//! means "the verified binary is the one that runs".
//!
//! No test touches the real network; no dependency beyond the crate's existing
//! `sha2` / `tar` / `flate2` / `tempfile`.

#[allow(dead_code)]
mod common;

use std::io::{Read, Write};
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Command, Output, Stdio};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

use common::helpers::sha256_hex;

fn installer(name: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("installers")
        .join(name)
}

fn tool_available(tool: &str) -> bool {
    Command::new("sh")
        .arg("-c")
        .arg(format!("command -v {tool}"))
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .is_ok_and(|status| status.success())
}

/// Honest skip: say why and return, never assert-true silently.
fn require_host_tools(tools: &[&str]) -> bool {
    for tool in tools {
        if !tool_available(tool) {
            eprintln!("skip: host lacks `{tool}`, which install.sh needs");
            return false;
        }
    }
    true
}

/// Serves up to `requests` connections, then stops. The handler maps a request
/// path to `(status line, body)`. Gives up after a deadline so a script that
/// never calls us cannot hang the suite.
fn serve<F>(requests: usize, handler: F) -> (String, JoinHandle<()>)
where
    F: Fn(&str) -> (String, Vec<u8>) + Send + 'static,
{
    let listener = TcpListener::bind("127.0.0.1:0").expect("bind loopback");
    let base = format!("http://{}", listener.local_addr().expect("local addr"));
    let handle = std::thread::spawn(move || {
        listener.set_nonblocking(true).expect("nonblocking");
        let deadline = Instant::now() + Duration::from_secs(30);
        for _ in 0..requests {
            let mut stream = loop {
                match listener.accept() {
                    Ok((stream, _)) => break stream,
                    Err(err) if err.kind() == std::io::ErrorKind::WouldBlock => {
                        if Instant::now() > deadline {
                            eprintln!("fake release: no more clients, serving {requests} max");
                            return;
                        }
                        std::thread::sleep(Duration::from_millis(5));
                    }
                    Err(err) => panic!("accept failed: {err}"),
                }
            };
            stream.set_nonblocking(false).expect("blocking stream");
            let mut buf = vec![0u8; 8192];
            let n = stream.read(&mut buf).expect("read request");
            let head = String::from_utf8_lossy(&buf[..n]).to_string();
            let path = head
                .lines()
                .next()
                .and_then(|line| line.split_whitespace().nth(1))
                .unwrap_or("/")
                .to_string();
            let (status, body) = handler(&path);
            let response = format!(
                "{status}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                body.len()
            );
            stream.write_all(response.as_bytes()).expect("write head");
            stream.write_all(&body).expect("write body");
        }
    });
    (base, handle)
}

/// A release tarball whose single member is an executable fixture that records
/// "I ran" plus its argv, so the test can prove what the script executed.
fn tar_gz_fixture(binary: &str, argv_out: &Path) -> Vec<u8> {
    let script = format!(
        "#!/bin/sh\necho \"ran\" > '{}'\nprintf 'argv:%s\\n' \"$*\" >> '{}'\n",
        argv_out.display(),
        argv_out.display()
    );
    let mut tar_buf = Vec::new();
    {
        let mut builder = tar::Builder::new(&mut tar_buf);
        let mut header = tar::Header::new_gnu();
        header.set_size(script.len() as u64);
        header.set_mode(0o755);
        header.set_cksum();
        builder
            .append_data(&mut header, binary, script.as_bytes())
            .expect("tar fixture");
        builder.into_inner().expect("finish tar");
    }
    let mut encoder = flate2::write::GzEncoder::new(Vec::new(), flate2::Compression::default());
    encoder.write_all(&tar_buf).expect("gzip fixture");
    encoder.finish().expect("finish gzip")
}

/// `install.sh` with every override a test may need, isolated from the host.
fn command(base_url: &str, home: &Path) -> Command {
    let mut cmd = Command::new("sh");
    cmd.arg(installer("install.sh"))
        // The seam under test: without it the script can only reach GitHub.
        .env("TEPOCHCALLI_RELEASE_BASE_URL", base_url)
        .env("HOME", home)
        .env("XDG_BIN_HOME", home.join("bin"));
    // Loopback must not be routed through a proxy.
    for var in [
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
    ] {
        cmd.env_remove(var);
    }
    cmd.env("no_proxy", "127.0.0.1,localhost");
    cmd
}

fn run(mut cmd: Command) -> Output {
    cmd.output().expect("run install.sh")
}

fn stderr_of(output: &Output) -> String {
    String::from_utf8_lossy(&output.stderr).to_string()
}

#[test]
fn shell_installer_rejects_checksum_mismatch() {
    // RED-first: before the base-URL seam this script could only talk to GitHub.
    if !require_host_tools(&["sh", "curl", "tar", "awk"]) {
        return;
    }
    let home = tempfile::tempdir().expect("tempdir");
    let argv_out = home.path().join("exec-marker.txt");
    let tarball = tar_gz_fixture("tepochcalli", &argv_out);
    let wrong_digest = "0".repeat(64);

    let (base, server) = serve(2, move |path| {
        if path.ends_with(".sha256") {
            (
                "HTTP/1.1 200 OK".to_string(),
                format!("{wrong_digest}  tepochcalli-x86_64-unknown-linux-gnu.tar.gz\n")
                    .into_bytes(),
            )
        } else {
            ("HTTP/1.1 200 OK".to_string(), tarball.clone())
        }
    });

    let output = run(command(&base, home.path()));
    server.join().expect("server thread");

    let stderr = stderr_of(&output);
    assert!(
        !output.status.success(),
        "a mismatched digest must fail, stderr was: {stderr}"
    );
    assert!(
        stderr.contains("CHECKSUM MISMATCH"),
        "error must name the checksum verification, got: {stderr}"
    );
    assert!(
        !argv_out.exists(),
        "the unverified binary must never execute"
    );
    assert!(
        !home.path().join("bin").join("tepochcalli").exists(),
        "nothing may be installed from an unverified archive"
    );
}

#[test]
fn shell_installer_installs_verified_binary() {
    // "Installs" = the verified binary is the one that runs (the script execs
    // from its temp dir instead of copying into XDG_BIN_HOME).
    if !require_host_tools(&["sh", "curl", "tar", "awk"]) {
        return;
    }
    let home = tempfile::tempdir().expect("tempdir");
    let argv_out = home.path().join("exec-marker.txt");
    let tarball = tar_gz_fixture("tepochcalli", &argv_out);
    let digest = sha256_hex(&tarball);

    let (base, server) = serve(2, move |path| {
        if path.ends_with(".sha256") {
            (
                "HTTP/1.1 200 OK".to_string(),
                format!("{digest}  tepochcalli-x86_64-unknown-linux-gnu.tar.gz\n").into_bytes(),
            )
        } else {
            ("HTTP/1.1 200 OK".to_string(), tarball.clone())
        }
    });

    // A pinned tag exercises the `shift` before the binary's own arguments.
    let mut cmd = command(&base, home.path());
    cmd.arg("tepochcalli-v0.3.0").arg("--version");
    let output = run(cmd);
    server.join().expect("server thread");

    let stderr = stderr_of(&output);
    assert!(
        output.status.success(),
        "verified install must succeed, stderr was: {stderr}"
    );
    let recorded = std::fs::read_to_string(&argv_out)
        .unwrap_or_else(|err| panic!("verified binary never ran ({err}); stderr: {stderr}"));
    assert!(
        recorded.contains("argv:--version"),
        "arguments must reach the binary, got: {recorded:?}"
    );
}

#[test]
fn shell_installer_fails_clean_on_missing_checksum() {
    // 404 on the sidecar: refuse to extract, never exec.
    if !require_host_tools(&["sh", "curl", "tar", "awk"]) {
        return;
    }
    let home = tempfile::tempdir().expect("tempdir");
    let argv_out = home.path().join("exec-marker.txt");
    let tarball = tar_gz_fixture("tepochcalli", &argv_out);

    let (base, server) = serve(2, move |path| {
        if path.ends_with(".sha256") {
            ("HTTP/1.1 404 Not Found".to_string(), Vec::new())
        } else {
            ("HTTP/1.1 200 OK".to_string(), tarball.clone())
        }
    });

    let output = run(command(&base, home.path()));
    server.join().expect("server thread");

    let stderr = stderr_of(&output);
    assert!(
        !output.status.success(),
        "a missing sidecar must fail, stderr was: {stderr}"
    );
    assert!(
        !stderr.trim().is_empty(),
        "failure must be reported, not silent"
    );
    assert!(
        !argv_out.exists(),
        "without a checksum the binary must never execute"
    );
}

#[test]
fn shell_installer_rejects_unknown_arch() {
    // Shadow `uname` so the real host arch cannot make this pass by accident.
    if !require_host_tools(&["sh", "curl", "tar", "awk"]) {
        return;
    }
    let home = tempfile::tempdir().expect("tempdir");
    let fake_bin = home.path().join("fake-bin");
    std::fs::create_dir_all(&fake_bin).expect("fake bin dir");
    let uname = fake_bin.join("uname");
    std::fs::write(
        &uname,
        "#!/bin/sh\ncase \"$1\" in\n  -s) echo Linux ;;\n  -m) echo sparc64 ;;\n  *) echo unknown ;;\nesac\n",
    )
    .expect("write fake uname");
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt as _;
        std::fs::set_permissions(&uname, std::fs::Permissions::from_mode(0o755)).expect("chmod");
    }

    let argv_out = home.path().join("exec-marker.txt");
    // Dead port: an unsupported platform must be rejected before any request.
    let mut cmd = command("http://127.0.0.1:9", home.path());
    cmd.env(
        "PATH",
        format!(
            "{}:{}",
            fake_bin.display(),
            std::env::var("PATH").unwrap_or_default()
        ),
    );
    let output = run(cmd);

    let stderr = stderr_of(&output);
    assert_eq!(
        output.status.code(),
        Some(1),
        "unknown arch exits 1, stderr was: {stderr}"
    );
    assert!(
        stderr.contains("unsupported platform"),
        "error must name the platform, got: {stderr}"
    );
    assert!(!argv_out.exists(), "nothing may execute on an unknown arch");
}

#[test]
fn powershell_installer_verifies_checksum_before_exec() {
    // STATIC PIN, not an execution test: install.ps1 cannot run on Linux, so
    // this only proves the guard is still present and still precedes the exec.
    let script = std::fs::read_to_string(installer("install.ps1")).expect("read install.ps1");

    assert!(
        script.contains("Get-FileHash") && script.contains("Algorithm SHA256"),
        "install.ps1 must compute a SHA-256 of the download"
    );
    let mismatch = script
        .find("if ($Expected.ToLower() -ne $Actual)")
        .expect("install.ps1 must compare the expected digest against the actual one");
    let refuse = script[mismatch..]
        .find("exit 1")
        .expect("a mismatch must exit non-zero");
    let exec = script
        .find("& (Join-Path $Work \"$App.exe\")")
        .expect("install.ps1 must run the extracted binary");
    assert!(
        mismatch + refuse < exec,
        "the checksum gate must run before the binary is executed"
    );
    assert!(
        script.contains("$env:TEPOCHCALLI_RELEASE_BASE_URL"),
        "install.ps1 keeps the base-URL seam its shell twin has"
    );
}
