"""Entrada del flow CocoIndex: `00-Resources/` → chunks citados con embedding en LanceDB.

Sirve specs/spec-rag-engine.md §Proposed Solution (esqueleto v1 corregido en D11)
y tasks/todo.md → T6 AC:

* **Lifespan** que inyecta la conexión LanceDB
  (`.tepochcalli/db/tepochcalli.lance`, §Target) y el `SentenceTransformerEmbedder`
  con `model`/`device` de `tepochcalli.toml` (E1, default `"cpu"`); ANTES de
  construir el embedder llama a `config.apply_model_cache_env()` (T3/E1).
* **Trío F2 de la purga automática** (condiciones 3/3, ninguna opcional):
  target gestionado (`lancedb.mount_table_target`), fan-out `coco.mount_each`
  (un componente por archivo ⇒ ruta estable) e ids `IdGenerator.next_id(chunk.text)`.
* **Índices ANN + FTS** declarados sobre la tabla: `declare_vector_index(column="embedding")`
  y `declare_fts_index(column="text")` (§Target LanceDB + índices).
* **Sin `cocoindex setup`** (no existe en la CLI v1): el entrypoint es
  `app.update_blocking()` en proceso o la CLI `cocoindex update <este archivo>`.

Sin reimplementación: el walk y los skips F5 salen de `source.build_path_matcher`
+ `source.classify_file`, el particionado y la cita derivada de
`parsers.chunk_document` y la forma canónica de la ruta de `citation` (T4/T5).

**Alcance de provider (spec-embeddings §Embeddings):** v1 solo soporta
`provider = "local"`; `provider = "litellm"` lanza
`EmbeddingProviderNotImplementedError` en el lifespan — no se construye a
medias la ruta LiteLLM.

**Raíz del vault:** `TEPOCHCALLI_VAULT_ROOT` si está definida (pruebas y vaults
alternativos); en caso contrario la derivada de este archivo
(`<vault>/.tepochcalli/flow/tepochcalli_flow/app.py` ⇒ el vault). El estado
del engine se fija en `<vault>/.tepochcalli/db/cocoindex/` — artefacto
derivado, gitignored y junto a LanceDB para que un solo `rm -r .tepochcalli/db/`
reconstruya todo (D14; spec-rag-engine §Rollback)— salvo que `COCOINDEX_DB`
esté definida, que manda (precedencia documentada en
https://cocoindex.io/docs/programming_guide/app/#lifespan-optional).
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import cocoindex as coco
from cocoindex.connectors import lancedb, localfs
from cocoindex.ops.sentence_transformers import SentenceTransformerEmbedder
from cocoindex.resources.file import FileLike
from cocoindex.resources.id import IdGenerator

from . import config as flow_config
from . import source
from .citation import RESOURCES_DIR, normalize_source_path
from .models import EMBEDDER, LANCE_DB, ChunkRow
from .parsers import DocumentChunk, chunk_document

logger = logging.getLogger(__name__)

VAULT_ROOT_ENV: Final = "TEPOCHCALLI_VAULT_ROOT"
"""Override de la raíz del vault (pruebas/vaults alternativos); default: la del payload."""

TABLE_NAME: Final = "chunks"
"""Tabla única del índice (spec-rag-engine §Target LanceDB + índices)."""

DB_RELPATH: Final = Path(".tepochcalli/db/tepochcalli.lance")
"""Base LanceDB embebida bajo el vault (ADR-002; §Target)."""

ENGINE_STATE_RELPATH: Final = Path(".tepochcalli/db/cocoindex")
"""Estado derivado del engine (D14): bajo `db/`, gitignored, junto a LanceDB.

Co-localizado con `DB_RELPATH` para que un solo `rm -r .tepochcalli/db/` —la
promesa de spec-rag-engine §Rollback— reconstruya LanceDB y el estado del
engine a la vez; jamás en `flow/`, que es código fuente versionado
(spec-vault-structure §gitignore).
"""


class EmbeddingProviderNotImplementedError(NotImplementedError):
    """Provider distinto de `local`: la ruta LiteLLM no está en v1 (§Embeddings).

    Aparece tipado para que T8/MCP pueda distinguir «configurado pero no
    implementado aún» de un fallo de indexación genérico.
    """


def resolve_vault_root() -> Path:
    """Resuelve la raíz del vault: env `TEPOCHCALLI_VAULT_ROOT` o la del payload.

    La derivación por `__file__` es estable porque el paquete es editable desde
    `<vault>/.tepochcalli/flow/` (mismo layout que instala el wizard, D2).
    """
    override = os.environ.get(VAULT_ROOT_ENV)
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3]


def _require_local_provider(config: flow_config.Config) -> None:
    """Exige `provider = "local"` en v1; `litellm` lanza el error tipado (§Embeddings)."""
    if config.embedding.provider != flow_config.DEFAULT_EMBEDDING_PROVIDER:
        raise EmbeddingProviderNotImplementedError(
            f"provider={config.embedding.provider!r} no está implementado aún: "
            "T6 soporta solo 'local' (SentenceTransformerEmbedder); la ruta "
            "LiteLLM llegará en una tarea posterior — spec-embeddings §Embeddings"
        )


@coco.lifespan
async def provide_resources(builder: coco.EnvironmentBuilder) -> AsyncIterator[None]:
    """Provee conexión LanceDB y embedder al Environment (§Proposed Solution; E1).

    Orden obligatorio: resolver config → exigir provider local →
    `apply_model_cache_env()` → construir el embedder. El cache de modelo se
    fija ANTES de instanciar embedder alguno (T3/E1).
    """
    vault_root = resolve_vault_root()
    config = flow_config.load_config(vault_root)
    _require_local_provider(config)
    config.apply_model_cache_env()
    if "COCOINDEX_DB" not in os.environ:
        builder.settings.db_path = vault_root / ENGINE_STATE_RELPATH
    builder.provide(LANCE_DB, await lancedb.connect_async(str(vault_root / DB_RELPATH)))
    builder.provide(
        EMBEDDER,
        SentenceTransformerEmbedder(config.embedding.model, device=config.embedding.device),
    )
    yield


@coco.fn
async def write_chunk(
    chunk: DocumentChunk,
    id_gen: IdGenerator,
    table: lancedb.TableTarget[ChunkRow],
) -> None:
    """Declara la fila LanceDB de un chunk: cita completa, id estable y vector (F1/F2).

    El id sale de `IdGenerator.next_id(chunk.text)` — condición 3/3 de la purga
    automática F2 — y el embedding de `use_context(EMBEDDER).embed()` (F6:
    `normalize_embeddings` vive en `embed()`, no en el constructor).
    """
    table.declare_row(
        row=ChunkRow(
            id=await id_gen.next_id(chunk.text),
            source_path=chunk.source_path,
            doc_kind=chunk.doc_kind,
            heading=chunk.heading,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
            text=chunk.text,
            embedding=await coco.use_context(EMBEDDER).embed(chunk.text),
            model=chunk.model,
            indexed_at=datetime.now(UTC).isoformat(),
        )
    )


@coco.fn(memo=True)
async def index_file(
    file: FileLike,
    table: lancedb.TableTarget[ChunkRow],
    config: flow_config.Config,
    resources_dir: Path,
) -> None:
    """Particiona un archivo con su cita derivada y fan-outea sus chunks (T5/T6).

    Memoizable por contenido: un archivo inmutable no se re-parsea ni se
    re-embebe (semántica Δ de spec-rag-engine §Semántica incremental). La ruta
    citada se normaliza con `citation.normalize_source_path` — nunca se
    reconstruye a mano.
    """
    text = await file.read_text()
    file_path = Path(os.fspath(file.file_path))
    chunks = chunk_document(
        text,
        normalize_source_path(file_path.relative_to(resources_dir)),
        config=config,
    )
    id_gen = IdGenerator()
    await coco.map(write_chunk, chunks, id_gen, table)


@coco.fn
async def build_flow() -> None:
    """Monta target gestionado, walk filtrado, fan-out por archivo e índices (T6).

    El trío F2 queda completo aquí: `mount_table_target` (gestionado),
    `coco.mount_each` (ruta de componente por archivo) y —dentro de
    `write_chunk`— `IdGenerator.next_id(chunk.text)`.
    """
    vault_root = resolve_vault_root()
    config = flow_config.load_config(vault_root)
    resources_dir = vault_root / RESOURCES_DIR
    table = await lancedb.mount_table_target(
        LANCE_DB,
        TABLE_NAME,
        table_schema=await lancedb.TableSchema.from_class(ChunkRow, primary_key=["id"]),
    )
    items = await _indexable_items(resources_dir)
    await coco.mount_each(index_file, items, table, config, resources_dir)
    table.declare_vector_index(column="embedding")
    table.declare_fts_index(column="text")


async def _indexable_items(resources_dir: Path) -> list[tuple[str, FileLike]]:
    """Walk real del conector + clasificación F5; devuelve SOLO indexables.

    `source.classify_file` (T5) decide: PDF pendiente de T7, ilegibles,
    oversized y rutas fuera de la whitelist nunca montan componente — se loguean
    como descarte sin abortar el delta (§Fuentes).
    """
    walker = localfs.walk_dir(
        resources_dir,
        recursive=True,
        path_matcher=source.build_path_matcher(),
    )
    items: list[tuple[str, FileLike]] = []
    async for key, file in walker.items():
        entry = source.classify_file(
            resources_dir,
            Path(os.fspath(file.file_path)),
            max_file_bytes=source.DEFAULT_MAX_FILE_BYTES,
        )
        if isinstance(entry, source.SourceEntry):
            items.append((key, file))
        else:
            logger.warning("Descartado %s: %s — %s", entry.source_path, entry.reason, entry.detail)
    return items


app = coco.App(coco.AppConfig(name="tepochcalli"), build_flow)
"""Entrypoint v1: `app.update_blocking()` o `cocoindex update <archivo>` (sin `setup`)."""
