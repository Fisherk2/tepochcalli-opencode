"""Traza de progreso del refresh: qué documento se extrae y cuánto tarda (TD-2 opción B).

El contrato MCP **no cambia** (ADR-005, `spec-mcp-server` §`index_refresh`): la
respuesta sigue siendo el resumen de 6 claves. Lo que cambia es que el refresh
deja de ser una caja opaca: un libro de 335 páginas tarda 50,6 s solo en
extraerse (108,5 s con indexación) según `docs/diagnosis/phase6-documents.md`
§6, y quien llama veía silencio.

Todo sale por `logging`, que `python -m tepochcalli_mcp` configura a
**stderr** (`__main__.main`). stdout es el canal del JSON-RPC del MCP: una sola
línea de log ahí corrompe el protocolo — por eso este módulo no imprime nada.

Los `.md`/`.txt` NO se trazan uno a uno: se leen en microsegundos y un vault de
10 000 notas produciría 10 000 líneas de ruido. Solo los binarios (markitdown)
tienen coste de segundos, y esos son justo los que el usuario necesita ver.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:  # solo anotación: este módulo no debe importar el motor en runtime
    from .models import RefreshReport

logger = logging.getLogger(__name__)

BINARY_DOC_KINDS: Final = frozenset({"pdf", "docx", "pptx", "xlsx", "xls"})
"""Extensiones extraídas con markitdown — las únicas con coste de segundos."""


def is_binary(document: str) -> bool:
    """Indica si el documento pasa por markitdown y merece una línea de traza.

    `document` es la ruta relativa al vault; decide la extensión, no el contenido.

    Ejemplo:
        >>> is_binary("libros/ejemplo.pdf"), is_binary("nota.md")
        (True, False)
    """
    return document.rsplit(".", 1)[-1].lower() in BINARY_DOC_KINDS


def extraction_started(document: str) -> None:
    """Anuncia el binario que se empieza a extraer: la línea que rompe el silencio."""
    if is_binary(document):
        logger.info("documento %s: extrayendo", document)


def extraction_finished(document: str, elapsed_ms: int) -> None:
    """Cierra la traza del binario con el tiempo REAL de extracción, no una estimación."""
    if is_binary(document):
        logger.info("documento %s: extraído en %d ms", document, elapsed_ms)


def refresh_started(roots: Sequence[str]) -> None:
    """Abre la traza del ciclo Δ nombrando las raíces que se van a recorrer."""
    logger.info("refresh: inicio (raíces: %s)", ", ".join(roots))


def refresh_locked() -> None:
    """Candado retenido por otro proceso: no hay update, y la traza no finge progreso."""
    logger.info("refresh: candado retenido por otro proceso — sin update")


def refresh_finished(report: RefreshReport) -> None:
    """Cierra la traza con las MISMAS cuentas del reporte (el JSON de stdout no se toca)."""
    logger.info(
        "refresh: fin scanned=%d indexed=%d skipped=%d elapsed_ms=%d",
        report.scanned,
        report.indexed,
        report.skipped,
        report.elapsed_ms,
    )
