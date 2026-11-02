"""Parseo y chunking con cita completa: texto plano directo y documentos con markitdown.

Sirve specs/spec-rag-engine.md §Chunking, §Fuentes y §Ruta de documentos (T3):

* `extract_text` — despacho por extensión: `.md`/`.markdown`/`.txt` se leen
  directamente en UTF-8 estricto (BOM incluido, el MISMO decodificador que la
  ruta de escritura de `app.index_file`); `pdf/docx/pptx/xlsx/xls` se extraen
  con **markitdown en proceso** (D48/D53). En todos los casos el string
  devuelto es el texto de referencia sobre el que se miden los offsets F1:
  **para un binario, `char_start`/`char_end` se refieren al texto extraído,
  nunca al binario** (`offsets_ref="extract"`, D50).
* `chunk_document` — `RecursiveSplitter` con el presupuesto canónico
  **`chunk_size=1536`, `chunk_overlap=192` en BYTES** (F4/D11: el splitter
  mide bytes, no chars) y devuelve registros de chunk que arrastran la cita
  DERIVADA con `citation.py` — `normalize_source_path`, `doc_kind_for`,
  `validate_offsets`, `verify_slice_identity`, `heading_before` y `model_id`
  se REUTILIZAN, no se reimplementan. **D54:** todo documento binario produce
  `heading=None` aunque markitdown emita `#` para un `.docx`; un heading
  inventado sería una cita falsa.

**Anclaje a la fuente instalada (R3):** `markitdown==0.1.9`.
`markitdown/_markitdown.py:322` declara
`MarkItDown.convert(source: str | requests.Response | Path | BinaryIO, *,
stream_info=None, **kwargs) -> DocumentConverterResult`; el texto vive en
`DocumentConverterResult.markdown` (`markitdown/_base_converter.py`). Los
fallos del extractor son subclases de `MarkItDownException`
(`markitdown/_exceptions.py`: `FileConversionException`,
`UnsupportedFormatException`, `MissingDependencyException`).

Como `citation`/`config`, este módulo solo trae primitivas del dominio de cita
más el splitter de cocoindex: la infraestructura del walk vive en `source.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from cocoindex.ops.text import RecursiveSplitter
from cocoindex.resources.chunk import Chunk
from markitdown import MarkItDown, MarkItDownException

from .citation import (
    SOURCE_OFFSETS_DOC_KINDS,
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

SPLITTER: Final = RecursiveSplitter()
"""Instancia única del splitter: estadoless, seguro entre documentos (§Chunking)."""

_SPLITTER_LANGUAGE: Final[dict[DocKind, str]] = {
    "md": "markdown",
    "markdown": "markdown",
    "txt": "plain",
    "pdf": "markdown",
    "docx": "markdown",
    "pptx": "markdown",
    "xlsx": "markdown",
    "xls": "markdown",
}
"""Separadores por `doc_kind` — heading ATX/párrafo/oración/palabra (§Chunking, F4).

Para los binarios, los del markdown: markitdown devuelve texto/markdown (un
`.xlsx` sale como tabla markdown), así que su estructura se parte igual.
"""


class ExtractionError(Exception):
    """markitdown no pudo extraer texto de un documento (T3, D48/OM-11).

    `detail` es la explicación humana que `source.classify_file` copia al
    `SkippedSource` y que el log del refresh muestra; el motivo tipado es
    `source.SkipReason.EXTRACTION_FAILED`. Un documento sin texto JAMÁS se
    indexa como fila vacía: se lanza antes de trocear.
    """

    def __init__(self, detail: str) -> None:
        """`detail` distingue «corrupto/cifrado» de «sin capa de texto»."""
        super().__init__(f"extraction_failed: {detail}")
        self.detail = detail


@dataclass(frozen=True)
class DocumentChunk:
    """Chunk en memoria con su cita completa — el esquema de fila de T6 sin `vector`/`id`."""

    source_path: str
    """Ruta POSIX relativa al vault (no nula, anidamiento intacto; D41)."""

    doc_kind: DocKind
    """`md|markdown|txt|pdf|docx|pptx|xlsx|xls` (no nulo; D43)."""

    heading: str | None
    """Último heading ATX previo en texto plano; `None` sin padre o en binarios (D13/D54)."""

    char_start: int
    """Offset de carácter inicio dentro del texto extraído (no nulo; identidad F1)."""

    char_end: int
    """Offset de carácter fin, exclusivo (no nulo): el slice del documento reproduce `text` (F1)."""

    text: str
    """Contenido exacto del chunk — idéntico al slice que declaran los offsets (F1)."""

    model: str
    """Embedder que va a vectorizar el chunk — detección de índice mixto (ADR-006)."""


def extract_text(file_path: Path) -> str:
    """Extrae el texto de un archivo según su extensión (§Fuentes, §Ruta de documentos).

    `.md`, `.markdown` y `.txt` se leen como UTF-8 sin transformación
    (decodificador estricto, BOM incluido: el MISMO que la ruta de escritura de
    `app.index_file`). El resto (`pdf/docx/pptx/xlsx/xls`) pasa por markitdown
    en proceso. En TODOS los casos el string devuelto es el texto de referencia
    sobre el que `chunk_document` mide los offsets F1 — para un binario esos
    offsets se refieren al **texto extraído**, nunca al binario (D50).

    Un fallo del extractor (corrupto, cifrado, no soportado) o un documento
    **sin capa de texto** (extracción vacía o solo espacios) lanza
    `ExtractionError`; nunca se devuelve el binario crudo y nunca se indexa un
    documento vacío (OM-11). Extensiones fuera de la whitelist las rechaza
    `citation.doc_kind_for`.
    """
    kind = doc_kind_for(file_path)
    if kind in SOURCE_OFFSETS_DOC_KINDS:
        return file_path.read_text(encoding="utf-8")
    return _extract_markdown(file_path)


def _extract_markdown(file_path: Path) -> str:
    """Extrae un documento binario con markitdown y valida que tenga texto.

    Fuente instalada `markitdown==0.1.9`: `MarkItDown().convert(path).markdown`
    (ver docstring del módulo). Los fallos del extractor se traducen a
    `ExtractionError`; un extracto vacío o solo espacios también — es el caso
    típico de un PDF escaneado sin OCR (fuera de alcance v1) y jamás debe
    producir una fila vacía.
    """
    try:
        markdown = MarkItDown().convert(file_path).markdown
    except MarkItDownException as exc:
        raise ExtractionError(f"documento corrupto, cifrado o no soportado: {exc}") from exc
    except OSError as exc:
        raise ExtractionError(f"no se pudo leer el documento: {exc}") from exc
    if not markdown.strip():
        raise ExtractionError(
            "sin capa de texto (posible documento escaneado; OCR no soportado) — "
            "no se indexa un documento vacío"
        )
    return markdown


def chunk_document(
    text: str,
    source_path: str,
    *,
    config: Config | None = None,
) -> list[DocumentChunk]:
    r"""Particiona `text` y devuelve chunks con la cita derivada (§Chunking).

    El presupuesto sale de `config.ChunkingConfig` —default 1536/192 en
    **BYTES** (D11)—, `source_path` se normaliza con el dominio de cita y cada
    chunk valida sus offsets (`validate_offsets`) y su identidad F1
    (`verify_slice_identity`), lanzando `CitationError` si el splitter
    devolviera un rango que no reproduce su propio texto. Texto vacío → `[]`.

    Para un documento binario, `text` es el extracto de markitdown y
    `char_start`/`char_end` se miden sobre ESTE string (nunca sobre el
    binario); su `heading` es siempre `None` (D54), aunque el extracto contenga
    líneas `#`: no se citan headings que markitdown no garantiza.

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
    """Deriva la cita de un `Chunk` del splitter reutilizando el dominio de cita (F1)."""
    char_start, char_end = validate_offsets(text, chunk.start.char_offset, chunk.end.char_offset)
    if not verify_slice_identity(text, char_start, char_end, chunk.text):
        raise CitationError(
            f"Offsets [{char_start}, {char_end}) no reproducen el chunk de {canonical_path} "
            "— identidad F1 rota (ver spec-rag-engine §Chunking)"
        )
    derived_heading = (
        scanner.heading_before(char_start) if kind in SOURCE_OFFSETS_DOC_KINDS else None
    )
    return DocumentChunk(
        source_path=canonical_path,
        doc_kind=kind,
        heading=derived_heading,
        char_start=char_start,
        char_end=char_end,
        text=chunk.text,
        model=model,
    )
