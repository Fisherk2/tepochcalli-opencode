"""Bench de escala del criterio 3 (10k/1k, n=100) + deriva del FTS ES/EN — Phase 6 T4.

Líneas: 501-700 justificado (herramienta one-shot de medición, como su hermano
`bench_search.py`); el grueso es el docstring de protocolo y el JSON publicado.

Qué mide (sobre el corpus de T1: 10 000 md + 1 000 PDF, verificado por
manifiesto, copiado a un vault propio — el corpus de T1 **nunca** se toca in
situ — y con el índice construido UNA sola vez en la fase `index`):

* **Criterio 3 a escala:** `p95_client_ms` (reloj del cliente por stdio real,
  incluye IPC: la cifra que decide) y `p95_server_took_ms` (handler), con
  **n = 100 consultas muestreadas del corpus**, `top_k=5` y percentil
  **nearest-rank** `sorted[ceil(0.95·n)-1]` (n=100 ⇒ el 95º valor ordenado).
* **Tabla por etapa** (embed / ANN+FTS / ensamblado / IPC) con método y margen:
  las cuatro fórmulas son las de `_stage_phase` de `bench_search.py`, con 100
  muestras en vez de 20.
* **Deriva FTS ES/EN:** `recall@5` de las MISMAS 100 consultas con la pierna FTS
  activa (híbrido ANN+FTS+RRF, el camino de producción) contra **solo ANN**, más
  el rango del fichero de origen en la **pierna FTS sola** (BM25), que es lo que
  da resolución al mecanismo.
* **Sonda del mecanismo** (`probe`, ver `tests/support/fts_probe.py`): el corpus
  de escala no tiene variación morfológica, así que por sí solo no puede
  demostrar la deriva del stemming inglés sobre español; la sonda sí, con pares
  flexivos y dos controles ingleses.

Umbral: `docs/TRD.md` §6.2 (T0/CP-0): deriva = caída de recall ES **> 10 %
relativo**. No se renegocia aquí; si no se dispara, se publica igual.

Cómo se apaga la pierna FTS: **la consulta ANN pura se construye DENTRO del
bench** (misma tabla, mismo embedder, misma conexión por llamada). No se añade
ningún keyword al adaptador ni se toca el contrato MCP ni el puerto
`ChunkReader` (ADR-005); la comparación aísla exactamente la pierna FTS/RRF.

Fases (una llamada de primer plano por fase; nada en segundo plano)::

    just python-bench-search-scale --phase prepare   # verifica corpus + copia al vault
    just python-bench-search-scale --phase index     # UNA indexación en frío (~10 min)
    just python-bench-search-scale --phase queries   # n=100 por stdio (client + took)
    just python-bench-search-scale --phase stages    # n=100 por etapa, en proceso
    just python-bench-search-scale --phase legs      # híbrido vs ANN vs FTS-solo
    just python-bench-search-scale --phase probe     # sonda morfológica ES/EN
    just python-bench-search-scale --phase report    # une todo → JSON archivado
    just python-bench-search-scale --phase all       # las siete en orden (30+ min)

Cada fase escribe `<WORK_DIR>/<fase>.json`; `report` archiva el JSON unificado
en `docs/diagnosis/phase6-search-scale.json`. El vault es **estable entre
fases**: los dos brazos de recall se miden sobre el MISMO índice, sin reindexar.

No corre en CI ni en `just ci` (no es `test_*`), no re-materializa el corpus si
el manifiesto verifica, y aborta si `obsidian-workspace/.tepochcalli/{db,models}`
apareciera (el payload no se contamina).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
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
from bench_search import (  # noqa: E402
    STAGE_BUDGETS_MS,
    TOP_K,
    VAULT_ROOT_ENV,
    _p95_block,
    _stage_phase,
    _stdio_phase,
)
from corpus import (  # noqa: E402
    DEFAULT_MD_FILES,
    DEFAULT_PDF_FILES,
    DEFAULT_SEED,
    MANIFEST_NAME,
    RESOURCES_DIR,
    Manifest,
    materialize_or_verify,
    verify,
)
from model_cache import link_model_cache, offline_env, resolve_model_cache  # noqa: E402

BUDGET_MS = 500
"""Criterio 3: p95 (nearest-rank, n=100) de la llamada CLIENTE < 500 ms."""

N_QUERIES = 100
"""Consultas muestreadas del corpus (protocolo TRD §6.1, criterio 3)."""

QUERY_WORDS = 12
"""Palabras por consulta: una frase del fichero de origen (el PDF, si es más corto)."""

QUERY_SEED = 20261112
"""Semilla del muestreo de consultas (determinista: las 100 se publican en el JSON)."""

DRIFT_MAX_RELATIVE_DROP = 0.10
"""Umbral T0/CP-0 (`docs/TRD.md` §6.2): caída de recall ES > 10 % relativo."""

FTS_DEPTH = 50
"""Profundidad con la que se busca el fichero de origen en la pierna FTS sola."""

CORPUS_ROOT = Path("/tmp/opencode/phase6-corpus")
"""Corpus de T1 (btrfs/NVMe): se VERIFICA y se copia; no se escribe ni se borra."""

WORK_DIR = Path("/tmp/opencode/phase6-search-scale")
VAULT = WORK_DIR / "vault"
"""Vault del bench con `.tepochcalli/db/` — estable entre fases."""

PROBE_VAULT = WORK_DIR / "probe-vault"
"""Vault diminuto de la sonda morfológica (se reconstruye, no se mide dos veces)."""

REPO_ROOT = Path(__file__).resolve().parents[2]
DIAGNOSIS_JSON = REPO_ROOT / "docs" / "diagnosis" / "phase6-search-scale.json"

PAYLOAD_DB = REPO_ROOT / "obsidian-workspace" / ".tepochcalli" / "db"
PAYLOAD_MODELS = REPO_ROOT / "obsidian-workspace" / ".tepochcalli" / "models"


def _emit(obj: dict[str, Any]) -> None:
    """Imprime un objeto JSON (stdout de una fase: solo JSON)."""
    print(json.dumps(obj, indent=2, ensure_ascii=False), flush=True)


def _work(name: str) -> Path:
    return WORK_DIR / f"{name}.json"


def _save(name: str, payload: dict[str, Any]) -> None:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    _work(name).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _load(name: str) -> dict[str, Any]:
    path = _work(name)
    if not path.is_file():
        raise SystemExit(f"falta {path}: corre antes `--phase {name}`")
    return json.loads(path.read_text(encoding="utf-8"))


def _vm_hwm_kib() -> int:
    """Pico de RSS del PROPIO proceso (`VmHWM`, high-water mark del kernel)."""
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmHWM:"):
            return int(line.split()[1])
    return 0


def _sample_queries(manifest: Manifest, n: int, seed: int, words: int) -> list[dict[str, Any]]:
    """Muestrea `n` consultas de `words` palabras de ficheros DISTINTOS del corpus.

    Determinista con `seed`: baraja el manifiesto ordenado por ruta y toma los
    primeros `n` ficheros usables (≥4 palabras de cuerpo). El título
    (`# Nota 00042` / `Informe PDF 00042`) se descarta para que la query no
    contenga el identificador único del fichero. El texto del PDF se extrae con
    el MISMO extractor del índice (`parsers.extract_text`), no con una copia.
    """
    from tepochcalli_flow.parsers import extract_text

    rng = random.Random(seed)
    pool = sorted(manifest.files, key=lambda entry: entry.path)
    rng.shuffle(pool)
    queries: list[dict[str, Any]] = []
    for entry in pool:
        if len(queries) == n:
            break
        path = CORPUS_ROOT / entry.path
        text = path.read_text(encoding="utf-8") if entry.kind == "md" else extract_text(path)
        tokens = [
            token for token in text.split() if not token.startswith("#") and not token.isdigit()
        ]
        if len(tokens) < 4:
            continue
        width = min(words, len(tokens))
        start = rng.randrange(len(tokens) - width + 1)
        queries.append(
            {
                "query": " ".join(tokens[start : start + width]),
                "source_path": entry.path,
                "kind": entry.kind,
                "lang": "es",
                "words": width,
            }
        )
    if len(queries) != n:
        raise SystemExit(f"el corpus solo dio {len(queries)} consultas usables de {n}")
    return queries


def _phase_prepare() -> dict[str, Any]:
    """Verifica el corpus de T1, copia su `00-Resources/` al vault y muestrea las 100 queries."""
    started = time.monotonic()
    manifest, reused = materialize_or_verify(
        CORPUS_ROOT,
        md_count=DEFAULT_MD_FILES,
        pdf_count=DEFAULT_PDF_FILES,
        seed=DEFAULT_SEED,
    )
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    if VAULT.exists():
        copied = False
    else:
        shutil.copytree(CORPUS_ROOT / RESOURCES_DIR, VAULT / RESOURCES_DIR)
        shutil.copy2(CORPUS_ROOT / MANIFEST_NAME, VAULT / MANIFEST_NAME)
        copied = True
    problems = verify(VAULT, manifest)
    if problems:
        raise SystemExit(f"el vault del bench no coincide con el corpus: {problems[:5]}")
    models_link = VAULT / ".tepochcalli" / "models"
    if copied:
        link_model_cache(VAULT, resolve_model_cache())
    if not models_link.exists():
        raise SystemExit(f"falta el cache de modelo en {models_link} (recrea el vault)")
    queries = _sample_queries(manifest, N_QUERIES, QUERY_SEED, QUERY_WORDS)
    return {
        "phase": "prepare",
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "corpus": {
            "root": str(CORPUS_ROOT),
            "reused": reused,
            "seed": manifest.seed,
            "generator_version": manifest.generator_version,
            "totals": manifest.to_dict()["totals"],
            "tree_sha256": manifest.tree_sha256,
        },
        "vault": str(VAULT),
        "vault_copied": copied,
        "vault_verified": len(problems) == 0,
        "models_cache": str(models_link.resolve()),
        "query_seed": QUERY_SEED,
        "query_words": QUERY_WORDS,
        "queries": queries,
    }


def _phase_index() -> dict[str, Any]:
    """UNA indexación en frío del vault (Phase 1 `refresh_blocking`) + conteo de filas."""
    from tepochcalli_flow import app as flow_app
    from tepochcalli_flow.adapters.lancedb_reader import LanceDBChunkReader
    from tepochcalli_flow.layout import DB_RELPATH

    assert os.environ.get(VAULT_ROOT_ENV) == str(VAULT), (
        "la fase index debe correr con el vault del bench en TEPOCHCALLI_VAULT_ROOT"
    )
    expected = DEFAULT_MD_FILES + DEFAULT_PDF_FILES
    swap_start = _swap_free_kb()
    wall = time.perf_counter()
    report = flow_app.refresh_blocking()
    wall_ms = round((time.perf_counter() - wall) * 1000)
    if report.locked:
        raise SystemExit("[index] refresh inesperadamente locked=True")
    if report.scanned != expected:
        raise SystemExit(f"[index] scanned={report.scanned} != {expected}")
    if report.indexed != expected:
        # Premisa del criterio: el corpus indexado DE VERDAD; un fallo por fichero
        # absorbido en `skipped` (lección F-T7-2) invalidaría la medición.
        raise SystemExit(
            f"[index] indexed={report.indexed} != {expected} (skipped={report.skipped})"
        )
    rows = asyncio.run(LanceDBChunkReader(VAULT / DB_RELPATH, embed=lambda text: []).count_rows())
    if rows < expected:
        raise SystemExit(f"[index] filas={rows} < {expected} ficheros: índice incompleto")
    return {
        "phase": "index",
        "elapsed_ms": report.elapsed_ms,
        "wall_ms": wall_ms,
        "scanned": report.scanned,
        "indexed": report.indexed,
        "skipped": report.skipped,
        "rows": rows,
        "roots": list(report.roots),
        "rss_peak_kib": _vm_hwm_kib(),
        "swap_free_kb_start": swap_start,
        "swap_free_kb_end": _swap_free_kb(),
    }


def _phase_queries() -> dict[str, Any]:
    """Las 100 consultas por stdio REAL: `client_ms` (incluye IPC) y `took_ms` del handler."""
    queries = _load("prepare")["queries"]
    warm, calls = _stdio_phase(VAULT, [item["query"] for item in queries])
    return {"phase": "queries", "n": len(calls), "warm": warm, "calls": calls}


def _phase_stages() -> dict[str, Any]:
    """Presupuesto por etapa con 100 muestras (`_stage_phase` de `bench_search.py`)."""
    queries = _load("prepare")["queries"]
    meta, stages = _stage_phase(VAULT, [item["query"] for item in queries])
    return {"phase": "stages", "meta": meta, "stages": stages}


def _phase_legs() -> dict[str, Any]:
    """Las tres piernas sobre el MISMO índice: híbrido (producción), solo ANN y FTS solo.

    * **híbrido:** `LanceDBChunkReader.search` — el camino exacto que usa el
      server (embeddings + ANN+FTS + RRF), sin IPC.
    * **solo ANN:** `nearest_to(vector)` sobre la MISMA tabla, con el mismo
      embedder y conexión abierta/cerrada por llamada; sin `nearest_to_text`.
    * **FTS solo:** `query_type="fts"`, profundidad 50, para saber en qué
      puesto queda el fichero de origen cuando solo puntúa BM25.
    """
    import lancedb
    from tepochcalli_flow.adapters.lancedb_reader import LanceDBChunkReader
    from tepochcalli_flow.config import load_config
    from tepochcalli_flow.layout import DB_RELPATH, TABLE_NAME
    from tepochcalli_mcp.backend import _read_embedder

    queries = _load("prepare")["queries"]
    config = load_config(VAULT)
    config.apply_model_cache_env()
    embed = _read_embedder(config)
    reader = LanceDBChunkReader(VAULT / DB_RELPATH, embed=embed)

    async def run() -> list[dict[str, Any]]:
        db = await lancedb.connect_async(str(VAULT / DB_RELPATH))
        try:
            table = await db.open_table(TABLE_NAME)
            records: list[dict[str, Any]] = []
            for item in queries:
                query = item["query"]
                started = time.perf_counter()
                hybrid = [chunk.source_path for chunk in await reader.search(query, TOP_K)]
                hybrid_ms = round((time.perf_counter() - started) * 1000, 1)
                vector = await asyncio.to_thread(embed, query)
                started = time.perf_counter()
                ann_rows = await (
                    table.query().nearest_to(vector).select(["source_path"]).limit(TOP_K).to_list()
                )
                ann_ms = round((time.perf_counter() - started) * 1000, 1)
                fts = await table.search(query, query_type="fts", fts_columns="text")
                fts_rows = await fts.select(["source_path"]).limit(FTS_DEPTH).to_list()
                records.append(
                    {
                        **item,
                        "hybrid_paths": hybrid,
                        "ann_paths": [str(row["source_path"]) for row in ann_rows],
                        "fts_paths": [str(row["source_path"]) for row in fts_rows],
                        "hybrid_ms": hybrid_ms,
                        "ann_ms": ann_ms,
                    }
                )
            return records
        finally:
            db.close()  # type: ignore[no-untyped-call]  # close() sin anotar en lancedb 0.40.0

    return {"phase": "legs", "n_rows": len(queries), "queries": asyncio.run(run())}


def _phase_probe() -> dict[str, Any]:
    """Sonda del mecanismo de deriva FTS ES/EN sobre un vault diminuto (ver `fts_probe`)."""
    from fts_probe import run_probe

    return {
        "phase": "probe",
        **run_probe(PROBE_VAULT, vault_root_env=VAULT_ROOT_ENV, top_k=TOP_K),
    }


def _recall(records: list[dict[str, Any]], key: str) -> dict[str, Any]:
    """`recall@5` y MRR del fichero de origen dentro de `records[*][key]`."""
    hits = 0
    reciprocal = 0.0
    for record in records:
        paths = record[key]
        if record["source_path"] in paths:
            hits += 1
            reciprocal += 1.0 / (paths.index(record["source_path"]) + 1)
    total = len(records)
    return {
        "recall_at_5": round(hits / total, 4),
        "hits": hits,
        "n": total,
        "mrr": round(reciprocal / total, 4),
    }


def _phase_report() -> dict[str, Any]:
    """Une las fases, aplica umbrales y archiva el JSON de evidencia."""
    prepare = _load("prepare")
    index = _load("index")
    queries = _load("prepare")["queries"]
    calls = _load("queries")["calls"]
    stage_payload = _load("stages")
    legs = _load("legs")["queries"]
    probe = _load("probe")
    if len(calls) != len(queries) or len(legs) != len(queries):
        raise SystemExit("n de consultas inconsistente entre fases")

    client = [float(record["client_ms"]) for record in calls]
    took = [float(record["took_ms"]) for record in calls]
    ipc = [client_ms - took_ms for client_ms, took_ms in zip(client, took, strict=True)]
    stages = stage_payload["stages"]
    samples = {
        "embed": [float(record["embed_ms"]) for record in stages],
        "ann_fts": [float(record["chunks_ms"]) - float(record["embed_ms"]) for record in stages],
        "assembly": [
            float(record["handler_ms"])
            - float(record["chunks_ms"])
            - float(record["index_models_ms"])
            + float(record["json_ms"])
            for record in stages
        ],
        "ipc": ipc,
    }
    stages_block = {
        name: _p95_block(values, STAGE_BUDGETS_MS[name]) for name, values in samples.items()
    }
    # El handler lee el estado del índice en CADA llamada (`index_models`); la
    # tabla de la spec no tiene fila para eso, así que se publica aparte: sin
    # ella las cuatro etapas no reconcilian con el total medido.
    index_state = [float(record["index_models_ms"]) for record in stages]
    index_state_p95 = round(_nearest_rank_p(index_state, 0.95), 1)
    stages_block["index_state"] = {
        "method": (
            "DIRECTA: `_VaultSearchBackend.index_models` (lectura del estado del índice) "
            "por llamada; NO está en la tabla de presupuesto de spec-mcp-server"
        ),
        "p95_ms": index_state_p95,
        "budget_ms": None,
        "pass": None,
        "min": round(min(index_state), 1),
        "max": round(max(index_state), 1),
    }
    p95_client = _nearest_rank_p(client, 0.95)
    p95_took = _nearest_rank_p(took, 0.95)
    latency_pass = p95_client < BUDGET_MS and all(
        block["pass"] for name, block in stages_block.items() if name != "index_state"
    )
    reconciliation = {
        "stage_p95_sum_ms": round(
            sum(block["p95_ms"] for block in stages_block.values() if block["budget_ms"]), 1
        ),
        "plus_index_state_p95_ms": round(index_state_p95, 1),
        "total_vs_p95_client_ms": p95_client,
        "note": "las cuatro etapas de la spec + `index_state` reconstruyen el total cliente",
    }

    def arm(key: str, source: list[dict[str, Any]]) -> dict[str, Any]:
        """`recall@5`/MRR de `source[*][key]` contra el `source_path` esperado."""
        rows = [{"source_path": r["source_path"], "paths": r[key]} for r in source]
        return _recall(rows, "paths")

    server = [
        {"source_path": q["source_path"], "paths": c["top_paths"]}
        for q, c in zip(queries, calls, strict=True)
    ]
    server_recall = _recall(server, "paths")
    hybrid_recall = arm("hybrid_paths", legs)
    ann_recall = arm("ann_paths", legs)
    fts_ranks = [
        r["fts_paths"].index(r["source_path"]) + 1 if r["source_path"] in r["fts_paths"] else None
        for r in legs
    ]

    def by_kind(kind: str, key: str) -> dict[str, Any]:
        """`recall@5` restringido a las consultas de un tipo de fuente (md | pdf)."""
        rows = [
            {"source_path": r["source_path"], "paths": r[key]} for r in legs if r["kind"] == kind
        ]
        return _recall(rows, "paths")

    fts_block = {
        "ranked_top_5": sum(rank is not None and rank <= TOP_K for rank in fts_ranks),
        "ranked_top_50": sum(rank is not None for rank in fts_ranks),
        "not_found_in_50": sum(rank is None for rank in fts_ranks),
        "n": len(fts_ranks),
        "mean_rank_when_found": round(
            sum(rank for rank in fts_ranks if rank is not None)
            / max(1, sum(rank is not None for rank in fts_ranks)),
            1,
        ),
    }
    ann_recall_at_5 = float(ann_recall["recall_at_5"])
    hybrid_recall_at_5 = float(hybrid_recall["recall_at_5"])
    if ann_recall_at_5 == 0:
        drift: dict[str, Any] = {
            "relative_drop": None,
            "exceeds_threshold": False,
            "reason": (
                "recall ANN-only = 0: la caída RELATIVA no está definida y la pierna FTS "
                "solo puede sumar; se publica el recall absoluto de cada brazo"
            ),
        }
    else:
        relative_drop = (ann_recall_at_5 - hybrid_recall_at_5) / ann_recall_at_5
        drift = {
            "relative_drop": round(relative_drop, 4),
            "exceeds_threshold": relative_drop > DRIFT_MAX_RELATIVE_DROP,
            "reason": f"umbral T0/CP-0: caída relativa > {DRIFT_MAX_RELATIVE_DROP:.0%}",
        }

    payload_created = [str(path) for path in (PAYLOAD_DB, PAYLOAD_MODELS) if path.exists()]
    if payload_created:
        raise SystemExit(f"el payload fue contaminado: {payload_created}")
    result = {
        "metric": "criterio 3 a escala (10k md + 1k pdf) + deriva FTS ES/EN — Phase 6 T4",
        "verdict": "PASS" if latency_pass else "FAIL",
        "budget_ms": BUDGET_MS,
        "n": len(client),
        "percentile_definition": (
            "nearest-rank: sorted[ceil(0.95*n)-1]; con n=100 es el 95º valor ordenado"
        ),
        "p95_client_ms": p95_client,
        "p95_server_took_ms": p95_took,
        "samples_client_ms": [round(value) for value in client],
        "samples_server_took_ms": [round(value) for value in took],
        "samples_ipc_ms": [round(value, 1) for value in ipc],
        "stages": stages_block,
        "stage_measurement": {
            "note": (
                "embed e IPC ~directos; ANN+FTS y ensamblado son estimaciones por DIFERENCIA "
                "(método y margen por etapa en cada bloque y en bench_search.py)"
            ),
            "spec_table_ms": STAGE_BUDGETS_MS,
            "chunks_indexed": stage_payload["meta"]["chunks_indexed"],
        },
        "recall": {
            "hybrid_server": server_recall,
            "hybrid_in_process": hybrid_recall,
            "ann_only_in_process": ann_recall,
            "fts_leg": fts_block,
            "hybrid_by_kind": {
                "md": by_kind("md", "hybrid_paths"),
                "pdf": by_kind("pdf", "hybrid_paths"),
            },
            "ann_by_kind": {"md": by_kind("md", "ann_paths"), "pdf": by_kind("pdf", "ann_paths")},
            "hybrid_also_fts_top5": sum(r["source_path"] in r["fts_paths"][:TOP_K] for r in legs),
        },
        "reconciliation": reconciliation,
        "drift": {
            **drift,
            "threshold_relative_drop": DRIFT_MAX_RELATIVE_DROP,
            "arms": "mismo corpus, mismas 100 consultas, MISMO índice (sin reindexar entre brazos)",
        },
        "probe": probe,
        "index": index,
        "corpus": prepare["corpus"],
        "queries": queries,
        "host": _host_block(VAULT),
        "query_seed": QUERY_SEED,
        "query_words": QUERY_WORDS,
        "top_k": TOP_K,
        "generated_utc": datetime.now(UTC).isoformat(),
        "commands": [f"just python-bench-search-scale --phase {name}" for name in PHASES],
    }
    DIAGNOSIS_JSON.parent.mkdir(parents=True, exist_ok=True)
    DIAGNOSIS_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def _swap_free_kb() -> int | None:
    """SwapFree actual (kB) — la presión de swap inflaría el p95 (lección T10)."""
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("SwapFree:"):
            return int(line.split()[1])
    return None


PHASES: dict[str, Any] = {
    "prepare": _phase_prepare,
    "index": _phase_index,
    "queries": _phase_queries,
    "stages": _phase_stages,
    "legs": _phase_legs,
    "probe": _phase_probe,
    "report": _phase_report,
}


def _measure_env() -> None:
    """Env de las fases de medición: vault del bench + cache de modelo + offline."""
    models = VAULT / ".tepochcalli" / "models"
    os.environ[VAULT_ROOT_ENV] = str(VAULT)
    os.environ["HF_HOME"] = str(models)
    os.environ["SENTENCE_TRANSFORMERS_HOME"] = str(models)
    os.environ.update(offline_env(resolve_model_cache()))
    os.environ.pop("COCOINDEX_DB", None)


def _run_all() -> int:
    """Corre las siete fases en orden, cada una en su proceso y en primer plano."""
    payload = _phase_prepare()  # en el padre: aún no hay symlink de modelo que resolver
    _save("prepare", payload)
    _emit(payload)
    _measure_env()
    for name in ("index", "queries", "stages", "legs", "probe", "report"):
        print(f"=== fase {name} ===", flush=True)
        subprocess.run([sys.executable, str(Path(__file__).resolve()), "--phase", name], check=True)
    return 0


def main() -> int:
    """CLI: `--phase <fase>` corre una fase; `--phase all` las encadena."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--phase", required=True, choices=[*PHASES, "all"], help="fase del bench a correr"
    )
    args = parser.parse_args()
    if args.phase == "all":
        return _run_all()
    if args.phase != "prepare":
        _measure_env()
    payload = PHASES[args.phase]()
    _save(args.phase, payload)
    _emit(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
