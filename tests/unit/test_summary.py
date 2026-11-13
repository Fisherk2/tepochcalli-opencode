"""T7 (D36/M3): el resumen de 5 claves, leído del fichero escrito, y su techo de 1 400 chars.

Fuentes de verdad:

* tasks/todo.md T7 AC (c), (d) — `build_summary` devuelve `written_to`,
  `source_uri`, `bytes`, `chars`, `preview` en orden fijo (+ `truncated` solo
  al recortar), leyendo el FICHERO ESCRITO; `serialize_budget` topa 1 400.
* tasks/plan.md §5.5 (contrato de wire) y M3 (`preview` ≤500, respuesta
  ≤1 400 chars ≈200 tokens ES/EN).
* ADR-009 D36 — sin clave `ok`; el resumen ES la confirmación.
"""

from __future__ import annotations

import json
from pathlib import Path

from tepochcalli_mcp import summary

SHORT = "# Informe\n\ncontenido breve\n"
"""Documento corto: cabe entero en el preview de 500 chars."""


def _written(vault: Path, text: str = SHORT) -> Path:
    """Escribe el `.md` como lo haría `writer.write_atomic` y devuelve su ruta absoluta."""
    target = vault / "00-resources" / "informe.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


# --- build_summary ---------------------------------------------------------------


def test_summary_has_the_five_keys_in_the_frozen_order(tmp_path: Path) -> None:
    """Orden de claves = contrato (Hyrum): ningún test puede pasar con sexta clave."""
    vault = tmp_path / "vault"
    target = _written(vault)

    payload = summary.build_summary(target, source_uri="fuentes/informe.docx", vault_root=vault)

    assert list(payload) == ["written_to", "source_uri", "bytes", "chars", "preview"]
    assert "ok" not in payload, "D36: el éxito es la ausencia de error"
    assert payload["written_to"] == "00-resources/informe.md"
    assert payload["source_uri"] == "fuentes/informe.docx"
    assert payload["bytes"] == target.stat().st_size
    assert payload["chars"] == len(SHORT)
    assert payload["preview"] == SHORT


def test_short_preview_is_not_marked_truncated(tmp_path: Path) -> None:
    """`truncated` solo aparece cuando el preview se recortó."""
    target = _written(tmp_path)

    payload = summary.build_summary(target, source_uri="x.docx")

    assert "truncated" not in payload
    assert str(target) == payload["written_to"], "sin vault_root: la ruta tal cual se dio"


def test_preview_is_capped_at_500_chars_and_flags_truncated(tmp_path: Path) -> None:
    """`preview` ≤500 chars del DISCO; el resto queda en el fichero, no en el wire."""
    target = _written(tmp_path, "a" * 900)

    payload = summary.build_summary(target, source_uri="x.docx")

    assert payload["truncated"] is True
    assert isinstance(payload["preview"], str) and len(payload["preview"]) == 500
    assert payload["preview"] == "a" * 500


def test_summary_reads_the_written_file_not_a_buffer(tmp_path: Path) -> None:
    """Los números siguen al DISCO: se reescribe el fichero y el resumen cambia."""
    target = _written(tmp_path, "uno\n")
    first = summary.build_summary(target, source_uri="x.docx")

    _written(tmp_path, "dos\n" * 10)
    second = summary.build_summary(target, source_uri="x.docx")

    assert first["chars"] == 4
    assert second["chars"] == 40, "stat/len del fichero, no del markdown en memoria"
    assert second["chars"] == len(target.read_text(encoding="utf-8"))


# --- serialize_budget ------------------------------------------------------------


def test_small_summary_serializes_untouched(tmp_path: Path) -> None:
    """Bajo el techo: JSON canónico tal cual (mismo `dumps` que `json_result`)."""
    payload = summary.build_summary(_written(tmp_path), source_uri="x.docx")

    text = summary.serialize_budget(payload)

    assert json.loads(text) == payload
    assert text == json.dumps(payload, ensure_ascii=False)


def test_big_preview_still_fits_under_the_ceiling(tmp_path: Path) -> None:
    """Un preview de 500 chars + las claves de cita caben en 1 400 (M3): sin recorte."""
    target = _written(tmp_path, "x" * 100_000)
    payload = summary.build_summary(
        target, source_uri="00-resources/fuentes/informe-anual-2026.docx", vault_root=tmp_path
    )

    text = summary.serialize_budget(payload)

    assert len(text) <= summary.SUMMARY_CHAR_CEILING == 1400
    assert json.loads(text) == payload


def test_oversized_summary_trims_only_the_preview(tmp_path: Path) -> None:
    """Si el resumen supera 1 400 (rutas anormalmente largas), se recorta SOLO `preview`.

    El resto de claves es el contrato: `written_to`, `source_uri`, `bytes` y
    `chars` jamás se tocan. `truncated` marca el recorte.
    """
    payload: dict[str, object] = {
        "written_to": "00-resources/" + "carpeta/" * 100 + "informe.md",
        "source_uri": "00-resources/fuentes/informe.docx",
        "bytes": 100_000,
        "chars": 100_000,
        "preview": "renglón\n" * 62,
        "truncated": True,
    }
    assert len(json.dumps(payload, ensure_ascii=False)) > 1400, "el caso debe superar el techo"

    text = summary.serialize_budget(payload)

    trimmed = json.loads(text)
    assert len(text) <= 1400
    assert trimmed["truncated"] is True
    assert trimmed["preview"] != payload["preview"], "el preview se recortó"
    assert str(trimmed["preview"]) == str(payload["preview"])[: len(str(trimmed["preview"]))]
    for key in ("written_to", "source_uri", "bytes", "chars"):
        assert trimmed[key] == payload[key]
