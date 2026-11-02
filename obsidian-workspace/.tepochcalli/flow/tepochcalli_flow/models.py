r"""Contratos tipados del flow: fila LanceDB `chunks` y reporte de refresh Δ (Phase 1, T6/T8).

Sirve specs/spec-rag-engine.md §Target LanceDB + índices: la fila
`{id, source_path, doc_kind, heading, char_start, char_end, text, embedding,
model, indexed_at}` que T9 (puerto de lectura) y Phase 2 (contrato `search`)
congelan como lectura. Y §Embeddings: las dims del vector se resuelven desde el
embedder vía `Annotated[NDArray[Any], EMBEDDER]` — nunca desde un literal `384` —
de modo que si cambia el modelo, el esquema sigue al embedder (ADR-006).

T8 añade el segundo contrato del módulo: `RefreshReport`, el retorno tipado de
`app.refresh_blocking()` que Phase 2 serializa **tal cual** en la tool
`index_refresh` (spec-mcp-server §Tool `index_refresh`) — su contabilidad de
`{scanned, indexed, skipped}` está documentada en la clase y NO puede mentir
(hallazgo #5 de CP-B).

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
from pathlib import Path
from typing import Annotated, Any

import cocoindex as coco
from cocoindex.connectors.lancedb import LanceAsyncConnection
from cocoindex.ops.sentence_transformers import SentenceTransformerEmbedder
from numpy.typing import NDArray

LANCE_DB = coco.ContextKey[LanceAsyncConnection]("tepochcalli_db")
"""Conexión asíncrona a la base LanceDB del vault (spec-rag-engine §Target)."""

EMBEDDER = coco.ContextKey[SentenceTransformerEmbedder]("embedder", detect_change=True)
"""Embedder del flow con detección de cambio: otro modelo ⇒ re-embedding (ADR-006)."""

ROOT_KEY: coco.ContextKey[Path] = coco.ContextKey[Path]("tepochcalli_root")
"""Base ESTABLE de cada `FilePath` del walk (D62, ADR-010 §4.7).

Verificado en `cocoindex==1.0.25` (`connectors/localfs/_common.py`): un `Path`
pelado resuelve contra el **CWD** del proceso, así que la clave de memo
dependería de dónde se lanzó el server. Con `base_dir=ROOT_KEY` explícito, el
`__coco_memo_key__()` de `FilePath` es `(clave, ruta relativa al vault)` y
mover el árbol no invalida el índice. El valor lo provee el lifespan con la
raíz del vault de hoy; la identidad no cambia con esa ruta.
"""


@dataclass(frozen=True)
class ChunkRow:
    """Una fila de la tabla `chunks` por chunk citado (spec-rag-engine §Target)."""

    id: int
    """Id estable derivado del texto del chunk — `IdGenerator.next_id` (F2 3/3)."""

    source_path: str
    """Cita POSIX relativa al VAULT con anidamiento intacto (no nulo; D41/D13)."""

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

    embedding: Annotated[NDArray[Any], EMBEDDER]
    """Vector 384-d normalizado (F6); dims y modelo resueltos desde el embedder.

    El dtype se deja como `Any` a propósito: lo resuelve el `VectorSchema` del
    embedder del contexto (`EMBEDDER`), que es quien fija dims y precisión
    (ADR-006). Un literal aquí (p. ej. `np.float32`) no aporta nada al schema y
    mentiría si cambia el embedder; `NDArray[Any]` sí es lo único que mypy
    acepta — el alias de numpy exige argumento de tipo.
    """

    model: str
    """Embedder que vectorizó el chunk — detección de índice mixto (ADR-006)."""

    indexed_at: str
    """Instante ISO-8601 UTC en que la fila se escribió (§Rollback / Monitoring)."""


@dataclass(frozen=True)
class RefreshReport:
    """Reporte de un ciclo Δ de `index_refresh` (spec-mcp-server §Tool `index_refresh`).

    Es el contrato que Phase 2 serializa tal cual (`dataclasses.asdict`), así
    que su contabilidad no puede mentir — el hallazgo #5 de CP-B demostró que
    dos casos se caían fuera de `skipped`. La identidad se sostiene POR
    CONSTRUCCIÓN en cada pasada:

        scanned == indexed + skipped

    * `scanned`: entradas de ruta VISITADAS por la pasada: los candidatos que
      el walk del conector entrega (indexables y los que `classify_file`
      descarta con `SkipReason`) más las que el conector traga en silencio y
      `source.unvisited_skips` recupera — symlink roto y directorio ilegible
      (este último contado como UNA entrada: sus archivos internos son
      inenumerables y no se inventan).
    * `indexed`: archivos cuyos chunks se (re)escribieron en esta pasada —
      data plane del componente `index_file` (`num_adds + num_reprocesses`),
      nunca el total de la pasada: la traversa `build_flow` reporta
      `reprocess=1` por diseño (E2), leerla mintiría sobre la idempotencia.
      Los borrados NO cuentan: un archivo borrado no es una visita; su purga
      se observa en las filas de LanceDB (F2).
    * `skipped`: `scanned - indexed` — toda entrada visitada que no reescribió
      el índice: excluida por clasificación, memoizada (`unchanged`), FALLIDA
      (no-UTF-8 o TOCTOU classify→read, aisladas por el exception handler del
      lifespan) o directorio ilegible. Los fallos quedan así CONTADOS en el
      contrato en vez de perderse en un log.
    * `elapsed_ms`: duración de la pasada medida con `time.monotonic()` —
      inmune a ajustes del reloj de sistema (puede ser 0 en un refresh
      bloqueado por candado, que no ejecuta update alguno).
    * `locked`: `True` ⇔ otro proceso retenía el candado: NO se ejecutó
      `update` y el reporte es cero en las tres cuentas (sin escrituras).
    * `roots`: las raíces de la pasada, tal como se pidieron (aditivo, ADR-010
      §4.1). Sin argumento es `("00-Resources",)`; las raíces viven solo en la
      invocación y no sobreviven al proceso (D32).
    """

    scanned: int
    """Entradas de ruta visitadas por la pasada (indexables + descartes + silenciosas)."""

    indexed: int
    """Archivos cuyos chunks se (re)escribieron — data plane de `index_file`."""

    skipped: int
    """`scanned - indexed`: visitadas sin reescritura — excluidas, memoizadas o fallidas."""

    elapsed_ms: int
    """Duración de la pasada en milisegundos con reloj MONOTÓNICO (`time.monotonic`)."""

    locked: bool
    """`True` si otro proceso retenía el candado y la invocación NO ejecutó update."""

    roots: tuple[str, ...]
    """Raíces pedidas en esta pasada, relativas al vault (ADR-010 §4.1; aditivo)."""
