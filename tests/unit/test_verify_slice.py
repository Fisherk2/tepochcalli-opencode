"""Verificador CLI: resolución del `source_path` vault-relativo y identidad F1 (T2).

El verificador solo LEE: `_source_slice_ok` resuelve `vault_root / source_path`
(nunca asume `00-Resources/`) y distingue «no aplica» (extracto de un binario)
de «no reproducible» (original ausente o slice roto).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from tepochcalli_flow import verify
from tepochcalli_flow.ports import CitedChunk


def _chunk(source_path: str, text: str, document: str) -> CitedChunk:
    """Construye una cita cuyo slice reproduce `text` dentro de `document`."""
    start = document.index(text)
    return CitedChunk(
        text=text,
        source_path=source_path,
        heading=None,
        char_start=start,
        char_end=start + len(text),
        score=0.5,
    )


def test_source_slice_resolves_vault_relative_and_detects_missing_or_extract(
    tmp_path: Path,
) -> None:
    """`vault/materiales/a.md` se resuelve contra el vault; ausente ⇒ False; extract ⇒ None."""
    document = "# A\n\ncuerpo citado.\n"
    path = tmp_path / "materiales" / "a.md"
    path.parent.mkdir(parents=True)
    path.write_text(document, encoding="utf-8")
    chunk = _chunk("materiales/a.md", "cuerpo citado.", document)

    assert verify._source_slice_ok(tmp_path, chunk) is True
    assert (
        verify._source_slice_ok(tmp_path, replace(chunk, source_path="materiales/otra.md")) is False
    )
    assert verify._source_slice_ok(tmp_path, replace(chunk, offsets_ref="extract")) is None
