"""T8: semántica incremental Δ, lock de un solo proceso y métricas del refresh.

Fuentes de verdad:

* specs/spec-mcp-server.md §Tool `index_refresh` — contrato congelado
  `{scanned, indexed, skipped, elapsed_ms, locked}` que Phase 2 serializa tal
  cual; `locked:true` equivale a no haber ejecutado update alguno.
* specs/spec-rag-engine.md §Semántica incremental — la 2ª pasada sin cambios no
  reescribe nada (criterio 2, Δ<30s); F5 «nunca aborta» extendido al TOCTOU
  classify→read (hallazgo #5 de CP-B): un fichero que desaparece o falla
  (no-UTF-8) queda CONTADO, no perdido en un log.
* tasks/todo.md → T8 AC — los cinco escenarios (add/modify/delete/idempotencia/
  lock), lock probado sin ESCRITURA, reloj monotónico, retorno tipado sin
  `Any`, aislamiento por fichero y las dos cuentas que no podían mentir:
  fichero no-UTF-8 y directorio ilegible.

Decisiones de test, documentadas a propósito:

* **El journey entero corre en UN subproceso** (patrón T9): `refresh_blocking`
  usa el environment global de cocoindex; pasadas sucesivas EN EL MISMO proceso
  y con el mismo vault sí funcionan (sonda T8), pero una llamada desde el
  proceso de pytest reutilizaría el environment ya arrancado para OTRO vault y
  escribiría en el equivocado. El driver ejecuta la secuencia completa
  (add → modify → delete → idempotencia → fallos → stale-lock) y emite un JSON
  por paso con su `RefreshReport`, sus filas SIN embedding y el snapshot de
  LanceDB; los tests afirman desde el padre.
* **El cache de modelo FUERA del repo** (patrón T6/T9): symlink
  `.tepochcalli/models` → el cache que resuelve `model_cache` (`HF_HOME`
  externo > spike T1 si existe > `~/.cache/huggingface`); el payload
  `obsidian-workspace/.tepochcalli/{db,models}` jamás se crea. La ruta del
  spike NO es un requisito: en frío (runner limpio) el hijo descarga una vez
  al cache externo, después corre con `HF_HUB_OFFLINE=1` (T11).
* **Idempotencia leída del data plane**: `indexed=0` en la 2ª pasada procede del
  componente `index_file` (`num_adds + num_reprocesses`), nunca del total de la
  pasada — la traversa `build_flow` reporta `reprocess=1` por diseño (E2), así
  que leer el total mentiría.
* **El lock se prueba reteniéndolo desde el padre**: el subproceso bloqueado no
  solo devuelve `locked:true`; NO ARRANCA el update — el snapshot byte a byte
  (mtime_ns + size) de `.tepochcalli/db/` antes/después lo prueba.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import subprocess
import sys
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, get_type_hints

import pytest
from cocoindex.connectors import lancedb
from model_cache import link_model_cache, offline_env, resolve_model_cache
from tepochcalli_flow import app as flow_app
from tepochcalli_flow import citation
from tepochcalli_flow import models as flow_models
from tepochcalli_flow.layout import DB_RELPATH

# Contenidos del journey: ficheros cortos, SIEMPRE de UN chunk, para que el
# número de filas por source_path sea 1 y las comparaciones sean exactas.
ALPHA_V1 = (
    "# Alpha\n\n"
    "La nota alpha cubre citas con offsets de carácter exactos e identidad F1.\n\n"
    "## Sección alpha\n\n"
    "Segundo párrafo de alpha para el chunk bajo el heading padre.\n"
)
ALPHA_V2 = (
    "# Alpha\n\n"
    "CONTENIDO REESCRITO: la segunda versión de alpha demuestra que solo SUS "
    "chunks se rehacen.\n\n"
    "## Sección alpha\n\n"
    "Más texto nuevo de alpha tras la modificación.\n"
)
BETA = "# Beta\n\nLa nota beta describe el walk filtrado y los skips tipados F5.\n"
GAMMA = "# Gamma\n\nLa nota gamma nace en el paso add: solo sus chunks deben aparecer.\n"
SANO = "# Sano\n\nArchivo UTF-8 sano que sí se indexa junto al latin-1 en el mismo refresh.\n"
EFIMERO_V1 = "# Efímero\n\nPrimera versión: se indexa y luego desaparece a mitad de pasada.\n"
EFIMERO_V2 = "# Efímero\n\nSegunda versión (mtime nuevo ⇒ re-ejecución) y después se borra.\n"
LATIN1_BYTES = b"caf\xe9 latin-1: bytes invalidos UTF-8\n"
"""Latin-1 real: 0xe9 no es UTF-8 válido ⇒ `errors='strict'` lanza en index_file."""
INTERNA = "# Interna\n\nVive tras un directorio ilegible; jamás debe indexarse.\n"

JOURNEY_TAGS = (
    "initial",
    "add",
    "modify",
    "delete",
    "idempotent",
    "nonutf8",
    "unreadable",
    "efimero-add",
    "vanish",
    "reconcile",
    "stale",
)

EXPECTED_COUNTS = {
    # tag: (scanned, indexed, skipped) — la cuenta exacta de cada pasada (T8).
    # Recuento: alpha+beta iniciales; gamma desde add; latin1+sano desde nonutf8;
    # prohibida/ (dir ilegible) + roto.md (symlink roto) desde unreadable;
    # efímero desde efimero-add y fuera tras reconcile.
    "initial": (2, 2, 0),
    "add": (3, 1, 2),
    "modify": (3, 1, 2),
    "delete": (2, 0, 2),
    "idempotent": (2, 0, 2),
    "nonutf8": (4, 1, 3),
    "unreadable": (6, 0, 6),
    "efimero-add": (7, 1, 6),
    "vanish": (7, 0, 7),
    "reconcile": (6, 0, 6),
    "stale": (6, 0, 6),
}

REPORT_FIELDS = ["scanned", "indexed", "skipped", "elapsed_ms", "locked"]

RESOURCE_DIR_NAME = citation.RESOURCES_DIR

JOURNEY_SCRIPT = """
import asyncio, dataclasses, json, os, sys
from pathlib import Path
from cocoindex.connectors import lancedb
from tepochcalli_flow import app as flow_app

VAULT = Path(os.environ["TEPOCHCALLI_VAULT_ROOT"])
RES = VAULT / "00-Resources"
DB = VAULT / ".tepochcalli" / "db" / "tepochcalli.lance"
LOCK = VAULT / flow_app.LOCK_RELPATH

ALPHA_V1 = (
    "# Alpha\\n\\n"
    "La nota alpha cubre citas con offsets de carácter exactos e identidad F1.\\n\\n"
    "## Sección alpha\\n\\n"
    "Segundo párrafo de alpha para el chunk bajo el heading padre.\\n"
)
ALPHA_V2 = (
    "# Alpha\\n\\n"
    "CONTENIDO REESCRITO: la segunda versión de alpha demuestra que solo SUS "
    "chunks se rehacen.\\n\\n"
    "## Sección alpha\\n\\n"
    "Más texto nuevo de alpha tras la modificación.\\n"
)
BETA = "# Beta\\n\\nLa nota beta describe el walk filtrado y los skips tipados F5.\\n"
GAMMA = "# Gamma\\n\\nLa nota gamma nace en el paso add: solo sus chunks deben aparecer.\\n"
SANO = "# Sano\\n\\nArchivo UTF-8 sano que sí se indexa junto al latin-1 en el mismo refresh.\\n"
EFIMERO_V1 = "# Efímero\\n\\nPrimera versión: se indexa y luego desaparece a mitad de pasada.\\n"
EFIMERO_V2 = "# Efímero\\n\\nSegunda versión (mtime nuevo ⇒ re-ejecución) y después se borra.\\n"
LATIN1_BYTES = b"caf\\xe9 latin-1: bytes invalidos UTF-8\\n"
INTERNA = "# Interna\\n\\nVive tras un directorio ilegible; jamás debe indexarse.\\n"


def read_rows():
    async def go():
        conn = await lancedb.connect_async(str(DB))
        table = await conn.open_table("chunks")
        return (await table.to_arrow()).to_pylist()
    rows = asyncio.run(go())
    for row in rows:
        row.pop("embedding", None)
    return rows


def lance_snapshot():
    base = VAULT / ".tepochcalli" / "db" / "tepochcalli.lance"
    return {
        str(path.relative_to(base)): [path.stat().st_mtime_ns, path.stat().st_size]
        for path in sorted(base.rglob("*"))
        if path.is_file()
    }


def lock_content():
    return LOCK.read_text(encoding="utf-8") if LOCK.exists() else ""


def step(tag):
    lock_before = lock_content()
    report = flow_app.refresh_blocking()
    print(
        json.dumps(
            {
                "tag": tag,
                "report": dataclasses.asdict(report),
                "rows": read_rows(),
                "lance": lance_snapshot(),
                "lock_content_before": lock_before,
                "lock_content": lock_content(),
            }
        ),
        flush=True,
    )


step("initial")

(RES / "gamma.md").write_text(GAMMA, encoding="utf-8")
step("add")

(RES / "alpha.md").write_text(ALPHA_V2, encoding="utf-8")
step("modify")

(RES / "beta.md").unlink()
step("delete")

step("idempotent")

(RES / "latin1.md").write_bytes(LATIN1_BYTES)
(RES / "sano.md").write_text(SANO, encoding="utf-8")
step("nonutf8")

# Directorio ilegible (localfs hace `except PermissionError: continue`) y
# symlink roto (el conector ni siquiera lo entrega): ambos solo visibles para
# nuestra traversa sombra.
prohibida = RES / "carpeta_prohibida"
prohibida.mkdir()
(prohibida / "interna.md").write_text(INTERNA, encoding="utf-8")
os.chmod(prohibida, 0o000)
(RES / "roto.md").symlink_to(RES / "no_existe.md")
step("unreadable")

(RES / "efimero.md").write_text(EFIMERO_V1, encoding="utf-8")
step("efimero-add")

# TOCTOU classify→read: la clasificación decide (efimero V2 con mtime nuevo
# ⇒ re-ejecución forzada) y ENTonces el archivo desaparece antes de que
# index_file lo lea. El delta no debe abortar.
(RES / "efimero.md").write_text(EFIMERO_V2, encoding="utf-8")
original_items = flow_app._indexable_items


async def vanish_after_classify(resources_dir):
    items = await original_items(resources_dir)
    (resources_dir / "efimero.md").unlink()
    return items


flow_app._indexable_items = vanish_after_classify
step("vanish")
flow_app._indexable_items = original_items

step("reconcile")

# Lock retenido por un proceso YA MUERTO (crash simulado): el contenido del
# archivo no es el candado, así que esta pasada debe ejecutarse igualmente.
LOCK.write_text("999999\\n", encoding="utf-8")
step("stale")

os.chmod(RES / "carpeta_prohibida", 0o755)
"""

LOCKED_SCRIPT = """
import dataclasses, json
from tepochcalli_flow import app as flow_app
report = flow_app.refresh_blocking()
print(json.dumps({"tag": "locked", "report": dataclasses.asdict(report)}), flush=True)
"""


@dataclass(frozen=True)
class StepRecord:
    """Evidencia de un paso del journey: reporte, filas y snapshot de LanceDB."""

    tag: str
    """Nombre del paso (clave de `EXPECTED_COUNTS`)."""

    report: dict[str, Any]
    """`dataclasses.asdict(RefreshReport)` del subproceso."""

    rows: list[dict[str, Any]]
    """Filas de `chunks` SIN embedding tras la pasada (orden de la tabla)."""

    lance: dict[str, list[int]]
    """Snapshot `{relpath: [mtime_ns, size]}` de `.tepochcalli/db/tepochcalli.lance`."""

    lock_content_before: str
    """Contenido del lock file ANTES de la pasada (aquí se prueba el stale)."""

    lock_content: str
    """Contenido del lock file justo DESPUÉS de la pasada (diagnóstico)."""


@dataclass(frozen=True)
class Journey:
    """Resultado del journey completo de refreshes corridos en un subproceso."""

    vault: Path
    """Raíz del vault temporal."""

    steps: dict[str, StepRecord]
    """Un `StepRecord` por tag de `JOURNEY_TAGS`."""

    stderr: str
    """stderr del driver: logs de aislamiento por fichero (`component build failed`)."""


def _spawn(script: str, vault: Path, cache: Path) -> subprocess.CompletedProcess[str]:
    """Ejecuta un script en subproceso con el vault y el cache de modelo enlazado.

    `HF_HUB_OFFLINE` solo se fuerza si `cache` ya tiene el modelo (offline_env):
    en frío el hijo descarga UNA vez al cache resuelto, nunca al `/tmp` de nadie.
    """
    models_link = vault / ".tepochcalli" / "models"
    env = {
        **os.environ,
        flow_app.VAULT_ROOT_ENV: str(vault),
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


@pytest.fixture(scope="module")
def journey(tmp_path_factory: pytest.TempPathFactory) -> Journey:
    """Vault temporal recorrido por 11 refreshes real (T8)."""
    # Probe de permisos (mismo patrón que test_parsers): el journey simula un
    # directorio con chmod 0o000; si el filesystem no enforce (NTFS/fuseblk),
    # la contabilidad exacta de los pasos no es reproducible → módulo entero skip.
    probe = tmp_path_factory.mktemp("permisos-probe")
    probe.chmod(0o000)
    if os.access(probe, os.R_OK):
        probe.chmod(0o755)
        pytest.skip("el filesystem no enforce permisos de lectura (NTFS/fuseblk)")
    probe.chmod(0o755)

    vault = tmp_path_factory.mktemp("vault-t8")
    resources = vault / RESOURCE_DIR_NAME
    resources.mkdir()
    (resources / "alpha.md").write_text(ALPHA_V1, encoding="utf-8")
    (resources / "beta.md").write_text(BETA, encoding="utf-8")

    cache = resolve_model_cache()
    link_model_cache(vault, cache)

    proc = _spawn(JOURNEY_SCRIPT, vault, cache)
    assert proc.returncode == 0, (
        f"el driver del journey falló (rc={proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
    )

    steps: dict[str, StepRecord] = {}
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        record = json.loads(stripped)
        steps[record["tag"]] = StepRecord(
            tag=record["tag"],
            report=record["report"],
            rows=record["rows"],
            lance=record["lance"],
            lock_content_before=record["lock_content_before"],
            lock_content=record["lock_content"],
        )
    assert tuple(steps) == JOURNEY_TAGS, f"el driver no emitió los pasos esperados: {tuple(steps)}"
    return Journey(vault=vault, steps=steps, stderr=proc.stderr)


def _sorted_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filas ordenadas por id: comparar estados de la tabla sin depender del orden."""
    return sorted(rows, key=lambda row: row["id"])


def _tree_snapshot(base: Path) -> dict[str, tuple[int, int]]:
    """Snapshot `{relpath: (mtime_ns, size)}` de todos los archivos bajo `base`."""
    return {
        str(path.relative_to(base)): (path.stat().st_mtime_ns, path.stat().st_size)
        for path in sorted(base.rglob("*"))
        if path.is_file()
    }


def _read_all_rows(vault: Path) -> list[dict[str, Any]]:
    """Lee la tabla `chunks` completa desde disco (patrón T9; en el padre)."""

    async def go() -> list[dict[str, Any]]:
        connection = await lancedb.connect_async(str(vault / DB_RELPATH))
        table = await connection.open_table("chunks")
        arrow = await table.to_arrow()
        return arrow.to_pylist()

    return asyncio.run(go())


def _sources(rows: list[dict[str, Any]]) -> set[str]:
    """Conjunto de `source_path` presentes en una lista de filas."""
    return {str(row["source_path"]) for row in rows}


def _rows_of(steps: StepRecord, source_path: str) -> list[dict[str, Any]]:
    """Filas de un `source_path` concreto, ordenadas por id."""
    return _sorted_rows([row for row in steps.rows if row["source_path"] == source_path])


# --- 1-3: add / modify / delete -------------------------------------------------


def test_initial_refresh_indexes_every_indexable_file(journey: Journey) -> None:
    """R1: los dos ficheros indexables iniciales se indexan y nada más."""
    report = journey.steps["initial"].report
    assert (report["scanned"], report["indexed"], report["skipped"]) == (2, 2, 0)
    assert report["locked"] is False
    assert report["elapsed_ms"] > 0
    assert _sources(journey.steps["initial"].rows) == {
        "00-Resources/alpha.md",
        "00-Resources/beta.md",
    }


def test_adding_a_file_indexes_only_the_new_file(journey: Journey) -> None:
    """R2: add → `indexed=1`; solo gamma aporta filas nuevas."""
    report = journey.steps["add"].report
    assert (report["scanned"], report["indexed"], report["skipped"]) == (3, 1, 2)
    initial, added = journey.steps["initial"], journey.steps["add"]
    for source_path in ("00-Resources/alpha.md", "00-Resources/beta.md"):
        assert _rows_of(initial, source_path) == _rows_of(added, source_path), (
            f"{source_path} no debe reescribirse en el paso add"
        )
    assert _rows_of(added, "00-Resources/gamma.md"), "gamma.md no indexó filas"


def test_modifying_a_file_rewrites_only_its_chunks(journey: Journey) -> None:
    """R3: modify → `indexed=1` y SOLO las filas de alpha cambian (byte a byte)."""
    report = journey.steps["modify"].report
    assert (report["scanned"], report["indexed"], report["skipped"]) == (3, 1, 2)
    added, modified = journey.steps["add"], journey.steps["modify"]
    for source_path in ("00-Resources/beta.md", "00-Resources/gamma.md"):
        assert _rows_of(added, source_path) == _rows_of(modified, source_path), (
            f"{source_path} no debe reescribirse al modificar alpha"
        )
    alpha_before = _rows_of(added, "00-Resources/alpha.md")
    alpha_after = _rows_of(modified, "00-Resources/alpha.md")
    assert alpha_before and alpha_after
    assert [row["text"] for row in alpha_before] != [row["text"] for row in alpha_after]


def test_deleting_a_file_purges_its_rows_and_keeps_the_rest(journey: Journey) -> None:
    """R4: delete → filas de beta PURGADAS; alpha y gamma intactas."""
    report = journey.steps["delete"].report
    assert (report["scanned"], report["indexed"], report["skipped"]) == (2, 0, 2)
    modified, deleted = journey.steps["modify"], journey.steps["delete"]
    assert "00-Resources/beta.md" not in _sources(deleted.rows), (
        "las filas de beta.md deben quedar purgadas (F2)"
    )
    for source_path in ("00-Resources/alpha.md", "00-Resources/gamma.md"):
        assert _rows_of(modified, source_path) == _rows_of(deleted, source_path)


# --- 4-5: idempotencia desde el data plane + contrato de métricas ---------------


def test_second_pass_without_changes_reports_indexed_zero(
    journey: Journey,
) -> None:
    """R5: idempotencia leída del data plane: `index_file` adds+reprocesses = 0.

    Si el reporte se calculase desde el total de la pasada, la traversa
    `build_flow` (`reprocess=1` por diseño, E2) lo elevaría a ≥1 y este test
    fallaría: la cuenta correcta sale del componente por fichero.
    """
    report = journey.steps["idempotent"].report
    assert (report["scanned"], report["indexed"], report["skipped"]) == (2, 0, 2)
    assert report["indexed"] == 0, "la 2ª pasada sin cambios no reescribe nada"
    deleted, idempotent = journey.steps["delete"], journey.steps["idempotent"]
    assert _sorted_rows(deleted.rows) == _sorted_rows(idempotent.rows), (
        "las filas deben ser idénticas byte a byte (incluido indexed_at)"
    )
    assert deleted.lance == idempotent.lance, (
        "LanceDB no debe tocarse en una pasada sin cambios (mtime+size)"
    )


def test_refresh_report_is_a_frozen_typed_contract_without_any() -> None:
    """El reporte es tipado, congelado y sin `Any` en la firma pública (T8 AC)."""
    report_cls = flow_models.RefreshReport
    assert [field.name for field in fields(report_cls)] == REPORT_FIELDS
    assert report_cls.__dataclass_params__.frozen is True

    hints = get_type_hints(report_cls)
    assert hints == {
        "scanned": int,
        "indexed": int,
        "skipped": int,
        "elapsed_ms": int,
        "locked": bool,
    }
    assert not any(hint is Any for hint in hints.values())

    signature = get_type_hints(flow_app.refresh_blocking)
    assert signature.get("return") is report_cls
    assert not any(hint is Any for hint in signature.values())
    assert list(fields(flow_app.RefreshReport)) == list(fields(report_cls)), (
        "app.py debe reexportar el MISMO contrato tipado"
    )


def test_elapsed_ms_is_computed_with_a_monotonic_clock() -> None:
    """`elapsed_ms` sale de `time.monotonic()` — inmune a ajustes de reloj.

    Limitación (como su hermana de test_pipeline_integration): inspecciona
    TEXTO fuente, no semántica — una forma equivalente de leer el reloj
    monotónico (p. ej. `time.monotonic_ns()`) rompería el assert siendo
    correcta. Si eso pasa se actualiza la prueba, no se relaja el contrato.
    """
    source = inspect.getsource(flow_app.refresh_blocking)
    assert "time.monotonic" in source
    assert "time.time(" not in source
    assert "datetime.now" not in source


def test_every_step_holds_the_scanned_identity_and_exact_counts(
    journey: Journey,
) -> None:
    """Barrido de honestidad: `scanned == indexed + skipped` y cuenta exacta en los 11 pasos."""
    assert tuple(journey.steps) == JOURNEY_TAGS
    for tag, expected in EXPECTED_COUNTS.items():
        report = journey.steps[tag].report
        assert (report["scanned"], report["indexed"], report["skipped"]) == expected, (
            f"cuenta inesperada en {tag}: {report}"
        )
        assert report["scanned"] == report["indexed"] + report["skipped"], (
            f"la cuenta miente en {tag}: {report}"
        )
        assert report["elapsed_ms"] > 0
        assert report["locked"] is False


# --- 5: el non-UTF-8 y el directorio ilegible NO son invisibles -----------------


def test_non_utf8_file_is_counted_isolated_and_never_indexed(
    journey: Journey,
) -> None:
    """R6: latin-1 cae en `skipped` (no en un log olvidado), sano sí se indexa."""
    report = journey.steps["nonutf8"].report
    assert (report["scanned"], report["indexed"], report["skipped"]) == (4, 1, 3)
    rows = journey.steps["nonutf8"].rows
    assert "00-Resources/latin1.md" not in _sources(rows), "latin1 no debe indexarse"
    assert _rows_of(journey.steps["nonutf8"], "00-Resources/sano.md"), (
        "el fichero sano del MISMO refresh sí debe indexarse"
    )
    assert "component build failed" in journey.stderr, (
        "el fallo por fichero debe ser visible (exception handler del lifespan)"
    )
    assert "latin1.md" in journey.stderr, "el log del fallo debe localizar el fichero (no-UTF-8)"


def test_unreadable_directory_and_broken_symlink_are_counted(
    journey: Journey,
) -> None:
    """R7: el directorio ilegible (y el symlink roto) entran en la cuenta.

    Sus contenidos jamás se indexan — el directorio SE REPRESENTA con una
    entrada.
    """
    report = journey.steps["unreadable"].report
    assert (report["scanned"], report["indexed"], report["skipped"]) == (6, 0, 6)
    rows = journey.steps["unreadable"].rows
    assert "00-Resources/carpeta_prohibida/interna.md" not in _sources(rows)
    assert not any("roto" in source for source in _sources(rows))
    assert journey.steps["nonutf8"].rows == rows, "un refresh sin escrituras no debe tocar filas"


# --- 4 (CP-B #5): TOCTOU classify→read ------------------------------------------


def test_file_vanishing_after_classification_does_not_abort_the_delta(
    journey: Journey,
) -> None:
    """R9: efimero desaparece entre `classify_file` y `index_file.read`.

    El delta COMPLETA (aislamiento del engine + exception handler), el fichero
    cae en `skipped` y sus filas antiguas quedan hasta la reconciliación.
    """
    report = journey.steps["vanish"].report
    assert (report["scanned"], report["indexed"], report["skipped"]) == (7, 0, 7)
    efimero_add, vanish = journey.steps["efimero-add"], journey.steps["vanish"]
    assert _rows_of(efimero_add, "00-Resources/efimero.md"), "el paso previo sí indexó efimero (v1)"
    assert _rows_of(vanish, "00-Resources/efimero.md") == _rows_of(
        efimero_add, "00-Resources/efimero.md"
    ), "el fallo de lectura no debe dejar escrituras parciales (dos fases)"
    for source_path in ("00-Resources/alpha.md", "00-Resources/sano.md"):
        assert _rows_of(efimero_add, source_path) == _rows_of(vanish, source_path)
    assert "efimero.md" in journey.stderr, "el desvanecimiento debe ser visible en el log del fallo"


def test_vanished_file_is_purged_on_the_next_refresh(journey: Journey) -> None:
    """R10: la pasada siguiente reconcilia.

    Efimero sale del walk y sus filas se purgan sin reescribir ninguna otra.
    """
    report = journey.steps["reconcile"].report
    assert (report["scanned"], report["indexed"], report["skipped"]) == (6, 0, 6)
    vanish, reconcile = journey.steps["vanish"], journey.steps["reconcile"]
    assert "00-Resources/efimero.md" not in _sources(reconcile.rows), (
        "las filas de efimero.md deben purgarse en la reconciliación"
    )
    for source_path in ("00-Resources/alpha.md", "00-Resources/gamma.md"):
        assert _rows_of(vanish, source_path) == _rows_of(reconcile, source_path)


# --- 2 (lock) + stale -----------------------------------------------------------


def test_stale_lock_file_from_a_crash_does_not_block_the_refresh(
    journey: Journey,
) -> None:
    """R11: un lock file con el pid de un proceso MUERTO no retiene nada.

    El candado es el flock, no la existencia del archivo; la pasada corre igual.
    """
    reconcile, stale = journey.steps["reconcile"], journey.steps["stale"]
    assert stale.lock_content_before == "999999\n", (
        "el paso debe partir de un lock file stale (crash simulado)"
    )
    report = stale.report
    assert (report["scanned"], report["indexed"], report["skipped"]) == (6, 0, 6)
    assert report["locked"] is False, (
        "el contenido residual de un crash no debe bloquear (stale recovery)"
    )
    assert report["elapsed_ms"] > 0
    assert stale.lock_content != "999999\n", (
        "un refresh exitoso reutiliza (no borra) el lock file con su nuevo pid"
    )
    assert _sorted_rows(reconcile.rows) == _sorted_rows(stale.rows)
    assert reconcile.lance == stale.lance


def test_concurrent_refresh_returns_locked_and_writes_nothing(
    journey: Journey,
) -> None:
    """2º proceso concurrente: `locked:true` con ceros Y sin la menor escritura.

    El padre RETIENE el candado (flock sobre el lock file del vault) mientras
    un subproceso invoca `refresh_blocking()`: el reporte es cero y el snapshot
    byte a byte de TODO `.tepochcalli/db/` (LanceDB + estado del engine + lock
    file) antes/después demuestra que no se escribió nada.
    """
    vault = journey.vault
    assert flow_app.LOCK_RELPATH.parts[:2] == (".tepochcalli", "db"), (
        "el candado vive bajo .tepochcalli/db/ (gitignored; D14/T2)"
    )
    lock_fd = flow_app._acquire_refresh_lock(vault)
    assert lock_fd is not None, "el vault no tiene el candado retenido aún"
    try:
        db_snapshot = _tree_snapshot(vault / ".tepochcalli" / "db")
        rows_before = _read_all_rows(vault)
        proc = _spawn(LOCKED_SCRIPT, vault, resolve_model_cache())
    finally:
        flow_app._release_refresh_lock(lock_fd)

    assert proc.returncode == 0, f"la invocación concurrente falló:\n{proc.stderr}"
    report = json.loads(proc.stdout.strip().splitlines()[-1])["report"]
    assert (report["scanned"], report["indexed"], report["skipped"]) == (0, 0, 0)
    assert report["locked"] is True
    assert report["elapsed_ms"] >= 0
    assert set(report) == set(REPORT_FIELDS), "el reporte bloqueado lleva el contrato completo"
    assert _tree_snapshot(vault / ".tepochcalli" / "db") == db_snapshot, (
        "la invocación bloqueada NO debe escribir ni un byte"
    )
    assert _read_all_rows(vault) == rows_before, (
        "las filas deben quedar idénticas tras la invocación bloqueada"
    )


# --- higiene del payload --------------------------------------------------------


def test_payload_db_and_models_are_never_created() -> None:
    """Ningún refresh de este módulo materializa `db/` ni `models/` en el payload."""
    payload = Path(__file__).parents[2] / "obsidian-workspace" / ".tepochcalli"
    assert not (payload / "db").exists()
    assert not (payload / "models").exists()
