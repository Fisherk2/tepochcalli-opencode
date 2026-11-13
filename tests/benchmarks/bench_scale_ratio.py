"""Bench del criterio 6 a escala: brazos 10 % vs 100 % y contraste de filesystem (Phase 6 T5).

Líneas: 701-1000, justificado **con advertencia** de refactorizar lo antes posible
(CODE_STYLE §Umbral): herramienta one-shot de medición de 7 fases; el grueso son los
tres brazos con orientaciones distintas (btrfs ×2, fuseblk) y el JSON publicado. Al
añadir fases o brazos: sacar `_phase_report` a su módulo antes de crecer más.

Protocolo: `docs/TRD.md` §6 (criterio 6, «sin regresión >2× entre tamaños») y
`docs/acceptance/protocol.md` §6. Corpus: **T1** (`tests/support/corpus.py`,
`tree_sha256 27a20c05…3ecd2`). Índice del brazo 100 %: **T4**
(`/tmp/opencode/t4-scale/vault`, 11 006 chunks).

* **Δ p95** (n=20, nearest-rank `sorted[ceil(0.95·n)-1]` = 19.º valor): 20 ciclos
  de «reescribir 10 `.md` + `index_refresh()`». Los 10 ficheros son constantes
  en ambos brazos a propósito: el embed queda fijo y el ratio aísla el coste del
  walk/engine a escala (11 000 vs 1 100 entradas), que es lo que pregunta el
  criterio 6. Rotación determinista `(run*97 + k*13) % n_md`, como P-02.
* **Latencia `search`**: n=100, `top_k=5`, por stdio real (`bench_search._stdio_phase`)
  con **las mismas 100 consultas de T4** leídas de su `prepare.json` (semilla 20261112).
* **Walk-only**: `source.scan_items` puro (sin embed, sin Δ), n=5.
* **Ratio** por métrica: `p95_100 / p95_10`, PASS si ≤ 2,0.

Brazo 10 %: 1 000 md + 100 PDF **derivados del manifiesto de T1** (uno de cada 10
en orden canónico de ruta, por tipo), cada copia verificada contra su `sha256` y
con su propio manifiesto. Es un subconjunto estricto del corpus, pero se mide con
**su propio índice en frío**: no se compara el índice de T4 contra sí mismo.

Brazo fuseblk/NTFS-3G (límite conocido, D-P6-3): `benchmarks/t5-ntfs/` (datos de
trabajo gitignored, borrables — `benchmarks/README.md`), que vive en el montaje
fuseblk/NTFS-3G (`df -T` en el JSON). Su índice se **construye en frío en ese
mismo FS** —copiar el de btrfs no vale: el memo del engine no cruza el cambio de
ruta y cada refresh re-embebe el corpus entero (medido y descartado)—. No decide
el criterio: va a la columna de límites.

Fases, una llamada de primer plano cada una (nada en segundo plano)::

    --phase prepare | index10 | search        # brazos btrfs
    --phase delta --arm b100|b10|ntfs --start 0 --cycles 5
    --phase walk  --arm b100|b10|ntfs
    --phase ntfs                              # corpus + índice de T4 → fuseblk
    --phase report                            # ratio, veredictos y JSON archivado

`search` corre **antes** de los Δ (los ciclos reescriben ficheros y el índice
dejaría 200 documentos re-indexados). Cada tramo Δ escribe
`<WORK_DIR>/delta-<arm>-<start>.json` y `report` exige los 20 ciclos.

No corre en CI ni en `just ci` (no es `test_*`). Borra el vault NTFS al informar
(`--keep` lo conserva) y aborta si `obsidian-workspace/.tepochcalli/{db,models}`
apareciera. No toca el corpus de T1, el contrato MCP ni el puerto `ChunkReader`.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))

from bench_delta import _host_block, _nearest_rank_p  # noqa: E402
from bench_search import TOP_K, VAULT_ROOT_ENV, _stdio_phase  # noqa: E402
from corpus import MANIFEST_NAME, RESOURCES_DIR, CorpusFile, Manifest, verify  # noqa: E402
from model_cache import link_model_cache, offline_env, resolve_model_cache  # noqa: E402

N_RUNS = 20
"""Ciclos Δ del presupuesto (TRD §6: «corridas ×20», como M1)."""

MODIFIED_PER_RUN = 10
"""Ficheros reescritos por ciclo (constante en ambos brazos: ver docstring)."""

BUDGET_MS = 30_000
"""Presupuesto del Δ de texto (TRD §6 criterio 2)."""

RATIO_MAX = 2.0
"""Cota del criterio 6: `p95_100 / p95_10` ≤ 2× (TRD §6, fijada en CP-0)."""

BASELINE_P02_MS = 26_967
"""Baseline P-02 (Phase 3.5, btrfs): Δ p95 del corpus 10k/1k con el bench viejo."""

SUBSET_STRIDE = 10
"""Uno de cada 10 ficheros por tipo ⇒ 1 000 md + 100 PDF (10 % proporcional)."""

SUBSET_SEED = 20261103
"""Semilla del contenido que reescriben los ciclos Δ (`corpus_text`)."""

WALK_SAMPLES = 5
"""Muestras de `scan_items` (sin embed, sin Δ) por brazo."""

DRIVER_TIMEOUT_S = 3600
QUERY_SEED = 20261112
"""Semilla del muestreo de consultas de T4 (se reutilizan sus 100)."""

CORPUS_ROOT = Path("/tmp/opencode/phase6-corpus")
T4_WORK = Path("/tmp/opencode/t4-scale")
VAULT100 = T4_WORK / "vault"
"""Vault + índice de T4 (11 006 chunks): brazo 100 %, sin reindexar."""

WORK_DIR = Path("/tmp/opencode/phase6-scale-ratio")
VAULT10 = WORK_DIR / "vault10"

REPO_ROOT = Path(__file__).resolve().parents[2]
NTFS_VAULT = REPO_ROOT / "benchmarks" / "t5-ntfs" / "vault"
"""Datos de trabajo (gitignored, borrables): `benchmarks/README.md` fija el reparto."""

PAYLOAD_DB = REPO_ROOT / "obsidian-workspace" / ".tepochcalli" / "db"
PAYLOAD_MODELS = REPO_ROOT / "obsidian-workspace" / ".tepochcalli" / "models"
DIAGNOSIS_JSON = REPO_ROOT / "docs" / "acceptance" / "scale-ratio.json"

ARMS = {"b100": VAULT100, "b10": VAULT10, "ntfs": NTFS_VAULT}
ARM_LABEL = {
    "b100": "btrfs · 11 000 entradas (índice de T4)",
    "b10": "btrfs · 1 100 entradas (subconjunto, índice propio)",
    "ntfs": "fuseblk/NTFS-3G · 11 000 entradas (índice construido en frío en ese FS)",
}

_COMMAND_SPECS = [("prepare", None), ("index10", None), ("search", None), ("ntfs", None)]
_COMMAND_SPECS += [(phase, arm) for arm in ("b100", "b10", "ntfs") for phase in ("walk", "delta")]
_COMMAND_SPECS += [("report", None)]
COMMANDS = [
    f"just python-bench-scale-ratio --phase {phase}" + (f" --arm {arm}" if arm else "")
    for phase, arm in _COMMAND_SPECS
]
"""Recetas exactas que reproducen cada tramo (en el orden del protocolo)."""


def _emit(obj: dict[str, Any]) -> None:
    """Imprime un objeto JSON (stdout de una fase: solo JSON)."""
    print(json.dumps(obj, indent=2, ensure_ascii=False), flush=True)


def _save(name: str, payload: dict[str, Any]) -> None:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    path = WORK_DIR / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _load(name: str) -> dict[str, Any]:
    path = WORK_DIR / f"{name}.json"
    if not path.is_file():
        raise SystemExit(f"falta {path}: corre antes la fase que lo produce")
    return json.loads(path.read_text(encoding="utf-8"))


def _rows(vault: Path) -> int:
    """Filas del índice del vault (solo lectura, embedder nulo)."""
    from tepochcalli_flow.adapters.lancedb_reader import LanceDBChunkReader
    from tepochcalli_flow.layout import DB_RELPATH

    return int(
        asyncio.run(LanceDBChunkReader(vault / DB_RELPATH, embed=lambda _text: []).count_rows())
    )


def _t4_queries() -> list[str]:
    """Las 100 consultas de T4 (mismo muestreo, semilla 20261112)."""
    path = T4_WORK / "prepare.json"
    if not path.is_file():
        raise SystemExit(
            f"faltan las consultas de T4 en {path}: corre antes "
            "`just python-bench-search-scale --phase prepare`"
        )
    return [str(item["query"]) for item in json.loads(path.read_text("utf-8"))["queries"]]


def _measure_env(vault: Path) -> None:
    """Env de las fases en proceso: vault + cache de modelo + offline."""
    models = vault / ".tepochcalli" / "models"
    os.environ[VAULT_ROOT_ENV] = str(vault)
    os.environ["HF_HOME"] = str(models)
    os.environ["SENTENCE_TRANSFORMERS_HOME"] = str(models)
    os.environ.update(offline_env(resolve_model_cache()))
    os.environ.pop("COCOINDEX_DB", None)


def _run_driver(argv: list[str], vault: Path) -> subprocess.CompletedProcess[str]:
    """Lanza el driver en un subproceso (un estado de cocoindex por vault)."""
    models = vault / ".tepochcalli" / "models"
    env = {
        **os.environ,
        VAULT_ROOT_ENV: str(vault),
        "HF_HOME": str(models),
        "SENTENCE_TRANSFORMERS_HOME": str(models),
        **offline_env(resolve_model_cache()),
    }
    env.pop("COCOINDEX_DB", None)
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), *argv],
        env=env,
        capture_output=True,
        text=True,
        timeout=DRIVER_TIMEOUT_S,
        check=False,
    )
    if proc.returncode != 0:
        print(proc.stderr[-6000:], file=sys.stderr)
        raise SystemExit(f"el driver falló (rc={proc.returncode}): {' '.join(argv[:2])}")
    return proc


def _json_lines(stdout: str) -> list[dict[str, Any]]:
    """Parsea las líneas JSON del driver (todo lo demás es ruido del engine)."""
    return [json.loads(line) for line in stdout.splitlines() if line.strip().startswith("{")]


# --- Brazo 10 %: derivado del manifiesto de T1 --------------------------------


def _phase_prepare() -> dict[str, Any]:
    """Deriva 1 000 md + 100 PDF del manifiesto de T1, verifica hashes y manifiesta."""
    started = time.monotonic()
    full = Manifest.from_dict(json.loads((CORPUS_ROOT / MANIFEST_NAME).read_text("utf-8")))
    picked: list[CorpusFile] = []
    for kind in ("md", "pdf"):
        ordered = sorted((e for e in full.files if e.kind == kind), key=lambda e: e.path)
        picked.extend(ordered[::SUBSET_STRIDE])
    counts = {kind: sum(1 for e in picked if e.kind == kind) for kind in ("md", "pdf")}
    if counts != {"md": 1_000, "pdf": 100}:
        raise SystemExit(f"el subconjunto dio {counts}, esperaba 1 000 md + 100 pdf")

    manifest10 = Manifest(
        seed=full.seed, generator_version=full.generator_version, files=tuple(picked)
    )
    reused = VAULT10.exists()
    if reused:
        # Idempotente como `corpus.materialize_or_verify`: solo se reutiliza si el
        # manifiesto en disco describe EXACTAMENTE el subconjunto derivado hoy.
        on_disk = json.loads((VAULT10 / MANIFEST_NAME).read_text("utf-8"))
        if on_disk["files"] != [entry.__dict__ for entry in picked]:
            raise SystemExit(f"{VAULT10} no describe el subconjunto derivado: usa otra raíz")
    else:
        for entry in picked:
            payload = (CORPUS_ROOT / entry.path).read_bytes()
            if hashlib.sha256(payload).hexdigest() != entry.sha256:
                raise SystemExit(f"{entry.path} no coincide con el manifiesto de T1")
            target = VAULT10 / entry.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        (VAULT10 / MANIFEST_NAME).write_text(manifest10.canonical_json() + "\n", encoding="utf-8")
    problems = verify(VAULT10, manifest10)
    if problems:
        raise SystemExit(f"el vault del 10 % no cuadra con su manifiesto: {problems[:5]}")
    if not (VAULT10 / ".tepochcalli" / "models").exists():
        link_model_cache(VAULT10, resolve_model_cache())

    return {
        "phase": "prepare",
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "reused": reused,
        "selection": (
            f"uno de cada {SUBSET_STRIDE} ficheros en orden canónico de ruta, por tipo "
            "(determinista, sin semilla): 10 % de md y 10 % de pdf del corpus de T1"
        ),
        "source_tree_sha256": full.tree_sha256,
        "subset": {**counts, "files": len(picked), "tree_sha256": manifest10.tree_sha256},
        "vault": str(VAULT10),
        "vault_verified": True,
    }


# --- Indexación en frío del brazo 10 % ---------------------------------------


def _phase_index10() -> dict[str, Any]:
    """UNA indexación en frío de las 1 100 entradas del brazo 10 %."""
    from tepochcalli_flow import app as flow_app

    _measure_env(VAULT10)
    wall = time.perf_counter()
    report = flow_app.refresh_blocking()
    result = {
        "phase": "index10",
        "elapsed_ms": report.elapsed_ms,
        "wall_ms": round((time.perf_counter() - wall) * 1000),
        "scanned": report.scanned,
        "indexed": report.indexed,
        "skipped": report.skipped,
        "locked": report.locked,
        "rows": _rows(VAULT10),
        "roots": list(report.roots),
    }
    if report.locked or report.scanned != 1_100 or report.indexed != 1_100:
        raise SystemExit(f"[index10] indexación incompleta: {result}")
    if result["rows"] < 1_100:
        raise SystemExit(f"[index10] filas={result['rows']} < 1100: índice incompleto")
    return result


# --- Latencia de `search` en ambos brazos (n=100, consultas de T4) -----------


def _phase_search() -> dict[str, Any]:
    """n=100 por stdio real en los DOS brazos btrfs, con las mismas consultas de T4."""
    queries = _t4_queries()
    arms: dict[str, Any] = {}
    for arm in ("b10", "b100"):
        vault = ARMS[arm]
        started = time.monotonic()
        warm, calls = _stdio_phase(vault, queries)
        arms[arm] = {
            "vault": str(vault),
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "warm": warm,
            "calls": calls,
            "chunks_indexed": _rows(vault),
        }
    return {"phase": "search", "n": len(queries), "query_seed": QUERY_SEED, "arms": arms}


# --- Walk-only (sin embed, sin Δ) -------------------------------------------


def _walk_driver(vault: Path, samples: int) -> None:
    """Corre en el subproceso: `scan_items` puro, `samples` veces."""
    from tepochcalli_flow import source

    for index in range(samples):
        started = time.perf_counter()
        items, scanned = asyncio.run(source.scan_items(vault))
        print(
            json.dumps(
                {
                    "kind": "walk",
                    "i": index,
                    "walk_ms": round((time.perf_counter() - started) * 1000, 1),
                    "items": len(items),
                    "scanned": scanned,
                }
            ),
            flush=True,
        )


def _phase_walk(arm: str, samples: int) -> dict[str, Any]:
    """`scan_items` sobre el vault del brazo: coste del walk, sin embed y sin Δ."""
    vault = ARMS[arm]
    records = [
        r
        for r in _json_lines(_run_driver(["--walk-driver", str(vault), str(samples)], vault).stdout)
        if r["kind"] == "walk"
    ]
    if len(records) != samples:
        raise SystemExit(f"esperaba {samples} muestras de walk, llegaron {len(records)}")
    expected = 1_100 if arm == "b10" else 11_000
    for record in records:
        if record["scanned"] != expected:
            raise SystemExit(f"[walk {arm}] scanned={record['scanned']} != {expected}")
    values = [float(record["walk_ms"]) for record in records]
    return {
        "phase": f"walk-{arm}",
        "arm": arm,
        "label": ARM_LABEL[arm],
        "vault": str(vault),
        "entries": expected,
        "n": samples,
        "walk_ms": values,
        "min_ms": min(values),
        "median_ms": sorted(values)[len(values) // 2],
        "max_ms": max(values),
        "note": "warm page cache tras la 1.ª muestra; sin embed y sin ciclo Δ",
        "host": _host_block(vault),
    }


# --- Δ por tramos -----------------------------------------------------------


def _delta_driver(vault: Path, start: int, cycles: int, pass_no: int) -> None:
    """Corre en el subproceso: calentamiento + `cycles` ciclos Δ a partir de `start`."""
    import random

    from corpus import corpus_text
    from tepochcalli_flow import app as flow_app

    manifest = Manifest.from_dict(json.loads((vault / MANIFEST_NAME).read_text("utf-8")))
    md_paths = sorted(vault / entry.path for entry in manifest.files if entry.kind == "md")
    n_files = len(manifest.files)

    def _refresh(tag: str, modified: int) -> None:
        report = flow_app.refresh_blocking()
        if report.locked or report.scanned != n_files or report.indexed != modified:
            raise SystemExit(f"[{tag}] refresh inesperado: {report}")
        print(json.dumps({"kind": "refresh", "tag": tag, "elapsed_ms": report.elapsed_ms}))

    def _rewrite(run: int, tag: str) -> None:
        for k in range(MODIFIED_PER_RUN):
            index = (run * 97 + k * 13) % len(md_paths)
            path = md_paths[index]
            path.write_text(
                corpus_text(index, random.Random(SUBSET_SEED + run * 1000 + k))
                + f"\n\n{tag} pasada {pass_no}: reescritura determinista "
                f"del fichero {path.name}.\n",
                encoding="utf-8",
            )

    # Calentamiento FUERA del presupuesto: un ciclo Δ completo sobre los MISMOS
    # ficheros del primer ciclo medido. Sin él, el 1.er ciclo de cada tramo paga
    # la inicialización del engine en un proceso nuevo (~+15 s medidos) y el p95
    # saldría del troceado, no del sistema. El ciclo medido reescribe esos
    # ficheros otra vez (marca distinta) ⇒ sigue siendo un cambio real.
    _rewrite(start, "Calentamiento")
    _refresh("warmup", MODIFIED_PER_RUN)
    for run in range(start, start + cycles):
        _rewrite(run, f"Corrida {run}")
        _refresh(f"run-{run:02d}", MODIFIED_PER_RUN)


def _phase_delta(arm: str, start: int, cycles: int, pass_no: int) -> dict[str, Any]:
    """Mide `cycles` ciclos Δ (desde `start`) en el vault del brazo y publica su JSON."""
    if cycles < 1 or start < 0 or start + cycles > N_RUNS:
        raise SystemExit(f"tramo inválido: start={start} cycles={cycles} (n total = {N_RUNS})")
    vault = ARMS[arm]
    records = _json_lines(
        _run_driver(
            ["--delta-driver", str(vault), str(start), str(cycles), str(pass_no)],
            vault,
        ).stdout
    )
    runs = [r for r in records if r["tag"] != "warmup"]
    if len(runs) != cycles:
        raise SystemExit(f"esperaba {cycles} ciclos, llegaron {len(runs)}")
    return {
        "phase": f"delta-{arm}",
        "arm": arm,
        "label": ARM_LABEL[arm],
        "vault": str(vault),
        "start": start,
        "cycles": cycles,
        "rewrite_pass": pass_no,
        "samples": [{"run": r["tag"], "elapsed_ms": r["elapsed_ms"]} for r in runs],
        "host": _host_block(vault),
    }


# --- Brazo fuseblk/NTFS-3G --------------------------------------------------


def _phase_ntfs() -> dict[str, Any]:
    """Materializa el vault NTFS (corpus de T1) e **indexa en frío en ese mismo FS**."""
    from tepochcalli_flow import app as flow_app

    started = time.monotonic()
    if NTFS_VAULT.parent.exists():
        shutil.rmtree(NTFS_VAULT.parent)
    NTFS_VAULT.parent.mkdir(parents=True)
    manifest = Manifest.from_dict(json.loads((CORPUS_ROOT / MANIFEST_NAME).read_text("utf-8")))
    shutil.copytree(CORPUS_ROOT / RESOURCES_DIR, NTFS_VAULT / RESOURCES_DIR)
    shutil.copy2(CORPUS_ROOT / MANIFEST_NAME, NTFS_VAULT / MANIFEST_NAME)
    problems = verify(NTFS_VAULT, manifest)
    if problems:
        raise SystemExit(f"la copia NTFS no cuadra con el manifiesto: {problems[:5]}")
    link_model_cache(NTFS_VAULT, resolve_model_cache())
    # El índice se construye EN FRÍO sobre fuseblk, como en P-02: copiar el
    # índice de btrfs NO sirve — el memo del engine no cruza el cambio de ruta y
    # cada refresh re-extrae y re-embebe las 11 000 entradas (medido: 96-204 s por
    # ciclo con `indexed=0`, es decir Δ convertido en re-embed completo).
    _measure_env(NTFS_VAULT)
    report = flow_app.refresh_blocking()
    rows = _rows(NTFS_VAULT)
    if report.scanned != 11_000 or report.indexed != 11_000 or rows < 11_000:
        raise SystemExit(f"[ntfs] indexación en frío incompleta: {report} rows={rows}")
    return {
        "phase": "ntfs",
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "cold_index_ms": report.elapsed_ms,
        "rows": rows,
        "vault": str(NTFS_VAULT),
        "host": _host_block(NTFS_VAULT),
        "files_verified": len(manifest.files),
        "index": (
            "construido en frío sobre fuseblk (la copia del índice de btrfs se descartó: el "
            "memo del engine no cruza el cambio de ruta ⇒ re-embed completo por refresh)"
        ),
    }


# --- Informe ----------------------------------------------------------------


def _arm_delta(arm: str) -> dict[str, Any]:
    """Une los tramos de un brazo; exige los 20 ciclos, contiguos y sin huecos."""
    chunks = sorted(WORK_DIR.glob(f"delta-{arm}-*.json"))
    if not chunks:
        raise SystemExit(f"no hay tramos delta de {arm}: falta correr la fase delta")
    samples: dict[int, int] = {}
    for chunk in chunks:
        for sample in json.loads(chunk.read_text("utf-8"))["samples"]:
            samples[int(sample["run"].split("-")[1])] = int(sample["elapsed_ms"])
    missing = [i for i in range(N_RUNS) if i not in samples]
    if missing:
        raise SystemExit(f"brazo {arm}: faltan los ciclos {missing} (n={len(samples)})")
    values = [samples[i] for i in range(N_RUNS)]
    return {
        "arm": arm,
        "label": ARM_LABEL[arm],
        "chunks": [chunk.name for chunk in chunks],
        "n": N_RUNS,
        "modified_per_run": MODIFIED_PER_RUN,
        "samples_ms": values,
        "p95_ms": _nearest_rank_p(values, 0.95),
        "min_ms": min(values),
        "median_ms": sorted(values)[len(values) // 2],
        "max_ms": max(values),
    }


def _search_block(arm_block: dict[str, Any]) -> dict[str, Any]:
    """p95 de `client_ms` (la puerta) y de `took_ms` (el punto de la spec) del brazo."""
    calls = arm_block["calls"]
    return {
        "p95_client_ms": _nearest_rank_p([float(c["client_ms"]) for c in calls], 0.95),
        "p95_server_took_ms": _nearest_rank_p([float(c["took_ms"]) for c in calls], 0.95),
        "n": len(calls),
        "chunks_indexed": arm_block["chunks_indexed"],
    }


def _ratio(numerator: float, denominator: float) -> dict[str, Any]:
    """Ratio `100 % / 10 %` con su veredicto contra la cota de TRD §6."""
    ratio = round(numerator / denominator, 3) if denominator else None
    return {
        "ratio_100_over_10": ratio,
        "threshold": RATIO_MAX,
        "pass": ratio is not None and ratio <= RATIO_MAX,
    }


def _ntfs_block(delta: dict[str, Any] | None, walk: dict[str, Any] | None) -> dict[str, Any]:
    """Cifra de NTFS como LÍMITE (D-P6-3): causa, presupuesto y recomendación."""
    block: dict[str, Any] = {
        "measured": delta is not None,
        "decides_criterion": False,
        "note": (
            "LÍMITE CONOCIDO (D-P6-3): no decide el criterio 6. El vault vive en el montaje "
            "fuseblk/NTFS-3G y su índice se construyó en frío ahí (mismo corpus y método que el "
            "brazo btrfs de 11 000)."
        ),
        "cause": (
            "walk de 11 000 entradas en NTFS-3G: 22 945 ms de mediana aquí (17,6 s en P-02); el "
            "ciclo de update lo domina el walk + el stat/memo del árbol sobre FUSE, no el embed "
            "de los 10 documentos"
        ),
        "recommendation": (
            "el presupuesto de 30 s es de un FS local rápido (btrfs/ext4/APFS); un vault en "
            "NTFS-3G, unidad de red o carpeta sincronizada (OneDrive/Dropbox) degrada el Δ por "
            "encima del presupuesto — mantener el vault en el disco local del sistema"
        ),
    }
    if delta is not None:
        block.update(
            {
                "label": delta["label"],
                "p95_ms": delta["p95_ms"],
                "budget_ms": BUDGET_MS,
                "verdict": "PASS" if delta["p95_ms"] < BUDGET_MS else "FAIL",
                "walk_median_ms": (walk or {}).get("median_ms"),
                "cold_index_ms": (
                    _load("ntfs")["cold_index_ms"] if (WORK_DIR / "ntfs.json").is_file() else None
                ),
                "discarded_attempt": (
                    "copiar el índice de btrfs al montaje fuseblk: el memo del engine no cruza el "
                    "cambio de ruta y CADA refresh re-extrae y re-embebe las 11 000 entradas "
                    "(96-204 s por ciclo, con indexed=0); se descartó y se indexó en frío en el FS"
                ),
                "samples_ms": delta["samples_ms"],
            }
        )
    return block


def _phase_report() -> dict[str, Any]:
    """Aplica la cota de 2×, archiva el JSON de evidencia y resume los veredictos."""
    cold = {
        "b10_btrfs_ms": _load("index10")["elapsed_ms"],
        "b100_btrfs_ms": 543_645,
        "ntfs_fuseblk_ms": (
            _load("ntfs")["cold_index_ms"] if (WORK_DIR / "ntfs.json").is_file() else None
        ),
        "note": (
            "indexación en frío de las 11 000 entradas: btrfs = T4, fuseblk = este bench. "
            "El coste del FS se ve aquí, no en el Δ de 10 ficheros"
        ),
    }
    present = [arm for arm in ARMS if any(WORK_DIR.glob(f"delta-{arm}-*.json"))]
    deltas = {arm: _arm_delta(arm) for arm in present}
    walks = {
        arm: json.loads((WORK_DIR / f"walk-{arm}.json").read_text("utf-8"))
        for arm in ARMS
        if (WORK_DIR / f"walk-{arm}.json").is_file()
    }
    search = _load("search")
    latency = {arm: _search_block(search["arms"][arm]) for arm in ("b10", "b100")}
    delta_ratio = _ratio(deltas["b100"]["p95_ms"], deltas["b10"]["p95_ms"])
    search_ratio = _ratio(latency["b100"]["p95_client_ms"], latency["b10"]["p95_client_ms"])
    baseline_delta = deltas["b100"]["p95_ms"] - BASELINE_P02_MS

    result = {
        "metric": (
            "criterio 6 — brazos 10 % vs 100 % (Δ p95 n=20 y search p95 n=100) en btrfs "
            "y en fuseblk/NTFS-3G"
        ),
        "verdict": "PASS" if delta_ratio["pass"] else "FAIL",
        "criterion": {
            "rule": f"p95(100 %) / p95(10 %) ≤ {RATIO_MAX}",
            "delta": delta_ratio,
            "search": search_ratio,
            "decided_by": "Δ p95 (índice 100 % = T4, índice 10 % propio en frío)",
            "deciding_filesystem": "btrfs (/tmp/opencode, NVMe) — D-P6-3",
        },
        "delta": {
            "budget_ms": BUDGET_MS,
            "percentile_definition": "nearest-rank: sorted[ceil(0.95*n)-1] = 19.º valor de 20",
            "arms": deltas,
            "baseline_p02": {
                "btrfs_p95_ms": BASELINE_P02_MS,
                "measured_p95_ms": deltas["b100"]["p95_ms"],
                "difference_ms": baseline_delta,
                "difference_pct": round(100 * baseline_delta / BASELINE_P02_MS, 1),
                "source": (
                    "docs/TECH_DEBT.md §Review 5-ejes Phase 3.5 (bench P-02, "
                    "bench_delta_scale.py, corpus sin manifiesto)"
                ),
            },
        },
        "search": {
            "budget_ms": 500,
            "n": search["n"],
            "query_seed": search["query_seed"],
            "queries": "las 100 de T4 (mismo muestreo y mismo texto)",
            "arms": latency,
            "verdict": (
                "PASS"
                if max(block["p95_client_ms"] for block in latency.values()) < 500
                else "FAIL"
            ),
        },
        "walk_only": walks,
        "cold_index": cold,
        "ntfs_limit": _ntfs_block(deltas.get("ntfs"), walks.get("ntfs")),
        "method": {
            "host": _host_block(VAULT100),
            "modified_per_run": MODIFIED_PER_RUN,
            "why_constant_rewrite": (
                "10 ficheros en AMBOS brazos: el embed queda constante y el ratio aísla el "
                "walk/engine a escala (lo que pregunta el criterio 6)"
            ),
            "arm_isolation": (
                "el brazo 100 % usa el índice de T4 (11 006 chunks) y el 10 % su propio índice "
                "en frío (1 100 entradas): no se compara un índice contra sí mismo; ambos brazos "
                "se miden en el mismo host con el mismo método"
            ),
            "order": (
                "prepare → index10 → search (índices intactos) → delta b100 → delta b10 → walk "
                "→ ntfs → delta ntfs → report"
            ),
            "documents": (
                "los PDF de 30+ páginas van APARTE (D51, T2: 3 144 ms p50 / 4 172 ms p95, n=3, "
                "documents.md): no se mezclan con el Δ de texto"
            ),
            "top_k": TOP_K,
        },
        "generated_utc": datetime.now(UTC).isoformat(),
        "commands": COMMANDS,
    }
    DIAGNOSIS_JSON.parent.mkdir(parents=True, exist_ok=True)
    DIAGNOSIS_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    _emit(
        {
            "report": str(DIAGNOSIS_JSON),
            "verdict": result["verdict"],
            "delta_p95_ms": {arm: block["p95_ms"] for arm, block in deltas.items()},
            "delta_ratio": delta_ratio,
            "search_p95_client_ms": {arm: b["p95_client_ms"] for arm, b in latency.items()},
            "search_ratio": search_ratio,
            "walk_median_ms": {arm: b.get("median_ms") for arm, b in walks.items()},
            "ntfs": result["ntfs_limit"].get("verdict"),
        }
    )
    return result


def main() -> int:
    """CLI: `--phase <fase>`; `--delta-driver`/`--walk-driver` son internos."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--phase", choices=["prepare", "index10", "search", "walk", "delta", "ntfs", "report"]
    )
    parser.add_argument("--arm", choices=sorted(ARMS), help="brazo de las fases walk/delta")
    parser.add_argument("--start", type=int, default=0, help="primer ciclo Δ del tramo")
    parser.add_argument("--cycles", type=int, default=5, help="ciclos Δ del tramo")
    parser.add_argument(
        "--pass",
        dest="pass_no",
        type=int,
        default=0,
        help="marca de pasada del contenido reescrito: una repetición tras un tramo perdido "
        "usa --pass 1 para que la reescritura vuelva a ser un cambio real",
    )
    parser.add_argument("--keep", action="store_true", help="conservar el vault NTFS")
    parser.add_argument("--delta-driver", nargs=4, metavar=("VAULT", "START", "CYCLES", "PASS"))
    parser.add_argument("--walk-driver", nargs=2, metavar=("VAULT", "SAMPLES"))
    args = parser.parse_args()

    if args.delta_driver:
        vault, start, cycles, pass_no = args.delta_driver
        _delta_driver(Path(vault), int(start), int(cycles), int(pass_no))
        return 0
    if args.walk_driver:
        vault, samples = args.walk_driver
        _walk_driver(Path(vault), int(samples))
        return 0
    if not args.phase:
        parser.error("falta --phase")
    if args.phase in {"walk", "delta"} and args.arm is None:
        parser.error(f"--phase {args.phase} exige --arm {sorted(ARMS)}")
    if args.phase != "prepare":
        _measure_env(VAULT10)

    try:
        if args.phase == "prepare":
            payload = _phase_prepare()
        elif args.phase == "index10":
            payload = _phase_index10()
        elif args.phase == "search":
            payload = _phase_search()
        elif args.phase == "walk":
            payload = _phase_walk(args.arm or "", WALK_SAMPLES)
        elif args.phase == "delta":
            payload = _phase_delta(args.arm or "", args.start, args.cycles, args.pass_no)
        elif args.phase == "ntfs":
            payload = _phase_ntfs()
        else:
            payload = _phase_report()
        if args.phase == "report":
            # `_phase_report` ya archiva el JSON de evidencia (con sus veredictos).
            pass
        else:
            chunk = f"-{payload['start']}" if "start" in payload else ""
            _save(payload["phase"] + chunk, payload)
            _emit(payload)
        created = [str(path) for path in (PAYLOAD_DB, PAYLOAD_MODELS) if path.exists()]
        if created:
            raise SystemExit(f"el payload fue contaminado: {created}")
        return 0
    finally:
        # El vault NTFS (11k entradas + índice) solo se conserva con --keep: el
        # checkout del repo queda limpio en cuanto el informe está archivado.
        if args.phase == "report" and not args.keep and NTFS_VAULT.parent.exists():
            shutil.rmtree(NTFS_VAULT.parent, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
