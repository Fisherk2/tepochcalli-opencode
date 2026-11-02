"""T3: extracción con markitdown y skips tipados (D48/D54/OM-11).

Fuentes de verdad: `specs/spec-rag-engine.md` §Ruta de documentos (un fallo del
extractor no aborta el pase; un documento sin texto nunca produce una fila
vacía) y `specs/adr/adr-011-*.md` §4.3.

Sin dependencias nuevas: el PDF en blanco es un PDF mínimo sintético y el
corrupto son bytes no decodificables por ningún convertidor de markitdown.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from tepochcalli_flow import citation, parsers, source

BLANK_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
    b"xref\n"
    b"0 4\n"
    b"0000000000 65535 f\x20\n"
    b"0000000009 00000 n\x20\n"
    b"0000000052 00000 n\x20\n"
    b"0000000101 00000 n\x20\n"
    b"trailer<</Size 4/Root 1 0 R>>\n"
    b"startxref\n"
    b"160\n"
    b"%%EOF\n"
)
"""PDF sintético con una página SIN capa de texto (markitdown devuelve '')."""

CORRUPT_BYTES = bytes(range(256)) * 4
"""Binario que ningún convertidor de markitdown puede decodificar."""


def _entries(items: list[source.WalkItem]) -> list[source.SourceEntry]:
    """Filtra las entradas indexables del pase."""
    return [item for item in items if isinstance(item, source.SourceEntry)]


def _skips(items: list[source.WalkItem]) -> list[source.SkippedSource]:
    """Filtra los descartes con motivo del pase."""
    return [item for item in items if isinstance(item, source.SkippedSource)]


def test_extract_text_rejects_a_document_without_text_layer(tmp_path: Path) -> None:
    """OM-11: un PDF sin texto lanza `ExtractionError` (nunca se indexa vacío)."""
    blank = tmp_path / "escaneado.pdf"
    blank.write_bytes(BLANK_PDF)

    with pytest.raises(parsers.ExtractionError, match="sin capa de texto"):
        parsers.extract_text(blank)


def test_extract_text_reports_a_corrupt_document_as_extraction_error(tmp_path: Path) -> None:
    """Un binario que markitdown no puede decodificar lanza el error tipado."""
    corrupto = tmp_path / "corrupto.pdf"
    corrupto.write_bytes(CORRUPT_BYTES)

    with pytest.raises(parsers.ExtractionError, match="corrupto"):
        parsers.extract_text(corrupto)


def test_walk_sources_skips_extraction_failures_with_the_typed_reason(tmp_path: Path) -> None:
    """El pase emite `SkippedSource(EXTRACTION_FAILED)` y el resto sigue indexándose."""
    vault = tmp_path / "vault"
    recursos = vault / citation.RESOURCES_DIR
    recursos.mkdir(parents=True)
    (recursos / "sana.md").write_text("# Sana\n\nprosa.\n", encoding="utf-8")
    (recursos / "escaneado.pdf").write_bytes(BLANK_PDF)
    (recursos / "corrupto.pdf").write_bytes(CORRUPT_BYTES)

    items = source.walk_sources(vault)

    assert [entry.source_path for entry in _entries(items)] == ["00-Resources/sana.md"]
    skips = {skip.source_path: skip for skip in _skips(items)}
    assert set(skips) == {"00-Resources/corrupto.pdf", "00-Resources/escaneado.pdf"}
    assert all(skip.reason is source.SkipReason.EXTRACTION_FAILED for skip in skips.values())
    assert "sin capa de texto" in skips["00-Resources/escaneado.pdf"].detail
    assert "corrupto" in skips["00-Resources/corrupto.pdf"].detail


def test_scan_items_does_not_extract_unless_probing_is_requested(tmp_path: Path) -> None:
    """El engine camina sin extraer (la extracción vive en `index_file`): sin doble parse."""
    vault = tmp_path / "vault"
    recursos = vault / citation.RESOURCES_DIR
    recursos.mkdir(parents=True)
    (recursos / "corrupto.pdf").write_bytes(CORRUPT_BYTES)

    items, scanned = asyncio.run(source.scan_items(vault))

    assert scanned == 1
    assert [entry.source_path for entry in _entries(items)] == ["00-Resources/corrupto.pdf"]


def test_classify_file_only_probes_extraction_when_asked(tmp_path: Path) -> None:
    """`probe_extraction=True` clasifica el fallo; por defecto no toca el contenido."""
    vault = tmp_path / "vault"
    recursos = vault / citation.RESOURCES_DIR
    recursos.mkdir(parents=True)
    blank = recursos / "escaneado.pdf"
    blank.write_bytes(BLANK_PDF)

    sin_probe = source.classify_file(vault, blank, max_file_bytes=source.DEFAULT_MAX_FILE_BYTES)
    con_probe = source.classify_file(
        vault, blank, max_file_bytes=source.DEFAULT_MAX_FILE_BYTES, probe_extraction=True
    )

    assert isinstance(sin_probe, source.SourceEntry)
    assert isinstance(con_probe, source.SkippedSource)
    assert con_probe.reason is source.SkipReason.EXTRACTION_FAILED
