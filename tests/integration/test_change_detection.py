"""T5 e2e: editar la lógica del parser invalida el memo del fichero (D58/D60).

Fuentes de verdad:

* tasks/todo.md → T5 AC (a)-(c): `extract_text`, `chunk_document` y el helper de
  cita que deriva el chunk se decoran con `@coco.fn` (sin `memo=True`) para que
  su lógica entre en el fingerprint del `index_file` memoizado.
* tasks/plan.md §5.4 (D58/D60): una función plana es **invisible** al memo; el
  índice queda obsoleto en silencio al editar el parser.
* Pin `cocoindex==1.0.25`: `_compute_logic_fingerprint` hashea el AST canónico
  (`cocoindex/_internal/function.py:660-710`), cada llamada a una
  `SyncFunction` añade su fingerprint al contexto del llamador
  (`function.py:845`) y el memo guarda/valida esas deps (`function.py:950`).

**Por qué dos procesos.** La invalidación real ocurre entre despliegues: el
proceso viejo registra el fingerprint de la lógica vieja y muere; el nuevo
registra el nuevo. Cambiar la función viva dentro del MISMO proceso no invalida
(ambos fingerprints siguen registrados y el memo no re-ejecuta el cuerpo), así
que el test indexa con `v1` en un subproceso, lo deja morir y reindexa el MISMO
vault con `v2` en otro subproceso: la dep guardada ya no está registrada ⇒ el
fichero se rehace. La tercera pasada, en el proceso de `v2`, demuestra la
idempotencia (`indexed == 0`).
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

from cocoindex._internal.function import SyncFunction
from model_cache import link_model_cache, offline_env, resolve_model_cache
from tepochcalli_flow import app as flow_app
from tepochcalli_flow import citation, parsers
from tepochcalli_flow.layout import DB_RELPATH, TABLE_NAME

_SCRIPT_HEADER = """
import dataclasses, json
import cocoindex as coco
from cocoindex._internal.function import SyncFunction
from tepochcalli_flow import app as flow_app
from tepochcalli_flow import parsers

for helper in (parsers.extract_text, parsers.chunk_document, parsers._to_document_chunk):
    assert isinstance(helper, SyncFunction), f"{helper!r} no está decorado con @coco.fn"

@coco.fn
def _extract(path):
    return path.read_text(encoding="utf-8")__SUFFIX__

flow_app.extract_text = _extract

def run(tag):
    report = flow_app.refresh_blocking()
    print(json.dumps({"tag": tag, "report": dataclasses.asdict(report)}), flush=True)

run(__FIRST_TAG__)
__EXTRA_RUN__
"""

NOTE = "# Nota\n\nProsa original que el parser trocea.\n"
SENTINEL_V2 = "SENTINEL_V2"


def test_parser_helpers_are_logic_tracked_coco_functions() -> None:
    """AC (a): parser, chunker y derivación de cita son `SyncFunction` (no helpers planos).

    `SyncFunction` es la clase que produce `@coco.fn` en `cocoindex==1.0.25`
    (`cocoindex/_internal/function.py:707`). Un helper plano NO tiene
    fingerprint y su edición no invalida al llamador memoizado (D58).
    """
    for helper in (parsers.extract_text, parsers.chunk_document, parsers._to_document_chunk):
        assert isinstance(helper, SyncFunction), f"{helper!r} no está decorado con @coco.fn"


def test_index_file_extracts_via_the_decorated_helpers_as_async() -> None:
    """AC (b): `index_file` usa `extract_text.as_async` (hilo del decorador), no `to_thread`."""
    source = inspect.getsource(flow_app.index_file)

    assert "extract_text.as_async(" in source
    assert "asyncio.to_thread(extract_text" not in source


def test_editing_the_parser_logic_invalidates_the_file_memo_and_reindexes(
    tmp_path: Path,
) -> None:
    """Misma entrada, lógica distinta entre procesos ⇒ reindexado; igual ⇒ memo hit."""
    vault = tmp_path / "vault"
    resources = vault / citation.RESOURCES_DIR
    resources.mkdir(parents=True)
    (resources / "nota.md").write_text(NOTE, encoding="utf-8")
    cache = resolve_model_cache()
    models_link = link_model_cache(vault, cache)

    first = _run_driver(vault, cache, models_link, suffix="", first_tag="v1", extra_run="")
    assert first.returncode == 0, f"primer proceso falló:\n{first.stdout}\n{first.stderr}"
    v1 = _reports(first)
    assert (v1["v1"]["indexed"], v1["v1"]["scanned"]) == (1, 1)

    second = _run_driver(
        vault,
        cache,
        models_link,
        suffix=f' + "\\n\\n{SENTINEL_V2}\\n"',
        first_tag="v2",
        extra_run='run("v2-again")',
    )
    assert second.returncode == 0, f"segundo proceso falló:\n{second.stdout}\n{second.stderr}"
    reports = _reports(second)
    assert reports["v2"]["indexed"] == 1, (
        "cambiar la lógica del extractor entre despliegues debe invalidar el memo (D58)"
    )
    assert reports["v2-again"]["indexed"] == 0, "misma lógica ⇒ memo hit (idempotencia)"
    for report in (*v1.values(), *reports.values()):
        assert report["scanned"] == report["indexed"] + report["skipped"]

    rows = _read_rows(vault)
    assert rows
    assert all(SENTINEL_V2 in str(row["text"]) for row in rows), (
        "el índice debe reflejar la lógica NUEVA, no la vieja memoizada"
    )


def _run_driver(
    vault: Path,
    cache: Path,
    models_link: Path,
    *,
    suffix: str,
    first_tag: str,
    extra_run: str,
) -> subprocess.CompletedProcess[str]:
    """Indexa el vault con la variante de extractor indicada, en subproceso propio."""
    script = (
        _SCRIPT_HEADER.replace("__SUFFIX__", suffix)
        .replace("__FIRST_TAG__", json.dumps(first_tag))
        .replace("__EXTRA_RUN__", extra_run)
    )
    env = {
        **os.environ,
        "TEPOCHCALLI_VAULT_ROOT": str(vault),
        "HF_HOME": str(models_link),
        "SENTENCE_TRANSFORMERS_HOME": str(models_link),
        **offline_env(cache),
    }
    env.pop("COCOINDEX_DB", None)
    return subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )


def _reports(proc: subprocess.CompletedProcess[str]) -> dict[str, dict[str, object]]:
    """Parseo de los reportes JSON emitidos por el driver."""
    return {
        record["tag"]: record["report"]
        for line in proc.stdout.splitlines()
        if (stripped := line.strip()).startswith("{")
        for record in [json.loads(stripped)]
    }


def _read_rows(vault: Path) -> list[dict[str, object]]:
    """Lee la tabla `chunks` completa desde disco (solo lectura)."""
    import lancedb

    async def _go() -> list[dict[str, object]]:
        connection = await lancedb.connect_async(str(vault / DB_RELPATH))
        try:
            table = await connection.open_table(TABLE_NAME)
            arrow = await table.to_arrow()
            return arrow.to_pylist()
        finally:
            connection.close()

    return asyncio.run(_go())
