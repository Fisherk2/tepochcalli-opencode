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
import subprocess
import sys
from pathlib import Path

from model_cache import link_model_cache, offline_env, resolve_model_cache
from tepochcalli_flow import citation
from tepochcalli_flow.layout import DB_RELPATH

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
