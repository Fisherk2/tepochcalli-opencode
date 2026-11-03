"""T11: handler de `list_formats` — el catálogo real, sin motor ni conversor (unit).

Fuentes de verdad:

* tasks/todo.md T11 AC (a)-(c) — `{formats, count, notes}` del catálogo, < 200
  tokens con el estimador de `budget`, y la nota dice que NO hay OCR.
* specs/spec-markitdown.md §Catálogo — 13 extensiones verificadas contra
  `markitdown==0.1.9`; `.doc`/`.ppt` fuera porque el paquete no trae convertidor
  legacy (prometerlos sería un fallo tardío, en tiempo de conversión).
* specs/spec-mcp-server.md §Presupuesto — `list_formats` es barata por
  construcción: dato curado, sin I/O.

El handler NO importa `markitdown` (test de arquitectura): lee `formats.py`.
La conversión real de cada extensión se ata en
`tests/integration/test_mcp_list_formats.py` (AC d).
"""

from __future__ import annotations

import json

from tepochcalli_mcp import budget, formats
from tepochcalli_mcp.tools import list_formats as handler


def test_payload_is_exactly_formats_count_and_notes_in_that_order() -> None:
    """Tres claves, en ese orden: el agente no recibe nada más (AC a)."""
    payload = handler.list_formats()

    assert list(payload) == ["formats", "count", "notes"]
    published = payload["formats"]
    assert isinstance(published, list)
    assert published == list(formats.SUPPORTED_FORMATS)
    assert payload["count"] == len(published) == 13
    assert payload["notes"] == formats.NOTES


def test_notes_explain_the_two_limits_the_agent_must_not_promise() -> None:
    """Sin OCR y sin `.doc`/`.ppt` legacy, con el motivo exacto (AC c)."""
    notes = str(handler.list_formats()["notes"])

    assert "OCR" in notes
    assert ".doc" in notes and ".ppt" in notes
    assert "markitdown 0.1.9" in notes
    assert "legacy" in notes


def test_response_fits_the_two_hundred_token_budget() -> None:
    """`chars/4 + 25` del `budget` < 200: el catálogo no infla la conversación (AC b)."""
    text = json.dumps(handler.list_formats(), ensure_ascii=False)

    assert budget.estimate_tokens(text) < 200
