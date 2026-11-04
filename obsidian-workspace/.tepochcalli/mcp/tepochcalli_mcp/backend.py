"""Backend de lectura del vault: `_VaultSearchBackend` — adaptador del puerto (W2/A-02).

Módulo de INFRAESTRUCTURA de la capa MCP (como `adapters/lancedb_reader` en el
flow y al lado de `embedder.py`): implementa el puerto fino `SearchBackend`
(`tools/search.py`, decisión T2 — el handler depende del puerto, no del motor)
y alimenta `rag_status` vía su DTO `IndexMeta` (T4). Es el SEGUNDO adaptador
del server y con el composition root (`server.py`, que lo construye e inyecta)
son los únicos módulos de la capa MCP que tocan el motor (`lancedb`, `cocoindex`
— solo en el corte de lectura). Solo lectura.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import TYPE_CHECKING

from tepochcalli_flow import citation
from tepochcalli_flow.config import Config
from tepochcalli_flow.layout import DB_RELPATH, TABLE_NAME
from tepochcalli_flow.ports import ChunkReader, CitedChunk

from tepochcalli_mcp import embedder
from tepochcalli_mcp.tools.rag_status import IndexMeta  # DTO del contrato de rag_status (T4)

if TYPE_CHECKING:
    from lancedb.table import AsyncTable


class _VaultSearchBackend:
    """`SearchBackend` sobre el vault real: lector Phase 1 + estado del índice.

    Implementa el puerto fino que `tools/search.py` consume (decisión T2:
    el handler depende del puerto, no del motor). Solo lectura. El lector y su
    embedder se construyen en la PRIMERA búsqueda (no en el arranque): el
    proceso stdio no paga el coste de torch/MiniLM hasta que alguien busca.
    """

    def __init__(self, vault_root: Path, config: Config) -> None:
        """Prepara el backend sobre `vault_root` con su config resuelta."""
        self._vault_root = vault_root
        self._config = config
        self._reader: ChunkReader | None = None

    @property
    def config(self) -> Config:
        """Config con la que se construyó este backend (R2: la compara `_backend()`)."""
        return self._config

    @property
    def expected_model(self) -> str:
        """Modelo configurado — el MISMO id que las filas guardan en `model` (ADR-006)."""
        return citation.model_id(self._config)

    async def index_models(self) -> set[str]:
        """Conjunto de `model` de las filas: vacío ⇒ índice inexistente (`INDEX_EMPTY`).

        Revisión Phase 2: lo UNIQUE de la columna en un solo punto con el borde
        de solo lectura de `_open_table` (review 2026-10-27): DB/tabla AUSENTE
        sin conectar ⇒ vacío (lancedb 0.40 no expone `execute_sql`/DISTINCT —
        coste residual documentado en `_select`); tabla EXISTENTE pero
        ilegible ⇒ el `ValueError` SUBE (el guard lo vuelve `INTERNAL`) —
        roto ya no finge vacío.

        El open de la tabla sale de `_open_table` de ESTE módulo — la MISMA
        apertura que `_select`/`index_meta` (W2/A-03: el handler ya comparte un
        único open por llamada; la cache de la tabla a escala queda en
        TECH_DEBT del eje perf, NO aquí: el docstring de `lancedb_reader.py`
        congela open-por-llamada del lector por los loops async).
        """
        return {str(row["model"]) for row in await self._select(["model"])}

    async def index_meta(self) -> IndexMeta:
        """DTO de estado del índice para `rag_status` (T4) — derivado, sin estado nuevo.

        Revisión Phase 2 (2026-10-27): el TOTAL sale de `count_rows()` —O(1),
        metadatos del fragmento, no lectura de filas—; `models` y
        `last_refresh` siguen de una proyección de 2 columnas
        (`max(indexed_at)`, ISO-8601 UTC con offset fijo ⇒ orden
        lexicográfico = cronológico). `db_size_bytes` = walk de TODO
        `<vault>/.tepochcalli/db/` — la spec dice `db/`, no solo el `.lance`.
        """
        db_root = self._vault_root / DB_RELPATH.parent
        size = (
            sum(path.stat().st_size for path in db_root.rglob("*") if path.is_file())
            if db_root.is_dir()
            else 0
        )
        async with self._open_table() as table:
            if table is None:  # DB o tabla AUSENTE: índice inexistente (vacío honesto)
                return IndexMeta(rows=0, models=set(), last_refresh=None, db_size_bytes=size)
            total = await table.count_rows()
            rows: list[dict[str, object]] = (
                await table.query().select(["model", "indexed_at"]).to_list()
            )
        return IndexMeta(
            rows=total,
            models={str(row["model"]) for row in rows},
            last_refresh=max((str(row["indexed_at"]) for row in rows), default=None),
            db_size_bytes=size,
        )

    @contextlib.asynccontextmanager
    async def _open_table(self) -> AsyncIterator[AsyncTable | None]:
        """Apertura de solo lectura de `chunks` — `None` si DB/tabla AUSENTE.

        Revisión Phase 2: la diferenciación vacío vs ROTO es honesta — DB
        ausente ∉ conectar (`connect_async` crearía el directorio) y tabla
        ausente se distingue con `list_tables()`; si la tabla EXISTE y es
        ilegible (`ValueError` de lancedb 0.40: esquema incompatible) el error
        ESCALA al caller → `internal_guard` ⇒ `INTERNAL` — jamás se finge
        `INDEX_EMPTY` con índice roto.
        """
        import lancedb  # adaptador: con el composition root, el único motor tocado aquí

        db_uri = self._vault_root / DB_RELPATH
        if not db_uri.exists():
            yield None
            return
        db = await lancedb.connect_async(str(db_uri))
        try:
            names = (await db.list_tables()).tables
            if TABLE_NAME not in names:
                yield None
                return
            yield await db.open_table(TABLE_NAME)
        finally:
            db.close()  # type: ignore[no-untyped-call]  # close() sin anotar en lancedb 0.40.0

    async def _select(self, columns: list[str]) -> list[dict[str, object]]:
        """Proyección de columnas de `chunks` — costura compartida search/rag_status (T2/T4).

        shortcut: lancedb 0.40.0 NO expone `execute_sql` — ni `SELECT DISTINCT
        model` ni `SELECT MAX(indexed_at)` bajan como pushdown a DataFusion; la
        proyección materializa solo ESAS columnas (cortas, sin `vector`) y el
        coste residual es O(filas) en ancho mínimo. Ver `_open_table` para el
        borde de ausencia/ilegibilidad (review 2026-10-27: roto ⇒ escala).
        """
        async with self._open_table() as table:
            if table is None:
                return []
            rows: list[dict[str, object]] = await table.query().select(columns).to_list()
        return rows

    async def cited_chunks(
        self, query: str, top_k: int, path_filter: str | None
    ) -> list[CitedChunk]:
        """Búsqueda por el puerto `ChunkReader` — el adaptador vectoriza la query (T2).

        El corte se construye con `_read_embedder` (este módulo, fábrica T6/D59):
        usa `SentenceTransformerEmbedder` sobre el **mismo path local** que el
        write path. Si el snapshot falta, `EmbedderModelError` sube al handler
        ⇒ `E_MODEL_INVALID` sin descargar nada.
        """
        if self._reader is None:
            from tepochcalli_flow.adapters.lancedb_reader import LanceDBChunkReader

            self._config.apply_model_cache_env()
            self._reader = LanceDBChunkReader(
                self._vault_root / DB_RELPATH,
                embed=_read_embedder(self._config),
            )
        return await self._reader.search(query, top_k, path_filter)


def _local_op(path: Path, device: str) -> embedder.AsyncEmbedder:
    """Op local de cocoindex (import perezoso: el arranque stdio no carga torch)."""
    from cocoindex.ops.sentence_transformers import SentenceTransformerEmbedder

    return SentenceTransformerEmbedder(str(path), device=device)


def _api_op(model: str, api_key: str) -> embedder.AsyncEmbedder:
    """Op de API de cocoindex (import perezoso: `litellm` no entra sin usarse).

    Rasgos de la op que el producto hereda (verificados en `ops/litellm.py`):
    reintentos con backoff exponencial (1 s ×2, tope 30 s) dentro de un
    `timeout` de 10 min — cierra TD-16; batching de 64
    (`@coco.fn.as_async(batching=True, max_batch_size=64)`); y un texto que
    empieza por `data:…;base64,`, `gs://` o `files/` se incrusta con un espacio
    delante — igual en write y read porque AMBOS usan esta op, así que la
    búsqueda sigue siendo consistente.
    """
    from cocoindex.ops.litellm import LiteLLMEmbedder

    return LiteLLMEmbedder(model, api_key=api_key)


def _read_embedder(config: Config) -> Callable[[str], list[float]]:
    """Fábrica del corte de LECTURA (T6/D59) — una sola implementación.

    Construye la op de cocoindex con el **path estable** del snapshot
    (`config.embedding_model_path`) y se la pasa a `embedder.build_read_cut`
    (que aplica la estrategia de provider y el dialecto de errores). El módulo
    `embedder` NO importa `cocoindex`: la frontera se cruza solo en este
    módulo adaptador y en el composition root, como con `lancedb`/`markitdown`.

    - `local`: `SentenceTransformerEmbedder(str(path), device=…)` — la op
      acepta «name **or path**» (fuente instalada: `ops/sentence_transformers.py:59-65`).
    - `api`: `LiteLLMEmbedder(model, api_key=…)` — constructor inerte; los
      reintentos con backoff y el batching de 64 son de la op (TD-16).
    """
    return embedder.build_read_cut(
        config,
        local_op_factory=_local_op,
        api_op_factory=_api_op,
    )
