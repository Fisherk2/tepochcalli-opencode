"""Parseo y chunking de texto plano con cita completa (Phase 1, T5).

Sirve specs/spec-rag-engine.md §Chunking y §Fuentes:

* `extract_text` — lectura directa de `.md`/`.markdown`/`.txt`; la rama PDF
  (Docling, CPU) llega en T7 y aquí se rechaza con error tipado
  (`PdfParserPendingError`), nunca con una lectura cruda del binario.
* `chunk_document` — `RecursiveSplitter` con el presupuesto canónico
  **`chunk_size=1536`, `chunk_overlap=192` en BYTES** (F4/D11: el splitter
  mide bytes, no chars) y devuelve registros de chunk que arrastran la cita
  DERIVADA con `citation.py` de T4 — `normalize_source_path`,
  `doc_kind_for`, `validate_offsets`, `verify_slice_identity`,
  `heading_before` y `model_id` se REUTILIZAN, no se reimplementan (AC de T5).

Como `citation`/`config`, este módulo solo trae primitivas del dominio de cita
más el splitter de cocoindex: la infraestructura del walk vive en `source.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from cocoindex.ops.text import RecursiveSplitter
from cocoindex.resources.chunk import Chunk

from .citation import (
    CitationError,
    DocKind,
    doc_kind_for,
    heading_before,
    model_id,
    normalize_source_path,
    validate_offsets,
    verify_slice_identity,
)
from .config import ChunkingConfig, Config

SPLITTER: Final = RecursiveSplitter()
"""Instancia única del splitter: estadoless, seguro entre documentos (§Chunking)."""

_SPLITTER_LANGUAGE: Final[dict[DocKind, str]] = {
    "md": "markdown",
    "markdown": "markdown",
    "txt": "plain",
}
"""Separadores por `doc_kind` — heading ATX/párrafo/oración/palabra (§Chunking, F4)."""


class PdfParserPendingError(RuntimeError):
    """PDF alcanzó el parseo de texto plano; Docling llega en T7 (spec §Ruta PDF)."""


@dataclass(frozen=True)
class DocumentChunk:
    """Chunk en memoria con su cita completa — el esquema de fila de T6 sin `vector`/`id`."""

    source_path: str
    """Ruta POSIX canónica `00-Resources/...` (no nula, anidamiento intacto; D9.1)."""

    doc_kind: DocKind
    """`md|markdown|txt` (no nulo) — `pdf` jamás llega hasta aquí en T5 (§Chunking)."""

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
    """Extrae el texto crudo de un archivo con parseo directo en T5 (§Fuentes).

    `.md`, `.markdown` y `.txt` se leen como UTF-8 sin transformación — los
    offsets que después cite `chunk_document` se miden sobre ESTE string.
    `.pdf` lanza `PdfParserPendingError` (T7 añade la rama Docling);
    extensiones fuera de la whitelist los rechaza `citation.doc_kind_for`.
    """
    kind = doc_kind_for(file_path)
    if kind == "pdf":
        raise PdfParserPendingError(
            f"PDF {file_path} sin parser: la rama Docling llega en T7 (spec-rag-engine §Ruta PDF)"
        )
    return file_path.read_text(encoding="utf-8")


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

    Ejemplo:
        >>> texto = "# Título\n\nprosa."
        >>> chunks = chunk_document(texto, "sub/nota.md")
        >>> chunks[0].source_path, chunks[0].doc_kind
        ('00-Resources/sub/nota.md', 'md')
    """
    if not text:
        return []
    kind = doc_kind_for(source_path)
    if kind == "pdf":
        raise PdfParserPendingError(
            f"chunk_document no parsea PDF ({source_path}): rama Docling en T7 (§Ruta PDF)"
        )
    chunking = ChunkingConfig() if config is None else config.chunking
    canonical_path = normalize_source_path(source_path)
    chunks = SPLITTER.split(
        text,
        chunk_size=chunking.max_chunk_size,
        chunk_overlap=chunking.overlap,
        language=_SPLITTER_LANGUAGE[kind],
    )
    return [
        _to_document_chunk(text, chunk, canonical_path, kind, model_id(config)) for chunk in chunks
    ]


def _to_document_chunk(
    text: str,
    chunk: Chunk,
    canonical_path: str,
    kind: DocKind,
    model: str,
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
        heading=heading_before(text, char_start),
        char_start=char_start,
        char_end=char_end,
        text=chunk.text,
        model=model,
    )
