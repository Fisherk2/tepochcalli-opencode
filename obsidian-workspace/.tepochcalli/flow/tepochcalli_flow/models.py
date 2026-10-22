r"""Esquema de fila LanceDB `chunks`: contrato de 10 campos (Phase 1, T6).

Sirve specs/spec-rag-engine.md §Target LanceDB + índices: la fila
`{id, source_path, doc_kind, heading, char_start, char_end, text, embedding,
model, indexed_at}` que T9 (puerto de lectura) y Phase 2 (contrato `search`)
congelan como lectura. Y §Embeddings: las dims del vector se resuelven desde el
embedder vía `Annotated[NDArray, EMBEDDER]` — nunca desde un literal `384` —
de modo que si cambia el modelo, el esquema sigue al embedder (ADR-006).

**D13:** `heading` es nullable — su valor es `None` cuando el documento no
tiene heading padre— mientras `source_path`, `char_start`, `char_end` y
`doc_kind` son no nulos; `TableSchema.from_class` traduce esa anotación a la
nulabilidad por columna de LanceDB (la cita es estructural, ADR-005).

Código de infraestructura (adaptador del target, hexagonal: la dependencia
apunta hacia el motor): importa `cocoindex` deliberadamente — la fila ES el
contrato con LanceDB; `citation.py`/`config.py`/`parsers.py` siguen sin tocarlo.
Las claves `ContextKey` viven AQUÍ —y no en `app.py`— porque la anotación del
vector debe resolver en este módulo sin imports circulares: `app.py` las
importa de aquí.

Notas de mapeo (fuente instalada `cocoindex==1.0.25`, `connectors/lancedb/_target.py`):

* `doc_kind` se anota `str`, no `DocKind`: un `Literal` caería en el mapeo
  JSON-encoder y almacenaría `"\"md\""`. El valor en ejecución sigue
  restringido al conjunto `citation.DocKind` por `parsers.chunk_document`.
* `indexed_at` es ISO-8601 UTC (`str`) por el mismo mapeo limpio: un `datetime`
  también pasaría por el encoder JSON.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

import cocoindex as coco
from cocoindex.connectors.lancedb import LanceAsyncConnection
from cocoindex.ops.sentence_transformers import SentenceTransformerEmbedder
from numpy.typing import NDArray

LANCE_DB = coco.ContextKey[LanceAsyncConnection]("tepochcalli_db")
"""Conexión asíncrona a la base LanceDB del vault (spec-rag-engine §Target)."""

EMBEDDER = coco.ContextKey[SentenceTransformerEmbedder]("embedder", detect_change=True)
"""Embedder del flow con detección de cambio: otro modelo ⇒ re-embedding (ADR-006)."""


@dataclass(frozen=True)
class ChunkRow:
    """Una fila de la tabla `chunks` por chunk citado (spec-rag-engine §Target)."""

    id: int
    """Id estable derivado del texto del chunk — `IdGenerator.next_id` (F2 3/3)."""

    source_path: str
    """Cita POSIX `00-Resources/...` con anidamiento intacto (no nulo; D9.1, D13)."""

    doc_kind: str
    """`md|markdown|txt|pdf` (no nulo, dominio `citation.DocKind`; D13)."""

    heading: str | None
    """Último heading ATX previo; `None` sin padre (nullable presente; D13)."""

    char_start: int
    """Offset de carácter inicio dentro del texto extraído (no nulo; identidad F1)."""

    char_end: int
    """Offset de carácter fin exclusivo (no nulo): el slice reproduce `text` (F1)."""

    text: str
    """Contenido exacto del chunk, idéntico al rango que citan sus offsets (F1)."""

    embedding: Annotated[NDArray, EMBEDDER]
    """Vector 384-d normalizado (F6); dims y modelo resueltos desde el embedder."""

    model: str
    """Embedder que vectorizó el chunk — detección de índice mixto (ADR-006)."""

    indexed_at: str
    """Instante ISO-8601 UTC en que la fila se escribió (§Rollback / Monitoring)."""
