"""Re-chequeo TOCTOU de `app.index_file`: un archivo que crece tras el classify falla aislado."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from tepochcalli_flow import app, source


class _FakeFile:
    """`localfs.File` en duck type: solo la superficie que `index_file` consume."""

    def __init__(self, path: Path) -> None:
        self.file_path = path


def test_index_file_raises_when_file_grows_after_classify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El re-chequeo post-classify detecta el crecimiento y falla el componente por fichero."""
    nota = tmp_path / "nota.md"
    nota.write_text("1234567890", encoding="utf-8")  # >2 bytes
    monkeypatch.setattr(source, "DEFAULT_MAX_FILE_BYTES", 2)

    with pytest.raises(ValueError, match="cambió durante el pase"):
        asyncio.run(
            app.index_file(
                _FakeFile(nota),  # type: ignore[arg-type]  # duck-typed para el borde
                table=None,  # type: ignore[arg-type]  # nunca se alcanza en esta rama
                config=None,  # type: ignore[arg-type]
            )
        )
