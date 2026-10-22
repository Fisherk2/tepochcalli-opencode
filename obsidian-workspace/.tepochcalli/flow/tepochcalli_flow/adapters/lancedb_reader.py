"""Adaptador LanceDB del puerto `ChunkReader` — híbrido ANN+FTS con cita congelada (T9).

Implementa `tepochcalli_flow.ports.ChunkReader` sobre la tabla `chunks` que T6
escribe en `.tepochcalli/db/tepochcalli.lance` (spec-rag-engine §Target
LanceDB + índices: ANN sobre `embedding` + FTS sobre `text`, ambos declarados
por el flow). ES código de infraestructura: importa `lancedb` deliberadamente
— la frontera hexagonal corre contra `ports.py`, que sigue sin motor
(test de arquitectura de CP-B, extendido en T9).

**Búsqueda híbrida (ambos índices, sin tuning — Phase 6 afinará).** Una sola
llamada a `table.query().nearest_to(vector).nearest_to_text(texto)` ejecuta
dos piernas —ANN (vecinos más cercanos sobre `embedding`) y FTS (BM25 sobre
`text`)— y las fusiona con `RRFReranker(K=60)`, el reranker por defecto de
LanceDB para `query_type="hybrid"` (https://docs.lancedb.com/search/hybrid-search;
el default y la fórmula están en la fuente instalada
`lancedb==0.40.0/rerankers/rrf.py`). No se expone ningún peso vector/FTS:
RRF fusiona por RANGO y no necesita que las escalas sean comparables.

**`score` ∈ [0,1]: mapeo y su significado honesto.** RRF puntúa cada chunk con

    rrf(chunk) = Σ_{piernas donde aparece} 1 / (rango_en_pierna + K),  K = 60

(fórmula de Cormack et al., SIGIR 2009 —
https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf, la misma que cita
el docstring de `RRFReranker` en la fuente instalada). El máximo teórico es
`2/(K+1)` (rango 1 en LAS DOS piernas), así que el `score` devuelto es

    score = rrf(chunk) * (K + 1) / 2,   recortado a [0, 1]

y NO es una probabilidad ni una similitud calibrada: es la fuerza de fusión
por rango RELATIVA al máximo teórico. Léase: 1.0 = primer rank en ANN y en
FTS a la vez; ~0.5 = primer rank en una sola pierna; monótono en los rangos;
comparable dentro del resultado de UNA consulta, no entre consultas (la
distancia nativa `_distance` de la pierna ANN —coseno, `1 - x·y/(‖x‖‖y‖)`
según https://docs.lancedb.com/search/vector-search— nunca se expone: en
modo híbrido las dos piernas tienen escalas inconmensurables —distancia
coseno vs BM25— y RRF existe precisamente para evitar compararlas).

**`path_filter`: glob relativo al vault ≡ `LIKE` de Phase 2.** El glob se
traduce a SQL con `path_filter_to_like_predicate` — `*` → `%`, `?` → `_`,
comodines `*`/`?` que SÍ cruzan `/` (semántica `LIKE`, la misma que
spec-mcp-server §search documenta como `*`→`%`; `**` ≡ `*`, como en el
ejemplo `00-Resources/lit-pediatría/**/*.pdf` de la spec)— y se aplica como
PREFILTRO `.where(...)` sobre ambas piernas (por defecto en el API asíncrona
de LanceDB; https://docs.lancedb.com/search/hybrid-search §prefilter).

**Ciclo de vida:** la conexión se abre y cierra POR LLAMADA. Es una decisión,
no un descuido: es barata (abrir un dataset embebido no arranca proceso
alguno — ADR-002), evita que un handle asíncrono vivo atrape el loop de
`asyncio.run` de un calling (los tests crean un loop por test) y deja que
Phase 2 agregue pooling en SU loop si el bench lo exige. Solo LEE: ni el
constructor ni `search` escriben disco alguno (verificador T9 lo snapshot-ea).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Final

import lancedb
from lancedb.rerankers import RRFReranker

from ..config import DEFAULT_TOP_K
from ..ports import CitedChunk

TABLE_NAME: Final = "chunks"
"""Tabla única del índice (spec-rag-engine §Target; `app.TABLE_NAME`, sin importar app)."""

VECTOR_COLUMN: Final = "embedding"
"""Columna vectorial ANN (ChunkRow.embedding; dims resueltas por el embedder)."""

FTS_COLUMN: Final = "text"
"""Columna con índice FTS nativo (ChunkRow.text; T6 la declara con declare_fts_index)."""

RRF_K: Final = RRFReranker().K
"""Constante K del RRF — el default de `RRFReranker` (leído de lancedb==0.40.0).

Se lee del reranker en vez de hardcodearla: la búsqueda híbrida usa el
`RRFReranker()` por defecto de `query_type="hybrid"`, y si un upgrade de
LanceDB cambiara el default, esta constante —y con ella la normalización— lo
seguirían sin reescribir la fórmula.
"""

RRF_MAX_SCORE: Final[float] = 2.0 / (RRF_K + 1)
"""Máximo teórico de RRF con dos piernas: rango 1 en ANN y en FTS (ver módulo)."""

_EscapeChars: Final = {"%": "\\%", "_": "\\_"}
r"""Literales LIKE que deben escaparse en el patrón (`\` ya se normalizó a `/`)."""


class LanceDBChunkReader:
    """`ChunkReader` sobre la tabla `chunks` de una base LanceDB embebida.

    El query vector lo inyecta el llamador (`embed`: texto → vector) — este
    adaptador no construye embedders (Phase 2 los gestiona y sus errores
    `E_*`; spec-mcp-server §Errors) — y el resto es solo lectura sobre el
    dataset que el flow de T6 mantiene.
    """

    def __init__(
        self,
        db_uri: str | Path,
        embed: Callable[[str], list[float]],
        *,
        table_name: str = TABLE_NAME,
    ) -> None:
        """Prepara el lector sobre `db_uri` (el directorio `*.lance` del vault).

        `embed` es un callable síncrono texto→vector (p. ej. la captura de
        `SentenceTransformer.encode`); la conexión a la tabla NO se abre aquí
        sino en cada `search` (ver docstring del módulo).
        """
        self._db_uri = str(db_uri)
        self._embed = embed
        self._table_name = table_name

    async def search(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        path_filter: str | None = None,
    ) -> list[CitedChunk]:
        """Los `top_k` chunks más relevantes para `query`, orden descendente (§search).

        Ejecuta la búsqueda híbrida ANN+FTS con prefiltro `path_filter` (glob
        relativo al vault) y devuelve la forma congelada `CitedChunk` — los
        seis campos SIEMPRE presentes, `heading` nullable (D13). `ValueError`
        en el borde para consulta vacía, `top_k < 1` o glob inválido; un
        esquema roto (tabla sin índices) propaga la excepción de LanceDB sin
        envolver: es un error de indexación, no de contrato.
        """
        text = query.strip()
        if not text:
            raise ValueError("query vacía: se exige una consulta no vacía (§search)")
        if top_k < 1:
            raise ValueError(f"top_k debe ser >= 1, recibido: {top_k}")
        predicate = path_filter_to_like_predicate(path_filter) if path_filter else None

        query_vector = self._embed(text)
        db = await lancedb.connect_async(self._db_uri)
        try:
            table = await db.open_table(self._table_name)
            search = (
                table.query()
                .nearest_to(query_vector)
                .nearest_to_text(text, columns=[FTS_COLUMN])
                .column(VECTOR_COLUMN)
                .limit(top_k)
            )
            if predicate is not None:
                search = search.where(predicate)
            rows = await search.to_list()
        finally:
            db.close()
        return _to_cited_chunks(rows)

    async def count_rows(self) -> int:
        """Filas de la tabla `chunks` — diagnóstico para el verificador (M4)."""
        db = await lancedb.connect_async(self._db_uri)
        try:
            table = await db.open_table(self._table_name)
            return await table.count_rows()
        finally:
            db.close()

    async def explain_plan(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        path_filter: str | None = None,
    ) -> str:
        """Plan de la búsqueda híbrida SIN ejecutarla (diagnóstico T9: ambas piernas).

        Útil para afirmar —sin depender del corpus— que la consulta usa el
        índice ANN (`KNNVectorDistance`), el índice FTS (`_score`) y la fusión
        RRF (`RRFReranker`).
        """
        text = query.strip()
        if not text:
            raise ValueError("query vacía: se exige una consulta no vacía (§search)")
        if top_k < 1:
            raise ValueError(f"top_k debe ser >= 1, recibido: {top_k}")
        predicate = path_filter_to_like_predicate(path_filter) if path_filter else None

        query_vector = self._embed(text)
        db = await lancedb.connect_async(self._db_uri)
        try:
            table = await db.open_table(self._table_name)
            search = (
                table.query()
                .nearest_to(query_vector)
                .nearest_to_text(text, columns=[FTS_COLUMN])
                .column(VECTOR_COLUMN)
                .limit(top_k)
            )
            if predicate is not None:
                search = search.where(predicate)
            return await search.explain_plan()
        finally:
            db.close()


def path_filter_to_like_predicate(path_filter: str) -> str:
    r"""Traduce el glob `path_filter` al predicado SQL `LIKE` de Phase 2 (§search).

    Equivalencia CONGELADA — la que spec-mcp-server §search anticipa como
    `*`→`%`—, generando `source_path LIKE '<patrón>' ESCAPE '\'`:

    * `*` → `%` (cualquier secuencia, INCLUYENDO `/`: semántica LIKE, no de
      shell; por eso `**` ≡ `*`, como en el ejemplo de la spec
      `00-Resources/lit-pediatría/**/*.pdf`);
    * `?` → `_` (un solo carácter, también cruza `/`);
    * los literales `%` y `_` del glob se escapan con `\` (un `_` de nombre
      propio —p. ej. `con_guion_bajo.md`— no debe casar cualquier carácter);
    * `\` del glob se normaliza a `/` ANTES de traducir, igual que
      `citation.normalize_source_path` (rutas POSIX, D9.1);
    * `'` se duplica (`''`): el predicado es una cadena SQL, nunca inyección.

    El glob es RELATIVO a la raíz del vault —como el `source_path` almacenado,
    que ya incluye `00-Resources/` (D9.1)—: un path absoluto o con `..`
    LANZA `ValueError` (frontera de confianza; el calling Phase 2 no puede
    colar un filtro que escape del vault).
    """
    if path_filter.startswith("/"):
        raise ValueError(
            f"path_filter debe ser un glob relativo al vault, no absoluto: {path_filter!r}"
        )
    if ".." in PurePosixPath(path_filter).parts:
        raise ValueError(
            f"path_filter no puede contener segmentos '..' (escape del vault): {path_filter!r}"
        )
    pattern = "".join(
        "%" if char == "*" else "_" if char == "?" else _EscapeChars.get(char, char)
        for char in path_filter.replace("\\", "/")
    )
    return f"source_path LIKE '{pattern.replace(chr(39), chr(39) * 2)}' ESCAPE '\\'"


def _to_cited_chunks(rows: list[dict[str, object]]) -> list[CitedChunk]:
    """Mapea filas LanceDB (con `_relevance_score` RRF) a `CitedChunk` normalizado.

    El score RRF se reescala al máximo teórico `2/(K+1)` y se recorta a
    [0,1] (ver docstring del módulo); el orden de llegada ya es descendente
    —RRF ordena por `_relevance_score`— pero se re-ordena aquí para GARANTIZAR
    el contrato aunque el almacén cambiara (estable: los empates conservan el
    orden del fusor).
    """
    chunks = [
        CitedChunk(
            text=str(row["text"]),
            source_path=str(row["source_path"]),
            heading=None if row["heading"] is None else str(row["heading"]),
            char_start=int(row["char_start"]),
            char_end=int(row["char_end"]),
            score=min(1.0, max(0.0, float(row["_relevance_score"]) / RRF_MAX_SCORE)),
        )
        for row in rows
    ]
    chunks.sort(key=lambda chunk: chunk.score, reverse=True)
    return chunks
