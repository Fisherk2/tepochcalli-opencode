"""Entrada del flow CocoIndex: N raíces del vault → chunks citados con embedding en LanceDB.

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

**Alcance de provider (spec-embeddings §Embeddings + D15/T6):** Strategy en el
lifespan vía `_build_embedder` — `local` ⇒ `SentenceTransformerEmbedder`
pineado; `litellm` ⇒ `LiteLLMEmbedder(model, api_key=…)` con la clave leída de
`api_key_env` (sin clave ⇒ error tipado ANTES de cualquier llamada, con un
mensaje que nombra solo la variable); `none` (D15) ⇒ `EmbedderNotConfiguredError` — el MCP
responde `E_NO_EMBEDDER` ANTES de llegar aquí con sus costuras `is_available`.
«No se construye a medias» sigue siendo la regla: cada provider o se cablea
completo o lanza su error tipado.

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
import logging
import os
import time
from collections.abc import AsyncIterator, Sequence
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
from . import progress, source
from .citation import normalize_source_path
from .layout import DB_RELPATH, ENGINE_STATE_RELPATH, LOCK_RELPATH, TABLE_NAME  # noqa: F401  # re-export: tests y wiring del flow consumen los nombres vía app
from .model_store import ensure_local_model
from .models import EMBEDDER, LANCE_DB, ROOT_KEY, ChunkRow, RefreshReport
from .parsers import DocumentChunk, chunk_document, extract_text
from .refresh_lock import acquire_refresh_lock as _acquire_refresh_lock
from .refresh_lock import release_refresh_lock as _release_refresh_lock
from .roots import DEFAULT_ROOTS

logger = logging.getLogger(__name__)

VAULT_ROOT_ENV: Final = "TEPOCHCALLI_VAULT_ROOT"
"""Override de la raíz del vault (pruebas/vaults alternativos); default: la del payload."""

FILE_PROCESSOR: Final = "index_file"
"""Nombre del componente por fichero: de SUS stats sale `indexed` (data plane).

Nunca `stats.total`: la traversa `build_flow` reporta `reprocess=1` por diseño
(E2) y contaminaría la idempotencia (hallazgo del T8; spec-rag-engine §Semántica
incremental).
"""

_active_roots: tuple[str, ...] = DEFAULT_ROOTS
"""Raíces de la pasada en curso (T2, ADR-010 §4.1).

Las raíces son un ARGUMENTO de `refresh_blocking`, pero el `coco.App` de
`cocoindex==1.0.25` fija los argumentos de su main function al construirse.
El lock del refresh serializa las pasadas y `build_flow` se re-ejecuta en cada
update (E2), así que el valor se fija antes del update y se restaura después:
sin estado que sobreviva a la llamada.
"""


class EmbedderNotConfiguredError(NotImplementedError):
    """`provider = "none"` (D15/T6): sin embedder que construir — estado VÁLIDO de config.

    El MCP nunca debe llegar aquí con un config sano: sus costuras
    (`embedder.is_available` en `search`/`index_refresh`) responden
    `E_NO_EMBEDDER` ANTES de invocar el flow (precedencia D7.3). Este error
    es la defensa para llamadas DIRECTAS al flow (verify/CLI/tests): nada se
    construye a medias.
    """


class EmbeddingApiKeyMissingError(ValueError):
    """`provider = "litellm"` sin clave en NINGUNA de las dos fuentes (T6).

    Se detecta ANTES de cualquier llamada a la API (chequeo local, cero red:
    `EmbeddingConfig.resolve_api_key()`). El mensaje nombra SOLO el nombre de la
    variable y el campo del toml — nunca un valor de clave (plan §9 riesgo
    crítico: «el traceback de litellm filtra la clave»; docs/SECURITY.md) — y el
    nombre viaja además en el atributo `api_key_env`, que el composition root
    del MCP (`server._refresh_once`) traduce a `E_API_AUTH` sin parsear mensajes.
    """

    def __init__(self, api_key_env: str) -> None:
        """`api_key_env` es SOLO el nombre de la variable (jamás un valor)."""
        super().__init__(
            f"falta la clave del embedder: ni la variable de entorno {api_key_env!r} "
            "ni `api_key` en [embedding] de tepochcalli.toml la definen — "
            "define la clave para provider='litellm'"
        )
        self.api_key_env = api_key_env


def resolve_vault_root() -> Path:
    """Resuelve la raíz del vault (absoluta): env `TEPOCHCALLI_VAULT_ROOT` o la del payload.

    La derivación por `__file__` es estable porque el paquete es editable desde
    `<vault>/.tepochcalli/flow/` (mismo layout que instala el wizard, D2). Se
    resuelve SIEMPRE: `source_path` y el walk deben ser independientes del cwd
    desde el que se lanzó el server (misma regla que el composition root del MCP).
    """
    override = os.environ.get(VAULT_ROOT_ENV)
    if override:
        return Path(override).resolve()
    return Path(__file__).resolve().parents[3]


def _build_embedder(config: flow_config.Config) -> object:
    """Strategy/Factory de provider (T6, plan §6): la ÚNICA puerta de construcción.

    * `local` ⇒ materializa el snapshot `<models>/<slug>@<sha>/` (idempotente;
      descarga con `revision` SOLO si falta) y construye
      `SentenceTransformerEmbedder(<path>, device)` — la op acepta «name or
      path» (firma instalada `ops/sentence_transformers.py:59-65`). Ambos
      caminos (write y read) usan el MISMO path ⇒ mismo binario (D59).
    * `litellm` ⇒ `LiteLLMEmbedder(model, api_key=…)` con la clave de
      `EmbeddingConfig.resolve_api_key()` (env var `api_key_env` si existe;
      si no, la `api_key` literal del toml gitignored que escribe el wizard —
      misma precedencia que el reader del MCP, una sola implementación). Fuente
      instalada `cocoindex==1.0.25/ops/litellm.py`: los kwargs pasan «to every
      ``litellm.aembedding`` call (e.g., ``api_key``…)» y el constructor es
      INERTE — sin clave ⇒ error tipado local, jamás una llamada con la pata
      caída; la dim se descubre con un embed real dentro de
      `__coco_vector_schema__`, durante el update.
    * `none` (D15) ⇒ `EmbedderNotConfiguredError`: nada a medias.

    `LiteLLMEmbedder` se importa perezosamente: `litellm` pesa y solo lo paga
    quien configura el proveedor de API.
    """
    provider = config.embedding.provider
    if provider == "litellm":
        from cocoindex.ops.litellm import LiteLLMEmbedder

        api_key = config.embedding.resolve_api_key()
        if api_key is None:
            raise EmbeddingApiKeyMissingError(config.embedding.api_key_env)
        return LiteLLMEmbedder(config.embedding.model, api_key=api_key)
    if provider == "none":
        raise EmbedderNotConfiguredError(
            "provider='none' (D15): sin embedder configurado — el MCP lo reporta "
            "como E_NO_EMBEDDER ANTES de llegar aquí"
        )
    model_path = ensure_local_model(config)
    return SentenceTransformerEmbedder(str(model_path), device=config.embedding.device)


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
    """Provee conexión LanceDB y embedder al Environment (§Proposed Solution; E1/T6).

    Orden obligatorio: resolver config → `apply_model_cache_env()` →
    construir el embedder POR PROVIDER con `_build_embedder` (Strategy T6:
    `local` | `litellm`; `none` ⇒ error tipado D15). El cache de modelo se
    fija ANTES de instanciar embedder alguno (T3/E1 — irrelevante para
    litellm e inocuo, pero la regla no se relaja). El exception handler
    global (T8) asegura que un fallo por fichero quede aislado y localizado en
    el log sin abortar nunca el delta (F5).
    """
    vault_root = resolve_vault_root()
    config = flow_config.load_config(vault_root)
    config.apply_model_cache_env()
    if "COCOINDEX_DB" not in os.environ:
        builder.settings.db_path = vault_root / ENGINE_STATE_RELPATH
    builder.provide(LANCE_DB, await lancedb.connect_async(str(vault_root / DB_RELPATH)))
    builder.provide(ROOT_KEY, vault_root)
    builder.provide(EMBEDDER, _build_embedder(config))
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
) -> None:
    """Particiona un archivo con su cita derivada y fan-outea sus chunks (T5/T6).

    Memoizable por contenido: un archivo inmutable no se re-parsea ni se
    re-embebe (semántica Δ de spec-rag-engine §Semántica incremental); la clave
    de memo depende de los ARGUMENTOS —el `localfs.File`, cuyo `base_dir=ROOT_KEY`
    la ancla a la ruta RELATIVA al vault (D62), y el `config`—, nunca de la ruta
    absoluta del vault. La cita es ese mismo relativo al vault (D41),
    normalizado con `citation.normalize_source_path` — nunca a mano. El texto
    sale de `parsers.extract_text`, el ÚNICO decodificador: md/txt en UTF-8
    estricto (BOM incluido, byte a byte equivalente a la lectura directa) y
    los binarios vía markitdown, cuyos offsets F1 se miden sobre el texto
    extraído (D50, `offsets_ref="extract"`). Un extractor que falla lanza
    `ExtractionError`: el componente de ESTE fichero falla aislado, queda
    contado en `skipped` y NUNCA escribe una fila vacía (OM-11).
    """
    file_path = Path(os.fspath(file.file_path))
    # Re-chequeo TOCTOU classify→read: el archivo pudo crecer (o conmutarse) tras
    # el classifier; superarlo aquí falla el componente de ESTE fichero (aislado,
    # el pase continúa) en vez de indexar >100MB. ANTES de extraer el texto:
    # markitdown sobre un documento que creció costaría más antes de fallar igual.
    if (size := os.stat(file_path).st_size) > source.DEFAULT_MAX_FILE_BYTES:
        raise ValueError(
            f"{file_path}: creció a {size} bytes tras el classify "
            f"(> {source.DEFAULT_MAX_FILE_BYTES}); cambió durante el pase"
        )
    # `extract_text` está decorado con @coco.fn (D58): `as_async` lo ejecuta en
    # un hilo (SyncFunction.as_async, cocoindex/_internal/function.py:952-954)
    # sin bloquear el loop del environment y SIN salto a hilo manual (D60).
    relative = file.file_path.path.as_posix()
    progress.extraction_started(relative)
    extraction_start = time.monotonic()
    text = await extract_text.as_async(file_path)
    progress.extraction_finished(relative, int((time.monotonic() - extraction_start) * 1000))
    chunks = chunk_document(text, normalize_source_path(relative), config=config)
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
    """Monta target gestionado, walk multi-raíz, fan-out por archivo e índices (T2/T6).

    El trío F2 queda completo aquí: `mount_table_target` (gestionado),
    `coco.mount_each` (ruta de componente por archivo) y —dentro de
    `write_chunk`— `IdGenerator.next_id(chunk.text)`.

    Las raíces de la pasada viven en `_active_roots` (argumento de
    `refresh_blocking`); cada archivo se monta con una clave vault-relativa
    (`file.file_path.as_posix()`), así que dos raíces con el mismo nombre de
    fichero no colisionan en `mount_each`.

    Devuelve el `_ScanTally` del pase (T8): `refresh_blocking` lo lee del
    resultado de la main function para armar `RefreshReport.scanned`. La
    traversa se re-ejecuta SIEMPRE (reprocess=1 por diseño, E2), así que el
    tally refleja el pase actual aunque nada haya cambiado.
    """
    vault_root = resolve_vault_root()
    config = flow_config.load_config(vault_root)
    table = await lancedb.mount_table_target(
        LANCE_DB,
        TABLE_NAME,
        table_schema=await lancedb.TableSchema.from_class(ChunkRow, primary_key=["id"]),
    )
    items, scanned = await _indexable_items(vault_root, _active_roots)
    await coco.mount_each(index_file, items, table, config)
    table.declare_vector_index(column="embedding")
    table.declare_fts_index(column="text")
    return _ScanTally(scanned=scanned)


async def _indexable_items(
    vault_root: Path, roots: Sequence[str | Path] | None
) -> tuple[list[tuple[str, localfs.File]], int]:
    """Walk multi-raíz + clasificación F5; SOLO indexables + total visitado (T2).

    `source.scan_items` valida y deduplica las raíces (D44/D46/D47) y decide qué
    archivo entra: symlinks que escapan del vault (frontera de confianza),
    ilegibles, oversized y rutas fuera de la whitelist nunca montan componente
    — se loguean como descarte sin abortar el delta (§Fuentes).

    Cada `localfs.File` se reconstruye con `localfs.FilePath(ruta_relativa,
    base_dir=ROOT_KEY)`: la clave de memo es estable aunque el vault se mueva
    (D62) y el CWD jamás entra en ella. La clave de `mount_each` es la misma
    ruta relativa al vault.

    Devuelve `(items, scanned)`: además de los candidatos entregados (indexables
    y descartes con motivo), `scanned` cuenta las entradas que el conector traga
    en silencio y `source.unvisited_skips` recupera — symlink roto y directorio
    ilegible—, de modo que la identidad `scanned == indexed + skipped` del
    `RefreshReport` no mienta (hallazgo #5 de CP-B; spec-mcp-server §`index_refresh`).
    """
    walked, scanned = await source.scan_items(vault_root, roots)
    items: list[tuple[str, localfs.File]] = []
    for entry in walked:
        if isinstance(entry, source.SourceEntry):
            relative = entry.path.relative_to(vault_root)
            file = localfs.File(localfs.FilePath(relative, base_dir=ROOT_KEY))
            items.append((relative.as_posix(), file))
        else:
            logger.warning("Descartado %s: %s — %s", entry.source_path, entry.reason, entry.detail)
    return items, scanned


app = coco.App(coco.AppConfig(name="tepochcalli"), build_flow)
"""Entrypoint v1: `app.update_blocking()` o `cocoindex update <archivo>` (sin `setup`)."""


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


def _roots_for(directories: Sequence[str] | None) -> tuple[str, ...]:
    """Raíces de la pasada: `None` ⇒ `Config.indexer_roots` (ADR-010 §4.1, D32).

    El default sale de `INDEXER_DIR` (`opencode.json` → entorno del proceso),
    por omisión `("00-Resources",)`. Se relee en cada pasada: cambiar la
    variable no exige reiniciar el proceso.
    """
    if directories is None:
        return flow_config.load_config(resolve_vault_root()).indexer_roots
    return tuple(directories)


def refresh_blocking(directories: Sequence[str] | None = None) -> RefreshReport:
    """Ejecuta un ciclo Δ del flow con lock de un solo proceso y devuelve su reporte (T2/T8).

    Entrypoint del criterio 2 (spec-rag-engine §Semántica incremental) y de la
    tool `index_refresh` de Phase 2, que lo invoca y serializa este retorno
    TAL CUAL (spec-mcp-server §Tool `index_refresh`).

    * **Raíces (ADR-010 §4.1):** `directories=None` indexa `Config.indexer_roots`
      (`INDEXER_DIR`, por omisión `00-Resources/`); una
      secuencia indexa esas raíces **recursivamente** y el reporte las declara
      en `roots`. Viven solo en la llamada (D32): no se escriben en
      `tepochcalli.toml` ni sobreviven al proceso. La validación de borde
      (existencia, tipo, `suggestions`) es de T7; aquí `source.normalize_roots`
      falla ruidosamente antes de caminar (D65).
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
      solo una raíz rota —ausente o no-listable— propaga excepción: eso SÍ es
      una instalación rota y debe ser ruidoso (F5).
    * `elapsed_ms` mide adquisición del candado + update con `time.monotonic()`.
    """
    roots = _roots_for(directories)
    start = time.monotonic()
    progress.refresh_started(roots)
    lock_fd = _acquire_refresh_lock(resolve_vault_root())
    if lock_fd is None:
        progress.refresh_locked()
        return RefreshReport(
            scanned=0,
            indexed=0,
            skipped=0,
            elapsed_ms=int((time.monotonic() - start) * 1000),
            locked=True,
            roots=roots,
        )
    global _active_roots
    previous_roots = _active_roots
    _active_roots = roots
    try:
        tally, stats = _update_blocking_with_stats()
    finally:
        _active_roots = previous_roots
        _release_refresh_lock(lock_fd)
    file_stats = stats.by_component.get(FILE_PROCESSOR)
    indexed = 0 if file_stats is None else file_stats.num_adds + file_stats.num_reprocesses
    report = RefreshReport(
        scanned=tally.scanned,
        indexed=indexed,
        skipped=tally.scanned - indexed,
        elapsed_ms=int((time.monotonic() - start) * 1000),
        locked=False,
        roots=roots,
    )
    progress.refresh_finished(report)
    return report
