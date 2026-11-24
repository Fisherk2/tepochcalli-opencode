"""T7 (D55/D39): el catálogo de formatos es DATO puro — sin `markitdown`.

Fuentes de verdad:

* tasks/todo.md T7 AC (e) — 13 extensiones verificadas y la nota «sin OCR».
* specs/spec-markitdown.md §Catálogo — verificado contra `markitdown==0.1.9` con
  extras `[pdf,docx,pptx,xlsx,xls]`: sin `.doc`/`.ppt` (no hay convertidor
  legacy), sin `.zip`/`.epub`/`.ipynb`/`.xml`/`.jpg`/`.msg` en v1.
* tasks/plan.md §5.5 — el catálogo del wire, en ese orden.

El módulo NO importa `markitdown`: el test de arquitectura prohíbe que el
dominio del server alcance el conversor; el catálogo se ata a una conversión
real en el test de integración (T11).
"""

from __future__ import annotations

import pytest
from tepochcalli_mcp import formats

EXPECTED = (
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".xls",
    ".html",
    ".htm",
    ".csv",
    ".txt",
    ".md",
    ".markdown",
    ".json",
    ".jsonl",
)
"""Los 13 del contrato §5.5, en ese orden (el wire los publica así)."""


def test_catalog_has_the_thirteen_verified_extensions() -> None:
    """Catálogo exacto: ni una extensión de más ni de menos."""
    assert formats.SUPPORTED_FORMATS == EXPECTED
    assert len(formats.SUPPORTED_FORMATS) == 13


@pytest.mark.parametrize("suffix", EXPECTED)
def test_every_catalog_extension_is_supported(suffix: str) -> None:
    """Cada extensión del catálogo se reconoce a sí misma."""
    assert formats.is_supported(suffix)


@pytest.mark.parametrize("suffix", [".doc", ".ppt", ".zip", ".epub", ".msg", ".ipynb", ".jpg"])
def test_extensions_outside_the_catalog_are_rejected(suffix: str) -> None:
    """Lo que markitdown 0.1.9 no convierte (o v1 no admite) queda fuera."""
    assert not formats.is_supported(suffix)


def test_suffix_matching_is_case_insensitive_and_tolerates_a_missing_dot() -> None:
    """El agente escribe `PDF`, `pdf` o `.PDF`: el borde normaliza, el catálogo no crece."""
    assert formats.is_supported("PDF")
    assert formats.is_supported(".PDF")
    assert formats.is_supported("pdf")
    assert not formats.is_supported("")


def test_notes_state_that_there_is_no_ocr() -> None:
    """La nota del wire dice explícitamente que un escaneado no se convierte (H1)."""
    assert "OCR" in formats.NOTES
    assert "escaneado" in formats.NOTES
