"""W-02 (review 5-ejes): prefetch del conversor con guard SSRF por hop (unit).

`convert_source` deja de pasar el URI crudo a markitdown (redirects automáticos
a ciegas): fetch propio con `requests` (`allow_redirects=False`,
`timeout=(10, 60)`) y re-validación SSRF de cada hop — un redirect hacia la
red interna sube `paths.VaultPathError` ⇒ `VALIDATION_ERROR` en el handler.

Casos con stub HTTP local (`127.0.0.1`), asiento sobre el guard REAL de
`paths._deny_internal_host` — el fixture solo lo vuelve permisivo para el
loopback, que es la única frontera de estos tests (localhost es su oficio
aquí): un guard real que deniegue `127.0.0.1` haría imposible probar en
máquina local el CAMINO del conversor (la denegación de hosts internos
propiamente dicha ya vive en `test_mcp_paths.py`):

* (a) redirect a interno ⇒ rechazo ANTES de conectar a `_METADATA_URL` (que es
  una constante, no un servidor montado);
* (b) hop legítimo ⇒ convierte (el `Response` llega a markitdown);
* (c) sin respuesta (timeout) ⇒ no cuelga (stub que lanza `requests.Timeout`).
"""

from __future__ import annotations

import http.server
import threading
from collections.abc import Iterator
from urllib.parse import urlsplit

import pytest
import requests
from tepochcalli_mcp import convert, paths

_CONTENT = b"linea de datos\notra linea\n"
"""Body plano que el stub sirve; markitdown lo reproduce tal cual (text/plain)."""

_METADATA_URL = "http://169.254.169.254/latest/meta-data"
"""Destino interno clásico (cloud metadata): constante de test, JAMÁS se conecta."""

_LOCAL_HOSTS = ("127.0.0.1", "localhost")


class _SourceHandler(http.server.BaseHTTPRequestHandler):
    """Servidor de test: corpus `text/plain`, o 302 → constante del caso."""

    redirect_to: str | None = None

    def do_GET(self) -> None:  # noqa: N802 (nombre de la API del stdlib)
        """Sirve un 302 (si el caso configura destino) o el corpus plano."""
        if type(self).redirect_to is not None:
            self.send_response(302)
            self.send_header("Location", type(self).redirect_to)
            self.end_headers()
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(_CONTENT)))
            self.end_headers()
            self.wfile.write(_CONTENT)

    def log_message(self, *args: object) -> None:
        """Silencio: el access log del stub no es salida de los tests."""


def _make_server(redirect_to: str | None) -> http.server.HTTPServer:
    """Servidor efímero en 127.0.0.1 con el comportamiento del caso."""
    handler = type("Handler", (_SourceHandler,), {"redirect_to": redirect_to})
    server = http.server.HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture()
def allow_localhost_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """El guard REAL de `paths`, tolerando el loopback del stub (solo aquí)."""
    real = paths._deny_internal_host

    def permissive_for_loopback(url: str) -> None:
        if urlsplit(url).hostname in _LOCAL_HOSTS:
            return
        real(url)

    monkeypatch.setattr(paths, "_deny_internal_host", permissive_for_loopback)


@pytest.fixture()
def plain_url(allow_localhost_guard: None) -> Iterator[str]:
    """URL base de un stub que entrega `_CONTENT` como `text/plain`."""
    server = _make_server(None)
    try:
        yield f"http://127.0.0.1:{server.server_port}/paper.txt"
    finally:
        server.shutdown()
        server.server_close()


def test_a_redirect_to_an_internal_address_is_rejected_before_connecting(
    allow_localhost_guard: None,
) -> None:
    """(a) 127.0.0.1 → 302 → `169.254.169.254` ⇒ `VaultPathError`, validado por hop.

    El destino interno es una CONSTANTE: si el guard corriera DESPUÉS del
    fetch (o solo en hop 1), el write del test intentaría conectar. Guard por
    hop = el mismo criterio del borde, aplicado a lo que RESUELVE el redirect.
    """
    server = _make_server(_METADATA_URL)
    try:
        url = f"http://127.0.0.1:{server.server_port}/start"
        with pytest.raises(paths.VaultPathError, match="169.254.169.254"):
            convert.convert_source(url)
    finally:
        server.shutdown()
        server.server_close()


def test_b_no_redirect_converts_the_body_via_the_response(plain_url: str) -> None:
    """(b) hop legítimo ⇒ el markdown trae el cuerpo y el frontmatter trazable."""
    markdown = convert.convert_source(plain_url)

    assert "linea de datos" in markdown
    assert "otra linea" in markdown
    assert markdown.startswith("---\nsource_uri: "), "el frontmatter de trazabilidad sigue"
    assert "converted_at:" in markdown


def test_c_no_response_times_out_without_hanging(
    allow_localhost_guard: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(c) el fetch con timeout no queda colgado ante una fuente sin respuesta."""

    def sleepy(*args: object, **kwargs: object) -> None:
        raise requests.exceptions.ConnectTimeout("sin respuesta (stub)")

    monkeypatch.setattr(convert.requests, "get", sleepy)
    with pytest.raises(requests.exceptions.ConnectTimeout):
        convert.convert_source("http://127.0.0.1/stubbed")
