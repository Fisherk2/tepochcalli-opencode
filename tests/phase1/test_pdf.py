"""Tests de la ruta PDF con Docling en CPU (Phase 1, T7) — escritos en rojo antes que la rama.

Fuentes de verdad:

* specs/spec-rag-engine.md §Ruta PDF (Docling, CPU) — `parse_document`
  despacha por extensión: PDF → Docling en modo CPU (sin opts GPU),
  emitiendo markdown con jerarquía de headings conservada (mejora las
  citas); el costo de PDFs grandes queda fuera del presupuesto Δ (TD-2).
* specs/spec-rag-engine.md §Fuentes — >100MB → `skipped` con motivo, sin
  abortar el delta (F5).
* specs/spec-markitdown.md §fallback — Docling y no markitdown para PDF:
  markitdown pierde la estructura de headings que alimenta las citas.
* tasks/todo.md → T7 AC — `doc_kind="pdf"`; `char_start`/`char_end`
  referidos al **markdown extraído**, nunca al binario PDF (documentado);
  fixture PDF real (1 página) con heading no nulo; **retirar
  `SkipReason.PDF_PARSER_PENDING` de `source.classify_file`** (hallazgo
  revisión CP-B #5: sin esto los PDFs seguirían saltándose en silencio
  con solo un warning); decodificador único UTF-8 estricto — un decoder
  distinto rompería M2.

Decisiones de test, documentadas a propósito (convención de T6):

* **Cache de modelos de Docling FUERA del repo.** El layout model de
  Docling (~1GB con sus snapshots) nunca debe aterrizar en
  `obsidian-workspace/.tepochcalli/models/` (payload). El cache estable es
  el del spike T1 `/tmp/opencode/tepochcalli-t1-spike/models` como `HF_HOME`
  (Docling descarga vía `snapshot_download` de huggingface_hub, así que
  `HF_HOME` dirige también sus modelos) más un directorio hermano para
  `DOCLING_CACHE_DIR` (el `cache_dir` propio de Docling, default
  `~/.cache/docling`).
* **M5 sin aserciones de tiempo:** el costo real se mide y se reporta en el
  cierre de Phase 1 (docs/WORKFLOW.md); un assert de timing sería flaky.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from docling.exceptions import ConversionError
from tepochcalli_flow import citation, parsers, source

# Deprecations INTERNAS de Docling al usarse su propia API default: su pipeline
# serializa opciones por hash en cada `convert` (`force_full_page_ocr`) y su
# `_init_models` lee el campo deprecado `generate_table_images` una vez. No son
# de este código ni del flow; se filtran AQUÍ (scope de este módulo) para
# preservar la regla de la suite: exactamente UN warning (TD-9, FutureWarning).
pytestmark = [
    pytest.mark.filterwarnings(
        "ignore:`force_full_page_ocr` is deprecated:DeprecationWarning"
    ),
    pytest.mark.filterwarnings(
        "ignore:This field is deprecated. Use `generate_page_images=True`:DeprecationWarning"
    ),
]

# Cache de modelos estable fuera del repo (ver docstring del módulo). `setdefault`
# deja mandar un `HF_HOME` externo sin romper la hermeticidad del payload.
SPIKE_CACHE = Path("/tmp/opencode/tepochcalli-t1-spike/models")
FALLBACK_CACHE = Path("/tmp/opencode/tepochcalli-t7-models")
DOCLING_CACHE = Path("/tmp/opencode/tepochcalli-t1-spike/docling")
FALLBACK_DOCLING_CACHE = Path("/tmp/opencode/tepochcalli-t7-docling")

os.environ.setdefault(
    "HF_HOME", str(SPIKE_CACHE if SPIKE_CACHE.exists() else FALLBACK_CACHE)
)
os.environ.setdefault(
    "DOCLING_CACHE_DIR",
    str(DOCLING_CACHE if DOCLING_CACHE.exists() else FALLBACK_DOCLING_CACHE),
)

FIXTURE_PDF = Path(__file__).parent / "fixtures" / "pdf" / "articulo_t7.pdf"
"""PDF real de 1 página escrito a mano (sin dependencias de autoría).

Título 20pt + secciones 14pt en Helvetica-Bold: el layout model de Docling
los clasifica como headings y el markdown emitido conserva la jerarquía.
Regenerable con `fixtures/pdf/gen_fixture_pdf.py`.
"""

TITLE = "Tepochcalli Fixture Document"
"""Título del documento — el heading que encabeza el markdown extraído."""

SECTIONS = {"Metodo de prueba", "Resultados", "Implicaciones"}
"""Secciones del fixture — la jerarquía de headings debe sobrevivir al parseo."""


def _skips(items: list[source.WalkItem]) -> list[source.SkippedSource]:
    """Filtra los elementos descartados de un pase de walk."""
    return [item for item in items if isinstance(item, source.SkippedSource)]


def _entries(items: list[source.WalkItem]) -> list[source.SourceEntry]:
    """Filtra los elementos indexables de un pase de walk."""
    return [item for item in items if isinstance(item, source.SourceEntry)]


# --- extract_text: la rama PDF de Docling (§Ruta PDF) ---------------------------


def test_extract_text_converts_a_pdf_to_markdown_with_heading_hierarchy() -> None:
    """El PDF produce markdown con la jerarquía de headings intacta (AC; §Ruta PDF).

    Los headings ATX son lo que `citation.heading_before` citará después
    (spec-markitdown §fallback: Docling y no markitdown por esta estructura).
    """
    markdown = parsers.extract_text(FIXTURE_PDF)

    assert markdown.startswith(f"## {TITLE}\n")
    assert citation.heading_before(markdown, markdown.index("Segundo apartado")) == (
        "Metodo de prueba"
    )
    assert citation.heading_before(
        markdown, markdown.index("Los chunks producidos")
    ) == ("Resultados")
    assert "%PDF" not in markdown  # jamás el binario crudo


def test_extract_text_pdf_is_deterministic_and_strictly_unicode() -> None:
    """Contrato de decodificador único (AC añadido CP-B): mismo string estricto en ambas rutas.

    La ruta md/txt (`read_text(encoding="utf-8")`, errors strict por
    defecto) y la rama Docling deben producir strings con la misma
    semántica: Unicode estricto —sin U+FFFD de `errors="replace"`, sin
    strip de BOM— y deterministas entre corridas, porque los offsets F1 se
    miden sobre ESTE string (un decoder distinto rompería M2).
    """
    first = parsers.extract_text(FIXTURE_PDF)
    second = parsers.extract_text(FIXTURE_PDF)

    assert first == second
    assert "\ufffd" not in first
    assert first.encode("utf-8").decode("utf-8") == first


# --- chunk_document: chunks citados de un PDF -----------------------------------


def test_chunk_document_yields_pdf_chunks_with_non_null_heading_and_f1_identity() -> (
    None
):
    """`doc_kind="pdf"`, `heading` de sección no nulo e identidad F1 sobre el MARKDOWN (AC).

    Los offsets `char_start`/`char_end` se miden sobre el markdown
    extraído por Docling —decisión documentada de T7—, nunca sobre el
    binario PDF: la identidad `markdown[char_start:char_end] == chunk.text`
    debe cumplirse sobre el string que devuelve `extract_text`.
    """
    markdown = parsers.extract_text(FIXTURE_PDF)

    chunks = parsers.chunk_document(markdown, "00-Resources/articulo.pdf")

    assert len(chunks) >= 2  # el fixture supera el presupuesto de 1536 bytes
    for chunk in chunks:
        assert chunk.doc_kind == "pdf"
        assert chunk.source_path == "00-Resources/articulo.pdf"
        assert citation.verify_slice_identity(
            markdown, chunk.char_start, chunk.char_end, chunk.text
        ), f"identidad F1 rota en [{chunk.char_start}, {chunk.char_end})"
        assert chunk.char_end <= len(markdown)  # sobre el markdown, no sobre el binario
    cited = {chunk.heading for chunk in chunks if chunk.heading is not None}
    assert cited & SECTIONS, f"heading de sección no citado en ningún chunk: {cited}"


# --- walk/classify: el skip `pdf_parser_pending` retirado (hallazgo CP-B #5) -----


def test_walk_sources_indexes_a_real_pdf_now_that_docling_landed_t7(
    tmp_path: Path,
) -> None:
    """AC de revisión: un PDF real YA NO se salta en `classify_file`; el pase lo indexa.

    Antes de T7 el walk emitía `skipped(pdf_parser_pending)` y el PDF
    jamás alcanzaba `extract_text`; ahora es una `SourceEntry` como
    cualquier archivo de la whitelist y su ruta vertical completa
    (walk → extract → chunk) produce citas F1 válidas.
    """
    recursos = tmp_path / citation.RESOURCES_DIR
    recursos.mkdir(parents=True)
    shutil.copy(FIXTURE_PDF, recursos / "articulo.pdf")
    (recursos / "notas.md").write_text("# Notas\n\nprosa.\n", encoding="utf-8")

    items = source.walk_sources(tmp_path)

    assert _skips(items) == []
    assert [(entry.source_path, entry.doc_kind) for entry in _entries(items)] == [
        ("00-Resources/articulo.pdf", "pdf"),
        ("00-Resources/notas.md", "md"),
    ]
    assert not hasattr(source.SkipReason, "PDF_PARSER_PENDING")  # motivo retirado


def test_walk_extract_chunk_end_to_end_over_a_real_pdf(tmp_path: Path) -> None:
    """Camino vertical #3: el PDF del walk se parsea, parte y cita sin roturas (CP-C)."""
    recursos = tmp_path / citation.RESOURCES_DIR
    papers = recursos / "sub" / "papers"
    papers.mkdir(parents=True)
    shutil.copy(FIXTURE_PDF, papers / "articulo.pdf")

    entries = _entries(source.walk_sources(tmp_path))
    assert [entry.source_path for entry in entries] == [
        "00-Resources/sub/papers/articulo.pdf"
    ]  # anidamiento libre preservado (D9.1)

    markdown = parsers.extract_text(entries[0].path)
    chunks = parsers.chunk_document(markdown, entries[0].source_path)

    assert chunks
    assert all(chunk.doc_kind == "pdf" for chunk in chunks)
    assert all(
        citation.verify_slice_identity(
            markdown, chunk.char_start, chunk.char_end, chunk.text
        )
        for chunk in chunks
    )


def test_oversized_pdf_is_skipped_with_reason_and_the_pass_completes(
    tmp_path: Path,
) -> None:
    """PDF sobre el umbral → `skipped(oversized)` con motivo y el delta NO se aborta (AC, F5).

    El umbral reutiliza el inyectable `max_file_bytes` de `§Fuentes`
    (DEFAULT_MAX_FILE_BYTES = 100MB); aquí se inyecta por debajo del
    tamaño real del fixture para no generar ficheros de 100MB.
    """
    recursos = tmp_path / citation.RESOURCES_DIR
    recursos.mkdir(parents=True)
    shutil.copy(FIXTURE_PDF, recursos / "grande.pdf")
    (recursos / "sana.md").write_text("# Sana\n\nprosa.\n", encoding="utf-8")

    items = source.walk_sources(tmp_path, max_file_bytes=FIXTURE_PDF.stat().st_size - 1)

    skips = _skips(items)
    assert [(skip.source_path, skip.reason) for skip in skips] == [
        ("00-Resources/grande.pdf", source.SkipReason.OVERSIZED),
    ]
    assert skips[0].detail  # el motivo lleva explicación, no solo el enum
    assert [entry.source_path for entry in _entries(items)] == ["00-Resources/sana.md"]


def test_corrupt_pdf_raises_conversion_error_and_never_raw_binary(
    tmp_path: Path,
) -> None:
    """Un PDF corrupto lanza `ConversionError` de Docling: nunca devuelve el binario como texto.

    Cubre el lado de error de la rama añadida en `extract_text` (T5
    cubría el rechazo previo con `PdfParserPendingError`, hoy retirado).
    """
    corrupto = tmp_path / "corrupto.pdf"
    corrupto.write_bytes(b"%PDF-1.4 fake")

    with pytest.raises(ConversionError):
        parsers.extract_text(corrupto)
