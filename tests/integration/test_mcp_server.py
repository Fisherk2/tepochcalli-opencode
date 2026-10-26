"""Contrato T1 del server MCP `tepochcalli-rag`: stdio, tools/list y placeholders.

Spike de anclaje fail-fast (tasks/plan.md §3, T1): valida contra el SDK
cliente REAL (mcp==2.3.0) que el proceso `python -m tepochcalli_mcp`
1) arranca por stdio y responde `initialize`,
2) declara exactamente las 4 tools del contrato congelado con sus
   input schemas,
3) emite SOLO JSON-RPC en stdout (nunca texto libre), y
4) responde cada tool con el placeholder de la forma EXACTA de
   tasks/plan.md §5 «Contrato de datos» (sin lógica todavía).

T8 añadirá después `tests/e2e/test_mcp_contract.py`; este fichero solo ancla
el esqueleto de T1.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import tepochcalli_mcp
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Las 4 tools congeladas del contrato (spec-mcp-server §API / plan §5), con
# las claves de su input schema y las requeridas — el orden de las
# propiedades lo fija la firma de cada tool.
_EXPECTED_INPUT_KEYS: dict[str, list[str]] = {
    "search": ["query", "top_k", "path_filter"],
    "index_refresh": [],
    "add_source": ["uri", "subdir"],
    "rag_status": [],
}
_EXPECTED_REQUIRED: dict[str, list[str]] = {
    "search": ["query"],
    "index_refresh": [],
    "add_source": ["uri"],
    "rag_status": [],
}


def test_tepochcalli_mcp_imports_and_exposes_version() -> None:
    """`tepochcalli_mcp` importa y expone `__version__` no vacío (patrón Phase 1)."""
    version = tepochcalli_mcp.__version__
    assert isinstance(version, str)
    assert version


def test_mcp_sdk_resolves_to_site_packages_without_shadowing() -> None:
    """`import mcp` resuelve al SDK, no al directorio `mcp/` del proyecto (AC T1).

    El editable install mete rutas en `sys.path`; si alguna permitiera
    resolver el nombre top-level `mcp` al contenedor del paquete, el SDK se
    rompería en silencio. El AC exige comprobar los tres imports.
    """
    import mcp
    import tepochcalli_flow  # noqa: F401  (tercer import del AC anti-shadowing)

    mcp_file = str(mcp.__file__).replace("\\", "/")
    assert "site-packages/mcp/" in mcp_file, f"shadowing: mcp resuelve a {mcp_file}"


@asynccontextmanager
async def _running_server() -> AsyncIterator[ClientSession]:
    """Levanta `python -m tepochcalli_mcp` por stdio y devuelve una sesión cliente."""
    params = StdioServerParameters(command=sys.executable, args=["-m", "tepochcalli_mcp"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def test_tools_list_returns_exactly_four_tools_with_expected_schemas() -> None:
    """`tools/list` devuelve exactamente las 4 tools con sus input schemas."""

    async def go() -> list[dict[str, object]]:
        async with _running_server() as session:
            tools = (await session.list_tools()).tools
            return [
                {
                    "name": t.name,
                    "required": t.input_schema.get("required", []),
                    "properties": list(t.input_schema.get("properties", {}).keys()),
                    "top_k_default": t.input_schema.get("properties", {})
                    .get("top_k", {})
                    .get("default"),
                    "path_filter_default": t.input_schema.get("properties", {})
                    .get("path_filter", {})
                    .get("default"),
                    "output_schema": t.output_schema,
                }
                for t in tools
            ]

    listed = asyncio.run(go())
    assert sorted(t["name"] for t in listed) == sorted(_EXPECTED_INPUT_KEYS)
    for tool in listed:
        name = str(tool["name"])
        assert tool["properties"] == _EXPECTED_INPUT_KEYS[name], name
        assert tool["required"] == _EXPECTED_REQUIRED[name], name
        # El contrato fija top_k=5 y path_filter=None por omisión (plan §5).
        if name == "search":
            assert tool["top_k_default"] == 5
            assert tool["path_filter_default"] is None
        # Los handlers devuelven CallToolResult explícito => sin outputSchema
        # (mcp 2.3.0: `-> CallToolResult` se trata como salida unstructured).
        assert tool["output_schema"] is None, name


def test_stdout_carries_only_jsonrpc_frames() -> None:
    """Cada línea de stdout del proceso parsea como JSON-RPC (AC T1: logs a stderr).

    Secuencia cruda por stdin (sin el cliente del SDK, que oculta el
    transporte): `initialize` + `notifications/initialized` + `tools/list`,
    y stdin cerrado para que el server termine.
    """
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "t1-spike", "version": "0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    proc = subprocess.run(
        [sys.executable, "-m", "tepochcalli_mcp"],
        input="\n".join(json.dumps(r) for r in requests) + "\n",
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    assert lines, "el server no emitió nada por stdout"
    for line in lines:
        frame = json.loads(line)
        assert frame["jsonrpc"] == "2.0", frame
    ids = {frame.get("id") for frame in (json.loads(line) for line in lines)}
    assert {1, 2} <= ids, f"faltan respuestas para initialize/tools/list: {ids}"


def test_each_tool_returns_placeholder_with_exact_contract_shape() -> None:
    """Cada tool responde YA el placeholder con la forma EXACTA de §5 (claves y orden)."""

    async def go() -> dict[str, list[str]]:
        payloads: dict[str, list[str]] = {}
        async with _running_server() as session:
            result = await session.call_tool("search", {"query": "pregunta de prueba"})
            assert not result.is_error
            search = json.loads(result.content[0].text)
            assert search["query"] == "pregunta de prueba"
            assert search["truncated"] is False
            assert search["results"] == []
            payloads["search"] = list(search)

            result = await session.call_tool("index_refresh", {})
            assert not result.is_error
            refresh = json.loads(result.content[0].text)
            payloads["index_refresh"] = list(refresh)

            result = await session.call_tool("add_source", {"uri": "https://example.org/paper"})
            assert not result.is_error
            add = json.loads(result.content[0].text)
            assert add["ok"] is True
            assert list(add["indexed"]) == ["scanned", "indexed", "skipped", "elapsed_ms"]
            payloads["add_source"] = list(add)

            result = await session.call_tool("rag_status", {})
            assert not result.is_error
            status = json.loads(result.content[0].text)
            # Orden exacto también dentro de cada bloque (plan §5).
            assert list(status["embedder"]) == ["mode", "model", "dims", "provider"]
            assert list(status["index"]) == [
                "rows",
                "model_matches_config",
                "last_refresh",
                "db_size_bytes",
            ]
            assert list(status["config"]) == ["path", "valid"]
            assert list(status["health"]) == ["state", "reason", "fix_hint"]
            payloads["rag_status"] = list(status)
        return payloads

    shapes = asyncio.run(go())
    # Orden exacto de claves por tool (tasks/plan.md §5 «Contrato de datos»).
    assert shapes["search"] == ["query", "took_ms", "truncated", "results"]
    assert shapes["index_refresh"] == ["scanned", "indexed", "skipped", "elapsed_ms", "locked"]
    assert shapes["add_source"] == ["ok", "written_to", "indexed"]
    assert shapes["rag_status"] == ["embedder", "index", "config", "health"]


def test_mcp_package_layout_matches_packaging_map() -> None:
    """El paquete instalado editable vive en `mcp/tepochcalli_mcp/` (corrección §pyproject).

    `package-dir` mapea `tepochcalli_mcp` -> `mcp/tepochcalli_mcp` de forma
    verbatim (spike T1, setuptools): el layout en disco y el mapa deben
    coincidir para que `uv sync` y el build sigan reproducibles.
    """
    init = Path(tepochcalli_mcp.__file__)
    assert init.parent.name == "tepochcalli_mcp"
    assert init.parent.parent.name == "mcp"
