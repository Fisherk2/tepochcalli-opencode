"""Servidor MCP `tepochcalli-rag`: `MCPServer` + registro de las 4 tools (T1).

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
  devuelto por el handler, y anotar el handler `-> CallToolResult` anula el
  `outputSchema` estructurado (salida unstructured) — lo que nuestro JSON
  canónico necesita.
* **stdout es exclusivo del JSON-RPC.** El SDK v2 ya se protege: el
  transporte stdio RECLAMA fd 1 durante el servicio y desvía cualquier
  salida espuria (prints de bibliotecas) hacia stderr
  (`mcp/server/stdio.py`, issue #1933); aun así, la regla de la casa se
  mantiene: todo log propio va a stderr vía `logging`, jamás `print`.
* Los tipos `CallToolResult`/`TextContent` se importan de `mcp.types`
  (reexporta la distribución hermana `mcp_types==2.3.0`).

Los 4 handlers devuelven hoy el PLACEHOLDER con la forma EXACTA de
tasks/plan.md §5 «Contrato de datos» (sin lógica): el contrato queda
congelado antes de que T2-T5 lo implementen. Composition root (patrón T1):
este es el único módulo que conoce el SDK.
"""

from __future__ import annotations

import json
import logging

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, TextContent

from tepochcalli_mcp import __version__

logger = logging.getLogger("tepochcalli_mcp")

server = MCPServer(name="tepochcalli-rag", version=__version__)


def _json_result(payload: dict[str, object]) -> CallToolResult:
    """Empaqueta un payload como JSON canónico en `content[0].text` (contrato §5)."""
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))],
    )


@server.tool()
def search(query: str, top_k: int = 5, path_filter: str | None = None) -> CallToolResult:
    """Busca chunks citados en `00-Resources/` y devuelve los más relevantes.

    Cada resultado trae los 7 campos congelados `{text, source_path, heading,
    char_start, char_end, score, offsets_ref}` con offsets reproducibles
    (spec-mcp-server §search). `top_k` por omisión 5, tope efectivo 8;
    `path_filter` es un glob RELATIVO al vault (`..` o absoluto → error).
    """
    return _json_result(
        {
            "query": query,
            "took_ms": 0,
            "truncated": False,
            "results": [],
        },
    )


@server.tool()
def index_refresh() -> CallToolResult:
    """Actualiza el índice de forma delta y reporta el ciclo (criterio 2).

    Devuelve `{scanned, indexed, skipped, elapsed_ms, locked}`; idempotente:
    una segunda llamada sin cambios reporta `indexed: 0` (spec-mcp-server).
    """
    return _json_result(
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
    """
    return _json_result(
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
    (spec-mcp-server §rag_status, ADR-007).
    """
    return _json_result(
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
