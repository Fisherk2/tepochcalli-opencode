"""Handler de `convert_base64`: bytes en contexto → `.md` en disco → resumen (T10).

Mismo contrato que `convert_document` (ADR-009), pero la entrada son **bytes en
base64** que el agente ya tiene en contexto: no hay ruta que validar como
entrada, solo la pista de tipo y el destino. El cuerpo NUNCA cruza el wire: se
escribe a disco y la respuesta es el resumen de 5 claves de `summary.py`.
Convertir ≠ indexar (D49).

Contrato y precedencia, en orden:

1. **Pista de tipo obligatoria** (D38) — `format` o la extensión de `filename`;
   sin pista (o con una fuera del catálogo) ⇒ `VALIDATION_ERROR`. Adivinar el
   extractor convertiría bytes opacos en markdown plausible pero falso; el
   error nombra `list_formats` para que el agente corrija la llamada.
2. **Decodificación** — `base64.b64decode(..., validate=True)`; corrupto ⇒
   `VALIDATION_ERROR` (nunca `INTERNAL`: es un argumento mal formado, D39).
3. **Identidad** (D38) — `source_uri` = `filename` si vino; sin él,
   `base64:<sha256-8>` de los bytes decodificados. La entrada tal como llegó,
   nunca inventada.
4. **Frontera B′** (D31) — `output_path` con `validate_vault_path(...,
   must_exist=False)`; omitido ⇒ `00-resources/<slug>.md`.
5. **Conversión** — costura inyectada por el composition root (`tools/` no
   importa markitdown). Markdown vacío ⇒ `SOURCE_UNREACHABLE` con `GUIDE_OCR` y
   **sin** escribir parciales.
6. **Escritura + resumen** — `writer.write_atomic` (idempotencia D66) y
   `summary.build_summary` leído del fichero escrito.

**OM-7:** los bytes son material **no confiado**: aquí solo se decodifican y se
pasan al conversor; no se interpretan, ejecutan ni inyectan en ningún prompt.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Final

from tepochcalli_mcp import errors, formats, paths
from tepochcalli_mcp.tools._convert_tail import BytesConvert, destination_path, write_converted

logger = logging.getLogger(__name__)

MAX_BASE64_CHARS: Final = 140_000_000
"""Tope de `data` base64 (W-08): ~100 MB decodificados (4 chars → 3 bytes).

Los bytes viajan EN CONTEXTO del agente: sin tope, la decodificación sería un
DoS de memoria en el proceso del vault. Documentos mayores van por `file:`
(`convert_document`) — el disco nunca pasa por el wire.
"""


@errors.internal_guard
async def convert_base64(
    data: str,
    output_path: str | None = None,
    format: str | None = None,
    filename: str | None = None,
    *,
    vault_root: Callable[[], Path],
    convert: BytesConvert,
) -> dict[str, object]:
    """Resumen de 5 claves del `.md` escrito — el cuerpo no viaja (D36).

    `convert` es la costura `convert_bytes(data, filename=…, extension=…,
    source_uri=…)` del composition root; argumentos posicionales del contrato
    MCP: `data`, `output_path?`, `format?`, `filename?`. La cola (fallos
    tipados, vacío, escritura, resumen) vive en `tools/_convert_tail.py`.
    """
    root = vault_root().resolve()
    try:
        extension = _effective_extension(format, filename)
        raw = _decode(data)
        digest = hashlib.sha256(raw).hexdigest()[:8]
        source_uri = filename or f"base64:{digest}"
        # Sin `filename`, el slug sale de la MISMA identidad que `source_uri`
        # (`base64-<sha256-8>`): reintentar escribe en el mismo destino y la
        # idempotencia de D66 aplica.
        slug = paths.slugify_uri(filename) if filename else f"base64-{digest}"
        target = paths.validate_vault_path(
            destination_path(output_path, slug, extension if format else ".md"),
            root,
            must_exist=False,
        )
    except paths.VaultPathError as exc:
        return errors.validation_error(str(exc), exc.details)
    return await write_converted(
        run_convert=lambda: asyncio.to_thread(
            convert, raw, filename=filename, extension=extension, source_uri=source_uri
        ),
        target=target,
        source_uri=source_uri,
        vault_root=root,
        tool="convert_base64",
        logger=logger,
    )


def _effective_extension(format: str | None, filename: str | None) -> str:
    """Extensión que elige el extractor: `format`, o la del `filename` (D38).

    Sin ninguna de las dos ⇒ `VaultPathError` que nombra `list_formats`: sin
    pista markitdown no puede elegir convertidor (D38). Una pista fuera del
    catálogo cae igual, con la lista del catálogo en `details` (D39).
    """
    hint = formats.normalize_suffix(format or (Path(filename).suffix if filename else ""))
    if not hint:
        raise paths.VaultPathError(
            "sin pista de tipo: pasa `format` o un `filename` con extensión "
            "(consulta `list_formats` para el catálogo)",
            {"formats": list(formats.SUPPORTED_FORMATS)},
        )
    if not formats.is_supported(hint):
        raise paths.VaultPathError(
            f"formato no soportado: {hint!r}", {"formats": list(formats.SUPPORTED_FORMATS)}
        )
    return hint


def _decode(data: str) -> bytes:
    """Bytes del documento; base64 inválido o demasiado grande ⇒ `VaultPathError`.

    W-08: el corte de tamaño es `VALIDATION_ERROR` nombando el tope — una
    entrada de cientos de MB en contexto es una llamada mal formada, no un
    fallo del server (D39), y decodificarla sería un auto-DoS.
    """
    if len(data) > MAX_BASE64_CHARS:
        raise paths.VaultPathError(
            f"base64 demasiado grande en `data`: {len(data)} chars superan el tope "
            f"{MAX_BASE64_CHARS} (~100 MB decodificados); guarda el documento en el "
            "vault (una raíz de `INDEXER_DIR`) y usa `convert_document`.",
            {"field": "data", "chars": len(data), "limit_chars": MAX_BASE64_CHARS},
        )
    try:
        return base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise paths.VaultPathError(f"base64 inválido en `data`: {exc}", {"field": "data"}) from None
