//! Port contract tests (T4): every port exercised through its fake.
//!
//! One test per port minimum; each test pins the exact signature from the
//! task so T5 adapters must conform to it.

mod common;

use std::collections::HashMap;

use common::{FakeHost, FakeHttp, FakeProc, FakeUiScript, ScriptedUi};
use sha2::{Digest, Sha256};
use tepochcalli::ports::{CommandRunner, GpuInfo, HostProbe, HttpClient, PayloadSource, Ui};
use tepochcalli::WizardError;

fn sha256_hex(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

#[test]
fn proc_returns_scripted_output() {
    let proc = FakeProc::scripted([Ok(tepochcalli::ports::CommandOutput {
        status: 0,
        stdout: "uv 0.9.8".to_string(),
        stderr: String::new(),
    })]);
    let out = proc
        .run("uv", &["--version"], std::path::Path::new("/tmp"), &[])
        .expect("scripted ok");
    assert_eq!(out.status, 0);
    assert_eq!(out.stdout, "uv 0.9.8");
}

#[test]
fn proc_replays_scripted_failure() {
    let proc = FakeProc::scripted([Err(WizardError::NetDownload)]);
    let err = proc
        .run("uv", &["--version"], std::path::Path::new("/tmp"), &[])
        .expect_err("scripted failure must surface");
    assert_eq!(err, WizardError::NetDownload);
}

#[test]
fn http_serves_bytes_and_verifies_sha() {
    let body = b"payload-bytes";
    let mut files = HashMap::new();
    files.insert("https://example.com/a".to_string(), body.to_vec());
    let http = FakeHttp::new(files);

    let got = http.get("https://example.com/a").expect("known url");
    assert_eq!(got, body);

    let dir = tempfile::tempdir().expect("tempdir");
    let dest = dir.path().join("a.bin");
    http.download("https://example.com/a", &dest, &sha256_hex(body))
        .expect("matching sha");
    assert_eq!(std::fs::read(&dest).expect("read back"), body);

    let bad = http.download("https://example.com/a", &dest, &"0".repeat(64));
    assert_eq!(bad, Err(WizardError::PayloadCorrupt));
}

#[test]
fn http_unknown_url_is_net_error() {
    let http = FakeHttp::new(HashMap::new());
    assert_eq!(
        http.get("https://example.com/nope"),
        Err(WizardError::NetDownload)
    );
}

#[test]
fn host_reports_fixture_values() {
    let host = FakeHost::new(
        Some(16.0),
        Some(12.0),
        Some(50.0),
        Some(GpuInfo {
            name: "nvidia".to_string(),
        }),
    );
    assert_eq!(host.ram_total_gb(), Some(16.0));
    assert_eq!(host.ram_available_gb(), Some(12.0));
    assert_eq!(host.disk_free_gb(std::path::Path::new("/tmp")), Some(50.0));
    assert_eq!(host.gpu().map(|g| g.name), Some("nvidia".to_string()));
}

#[test]
fn host_probe_failure_is_none_not_crash() {
    // D8.2 fallback: a failed probe yields None, never an error.
    let host = FakeHost::new(None, None, None, None);
    assert_eq!(host.ram_total_gb(), None);
    assert_eq!(host.ram_available_gb(), None);
    assert_eq!(host.disk_free_gb(std::path::Path::new("/tmp")), None);
    assert!(host.gpu().is_none());
}

#[test]
fn payload_materializes_fixture_files() {
    let src = tempfile::tempdir().expect("src tempdir");
    std::fs::write(src.path().join("a.md"), "# hi").expect("fixture write");
    let fake = common::FakePayload::new(src.path());
    let dest = tempfile::tempdir().expect("dest tempdir");
    let written = fake
        .materialize_report(dest.path())
        .expect("materialize")
        .written;
    assert_eq!(written.len(), 1);
    assert_eq!(
        std::fs::read_to_string(dest.path().join("a.md")).expect("read back"),
        "# hi"
    );
}

#[test]
fn ui_returns_canned_answers_in_order() {
    let ui = ScriptedUi::new(FakeUiScript {
        selects: vec![2].into(),
        inputs: vec!["my-model".to_string()].into(),
    });
    assert_eq!(ui.select("pick", &["a", "b", "c"], 0).expect("select"), 2);
    assert_eq!(
        ui.input("name?", None).expect("input"),
        "my-model".to_string()
    );
    ui.panel("title", "body"); // Panel never fails; must not panic.
}

#[test]
fn ui_errors_when_script_exhausted() {
    let ui = ScriptedUi::new(FakeUiScript::default());
    assert_eq!(ui.select("pick", &["a"], 0), Err(WizardError::UserAborted));
    assert_eq!(ui.input("name?", None), Err(WizardError::UserAborted));
}
