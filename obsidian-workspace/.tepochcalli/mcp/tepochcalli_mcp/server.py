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

**Composition root (patrón T1, cerrado en T2):** este es el ÚNICO módulo del
paquete que conoce el SDK, el flow con motor (`lancedb`, `cocoindex`) y la
config del vault — el test de arquitectura extendido lo exime de la regla de
dominio y afirma que `server` SÍ alcanza `lancedb`, igual que `adapters/` en
Phase 1. El wiring de `search` (T2): `resolve_vault_root` → `load_config` →
`_VaultSearchBackend` (lector `LanceDBChunkReader` + embedder de `embedder.py`,
perezosos para que `tools/list` y el arranque stdio no carguen torch ni el
modelo) → inyectado al handler `tools/search.py`, que solo ve el puerto.
Los otros 3 handlers siguen con el placeholder de la forma exacta de §5 hasta
T3/T4/T5.
"""

from __future__ import annotations

import logging
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult
from tepochcalli_flow import citation
from tepochcalli_flow.config import Config, load_config
from tepochcalli_flow.layout import DB_RELPATH, TABLE_NAME
from tepochcalli_flow.ports import ChunkReader, CitedChunk

import tepochcalli_mcp.tools
from tepochcalli_mcp import __version__, budget
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

        Comprueba la existencia de la DB ANTES de conectar — `connect_async`
        crearía el directorio, rompiendo la solo-lectura. `open_table` sobre una
        tabla ausente LANZA `ValueError` (sonda empírica T2 contra
        `lancedb==0.40.0`): se traduce en conjunto vacío, que el handler vuelve
        `INDEX_EMPTY` — la guía `index_refresh()` también reconstruye una DB
        ilegible, que es el otro caso que verify.py trata como «a medio indexar».
        """
        import lancedb  # composition root: el único sitio con el motor (decisión T2)

        db_uri = self._vault_root / DB_RELPATH
        if not db_uri.exists():
            return set()
        try:
            db = await lancedb.connect_async(str(db_uri))
            try:
                table = await db.open_table(TABLE_NAME)
                rows = await table.query().select(["model"]).to_list()
            finally:
                db.close()  # type: ignore[no-untyped-call]  # close() sin anotar en lancedb 0.40.0
        except ValueError:
            return set()  # tabla `chunks` ausente o DB ilegible: índice no consultable
        return {str(row["model"]) for row in rows}

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


def _backend() -> _VaultSearchBackend:
    """Backend del vault, perezoso y cacheado por proceso (una sola carga de modelo).

    Resuelve la raíz del vault con la MISMA regla que el flow
    (`resolve_vault_root`: env `TEPOCHCALLI_VAULT_ROOT` o la del payload); T9
    traducirá aquí `TEPOCHCALLI_ROOT` (el nombre del contrato MCP) a ese env.
    """
    global _backend_instance
    if _backend_instance is None:
        from tepochcalli_flow.app import resolve_vault_root

        vault_root = resolve_vault_root()
        _backend_instance = _VaultSearchBackend(vault_root, load_config(vault_root))
    return _backend_instance


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
    payload = await search_handler.search(query, top_k, path_filter, backend=_backend())
    return tepochcalli_mcp.tools.json_result(payload)


@server.tool()
def index_refresh() -> CallToolResult:
    """Actualiza el índice de forma delta y reporta el ciclo (criterio 2).

    Devuelve `{scanned, indexed, skipped, elapsed_ms, locked}`; idempotente:
    una segunda llamada sin cambios reporta `indexed: 0` (spec-mcp-server).
    Placeholder de la forma exacta de §5 hasta T3.
    """
    return tepochcalli_mcp.tools.json_result(
        {
            "scanned": 0,
            "indexed": 0,
            "skipped": 0,
            "elapsed_ms": 0,
            "locked": False,
        },
    )


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
def rag_status() -> CallToolResult:
    """Diagnostica embedder, índice, config y salud del RAG (barato, D7.3).

    Cuatro bloques fijos `{embedder, index, config, health}`; ante cualquier
    `E_*` el agente debe llamar esta tool y reportar el `fix_hint`
    (spec-mcp-server §rag_status, ADR-007). Placeholder de la forma exacta de
    §5 hasta T4.
    """
    return tepochcalli_mcp.tools.json_result(
        {
            "embedder": {"mode": "none", "model": None, "dims": None, "provider": None},
            "index": {
                "rows": 0,
                "model_matches_config": True,
                "last_refresh": None,
                "db_size_bytes": 0,
            },
            "config": {"path": ".tepochcalli/config/tepochcalli.toml", "valid": True},
            "health": {
                "state": "degraded",
                "reason": "E_NO_EMBEDDER",
                "fix_hint": "Ejecuta `tepochcalli config embedder` y luego `index_refresh()`",
            },
        },
    )
