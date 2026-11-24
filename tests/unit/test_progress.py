"""Traza de progreso: solo los binarios se trazan (TD-2 opción B).

La regla que se pina aquí es la de NO ruido: un vault de 10 000 notas no puede
producir 10 000 líneas de log. El resto del comportamiento (una línea por PDF
en stderr, JSON intacto, stdout limpio) se demuestra end-to-end en
`tests/integration/test_mcp_refresh_progress.py`.
"""

from __future__ import annotations

import logging

import pytest
from tepochcalli_flow import progress


def test_is_binary_covers_exactly_the_markitdown_formats() -> None:
    """Las 5 extensiones de markitdown son binarias; el resto, no."""
    assert all(
        progress.is_binary(f"libros/x.{kind}") for kind in ("pdf", "docx", "pptx", "xlsx", "xls")
    )
    assert not progress.is_binary("nota.md")
    assert not progress.is_binary("sub/datos.txt")
    assert not progress.is_binary("carpeta/sin-extension")


def test_extension_match_ignores_case() -> None:
    """`EJEMPLO.PDF` es el mismo documento que `ejemplo.pdf`."""
    assert progress.is_binary("LIBRO.PDF")


def test_markdown_documents_emit_no_trace(caplog: pytest.LogCaptureFixture) -> None:
    """Ni al empezar ni al terminar: los `.md` no generan línea."""
    with caplog.at_level(logging.INFO, logger=progress.__name__):
        progress.extraction_started("nota.md")
        progress.extraction_finished("nota.md", 3)
    assert caplog.records == []
