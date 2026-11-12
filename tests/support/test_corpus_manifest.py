"""Tests del manifiesto del corpus de escala (Phase 6, T1) — escritos en rojo antes.

Fuentes de verdad:

* tasks/plan.md §5 T1 — corpus determinista 10 000 md + 1 000 PDF con
  `corpus-manifest.json` (ruta relativa, sha256, bytes, tipo + `seed`,
  `generator_version`, totales), reproducible y reutilizable sin reindexar.
* tasks/todo.md T1 — dos materializaciones ⇒ manifiesto idéntico (hash del
  árbol, no comparación de carpetas); el manifiesto verificado salta la
  materialización; `obsidian-workspace/.tepochcalli/{db,models}` intactos.

El corpus de estos tests es **diminuto** (parámetros) para caber en <2 s: la
escala real (10k/1k) es una medición one-shot, nunca un test.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from corpus import MANIFEST_NAME, materialize, materialize_or_verify, verify

MD_COUNT = 5
PDF_COUNT = 3
SEED = 424242


def test_manifest_has_one_entry_per_file_with_hashes(tmp_path: Path) -> None:
    """Manifiesto: metadatos globales + por fichero `path`/`sha256`/`bytes`/`kind`."""
    manifest = materialize(tmp_path, md_count=MD_COUNT, pdf_count=PDF_COUNT, seed=SEED)
    data = json.loads((tmp_path / MANIFEST_NAME).read_text(encoding="utf-8"))

    assert data["seed"] == SEED
    assert data["generator_version"] == manifest.generator_version
    assert data["totals"]["md"] == MD_COUNT
    assert data["totals"]["pdf"] == PDF_COUNT
    assert data["totals"]["files"] == MD_COUNT + PDF_COUNT
    assert len(data["files"]) == MD_COUNT + PDF_COUNT

    paths = [entry["path"] for entry in data["files"]]
    assert paths == sorted(paths), "las entradas van ordenadas por ruta (manifiesto canónico)"
    for entry in data["files"]:
        assert set(entry) == {"path", "sha256", "bytes", "kind"}
        assert not entry["path"].startswith("/"), "path relativo a la raíz del corpus"
        file_path = tmp_path / entry["path"]
        payload = file_path.read_bytes()
        assert hashlib.sha256(payload).hexdigest() == entry["sha256"]
        assert len(payload) == entry["bytes"]
        assert entry["kind"] == file_path.suffix.lstrip(".")


def test_two_materializations_with_the_same_seed_are_identical(tmp_path: Path) -> None:
    """Misma seed ⇒ mismo JSON canónico y mismo hash de árbol (no se comparan carpetas)."""
    first = materialize(tmp_path / "a", md_count=MD_COUNT, pdf_count=PDF_COUNT, seed=SEED)
    second = materialize(tmp_path / "b", md_count=MD_COUNT, pdf_count=PDF_COUNT, seed=SEED)

    assert first.canonical_json() == second.canonical_json()
    assert first.tree_sha256 == second.tree_sha256
    # Canónico = `sort_keys=True` y sin espacios, sin timestamps ni rutas absolutas dentro.
    assert first.canonical_json() == json.dumps(
        json.loads(first.canonical_json()), sort_keys=True, separators=(",", ":")
    )
    assert str(tmp_path) not in first.canonical_json()


def test_valid_manifest_is_reused_without_rewriting(tmp_path: Path) -> None:
    """Un manifiesto válido se verifica y salta la materialización (mtime_ns intacto)."""
    materialize(tmp_path, md_count=MD_COUNT, pdf_count=PDF_COUNT, seed=SEED)
    before = _mtimes(tmp_path)

    manifest, reused = materialize_or_verify(
        tmp_path, md_count=MD_COUNT, pdf_count=PDF_COUNT, seed=SEED
    )

    assert reused is True
    assert verify(tmp_path, manifest) == []
    assert _mtimes(tmp_path) == before, "la reutilización no reescribe ningún fichero"


def test_missing_manifest_materializes_the_corpus(tmp_path: Path) -> None:
    """Sin manifiesto previo se materializa (y se declara que no fue reutilización)."""
    manifest, reused = materialize_or_verify(
        tmp_path, md_count=MD_COUNT, pdf_count=PDF_COUNT, seed=SEED
    )

    assert reused is False
    assert len(manifest.files) == MD_COUNT + PDF_COUNT
    assert (tmp_path / MANIFEST_NAME).is_file()


def test_tampered_file_invalidates_the_manifest(tmp_path: Path) -> None:
    """Un fichero alterado ⇒ verificación con discrepancias y NUNCA regeneración silenciosa."""
    manifest = materialize(tmp_path, md_count=MD_COUNT, pdf_count=PDF_COUNT, seed=SEED)
    victim = tmp_path / manifest.files[0].path
    victim.write_text("alterado fuera del generador\n", encoding="utf-8")

    problems = verify(tmp_path, manifest)

    assert problems, "la alteración debe detectarse"
    assert any(manifest.files[0].path in problem for problem in problems)
    with pytest.raises(RuntimeError):
        materialize_or_verify(tmp_path, md_count=MD_COUNT, pdf_count=PDF_COUNT, seed=SEED)
    assert victim.read_text(encoding="utf-8") == "alterado fuera del generador\n"


def _mtimes(root: Path) -> dict[str, int]:
    """`mtime_ns` de todo el árbol: la prueba de que la reutilización no escribe."""
    return {
        path.relative_to(root).as_posix(): path.stat().st_mtime_ns
        for path in root.rglob("*")
        if path.is_file()
    }
