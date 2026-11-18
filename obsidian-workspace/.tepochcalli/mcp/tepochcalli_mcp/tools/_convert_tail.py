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

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Final, Protocol

from tepochcalli_flow.citation import RESOURCES_DIR

from tepochcalli_mcp import errors, formats, paths, summary, writer

CONVERT_TIMEOUT: Final = 120.0
"""Guarda de pared del convert (S4min): tope de espera del parse en proceso.

El hilo del parse NO se cancela al expirar (los threads de
`asyncio.to_thread` son ininterrumpibles); el timeout solo acota la espera
del handler y el residuo se declara en la guía (`GUIDE_PARSE_TIMEOUT`)."""


class LocalConvert(Protocol):
    """Costura del composition root para `convert_document` (T9): `convert_local`.

    Un Protocol (patrón `SearchBackend` de `tools/search.py`) pina la firma
    REAL que `_convert_local_seam` construye en `server.py`: mypy strict
    rechaza un wiring que deje de coincidir.
    """

    def __call__(self, path: Path, *, source_uri: str, extension_hint: str | None) -> str:
        """Markdown del documento del vault, con la pista como `extension_hint`."""
        ...


class BytesConvert(Protocol):
    """Costura del composition root para `convert_base64` (T10): `convert_bytes`.

    Firma REAL de `_convert_bytes_seam` (server.py) — idéntico patrón a
    `LocalConvert`.
    """

    def __call__(
        self, data: bytes, *, filename: str | None, extension: str, source_uri: str
    ) -> str:
        """Markdown de los bytes en contexto (`BytesIO` + `StreamInfo`)."""
        ...


def destination_path(output_path: str | None, slug: str, suffix: str) -> str:
    """Destino pedido o `00-resources/<slug><suffix>`; sin auto-renombrado (D37/D66).

    El alternativo ante colisión solo se **propone** en el error de
    `writer.write_atomic`: renombrar solo rompería la idempotencia. El slug y
    el sufijo los calcula cada handler — la identidad de la fuente difiere
    por tool (`path` pedido vs `filename`/`base64-<digest>`).
    """
    candidate = (
        Path(output_path) if output_path is not None else Path(RESOURCES_DIR) / (slug + suffix)
    )
    try:
        suffixed = candidate.with_suffix(suffix)
    except ValueError as exc:
        # `.` / `/` no tienen nombre ⇒ `ValueError`: destino malformado es una
        # entrada mal escrita (VALIDATION_ERROR, D64), no INTERNAL.
        raise paths.VaultPathError(
            f"output_path malformado: {output_path!r} no acepta el sufijo {suffix!r}",
            {"requested": output_path, "suffix": suffix},
        ) from exc
    return str(suffixed)


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
        content = await asyncio.wait_for(run_convert(), timeout=CONVERT_TIMEOUT)
    except formats.UnsupportedFormatError as exc:
        return errors.validation_error(str(exc), {"formats": list(formats.SUPPORTED_FORMATS)})
    except TimeoutError:
        # S4min: guarda de pared — el parse en proceso no se cancela; el
        # residuo (hilo vivo) se declara en la guía.
        return errors.source_unreachable(
            source_uri, "TimeoutError", guide=errors.GUIDE_PARSE_TIMEOUT
        )
    except Exception as exc:  # corrupto, cifrado: no es una entrada mal escrita (D39)
        # W-05: el URI fuga tal cual entraba; en log va REDACTADO (review eje 4)
        # y TRUNCADO (log-forge: un URI kilométrico no infla el stderr).
        redacted = paths.redact_uri(source_uri)[:300]
        logger.exception("%s: fallo de conversión para %s", tool, redacted)
        return errors.source_unreachable(source_uri, type(exc).__name__)
    if not content.strip():
        return errors.source_unreachable(source_uri, "EmptyMarkdown", guide=errors.GUIDE_OCR)
    try:
        written = writer.write_atomic(target, content)
    except paths.VaultPathError as exc:
        return errors.validation_error(str(exc), exc.details)
    return summary.build_summary(written, source_uri=source_uri, vault_root=vault_root)
