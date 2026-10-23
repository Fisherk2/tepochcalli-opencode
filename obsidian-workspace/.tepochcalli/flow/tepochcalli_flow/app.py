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
* **Δ con lock de un solo proceso y métricas (T8):** `refresh_blocking()` es el
  entrypoint que Phase 2 invocará en `index_refresh` —adquiere
  `.tepochcalli/db/refresh.lock` (candado del SO; ver constante), corre el
  update sobre el loop de fondo de cocoindex y devuelve el `RefreshReport`
  tipado de `models` (`{scanned, indexed, skipped, elapsed_ms, locked}`).
  Los fallos por fichero (no-UTF-8, TOCTOU classify→read) quedan AISLADOS y
  CONTADOS: el exception handler del lifespan los localiza en el log y la
  cuenta `scanned == indexed + skipped` los absorbe en `skipped`
  (https://cocoindex.io/docs/advanced_topics/exception_handlers/).

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

import asyncio
import errno
import logging
import os
import sys
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import cocoindex as coco
from cocoindex._internal.environment import default_env_loop
from cocoindex.connectors import lancedb, localfs
from cocoindex.ops.sentence_transformers import SentenceTransformerEmbedder
from cocoindex.resources.id import IdGenerator

from . import config as flow_config
from . import source
from .citation import RESOURCES_DIR, normalize_source_path
from .models import EMBEDDER, LANCE_DB, ChunkRow, RefreshReport
from .parsers import DocumentChunk, chunk_document

logger = logging.getLogger(__name__)

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

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

LOCK_RELPATH: Final = Path(".tepochcalli/db/refresh.lock")
"""Lock file del refresh bajo `.tepochcalli/db/` — decisión deliberada T8 (T2, D14).

* **Ubicación:** `db/` es el artefacto gitignored que el refresh PROTEGE
  (LanceDB + estado del engine): candado junto a lo que muta, sin ensuciar
  `git status` y limpiado por el mismo `rm -r .tepochcalli/db/` del rollback.
* **El candado NO es el archivo: es el lock exclusivo del SO sobre él.** El
  kernel lo libera aunque el proceso muera con SIGKILL, así que UN CRASH NO
  PUEDE DEJAR UN CANDADO RETENIDO. Un lock file residual (p. ej. con el pid de
  un proceso muerto) es inofensivo: no retiene lock alguno y la siguiente
  pasada lo reutiliza — jamás se borra, porque el par `unlink`/`create`
  introduce carreras entre adquirentes.
* Segunda invocación concurrente ⇒ el lock falla ⇒ `RefreshReport(...,
  locked=True)` SIN arrancar update: cierra el doble-write que ADR-002 §6
  acepta como riesgo.
* Rama POSIX (`fcntl.flock`) + rama Windows (`msvcrt.locking`, ADR-003); la
  win32 no tiene cobertura en la CI de fase 1 (solo se prueba el flock real).
"""

FILE_PROCESSOR: Final = "index_file"
"""Nombre del componente por fichero: de SUS stats sale `indexed` (data plane).

Nunca `stats.total`: la traversa `build_flow` reporta `reprocess=1` por diseño
(E2) y contaminaría la idempotencia (hallazgo del T8; spec-rag-engine §Semántica
incremental).
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


def _observe_component_failure(exc: BaseException, ctx: coco.ExceptionContext) -> None:
    """Exception handler global: el fallo de UN fichero no aborta el delta (F5/T8).

    Registrado en el lifespan; sustituye el log por defecto del engine con la
    misma severidad (ERROR) y añade `stable_path` para localizar el fichero —
    es lo que hace visibles el no-UTF-8 y el TOCTOU classify→read que solo
    aparecían en un log (hallazgo #5 de CP-B).

    Devuelve SIEMPRE `None`: si una excepción escapara de aquí, se propagaría
    por `handle.ready()` y rompería el aislamiento por fichero que el engine
    aplica a los `mount_each` en segundo plano
    (https://cocoindex.io/docs/advanced_topics/exception_handlers/).
    """
    logger.error("component build failed: %s (%s)", exc, ctx.stable_path, exc_info=exc)


@coco.lifespan
async def provide_resources(builder: coco.EnvironmentBuilder) -> AsyncIterator[None]:
    """Provee conexión LanceDB y embedder al Environment (§Proposed Solution; E1).

    Orden obligatorio: resolver config → exigir provider local →
    `apply_model_cache_env()` → construir el embedder. El cache de modelo se
    fija ANTES de instanciar embedder alguno (T3/E1). El exception handler
    global (T8) asegura que un fallo por fichero quede aislado y localizado en
    el log sin abortar nunca el delta (F5).
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
    builder.set_exception_handler(_observe_component_failure)
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
    file: localfs.File,
    table: lancedb.TableTarget[ChunkRow],
    config: flow_config.Config,
    resources_dir: Path,
) -> None:
    """Particiona un archivo con su cita derivada y fan-outea sus chunks (T5/T6).

    Memoizable por contenido: un archivo inmutable no se re-parsea ni se
    re-embebe (semántica Δ de spec-rag-engine §Semántica incremental). La ruta
    citada se normaliza con `citation.normalize_source_path` — nunca se
    reconstruye a mano. La lectura es UTF-8 estricto (`errors="strict"`, BOM
    incluido): el MISMO decodificador que `parsers.extract_text`, para que los
    offsets F1 se midan sobre el mismo string en ambos caminos.
    """
    text = await file.read_text(encoding="utf-8", errors="strict")
    file_path = Path(os.fspath(file.file_path))
    # Re-chequeo TOCTOU classify→read: el archivo pudo crecer (o conmutarse) tras
    # el classifier; superarlo aquí falla el componente de ESTE fichero (aislado,
    # el pase continúa) en vez de indexar >100MB.
    if (size := os.stat(file_path).st_size) > source.DEFAULT_MAX_FILE_BYTES:
        raise ValueError(
            f"{file_path}: creció a {size} bytes tras el classify "
            f"(> {source.DEFAULT_MAX_FILE_BYTES}); cambió durante el pase"
        )
    chunks = chunk_document(
        text,
        normalize_source_path(file_path.relative_to(resources_dir)),
        config=config,
    )
    id_gen = IdGenerator()
    await coco.map(write_chunk, chunks, id_gen, table)


@dataclass(frozen=True)
class _ScanTally:
    """Tally del pase de clasificación: lo que `build_flow` devuelve a `refresh_blocking`.

    Cruza la frontera del engine como resultado de la main function (serde
    msgspec de dataclass, mismo camino que `DocumentChunk`); `refresh_blocking`
    lo combina con `UpdateStats` para armar el `RefreshReport`.
    """

    scanned: int
    """Entradas de ruta visitadas: candidatos entregados + descartes + silenciosas."""


@coco.fn
async def build_flow() -> _ScanTally:
    """Monta target gestionado, walk filtrado, fan-out por archivo e índices (T6).

    El trío F2 queda completo aquí: `mount_table_target` (gestionado),
    `coco.mount_each` (ruta de componente por archivo) y —dentro de
    `write_chunk`— `IdGenerator.next_id(chunk.text)`.

    Devuelve el `_ScanTally` del pase (T8): `refresh_blocking` lo lee del
    resultado de la main function para armar `RefreshReport.scanned`. La
    traversa se re-ejecuta SIEMPRE (reprocess=1 por diseño, E2), así que el
    tally refleja el pase actual aunque nada haya cambiado.
    """
    vault_root = resolve_vault_root()
    config = flow_config.load_config(vault_root)
    resources_dir = vault_root / RESOURCES_DIR
    table = await lancedb.mount_table_target(
        LANCE_DB,
        TABLE_NAME,
        table_schema=await lancedb.TableSchema.from_class(ChunkRow, primary_key=["id"]),
    )
    items, scanned = await _indexable_items(resources_dir)
    await coco.mount_each(index_file, items, table, config, resources_dir)
    table.declare_vector_index(column="embedding")
    table.declare_fts_index(column="text")
    return _ScanTally(scanned=scanned)


async def _indexable_items(resources_dir: Path) -> tuple[list[tuple[str, localfs.File]], int]:
    """Walk real del conector + clasificación F5; SOLO indexables + total visitado (T8).

    `source.classify_file` (T5) decide: symlinks que escapan del recurso
    (frontera de confianza), ilegibles, oversized y rutas fuera de la whitelist
    nunca montan componente — se loguean como descarte sin abortar el delta
    (§Fuentes). Los `.pdf` los parsea Docling (T7): el walk ya no los descarta.

    Devuelve `(items, scanned)`: además de los candidatos entregados (indexables
    y descartes con motivo), `scanned` cuenta las entradas que el conector traga
    en silencio y `source.unvisited_skips` recupera — symlink roto y directorio
    ilegible—, de modo que la identidad `scanned == indexed + skipped` del
    `RefreshReport` no mienta (hallazgo #5 de CP-B; spec-mcp-server §`index_refresh`).
    """
    walker = localfs.walk_dir(
        resources_dir,
        recursive=True,
        path_matcher=source.build_path_matcher(),
    )
    items: list[tuple[str, localfs.File]] = []
    scanned = 0
    async for key, file in walker.items():
        scanned += 1
        entry = source.classify_file(
            resources_dir,
            Path(os.fspath(file.file_path)),
            max_file_bytes=source.DEFAULT_MAX_FILE_BYTES,
        )
        if isinstance(entry, source.SourceEntry):
            items.append((key, file))
        else:
            logger.warning("Descartado %s: %s — %s", entry.source_path, entry.reason, entry.detail)
    silent = source.unvisited_skips(resources_dir)
    scanned += len(silent)
    for skip in silent:
        logger.warning("Descartado %s: %s — %s", skip.source_path, skip.reason, skip.detail)
    return items, scanned


app = coco.App(coco.AppConfig(name="tepochcalli"), build_flow)
"""Entrypoint v1: `app.update_blocking()` o `cocoindex update <archivo>` (sin `setup`)."""


def _try_exclusive_lock(fd: int) -> None:
    """Lock exclusivo NO bloqueante sobre `fd`; `OSError` de bloqueo = ya retenido."""
    if sys.platform == "win32":
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _release_os_lock(fd: int) -> None:
    """Libera el lock del SO; la rama Windows exige volver a la posición 0."""
    if sys.platform == "win32":
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)


def _acquire_refresh_lock(vault_root: Path) -> int | None:
    """Devuelve el fd del candado de refresh retenido, o `None` si OTRO proceso lo retiene ya.

    Semántica de stale (decisión en `LOCK_RELPATH`): el candado es el lock del
    SO, no el archivo — un crash no puede dejarlo retenido (el kernel lo suelta
    con el proceso) y el lock file residual se REUTILIZA sin leer su contenido.
    El pid se escribe solo como diagnóstico, tras retener. Un error de bloqueo
    distinto de «ya retenido» se propaga: un disco roto no es un refresh
    concurrente.
    """
    path = vault_root / LOCK_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        _try_exclusive_lock(fd)
    except OSError as exc:
        os.close(fd)
        if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK):
            return None
        raise
    os.lseek(fd, 0, os.SEEK_SET)
    os.ftruncate(fd, 0)
    os.write(fd, f"{os.getpid()}\n".encode())
    return fd


def _release_refresh_lock(fd: int) -> None:
    """Suelta el candado y cierra el fd; el lock file persiste a propósito."""
    try:
        _release_os_lock(fd)
    finally:
        os.close(fd)


def _update_blocking_with_stats() -> tuple[_ScanTally, coco.UpdateStats]:
    """Corre el update bloqueantemente y devuelve (tally del pase, stats finales).

    `app.update_blocking()` no expone stats y `app.update()` exige `await` en
    el MISMO loop del environment de cocoindex. Se programa la consumición en
    el loop de FONDO compartido (`default_env_loop`, el mismo que usan las
    rutas síncronas como `update_blocking` — pin interno `cocoindex==1.0.25`
    de pyproject) porque allí vive el environment y porque pasadas sucesivas en
    el mismo proceso así funcionan: un `asyncio.run` por pasada cierra su loop
    y la segunda falla con «Event loop is closed» (sonda T8).

    `handle.stats()` tras `handle.result()` devuelve el snapshot FINAL, con
    `by_component["index_file"]` en el data plane
    (https://cocoindex.io/docs/advanced_topics/progress_monitoring/).
    """
    handle = app.update()

    async def _consume() -> tuple[_ScanTally, coco.UpdateStats]:
        await coco.default_env()  # asegura el env en ESTE loop antes del await del handle
        result = await handle.result()
        stats = handle.stats()
        if stats is None:  # inalcanzable: stats() post-result siempre snapshota
            raise RuntimeError("el update terminó sin stats del engine")
        return result, stats

    return asyncio.run_coroutine_threadsafe(_consume(), default_env_loop()).result()


def refresh_blocking() -> RefreshReport:
    """Ejecuta un ciclo Δ del flow con lock de un solo proceso y devuelve su reporte (T8).

    Entrypoint del criterio 2 (spec-rag-engine §Semántica incremental) y de la
    tool `index_refresh` de Phase 2, que lo invoca y serializa este retorno
    TAL CUAL (spec-mcp-server §Tool `index_refresh`).

    * **Lock:** si OTRO proceso retiene `.tepochcalli/db/refresh.lock` NO se
      arranca update alguno y el reporte es cero con `locked=True` — ni una
      escritura (doble-write que ADR-002 §6 acepta como riesgo, cerrado aquí).
      Un lock file residual de un crash no retiene: ver `LOCK_RELPATH`.
    * **Cuenta honesta:** `indexed` sale del data plane (`index_file`
      `num_adds + num_reprocesses`, nunca el total) y `skipped = scanned -
      indexed`; la identidad `scanned == indexed + skipped` es por construcción
      y absorbe en `skipped` los fallos por fichero (no-UTF-8, TOCTOU) y los
      silencios del conector (symlink roto, directorio ilegible) — ver
      `models.RefreshReport`.
    * **Fallo por fichero:** aislado (engine + exception handler del lifespan);
      solo un `00-Resources/` roto —raíz ausente o no-listable— propaga
      excepción: eso SÍ es una instalación rota y debe ser ruidoso (F5).
    * `elapsed_ms` mide adquisición del candado + update con `time.monotonic()`.
    """
    start = time.monotonic()
    lock_fd = _acquire_refresh_lock(resolve_vault_root())
    if lock_fd is None:
        return RefreshReport(
            scanned=0,
            indexed=0,
            skipped=0,
            elapsed_ms=int((time.monotonic() - start) * 1000),
            locked=True,
        )
    try:
        tally, stats = _update_blocking_with_stats()
    finally:
        _release_refresh_lock(lock_fd)
    file_stats = stats.by_component.get(FILE_PROCESSOR)
    indexed = 0 if file_stats is None else file_stats.num_adds + file_stats.num_reprocesses
    return RefreshReport(
        scanned=tally.scanned,
        indexed=indexed,
        skipped=tally.scanned - indexed,
        elapsed_ms=int((time.monotonic() - start) * 1000),
        locked=False,
    )
