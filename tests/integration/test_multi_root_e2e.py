"""T2 e2e: índice multi-raíz con `source_path` relativo al vault (ADR-010 §4.10).

Fuente de verdad: `specs/spec-rag-engine.md` §Fuentes/§Target,
`specs/spec-vault-structure.md` §Raíces del índice y ADR-010 §4.10:

* `refresh_blocking(directories=[...])` indexa N raíces recursivamente.
* `source_path` es relativo al VAULT (`materiales/…`, `documentos/…`), no a la
  raíz pedida.
* El slice del fichero ORIGINAL reproduce `text` (identidad F1) con el
  `source_path` nuevo.
* `RefreshReport.roots` es aditivo; `scanned == indexed + skipped`.

El update corre en SUBPROCESO (environment global de cocoindex, patrón T9/T8);
el cache de modelo queda fuera del repo (`model_cache`, T11).
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from model_cache import link_model_cache, offline_env, resolve_model_cache
from support.mcp_server import running_server, server_env
from tepochcalli_flow import citation, parsers
from tepochcalli_flow.layout import DB_RELPATH

FIXTURE_PDF = Path(__file__).parents[1] / "fixtures" / "pdf" / "articulo_t7.pdf"
"""PDF real de 1 página con texto extraíble (fixture compartido con T3/T11)."""

CLIMA = "# Clima\n\nLa aridez del altiplano condiciona el calendario agrícola.\n"
ARTICULO = "# Artículo\n\nTexto del artículo que vive bajo documentos/pdf.\n"
NOTA = "# Nota\n\nMaterial por omisión del vault.\n"

REFRESH_SCRIPT = """
import dataclasses, json
from tepochcalli_flow.app import refresh_blocking
report = refresh_blocking(directories=["materiales", "documentos"])
print(json.dumps(dataclasses.asdict(report)), flush=True)
"""


def test_custom_roots_are_indexed_recursively_with_vault_relative_citations(
    tmp_path: Path,
) -> None:
    """`materiales/1-geografia/clima.md` y `documentos/pdf/articulo.md` entran con su ruta."""
    vault = tmp_path / "vault"
    (vault / "materiales" / "1-geografia").mkdir(parents=True)
    (vault / "documentos" / "pdf").mkdir(parents=True)
    resources = vault / citation.RESOURCES_DIR
    resources.mkdir()
    (resources / "nota.md").write_text(NOTA, encoding="utf-8")
    (vault / "materiales" / "1-geografia" / "clima.md").write_text(CLIMA, encoding="utf-8")
    (vault / "documentos" / "pdf" / "articulo.md").write_text(ARTICULO, encoding="utf-8")

    cache = resolve_model_cache()
    models_link = link_model_cache(vault, cache)
    env = {
        **os.environ,
        "TEPOCHCALLI_VAULT_ROOT": str(vault),
        "HF_HOME": str(models_link),
        "SENTENCE_TRANSFORMERS_HOME": str(models_link),
        **offline_env(cache),
    }
    env.pop("COCOINDEX_DB", None)
    proc = subprocess.run(
        [sys.executable, "-c", REFRESH_SCRIPT],
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert proc.returncode == 0, f"refresh multi-raíz falló:\n{proc.stdout}\n{proc.stderr}"
    report = json.loads(proc.stdout.strip().splitlines()[-1])

    assert report["roots"] == ["materiales", "documentos"]
    assert (report["scanned"], report["indexed"], report["skipped"]) == (2, 2, 0)
    assert report["scanned"] == report["indexed"] + report["skipped"]

    rows = _read_rows(vault)
    by_source = {str(row["source_path"]): row for row in rows}
    assert set(by_source) == {
        "materiales/1-geografia/clima.md",
        "documentos/pdf/articulo.md",
    }
    for source_path, row in by_source.items():
        document = (vault / source_path).read_text(encoding="utf-8")
        assert citation.verify_slice_identity(
            document,
            int(str(row["char_start"])),
            int(str(row["char_end"])),
            str(row["text"]),
        ), f"identidad F1 rota en {source_path}"
        assert row["doc_kind"] == "md"


REFRESH_ROOTS_SCRIPT = """
import dataclasses, json
from tepochcalli_flow.app import refresh_blocking
print(json.dumps(dataclasses.asdict(refresh_blocking(directories={roots!r}))), flush=True)
"""


def _refresh_roots(vault: Path, roots: list[str]) -> tuple[dict[str, object], Path]:
    """Indexa `roots` en subproceso y devuelve `(report, symlink de modelos)`."""
    cache = resolve_model_cache()
    models_link = link_model_cache(vault, cache)
    env = {
        **os.environ,
        "TEPOCHCALLI_VAULT_ROOT": str(vault),
        "HF_HOME": str(models_link),
        "SENTENCE_TRANSFORMERS_HOME": str(models_link),
        **offline_env(cache),
    }
    env.pop("COCOINDEX_DB", None)
    proc = subprocess.run(
        [sys.executable, "-c", REFRESH_ROOTS_SCRIPT.format(roots=roots)],
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert proc.returncode == 0, f"refresh de raíces falló:\n{proc.stdout}\n{proc.stderr}"
    return json.loads(proc.stdout.strip().splitlines()[-1]), models_link


def test_a_pdf_under_a_nested_root_is_cited_vault_relative_with_extract_offsets(
    tmp_path: Path,
) -> None:
    """`materiales/1-geografia/x.pdf`: cita vault-relativa y slice del extracto.

    `offsets_ref="extract"` porque el binario no es el espacio de cita (D50).
    """
    vault = tmp_path / "vault"
    target = vault / "materiales" / "1-geografia"
    target.mkdir(parents=True)
    shutil.copy(FIXTURE_PDF, target / "x.pdf")

    report, models_link = _refresh_roots(vault, ["materiales"])
    assert report["roots"] == ["materiales"]

    rows = _read_rows(vault)
    by_source = {str(row["source_path"]): row for row in rows}
    assert set(by_source) == {"materiales/1-geografia/x.pdf"}
    row = by_source["materiales/1-geografia/x.pdf"]
    assert row["doc_kind"] == "pdf"
    assert citation.offsets_ref_for("pdf") == "extract"
    extracted = parsers.extract_text(vault / "materiales" / "1-geografia" / "x.pdf")
    assert citation.verify_slice_identity(
        extracted,
        int(str(row["char_start"])),
        int(str(row["char_end"])),
        str(row["text"]),
    ), "el slice del extracto reproduce el texto de la fila"

    async def search() -> dict[str, object]:
        async with running_server(server_env(vault, models_link)) as session:
            result = await session.call_tool("search", {"query": "Tepochcalli Fixture Document"})
            assert not result.is_error, result.content[0].text
            return json.loads(result.content[0].text)

    payload = asyncio.run(search())
    results = payload["results"]
    assert isinstance(results, list) and results
    assert {str(item["source_path"]) for item in results} == {"materiales/1-geografia/x.pdf"}
    assert all(item["offsets_ref"] == "extract" for item in results)


def test_a_file_root_indexes_only_that_file(tmp_path: Path) -> None:
    """Una raíz puede ser un fichero suelto: solo entra el fichero pedido (D46)."""
    vault = tmp_path / "vault"
    (vault / "materiales").mkdir(parents=True)
    (vault / "materiales" / "a.md").write_text("# A\n\nprosa.\n", encoding="utf-8")
    (vault / "materiales" / "b.md").write_text("# B\n\nprosa.\n", encoding="utf-8")

    report, _models = _refresh_roots(vault, ["materiales/a.md"])

    assert report["roots"] == ["materiales/a.md"]
    assert report["scanned"] == 1
    rows = _read_rows(vault)
    assert {str(row["source_path"]) for row in rows} == {"materiales/a.md"}


def test_overlapping_roots_count_each_file_once(tmp_path: Path) -> None:
    """Raíces solapadas (`materiales` + `materiales/1-geografia`) cuentan cada fichero una vez."""
    vault = tmp_path / "vault"
    (vault / "materiales" / "1-geografia").mkdir(parents=True)
    (vault / "materiales" / "a.md").write_text("# A\n\nprosa.\n", encoding="utf-8")
    (vault / "materiales" / "1-geografia" / "b.md").write_text("# B\n\nprosa.\n", encoding="utf-8")

    report, _models = _refresh_roots(vault, ["materiales", "materiales/1-geografia"])

    assert report["scanned"] == 2, "cada fichero cuenta una vez aunque las raíces se solapen"
    rows = _read_rows(vault)
    assert {str(row["source_path"]) for row in rows} == {
        "materiales/a.md",
        "materiales/1-geografia/b.md",
    }


def _read_rows(vault: Path) -> list[dict[str, object]]:
    """Lee la tabla `chunks` completa desde el disco (solo lectura)."""
    import lancedb

    async def _go() -> list[dict[str, object]]:
        connection = await lancedb.connect_async(str(vault / DB_RELPATH))
        try:
            table = await connection.open_table("chunks")
            arrow = await table.to_arrow()
            return arrow.to_pylist()
        finally:
            connection.close()

    return asyncio.run(_go())
