"""T7 (D31/D66): el escritor atómico e idempotente — la MISMA función que usa `add_source`.

Fuentes de verdad:

* tasks/todo.md T7 AC (f), (k) — `writer.write_atomic` sube de
  `tools/add_source.py` (no se duplica); destino con bytes idénticos ⇒ no se
  escribe y se devuelve el mismo path; con bytes distintos ⇒ error tipado
  («elige otro `output_path`») y NUNCA se sobrescribe.
* ADR-009 D66 — la idempotencia es la única semántica que hace seguro
  reintentar sin parámetro `overwrite`.
* ADR-011 D63 — `write_atomic` es nuestro (el `declare_file` de cocoindex es
  *target state* del índice, no una escritura en disco).

Los dos tests de fallo del rename viven aquí desde T7: probaban
`handler._write_atomic`, que ya no existe — la función es una sola.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from tepochcalli_mcp import writer
from tepochcalli_mcp.tools import add_source

CONTENT = "# Nota\n\ncuerpo único\n"

REPORT = {"scanned": 1, "indexed": 1, "skipped": 0, "elapsed_ms": 5, "locked": False}
"""Reporte Δ con la forma `asdict(RefreshReport)` (la que el handler espera)."""


def _target(tmp_path: Path) -> Path:
    """Destino dentro de un `00-Resources/` real (el temporal va al MISMO directorio)."""
    directory = tmp_path / "00-Resources"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "informe.md"


# --- escritura atómica -----------------------------------------------------------


def test_writes_the_file_and_returns_its_path(tmp_path: Path) -> None:
    """Camino feliz: contenido UTF-8 en el destino, sin temporales huérfanos."""
    target = _target(tmp_path)

    written = writer.write_atomic(target, CONTENT)

    assert written == target
    assert target.read_text(encoding="utf-8") == CONTENT
    assert sorted(p.name for p in target.parent.iterdir()) == ["informe.md"]


def test_temporary_is_cleaned_up_and_the_error_reraised(tmp_path: Path) -> None:
    """Fallo ANTES del rename ⇒ el `.tmp` se limpia (si no, el walk lo indexaría)."""
    target = _target(tmp_path)

    def _broken_replace(_src: object, _dst: object) -> None:
        raise OSError("cross-device link")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(writer.os, "replace", _broken_replace)
        with pytest.raises(OSError, match="cross-device"):
            writer.write_atomic(target, CONTENT)

    assert not target.exists(), "el destino no existe: el rename no llegó a correr"
    assert list(target.parent.iterdir()) == [], "el temporal se limpia en la rama de fallo"


def test_refuses_to_overwrite_a_target_with_different_bytes(tmp_path: Path) -> None:
    """D66: contenido distinto ⇒ error con nombre alternativo; el original intacto."""
    target = _target(tmp_path)
    target.write_text("previa editada a mano\n", encoding="utf-8")

    with pytest.raises(writer.paths.VaultPathError) as excinfo:
        writer.write_atomic(target, CONTENT)

    assert "output_path" in str(excinfo.value)
    assert excinfo.value.details is not None
    assert excinfo.value.details["requested"] == "informe.md"
    assert excinfo.value.details["exists"] is True
    assert excinfo.value.details["suggested"] == "informe-2.md"
    assert target.read_text(encoding="utf-8") == "previa editada a mano\n"


def test_a_directory_at_the_destination_is_a_validation_error(tmp_path: Path) -> None:
    """Un directorio donde un fichero ⇒ error corregible, no `IsADirectoryError` ⇒ INTERNAL."""
    target = _target(tmp_path)
    target.mkdir()

    with pytest.raises(writer.paths.VaultPathError) as excinfo:
        writer.write_atomic(target, CONTENT)

    assert excinfo.value.details is not None
    assert excinfo.value.details["expected"] == "file"
    assert excinfo.value.details["found"] == "directory"


# --- idempotencia (D66) ----------------------------------------------------------


def test_identical_bytes_are_not_rewritten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mismos bytes ⇒ devuelve el mismo path SIN tocar el disco (ni el mtime)."""
    target = _target(tmp_path)
    first = writer.write_atomic(target, CONTENT)
    stamp = target.stat().st_mtime_ns

    def _bomb(*_args: object) -> None:
        raise AssertionError("no debe reescribirse un destino idéntico")

    monkeypatch.setattr(writer.os, "replace", _bomb)
    second = writer.write_atomic(target, CONTENT)

    assert second == first
    assert target.stat().st_mtime_ns == stamp
    assert target.read_text(encoding="utf-8") == CONTENT


# --- una sola implementación (el escritor es compartido con `add_source`) --------


def test_add_source_uses_the_shared_writer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`add_source` NO tiene copia: llama a `writer.write_atomic` (AC (f))."""
    calls: list[Path] = []
    real = writer.write_atomic

    def _spy(target: Path, content: str) -> Path:
        calls.append(target)
        return real(target, content)

    monkeypatch.setattr(writer, "write_atomic", _spy)

    payload = asyncio.run(
        add_source.add_source(
            (tmp_path / "staging" / "notas.md").as_uri(),
            None,
            vault_root=lambda: tmp_path,
            convert=lambda _uri: CONTENT,
            refresh=lambda: dict(REPORT),
            embedder_available=lambda: True,
        )
    )

    assert payload["ok"] is True
    assert calls == [(tmp_path / "00-Resources" / "_inbox" / "notas.md").resolve()]
    assert not hasattr(add_source, "_write_atomic"), "la implementación se movió, no se copió"
