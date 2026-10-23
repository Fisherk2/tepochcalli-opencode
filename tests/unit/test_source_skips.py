"""Skips tipados de `source.py` fuera del walk completo (F5/T8) — caracterización + F1.

Fuentes de verdad:

* specs/spec-rag-engine.md §Fuentes — F5: `>100MB / symlink roto / ilegible →
  skipped` con motivo, sin abortar el delta. El motivo que se reporta debe ser
  el REAL: un archivo regular que desaparece en la carrera walk→classify no es
  un symlink roto (F1, defecto corregido aquí).
* specs/spec-mcp-server.md §`index_refresh` — `scanned == indexed + skipped`:
  el contador solo suma lo que el conector realmente traga (T8: symlink roto y
  directorio ilegible), nunca descartes de rutas que la whitelist excluye.

Estos tests bajan a las funciones de clasificación directas (`classify_file`,
`unvisited_skips`, `_unreadable_dir_skips`) para cubrir las ramas defensivas
que un walk completo no alcanza de forma determinista.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from tepochcalli_flow import citation, source

# --- F1: FileNotFoundError de un archivo REGULAR ≠ symlink roto ----------------


def test_classify_file_reports_a_vanished_regular_file_as_unreadable_not_a_broken_symlink(
    tmp_path: Path,
) -> None:
    """Contrato F5 + honestidad del log: desaparecido regular → `unreadable`, no `broken_symlink`.

    Un archivo regular que se borra entre el walk y el classify (carrera
    walk→classify) produce `FileNotFoundError`, pero NO es un symlink roto:
    reportarlo como `BROKEN_SYMLINK` manda al usuario a buscar links que nunca
    existieron. El motivo correcto es `UNREADABLE` y el `detail` debe decir que
    el archivo DESAPARECIÓ. El recuento no cambia (`scanned == indexed +
    skipped`); solo el motivo y el mensaje.

    El `source_path` se afirma en su forma canónica reutilizando el mismo
    criterio del walk: `citation.RESOURCES_DIR` + nombre relativo.
    """
    recursos = tmp_path / citation.RESOURCES_DIR
    recursos.mkdir(parents=True)
    desaparecido = recursos / "nota.md"
    desaparecido.write_text("# Nota\n\nprosa.\n", encoding="utf-8")
    desaparecido.unlink()  # la ruta ya no existe y NUNCA fue un symlink

    item = source.classify_file(
        recursos,
        desaparecido,
        max_file_bytes=source.DEFAULT_MAX_FILE_BYTES,
    )

    assert isinstance(item, source.SkippedSource)
    assert item.reason is source.SkipReason.UNREADABLE
    assert "desapareci" in item.detail
    assert item.detail != ""
    assert item.source_path == "00-Resources/nota.md"
    assert item.path == desaparecido


# --- TOCTOU walk→classify: el archivo cambió durante el pase -------------------


def test_classify_file_skips_unreadable_when_doc_kind_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Carrera walk→classify: si `doc_kind_for`/`normalize` lanza → skip, no aborta el pase."""
    recursos = tmp_path / citation.RESOURCES_DIR
    recursos.mkdir(parents=True)
    nota = recursos / "nota.md"
    nota.write_text("# Nota\n\nprosa.\n", encoding="utf-8")

    def _race(file_path: Path) -> citation.DocKind:
        raise ValueError("cambió durante el pase")

    monkeypatch.setattr(source, "doc_kind_for", _race)

    item = source.classify_file(recursos, nota, max_file_bytes=source.DEFAULT_MAX_FILE_BYTES)

    assert isinstance(item, source.SkippedSource)
    assert item.reason is source.SkipReason.UNREADABLE
    assert "cambió durante el pase" in item.detail


# --- T8: la regla de aceptación del `onerror` de os.walk -----------------------


def test_unvisited_skips_ignores_io_errors_that_are_not_permission_denied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contrato T8: `_onerror` solo cuenta `PermissionError` DENTRO del recurso.

    `localfs.walk_dir` traga exactamente `PermissionError` (`except
    PermissionError: continue`), así que el `onerror` de `_unreadable_dir_skips`
    debe ignorar (a) excepciones que no son `PermissionError`, (b) un
    `PermissionError` sin `filename` y (c) uno cuyo path cae fuera de
    `00-Resources/`. Se incluye el caso POSITIVO en el mismo test para que el
    doble de `os.walk` no pueda pasar vacíamente: la identidad que el contador
    preserva es «1 entrada `unreadable_dir` por cada `PermissionError` del
    conector con path dentro del recurso, y 0 por todo lo demás».
    """
    recursos = tmp_path / citation.RESOURCES_DIR
    recursos.mkdir(parents=True)
    (recursos / "sub").mkdir()
    matcher = source.build_path_matcher()

    def drive(errores: list[BaseException]) -> list[source.SkippedSource]:
        """Ejecuta `_unreadable_dir_skips` con un `os.walk` que dispara `errores`."""

        def fake_walk(
            top: str | Path,
            *,
            onerror: Callable[[OSError], None],
        ) -> list[tuple[str, list[str], list[str]]]:
            """Sustituto de `os.walk`: reporta cada error por `onerror` y no recorre nada."""
            for error in errores:
                # El hook real de os.walk solo entrega OSError; el cast reproduce la
                # entrada de una capa sustituida sin relajar la firma del doble.
                onerror(cast(OSError, error))
            return []

        monkeypatch.setattr(source.os, "walk", fake_walk)
        return source._unreadable_dir_skips(recursos, matcher)

    ignorados: list[BaseException] = [
        OSError(5, "error de E/S que el conector NO traga", str(recursos / "sub")),
        RuntimeError("fallo de otra capa"),  # ni siquiera es OSError
        PermissionError(13, "permiso denegado"),  # sin filename
        PermissionError(13, "permiso denegado", str(tmp_path / "fuera-del-recurso")),
    ]
    assert drive(ignorados) == []

    aceptado = [PermissionError(13, "permiso denegado", str(recursos / "sub"))]
    assert [(skip.source_path, skip.reason) for skip in drive(aceptado)] == [
        ("00-Resources/sub", source.SkipReason.UNREADABLE_DIR)
    ]


# --- whitelist del barrido de symlinks rotos -----------------------------------


def test_broken_symlink_outside_the_whitelist_is_not_reported_as_a_skip(tmp_path: Path) -> None:
    """Contrato F5 + whitelist: solo el symlink roto INDEXABLE cuenta como skip.

    `unvisited_skips` usa el mismo matcher que el walk: un `roto.xyz -> nada`
    está fuera de `.md/.markdown/.txt/.pdf`, así que no es un candidato y
    tampoco un descarte. Reportarlo inflaría `scanned`/`skipped` con archivos
    que la spec nunca consideró.
    """
    recursos = tmp_path / citation.RESOURCES_DIR
    recursos.mkdir(parents=True)
    try:
        (recursos / "roto.md").symlink_to(recursos / "objetivo_inexistente.md")
        (recursos / "roto.xyz").symlink_to(recursos / "objetivo_inexistente.xyz")
    except (OSError, NotImplementedError) as exc:  # pragma: no cover - FS sin symlinks
        pytest.skip(f"el filesystem no soporta symlinks: {exc}")

    skips = source.unvisited_skips(recursos)

    assert [(skip.source_path, skip.reason) for skip in skips] == [
        ("00-Resources/roto.md", source.SkipReason.BROKEN_SYMLINK)
    ]
