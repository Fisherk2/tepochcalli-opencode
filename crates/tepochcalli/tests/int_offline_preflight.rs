//! R-offline-1 (T13): la sonda de red del preflight, en proceso y contra
//! loopback real — sin red externa ni proceso hijo.
//!
//! El contrato son dos preguntas distintas: «¿hay red?» (cualquier status
//! HTTP cuenta, 503 incluido) y «¿el transporte falla?» (⇒ `NetDownload`).

use std::io::{BufRead, BufReader, Write};
use std::net::TcpListener;
use std::sync::Once;

use tepochcalli::adapters::UreqHttpClient;
use tepochcalli::ports::HttpClient;
use tepochcalli::WizardError;

/// Los proxies del entorno romperían el loopback; una sola escritura, antes
/// de que ningún test sondee (el resto espera a este `Once`).
fn no_proxy_for_loopback() {
    static ONCE: Once = Once::new();
    ONCE.call_once(|| std::env::set_var("NO_PROXY", "*"));
}

#[test]
fn probe_ok_con_cualquier_status() {
    no_proxy_for_loopback();
    let listener = TcpListener::bind("127.0.0.1:0").expect("bind loopback");
    let addr = listener.local_addr().expect("loopback addr");
    let server = std::thread::spawn(move || {
        let (mut socket, _) = listener.accept().expect("accept probe");
        let mut reader = BufReader::new(socket.try_clone().expect("clone socket"));
        let mut line = String::new();
        let _ = reader.read_line(&mut line);
        socket
            .write_all(b"HTTP/1.1 503 Service Unavailable\r\ncontent-length: 0\r\n\r\n")
            .expect("write 503");
    });

    let result = UreqHttpClient::new().probe(&format!("http://{addr}/x"));
    server.join().expect("server thread");

    assert!(
        result.is_ok(),
        "un status HTTP cuenta como red viva: {result:?}"
    );
}

#[test]
fn probe_sin_red_es_net_download() {
    no_proxy_for_loopback();
    // Puerto cerrado: bind + drop deja el loopback sin listener.
    let addr = TcpListener::bind("127.0.0.1:0")
        .expect("bind a port to close")
        .local_addr()
        .expect("loopback addr");

    let result = UreqHttpClient::new().probe(&format!("http://{addr}/x"));

    assert_eq!(result, Err(WizardError::NetDownload));
}
