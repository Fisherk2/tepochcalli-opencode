"""Servidor MCP `tepochcalli-rag`: `MCPServer`, composition root y registro de las 4 tools (T1+T2).

Spike de anclaje fail-fast (tasks/plan.md §3) contra `mcp==2.3.0`, verificado
en la fuente INSTALADA (`venv/lib/python3.12/site-packages/mcp/`), no de
memoria:

* `FastMCP` → `MCPServer`: `mcp.server.fastmcp` ya no tiene API; existe solo
  como shim que lanza `ModuleNotFoundError` con mensaje de migración
  (`mcp/server/fastmcp.py`). La forma real es
  `from mcp.server.mcpserver import MCPServer`.
* El transporte se configura en `run()`: `MCPServer(...)` no acepta puerto ni
  transporte en el constructor; `server.run()` corre **stdio** por omisión
  (`def run(self, transport: Literal["stdio", "sse", "streamable-http"] = "stdio", ...)`).
* `ToolError` NO sirve para nuestro contrato: mete texto libre en `content`
  y ahora vive en `mcp.server.mcpserver.exceptions` (ya no en `mcp.types`).
  El contrato congelado exige `content[0].text` = JSON canónico
  `{error:{code,message,…}}` (spec-mcp-server §Manejo de errores), nunca
  texto libre ⇒ los handlers NO lanzan `ToolError`: construyen
  `CallToolResult` explícito (`mcp.types.CallToolResult`; en el wire el
  campo es `isError`). El SDK lo confirma en su fuente:
  `func_metadata.convert_result` devuelve intacto cualquier `CallToolResult`
  devuelto por el handler —también un handler `async`—, y anotar el handler
  `-> CallToolResult` anula el `outputSchema` estructurado (salida
  unstructured) — lo que nuestro JSON canónico necesita.
* **stdout es exclusivo del JSON-RPC.** El SDK v2 ya se protege: el
  transporte stdio RECLAMA fd 1 durante el servicio y desvía cualquier
  salida espuria (prints de bibliotecas) hacia stderr
  (`mcp/server/stdio.py`, issue #1933); aun así, la regla de la casa se
  mantiene: todo log propio va a stderr vía `logging`, jamás `print`.
* Los tipos `CallToolResult`/`TextContent` se importan de `mcp.types`
  (reexporta la distribución hermana `mcp_types==2.3.0`).

**Composition root (patrón T1, cerrado en T2/T3):** este es el ÚNICO módulo
del paquete que conoce el SDK, el flow con motor (`lancedb`, `cocoindex`) y la
config del vault — el test de arquitectura extendido lo exime de la regla de
dominio y afirma que `server` SÍ alcanza `lancedb`, igual que `adapters/` en
Phase 1. El wiring de `search` (T2/G1): `_vault_root` → `load_config` →
`_VaultSearchBackend` (lector `LanceDBChunkReader` + embedder de
`embedder.py`, perezosos para que `tools/list` y el arranque stdio no carguen
torch ni el modelo) → inyectado al handler `tools/search.py` como FACTORY
(`backend_factory`), para que el arranque quede BAJO `@errors.internal_guard`
— si el backend se construye aquí, antes de llamar, un fallo escapa al SDK con
texto libre (G1). El wiring de `index_refresh` (T3): tres seams perezosos —
`_refresh_once` (`refresh_blocking()` + `dataclasses.asdict`, la única zona
que serializa el `RefreshReport`), `_embedder_available` (costura `E_NO_EMBEDDER`
de `embedder.is_available`) y `_index_exists` — que el handler invoca bajo la
MISMA guarda (`rag_status`, T4, consume `_meta_seam`/`_vault_config`/
`_config_valid` de este mismo módulo). El wiring de `add_source` (T5): tres
seams — `_vault_root`, `_convert_seam` (markitdown EN PROCESO vía
`tepochcalli_mcp.convert`, import perezoso para no pagar su coste en
`tools/list`) y `_refresh_once` (el MISMO de T3). **Desviación del plan §5
respecta a `convert.py`:** el diagrama dibuja `TOOLS → CONV`, pero la puerta
de arquitectura (y la regla textual del mismo §5) impiden que `tools.*`
importe `markitdown`; la costura se inyecta AQUÍ desde el composition root —
el detalle y su rationale viven en el docstring de `tools/add_source.py`.
"""

from __future__ import annotations

import contextlib
import logging
import os
import tomllib
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Final

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult
from tepochcalli_flow import citation
from tepochcalli_flow.config import CONFIG_RELPATH, Config, load_config
from tepochcalli_flow.layout import DB_RELPATH, TABLE_NAME
from tepochcalli_flow.ports import ChunkReader, CitedChunk

if TYPE_CHECKING:
    from lancedb.table import AsyncTable

import tepochcalli_mcp.tools
from tepochcalli_mcp import __version__, budget, diagnostics, embedder, paths, summary
from tepochcalli_mcp.tools import add_source as add_source_handler
from tepochcalli_mcp.tools import convert_base64 as convert_base64_handler
from tepochcalli_mcp.tools import convert_document as convert_document_handler
from tepochcalli_mcp.tools import index_refresh as index_refresh_handler
from tepochcalli_mcp.tools import list_formats as list_formats_handler
from tepochcalli_mcp.tools import rag_status as rag_status_handler
from tepochcalli_mcp.tools import search as search_handler

logger = logging.getLogger("tepochcalli_mcp")

server = MCPServer(name="tepochcalli-rag", version=__version__)

CONTRACT_ROOT_ENV: Final = "TEPOCHCALLI_ROOT"
"""Nombre de la raíz del vault en el contrato MCP (`opencode.json` → `environment`).

Spec-mcp-server §Carga de configuración. El flow NO lo conoce: su nombre es
`TEPOCHCALLI_VAULT_ROOT` (Phase 1) y la traducción ocurre en `_vault_root`,
el composition root — un solo nombre para el vault en todo el sistema.
"""


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
        """
        return {str(row["model"]) for row in await self._select(["model"])}

    async def index_meta(self) -> rag_status_handler.IndexMeta:
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
                return rag_status_handler.IndexMeta(
                    rows=0, models=set(), last_refresh=None, db_size_bytes=size
                )
            total = await table.count_rows()
            rows: list[dict[str, object]] = (
                await table.query().select(["model", "indexed_at"]).to_list()
            )
        return rag_status_handler.IndexMeta(
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
        import lancedb  # composition root: el único sitio con el motor (decisión T2)

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

        El corte se construye con `_read_embedder` (composition root, T6/D59):
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


_backend_instance: _VaultSearchBackend | None = None


def _vault_root() -> Path:
    """Raíz del vault con la MISMA regla que el flow (`resolve_vault_root`).

    **Traducción T9 (aquí, en el composition root):** el contrato MCP nombra
    la raíz `TEPOCHCALLI_ROOT` (spec-mcp-server §Carga de configuración; la
    inyecta `obsidian-workspace/opencode.json`) y el flow resuelve con
    `TEPOCHCALLI_VAULT_ROOT` — un solo nombre para el vault, traducido en el
    ÚNICO módulo que conoce ambos lados (ADR-005). La env queda traducida en
    el proceso, de modo que `refresh_blocking()` (que llama
    `resolve_vault_root()` directo) ve el mismo vault sin conocer el nombre
    del contrato. `setdefault`: si el nombre del flow ya está (tests,
    `verify.py`), no se pisa.

    Revisión Phase 2 (eje 7, 2026-10-27): el retorno va `.resolve()` — la env
    (p. ej. `TEPOCHCALLI_ROOT: "."` de `opencode.json`) es RELATIVA al cwd del
    harness, y el cwd del proceso stdio NO tiene por qué ser el vault;
    resuelto, todo path/walk/written_to depende solo del filesystem, no del
    directorio de lanzamiento.

    Import perezoso de `tepochcalli_flow.app` — arrastra `cocoindex` y no
    debe frenar el arranque stdio ni `tools/list`.
    """
    from tepochcalli_flow.app import VAULT_ROOT_ENV, resolve_vault_root

    if (contract_root := os.environ.get(CONTRACT_ROOT_ENV)) is not None:
        os.environ.setdefault(VAULT_ROOT_ENV, contract_root)
    return resolve_vault_root().resolve()


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
    """Composition root del corte de LECTURA (T6/D59) — una sola implementación.

    Construye la op de cocoindex con el **path estable** del snapshot
    (`config.embedding_model_path`) y se la pasa a `embedder.build_read_cut`
    (que aplica la estrategia de provider y el dialecto de errores). El módulo
    `embedder` NO importa `cocoindex`: la frontera se cruza solo aquí, como con
    `lancedb`/`markitdown`.

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


def _backend() -> _VaultSearchBackend:
    """Backend del vault — cache CON invalidación por cambio de config (riesgo R2, CP-B).

    **Decisión R2 (documentada aquí, en `tests/unit/test_mcp_server_backend.py`
    y en el reporte T6):** `load_config` corre por CADA invocación (lectura de
    toml, µs — lo caro, el embedder, sigue perezoso dentro del lector) y si la
    config CAMBIÓ — swap de modelo en la misma sesión (ADR-008: `tepochcalli
    config embedder` + reindex sin reiniciar el server)— el backend se
    RECONSTRUYE con la config NUEVA. Así `search` y `rag_status` nombran
    siempre la MISMA config viva en una sesión, y el lector con el modelo del
    swap se construye en la primera búsqueda posterior. `Config.__eq__`
    compara las secciones parseadas, no `models_dir` (firma del dataclass): un
    cambio de raíz de vault no dispara rebuild. Como T2, la factory se invoca
    DENTRO del handler bajo `@errors.internal_guard` (G1).
    """
    global _backend_instance
    vault_root = _vault_root()
    config = load_config(vault_root)
    if _backend_instance is None or _backend_instance.config != config:
        _backend_instance = _VaultSearchBackend(vault_root, config)
    return _backend_instance


_last_refresh_roots_state: tuple[str, ...] = ()
"""Raíces de la última indexación EFECTIVA de la sesión (T8/D42) — estado en memoria.

`rag_status.index.last_refresh_roots` lo publica y NO se persiste: las raíces
viven solo en la invocación (ADR-010 §4.1), y el arranque del proceso las
deja vacías. Lo escribe `_refresh_once` al cerrar un refresh no bloqueado.
"""


def _refresh_once(directories: tuple[str, ...] | None = None) -> dict[str, object]:
    """Seam T3 + raíces T8 + traducción T6: ciclo Δ + `asdict` — único punto que serializa.

    `refresh_blocking(directories)` es síncrono y bloqueante: el handler lo
    corre con `asyncio.to_thread`; el candado vive DENTRO (un refresh
    bloqueado devuelve tres ceros con `locked: true` sin ejecutar update).
    `asdict` copia los campos EN SU ORDEN — el handler devuelve ese dict tal
    cual, sin recalcular.

    **Raíces (T8):** `None` ⇒ `Config.indexer_roots` (`INDEXER_DIR`, por omisión
    `00-Resources/`, D42); una tupla indexa esas raíces y el reporte las
    declara. Solo un refresh que EFECTIVAMENTE indexó anota
    `_last_refresh_roots_state` — un candado retenido no es una indexación.

    **Traducción T6 (aquí, en el composition root — dirección correcta flow→mcp):**
    `EmbeddingApiKeyMissingError` del flow (litellm sin `api_key_env`) ⇒
    `embedder.EmbedderAuthError` de dominio, que `index_refresh`/`add_source`
    responden como `E_API_AUTH`. `from None` corta la cadena: el log del guard
    nunca hereda texto del flow. Los rechazos de API que ocurren DENTRO del
    update (401 real, rate limit) escapan como excepciones de litellm ⇒
    `INTERNAL` con la política de redacción del flow — documentado en el
    reporte T6 como límite del camino de escritura.
    """
    global _last_refresh_roots_state
    from tepochcalli_flow.app import EmbeddingApiKeyMissingError, refresh_blocking

    try:
        report = asdict(refresh_blocking(directories))
    except EmbeddingApiKeyMissingError as exc:
        raise embedder.EmbedderAuthError(exc.api_key_env) from None
    if not report["locked"]:
        _last_refresh_roots_state = tuple(str(root) for root in report["roots"])
    return report


def _add_source_refresh() -> dict[str, object]:
    """Seam de refresh de `add_source`: raíces configuradas MÁS `00-Resources/`.

    `add_source` escribe SIEMPRE en `00-Resources/` (D9.1) y el target del flow
    reconcilia el conjunto DECLARADO de raíces (spec-rag-engine §Δ): un refresh
    sin esa raíz purgaría las filas del `.md` recién escrito. Orden preservado
    (primero las de `INDEXER_DIR`, luego la contractual si falta) y sin duplicar.
    """
    configured = load_config(_vault_root()).indexer_roots
    if citation.RESOURCES_DIR in configured:
        return _refresh_once(configured)
    return _refresh_once((*configured, citation.RESOURCES_DIR))


def _convert_seam(uri: str) -> str:
    """Seam T5: markitdown EN PROCESO (D-b) — markdown con frontmatter, import perezoso.

    El composition root es el ÚNICO punto que puede conocer `convert.py`
    (importa `markitdown`, raíz prohibida en `tools.*`): el handler recibe
    ESTA costura, no el módulo — desviación `TOOLS → CONV` documentada en
    `tools/add_source.py`. El import dentro de la función (patrón
    `_refresh_once`/`_vault_root`) mantiene `tools/list` y el arranque stdio
    libres del coste de markitdown.
    """
    from tepochcalli_mcp.convert import convert_source

    return convert_source(uri)


def _convert_local_seam(path: Path, *, source_uri: str) -> str:
    """Seam T9: markitdown EN PROCESO sobre un documento del vault, sin frontmatter."""
    from tepochcalli_mcp.convert import convert_local

    return convert_local(path, source_uri=source_uri)


def _convert_bytes_seam(
    data: bytes, *, filename: str | None, extension: str, source_uri: str
) -> str:
    """Seam T10: markitdown EN PROCESO sobre bytes en contexto (`BytesIO` + `StreamInfo`)."""
    from tepochcalli_mcp.convert import convert_bytes

    return convert_bytes(data, filename=filename, extension=extension, source_uri=source_uri)


def _embedder_available() -> bool:
    """Seam T3: costura `E_NO_EMBEDDER` vía `embedder.is_available` (torch perezoso).

    T6 sustituirá el cuerpo por la lectura real de `provider` (D15) sin tocar
    el handler — la dependencia ya apunta a la costura.
    """
    from tepochcalli_mcp.embedder import is_available

    return is_available(load_config(_vault_root()))


def _last_refresh_roots_seam() -> tuple[str, ...]:
    """Seam T8: raíces de la última indexación de la sesión (en memoria, no persistidas)."""
    return _last_refresh_roots_state


def _indexer_roots_seam() -> tuple[str, ...]:
    """Seam de raíces por omisión: `Config.indexer_roots` (`INDEXER_DIR` de `opencode.json`).

    Se lee del entorno en CADA llamada (mismo criterio que `_embedder_available`):
    cambiar `INDEXER_DIR` no exige reiniciar el server. `load_config` nunca
    lanza, y la validación de cada raíz sigue en el borde del handler.
    """
    return load_config(_vault_root()).indexer_roots


def _available_roots_seam() -> tuple[str, ...]:
    """Seam T8/D67: directorios indexables de primer nivel del vault (fuera los de punto)."""
    return paths.vault_dirs(_vault_root())


def _index_exists() -> bool:
    """Seam T3: ¿existe la DB tras el refresh? Solo el path, sin conexión."""
    return (_vault_root() / DB_RELPATH).exists()


def _vault_config() -> Config:
    """Seam T4: `load_config` del vault — invoked DENTRO del handler bajo la guarda (G1).

    `load_config` nunca lanza (archivo ausente = defaults canónicos; malformado
    = warning + defaults), así que lo único observable es la config resuelta.
    """
    return load_config(_vault_root())


def _meta_seam() -> Awaitable[rag_status_handler.IndexMeta]:
    """Seam T4: `IndexMeta` derivado — construye el backend perezoso BAJO la guarda."""
    return _backend().index_meta()


def _config_valid() -> bool:
    """Seam T4: validez del toml — SEMÁNTICA DECIDIDA y declarada en la tool (T4).

    `false` SOLO si `tepochcalli.toml` existe y no se pudo leer/parsear
    (malformado TOML o ilegible); AUSENTE ⇒ `true` — el fichero es opcional y
    los defaults canónicos son una config válida. «Existe» por sí solo no
    significa nada: el campo mide PARSEO, no existencia (`load_config` no
    puede señalárnoslo: nunca lanza). El parsing DUPLICADO aquí es
    deliberado: es la única forma de obtener la señal sin tocar el loader
    vedado de `flow/config.py`.

    `rag_status` combina esta señal con `_config_problems_seam`: `valid` es
    `parseo OK y problems vacío` (un `INDEXER_DIR` malo ⇒ `false`).
    """
    toml_path = _vault_root() / CONFIG_RELPATH
    try:
        tomllib.loads(toml_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return True
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError):
        return False
    return True


def _config_problems_seam() -> tuple[str, ...]:
    """Seam de diagnóstico: problemas de entorno/raíces visibles en la 1.ª llamada.

    Se recalcula por llamada (mismo criterio que `_indexer_roots_seam`):
    cambiar `INDEXER_DIR` no exige reiniciar el server.
    """
    vault_root = _vault_root()
    return diagnostics.config_problems(load_config(vault_root), vault_root)


def _unknown_env_seam() -> tuple[str, ...]:
    """Seam de diagnóstico: variables de entorno que parecen nuestras y no lo son."""
    return diagnostics.unknown_env(os.environ)


@server.tool()
async def search(
    query: str, top_k: int = budget.TOP_K_DEFAULT, path_filter: str | None = None
) -> CallToolResult:
    """Busca chunks citados en `00-Resources/` y devuelve los más relevantes.

    Cada resultado trae los 7 campos congelados `{text, source_path, heading,
    char_start, char_end, score, offsets_ref}` con offsets reproducibles
    (spec-mcp-server §search). `top_k` por omisión 5, tope efectivo 8;
    `path_filter` es un glob RELATIVO al vault (`..` o absoluto → error).
    """
    payload = await search_handler.search(
        query, top_k, path_filter, backend_factory=_backend, embedder_available=_embedder_available
    )
    return tepochcalli_mcp.tools.json_result(payload)


@server.tool()
async def index_refresh(directories: list[str] | None = None) -> CallToolResult:
    """Actualiza el índice de forma delta y reporta el ciclo (criterio 2).

    Devuelve `{scanned, indexed, skipped, elapsed_ms, locked, roots}`
    serializado TAL CUAL desde `RefreshReport` (Phase 1); idempotente: una
    segunda llamada sin cambios reporta `indexed: 0` (spec-mcp-server §Tool
    `index_refresh`). `directories` son las raíces a indexar, **recursivas** y
    relativas al vault (una raíz puede ser un fichero suelto); omitido ⇒
    las raíces de `INDEXER_DIR` (por omisión `["00-Resources"]`). Las raíces se
    validan ANTES de tocar el motor: una inexistente, de otro tipo o fuera del
    vault ⇒ `VALIDATION_ERROR` con `details.suggestions` y no se indexa NINGUNA
    (fail-fast atómico). Un directorio vacío no es error: `scanned: 0`.
    """
    payload = await index_refresh_handler.index_refresh(
        directories,
        vault_root=_vault_root,
        default_roots=_indexer_roots_seam,
        refresh=_refresh_once,
        embedder_available=_embedder_available,
        index_exists=_index_exists,
    )
    return tepochcalli_mcp.tools.json_result(payload)


@server.tool()
async def add_source(uri: str, subdir: str | None = None) -> CallToolResult:
    """Convierte una fuente externa (http(s)/file) a Markdown, la escribe citada y reindexa.

    Una sola llamada (Facade, plan §T5): validación en el borde (D16 —
    `file:` fuera del vault ⇒ `VALIDATION_ERROR`), conversión con markitdown
    EN PROCESO (D-b, costura `_convert_seam`), escritura atómica en
    `00-Resources/<subdir|_inbox>/` con frontmatter de trazabilidad
    (`source_uri`, `converted_at`) y ciclo Δ interno sobre las raíces
    configuradas MÁS `00-Resources/` (el destino se declara siempre: si no,
    el target purgaría el .md recién escrito).
    Fetch/convert fallido ⇒ `SOURCE_UNREACHABLE` con la guía de
    spec-markitdown; refresh bloqueado ⇒ `ENGINE_LOCKED` (el archivo sí
    quedó; ver `tools/add_source.py` para el detalle del `locked`).
    """
    payload = await add_source_handler.add_source(
        uri,
        subdir,
        vault_root=_vault_root,
        convert=_convert_seam,
        refresh=_add_source_refresh,
        embedder_available=_embedder_available,
    )
    return tepochcalli_mcp.tools.json_result(payload)


@server.tool()
async def convert_document(
    path: str, output_path: str | None = None, format: str | None = None
) -> CallToolResult:
    """Convierte un documento del vault a Markdown: escribe el .md y devuelve SOLO el resumen.

    Escribe el `.md` a disco y devuelve SOLO el resumen (5 claves: `written_to`,
    `bytes`, `chars`, `preview` — más `source_uri` y `truncated` si aplica): el
    cuerpo del documento NUNCA viaja por el wire (ADR-009/D36) — para leerlo,
    haz `read` del `written_to` o indexa y usa `search`. NO es el camino de
    indexación: para indexar usa `index_refresh` o `add_source`. Entrada y
    salida deben quedar dentro del vault (frontera B′): `..`, ruta absoluta
    externa o symlink que escapa ⇒ `VALIDATION_ERROR`; `path` inexistente o
    que es un directorio ⇒ `VALIDATION_ERROR`. `output_path` omitido ⇒
    `00-Resources/<slug>.md`. `format` fuerza la extensión del destino y hace
    de pista de tipo; una extensión fuera del catálogo ⇒ `VALIDATION_ERROR`
    con la lista. Destino existente ⇒ idempotente: mismos bytes devuelven el
    mismo resumen, bytes distintos ⇒ `VALIDATION_ERROR` (nunca se sobrescribe).
    Un documento sin capa de texto ⇒ `SOURCE_UNREACHABLE` con guía: este
    conversor no hace OCR.
    """
    payload = await convert_document_handler.convert_document(
        path, output_path, format, vault_root=_vault_root, convert=_convert_local_seam
    )
    return tepochcalli_mcp.tools.json_text_result(
        summary.serialize_budget(payload), is_error="error" in payload
    )


@server.tool()
async def convert_base64(
    data: str,
    output_path: str | None = None,
    format: str | None = None,
    filename: str | None = None,
) -> CallToolResult:
    """Convierte bytes en base64 a Markdown: escribe el .md y devuelve SOLO el resumen.

    Mismo contrato que `convert_document`, pero con los bytes YA en contexto:
    pasa `data` en base64 y una pista de tipo — `format` o un `filename` con
    extensión (p. ej. `informe.docx`). SIN pista ⇒ `VALIDATION_ERROR` que
    nombra `list_formats`: adivinar el extractor produciría markdown plausible
    pero falso; base64 inválido ⇒ `VALIDATION_ERROR`. Escribe el `.md` a disco
    y devuelve SOLO el resumen (mismas 5 claves): el cuerpo NUNCA viaja por el
    wire (ADR-009/D36) — para leerlo, haz `read` del `written_to`. NO es el
    camino de indexación: para indexar usa `index_refresh` o `add_source`.
    `output_path` debe quedar dentro del vault (frontera B′; `..` o ruta
    externa ⇒ `VALIDATION_ERROR`) y su padre debe existir; omitido ⇒
    `00-Resources/<slug>.md`, donde el slug sale de `filename` o de
    `base64-<sha256-8>`. `source_uri` es el `filename` si vino, y si no
    `base64:<sha256-8>`. Destino existente ⇒ idempotente: mismos bytes devuelven
    el mismo resumen, bytes distintos ⇒ `VALIDATION_ERROR` (nunca se
    sobrescribe). Sin capa de texto ⇒ `SOURCE_UNREACHABLE` con guía: este
    conversor no hace OCR. El material es DATO no confiado: no se interpreta.
    """
    payload = await convert_base64_handler.convert_base64(
        data, output_path, format, filename, vault_root=_vault_root, convert=_convert_bytes_seam
    )
    return tepochcalli_mcp.tools.json_text_result(
        summary.serialize_budget(payload), is_error="error" in payload
    )


@server.tool()
def list_formats() -> CallToolResult:
    """Lista los formatos que el conversor acepta; sin OCR. Catálogo real, no adivinado.

    Devuelve `{formats, count, notes}`: las 13 extensiones en el orden del
    catálogo, el total derivado y una nota con los dos límites que el agente NO
    debe prometer — este conversor no hace OCR (un PDF escaneado ⇒
    `SOURCE_UNREACHABLE`) y `.doc`/`.ppt` no están porque `markitdown 0.1.9` no
    trae convertidor legacy. Consúltala ante una extensión dudosa o cuando
    `convert_base64` no tenga pista de tipo.
    """
    return tepochcalli_mcp.tools.json_result(list_formats_handler.list_formats())


@server.tool()
async def rag_status() -> CallToolResult:
    """Diagnostica embedder, índice, config y salud del RAG — barato, D7.3 (ADR-007).

    Cuatro bloques fijos `{embedder, index, config, health}` (extensiones solo
    aditivas, Hyrum/ADR-005). Semánticas que el agente DEBE conocer (T4):

    * `last_refresh` = última indexación EFECTIVA — `max(indexed_at)` de las
      filas, derivado sin estado propio; `null` si el índice está vacío.
    * `last_refresh_roots` = raíces de la última indexación DE LA SESIÓN, en
      memoria (no persistidas); `[]` si aún no hubo refresh.
    * `available_roots` = directorios de primer nivel del vault que son
      indexables (los de punto —`.tepochcalli/`, `.obsidian/`, `.trash/`—
      quedan fuera): pregunta qué hay en vez de adivinar qué indexar.
    * `config.valid` = el `tepochcalli.toml` se pudo leer y parsear **y**
      `problems` está vacío; `false` si existe y está malformado o si hay
      problemas de entorno — ausente ⇒ `true` (fichero opcional, defaults
      canónicos; no es un chequeo de existencia).
    * `config.problems` = qué está mal en el entorno de la config (raíz
      `TEPOCHCALLI_ROOT`, cada raíz de `INDEXER_DIR`, `TEPOCHCALLI_TOP_K`),
      mensajes cortos, tope 3 — visible en la PRIMERA llamada, sin indexar.
    * `config.unknown_env` = variables que parecen nuestras y no lo son
      (`INDEXER_DRI`, `TEPOCHALLI_ROOT`…): una clave mal escrita no se ignora
      en silencio. Tope 3. Ninguno de los dos degrada `health`.
    * `mode`: `local` (peso en `.tepochcalli/models/`), `api` (LiteLLM:
      `provider` nombra el proveedor —hoy la clave `litellm` que la config
      puede expresar—, `model` su id) o `none` (T6/D15).
    * `health.reason` usa EXCLUSIVAMENTE la taxonomía `E_*` (o `null` en
      `ok`); ante cualquier `E_*`, llama esta tool y reporta el `fix_hint`
      exacto al usuario —nunca el error crudo— (regla del vault,
      specs/spec-agent-workflow.md).

    Coste <200 tokens por construcción (spec-mcp-server §Presupuesto): es la
    llamada que D7.3 exige ante cualquier error SIN penalizar la conversación.
    """
    payload = await rag_status_handler.rag_status(
        config_factory=_vault_config,
        index_meta=_meta_seam,
        config_valid=_config_valid,
        last_refresh_roots=_last_refresh_roots_seam,
        available_roots=_available_roots_seam,
        problems=_config_problems_seam,
        unknown_env=_unknown_env_seam,
    )
    return tepochcalli_mcp.tools.json_result(payload)
