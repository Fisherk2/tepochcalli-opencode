"""Dominio de cita: derivación pura de metadatos por chunk (Phase 1, T4).

Implementa el criterio de usuario 5 («citas precisas») y la fila que Phase 2
congela en el contrato `search`:

* specs/spec-rag-engine.md §Chunking — por chunk se derivan `source_path`,
  `heading`, `char_start`/`char_end`, `doc_kind` y `model`; F1: la cita se toma
  de los offsets de carácter y se cumple exactamente
  `text[char_start:char_end] == chunk.text` (verificado 51/51 en el spike T1).
* specs/spec-mcp-server.md §search — forma congelada del resultado
  `{text, source_path, heading, char_start, char_end, score}`.

Código de dominio (hexagonal: la dependencia apunta hacia dentro): sin I/O, sin
red, sin modelos y sin infraestructura del motor de indexación ni del indexador
vectorial — solo primitivas (`str`, `int`, `Path`) y `config` (test de
arquitectura, T9). Los adaptadores de T5/T6 pasan los offsets como enteros
planos (`chunk.start.char_offset`, `chunk.end.char_offset`).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Final, Literal

from .config import DEFAULT_EMBEDDING_MODEL, Config

type DocKind = Literal["md", "markdown", "txt", "pdf"]
"""Conjunto cerrado de `doc_kind` (spec-rag-engine.md §Chunking; T4 AC)."""

RESOURCES_DIR: Final = "00-Resources"
"""Única raíz indexable del vault (spec-vault-structure.md, D9.1)."""

_FRONTMATTER_DELIMITER: Final = "---"
_ATX_HEADING: Final = re.compile(r"^ {0,3}#{1,6}[ \t]+(\S.*?)[ \t]*$")
_ATX_CLOSING: Final = re.compile(r"[ \t]+#+[ \t]*$")
_FENCE_OPEN: Final = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_FENCE_CLOSE: Final = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*$")
_BACKTICK_RUN: Final = re.compile("`+")

_BOM: Final = "\ufeff"
"""BOM UTF-8 como carácter (la lectura estricta lo conserva): se ignora en la línea 0."""

_LINE_SEPARATORS: Final = "\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029"
"""Separadores de `str.splitlines()` (CPython): el mismo conjunto, sin derivar semántica."""

_DOC_KIND_BY_SUFFIX: Final[dict[str, DocKind]] = {
    "md": "md",
    "markdown": "markdown",
    "txt": "txt",
    "pdf": "pdf",
}


class CitationError(ValueError):
    """Error de dominio de la cita: offsets o path inválidos (criterio 5, T4)."""


class UnsupportedDocKindError(CitationError):
    """Extensión fuera del conjunto soportado {md, markdown, txt, pdf} (§Chunking)."""


def normalize_source_path(path: str | Path) -> str:
    """Normaliza `path` a POSIX relativo al vault con prefijo `00-Resources/` (D9.1).

    Conserva exactamente el anidamiento libre del usuario —ese anidamiento ES la
    procedencia de la cita (spec-mcp-server.md §search)— y garantiza la forma
    canónica: sin `./`, sin segmentos `..` (se resuelven dentro del recurso; los
    `..` sobrantes a la izquierda se descartan), barras hacia delante y sin
    separadores duplicados. Un path que apunta a la raíz del recurso (vacío,
    `.` o `00-Resources/`) LANZA `CitationError`: no es una cita.
    """
    raw = os.fspath(path).replace("\\", "/")
    resolved: list[str] = []
    for segment in raw.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if resolved:
                # `..` se resuelve dentro del recurso; sin segmento que poppear se descarta.
                resolved.pop()
            continue
        resolved.append(segment)
    if resolved and resolved[0] == RESOURCES_DIR:
        resolved = resolved[1:]
    if not resolved:
        raise CitationError(
            f"source_path apunta fuera de {RESOURCES_DIR}/: {raw!r} — se exige un "
            "archivo dentro del recurso"
        )
    return f"{RESOURCES_DIR}/" + "/".join(resolved)


class _HeadingState:
    """Estado del escaneo de headings: frontmatter, fence, span y último título."""

    __slots__ = ("heading", "fence", "in_frontmatter", "open_backticks")

    def __init__(self) -> None:
        self.heading: str | None = None
        self.fence: str | None = None
        self.in_frontmatter = False
        self.open_backticks = 0

    def copy(self) -> _HeadingState:
        """Copia independiente — la línea parcial de una consulta NO se persiste."""
        clone = _HeadingState()
        clone.heading = self.heading
        clone.fence = self.fence
        clone.in_frontmatter = self.in_frontmatter
        clone.open_backticks = self.open_backticks
        return clone

    def fold(self, line: str, index: int) -> None:
        """Pliega una línea sobre el estado, con la semántica del barrido naive (F1, T4).

        `line` puede traer o no su separador final (a `str.splitlines()` le da
        igual) y `index` es su posición documental —el índice que el barrido
        naive obtenía con `enumerate`—, necesario para las reglas de la línea 0.
        """
        line = line.rstrip(_LINE_SEPARATORS)
        if index == 0:
            line = line.removeprefix(_BOM)
        if self.in_frontmatter:
            self.in_frontmatter = line.strip() != _FRONTMATTER_DELIMITER
            return
        if index == 0 and line.strip() == _FRONTMATTER_DELIMITER:
            self.in_frontmatter = True
            return
        if self.fence is not None:
            if _closes_fence(line, self.fence):
                self.fence = None
            return
        opened_fence = _FENCE_OPEN.match(line)
        if opened_fence is not None:
            self.fence = opened_fence.group(1)
            self.open_backticks = 0  # el bloque mató el párrafo: el span sin cerrar queda literal.
            return
        if self.open_backticks == 0 and (atx := _ATX_HEADING.match(line)) is not None:
            self.heading = _clean_heading_title(atx.group(1))
            return
        self.open_backticks = _update_code_span(line, self.open_backticks)


class HeadingScanner:
    """Cursor incremental sobre las líneas de un documento para citar headings (F1, T4).

    Semántica EXACTAMENTE equivalente al barrido naive del prefijo
    (`text[:char_start].splitlines()`) —los tests de borde de T4 la pinan y un
    test diferencial la afirma offset a offset sobre separadores difíciles—,
    pero sin re-escanear el documento por chunk: `chunk_document` reparte UN
    scanner entre los chunks de un archivo —que llegan en orden— y solo avanza
    sobre líneas nuevas. Con `max_file_bytes = 100MB` (F5), re-escanear el
    prefijo por chunk sería un auto-DoS contra el presupuesto Δ<30s.

    Semántica del escaneo (idéntica al barrido naive, en este orden):

    * ATX `#`..`######` con título no vacío (CommonMark: hasta 3 espacios de
      sangría, espacio tras los hashes, secuencia de cierre `# Title #` fuera).
    * Los bloques cercados ``` / ~~~ (con info string incluido) no cuentan.
    * Los spans de código inline multi-línea (backticks) no cuentan.
    * El frontmatter YAML se salta: delimitadores `---` y comentarios `#` no
      son headings. El BOM (`\ufeff`) de la línea 0 se ignora antes de estas
      reglas —sin esa limpieza un `\ufeff---` no abre el bloque y un comentario
      YAML se citaría como heading—.
    * Setext (`===`/`---`) NO soportado — limitación documentada: solo ATX.
    * Sin heading previo → `None` (ni `""` ni el nombre del archivo): el esquema
      admite nulo aquí y ese nulo es el valor almacenado (spec-mcp-server.md).

    Las consultas deben avanzar (los offsets de chunk son monótonos); una
    consulta hacia atrás reinicia el cursor y responde como la función naive.
    """

    def __init__(self, text: str) -> None:
        """Prepara el cursor sobre `text` sin plegar línea alguna."""
        self._text = text
        self._lines = text.splitlines(keepends=True)
        self._state = _HeadingState()
        self._next_line = 0
        self._scanned = 0

    def heading_before(self, char_start: int) -> str | None:
        """Último heading ATX que precede a `char_start`, avanzando el cursor (F1, T4)."""
        if char_start < self._scanned:
            self._state = _HeadingState()
            self._next_line = 0
            self._scanned = 0
        while self._next_line < len(self._lines):
            line = self._lines[self._next_line]
            if self._scanned + len(line) > char_start:
                break
            self._state.fold(line, index=self._next_line)
            self._scanned += len(line)
            self._next_line += 1
        # La línea parcial que llega a `char_start` se pliega sobre una copia: si
        # la consulta siguiente cae en la misma línea, la re-pliega completa.
        pending = self._state.copy()
        tail = self._text[self._scanned : char_start]
        for index, line in enumerate(tail.splitlines(), start=self._next_line):
            pending.fold(line, index=index)
        return pending.heading


def heading_before(text: str, char_start: int) -> str | None:
    """Extrae el último heading ATX que precede a `char_start` (F1, T4).

    Forma puntual: una sola consulta con cursor desechable. La semántica
    completa vive en `HeadingScanner`, que `chunk_document` comparte entre los
    chunks de un documento para no re-escanear el texto por chunk.
    """
    return HeadingScanner(text).heading_before(char_start)


def validate_offsets(text: str, char_start: int, char_end: int) -> tuple[int, int]:
    """Valida y devuelve los offsets de carácter de la cita (F1, §Chunking).

    Exige `0 <= char_start < char_end <= len(text)`; cualquier violación LANZA
    `CitationError` — nunca se recorta: la cita debe ser exacta.
    """
    if not 0 <= char_start < char_end <= len(text):
        raise CitationError(
            f"Offsets inválidos [{char_start}, {char_end}) sobre texto de {len(text)} "
            "caracteres (exigido: 0 <= char_start < char_end <= len(text))"
        )
    return char_start, char_end


def verify_slice_identity(text: str, char_start: int, char_end: int, chunk_text: str) -> bool:
    """Comprueba la identidad F1 `text[char_start:char_end] == chunk_text` (T1: 51/51).

    Devuelve False —sin lanzar— si los offsets están fuera de rango, para que
    T5/T6 puedan hacer un `assert` barato en caliente sin try/except.
    """
    if not 0 <= char_start < char_end <= len(text):
        return False
    return text[char_start:char_end] == chunk_text


def doc_kind_for(path: str | Path) -> DocKind:
    """Deriva `doc_kind` de la extensión del path, en minúsculas (§Chunking).

    ∈ {md, markdown, txt, pdf}. Una extensión desconocida o ausente LANZA
    `UnsupportedDocKindError` — nunca se asume `txt`, para que T5 falle temprano
    sobre material fuera de la whitelist.
    """
    suffix = Path(os.fspath(path)).suffix.lower().removeprefix(".")
    kind = _DOC_KIND_BY_SUFFIX.get(suffix)
    if kind is None:
        raise UnsupportedDocKindError(
            f"Extensión desconocida {suffix!r} en {os.fspath(path)!r}; "
            "doc_kind ∈ {md, markdown, txt, pdf}"
        )
    return kind


def model_id(config: Config | None = None) -> str:
    """Devuelve el id del embedder que guarda la fila en `model` (ADR-006, T4).

    Con la config resuelta devuelve su embedder configurado; sin ella, el
    default canónico importado de `config.py` — el único lugar del código donde
    ese literal existe (spec-embeddings.md).
    """
    if config is None:
        return DEFAULT_EMBEDDING_MODEL
    return config.embedding.model


def _closes_fence(line: str, fence: str) -> bool:
    """Comprueba si `line` cierra el bloque cercado: mismo char, longitud ≥, sin info string."""
    match = _FENCE_CLOSE.match(line)
    return match is not None and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence)


def _update_code_span(line: str, open_run: int) -> int:
    """Estado del span de código inline tras `line` (CommonMark: run de backticks igual cierra)."""
    for match in _BACKTICK_RUN.finditer(line):
        run_length = len(match.group())
        if open_run == 0:
            open_run = run_length
        elif run_length == open_run:
            open_run = 0
    return open_run


def _clean_heading_title(raw_title: str) -> str:
    """Quita la secuencia de cierre ATX (`## Título ##` → `Título`, CommonMark §ATX)."""
    return _ATX_CLOSING.sub("", raw_title).strip()
