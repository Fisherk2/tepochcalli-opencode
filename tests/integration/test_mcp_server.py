"""Contrato T1 del server MCP `tepochcalli-rag`: stdio, tools/list y placeholders.

Actualizado en T2: `search` ya no es placeholder.

Spike de anclaje fail-fast (tasks/plan.md §3, T1): valida contra el SDK
cliente REAL (mcp==2.3.0) que el proceso `python -m tepochcalli_mcp`
1) arranca por stdio y responde `initialize`,
2) declara exactamente las 4 tools del contrato congelado con sus
   input schemas,
3) emite SOLO JSON-RPC en stdout (nunca texto libre), y
4) responde cada tool con la forma EXACTA de tasks/plan.md §5.

**T2:** `search` dejó de ser placeholder — implementa el camino real y contra
un vault SIN índice responde `INDEX_EMPTY` (canónico, no vacío); su shape de
éxito vive en `tests/integration/test_mcp_search.py`. T3-T5 llenaron las
otras 3 tools. El contract test D7.3 completo vive desde T8 en
`tests/e2e/test_mcp_contract.py`; este fichero sigue anclando el esqueleto
(arranque stdio, `tools/list` y stdout exclusivo de JSON-RPC).
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import tepochcalli_mcp
from mcp import ClientSession
from model_cache import link_model_cache, offline_env, resolve_model_cache
from support.mcp_server import running_server
from tepochcalli_flow import citation

# Las 4 tools congeladas del contrato (spec-mcp-server §API / plan §5), con
# las claves de su input schema y las requeridas — el orden de las
# propiedades lo fija la firma de cada tool.
_EXPECTED_INPUT_KEYS: dict[str, list[str]] = {
    "search": ["query", "top_k", "path_filter"],
    "index_refresh": ["directories"],
    "add_source": ["uri", "subdir"],
    "rag_status": [],
    "convert_document": ["path", "output_path", "format"],
    "convert_base64": ["data", "output_path", "format", "filename"],
    "list_formats": [],
}
_EXPECTED_REQUIRED: dict[str, list[str]] = {
    "search": ["query"],
    "index_refresh": [],
    "add_source": ["uri"],
    "rag_status": [],
    "convert_document": ["path"],
    "convert_base64": ["data"],
    "list_formats": [],
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
async def _running_server(vault_root: Path | None = None) -> AsyncIterator[ClientSession]:
    """Levanta `python -m tepochcalli_mcp` por stdio y devuelve una sesión cliente.

    Adaptador de una línea sobre `support.mcp_server.running_server` (R4/T8):
    esta única variante monta la env desde `vault_root` (None ⇒ heredar la del
    padre), como siempre. `vault_root` fija `TEPOCHCALLI_VAULT_ROOT` en el
    proceso hijo: T2 lo usa para que `search` responda `INDEX_EMPTY` de forma
    DETERMINISTA (un vault temporal sin `.tepochcalli/db/`), sin depender del
    índice local del repo. A propósito SIN canario `nonet`: aquí no se indexa
    ni se busca, solo se arranca el proceso y se leen shapes.
    """
    env = None if vault_root is None else {**os.environ, "TEPOCHCALLI_VAULT_ROOT": str(vault_root)}
    async with running_server(env) as session:
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


def test_top_k_default_follows_the_environment_without_touching_the_schema() -> None:
    """`TEPOCHCALLI_TOP_K=7` ⇒ `search.top_k` con `default: 7`; firma y required intactos.

    El default sale de `budget.TOP_K_DEFAULT` (derivado del entorno en import):
    la firma de la tool no cambia, solo su valor por omisión.
    """
    env = {**os.environ, "TEPOCHCALLI_TOP_K": "7"}

    async def go() -> dict[str, object]:
        async with running_server(env) as session:
            search = next(t for t in (await session.list_tools()).tools if t.name == "search")
            schema = search.input_schema
            properties = schema.get("properties", {})
            return {
                "default": properties["top_k"]["default"],
                "properties": list(properties),
                "required": schema.get("required", []),
            }

    listed = asyncio.run(go())

    assert listed == {
        "default": 7,
        "properties": ["query", "top_k", "path_filter"],
        "required": ["query"],
    }


def test_stdout_carries_only_jsonrpc_frames() -> None:
    """Cada línea de stdout del proceso parsea como JSON-RPC (AC T1: logs a stderr).

    Secuencia cruda por stdin (sin el cliente del SDK, que oculta el
    transporte): `initialize` + `notifications/initialized` + `tools/list`.
    **stdin se mantiene ABIERTO hasta leer las dos respuestas** y solo entonces
    se cierra para que el server termine: cerrarlo de inmediato tras escribir
    raza con el flush de la segunda respuesta — el transporte stdio del SDK
    cancela su `stdout_writer` al salir del task group al recibir EOF
    (`mcp/server/stdio.py`) y la respuesta de `tools/list` se pierde. Sonda T2:
    con escritura+cierre atómicos el test parpadea 1 de cada 3 corridas; un
    cliente real mantiene stdio abierto mientras espera respuestas. Un watchdog
    de 60 s mata el proceso para que `readline` no pueda colgarse.
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
    proc = subprocess.Popen(
        [sys.executable, "-m", "tepochcalli_mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    watchdog = threading.Timer(60.0, proc.kill)
    watchdog.start()
    frames: list[dict[str, object]] = []
    try:
        assert proc.stdin is not None and proc.stdout is not None
        proc.stdin.write("\n".join(json.dumps(r) for r in requests) + "\n")
        proc.stdin.flush()
        while len(frames) < 2:
            line = proc.stdout.readline()
            if not line:
                break
            if line.strip():
                frames.append(json.loads(line))
        proc.stdin.close()
        proc.wait(timeout=30)
    finally:
        watchdog.cancel()
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    assert proc.returncode == 0, proc.stderr.read() if proc.stderr else ""
    assert frames, "el server no emitió nada por stdout"
    for frame in frames:
        assert frame["jsonrpc"] == "2.0", frame
    ids = {frame.get("id") for frame in frames}
    assert {1, 2} <= ids, f"faltan respuestas para initialize/tools/list: {ids}"


def test_each_tool_returns_placeholder_with_exact_contract_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cada tool responde la forma EXACTA de §5 (claves y orden); dos ya son reales.

    `search` (T2) e `index_refresh` (T3) se invocan contra un vault temporal
    REAL pero vacío: `search` responde `INDEX_EMPTY` canónico (`is_error=true`,
    JSON en `content[0].text`) y `index_refresh` ejecuta el ciclo Δ de Phase 1
    —con `00-Resources/` presente y el modelo en cache (symlink + offline,
    patrón de fixtures)— y devuelve el reporte honesto `(0,0,0)`. El refresh
    materializa el embedder por CONSTRUCCIÓN (dims del esquema, aun sin
    ficheros), por eso el test fija el cache antes de arrancar el server.
    La forma de ÉXITO de `search` la pin `test_mcp_search.py` sobre un vault
    indexado y la del journey completo `test_mcp_refresh.py`; `add_source`
    (real desde T5) usa un `file:` DENTRO del vault temporal —la forma la
    pinan también `test_mcp_add_source.py`— y `rag_status` (T4) los cuatro
    bloques; ningún paso de este test toca la red.
    """
    (tmp_path / citation.RESOURCES_DIR).mkdir()
    cache = resolve_model_cache()
    link_model_cache(tmp_path, cache)
    for key, value in offline_env(cache).items():
        monkeypatch.setenv(key, value)

    async def go() -> dict[str, list[str]]:
        payloads: dict[str, list[str]] = {}
        async with _running_server(tmp_path) as session:
            result = await session.call_tool("search", {"query": "pregunta de prueba"})
            assert result.is_error
            search = json.loads(result.content[0].text)
            assert search["error"]["code"] == "INDEX_EMPTY"
            payloads["search"] = list(search)

            result = await session.call_tool("index_refresh", {})
            assert not result.is_error, result.content[0].text
            refresh = json.loads(result.content[0].text)
            # Vault sin indexables: el ciclo Δ es honesto — cero cuentas, sin candado.
            assert (refresh["scanned"], refresh["indexed"], refresh["skipped"]) == (0, 0, 0)
            assert refresh["locked"] is False
            payloads["index_refresh"] = list(refresh)

            staging = tmp_path / "staging.md"
            staging.write_text(
                "# Staging T5\n\nFichero minimo para ejercitar add_source sin red.\n",
                encoding="utf-8",
            )
            result = await session.call_tool("add_source", {"uri": staging.as_uri()})
            assert not result.is_error, result.content[0].text
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
                "last_refresh_roots",
                "available_roots",
            ]
            assert list(status["config"]) == ["path", "valid", "problems", "unknown_env"]
            assert list(status["health"]) == ["state", "reason", "fix_hint"]
            payloads["rag_status"] = list(status)
        return payloads

    shapes = asyncio.run(go())
    # Orden exacto de claves por tool (tasks/plan.md §5 «Contrato de datos»).
    assert shapes["search"] == ["error"]  # T2 real: INDEX_EMPTY sobre vault sin índice
    assert shapes["index_refresh"] == [
        "scanned",
        "indexed",
        "skipped",
        "elapsed_ms",
        "locked",
        "roots",
    ]
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
