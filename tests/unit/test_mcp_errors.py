"""T2: taxonomía de errores del server — payloads canónicos, dominio puro (plan §5).

Fuentes de verdad:

* tasks/plan.md §5 «Taxonomía de errores» — legado `{error:{code,message,details}}`
  para `VALIDATION_ERROR`/`INDEX_EMPTY`/`INTERNAL`; dialecto `E_*`
  `{error:{code,message,fix_hint}}` (+ `details.legacy_code` en
  `E_MODEL_MISMATCH`, spec-mcp-server §Códigos de error estructurados).
* specs/spec-mcp-server.md §Manejo de errores — «nunca texto libre»: el payload
  ES el JSON que viaja en `content[0].text`.

El orden de claves se aserta con `list(...)`: en el wire el orden es parte del
contrato congelado (Hyrum, ADR-005). Estos tests NO importan infraestructura —
`errors.py` es dominio puro del server (test de arquitectura extendido).
"""

from __future__ import annotations

import json

from tepochcalli_mcp import errors


def test_validation_error_uses_the_legacy_shape_with_exact_key_order() -> None:
    """`VALIDATION_ERROR` → `{error:{code,message,details}}` (legado, plan §5)."""
    payload = errors.validation_error("top_k debe estar en [1,20]; recibido: 21")

    assert list(payload) == ["error"]
    error = payload["error"]
    assert list(error) == ["code", "message", "details"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["message"] == "top_k debe estar en [1,20]; recibido: 21"
    assert error["details"] is None


def test_validation_error_carries_structured_details_when_provided() -> None:
    """El `details` legado acepta estructura (los args rechazados), tipado object."""
    payload = errors.validation_error("subdir inválido", details={"subdir": "../secreto"})

    assert payload["error"]["details"] == {"subdir": "../secreto"}


def test_index_empty_uses_the_spec_message_and_legacy_shape() -> None:
    """`INDEX_EMPTY` → legado con el mensaje textual de spec-mcp-server §errores."""
    payload = errors.index_empty()

    error = payload["error"]
    assert list(error) == ["code", "message", "details"]
    assert error["code"] == "INDEX_EMPTY"
    assert error["message"] == "El índice no existe; ejecute index_refresh()."
    assert error["details"] is None


def test_model_mismatch_is_e_dialect_with_legacy_alias_in_details() -> None:
    """`E_MODEL_MISMATCH` → dialecto `E_*` + `details.legacy_code = INDEX_STALE_MODEL`.

    spec-mcp-server §Códigos: `code` = `E_MODEL_MISMATCH` (término D7.3) y el
    alias heredado viaja en `details.legacy_code` — ambos nombres en el payload.
    """
    payload = errors.model_mismatch(
        index_models={"modelo-viejo"},
        expected="paraphrase-multilingual-MiniLM-L12-v2",
    )

    error = payload["error"]
    assert list(error) == ["code", "message", "fix_hint", "details"]
    assert error["code"] == "E_MODEL_MISMATCH"
    assert "modelo-viejo" in error["message"]
    assert "paraphrase-multilingual-MiniLM-L12-v2" in error["message"]
    assert error["fix_hint"]  # la solución exacta, accionable (D7.3)
    assert list(error["details"]) == ["legacy_code"]
    assert error["details"]["legacy_code"] == "INDEX_STALE_MODEL"


def test_internal_never_leaks_stack_traces() -> None:
    """`INTERNAL` → legado; el mensaje no puede contener traceback ni texto libre."""
    payload = errors.internal()

    error = payload["error"]
    assert list(error) == ["code", "message", "details"]
    assert error["code"] == "INTERNAL"
    assert "Traceback" not in error["message"]
    assert error["details"] is None


def test_payloads_are_json_serializable_without_ascii_escaping() -> None:
    """Todo payload sobrevive a `json.dumps(ensure_ascii=False)` (el medio del contrato)."""
    for payload in (
        errors.validation_error("query vacía: se exige una consulta no vacía"),
        errors.index_empty(),
        errors.model_mismatch({"miniatura-ñ"}, "modelo-actual-日"),
        errors.internal(),
    ):
        round_trip = json.loads(json.dumps(payload, ensure_ascii=False))
        assert round_trip == payload
