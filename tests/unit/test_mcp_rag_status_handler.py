"""T4: handler `rag_status` — 4 bloques congelados, health accionable y <200 tokens (plan §6).

Fuentes de verdad:

* tasks/plan.md §6 T4 AC + tasks/todo.md T4.
* specs/spec-mcp-server.md §Tool `rag_status` — los DOS ejemplos JSON son la
  referencia literal del shape; §Presupuesto de tokens (<200 por construcción).
* ADR-007/D7.3 — `reason` exclusivamente de la taxonomía `E_*`; ante cualquier
  `E_*` el agente llama esta tool y reporta el `fix_hint` exacto.

Decisiones de contrato (iguales en el docstring del handler y en la
descripción de la tool, que es lo que el agente lee):

* `mode`: `litellm` ⇒ `api`, `local` ⇒ `local`; `none` solo con un `Config`
  construido a mano — el loader real no lo admite hasta T6/D15. La fuente es
  `embedder.mode`, la MISMA de la que deriva `is_available` (costura de T3).
* `provider`: `null` en `local` y `none` (ejemplos LITERALES de la spec); en
  `api` = `config.embedding.provider` (hoy solo puede ser `litellm`: lo único
  que la config D11 puede nombrar).
* `dims`: 384 (`DEFAULT_EMBEDDING_DIMS`) SOLO si `model ==
  DEFAULT_EMBEDDING_MODEL` — único modelo cuyas dims son un hecho conocido
  sin cargar nada; `null` para modelos custom (una tool barata no pide dims a
  la red) y `null` en `none`.
* `model_matches_config` = `models ⊆ {config.model}`: ÍNDICE VACÍO ⇒ true
  (ejemplo literal de la spec: `rows: 0` con `matches: true`); con filas ⇒
  todas del modelo esperado — equivalente al `==` del AC en el único caso no
  vacío.
* `config.valid` = **el toml se pudo leer y parsear**; `false` SOLO si existe
  y está malformado/ilegible; AUSENTE ⇒ `true` (fichero opcional, defaults
  canónicos — «existe» por sí solo no significa nada, por eso no es un
  chequeo de existencia: el loader nunca falla).
* `health`: `none` ⇒ `degraded`+`E_NO_EMBEDDER` (precedencia) ⇒ mismatch ⇒
  `degraded`+`E_MODEL_MISMATCH` ⇒ si no `ok`/`null`/`null`. `reason` solo
  admite `E_*`, así que un índice VACÍO con embedder sano es `ok` (ningún
  `E_*` aplica). `config.valid` no degrada la salud: es informativo.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from tepochcalli_flow.config import (
    DEFAULT_EMBEDDING_MODEL,
    Config,
    EmbeddingConfig,
)
from tepochcalli_mcp import budget, embedder, errors
from tepochcalli_mcp.tools import json_result
from tepochcalli_mcp.tools import rag_status as status_handler

SANE_META: status_handler.IndexMeta = {
    "rows": 5,
    "models": {DEFAULT_EMBEDDING_MODEL},
    "last_refresh": "2026-10-21T14:32:10+00:00",
    "db_size_bytes": 18_400_000,
}


def _config(*, provider: str = "local", model: str = DEFAULT_EMBEDDING_MODEL) -> Config:
    """Config construida a mano — el loader real no puede expresar `none` (D15/T6)."""
    return Config(
        models_dir=Path("/vault/.tepochcalli/models"),
        embedding=EmbeddingConfig(provider=provider, model=model),
    )


def _call(
    *,
    config: Config | None = None,
    meta: status_handler.IndexMeta | None = None,
    config_valid: bool = True,
    meta_error: Exception | None = None,
) -> dict[str, object]:
    """Invoca el handler en su propio loop con seams de doble (cada test, aislado)."""
    resolved = config if config is not None else _config()
    resolved_meta = meta if meta is not None else SANE_META

    async def _meta_seam() -> status_handler.IndexMeta:
        if meta_error is not None:
            raise meta_error
        return resolved_meta

    return asyncio.run(
        status_handler.rag_status(
            config_factory=lambda: resolved,
            index_meta=_meta_seam,
            config_valid=lambda: config_valid,
        )
    )


# --- shape congelado: 4 bloques, orden exacto --------------------------------------


def test_four_blocks_with_exact_key_order_inside_each_block() -> None:
    """Shape literal de spec §rag_status: 4 bloques y orden de claves por bloque."""
    payload = _call()

    assert list(payload) == ["embedder", "index", "config", "health"]
    assert list(payload["embedder"]) == ["mode", "model", "dims", "provider"]  # type: ignore[arg-type]
    assert list(payload["index"]) == [
        "rows",
        "model_matches_config",
        "last_refresh",
        "db_size_bytes",
    ]
    assert list(payload["config"]) == ["path", "valid"]
    assert list(payload["health"]) == ["state", "reason", "fix_hint"]


def test_sane_install_reports_ok_with_the_spec_values() -> None:
    """Instalación sana (ejemplo 1 de la spec): ok/null/null + bloque index derivado."""
    payload = _call()

    embedder = payload["embedder"]
    assert embedder["mode"] == "local"  # type: ignore[index]
    assert embedder["model"] == DEFAULT_EMBEDDING_MODEL
    assert embedder["dims"] == 384
    assert embedder["provider"] is None  # ej. literal: local ⇒ provider null
    index = payload["index"]
    assert index["rows"] == 5
    assert index["model_matches_config"] is True
    assert index["last_refresh"] == SANE_META["last_refresh"]  # derivado, passthrough
    assert index["db_size_bytes"] == 18_400_000
    health = payload["health"]
    assert health == {"state": "ok", "reason": None, "fix_hint": None}


def test_config_path_is_the_relative_toml_literal() -> None:
    """`config.path` relativo POR CONSTRUCCIÓN — el literal exacto de la spec."""
    payload = _call()

    config_block = payload["config"]
    assert config_block["path"] == ".tepochcalli/config/tepochcalli.toml"
    assert config_block["valid"] is True


def test_empty_index_is_ok_with_null_last_refresh() -> None:
    """Índice vacío + embedder sano ⇒ `ok` (ningún `E_*` aplica) y `last_refresh: null`."""
    payload = _call(meta={"rows": 0, "models": set(), "last_refresh": None, "db_size_bytes": 0})

    index = payload["index"]
    assert index["rows"] == 0
    assert index["model_matches_config"] is True, "vacío ⇒ true (ej. literal de la spec)"
    assert index["last_refresh"] is None
    assert index["db_size_bytes"] == 0
    assert payload["health"] == {"state": "ok", "reason": None, "fix_hint": None}


# --- los 3 estados del AC (sano / sin embedder / modelo distinto) ---------------------


def test_no_embedder_state_is_degraded_with_the_exact_fix_hint() -> None:
    """Modo `none` ⇒ `degraded` + `E_NO_EMBEDDER` + fix_hint literal de la spec.

    Se demuestra con un `Config` construido a mano (la costura): el loader de
    `flow/config.py` — VEDADO hasta T6/D15 — aún no puede expresar `none`.
    """
    payload = _call(config=_config(provider="none"))

    assert payload["embedder"] == {
        "mode": "none",
        "model": None,
        "dims": None,
        "provider": None,
    }  # ej. literal 2 de la spec
    assert payload["health"] == {
        "state": "degraded",
        "reason": "E_NO_EMBEDDER",
        "fix_hint": "Ejecuta `tepochcalli config embedder` y luego `index_refresh()`",
    }


def test_model_mismatch_state_is_degraded_with_legacy_fix_hint() -> None:
    """Filas de OTRO modelo ⇒ `degraded` + `E_MODEL_MISMATCH`, sin cruzar dims."""
    meta: status_handler.IndexMeta = {
        "rows": 3,
        "models": {"modelo-viejo"},
        "last_refresh": "2026-10-21T14:32:10+00:00",
        "db_size_bytes": 4096,
    }

    payload = _call(meta=meta)

    assert payload["index"]["model_matches_config"] is False  # type: ignore[index]
    health = payload["health"]
    assert health["state"] == "degraded"  # type: ignore[index]
    assert health["reason"] == "E_MODEL_MISMATCH"  # type: ignore[index]
    assert health["fix_hint"] == errors.FIX_MODEL_MISMATCH  # type: ignore[index]


def test_no_embedder_takes_precedence_over_model_mismatch() -> None:
    """Precedencia: sin embedder, el `E_*` del provider gana aunque el índice esté stale."""
    meta: status_handler.IndexMeta = {
        "rows": 3,
        "models": {"modelo-viejo"},
        "last_refresh": None,
        "db_size_bytes": 0,
    }

    payload = _call(config=_config(provider="none"), meta=meta)

    assert payload["health"]["reason"] == "E_NO_EMBEDDER"  # type: ignore[index]


def test_config_valid_false_is_informational_and_never_degrades_health() -> None:
    """`valid: false` (toml malformado) NO degrada la salud: ningún `E_*` lo cubre."""
    payload = _call(config_valid=False)

    assert payload["config"]["valid"] is False
    assert payload["health"]["state"] == "ok"  # type: ignore[index]


# --- mapeo mode/provider/dims (la fuente de T3 y de esta tool) -------------------------


def test_mode_maps_loader_values_to_the_d7_3_vocabulary() -> None:
    """`litellm` ⇒ `api`; `local` ⇒ `local`; `none` (Config a mano) ⇒ `none`.

    La fuente ÚNICA es `embedder.mode` — de ella deriva `is_available` (la
    costura de precedencia de T3), así que ambas tools leen el mismo hecho.
    """
    assert embedder.mode(_config()) == "local"
    assert embedder.mode(_config(provider="litellm")) == "api"
    assert embedder.mode(_config(provider="none")) == "none"


def test_provider_is_null_except_in_api_mode_where_it_names_the_config_key() -> None:
    """spec: `null` en local/none; en api, la clave que la config puede nombrar."""
    assert status_handler._provider_of("local", _config()) is None
    assert status_handler._provider_of("none", _config(provider="none")) is None
    assert status_handler._provider_of("api", _config(provider="litellm")) == "litellm"


def test_dims_are_known_only_for_the_pinned_default_model() -> None:
    """384 solo para el modelo pineado (ADR-006); custom ⇒ null (sin preguntar a la red)."""
    assert status_handler._dims_of(DEFAULT_EMBEDDING_MODEL) == 384
    assert status_handler._dims_of("text-embedding-3-small") is None
    assert status_handler._dims_of(None) is None


# --- presupuesto: <200 tokens (D7.3: barata por diseño) ---------------------------------


def test_payload_stays_under_200_tokens_in_every_state() -> None:
    """Los 3 estados por debajo del techo de §Presupuesto de tokens."""
    for payload in (
        _call(),
        _call(config=_config(provider="none")),
        _call(
            meta={"rows": 3, "models": {"modelo-viejo"}, "last_refresh": None, "db_size_bytes": 0}
        ),
    ):
        cost = budget.estimate_tokens(json.dumps(payload, ensure_ascii=False))
        assert cost < 200, cost


# --- la guarda compartida (G1) cubre también este handler --------------------------------


def test_unexpected_index_failure_is_canonical_internal() -> None:
    """Un fallo ≠ ValueError del seam de índice ⇒ `INTERNAL` canónico con `is_error`."""
    payload = _call(meta_error=OSError("tabla corrupta con detalle privado"))

    result = json_result(payload)
    assert result.is_error is True
    error = json.loads(result.content[0].text)["error"]
    assert list(error) == ["code", "message", "details"]
    assert error["code"] == "INTERNAL"
    assert "detalle privado" not in error["message"]
