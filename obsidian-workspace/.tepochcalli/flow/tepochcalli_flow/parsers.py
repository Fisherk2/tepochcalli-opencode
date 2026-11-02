"""Parseo y chunking de texto plano con cita completa (Phase 1, T5 + T7).

Sirve specs/spec-rag-engine.md §Chunking, §Fuentes y §Ruta PDF (Docling, CPU):

* `extract_text` — despacho por extensión: `.md`/`.markdown`/`.txt` lectura
  directa UTF-8 estricto (BOM incluido, el MISMO decodificador que la ruta
  de escritura de T6 `app.index_file`), `.pdf` → Docling en modo CPU
  emitiendo markdown con la jerarquía de headings conservada (mejora las
  citas; spec-markitdown §fallback: Docling y no markitdown). En todos los
  casos el string devuelto es el texto de referencia sobre el que se miden
  los offsets F1: **para un PDF `char_start`/`char_end` referidos al
  markdown extraído, nunca al binario** (decisión T7 documentada).
* `chunk_document` — `RecursiveSplitter` con el presupuesto canónico
  **`chunk_size=1536`, `chunk_overlap=192` en BYTES** (F4/D11: el splitter
  mide bytes, no chars) y devuelve registros de chunk que arrastran la cita
  DERIVADA con `citation.py` de T4 — `normalize_source_path`,
  `doc_kind_for`, `validate_offsets`, `verify_slice_identity`,
  `heading_before` y `model_id` se REUTILIZAN, no se reimplementan (AC de T5).
  El markdown que Docling emite para PDFs usa los separadores markdown
  (§Ruta PDF: mismos headings ATX que md).

Como `citation`/`config`, este módulo solo trae primitivas del dominio de cita
más el splitter de cocoindex: la infraestructura del walk vive en `source.py`.
Docling se importa perezosamente en la rama PDF: importar `parsers` para la
ruta md/txt no carga Docling/torch.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Final

from cocoindex.ops.text import RecursiveSplitter
from cocoindex.resources.chunk import Chunk

from .citation import (
    CitationError,
    DocKind,
    HeadingScanner,
    doc_kind_for,
    model_id,
    normalize_source_path,
    validate_offsets,
    verify_slice_identity,
)
from .config import ChunkingConfig, Config

if TYPE_CHECKING:
    from docling.document_converter import DocumentConverter

SPLITTER: Final = RecursiveSplitter()
"""Instancia única del splitter: estadoless, seguro entre documentos (§Chunking)."""

_SPLITTER_LANGUAGE: Final[dict[DocKind, str]] = {
    "md": "markdown",
    "markdown": "markdown",
    "txt": "plain",
    "pdf": "markdown",
}
"""Separadores por `doc_kind` — heading ATX/párrafo/oración/palabra (§Chunking, F4).

Para `pdf`, los del markdown: Docling EMITE markdown con jerarquía de
headings (§Ruta PDF), así que su estructura se parte como cualquier `.md`.
"""


@dataclass(frozen=True)
class DocumentChunk:
    """Chunk en memoria con su cita completa — el esquema de fila de T6 sin `vector`/`id`."""

    source_path: str
    """Ruta POSIX relativa al vault (no nula, anidamiento intacto; D41)."""

    doc_kind: DocKind
    """`md|markdown|txt|pdf` (no nulo) — para PDF, `doc_kind_for` de T4 (§Chunking)."""

    heading: str | None
    """Último heading ATX previo al offset; `None` sin padre (nullable, D13)."""

    char_start: int
    """Offset de carácter inicio dentro del texto extraído (no nulo; identidad F1)."""

    char_end: int
    """Offset de carácter fin, exclusivo (no nulo): el slice del documento reproduce `text` (F1)."""

    text: str
    """Contenido exacto del chunk — idéntico al slice que declaran los offsets (F1)."""

    model: str
    """Embedder que va a vectorizar el chunk — detección de índice mixto (ADR-006)."""


def extract_text(file_path: Path) -> str:
    """Extrae el texto de un archivo según su extensión (§Fuentes, §Ruta PDF).

    `.md`, `.markdown` y `.txt` se leen como UTF-8 sin transformación
    (decodificador estricto, BOM incluido: el MISMO que la ruta de
    escritura de T6, `app.index_file`); `.pdf` pasa por Docling en modo CPU
    y devuelve su markdown con la jerarquía de headings intacta. En TODOS
    los casos el string devuelto es el texto de referencia sobre el que
    `chunk_document` mide los offsets F1 — para un PDF esos offsets se
    refieren al **markdown extraído**, nunca al binario del PDF (decisión
    T7 documentada; el binario jamás se lee como texto). Un PDF corrupto
    propaga `docling.exceptions.ConversionError`, nunca devuelve bytes
    crudos. Extensiones fuera de la whitelist las rechaza
    `citation.doc_kind_for`.
    """
    kind = doc_kind_for(file_path)
    if kind == "pdf":
        return _extract_pdf_markdown(file_path)
    return file_path.read_text(encoding="utf-8")


@cache
def _pdf_converter() -> DocumentConverter:
    """Devuelve el converter Docling único del proceso, en CPU sin opts GPU (§Ruta PDF).

    Pérezoso y cacheado por proceso: importar `parsers` para la ruta md/txt
    no carga Docling/torch, e inicializar el pipeline (carga del layout
    model, ~1GB de residentes) cuesta segundos — reutilizarlo es lo que
    hace soportable el costo de un delta con varios PDFs (TD-2; el costo
    real se mide en M5, nunca se estima).
    """
    from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions(
        accelerator_options=AcceleratorOptions(device=AcceleratorDevice.CPU),
        do_ocr=False,  # OCR completo fuera de scope v1 (spec-rag-engine §Alcance)
    )
    return DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)},
    )


def _extract_pdf_markdown(file_path: Path) -> str:
    """Convierte un PDF a markdown con Docling CPU y devuelve ese markdown (§Ruta PDF).

    La jerarquía de headings ATX que Docling emite es la que después cita
    `citation.heading_before` (spec-markitdown §fallback: por eso Docling y
    no markitdown para PDFs). El string devuelto ES el texto de referencia
    de los offsets F1: `char_start`/`char_end` citan este markdown, jamás
    el binario del PDF (decisión T7).
    """
    result = _pdf_converter().convert(file_path)
    return result.document.export_to_markdown()


def chunk_document(
    text: str,
    source_path: str,
    *,
    config: Config | None = None,
) -> list[DocumentChunk]:
    r"""Particiona `text` y devuelve chunks con la cita derivada (§Chunking, AC de T5).

    El presupuesto sale de `config.ChunkingConfig` —default 1536/192 en
    **BYTES** (D11)—, `source_path` se normaliza con el dominio de T4 y cada
    chunk valida sus offsets (`validate_offsets`) y su identidad F1
    (`verify_slice_identity`), lanzando `CitationError` si el splitter
    devolviera un rango que no reproduce su propio texto. Texto vacío → `[]`.

    `text` puede ser markdown crudo o el markdown extraído de un PDF por
    `extract_text` (doc_kind `pdf`, mismos separadores): en ambos casos
    `char_start`/`char_end` se miden sobre ESTE string — para un PDF, sobre
    el markdown extraído, nunca sobre el binario (decisión T7, §Ruta PDF).

    Ejemplo:
        >>> texto = "# Título\n\nprosa."
        >>> chunks = chunk_document(texto, "sub/nota.md")
        >>> chunks[0].source_path, chunks[0].doc_kind
        ('sub/nota.md', 'md')
    """
    if not text:
        return []
    kind = doc_kind_for(source_path)
    chunking = ChunkingConfig() if config is None else config.chunking
    canonical_path = normalize_source_path(source_path)
    chunks = SPLITTER.split(
        text,
        chunk_size=chunking.max_chunk_size,
        chunk_overlap=chunking.overlap,
        language=_SPLITTER_LANGUAGE[kind],
    )
    scanner = HeadingScanner(text)  # cursor compartido: los chunks llegan en orden
    return [
        _to_document_chunk(text, chunk, canonical_path, kind, model_id(config), scanner)
        for chunk in chunks
    ]


def _to_document_chunk(
    text: str,
    chunk: Chunk,
    canonical_path: str,
    kind: DocKind,
    model: str,
    scanner: HeadingScanner,
) -> DocumentChunk:
    """Deriva la cita de un `Chunk` del splitter reutilizando el dominio de T4 (F1)."""
    char_start, char_end = validate_offsets(text, chunk.start.char_offset, chunk.end.char_offset)
    if not verify_slice_identity(text, char_start, char_end, chunk.text):
        raise CitationError(
            f"Offsets [{char_start}, {char_end}) no reproducen el chunk de {canonical_path} "
            "— identidad F1 rota (ver spec-rag-engine §Chunking)"
        )
    return DocumentChunk(
        source_path=canonical_path,
        doc_kind=kind,
        heading=scanner.heading_before(char_start),
        char_start=char_start,
        char_end=char_end,
        text=chunk.text,
        model=model,
    )
