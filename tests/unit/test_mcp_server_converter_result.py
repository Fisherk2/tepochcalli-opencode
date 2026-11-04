"""W-10 (review 5-ejes): `serialize_budget` SOLO empaqueta payloads de éxito.

El shape congelado de ADR-009 es la forma de un RESUMEN (5 claves). Un payload
de error que pasara por `summary.serialize_budget` ganaría un `preview: ""` y
un `truncated: true` fantasma — claves que no existen en la taxonomía de
errores. El helper `_converter_result` de `server.py` separa los dos caminos;
`json_result` (patrón de `tools/__init__.py`) lleva el `is_error` implícito.
"""

from __future__ import annotations

import json

from tepochcalli_mcp import server, summary

_LONG_ERROR: dict[str, object] = {
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "m" * 2000,
        "details": None,
    }
}
"""Error LEGÍTIMO mas de 1400 chars serializados: el caso que añade fantasmas."""


def test_error_payload_travels_untouched_without_phantom_keys() -> None:
    """Error largo ⇒ keys exactas del dialecto y NUNCA `preview`/`truncated` ajenos."""
    result = server._converter_result(_LONG_ERROR)

    assert result.is_error is True
    text = result.content[0].text
    assert json.loads(text) == _LONG_ERROR, 'sin `preview: ""` ni `truncated` fantasma'
    assert "preview" not in text and "truncated" not in text


def test_success_payload_keeps_the_budgetized_shape() -> None:
    """Éxito ⇒ EXACTAMENTE el resumen recortado de antes (cero cambio de forma)."""
    oversized = {
        "written_to": "00-Resources/a.md",
        "source_uri": "documentos/a.docx",
        "bytes": 6,
        "chars": 6,
        "preview": "p" * 3000,
    }
    result = server._converter_result(oversized)

    assert result.is_error is False
    assert json.loads(result.content[0].text) == json.loads(summary.serialize_budget(oversized))
