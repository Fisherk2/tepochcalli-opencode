"""Handler de `convert_document`: documento del vault → `.md` en disco → resumen (T9).

El defecto que esta tool cierra (ADR-009, diagnosis `fix01`): el MCP standalone
devolvía el markdown **completo** en `content[0].text` y una conversión de 100
páginas saturaba la ventana de contexto. Aquí el cuerpo NUNCA cruza el wire: se
escribe a disco y la respuesta es el resumen de 5 claves de `summary.py`, leído
del FICHERO escrito (OM-1). Convertir ≠ indexar (D49): el motor indexa los
originales; para indexar se usa `index_refresh` o `add_source`.

Contrato y precedencia, en orden:

1. **Frontera B′** (D31) — `path` con `validate_vault_path(..., must_exist=True,
   expect="file")`: inexistente o directorio ⇒ `VALIDATION_ERROR` ANTES de
   tocar markitdown (D64; sin esto el motor lo volvería `INTERNAL` por una ruta
   mal escrita). `output_path` con `must_exist=False`: se valida su padre.
2. **Catálogo** (D39) — extensión efectiva (`format` o la del fichero) fuera de
   `formats.SUPPORTED_FORMATS` ⇒ `VALIDATION_ERROR` con la lista en `details`.
3. **Conversión** — costura inyectada por el composition root (`tools/` no
   importa markitdown). `formats.UnsupportedFormatError` ⇒ `VALIDATION_ERROR`;
   cualquier otro fallo ⇒ `SOURCE_UNREACHABLE`. Markdown vacío o solo espacios
   ⇒ `SOURCE_UNREACHABLE` con `GUIDE_OCR` («este conversor no hace OCR») y
   **sin** escribir parciales.
4. **Escritura** — `writer.write_atomic` (la MISMA función que `add_source`):
   idéntico ⇒ no reescribe; distinto ⇒ `VALIDATION_ERROR` con alternativo
   propuesto. Nunca se sobrescribe material del usuario (D66).
5. **Resumen** — exactamente `summary.build_summary(escrito, …)`: `written_to`,
   `source_uri`, `bytes`, `chars`, `preview` (+ `truncated`). Sin clave `ok`.

`@errors.internal_guard` (G1) envuelve el handler completo: cualquier fallo no
mapeado ⇒ `INTERNAL` canónico, con el traceback solo en el log stderr.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path

from tepochcalli_flow.citation import RESOURCES_DIR

from tepochcalli_mcp import errors, formats, paths, summary, writer

logger = logging.getLogger(__name__)


@errors.internal_guard
async def convert_document(
    path: str,
    output_path: str | None = None,
    format: str | None = None,
    *,
    vault_root: Callable[[], Path],
    convert: Callable[..., str],
) -> dict[str, object]:
    """Resumen de 5 claves del `.md` escrito — el cuerpo no viaja (D36).

    `convert` es la costura `convert_local(path, source_uri=…)` del composition
    root; argumentos posicionales del contrato MCP: `path`, `output_path?`,
    `format?`.
    """
    root = vault_root().resolve()
    try:
        source = paths.validate_vault_path(path, root, must_exist=True, expect="file")
        suffix = _suffix(format, source)
        target = paths.validate_vault_path(
            _destination(path, output_path, suffix), root, must_exist=False
        )
    except paths.VaultPathError as exc:
        return errors.validation_error(str(exc), exc.details)
    try:
        content = await asyncio.to_thread(convert, source, source_uri=path)
    except formats.UnsupportedFormatError as exc:
        return errors.validation_error(str(exc), {"formats": list(formats.SUPPORTED_FORMATS)})
    except Exception as exc:  # corrupto, cifrado: no es una ruta mal escrita (D39)
        logger.exception("convert_document: fallo de conversión para %s", path)
        return errors.source_unreachable(path, type(exc).__name__)
    if not content.strip():
        return errors.source_unreachable(path, "EmptyMarkdown", guide=errors.GUIDE_OCR)
    try:
        written = writer.write_atomic(target, content)
    except paths.VaultPathError as exc:
        return errors.validation_error(str(exc), exc.details)
    return summary.build_summary(written, source_uri=path, vault_root=root)


def _suffix(format: str | None, source: Path) -> str:
    """Extensión del DESTINO: `format` la fuerza; sin él, `.md` (D37).

    La validación del catálogo usa la extensión EFECTIVA (`format` como pista de
    tipo o la del documento): fuera del catálogo ⇒ `VaultPathError` (el borde lo
    mapea a `VALIDATION_ERROR` con la lista).
    """
    hinted = _normalize_extension(format) if format else ""
    effective = hinted or _normalize_extension(source.suffix)
    if not formats.is_supported(effective):
        raise paths.VaultPathError(
            f"formato no soportado: {effective or '(sin extensión)'!r}",
            {"formats": list(formats.SUPPORTED_FORMATS)},
        )
    return hinted or ".md"


def _normalize_extension(extension: str) -> str:
    """`.PDF`/`pdf` ⇒ `.pdf`: el catálogo compara extensiones normalizadas."""
    normalized = extension.strip().lower()
    return normalized if not normalized or normalized.startswith(".") else f".{normalized}"


def _destination(path: str, output_path: str | None, suffix: str) -> str:
    """Destino pedido o `00-Resources/<slug><suffix>`; sin auto-renombrado (D37/D66).

    El alternativo ante colisión solo se **propone** en el error de
    `writer.write_atomic`: renombrar solo rompería la idempotencia.
    """
    candidate = (
        Path(output_path)
        if output_path is not None
        else Path(RESOURCES_DIR) / (paths.slugify_uri(path) + suffix)
    )
    return str(candidate.with_suffix(suffix))
