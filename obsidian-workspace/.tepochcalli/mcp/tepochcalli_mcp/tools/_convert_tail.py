"""Cola compartida de los handlers del conversor (T9/T10, ADR-009).

`convert_document` y `convert_base64` terminaban igual byte-a-byte: fallos de
conversión tipados (`VALIDATION_ERROR` con el catálogo, `SOURCE_UNREACHABLE`
para cualquier otro), markdown vacío ⇒ `GUIDE_OCR` sin escribir parciales,
`writer.write_atomic` ⇒ `VaultPathError` ⇒ `VALIDATION_ERROR`, y el resumen de
5 claves de `summary.py`. Aquí vive UNA vez — la precedencia de ADR-009 se
edita en un solo sitio; la ÚNICA diferencia real entre los dos handlers es la
costura de conversión, que entra como callable.

`tools/` NUNCA importa `convert.py` (markitdown) — la costura la inyecta el
composition root; este módulo es dominio puro del server igual que sus vecinos.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from tepochcalli_mcp import errors, formats, paths, summary, writer


async def write_converted(
    *,
    run_convert: Callable[[], Awaitable[str]],
    target: Path,
    source_uri: str,
    vault_root: Path,
    tool: str,
    logger: logging.Logger,
) -> dict[str, object]:
    """Del `content` convertido al resumen escrito — la cola común de ADR-009.

    `run_convert` devuelve el markdown (el cuerpo no cruza el wire, D36);
    `source_uri` es la identidad del input (nombra fallos y `written_to` vía
    `build_summary`); `tool` es solo el prefijo del log stderr.
    """
    try:
        content = await run_convert()
    except formats.UnsupportedFormatError as exc:
        return errors.validation_error(str(exc), {"formats": list(formats.SUPPORTED_FORMATS)})
    except Exception as exc:  # corrupto, cifrado: no es una entrada mal escrita (D39)
        logger.exception("%s: fallo de conversión para %s", tool, source_uri)
        return errors.source_unreachable(source_uri, type(exc).__name__)
    if not content.strip():
        return errors.source_unreachable(source_uri, "EmptyMarkdown", guide=errors.GUIDE_OCR)
    try:
        written = writer.write_atomic(target, content)
    except paths.VaultPathError as exc:
        return errors.validation_error(str(exc), exc.details)
    return summary.build_summary(written, source_uri=source_uri, vault_root=vault_root)
