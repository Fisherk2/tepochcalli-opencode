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

import json
from datetime import UTC, datetime

from markitdown import MarkItDown


def convert_source(uri: str) -> str:
    """Convierte `uri` (http(s)/file) a Markdown con frontmatter de trazabilidad.

    Cualquier fallo —red, formato no soportado, archivo ilegible— sube como
    excepción markitdown: el handler de `add_source` lo mapea a
    `SOURCE_UNREACHABLE` y el traceback queda en el log stderr del server,
    nunca en el payload (spec-mcp-server §Manejo de errores).
    """
    markdown = MarkItDown().convert(uri).markdown
    source = json.dumps(uri, ensure_ascii=False)
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    return f"---\nsource_uri: {source}\nconverted_at: {stamp}\n---\n\n{markdown}\n"
