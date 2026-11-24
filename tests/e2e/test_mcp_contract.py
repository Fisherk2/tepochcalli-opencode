"""T8: contract tests D7.3 — el contrato de las 4 tools AFIRMADO EN EL WIRE (plan §5/§6).

Fuentes de verdad (el test se escribe contra LA SPEC, no contra la implementación):

* specs/spec-mcp-server.md §API / Interface Design (las 4 tools y sus
  ejemplos), §Manejo de errores («isError + payload JSON canónico, nunca
  texto libre»), §Códigos de error estructurados (los 5 `E_*` con
  `{error:{code,message,fix_hint}}`), §Presupuesto (`rag_status` <200).
* tasks/plan.md §5 «Contrato de datos» (claves y orden EXACTOS) +
  «Taxonomía de errores» + §6 T8 AC (incluido CP-D).
* tasks/todo.md → T8 AC + deuda D6-5 + decisiones ya tomadas (F-T7-1).

Decisiones de test, documentadas a propósito:

* **Proceso REAL `python -m tepochcalli_mcp` por stdio con el cliente del
  SDK** (patrón T1): el contrato se gradúa donde el harness lo ve —
  `content[0].text`, `is_error`, `structured_content` — no sobre el handler
  invocado en proceso. Cada test lanza SU proceso con su
  `TEPOCHCALLI_VAULT_ROOT`: el environment global de cocoindex no admite dos
  vaults en el mismo proceso (sonda T9) y los escenarios con config PROPIA
  (degradada, litellm sin clave, modelo ajeno, cache vacío) no pueden
  contaminarse entre sí ni del vault compartido.
* **`structured_content is None` se afirma, no se asume** (hallazgo H6 del
  spike T1, verificado en la fuente del SDK v2): los handlers están anotados
  `-> CallToolResult`, el SDK trata eso como salida *unstructured*, anula el
  `outputSchema` y deja `structured_content = None` **también en éxito**.
  Lo coherente con el shape es ese `None`: el contrato vive SOLO en
  `content[0].text`. El porqué vive en `support.mcp_server.wire_payload`.
* **`last_refresh` sin normalizar**: Phase 1 escribe
  `datetime.now(UTC).isoformat()` ⇒ `"+00:00"`, mientras el ejemplo de la
  spec muestra `"Z"`. El contrato congela el CAMPO, no el sufijo — mismo
  instante ISO-8601. El test aserta «ISO-8601 parseable con offset UTC» y
  deja constancia de la divergencia (decisión del lead 2026-10-26: NO
  código cosmético de normalización).
* **Los 5 `E_*` en el wire con escenarios REALES** (config `none`,
  litellm sin clave, modelo distinto, cache vacío offline, modelo no
  materializable): su precedencia y sus constructores ya están testeados en
  unit (`test_mcp_e_dialect.py`, `test_mcp_errors.py`) — aquí se gradúa el
  MISMO dialecto atravesando el proceso por stdio. D6-5 se paga en
  `test_api_auth_travels_the_wire_from_search…` (el contract test por
  código que su RED aislada nunca llegó a observar).
* **Cero red, cero LLM**: todos los hijos corren con el canario
  `tests/support/nonet/sitecustomize.py` — cualquier `connect` AF_INET lanza
  `OSError`, la tool respondería `INTERNAL` y todo test de éxito fallaría
  solo (auto-exigente). Una llamada LLM por API ES una conexión saliente:
  UN guard cubre ambos AC.
* **Ninguna aserción depende del reloj** (regla anti-flake de la gotera T3):
  aquí SOLO se miden formas y tokens (`budget.estimate_tokens`); la latencia
  vive en `tests/benchmarks/bench_search.py`, jamás en la suite de
  corrección. Presupuesto de `search`: no se repite el gate ≤1600 de T7 (y
  NO se pone un assert de ≤1600 sobre el JSON literal entero: mandaría la
  fórmula de la spec, decisión F-T7-1 ya tomada).
"""

from __future__ import annotations

import asyncio
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from mcp.types import CallToolResult
from support.mcp_server import (
    ADD_SOURCE_FIELDS,
    ADD_SOURCE_INDEXED_FIELDS,
    RAG_STATUS_BLOCKS,
    RAG_STATUS_INNER_KEYS,
    REFRESH_FIELDS,
    SEARCH_RESULT_FIELDS,
    SEARCH_TOP_LEVEL_FIELDS,
    index_vault,
    running_server,
    server_env,
    wire_payload,
)
from tepochcalli_flow.config import (
    DEFAULT_API_KEY_ENV,
    DEFAULT_EMBEDDING_MODEL,
    MODEL_REVISION,
    model_slug,
)
from tepochcalli_mcp import budget, errors

FIXTURE_VAULT = Path(__file__).parents[1] / "fixtures" / "vault_markdown"
"""Fixture de Phase 1 (md con headings + subárbol + binario descartado)."""

GOLDEN_QUERY = "whitelist de extensiones indexables"
"""Consulta dorada determinista sobre el fixture (vocabulario real de `nota.md`)."""

FILTER_QUERY = "indexación del flujo"
"""Consulta del test de `path_filter` — misma ancla que T2 sobre este vault."""

STAGING_SOURCE = "# Staging T8\n\nFichero de staging para el contract test de add_source.\n"
"""Fuente `file:` DENTRO del vault pero fuera de `00-resources/` (patrón T5)."""

INVALID_SEARCH_ARGUMENTS = {
    "top_k_fuera_de_rango": {"query": GOLDEN_QUERY, "top_k": 99},
    "glob_absoluto": {"query": GOLDEN_QUERY, "path_filter": "/absoluto/*.md"},
    "glob_con_escape": {"query": GOLDEN_QUERY, "path_filter": "00-resources/../secreto/*"},
    "glob_vacio": {"query": GOLDEN_QUERY, "path_filter": ""},
}
"""Args inválidos del AC: `top_k` fuera de [1,20] y los 3 globs malos (.., absoluto, vacío)."""


def _write_toml(vault: Path, content: str) -> None:
    """Escribe `tepochcalli.toml` — la config PROPIA de cada escenario (aislamiento)."""
    config_dir = vault / ".tepochcalli" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "tepochcalli.toml").write_text(content, encoding="utf-8")


def _cloned_vault(indexed: Path, dst: Path, *, empty_models: bool = False) -> Path:
    """Copia del vault indexado para un escenario con entorno PROPIO (F.I.R.S.T.).

    `symlinks=True` copia el enlace `.tepochcalli/models` tal cual (mismo
    cache); `empty_models=True` lo sustituye por un directorio VACÍO — los
    escenarios de modelo no materializable arrancan sin pesos, sin tocar el
    vault compartido del módulo.
    """
    shutil.copytree(indexed, dst, dirs_exist_ok=True, symlinks=True)
    if empty_models:
        models = dst / ".tepochcalli" / "models"
        models.unlink()
        models.mkdir()
    return dst


@pytest.fixture(scope="module")
def contract_vault(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """Vault de contrato: fixture md + staging, indexado UNA vez en subproceso (patrón T2)."""
    vault = tmp_path_factory.mktemp("vault-t8-contract")
    shutil.copytree(FIXTURE_VAULT, vault, dirs_exist_ok=True)
    staging = vault / "staging"
    staging.mkdir()
    (staging / "contrato.md").write_text(STAGING_SOURCE, encoding="utf-8")
    models_link = index_vault(vault)
    return vault, models_link


# --- el shape congelado de las 4 tools, request y response, en el wire --------------------


def test_each_tool_answers_the_frozen_contract_shape_over_the_wire(
    contract_vault: tuple[Path, Path],
) -> None:
    """Las 4 tools: claves y orden EXACTOS de request y response (plan §5, D7.3)."""
    vault, models_link = contract_vault
    env = server_env(vault, models_link)
    staging_uri = (vault / "staging" / "contrato.md").as_uri()

    async def journey() -> dict[str, list[str]]:
        shapes: dict[str, list[str]] = {}
        async with running_server(env) as session:
            # --- request shape: exactamente las 4 tools y sus input schemas ---
            tools = {tool.name: tool for tool in (await session.list_tools()).tools}
            assert sorted(tools) == [
                "add_source",
                "convert_base64",
                "convert_document",
                "index_refresh",
                "list_formats",
                "rag_status",
                "search",
            ]
            search_schema = tools["search"].input_schema
            assert list(search_schema["properties"]) == ["query", "top_k", "path_filter"]
            assert search_schema["required"] == ["query"]
            assert search_schema["properties"]["top_k"]["default"] == 5
            assert search_schema["properties"]["path_filter"]["default"] is None
            assert list(tools["add_source"].input_schema["properties"]) == ["uri", "subdir"]
            assert tools["add_source"].input_schema["required"] == ["uri"]
            assert list(tools["convert_base64"].input_schema["properties"]) == [
                "data",
                "output_path",
                "format",
                "filename",
            ]
            assert tools["convert_base64"].input_schema["required"] == ["data"]
            refresh_schema = tools["index_refresh"].input_schema
            assert refresh_schema["properties"] == {}, "sin `directories` ni parámetros"
            assert refresh_schema.get("required", []) == []
            assert tools["list_formats"].input_schema["properties"] == {}
            assert tools["list_formats"].input_schema.get("required", []) == []
            assert tools["rag_status"].input_schema["properties"] == {}
            # H6: handlers `-> CallToolResult` ⇒ sin outputSchema; el shape vive
            # en content[0].text y `structured_content` queda None (lo afirma wire_payload).
            assert all(tool.output_schema is None for tool in tools.values())

            # --- index_refresh: el reporte tal cual, con la identidad de cuentas ---
            result = await session.call_tool("index_refresh", {})
            refresh = wire_payload(result)
            assert not result.is_error, refresh
            shapes["index_refresh"] = list(refresh)
            assert refresh["locked"] is False
            assert refresh["scanned"] == refresh["indexed"] + refresh["skipped"]
            assert isinstance(refresh["elapsed_ms"], int) and refresh["elapsed_ms"] >= 0

            # --- search: 4 claves de nivel superior + 7 campos por resultado ---
            result = await session.call_tool("search", {"query": GOLDEN_QUERY})
            search = wire_payload(result)
            assert not result.is_error, search
            shapes["search"] = list(search)
            assert search["query"] == GOLDEN_QUERY
            assert isinstance(search["took_ms"], int)
            assert isinstance(search["truncated"], bool)
            results = search["results"]
            assert isinstance(results, list) and results, "el vault indexado debe devolver citas"
            scores: list[float] = []
            for item in results:
                assert list(item) == SEARCH_RESULT_FIELDS
                assert isinstance(item["text"], str) and item["text"]
                assert str(item["source_path"]).startswith("00-resources/")
                assert (vault / str(item["source_path"])).is_file(), "source_path real"
                assert item["heading"] is None or isinstance(item["heading"], str)  # D13
                assert isinstance(item["char_start"], int) and isinstance(item["char_end"], int)
                assert 0 <= item["char_start"] < item["char_end"]
                assert isinstance(item["score"], float)
                assert 0.0 <= item["score"] <= 1.0
                # fixture md-only: los offsets citan el archivo original (spec §search)
                assert item["offsets_ref"] == "source"
                scores.append(item["score"])
            assert scores == sorted(scores, reverse=True), "score descendente garantizado"

            # --- rag_status: 4 bloques, orden interno, salud sana y <200 tokens ---
            result = await session.call_tool("rag_status", {})
            status = wire_payload(result)
            assert not result.is_error, status
            shapes["rag_status"] = list(status)
            for block, keys in RAG_STATUS_INNER_KEYS.items():
                assert list(status[block]) == keys, block
            assert status["health"] == {"state": "ok", "reason": None, "fix_hint": None}
            last_refresh = status["index"]["last_refresh"]
            assert isinstance(last_refresh, str) and last_refresh, "derivado de indexed_at real"
            # ISO-8601 con offset UTC. Phase 1 escribe "+00:00"; el ejemplo de la
            # spec muestra "Z" — mismo instante, distinto sufijo. El contrato
            # congela el CAMPO, no el sufijo (decisión del lead 2026-10-26: sin
            # normalización cosmética; la divergencia queda documentada AQUÍ).
            parsed = datetime.fromisoformat(last_refresh)
            assert parsed.utcoffset() == timedelta(0), "offset UTC en el ISO-8601 del índice"
            assert budget.estimate_tokens(json.dumps(status, ensure_ascii=False)) < 200

            # --- add_source al FINAL del viaje: muta el vault y nada depende de su estado ---
            result = await session.call_tool("add_source", {"uri": staging_uri})
            added = wire_payload(result)
            assert not result.is_error, added
            shapes["add_source"] = list(added)
            assert added["ok"] is True
            assert added["written_to"] == "00-resources/_inbox/contrato.md"
            assert list(added["indexed"]) == ADD_SOURCE_INDEXED_FIELDS
        return shapes

    shapes = asyncio.run(journey())
    # Orden EXACTO de claves por tool — plan §5 «Contrato de datos» (Hyrum/ADR-005).
    assert shapes["index_refresh"] == REFRESH_FIELDS
    assert shapes["search"] == SEARCH_TOP_LEVEL_FIELDS
    assert shapes["rag_status"] == RAG_STATUS_BLOCKS
    assert shapes["add_source"] == ADD_SOURCE_FIELDS


# --- en error: is_error + JSON canónico, NUNCA texto libre ---------------------------------


def test_invalid_search_arguments_return_json_validation_error_on_the_wire(
    contract_vault: tuple[Path, Path],
) -> None:
    """Args inválidos (`top_k`, globs `..`/absoluto/vacío) → `VALIDATION_ERROR` JSON en el wire.

    Cada caso sale con `is_error = true` y `content[0].text` parseable con la
    forma LEGADA `{error:{code,message,details}}` (plan §Taxonomía) — el
    resultado de `wire_payload` ya habría hecho fallar el test si el texto
    fuera prosa.
    """
    vault, models_link = contract_vault
    env = server_env(vault, models_link)

    async def calls() -> dict[str, tuple[CallToolResult, dict[str, object]]]:
        out: dict[str, tuple[CallToolResult, dict[str, object]]] = {}
        async with running_server(env) as session:
            for name, arguments in INVALID_SEARCH_ARGUMENTS.items():
                result = await session.call_tool("search", arguments)
                out[name] = (result, wire_payload(result))
        return out

    for name, (result, payload) in asyncio.run(calls()).items():
        assert result.is_error, name
        assert list(payload) == ["error"], name
        error = payload["error"]
        assert list(error) == ["code", "message", "details"], name
        assert error["code"] == "VALIDATION_ERROR", name
        assert isinstance(error["message"], str) and error["message"], name
        assert error["details"] is None, name


def test_missing_index_answers_index_empty_as_json_error(tmp_path: Path) -> None:
    """Vault SIN índice con embedder local por omisión → `INDEX_EMPTY` legado en el wire."""
    (tmp_path / "00-resources").mkdir(parents=True)
    env = server_env(tmp_path)  # sin env de modelo: INDEX_EMPTY no debe cargar pesos

    async def call() -> tuple[CallToolResult, dict[str, object]]:
        async with running_server(env) as session:
            result = await session.call_tool("search", {"query": GOLDEN_QUERY})
            return result, wire_payload(result)

    result, payload = asyncio.run(call())
    assert result.is_error
    assert list(payload) == ["error"]
    error = payload["error"]
    assert list(error) == ["code", "message", "details"]
    assert error["code"] == "INDEX_EMPTY"
    assert error["message"] == "El índice no existe; ejecute index_refresh()."
    assert error["details"] is None


# --- instalación degradada (salida 5 / D15): el AC end-to-end de T8 ------------------------


def test_degraded_install_returns_e_no_embedder_and_degraded_rag_status(tmp_path: Path) -> None:
    """`provider = "none"` ⇒ `search`/`index_refresh` = `E_NO_EMBEDDER` y `rag_status` degraded.

    El `health.fix_hint` es el literal de spec §rag_status. End-to-end sobre
    el proceso real: la precedencia `E_NO_EMBEDDER` >
    `INDEX_EMPTY` se demuestra AQUÍ (el vault ni siquiera tiene db) — la
    regla del vault obliga al agente a reportar la guía, no el error crudo.
    """
    _write_toml(tmp_path, '[embedding]\nprovider = "none"\n')
    (tmp_path / "00-resources").mkdir()  # el default `index_refresh()` exige la raíz (T8)
    env = server_env(tmp_path)  # la degradación jamás debe cargar pesos

    async def journey() -> tuple[
        CallToolResult,
        dict[str, object],
        CallToolResult,
        dict[str, object],
        CallToolResult,
        dict[str, object],
    ]:
        async with running_server(env) as session:
            status_result = await session.call_tool("rag_status", {})
            status = wire_payload(status_result)
            search_result = await session.call_tool("search", {"query": GOLDEN_QUERY})
            search = wire_payload(search_result)
            refresh_result = await session.call_tool("index_refresh", {})
            refresh = wire_payload(refresh_result)
            return status_result, status, search_result, search, refresh_result, refresh

    status_result, status, search_result, search, refresh_result, refresh = asyncio.run(journey())

    # rag_status: 4 bloques exactos, degraded con su guía y <200 tokens (D7.3).
    assert not status_result.is_error
    assert list(status) == RAG_STATUS_BLOCKS
    for block, keys in RAG_STATUS_INNER_KEYS.items():
        assert list(status[block]) == keys, block
    assert status["embedder"] == {"mode": "none", "model": None, "dims": None, "provider": None}
    assert status["index"] == {
        "rows": 0,
        "model_matches_config": True,
        "last_refresh": None,
        "db_size_bytes": 0,
        "last_refresh_roots": [],
        "available_roots": ["00-resources"],
    }
    assert status["health"] == {
        "state": "degraded",
        "reason": "E_NO_EMBEDDER",
        # Literal del ejemplo «instalación con Configurar después» de
        # spec-mcp-server §rag_status — la regla del vault obliga a reportar
        # ESTE texto (anclado en la spec, no en `errors.FIX_NO_EMBEDDER`).
        "fix_hint": "Ejecuta `tepochcalli config embedder` y luego `index_refresh()`",
    }
    assert budget.estimate_tokens(json.dumps(status, ensure_ascii=False)) < 200

    # search: E_NO_EMBEDDER en el wire — precede a INDEX_EMPTY (vault sin db).
    assert search_result.is_error
    assert search == errors.no_embedder(), "payload byte a byte igual al constructor del dominio"
    assert list(search["error"]) == ["code", "message", "fix_hint"]

    # index_refresh: también emisor (spec §Códigos) — sin embedder no hay ciclo Δ.
    assert refresh_result.is_error
    assert refresh == errors.no_embedder()


def _resources_paths(vault: Path) -> set[str]:
    """Snapshot de rutas bajo `00-resources/` (relativas al vault) — prueba de NO escritura."""
    resources = vault / "00-resources"
    if not resources.is_dir():
        return set()
    return {path.relative_to(vault).as_posix() for path in resources.rglob("*")}


def test_degraded_install_add_source_returns_e_no_embedder_and_writes_nothing(
    tmp_path: Path,
) -> None:
    """`provider = "none"` ⇒ `add_source` = `E_NO_EMBEDDER` y CERO escritura (spec §Códigos).

    Spec-mcp-server.md:151 exige `E_NO_EMBEDDER` para `search`, `index_refresh`
    **y `add_source`**; el test vecino recorre las dos primeras y deja fuera la
    tercera. End-to-end contra el proceso real, con una fuente `file:`
    DENTRO del vault que SÍ existe: si el corte faltara, la conversión real
    escribiría el `.md` y el refresh fallaría más tarde (enmascarando el
    código correcto con `INTERNAL`). Por eso aquí se afirman las dos mitades:
    el dialecto en el wire Y el efecto secundario ausente.
    """
    _write_toml(tmp_path, '[embedding]\nprovider = "none"\n')
    staging = tmp_path / "staging"
    staging.mkdir()
    source = staging / "degradado.md"
    source.write_text("# Degradado\n\nfuente real dentro del vault\n", encoding="utf-8")
    before = _resources_paths(tmp_path)
    env = server_env(tmp_path)  # la degradación jamás debe cargar pesos

    async def call() -> tuple[CallToolResult, dict[str, object]]:
        async with running_server(env) as session:
            result = await session.call_tool("add_source", {"uri": source.as_uri()})
            return result, wire_payload(result)

    result, payload = asyncio.run(call())

    assert result.is_error
    assert payload == errors.no_embedder(), "payload byte a byte igual al constructor del dominio"
    assert _resources_paths(tmp_path) == before, "sin embedder no se escribe NADA en 00-resources/"
    assert not (tmp_path / "00-resources" / "_inbox").exists(), "ni siquiera se crea el destino"


# --- los E_* RECORRIENDO el proceso: escenario real por código y por stdio -----------------


def test_api_auth_travels_the_wire_from_search_on_litellm_without_key(
    contract_vault: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D6-5 pagada: `E_API_AUTH` EN EL WIRE — proceso real, litellm SIN clave, cero red.

    El contract test por código que la deuda D6-5 declaró sin RED aislada (el
    patrón `-k` de T6 no matcheó nada): aquí la llamada sale por stdio contra
    `python -m tepochcalli_mcp` y se afirma el dialecto tal cual lo recibe el
    harness — JSON en `content[0].text`, `is_error = true`, SOLO el nombre de
    la env var y jamás un valor de clave. El chequeo de clave es local: el
    hijo arranca con el canario `nonet` y no diala nada.
    """
    vault, models_link = contract_vault
    clone = _cloned_vault(vault, tmp_path)
    _write_toml(clone, f'[embedding]\nprovider = "litellm"\nmodel = "{DEFAULT_EMBEDDING_MODEL}"\n')
    # ANTES de montar la env: el hijo hereda `os.environ` sin la clave.
    monkeypatch.delenv(DEFAULT_API_KEY_ENV, raising=False)
    env = server_env(clone, models_link)

    async def call() -> tuple[CallToolResult, dict[str, object]]:
        async with running_server(env) as session:
            result = await session.call_tool("search", {"query": GOLDEN_QUERY})
            return result, wire_payload(result)

    result, payload = asyncio.run(call())
    assert result.is_error
    assert list(payload) == ["error"]
    error = payload["error"]
    assert list(error) == ["code", "message", "fix_hint"]
    assert error["code"] == "E_API_AUTH"
    assert DEFAULT_API_KEY_ENV in error["message"], "nombra QUÉ clave (accionable)"
    assert error["fix_hint"] == errors.FIX_API_AUTH
    assert "sk-" not in result.content[0].text, "jamás un valor de clave en el wire"


def test_model_mismatch_travels_the_wire_without_crossing_dims(
    contract_vault: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    """`E_MODEL_MISMATCH` en el wire + alias legado en `details` — search NO cruza dims."""
    vault, _models_link = contract_vault
    clone = _cloned_vault(vault, tmp_path)
    _write_toml(clone, '[embedding]\nmodel = "modelo-de-otra-vida"\n')
    # SIN env de modelo: el mismatch precede a cualquier embed — si cargara pesos,
    # la ausencia de cache lo dejaría en `E_OFFLINE_NO_CACHE` y el test fallaría.
    env = server_env(clone)

    async def call() -> tuple[CallToolResult, dict[str, object]]:
        async with running_server(env) as session:
            result = await session.call_tool("search", {"query": GOLDEN_QUERY})
            return result, wire_payload(result)

    result, payload = asyncio.run(call())
    assert result.is_error
    error = payload["error"]
    assert list(error) == ["code", "message", "fix_hint", "details"]
    assert error["code"] == "E_MODEL_MISMATCH"
    assert "modelo-de-otra-vida" in error["message"]
    assert DEFAULT_EMBEDDING_MODEL in error["message"]
    assert error["fix_hint"] == errors.FIX_MODEL_MISMATCH
    # Ancla a la spec §INDEX_STALE_MODEL («requiere `tepochcalli reindex --confirm`»):
    # sin esto el texto del fix viaja auto-referenciado y una derivación silenciosa
    # del literal pasaría inadvertida (la unidad solo leía no-vacío para este código).
    assert "reindex --confirm" in error["fix_hint"]
    assert error["details"] == {"legacy_code": "INDEX_STALE_MODEL"}


def test_offline_without_cache_travels_the_wire_as_e_offline_no_cache(
    contract_vault: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    """Snapshot con los ficheros esperados pero ILEGIBLE + offline ⇒ `E_OFFLINE_NO_CACHE`.

    T6: la ausencia o la falta de pesos del snapshot es `E_MODEL_INVALID` (más
    precisa, TD-29); este caso conserva el contrato de `E_OFFLINE_NO_CACHE` para un
    snapshot que **pasa** la comprobación barata (manifiesto + fichero de pesos) y
    aun así no se puede cargar sin red: los pesos son basura, no un modelo. El hijo
    corre con `HF_HUB_OFFLINE=1` y un `HF_HOME` vacío.
    """
    vault, _models_link = contract_vault
    clone = _cloned_vault(vault, tmp_path, empty_models=True)
    stable = (
        clone
        / ".tepochcalli"
        / "models"
        / f"{model_slug(DEFAULT_EMBEDDING_MODEL)}@{MODEL_REVISION}"
    )
    stable.mkdir()
    (stable / "config.json").write_text("{}", encoding="utf-8")
    (stable / "model.safetensors").write_bytes(b"no es un safetensors")  # no es un modelo válido
    # HF_HOME vacío + HF_HUB_OFFLINE=1 (server_env lo fija con model_cache):
    # la carga local falla contra un cache sin modelo cargable y SIN intento de red.
    env = server_env(clone, clone / ".tepochcalli" / "models")

    async def call() -> tuple[CallToolResult, dict[str, object]]:
        async with running_server(env) as session:
            result = await session.call_tool("search", {"query": GOLDEN_QUERY})
            return result, wire_payload(result)

    result, payload = asyncio.run(call())
    assert result.is_error
    error = payload["error"]
    assert list(error) == ["code", "message", "fix_hint"]
    assert error["code"] == "E_OFFLINE_NO_CACHE"
    assert error["fix_hint"] == errors.FIX_OFFLINE_NO_CACHE


def test_model_that_cannot_be_materialized_travels_the_wire_as_e_model_invalid(
    contract_vault: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    """Cache VACÍO sin modo offline ⇒ `E_MODEL_INVALID` — y cero sockets por construcción.

    Es la otra mitad del par T6 (offline vs inválido): con los flags offline
    retirados el clasificador debe caer en `E_MODEL_INVALID`. Para no depender
    del backoff wall-clock de huggingface_hub (reintentos de hasta ~25 s que
    romperían la regla anti-flake de la suite) ni abrir ni un solo socket, el
    hijo arranca con `HF_ENDPOINT` en un esquema no-http: httpx lanza
    `UnsupportedProtocol` ANTES de cualquier I/O — determinismo sin sleeps y
    cero red más fuerte que el propio canario.
    """
    vault, _models_link = contract_vault
    clone = _cloned_vault(vault, tmp_path, empty_models=True)
    env = server_env(clone, clone / ".tepochcalli" / "models")
    env.pop("HF_HUB_OFFLINE", None)
    env.pop("TRANSFORMERS_OFFLINE", None)
    env["HF_ENDPOINT"] = "ftp://tepochcalli.invalid"

    async def call() -> tuple[CallToolResult, dict[str, object]]:
        async with running_server(env) as session:
            result = await session.call_tool("search", {"query": GOLDEN_QUERY})
            return result, wire_payload(result)

    result, payload = asyncio.run(call())
    assert result.is_error
    error = payload["error"]
    assert list(error) == ["code", "message", "fix_hint"]
    assert error["code"] == "E_MODEL_INVALID", payload
    assert error["fix_hint"] == errors.FIX_MODEL_INVALID


# --- path_filter: globs VÁLIDOS con prefijo 00-resources/ ---------------------------------


def test_valid_path_filter_globs_prefilter_results_on_the_wire(
    contract_vault: tuple[Path, Path],
) -> None:
    """Glob válido bajo `00-resources/` prefiltra de verdad; sin match ⇒ vacío SIN error."""
    vault, models_link = contract_vault
    env = server_env(vault, models_link)

    async def calls() -> dict[str, dict[str, object]]:
        out: dict[str, dict[str, object]] = {}
        async with running_server(env) as session:
            unfiltered = await session.call_tool("search", {"query": FILTER_QUERY, "top_k": 8})
            out["general"] = wire_payload(unfiltered)
            filtered = await session.call_tool(
                "search",
                {"query": FILTER_QUERY, "top_k": 8, "path_filter": "00-resources/sub/*"},
            )
            out["filtered"] = wire_payload(filtered)
            no_match = await session.call_tool(
                "search",
                {"query": FILTER_QUERY, "path_filter": "00-resources/no-existe/*.md"},
            )
            out["no_match"] = wire_payload(no_match)
        return out

    payloads = asyncio.run(calls())

    general = payloads["general"]["results"]
    assert general, "sin filtro, el vault indexado responde"
    assert any(not str(item["source_path"]).startswith("00-resources/sub/") for item in general), (
        "sin filtro debe haber resultados fuera de sub/ (si no, el prefiltra sería vacío)"
    )

    filtered = payloads["filtered"]["results"]
    assert filtered, "00-resources/sub/* debe devolver la nota anidada"
    assert all(str(item["source_path"]).startswith("00-resources/sub/") for item in filtered)

    assert payloads["no_match"]["results"] == [], "glob válido sin match: vacío, no error"
    assert "error" not in payloads["no_match"]
