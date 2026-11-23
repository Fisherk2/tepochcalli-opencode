//! R-offline-1 (T13): la sonda de red del preflight, en proceso y contra
//! loopback real — sin red externa ni proceso hijo.
//!
//! El contrato son dos preguntas distintas: «¿hay red?» (cualquier status
//! HTTP cuenta, 503 incluido) y «¿el transporte falla?» (⇒ `NetDownload`),
//! más el guard L4-2 que decide ANTES de la red: `https_only` rechaza
//! `http://` no-loopback sin abrir socket ni consultar DNS.

use std::io::{BufRead, BufReader, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::sync::{Mutex, Once};
use std::time::{Duration, Instant};

use tepochcalli::adapters::UreqHttpClient;
use tepochcalli::ports::HttpClient;
use tepochcalli::WizardError;

/// Los proxies del entorno romperían el loopback; una sola escritura, antes
/// de que ningún test sondee (el resto espera a este `Once`). Solo el
/// loopback se salva del proxy: `*` también apagaría el `ALL_PROXY` que los
/// tests del guard L4-2 fijan para demostrar que la petición NO-loopback
/// saldría de no existir el guard (con `*` el guard sería indemostrable).
fn no_proxy_for_loopback() {
    static ONCE: Once = Once::new();
    ONCE.call_once(|| std::env::set_var("NO_PROXY", "127.0.0.1,localhost"));
}

/// Serializa el fijado de `ALL_PROXY` entre los tests del guard: si dos lo
/// apuntaran a la vez, el aserto del otro correría contra un proxy ya
/// cerrado y perdería capacidad de discriminar.
static PROXY_ENV: Mutex<()> = Mutex::new(());

/// Lee una petición HTTP completa (hasta la línea en blanco): cerrar con
/// bytes del cliente sin leer dispararía RST y rompería el determinismo.
fn read_http_headers(socket: &TcpStream) {
    let mut reader = BufReader::new(socket.try_clone().expect("clone socket"));
    loop {
        let mut line = String::new();
        match reader.read_line(&mut line) {
            Ok(0) | Err(_) => return,
            Ok(_) if line == "\r\n" || line == "\n" => return,
            Ok(_) => {}
        }
    }
}

/// Restaura `ALL_PROXY` al valor previo al soltar: `set_var` muta el padre
/// de TODOS los tests del binario, así que no puede quedar pegado.
struct AllProxyGuard {
    previous: Option<std::ffi::OsString>,
}

impl Drop for AllProxyGuard {
    fn drop(&mut self) {
        match self.previous.take() {
            Some(value) => std::env::set_var("ALL_PROXY", value),
            None => std::env::remove_var("ALL_PROXY"),
        }
    }
}

/// Proxy http vivo en loopback + `ALL_PROXY` apuntando a él: cualquier
/// petición `http://` no-loopback que ESCAPE del guard termina aquí y
/// contesta 200. Devuelve el addr (para desbloquear un `accept` que el
/// guard impidió), el hilo servidor y el guard que restaura `ALL_PROXY`.
fn live_mirror_proxy() -> (SocketAddr, std::thread::JoinHandle<()>, AllProxyGuard) {
    let listener = TcpListener::bind("127.0.0.1:0").expect("bind mirror proxy");
    let addr = listener.local_addr().expect("mirror proxy addr");
    let server = std::thread::spawn(move || {
        let (mut socket, _) = listener.accept().expect("accept at mirror proxy");
        // ureq 3.5 tunela vía CONNECT incluso con proxy http (`is_connect`
        // es true para Http|Https): primero el handshake, luego la petición
        // real dentro del túnel. Ambas lecturas se completan (o llegan a
        // EOF con el dummy) antes de responder.
        read_http_headers(&socket);
        let _ = socket.write_all(b"HTTP/1.1 200 Connection Established\r\n\r\n");
        read_http_headers(&socket);
        let _ = socket.write_all(b"HTTP/1.1 200 OK\r\ncontent-length: 0\r\n\r\n");
    });
    let previous = std::env::var_os("ALL_PROXY");
    std::env::set_var("ALL_PROXY", format!("http://{addr}"));
    (addr, server, AllProxyGuard { previous })
}

/// Petición completa para desbloquear el `accept` del proxy cuando el guard
/// impidió que la sonda llegara (sin ella el `join` colgaría el hilo).
fn dummy_proxy_request(addr: SocketAddr) {
    if let Ok(mut stream) = TcpStream::connect(addr) {
        let _ = stream.write_all(b"GET / HTTP/1.1\r\nHost: mirror-public.test\r\n\r\n");
    }
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

/// Hueco #3 — L4-2 en `probe`: con `https_only=true` (default) una
/// `http://` no-loopback se rechaza ANTES de abrir socket o consultar DNS,
/// así que el resultado es `NetDownload` (exit 20 del preflight) y no
/// depende de la red: el proxy vivo de este test queda sin recibir ni una
/// conexión de la sonda.
///
/// Regresión que detecta: si `probe` dejara de pasar por el guard (o el
/// rechazo se mapeara a otro `WizardError`), la petición saldría por el
/// proxy vivo y el aserto pondría el test en rojo. Un proxy MUERTO no
/// discriminaría: también daría `Err` aunque el guard no existiera.
#[test]
fn probe_http_no_loopback_se_rechaza_sin_tocar_la_red() {
    no_proxy_for_loopback();
    let _gate = PROXY_ENV
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner());
    let (proxy, server, _env) = live_mirror_proxy();

    let result = UreqHttpClient::new().probe("http://mirror-public.test/x");

    dummy_proxy_request(proxy);
    server.join().expect("mirror proxy thread");
    assert_eq!(
        result,
        Err(WizardError::NetDownload),
        "http no-loopback sin autorización ⇒ NetDownload (exit 20)"
    );
}

/// Hueco #4(c) — camino del mirror http consentido (L4-2): con
/// `https_only=false` la MISMA `http://` no-loopback sí se sondea — el
/// cliente autorizado llega al transporte y el proxy vivo contesta 200.
///
/// Regresión que detecta: si `with_https_only(false)` dejara de relajar el
/// guard (o el constructor desapareciera), el rechazo temprano devolvería
/// `Err(NetDownload)` en vez de `Ok(())`. Comparte proxy vivo con el test
/// del guard: la pareja fija el contrato completo de L4-2 en `probe`.
#[test]
fn probe_con_mirror_http_autorizado_sondea_ok() {
    no_proxy_for_loopback();
    let _gate = PROXY_ENV
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner());
    let (proxy, server, _env) = live_mirror_proxy();

    let result = UreqHttpClient::with_https_only(false).probe("http://mirror-public.test/x");

    dummy_proxy_request(proxy);
    server.join().expect("mirror proxy thread");
    assert_eq!(result, Ok(()), "el mirror autorizado debe sondear");
}

/// Hueco #4(a) — borde del contrato de `probe`: sigue redirects — un 302
/// en loopback con destino vivo termina en `Ok(())`, muy por debajo del
/// `PROBE_TIMEOUT` (8 s) y con el mismo salto que acepta el cliente.
///
/// Regresión que detecta: un `max_redirects` a 0 (o tratar el 3xx como
/// fallo aunque `http_status_as_error(false)`) convertiría el salto en
/// `NetDownload` y el test saldría en rojo.
#[test]
fn probe_sigue_un_redirect_hasta_un_200() {
    no_proxy_for_loopback();
    // Destino final del redirect.
    let final_listener = TcpListener::bind("127.0.0.1:0").expect("bind final");
    let final_addr = final_listener.local_addr().expect("final addr");
    let final_server = std::thread::spawn(move || {
        let (mut socket, _) = final_listener.accept().expect("accept final");
        read_http_headers(&socket);
        socket
            .write_all(b"HTTP/1.1 200 OK\r\ncontent-length: 0\r\n\r\n")
            .expect("write 200");
    });

    // Origen que responde 302 hacia el destino.
    let origin_listener = TcpListener::bind("127.0.0.1:0").expect("bind origin");
    let origin_addr = origin_listener.local_addr().expect("origin addr");
    let origin_server = std::thread::spawn(move || {
        let (mut socket, _) = origin_listener.accept().expect("accept origin");
        read_http_headers(&socket);
        let response = format!(
            "HTTP/1.1 302 Found\r\nlocation: http://{final_addr}/ok\r\ncontent-length: 0\r\n\r\n"
        );
        socket.write_all(response.as_bytes()).expect("write 302");
    });

    let result = UreqHttpClient::new().probe(&format!("http://{origin_addr}/x"));
    origin_server.join().expect("origin thread");
    final_server.join().expect("final thread");

    assert!(
        result.is_ok(),
        "un redirect seguido hasta un 200 cuenta como red viva: {result:?}"
    );
}

/// Hueco #4(b) — borde del contrato de `probe`: un servidor en loopback
/// que acepta pero NUNCA contesta agota `PROBE_TIMEOUT` (8 s) ⇒
/// `NetDownload`. Tarda ~8 s: es loopback, sin red real; el hilo se cierra
/// con `join` tras liberar el socket.
///
/// Regresión que detecta: sin el timeout de la sonda `probe` colgaría
/// (o fallaría antes de tiempo); el suelo de 7 s prueba que el fallo vino
/// del presupuesto de 8 s y no de un cierre prematuro del socket.
#[test]
fn probe_con_servidor_mudo_agota_el_timeout() {
    no_proxy_for_loopback();
    let listener = TcpListener::bind("127.0.0.1:0").expect("bind mute server");
    let addr = listener.local_addr().expect("mute addr");
    let (tx, rx) = std::sync::mpsc::channel::<()>();
    let server = std::thread::spawn(move || {
        // `_socket` vive hasta el final del scope: cerrarlo de inmediato
        // haría fallar a ureq de vuelta, no por timeout.
        let (_socket, _) = listener.accept().expect("accept probe");
        let _ = rx.recv_timeout(Duration::from_secs(20));
    });

    let start = Instant::now();
    let result = UreqHttpClient::new().probe(&format!("http://{addr}/x"));
    let elapsed = start.elapsed();
    let _ = tx.send(());
    // Desbloquea un `accept` que la sonda no llegó a usar (si el guard
    // rechazara también el loopback), para que el `join` nunca cuelgue.
    let _ = TcpStream::connect(addr);
    server.join().expect("mute server thread");

    assert_eq!(result, Err(WizardError::NetDownload));
    assert!(
        elapsed >= Duration::from_secs(7),
        "el fallo debe venir del presupuesto de 8 s, no de un cierre prematuro: {elapsed:?}"
    );
}
