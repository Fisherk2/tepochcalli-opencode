"""Conversión de fuentes externas a Markdown con markitdown EN PROCESO (D-b, T5).

Anclado contra el paquete INSTALADO (`markitdown==0.1.9`, source-driven, no de
memoria): `MarkItDown().convert(source: str | requests.Response | Path |
BinaryIO, *, stream_info=None, **kwargs) -> DocumentConverterResult` — en
0.1.9 el campo activo del resultado es `result.markdown` (`text_content` está
soft-deprecado en su propio docstring). Sin subproceso y sin cliente MCP
(decisión D-b del plan §2): la MISMA librería en el MISMO venv, coste cero
adicional sobre D18.

Este módulo ES infraestructura (importa `markitdown`, raíz prohibida para el
dominio y para `tools.*` — test de arquitectura): lo consume SOLO el
composition root (`server.py`) vía la costura `_convert_seam`.
`tools/add_source.py` NUNCA lo importa — la desviación `TOOLS → CONV` del
plan §5 está documentada en el docstring de ese handler.

El markdown resultante se envuelve con el frontmatter de trazabilidad de
spec-markitdown §Contrato (`source_uri`, `converted_at`): es lo que hace
citable un documento cuyos offsets no son fiables. `source_uri` va entrecomillado
como string JSON (URI con `:`/espacios ⇒ YAML válido). Los tests assertan
SOLO la presencia de `converted_at`, nunca su valor (regla G1: cero
aserciones dependientes del tiempo).

**W-02 (review 5-ejes): prefetch propio de `http(s)`.** El URI crudo ya no va
directo a markitdown (que hoy sigue redirects automáticos a ciegas):
`convert_source` fetch-ea con `requests` (`allow_redirects=False`,
`timeout=(10, 60)`) y re-valida SSRF en CADA hop — el guard del borde cubre el
URI entrante, pero la respuesta de un redirect podía saltar a la red interna.
Hops: máx 5, esquemas http/s únicamente; aprobado cada hop, el body se baja con
el cap de bytes (105 MB ≈ el envelope `convert_base64`) y se entrega a
markitdown como `Response` (`_markitdown.py:311`). **S1 (rebinding):** el
hostname se resuelve UNA vez por hop con el mismo canal del guard y la
conexión se fija a ESA IP (Host/SNI originales) — la segunda resolución que
hacía `requests` era la ventana del rebinding. Sin dependencia nueva:
`requests` YA viaja dentro de markitdown (R1/ADR-011).
"""

from __future__ import annotations

import io
import ipaddress
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Final
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from markitdown import MarkItDown, StreamInfo
from markitdown._exceptions import UnsupportedFormatException

from tepochcalli_mcp import formats, paths
from tepochcalli_mcp.paths import redact_uri

_MAX_REDIRECT_HOPS: Final = 5
"""Hops de redirect que el conversor sigue: más de 5 es un bucle, no una fuente."""

_MAX_RESPONSE_BYTES: Final = 105_000_000
"""Cap del body descargado (W-02/W-08): ~100 MB ≡ el envelope de 140M chars base64."""

_FETCH_TIMEOUT: Final = (10.0, 60.0)
"""Timeout del prefetch W-02: (conexión 10 s, lectura entre paquetes 60 s)."""


class _PinnedIPAdapter(requests.adapters.HTTPAdapter):
    """Adapter TLS que verifica contra el hostname original pese a conectar a la IP fija.

    S1 (rebinding): la conexión va a la IP literal del URL; `server_hostname`
    baja al `HTTPSConnection` de urllib3 (2.8) para que SNI y la verificación
    del certificado sigan usando el hostname original — sin esto el cert de un
    https se contrastaría contra la IP y fallaría siempre.
    """

    def __init__(self, hostname: str) -> None:
        super().__init__()
        self.poolmanager.connection_pool_kw["server_hostname"] = hostname


def _pin_resolved_ip(url: str) -> tuple[str, str, dict[str, str]] | None:
    """Resuelve el host UNA vez y devuelve (ip_literal, url_fijo, headers) (S1).

    Rebinding DNS: el guard juzga SU resolución, pero `requests` resolvía DE
    NUEVO al conectar — una segunda respuesta del DNS podía apuntar a la red
    interna. Aquí se resuelve con el MISMO canal del guard
    (`paths._resolve_addresses`), se re-juzga cada IP con
    `paths._is_internal_address` y la conexión se fija a la primera con el
    Host original. Host ya-literal, ausente o DNS vacío ⇒ None (requests
    conecta tal cual, como hoy).
    """
    parts = urlsplit(url)
    host = parts.hostname or ""
    netloc = parts.netloc
    idx, width = netloc.rfind(f"[{host}]"), len(host) + 2
    if idx < 0:
        idx, width = netloc.rfind(host), len(host)
    if not host or idx < 0:
        return None
    try:
        ipaddress.ip_address(host)  # ya es literal: el DNS no interviene, no hay rebinding
        return None
    except ValueError:
        pass
    addresses = paths._resolve_addresses(host)
    for address in addresses:
        if paths._is_internal_address(address):
            raise ValueError(
                f"URI no aceptable: {redact_uri(url)!r} resuelve a una dirección de red interna"
            )
    if not addresses:
        return None  # sin resolver: requests fallará por su cuenta, como hoy
    literal = f"[{addresses[0]}]" if addresses[0].version == 6 else str(addresses[0])
    pinned_url = urlunsplit(
        (parts.scheme, literal + netloc[idx + width :], parts.path, parts.query, parts.fragment)
    )
    return literal, pinned_url, {"Host": netloc[idx:]}


def _fetch_via(url: str, pinned: tuple[str, str, dict[str, str]] | None) -> requests.Response:
    """GET del hop: con `pinned`, conecta a la IP fija con el Host original (S1).

    En https el adapter `_PinnedIPAdapter` restaura el server_hostname del
    hostname original; en http el header Host basta. Con headers vacío no se
    pasan: `requests` pone los suyos.
    """
    if pinned is None:
        return requests.get(url, allow_redirects=False, timeout=_FETCH_TIMEOUT, stream=True)
    literal, pinned_url, headers = pinned
    if urlsplit(pinned_url).scheme == "https":
        session = requests.Session()
        try:
            session.mount(f"https://{literal}", _PinnedIPAdapter(urlsplit(url).hostname or ""))
            return session.get(
                pinned_url,
                headers=headers,
                allow_redirects=False,
                timeout=_FETCH_TIMEOUT,
                stream=True,
            )
        finally:
            session.close()
    return requests.get(
        pinned_url, headers=headers, allow_redirects=False, timeout=_FETCH_TIMEOUT, stream=True
    )


def convert_source(uri: str) -> str:
    """Convierte `uri` (http(s)/file) a Markdown con frontmatter de trazabilidad.

    Cualquier fallo —red, formato no soportado, archivo ilegible— sube como
    excepción markitdown: el handler de `add_source` lo mapea a
    `SOURCE_UNREACHABLE` y el traceback queda en el log stderr del server,
    nunca en el payload (spec-mcp-server §Manejo de errores). Los rechazos
    SSRF de un redirect suben como `paths.VaultPathError` — el handler los
    mapea a `VALIDATION_ERROR` con el MISMO mensaje del guard del borde.
    Revisión Phase 2 (eje 4): al frontmatter se redacta con
    `paths.redact_uri` — credenciales en el URI (userinfo/query secreta)
    jamás se persisten citadas en el vault.
    """
    source: str | requests.Response
    scheme = urlsplit(uri).scheme
    source = _fetch_http(uri) if scheme in ("http", "https") else uri
    markdown = MarkItDown().convert(source).markdown
    redacted = json.dumps(redact_uri(uri), ensure_ascii=False)
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    return f"---\nsource_uri: {redacted}\nconverted_at: {stamp}\n---\n\n{markdown}\n"


def _fetch_http(uri: str) -> requests.Response:
    """Prefetch W-02: el body descargado y los metadatos del wire, hop a hop.

    Por hop: guard SSRF (`paths._deny_internal_host`, el MISMO guard del borde)
    ANTES de conectar; `GET` sin redirects automáticos; con un 3xx con
    `location` se resuelve la URL relativa y se re-juzga el destino siguiente
    (esquemas no http/s RECHAZADOS). El body se baja con el cap de bytes; el
    `Response` devuelto conserva headers/URL, así que markitdown
    (`convert_response`) elige el extractor con el content-type/charset/
    extension del wire.
    """
    url: str = uri
    for _hop in range(_MAX_REDIRECT_HOPS + 1):
        pinned: tuple[str, str, dict[str, str]] | None
        try:
            paths._deny_internal_host(url)
            pinned = _pin_resolved_ip(url)
        except ValueError as exc:
            raise paths.VaultPathError(str(exc)) from None
        response = _fetch_via(url, pinned)
        location = response.headers.get("location") if 300 <= response.status_code < 400 else None
        if location is None:
            _drain_body(response)
            return response
        response.close()
        target = urljoin(url, location)
        if urlsplit(target).scheme not in ("http", "https"):
            raise ValueError(
                f"redirect a esquema no aceptado (solo http/https): {target!r} desde {url!r}"
            )
        url = target
    raise ValueError(f"demasiados redirects (> {_MAX_REDIRECT_HOPS}) desde {uri!r}")


def _drain_body(response: requests.Response) -> None:
    """Baja el body de `response` AL PROPIO response, con el cap de bytes.

    markitdown (`convert_response`) llama `response.iter_content`: reponiendo
    el body descargado como `_content`, el cap aplica — un servidor que
    anuncie gigas no agota la memoria del proceso del vault (W-02/W-08).
    """
    buffer = bytearray()
    for chunk in response.iter_content(chunk_size=65536):
        buffer.extend(chunk)
        if len(buffer) > _MAX_RESPONSE_BYTES:
            response.close()
            raise ValueError(
                f"La respuesta de {response.url!r} supera el tope de {_MAX_RESPONSE_BYTES} "
                "bytes (~100 MB); documentos mayores: guardarlos en el vault y usar "
                "`convert_document`."
            )
    response.close()
    # El body YA fue consumido por esta descarga (stream=True): reponerlo como
    # `_content` hace que `iter_content` de markitdown sirva slices de estos
    # bytes — cap respetado — conservando headers/URL/charset del wire.
    response._content = bytes(buffer)
    response._content_consumed = True


def convert_local(path: Path, *, source_uri: str, extension_hint: str | None = None) -> str:
    """Convierte un documento del vault a Markdown, SIN frontmatter (D36/T9).

    `source_uri` es la entrada tal como la dio el agente: no se usa para leer
    —la frontera B′ ya resolvió `path`— sino para nombrar el fallo tipado. El
    artefacto de `add_source` lleva frontmatter de trazabilidad; este no: un
    `converted_at` haría que dos conversiones idénticas difirieran siempre y
    D66 (idempotencia) sería inalcanzable.

    W-06 (orden del dueño, 2026-11-03): `extension_hint` es el `format` del
    handler — pista de conversión real (`StreamInfo.extension`): un fichero
    SIN extensión + `format=".txt"` se convierte en vez de responder
    `UnsupportedFormatException` engañoso. El sufijo del DELTINO lo fuerza el
    handler (`_destination_suffix`); aquí no se toca.

    `UnsupportedFormatException` no cruza la costura: se traduce a
    `formats.UnsupportedFormatError` (dominio), que el handler mapea a
    `VALIDATION_ERROR` con el catálogo. Cualquier otro fallo sube como
    excepción markitdown ⇒ `SOURCE_UNREACHABLE` en el handler.
    """
    stream_info = StreamInfo(extension=extension_hint) if extension_hint else None
    try:
        return MarkItDown().convert(str(path), stream_info=stream_info).markdown
    except UnsupportedFormatException:
        raise _unsupported(source_uri) from None


def convert_bytes(data: bytes, *, filename: str | None, extension: str, source_uri: str) -> str:
    """Convierte bytes en contexto a Markdown, SIN frontmatter (T10/D36).

    Anclado al paquete INSTALADO (`markitdown==0.1.9`): `StreamInfo` es
    `@dataclass(kw_only=True, frozen=True)` con `extension`/`filename`
    (`markitdown/_stream_info.py:5-16`) y `MarkItDown().convert(source,
    *, stream_info=None)` acepta un `BinaryIO` (`_markitdown.py:322-366`,
    `convert_stream`). `extension` es la pista que elige el extractor — va con
    punto (`.docx`), igual que la que `convert_local` deriva del path—;
    `filename` solo refuerza la identidad y el tipo.

    `source_uri` nombra el fallo tipado (la entrada tal como llegó); el
    artefacto no lleva frontmatter: lo haría distinto en cada llamada y D66
    (idempotencia) sería inalcanzable. Mismo mapeo de error que
    `convert_local`: `UnsupportedFormatException` ⇒ `formats.
    UnsupportedFormatError`; el resto sube ⇒ `SOURCE_UNREACHABLE` en el borde.
    """
    try:
        return (
            MarkItDown()
            .convert(
                io.BytesIO(data), stream_info=StreamInfo(extension=extension, filename=filename)
            )
            .markdown
        )
    except UnsupportedFormatException:
        raise _unsupported(source_uri) from None


def _unsupported(source_uri: str) -> formats.UnsupportedFormatError:
    """Fallo tipado de formato no soportado con el catálogo (mismo template).

    La traducción `UnsupportedFormatException` ⇒ `formats.
    UnsupportedFormatError` es idéntica en `convert_local` y `convert_bytes`:
    mensaje con `source_uri` y la lista curada, `from None` para no arrastrar
    el traceback markitdown al log del server. El handler la mapea a
    `VALIDATION_ERROR` con el catálogo.
    """
    return formats.UnsupportedFormatError(
        f"formato no soportado para {source_uri!r}; "
        f"usa uno de {', '.join(formats.SUPPORTED_FORMATS)}"
    )
