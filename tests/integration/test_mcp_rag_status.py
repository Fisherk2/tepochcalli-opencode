"""T4: `rag_status` end-to-end — estado sano real, toml malformado y <200 tokens (plan §6).

Fuentes de verdad: tasks/todo.md T4 (3 estados + assert de tokens <200);
specs/spec-mcp-server.md §Tool `rag_status` (shape literal) + §Presupuesto;
la regla de la gotera T4-T10: **cero aserciones dependientes del tiempo**.

Decisiones de test, documentadas:

* **Server como SUBPROCESO por stdio** con `TEPOCHCALLI_VAULT_ROOT` propio
  (mismo patrón que `test_mcp_server`/`test_mcp_refresh`): el environment
  global de cocoindex no admite dos vaults en el proceso padre, y la tool se
  ejercita como la ve el harness.
* **Canario de cero red** = `tests/support/nonet/sitecustomize.py` por
  `PYTHONPATH` en el hijo + `HF_HUB_OFFLINE=1` cuando hay modelo: `rag_status`
  NI SICHIERA carga el embedder (es la tool barata), y el `index_refresh` del
  estado sano corre offline tras el warm (ventana única de descarga del
  fixture, patrón de la casa).
* **Cada test usa SU vault** — son independientes entre sí y del orden de
  corrida: el `valid: true` del estado sano (toml AUSENTE) no puede contaminar
  el `valid: false` del malformado.
* Los estados `none` y `modelo distinto` NO son alcanzables por el server
  real (el loader no admite `none` — D15/T6; el vault real está indexado con
  el modelo de config): viven en el unit
  `tests/unit/test_mcp_rag_status_handler.py` con seams, como pide el AC.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from mcp import ClientSession
from support.mcp_server import running_server, server_env, warm_model
from tepochcalli_flow import citation
from tepochcalli_flow.config import DEFAULT_EMBEDDING_MODEL
from tepochcalli_mcp import budget

TOML_RELPATH = ".tepochcalli/config/tepochcalli.toml"
"""Literal de `config.path` (spec §rag_status) — relativo, con `/` en todo SO."""

ALPHA = (
    "# Alpha — nota para el estado sano\n\n"
    "Dos párrafos de prosa para que el ciclo delta del hijo tenga chunks que\n"
    "indexar antes de pedir el diagnóstico del RAG.\n\n"
    "## Detalle\n\n"
    "Segundo párrafo con métricas, cohorte y seguimiento de referencia.\n"
)
BETA = (
    "# Beta — segunda nota\n\n"
    "Fichero estable del vault T4: completa el índice mínimo del estado sano.\n"
)


async def _call(session: ClientSession, tool: str, arguments: dict[str, object]) -> dict:
    """Tool call por stdio: payload JSON parseado, con `is_error` como precondición."""
    result = await session.call_tool(tool, arguments)
    assert not result.is_error, f"{tool} falló: {result.content[0].text}"
    return json.loads(result.content[0].text)


def _assert_tokens_under_200(payload: dict) -> None:
    """D7.3: la tool es barata por diseño — techo de §Presupuesto de tokens."""
    cost = budget.estimate_tokens(json.dumps(payload, ensure_ascii=False))
    assert cost < 200, cost


# --- estado 1: sano (vault real indexado por la propia tool) ---------------------------


def test_sane_install_reports_the_full_block_contract(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Vault real (2 md) → `index_refresh` de la tool → `rag_status` sano, <200 tokens."""
    vault = tmp_path_factory.mktemp("vault-t4-ok")
    resources = vault / citation.RESOURCES_DIR
    resources.mkdir(parents=True)
    (resources / "alpha.md").write_text(ALPHA, encoding="utf-8")
    (resources / "beta.md").write_text(BETA, encoding="utf-8")

    models_link = warm_model(vault)

    env = server_env(vault, models_link)

    async def go() -> dict:
        async with running_server(env) as session:
            refresh = await _call(session, "index_refresh", {})
            assert refresh["indexed"] >= 1, "el estado sano necesita un índice REAL"
            return await _call(session, "rag_status", {})

    payload = asyncio.run(go())

    assert list(payload) == ["embedder", "index", "config", "health"]
    assert list(payload["embedder"]) == ["mode", "model", "dims", "provider"]
    assert list(payload["index"]) == [
        "rows",
        "model_matches_config",
        "last_refresh",
        "db_size_bytes",
    ]
    assert list(payload["config"]) == ["path", "valid"]
    assert list(payload["health"]) == ["state", "reason", "fix_hint"]

    embedder_block = payload["embedder"]
    assert embedder_block == {
        "mode": "local",
        "model": DEFAULT_EMBEDDING_MODEL,
        "dims": 384,
        "provider": None,
    }
    assert payload["health"] == {"state": "ok", "reason": None, "fix_hint": None}

    index_block = payload["index"]
    assert index_block["rows"] >= 1
    assert index_block["model_matches_config"] is True
    last_refresh = index_block["last_refresh"]
    assert isinstance(last_refresh, str) and last_refresh, "derivado de indexed_at real"
    assert index_block["db_size_bytes"] > 0, "el walk de .tepochcalli/db/ encuentra la DB"

    config_block = payload["config"]
    assert config_block["path"] == TOML_RELPATH, "relativo y con / en todo SO (spec literal)"
    assert config_block["valid"] is True, "toml AUSENTE ⇒ true: es opcional (decisión T4)"

    _assert_tokens_under_200(payload)


# --- estado 2: toml malformado (informativo, no degrada la salud) ----------------------


def test_malformed_toml_reports_valid_false_without_degrading_health(tmp_path: Path) -> None:
    """`valid: false` SOLO exige toml presente-y-roto; la salud sigue `ok` (decisión T4).

    Vault propio SIN índice ni modelo: `rag_status` no carga embedder ni
    escribe nada — la llamada más barata del contrato, con el canario `nonet`.
    """
    toml_path = tmp_path / TOML_RELPATH
    toml_path.parent.mkdir(parents=True)
    toml_path.write_text("[embedding\nmodel = 'roto", encoding="utf-8")  # TOML malformado
    env = server_env(tmp_path)

    try:

        async def go() -> dict:
            async with running_server(env) as session:
                return await _call(session, "rag_status", {})

        payload = asyncio.run(go())
    finally:
        toml_path.unlink(missing_ok=True)

    assert payload["config"] == {"path": TOML_RELPATH, "valid": False}
    assert payload["embedder"]["mode"] == "local", "el loader cae a defaults con warning"
    assert payload["health"] == {"state": "ok", "reason": None, "fix_hint": None}, (
        "ningún E_* cubre un toml roto: valid es informativo, no degrada"
    )
    assert payload["index"] == {
        "rows": 0,
        "model_matches_config": True,
        "last_refresh": None,
        "db_size_bytes": 0,
    }
    _assert_tokens_under_200(payload)
