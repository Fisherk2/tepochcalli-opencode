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
MISMA guarda. `add_source` y `rag_status` siguen con el placeholder de la
forma exacta de §5 — T5 y T4 respectivamente.
"""

from __future__ import annotations

import logging
import tomllib
from collections.abc import Awaitable
from dataclasses import asdict
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult
from tepochcalli_flow import citation
from tepochcalli_flow.config import CONFIG_RELPATH, Config, load_config
from tepochcalli_flow.layout import DB_RELPATH, TABLE_NAME
from tepochcalli_flow.ports import ChunkReader, CitedChunk

import tepochcalli_mcp.tools
from tepochcalli_mcp import __version__, budget
from tepochcalli_mcp.tools import index_refresh as index_refresh_handler
from tepochcalli_mcp.tools import rag_status as rag_status_handler
from tepochcalli_mcp.tools import search as search_handler

logger = logging.getLogger("tepochcalli_mcp")

server = MCPServer(name="tepochcalli-rag", version=__version__)


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
    def expected_model(self) -> str:
        """Modelo configurado — el MISMO id que las filas guardan en `model` (ADR-006)."""
        return citation.model_id(self._config)

    async def index_models(self) -> set[str]:
        """Conjunto de `model` de las filas: vacío ⇒ índice inexistente (`INDEX_EMPTY`).

        Misma costura `_select` que usa `rag_status` (T4): la consulta NO se
        reimplementa — un solo punto con el borde de solo lectura documentado
        allí (DB ausente sin conectar; tabla ilegible ⇒ `ValueError` de
        lancedb ⇒ sin filas).
        """
        rows = await self._select(["model"])
        return {str(row["model"]) for row in rows}

    async def index_meta(self) -> rag_status_handler.IndexMeta:
        """DTO de estado del índice para `rag_status` (T4) — derivado, sin estado nuevo.

        UNA proyección de 2 columnas (`model` + `indexed_at`); de ahí salen
        `rows`, `models` y `last_refresh = max(indexed_at)` (ISO-8601 UTC con
        offset fijo ⇒ orden lexicográfico = cronológico). `db_size_bytes` =
        walk de TODO `<vault>/.tepochcalli/db/` — la spec dice `db/`, no solo
        el `.lance`. shortcut: con ~100k filas reconsiderar el scan de
        `indexed_at` (plan §9 riesgo «rag_status leyendo el índice completo»);
        la proyección ya es de 2 columnas cortas y el AC es ≤10k notas.
        """
        rows = await self._select(["model", "indexed_at"])
        # `.tepochcalli/db/` ENTERO (spec §rag_status dice `db/`, no solo `.lance`).
        db_root = self._vault_root / DB_RELPATH.parent
        size = (
            sum(path.stat().st_size for path in db_root.rglob("*") if path.is_file())
            if db_root.is_dir()
            else 0
        )
        return rag_status_handler.IndexMeta(
            rows=len(rows),
            models={str(row["model"]) for row in rows},
            last_refresh=max((str(row["indexed_at"]) for row in rows), default=None),
            db_size_bytes=size,
        )

    async def _select(self, columns: list[str]) -> list[dict[str, object]]:
        """Proyección de columnas de `chunks` — costura compartida search/rag_status (T2/T4).

        Solo lectura con el MISMO borde ya probado en T2: DB ausente ⇒ sin
        filas y SIN conectar (`connect_async` crearía el directorio); tabla
        ausente/ilegible ⇒ `ValueError` de `lancedb==0.40.0` (sonda T2) ⇒ sin
        filas. `rag_status` distingue «índice inexistente» por `rows == 0` y
        `models == ∅`, sin necesidad del motivo exacto.
        """
        import lancedb  # composition root: el único sitio con el motor (decisión T2)

        db_uri = self._vault_root / DB_RELPATH
        if not db_uri.exists():
            return []
        try:
            db = await lancedb.connect_async(str(db_uri))
            try:
                table = await db.open_table(TABLE_NAME)
                rows: list[dict[str, object]] = await table.query().select(columns).to_list()
            finally:
                db.close()  # type: ignore[no-untyped-call]  # close() sin anotar en lancedb 0.40.0
        except ValueError:
            return []
        return rows

    async def cited_chunks(
        self, query: str, top_k: int, path_filter: str | None
    ) -> list[CitedChunk]:
        """Búsqueda por el puerto `ChunkReader` — el adaptador vectoriza la query (T2)."""
        if self._reader is None:
            from tepochcalli_flow.adapters.lancedb_reader import LanceDBChunkReader

            from tepochcalli_mcp.embedder import build_embedder

            self._config.apply_model_cache_env()
            self._reader = LanceDBChunkReader(
                self._vault_root / DB_RELPATH,
                embed=build_embedder(self._config),
            )
        return await self._reader.search(query, top_k, path_filter)


_backend_instance: _VaultSearchBackend | None = None


def _vault_root() -> Path:
    """Raíz del vault con la MISMA regla que el flow (`resolve_vault_root`).

    Env `TEPOCHCALLI_VAULT_ROOT` o la del payload; T9 traducirá aquí
    `TEPOCHCALLI_ROOT` (el nombre del contrato MCP) a ese env. Import perezoso
    de `tepochcalli_flow.app` — arrastra `cocoindex` y no debe frenar el
    arranque stdio ni `tools/list`.
    """
    from tepochcalli_flow.app import resolve_vault_root

    return resolve_vault_root()


def _backend() -> _VaultSearchBackend:
    """Backend del vault, perezoso y cacheado por proceso (una sola carga de modelo).

    Se pasa al handler como FACTORY —no construida fuera—: el handler lo
    invoca bajo `@errors.internal_guard` (G1), de modo que resolver vault y
    config también queda cubierto por `INTERNAL` canónico.
    """
    global _backend_instance
    if _backend_instance is None:
        vault_root = _vault_root()
        _backend_instance = _VaultSearchBackend(vault_root, load_config(vault_root))
    return _backend_instance


def _refresh_once() -> dict[str, object]:
    """Seam T3: ciclo Δ de Phase 1 + `dataclasses.asdict` — único punto que serializa.

    `refresh_blocking()` es síncrono y bloqueante: el handler lo corre con
    `asyncio.to_thread`; el candado vive DENTRO (un refresh bloqueado devuelve
    tres ceros con `locked: true` sin ejecutar update). `asdict` copia los
    campos EN SU ORDEN — el handler devuelve ese dict tal cual, sin recalcular.
    """
    from tepochcalli_flow.app import refresh_blocking

    return asdict(refresh_blocking())


def _embedder_available() -> bool:
    """Seam T3: costura `E_NO_EMBEDDER` vía `embedder.is_available` (torch perezoso).

    T6 sustituirá el cuerpo por la lectura real de `provider` (D15) sin tocar
    el handler — la dependencia ya apunta a la costura.
    """
    from tepochcalli_mcp.embedder import is_available

    return is_available(load_config(_vault_root()))


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
    """
    toml_path = _vault_root() / CONFIG_RELPATH
    try:
        tomllib.loads(toml_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return True
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError):
        return False
    return True


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
    payload = await search_handler.search(query, top_k, path_filter, backend_factory=_backend)
    return tepochcalli_mcp.tools.json_result(payload)


@server.tool()
async def index_refresh() -> CallToolResult:
    """Actualiza el índice de forma delta y reporta el ciclo (criterio 2).

    Devuelve `{scanned, indexed, skipped, elapsed_ms, locked}` serializado TAL
    CUAL desde `RefreshReport` (Phase 1); idempotente: una segunda llamada sin
    cambios reporta `indexed: 0` (spec-mcp-server §Tool `index_refresh`).
    """
    payload = await index_refresh_handler.index_refresh(
        refresh=_refresh_once,
        embedder_available=_embedder_available,
        index_exists=_index_exists,
    )
    return tepochcalli_mcp.tools.json_result(payload)


@server.tool()
def add_source(uri: str, subdir: str | None = None) -> CallToolResult:
    """Convierte una fuente externa (http(s)/file) a Markdown y la reindexa.

    Escribe siempre dentro de `00-Resources/<subdir|_inbox>/` con frontmatter
    de trazabilidad, luego ejecuta el ciclo de `index_refresh` internamente
    (spec-mcp-server §add_source; `file:` fuera del vault se rechaza, D16).
    Placeholder de la forma exacta de §5 hasta T5.
    """
    return tepochcalli_mcp.tools.json_result(
        {
            "ok": True,
            "written_to": "",
            "indexed": {"scanned": 0, "indexed": 0, "skipped": 0, "elapsed_ms": 0},
        },
    )


@server.tool()
async def rag_status() -> CallToolResult:
    """Diagnostica embedder, índice, config y salud del RAG — barato, D7.3 (ADR-007).

    Cuatro bloques fijos `{embedder, index, config, health}` (extensiones solo
    aditivas, Hyrum/ADR-005). Semánticas que el agente DEBE conocer (T4):

    * `last_refresh` = última indexación EFECTIVA — `max(indexed_at)` de las
      filas, derivado sin estado propio; `null` si el índice está vacío.
    * `config.valid` = el `tepochcalli.toml` se pudo leer y parsear; `false`
      SOLO si existe y está malformado — ausente ⇒ `true` (fichero opcional,
      defaults canónicos; no es un chequeo de existencia).
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
    )
    return tepochcalli_mcp.tools.json_result(payload)
