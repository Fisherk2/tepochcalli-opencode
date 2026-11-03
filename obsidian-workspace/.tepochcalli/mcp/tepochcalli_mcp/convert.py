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

shortcut: `convert_source` no expone timeout de red — una URL que cuelgue
bloquea el worker de `asyncio.to_thread` del handler. Aceptado en v1 (el
harness impone su propio timeout de tool call); si se necesita, prefetch
con `requests` y `timeout=` (también soportado por `convert(source)`).
"""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path

from markitdown import MarkItDown, StreamInfo
from markitdown._exceptions import UnsupportedFormatException

from tepochcalli_mcp import formats
from tepochcalli_mcp.paths import redact_uri


def convert_source(uri: str) -> str:
    """Convierte `uri` (http(s)/file) a Markdown con frontmatter de trazabilidad.

    Cualquier fallo —red, formato no soportado, archivo ilegible— sube como
    excepción markitdown: el handler de `add_source` lo mapea a
    `SOURCE_UNREACHABLE` y el traceback queda en el log stderr del server,
    nunca en el payload (spec-mcp-server §Manejo de errores).
    Revisión Phase 2 (eje 4): el URI va al fetch TAL CUAL, pero al frontmatter
    se redacta con `paths.redact_uri` — credenciales en el URI (userinfo/query
    secreta) jamás se persisten citadas en el vault.
    """
    markdown = MarkItDown().convert(uri).markdown
    source = json.dumps(redact_uri(uri), ensure_ascii=False)
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    return f"---\nsource_uri: {source}\nconverted_at: {stamp}\n---\n\n{markdown}\n"


def convert_local(path: Path, *, source_uri: str) -> str:
    """Convierte un documento del vault a Markdown, SIN frontmatter (D36/T9).

    `source_uri` es la entrada tal como la dio el agente: no se usa para leer
    —la frontera B′ ya resolvió `path`— sino para nombrar el fallo tipado. El
    artefacto de `add_source` lleva frontmatter de trazabilidad; este no: un
    `converted_at` haría que dos conversiones idénticas difirieran siempre y
    D66 (idempotencia) sería inalcanzable.

    `UnsupportedFormatException` no cruza la costura: se traduce a
    `formats.UnsupportedFormatError` (dominio), que el handler mapea a
    `VALIDATION_ERROR` con el catálogo. Cualquier otro fallo sube como
    excepción markitdown ⇒ `SOURCE_UNREACHABLE` en el handler.
    """
    try:
        return MarkItDown().convert(str(path)).markdown
    except UnsupportedFormatException:
        raise formats.UnsupportedFormatError(
            f"formato no soportado para {source_uri!r}; "
            f"usa uno de {', '.join(formats.SUPPORTED_FORMATS)}"
        ) from None


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
        raise formats.UnsupportedFormatError(
            f"formato no soportado para {source_uri!r}; "
            f"usa uno de {', '.join(formats.SUPPORTED_FORMATS)}"
        ) from None
