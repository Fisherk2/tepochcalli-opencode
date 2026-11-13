"""T2: índice multi-raíz y cita vault-relativa (ADR-010 §4.2/§4.4/§4.5/§4.7/§4.9).

Fuentes de verdad: `specs/spec-rag-engine.md` §Fuentes (§Raíces), §Target
LanceDB; `specs/spec-vault-structure.md` §Raíces del índice; ADR-010.

Se prueban aquí las reglas del walk sin engine: validación antes del disco,
recursión, raíz-fichero, dedup, poda de directorios-punto, frontera de symlink
igual al vault y la identidad de memo de cada `FilePath` (D62).
"""

from __future__ import annotations

import asyncio
from pathlib import Path, PurePosixPath

import pytest
from cocoindex.connectors import localfs
from tepochcalli_flow import citation, models, source


def _entries(items: list[source.WalkItem]) -> list[source.SourceEntry]:
    """Filtra las entradas indexables del pase."""
    return [item for item in items if isinstance(item, source.SourceEntry)]


def _scan(vault: Path, roots: list[str] | None = None) -> tuple[list[source.WalkItem], int]:
    """Corre `scan_items` en su propio loop (el walk real es asíncrono)."""
    return asyncio.run(source.scan_items(vault, roots))


# --- (b) validación de N raíces ANTES del disco ---------------------------------


def test_walk_sources_rejects_a_missing_root_with_the_typed_error_before_any_walk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Raíz inexistente ⇒ `FileNotFoundError` y el walk NUNCA se ejecuta (D44/D65)."""

    def _must_not_walk(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("el walk no debe ejecutarse antes de validar las raíces")

    monkeypatch.setattr(source, "_connector_candidates", _must_not_walk)
    monkeypatch.setattr(source, "unvisited_skips", _must_not_walk)

    with pytest.raises(FileNotFoundError, match="no-existe"):
        source.walk_sources(tmp_path, ["no-existe"])


def test_walk_sources_rejects_roots_outside_the_vault_before_touching_the_disk(
    tmp_path: Path,
) -> None:
    """Raíz absoluta o con `..` que escapa ⇒ `ValueError` antes de mirar el disco."""
    vault = tmp_path / "vault"
    vault.mkdir()

    with pytest.raises(ValueError):
        source.walk_sources(vault, ["../fuera"])
    with pytest.raises(ValueError):
        source.walk_sources(vault, [str(tmp_path / "absoluta")])


def test_walk_sources_rejects_a_root_symlink_that_escapes_the_vault(tmp_path: Path) -> None:
    """Una raíz que es un symlink fuera del vault se rechaza (frontera D47)."""
    vault = tmp_path / "vault"
    vault.mkdir()
    fuera = tmp_path / "fuera"
    fuera.mkdir()
    (fuera / "x.md").write_text("# X\n\nfuera.\n", encoding="utf-8")
    try:
        (vault / "materiales").symlink_to(fuera, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:  # pragma: no cover - FS sin symlinks
        pytest.skip(f"el filesystem no soporta symlinks: {exc}")

    with pytest.raises(ValueError, match="materiales"):
        source.walk_sources(vault, ["materiales"])


# --- (c) recursión a cualquier profundidad ---------------------------------------


def test_walk_sources_recurses_to_any_depth_across_several_roots(tmp_path: Path) -> None:
    """`materiales/1-geografia/x.pdf` y `documentos/pdf/y.pdf` se indexan (D46)."""
    vault = tmp_path / "vault"
    (vault / "materiales" / "1-geografia").mkdir(parents=True)
    (vault / "documentos" / "pdf").mkdir(parents=True)
    (vault / "00-resources").mkdir()
    (vault / "materiales" / "1-geografia" / "x.pdf").write_bytes(b"%PDF fake")
    (vault / "documentos" / "pdf" / "y.pdf").write_bytes(b"%PDF fake")
    (vault / "00-resources" / "nota.md").write_text("# Nota\n\nfuera del pase.\n", encoding="utf-8")

    items = source.walk_sources(vault, ["materiales", "documentos"])

    assert [entry.source_path for entry in _entries(items)] == [
        "documentos/pdf/y.pdf",
        "materiales/1-geografia/x.pdf",
    ]
    assert [entry.doc_kind for entry in _entries(items)] == ["pdf", "pdf"]


# --- (d) y (m): raíz = fichero suelto, nunca a walk_dir ---------------------------


def test_walk_sources_emits_a_file_root_without_passing_it_to_walk_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Una raíz-fichero se emite como entrada única; `walk_dir` no la recibe (D46)."""
    vault = tmp_path / "vault"
    (vault / "notas").mkdir(parents=True)
    (vault / "notas" / "suelta.md").write_text("# Suelta\n\nprosa.\n", encoding="utf-8")

    def _must_not_walk(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("una raíz-fichero NUNCA se pasa a walk_dir (lanza ValueError)")

    monkeypatch.setattr(source, "_connector_candidates", _must_not_walk)

    items = source.walk_sources(vault, ["notas/suelta.md"])

    assert [(entry.source_path, entry.doc_kind) for entry in _entries(items)] == [
        ("notas/suelta.md", "md")
    ]
    assert not [item for item in items if isinstance(item, source.SkippedSource)]


# --- (e) dedup de raíces solapadas ------------------------------------------------


@pytest.mark.parametrize(
    "roots",
    [
        ["00-resources", "00-resources/sub"],
        ["00-resources/sub", "00-resources"],
        ["00-resources"] * 2,
    ],
)
def test_walk_sources_deduplicates_overlapping_roots_and_keeps_the_count_identity(
    tmp_path: Path, roots: list[str]
) -> None:
    """Raíces solapadas o repetidas cuentan cada archivo UNA vez (D46)."""
    vault = tmp_path / "vault"
    recursos = vault / citation.RESOURCES_DIR
    (recursos / "sub").mkdir(parents=True)
    (recursos / "a.md").write_text("# A\n\nprosa.\n", encoding="utf-8")
    (recursos / "sub" / "b.md").write_text("# B\n\nprosa.\n", encoding="utf-8")

    items, scanned = _scan(vault, roots)

    entries = _entries(items)
    assert scanned == len(items) == 2
    assert sorted(entry.source_path for entry in entries) == [
        "00-resources/a.md",
        "00-resources/sub/b.md",
    ]


# --- (f) `source_path` vault-relativo y frontera de symlink = vault ---------------


def test_classify_file_cites_vault_relative_paths(tmp_path: Path) -> None:
    """La cita del classify es el path relativo al vault, no al recurso pedido."""
    vault = tmp_path / "vault"
    documento = vault / "materiales" / "1-geografia" / "clima.md"
    documento.parent.mkdir(parents=True)
    documento.write_text("# Clima\n\nprosa.\n", encoding="utf-8")

    item = source.classify_file(vault, documento, max_file_bytes=source.DEFAULT_MAX_FILE_BYTES)

    assert isinstance(item, source.SourceEntry)
    assert item.source_path == "materiales/1-geografia/clima.md"


def test_a_symlink_between_roots_inside_the_vault_is_indexable(tmp_path: Path) -> None:
    """Un link de `documentos/` a `materiales/` es legítimo: ambos dentro del vault (D47)."""
    vault = tmp_path / "vault"
    (vault / "materiales").mkdir(parents=True)
    (vault / "documentos").mkdir()
    (vault / "materiales" / "x.md").write_text("# X\n\nprosa.\n", encoding="utf-8")
    try:
        (vault / "documentos" / "enlace.md").symlink_to(vault / "materiales" / "x.md")
    except (OSError, NotImplementedError) as exc:  # pragma: no cover - FS sin symlinks
        pytest.skip(f"el filesystem no soporta symlinks: {exc}")

    item = source.classify_file(
        vault, vault / "documentos" / "enlace.md", max_file_bytes=source.DEFAULT_MAX_FILE_BYTES
    )

    assert isinstance(item, source.SourceEntry)
    assert item.source_path == "documentos/enlace.md"


# --- (g) y (l) identidad de memo por raíz -----------------------------------------


def test_file_path_memo_key_does_not_depend_on_the_vault_location() -> None:
    """`FilePath` con `base_dir=ROOT_KEY` memoiza por (clave, relativo), no por ruta (D62)."""
    assert models.ROOT_KEY.key == "tepochcalli_root"
    path = localfs.FilePath("materiales/a.md", base_dir=models.ROOT_KEY)

    assert path.base_dir is models.ROOT_KEY  # `base_dir` explícito, nunca un Path pelado
    assert path.__coco_memo_key__() == (models.ROOT_KEY.key, PurePosixPath("materiales/a.md"))
    # Mismo relativo + misma clave ⇒ misma clave de memo aunque el vault se mueva.
    assert (
        localfs.FilePath("materiales/a.md", base_dir=models.ROOT_KEY).__coco_memo_key__()
        == path.__coco_memo_key__()
    )


# --- (n) la exclusión PODA los directorios-punto ----------------------------------


def test_walk_sources_pruning_excludes_dot_directories_when_indexing_the_vault_root(
    tmp_path: Path,
) -> None:
    """Raíz = vault: `.tepochcalli/` y `.obsidian/` no producen filas (ADR-010 §4.9)."""
    vault = tmp_path / "vault"
    (vault / ".tepochcalli").mkdir(parents=True)
    (vault / ".obsidian").mkdir()
    (vault / "nota.md").write_text("# Nota\n\nprosa.\n", encoding="utf-8")
    (vault / ".tepochcalli" / "interna.md").write_text("# Interna\n\nprosa.\n", encoding="utf-8")
    (vault / ".obsidian" / "config.md").write_text("# Config\n\nprosa.\n", encoding="utf-8")

    items = source.walk_sources(vault, ["."])

    assert [entry.source_path for entry in _entries(items)] == ["nota.md"]
    assert not [item for item in items if isinstance(item, source.SkippedSource)]


# --- (o) los bucles de symlink los corta el conector ------------------------------


def test_a_symlink_directory_loop_terminates_without_a_visited_set(tmp_path: Path) -> None:
    """Un directorio con un link a sí mismo termina el walk (cadena de ancestros, D62)."""
    vault = tmp_path / "vault"
    recursos = vault / citation.RESOURCES_DIR
    recursos.mkdir(parents=True)
    (recursos / "nota.md").write_text("# Nota\n\nprosa.\n", encoding="utf-8")
    try:
        (recursos / "loop").symlink_to(recursos, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:  # pragma: no cover - FS sin symlinks
        pytest.skip(f"el filesystem no soporta symlinks: {exc}")

    items = source.walk_sources(vault)

    assert [entry.source_path for entry in _entries(items)] == ["00-resources/nota.md"]
