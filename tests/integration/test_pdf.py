"""Ruta de documentos con markitdown (T3): PDF sin headings y citas sobre el extracto.

Fuentes de verdad:

* specs/spec-rag-engine.md §Ruta de documentos — `markitdown==0.1.9` extrae el
  texto de `pdf/docx/pptx/xlsx/xls`; los offsets citan el texto EXTRAÍDO
  (`offsets_ref="extract"`), nunca el binario.
* specs/adr/adr-011-politica-dependencias-dos-librerias.md §4.3 (D53/D54):
  Docling fuera y **el PDF pierde la jerarquía de headings** ⇒ `heading` nulo.
* tasks/todo.md → T3 AC (d): el PDF produce `heading is None`; no se disimula
  con el título del fichero.
* tasks/todo.md → T3 AC (e): un extractor que falla no aborta el pase; el
  documento sin capa de texto queda fuera sin producir una fila vacía.

El fixture PDF se escribe a mano (`tests/fixtures/pdf/articulo_t7.pdf`); su
texto conserva las palabras «Docling» de la época en que se generó, pero el
extractor bajo prueba es markitdown. No hay aserciones de tiempo (regla
anti-flake: la medición vive en `tests/benchmarks/`).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from tepochcalli_flow import citation, parsers, source

FIXTURE_PDF = Path(__file__).parents[1] / "fixtures" / "pdf" / "articulo_t7.pdf"
"""PDF real de 1 página (título + secciones en texto plano)."""

TITLE = "Tepochcalli Fixture Document"
"""Título del documento — texto presente en el extracto de markitdown."""

SECTIONS = {"Metodo de prueba", "Resultados", "Implicaciones"}
"""Secciones del fixture — presentes como texto, SIN jerarquía de headings (D54)."""

CORRUPT_BYTES = bytes(range(256)) * 4
"""Binario que ningún convertidor de markitdown puede decodificar."""


def _skips(items: list[source.WalkItem]) -> list[source.SkippedSource]:
    """Filtra los elementos descartados de un pase de walk."""
    return [item for item in items if isinstance(item, source.SkippedSource)]


def _entries(items: list[source.WalkItem]) -> list[source.SourceEntry]:
    """Filtra los elementos indexables de un pase de walk."""
    return [item for item in items if isinstance(item, source.SourceEntry)]


# --- extract_text: markitdown sin jerarquía ------------------------------------


def test_extract_text_reads_a_pdf_with_markitdown_and_without_headings() -> None:
    """El PDF se extrae como texto plano: título/secciones presentes, cero ATX (D54)."""
    markdown = parsers.extract_text(FIXTURE_PDF)

    assert TITLE in markdown
    assert SECTIONS <= set(markdown.splitlines())
    assert not any(line.lstrip().startswith("#") for line in markdown.splitlines()), (
        "markitdown no emite jerarquía de headings para el PDF (D54)"
    )
    assert "%PDF" not in markdown  # jamás el binario crudo


def test_extract_text_pdf_is_deterministic_and_strictly_unicode() -> None:
    """Mismo string en dos corridas, sin U+FFFD (los offsets F1 se miden sobre él)."""
    first = parsers.extract_text(FIXTURE_PDF)
    second = parsers.extract_text(FIXTURE_PDF)

    assert first == second
    assert "\ufffd" not in first
    assert first.encode("utf-8").decode("utf-8") == first


# --- chunk_document: chunks citados de un PDF -----------------------------------


def test_chunk_document_yields_pdf_chunks_with_null_heading_and_f1_identity() -> None:
    """`doc_kind="pdf"`, `heading is None` (D54) e identidad F1 sobre el extracto."""
    markdown = parsers.extract_text(FIXTURE_PDF)

    chunks = parsers.chunk_document(markdown, "00-resources/articulo.pdf")

    assert len(chunks) >= 2  # el fixture supera el presupuesto de 1536 bytes
    for chunk in chunks:
        assert chunk.doc_kind == "pdf"
        assert chunk.source_path == "00-resources/articulo.pdf"
        assert chunk.heading is None, "D54: el PDF pierde la jerarquía de headings"
        assert citation.verify_slice_identity(
            markdown, chunk.char_start, chunk.char_end, chunk.text
        ), f"identidad F1 rota en [{chunk.char_start}, {chunk.char_end})"
        assert chunk.char_end <= len(markdown)  # sobre el extracto, no sobre el binario


# --- walk/classify: el PDF es un indexable más --------------------------------


def test_walk_sources_indexes_a_real_pdf(tmp_path: Path) -> None:
    """Un PDF real es una `SourceEntry` como cualquier archivo de la whitelist."""
    recursos = tmp_path / citation.RESOURCES_DIR
    recursos.mkdir(parents=True)
    shutil.copy(FIXTURE_PDF, recursos / "articulo.pdf")
    (recursos / "notas.md").write_text("# Notas\n\nprosa.\n", encoding="utf-8")

    items = source.walk_sources(tmp_path)

    assert _skips(items) == []
    assert [(entry.source_path, entry.doc_kind) for entry in _entries(items)] == [
        ("00-resources/articulo.pdf", "pdf"),
        ("00-resources/notas.md", "md"),
    ]


def test_walk_extract_chunk_end_to_end_over_a_real_pdf(tmp_path: Path) -> None:
    """Camino vertical #3: el PDF del walk se extrae, parte y cita sin roturas."""
    recursos = tmp_path / citation.RESOURCES_DIR
    papers = recursos / "sub" / "papers"
    papers.mkdir(parents=True)
    shutil.copy(FIXTURE_PDF, papers / "articulo.pdf")

    entries = _entries(source.walk_sources(tmp_path))
    assert [entry.source_path for entry in entries] == [
        "00-resources/sub/papers/articulo.pdf"
    ]  # anidamiento libre preservado (D9.1)

    markdown = parsers.extract_text(entries[0].path)
    chunks = parsers.chunk_document(markdown, entries[0].source_path)

    assert chunks
    assert all(chunk.doc_kind == "pdf" for chunk in chunks)
    assert all(chunk.heading is None for chunk in chunks)
    assert all(
        citation.verify_slice_identity(markdown, chunk.char_start, chunk.char_end, chunk.text)
        for chunk in chunks
    )


def test_oversized_pdf_is_skipped_with_reason_and_the_pass_completes(
    tmp_path: Path,
) -> None:
    """PDF sobre el umbral → `skipped(oversized)` con motivo y el delta NO se aborta (F5)."""
    recursos = tmp_path / citation.RESOURCES_DIR
    recursos.mkdir(parents=True)
    shutil.copy(FIXTURE_PDF, recursos / "grande.pdf")
    (recursos / "sana.md").write_text("# Sana\n\nprosa.\n", encoding="utf-8")

    items = source.walk_sources(tmp_path, max_file_bytes=FIXTURE_PDF.stat().st_size - 1)

    skips = _skips(items)
    assert [(skip.source_path, skip.reason) for skip in skips] == [
        ("00-resources/grande.pdf", source.SkipReason.OVERSIZED),
    ]
    assert skips[0].detail  # el motivo lleva explicación, no solo el enum
    assert [entry.source_path for entry in _entries(items)] == ["00-resources/sana.md"]


def test_corrupt_document_is_reported_as_extraction_failed_and_never_raw_binary(
    tmp_path: Path,
) -> None:
    """Un binario corrupto lanza `ExtractionError`: nunca se devuelve el binario como texto."""
    corrupto = tmp_path / "corrupto.pdf"
    corrupto.write_bytes(CORRUPT_BYTES)

    with pytest.raises(parsers.ExtractionError, match="corrupto"):
        parsers.extract_text(corrupto)
