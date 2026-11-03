"""T6/D59: snapshot ausente ⇒ `E_MODEL_INVALID` y CERO red (read path puro).

Fuentes de verdad: tasks/todo.md → T6 AC (d) — el read path NUNCA materializa
ni descarga; si `<models>/<slug>@<sha>/` no existe responde `E_MODEL_INVALID`
con la guía de `tepochcalli config embedder`.

El hijo MCP corre con dos candados independientes: `HF_HUB_OFFLINE=1` con un
cache HF **vacío** (no hay modelo que cargar sin descargar) y un `sitecustomize`
propio que REGISTRA y bloquea cualquier `connect` IPv4/IPv6. Así el test
distingue «error correcto sin red» de «error por intentar red»: el log del
canario debe quedar ausente.

El índice se crea a mano (una tabla `chunks` con `model`): el gate de modelo
pasa y el flujo llega al corte de la query, que es donde debe fallar sin red.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from support.mcp_server import running_server, wire_payload
from tepochcalli_flow.config import DEFAULT_EMBEDDING_MODEL, MODEL_REVISION, model_slug
from tepochcalli_flow.layout import DB_RELPATH, TABLE_NAME

_CANARY = """
import os
import pathlib
import socket

_real_connect = socket.socket.connect


def _guard(self, address, *args, **kwargs):
    pathlib.Path(os.environ["NONET_LOG"]).write_text(f"connect {address!r}", encoding="utf-8")
    raise OSError(f"canario nonet: salida de red prohibida hacia {address!r}")


socket.socket.connect = _guard
"""


def test_missing_local_snapshot_returns_e_model_invalid_with_zero_network(
    tmp_path: Path,
) -> None:
    """Sin snapshot: `E_MODEL_INVALID`, guía de reconfiguración y ningún directorio creado."""
    vault = tmp_path / "vault"
    (vault / ".tepochcalli" / "db").mkdir(parents=True)
    _create_model_only_table(vault)
    stable = (
        vault
        / ".tepochcalli"
        / "models"
        / f"{model_slug(DEFAULT_EMBEDDING_MODEL)}@{MODEL_REVISION}"
    )
    assert not stable.exists()

    canary_dir = tmp_path / "canary"
    canary_dir.mkdir()
    (canary_dir / "sitecustomize.py").write_text(_CANARY, encoding="utf-8")
    nonet_log = tmp_path / "nonet.log"
    empty_hf = tmp_path / "empty-hf"
    env = {
        **os.environ,
        "TEPOCHCALLI_VAULT_ROOT": str(vault),
        "HF_HOME": str(empty_hf),
        "SENTENCE_TRANSFORMERS_HOME": str(empty_hf),
        "HF_HUB_OFFLINE": "1",
        "PYTHONPATH": str(canary_dir),
        "NONET_LOG": str(nonet_log),
    }
    env.pop("COCOINDEX_DB", None)

    async def _search() -> dict[str, object]:
        async with running_server(env) as session:
            result = await session.call_tool("search", {"query": "citas con offsets"})
            return wire_payload(result)

    payload = asyncio.run(_search())

    error = payload["error"]
    assert error["code"] == "E_MODEL_INVALID", error  # type: ignore[index]
    assert "config embedder" in error["fix_hint"]  # type: ignore[index]
    assert not stable.exists(), "el read path no materializa ni descarga (D59)"
    assert not nonet_log.exists(), "el read path no debe intentar red (ni para el snapshot)"


def _create_model_only_table(vault: Path) -> None:
    """Crea `chunks` con la columna `model` (basta para el gate de modelo de `search`)."""
    import lancedb

    async def _create() -> None:
        connection = await lancedb.connect_async(str(vault / DB_RELPATH))
        try:
            await connection.create_table(TABLE_NAME, data=[{"model": DEFAULT_EMBEDDING_MODEL}])
        finally:
            connection.close()

    asyncio.run(_create())
