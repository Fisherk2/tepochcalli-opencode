"""Bench `search` <500 ms p95 (criterio 3) + presupuesto POR ETAPA medido — T7.

Fuente de verdad del protocolo: **specs/spec-mcp-server.md §Presupuesto de
latencia** (punto de medición = tool-call recibido → respuesta serializada,
embed de la query incluido; tabla etapa: embed ≤120 · ANN+FTS ≤200 ·
ensamblado ≤30 · IPC ≤150 · total ≤500) y **tasks/todo.md T7** (AC: p95 <500 ms
sobre fixture de 100 archivos publicando n y método de percentil).

Qué mide y qué no
-----------------
* **Fase stdio (la cifra del criterio 3):** UN server hijo
  `python -m tepochcalli_mcp` por stdio real; el padre cronometra la llamada
  COMPLETA del cliente (`client_ms`, de `call_tool` a payload parseado) y lee
  `took_ms` que el handler reporta dentro. Se publican AMBOS p95:
  `p95_client_ms` (puerta del gate: incluye IPC, la experiencia real) y
  `p95_server_took_ms` (punto de medición de la spec, dentro del handler).
  UNA llamada de calentamiento ANTES de las 20 muestras: la PRIMERA búsqueda
  del server construye el lector + MiniLM dentro del hijo (segundos) — la spec
  excluye el cold start del proceso de la medición, igual que bench_delta
  excluye el índice frío.
* **Fase de etapas (presupuesto por etapa):** corre EN EL DRIVER con los
  MISMOS componentes que el composition root (`build_embedder(config)` +
  `LanceDBChunkReader` + handler `tools/search.py` real + `_VaultSearchBackend`
  para el estado del índice), instrumentados desde FUERA — sin tocar `flow/`
  ni `mcp/`. Cada etapa declara su método y su margen en el JSON publicado:

  * **embed — MEDICIÓN DIRECTA.** `_timed_embed` envuelve el callable real
    texto→vector y cronometra la llamada DENTRO del worker thread
    (`asyncio.to_thread`, el mismo contexto que producción). Margen: ~µs de las
    dos lecturas de `perf_counter` + el wrapper; el salto de hilo NO se cuenta
    (queda fuera de la ventana).
  * **ANN+FTS — DIFERENCIA dentro de la misma llamada** (`chunks_ms −
    embed_ms`, ambas tomadas en el `search` del lector). Eso incluye apertura/
    cierre de conexión LanceDB, la consulta híbrida, `to_list`, el mapeo a
    `CitedChunk` y — honestidad — la espera de scheduling del thread del embed
    (ms posibles bajo carga). Margen: ~µs de reloj; es una estimación por
    diferencia, no un cronometraje de la consulta interna de LanceDB (que
    exigiría instrumentar `flow/`, vedado en T7).
  * **ensamblado — DIFERENCIA + JSON directo**: `handler_ms − chunks_ms −
    index_models_ms` (validación, seams, `apply_budget`, armado del dict) más
    `json_ms` medido DIRECTAMENTE sobre `tepochcalli_mcp.tools.json_result`
    (el `content[0].text` real). Margen: incluye el overhead fijo del handler
    (µs-ms) y el `asyncio.run` por iteración — se atribuye a esta etapa a
    propósito.
  * **IPC — DIFERENCIA cliente − servidor por llamada stdio**
    (`client_ms − took_ms`). Incluye despacho del SDK, framing JSON-RPC,
    tuberías, la SERIALIZACIÓN server-side (ocurre antes de que el cliente
    vea la respuesta) y ±0,5 ms de cuantización de `took_ms` (entero).

Definición del percentil (nearest-rank, declarada a propósito)
--------------------------------------------------------------
p95 por nearest-rank: `sorted_samples[ceil(0.95 * n) - 1]` (helper
`_nearest_rank_p` REUTILIZADO de `bench_delta.py`). Con **n = 20**, `ceil(19)
= 19` ⇒ el p95 es el **valor ordenado nº 19** (el segundo mayor de 20).
Consecuencias para los outliers, aprendidas con el dolor en n=10 (donde p95
colapsaba al máximo): con n=20 **un único pico aislado NO determina el p95**,
pero las DOS corridas más lentas pesan (la 19ª entra entera). Se publican las
20 muestras crudas de cada etapa para que el lector juzgue.

Reproducción (todos los knobs, fijos por defecto)
-------------------------------------------------
* Corpus determinista: `WORDS` + `_corpus_text` de `bench_delta.py` (MISMO
  vocabulario/tamaños que el bench hermano) para **100 archivos** md/txt — el
  AC dice «fixture de 100 archivos»; el indexador es el MISMO entrypoint que
  usa el fixture de 100 chunks de T2 (`refresh_blocking()` del flow en
  subproceso aislado), no se inventa otro.
* 20 consultas deterministas (`QUERIES`) rotadas por corrida; `top_k=5` (el
  default del contrato y el que cita TRD §6 criterio 3).
* Proceso: UN subproceso driver (environment global de cocoindex aislado,
  patrón `bench_delta`) que indexa, mide por stdio y mide etapas; el padre
  solo orquesta y reporta.
* Modelo: defaults de `tepochcalli_flow.config` (sin `tepochcalli.toml`),
  cache SYMLINK al cache que resuelve `model_cache` (`HF_HOME` externo >
  `~/.cache/huggingface`), offline si el snapshot ya está cacheado.

Garantías de idempotencia (nunca ensucia el repo)
--------------------------------------------------
* Vault bajo `/tmp/opencode/tepochcalli-t1-spike/bench-search/` (borrado al
  final salvo `--keep`); `tests/fixtures/` intacto.
* `obsidian-workspace/.tepochcalli/{db,models}` (payload) NO se crea: el padre
  lo verifica al terminar y aborta si existieran (mismo sello que bench_delta).

Uso (vía recetas del Justfile — el portero de comandos):
    just bench-search              # local: 20 corridas, p95 nearest-rank, etapas
    just bench-search --smoke      # CI: 1 corrida con umbral generoso, SIN percentil
    just bench-search --keep       # conservar el vault temporal para inspección

Modo smoke (`--smoke`) — el ÚNICO gate de `search` que puede correr en CI
------------------------------------------------------------------------
`--smoke` indexa el MISMO corpus de 100 archivos (la premisa del AC) y ejecuta
UNA sola búsqueda por stdio con umbral **generoso de 5000 ms** (~10× margen
sobre lo esperado) y NO calcula percentil alguno: el p95 real de arriba es una
medición LOCAL documentada y jamás corre en CI (misma disciplina que
`bench_delta.py --smoke` y la regla anti-flake T3: las aserciones de la suite
no dependen del reloj). La fase de etapas tampoco corre en smoke.

Marcado `slow`: si pytest recolectara este fichero (fuera de `testpaths`), el
`pytestmark` de abajo lo deselecciona bajo el filtro por omisión `-m 'not
slow'` — en la suite de corrección NADA de este archivo corre.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import random
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bench_delta import WORDS, _corpus_text, _host_block, _nearest_rank_p  # noqa: E402
from model_cache import link_model_cache, offline_env, resolve_model_cache  # noqa: E402

pytestmark = pytest.mark.slow
"""Si pytest recolecta este fichero, jamás corre sin `-m slow` (ver docstring)."""

SEED = 20261026
"""Semilla del corpus: con este entero los archivos y consultas son idénticos."""

N_FILES = 100
"""Tamaño del corpus md/txt (AC de T7: «fixture de 100 archivos»)."""

N_RUNS = 20
"""Corridas del presupuesto (metodología congelada: n=20, nearest-rank)."""

TOP_K = 5
"""`top_k` de las llamadas: el default del contrato (TRD §6 criterio 3)."""

BUDGET_MS = 500
"""Gate 3: p95 (nearest-rank, n=20) de la llamada CLIENTE < 500 ms."""

STAGE_BUDGETS_MS: dict[str, float] = {
    "embed": 120.0,
    "ann_fts": 200.0,
    "assembly": 30.0,
    "ipc": 150.0,
}
"""Tabla de etapas de spec-mcp-server §Presupuesto de latencia (p95)."""

SMOKE_RUNS = 1
"""Corridas del modo `--smoke` (gate de CI): UNA búsqueda, sin percentil."""

SMOKE_BUDGET_MS = 5000
"""Umbral smoke generoso ~10× (caza regresiones de un orden de magnitud)."""

BENCH_DIR = Path("/tmp/opencode/tepochcalli-t1-spike/bench-search")
"""Vaults temporales del bench (btrfs/NVMe, fuera del repo)."""

REPO_ROOT = Path(__file__).resolve().parents[2]

PAYLOAD_DB = REPO_ROOT / "obsidian-workspace" / ".tepochcalli" / "db"
PAYLOAD_MODELS = REPO_ROOT / "obsidian-workspace" / ".tepochcalli" / "models"

NONET_DIR = Path(__file__).resolve().parents[1] / "support" / "nonet"
"""Canario de cero red (`sitecustomize.py`) — va al PYTHONPATH del server hijo."""

VAULT_ROOT_ENV = "TEPOCHCALLI_VAULT_ROOT"
"""Env del vault del flow (contrato de `tepochcalli_flow.app.VAULT_ROOT_ENV`).

Constante local para que el PADRE no importe `app` (arrastra cocoindex); el
driver aserta la igualdad con el nombre real — si el contrato cambiara, el
bench revienta en vez de apuntar a un vault fantasma.
"""

QUERIES: list[str] = [
    f"{WORDS[index]} {WORDS[(index + 7) % len(WORDS)]} y {WORDS[(index * 3) % len(WORDS)]}"
    for index in range(N_RUNS)
]
"""20 consultas deterministas sobre el vocabulario del corpus (rotación por corrida)."""


def _emit(obj: dict[str, Any]) -> None:
    """Imprime un registro JSON por línea (el padre lo parsea; stdout solo es JSON)."""
    print(json.dumps(obj), flush=True)


def _swap_free_kb() -> int | None:
    """SwapFree actual (kB) — presión de swap que inflaría el p95 (lección T10)."""
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("SwapFree:"):
            return int(line.split()[1])
    return None


def _stdio_phase(vault: Path, runs: int) -> None:
    """Fase de medida REAL por stdio: cliente → server hijo → payload (incluye IPC).

    Emite un registro `call` por corrida con `client_ms` (reloj del cliente),
    `took_ms` (reloj DEL HANDLER dentro del payload), `results_n` y
    `truncated`. Una llamada de calentamiento —fuera de las muestras— construye
    el lector y carga MiniLM dentro del hijo. Cualquier `is_error` aborta el
    bench: medir errores no mide `search`.
    """
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = {**os.environ, VAULT_ROOT_ENV: str(vault)}
    pythonpath = [str(NONET_DIR)]
    if existing := os.environ.get("PYTHONPATH"):
        pythonpath.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath)
    queries = QUERIES if runs == N_RUNS else QUERIES[:runs]

    async def go() -> None:
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "tepochcalli_mcp"], env=env
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                warm = await session.call_tool("search", {"query": queries[0], "top_k": TOP_K})
                if warm.is_error:
                    raise SystemExit(f"[warm] el server respondió error: {warm.content[0].text}")
                warm_payload = json.loads(warm.content[0].text)
                if "error" in warm_payload:
                    raise SystemExit(f"[warm] search falló: {warm_payload}")
                _emit(
                    {
                        "kind": "warm",
                        "client_ms": None,
                        "took_ms": warm_payload["took_ms"],
                        "results_n": len(warm_payload["results"]),
                    }
                )
                for index in range(runs):
                    t0 = time.perf_counter()
                    result = await session.call_tool(
                        "search", {"query": queries[index], "top_k": TOP_K}
                    )
                    client_ms = round((time.perf_counter() - t0) * 1000)
                    payload = json.loads(result.content[0].text)
                    if result.is_error or "error" in payload:
                        raise SystemExit(f"[call {index}] search falló: {payload}")
                    _emit(
                        {
                            "kind": "call",
                            "i": index,
                            "client_ms": client_ms,
                            "took_ms": payload["took_ms"],
                            "results_n": len(payload["results"]),
                            "truncated": payload["truncated"],
                        }
                    )

    asyncio.run(go())


def _stage_phase(vault: Path) -> None:
    """Presupuesto POR ETAPA medido en proceso — ver métodos y márgenes del docstring.

    Emite `stage_meta` (filas del índice) y un registro `stage` por corrida con
    los intervalos crudos de los que el padre deriva embed/ANN+FTS/ensamblado.
    Sin instrumentación interna: solo envoltorios sobre los MISMOS objetos que
    el composition root construye (`flow/` y `mcp/` intactos).
    """
    from tepochcalli_flow.adapters.lancedb_reader import LanceDBChunkReader
    from tepochcalli_flow.config import load_config
    from tepochcalli_flow.layout import DB_RELPATH
    from tepochcalli_flow.ports import CitedChunk
    from tepochcalli_mcp.backend import _read_embedder, _VaultSearchBackend
    from tepochcalli_mcp.tools import json_result
    from tepochcalli_mcp.tools import search as search_handler

    config = load_config(vault)
    config.apply_model_cache_env()
    real_embed = _read_embedder(config)
    embed_calls: list[float] = []

    def _timed_embed(text: str) -> list[float]:
        """Embed real cronometrado DIRECTAMENTE (misma ventana que producción)."""
        started = time.perf_counter()
        try:
            return real_embed(text)
        finally:
            embed_calls.append((time.perf_counter() - started) * 1000)

    reader = LanceDBChunkReader(vault / DB_RELPATH, embed=_timed_embed)
    real_backend = _VaultSearchBackend(vault, config)
    last: dict[str, float] = {}

    class _TimedBackend:
        """`SearchBackend` con los MISMOS componentes que `server`, cronometrados fuera."""

        @property
        def expected_model(self) -> str:
            """Delega al backend real del composition root."""
            return real_backend.expected_model

        async def index_models(self) -> set[str]:
            """Estado del índice (misma costura `_select`) con su intervalo."""
            started = time.perf_counter()
            try:
                return await real_backend.index_models()
            finally:
                last["index_models"] = (time.perf_counter() - started) * 1000

        async def cited_chunks(
            self, query: str, top_k: int, path_filter: str | None
        ) -> list[CitedChunk]:
            """Lectura del lector (embed + ANN+FTS) con su intervalo COMPLETO."""
            started = time.perf_counter()
            try:
                return await reader.search(query, top_k, path_filter)
            finally:
                last["chunks"] = (time.perf_counter() - started) * 1000

    backend = _TimedBackend()

    def _run(query: str) -> dict[str, object]:
        """Una corrida del handler real + su `json_result`; devuelve los intervalos."""
        embed_calls.clear()
        t0 = time.perf_counter()
        payload = asyncio.run(
            search_handler.search(
                query,
                TOP_K,
                None,
                backend_factory=lambda: backend,
                embedder_available=lambda: True,  # R1 ya probada en T6/T2; aquí no decide
            )
        )
        handler_ms = (time.perf_counter() - t0) * 1000
        if "error" in payload:
            raise SystemExit(f"[stage] search falló: {payload}")
        t0 = time.perf_counter()
        json_result(payload)
        json_ms = (time.perf_counter() - t0) * 1000
        return {
            "handler_ms": handler_ms,
            "json_ms": json_ms,
            "chunks_ms": last["chunks"],
            "index_models_ms": last["index_models"],
            "embed_ms": embed_calls[-1],
            "took_ms": payload["took_ms"],
        }

    _run(QUERIES[0])  # warm: carga del modelo del driver FUERA de las 20 muestras
    rows = asyncio.run(reader.count_rows())
    _emit({"kind": "stage_meta", "chunks_indexed": rows})
    for index in range(N_RUNS):
        _emit({"kind": "stage", "i": index, **_run(QUERIES[index])})


def _driver(vault: Path, smoke: bool) -> None:
    """Corre en el subproceso: corpus de 100 archivos → índice → fase stdio → etapas.

    `smoke=True` hace UNA sola llamada stdio (sin etapas ni percentil); el
    default ejecuta el protocolo completo de 20 corridas del AC.
    """
    from tepochcalli_flow import app as flow_app

    assert VAULT_ROOT_ENV == flow_app.VAULT_ROOT_ENV, (
        "la env local del bench divergió del contrato del flow"
    )
    runs = SMOKE_RUNS if smoke else N_RUNS
    resources = vault / "00-Resources"
    resources.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    for index in range(N_FILES):
        name = f"nota-{index:02d}." + ("md" if index % 2 == 0 else "txt")
        (resources / name).write_text(_corpus_text(index, rng), encoding="utf-8")

    swap_start = _swap_free_kb()
    _emit({"kind": "start", "python": platform.python_version(), "pid": os.getpid()})

    wall = time.perf_counter()
    report = flow_app.refresh_blocking()
    index_wall_ms = round((time.perf_counter() - wall) * 1000)
    if report.locked:
        raise SystemExit("[index] refresh inesperadamente locked=True")
    if report.scanned != N_FILES:
        raise SystemExit(f"[index] scanned={report.scanned} != {N_FILES}")
    if report.indexed != N_FILES:
        # Premisa del AC: los 100 archivos indexados DE VERDAD — un fallo por
        # fichero absorbido en `skipped` (lección F-T7-2) no puede pasar desapercibido.
        raise SystemExit(
            f"[index] indexed={report.indexed} != {N_FILES} (skipped={report.skipped})"
        )
    _emit(
        {
            "kind": "index",
            "scanned": report.scanned,
            "indexed": report.indexed,
            "skipped": report.skipped,
            "elapsed_ms": report.elapsed_ms,
            "wall_ms": index_wall_ms,
        }
    )

    _stdio_phase(vault, runs)
    if not smoke:
        _stage_phase(vault)
    _emit(
        {
            "kind": "done",
            "swap_free_kb_start": swap_start,
            "swap_free_kb_end": _swap_free_kb(),
        }
    )


def _p95_block(samples: list[float], budget: float) -> dict[str, Any]:
    """Bloque de etapa: p95 nearest-rank (n=20), presupuesto y veredicto."""
    p95 = _nearest_rank_p(samples, 0.95)
    return {
        "p95_ms": round(p95, 1),
        "budget_ms": budget,
        "pass": p95 < budget,
        "samples": [round(sample, 1) for sample in samples],
        "min": round(min(samples), 1),
        "max": round(max(samples), 1),
    }


def _parent(keep_vault: bool, out_path: Path | None, smoke: bool) -> int:
    """Orquesta: vault temporal → driver → veredicto → JSON publicado + resumen."""
    runs = SMOKE_RUNS if smoke else N_RUNS
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    vault = Path(tempfile.mkdtemp(prefix="bench-search-", dir=BENCH_DIR))
    try:
        cache = resolve_model_cache()
        models_link = link_model_cache(vault, cache)
        host = _host_block(vault)
        env = {
            **os.environ,
            VAULT_ROOT_ENV: str(vault),
            "HF_HOME": str(models_link),
            "SENTENCE_TRANSFORMERS_HOME": str(models_link),
            **offline_env(cache),
        }
        env.pop("COCOINDEX_DB", None)
        bench_start = datetime.now(UTC)
        cmd = [sys.executable, str(Path(__file__).resolve()), "--driver", str(vault)]
        proc = subprocess.run(
            cmd + (["--smoke"] if smoke else []),
            env=env,
            capture_output=True,
            text=True,
            timeout=3600,
            check=False,
        )
        if proc.returncode != 0:
            print(proc.stderr[-8000:], file=sys.stderr)
            raise SystemExit(f"el driver del bench falló (rc={proc.returncode})")

        index_record: dict[str, Any] = {}
        warm_record: dict[str, Any] = {}
        calls: list[dict[str, Any]] = []
        stages: list[dict[str, Any]] = []
        stage_meta: dict[str, Any] = {}
        done: dict[str, Any] = {}
        for line in proc.stdout.splitlines():
            stripped = line.strip()
            if not stripped.startswith("{"):
                continue
            record = json.loads(stripped)
            kind = record["kind"]
            if kind == "index":
                index_record = record
            elif kind == "warm":
                warm_record = record
            elif kind == "call":
                calls.append(record)
            elif kind == "stage":
                stages.append(record)
            elif kind == "stage_meta":
                stage_meta = record
            elif kind == "done":
                done = record
        if len(calls) != runs:
            raise SystemExit(f"esperaba {runs} llamadas, llegaron {len(calls)}")
        if not smoke and len(stages) != N_RUNS:
            raise SystemExit(f"esperaba {N_RUNS} corridas de etapa, llegaron {len(stages)}")

        client = [float(record["client_ms"]) for record in calls]
        took = [float(record["took_ms"]) for record in calls]
        ipc = [client_ms - took_ms for client_ms, took_ms in zip(client, took, strict=True)]
        percentile_definition = (
            "nearest-rank: sorted[ceil(0.95*n)-1]; con n=20 es el 19º valor "
            "ordenado (segundo mayor) — un outlier aislado no lo determina, "
            "pero las 2 corridas más lentas pesan"
        )

        stages_block: dict[str, Any] = {}
        if smoke:
            verdict = "PASS" if client[0] < SMOKE_BUDGET_MS else "FAIL"
            p95_client: int | None = None
            p95_took: int | None = None
        else:
            embed = [float(record["embed_ms"]) for record in stages]
            ann_fts = [float(record["chunks_ms"]) - float(record["embed_ms"]) for record in stages]
            assembly = [
                float(record["handler_ms"])
                - float(record["chunks_ms"])
                - float(record["index_models_ms"])
                + float(record["json_ms"])
                for record in stages
            ]
            methods = {
                "embed": (
                    "DIRECTA: perf_counter alrededor del callable build_embedder(config) "
                    "dentro del worker thread (mismo contexto que producción); margen ~µs, "
                    "el salto de hilo queda fuera de la ventana"
                ),
                "ann_fts": (
                    "DIFERENCIA chunks_ms − embed_ms dentro de la MISMA reader.search(): "
                    "incluye apertura de conexión, consulta híbrida, to_list, mapeo a "
                    "CitedChunk y la espera de scheduling del thread del embed; margen "
                    "relojes ~µs — NO descompone la consulta interna de LanceDB (exigiría "
                    "instrumentar flow/, vedado en T7)"
                ),
                "assembly": (
                    "DIFERENCIA handler_ms − chunks_ms − index_models_ms (validación, "
                    "seams, apply_budget, dict) + json_ms MEDIDO DIRECTO sobre "
                    "tools.json_result; incluye el overhead fijo del handler y el "
                    "asyncio.run por iteración"
                ),
                "ipc": (
                    "DIFERENCIA client_ms − took_ms por llamada stdio: despacho SDK, "
                    "framing JSON-RPC, tuberías, serialización server-side y ±0,5 ms de "
                    "cuantización de took_ms (entero)"
                ),
            }
            samples = {
                "embed": embed,
                "ann_fts": ann_fts,
                "assembly": assembly,
                "ipc": ipc,
            }
            stages_block = {
                name: {
                    "method": methods[name],
                    **_p95_block(values, STAGE_BUDGETS_MS[name]),
                }
                for name, values in samples.items()
            }
            p95_client = _nearest_rank_p(client, 0.95)
            p95_took = _nearest_rank_p(took, 0.95)
            verdict = (
                "PASS"
                if p95_client < BUDGET_MS and all(block["pass"] for block in stages_block.values())
                else "FAIL"
            )

        payload_created = [str(path) for path in (PAYLOAD_DB, PAYLOAD_MODELS) if path.exists()]
        if payload_created:
            raise SystemExit(f"el payload fue contaminado: {payload_created}")

        result: dict[str, Any] = {
            "metric": (
                f"smoke search CI: 1 corrida vs umbral generoso {SMOKE_BUDGET_MS} ms "
                "(sin percentil, sin etapas)"
                if smoke
                else "criterio 3: p95 search client (nearest-rank, n=20) vs 500 ms + etapas"
            ),
            "verdict": verdict,
            "budget_ms": SMOKE_BUDGET_MS if smoke else BUDGET_MS,
            "n": None if smoke else N_RUNS,
            "percentile_definition": None if smoke else percentile_definition,
            "p95_client_ms": p95_client,
            "p95_server_took_ms": p95_took,
            "samples_client_ms": client,
            "samples_server_took_ms": took,
            "samples_ipc_ms": [round(value, 1) for value in ipc],
            "stages": stages_block,
            "stage_measurement": (
                None
                if smoke
                else {
                    "note": (
                        "embed e IPC ~directos; ANN+FTS y ensamblado son estimaciones por "
                        "DIFERENCIA — método y margen en cada bloque, ver docstring"
                    ),
                    "spec_table_ms": STAGE_BUDGETS_MS,
                }
            ),
            "index": index_record,
            "warm": warm_record,
            "chunks_indexed": stage_meta.get("chunks_indexed"),
            "results_n_min": min(int(record["results_n"]) for record in calls),
            "host": host,
            "swap": done,
            "seed": SEED,
            "n_files": N_FILES,
            "top_k": TOP_K,
            "bench_started_utc": bench_start.isoformat(),
            "deviation_from_trd_reference_host": (
                "TRD §6 fija VM limpia 8GB SSD como referencia; esta medición es sobre el "
                "host de desarrollo (ver host block) — declarado como desviación"
            ),
        }
        out_path = out_path or BENCH_DIR / (
            f"bench-search-{bench_start.strftime('%Y%m%dT%H%M%SZ')}.json"
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        if smoke:
            print(f"=== smoke search (1 corrida, umbral generoso) — {verdict} ===")
            print(
                f"client: {client[0]} ms < {SMOKE_BUDGET_MS} ms "
                "(sin percentil: el p95 es medición local, nunca CI)"
            )
        else:
            print(f"=== bench search criterio 3 — {verdict} ===")
            print(f"p95 client (nearest-rank, n=20, 19º valor): {p95_client} ms < {BUDGET_MS} ms")
            print(f"p95 server took_ms (punto de medición de la spec): {p95_took} ms")
            print(
                "etapas (p95 / presupuesto): "
                + " · ".join(
                    f"{name} {block['p95_ms']}/{block['budget_ms']} ms"
                    + ("" if block["pass"] else " ❌")
                    for name, block in stages_block.items()
                )
            )
            print(f"20 samples client (ms): {[round(value) for value in client]}")
            print(f"20 samples ipc (ms): {result['samples_ipc_ms']}")
            print(
                f"chunks indexados: {result['chunks_indexed']} · "
                f"results_n min: {result['results_n_min']}"
            )
        print(
            f"índice inicial: {index_record.get('elapsed_ms')} ms "
            f"(scanned={index_record.get('scanned')}, indexed={index_record.get('indexed')}, "
            f"skipped={index_record.get('skipped')})"
        )
        print(f"swap free: {done.get('swap_free_kb_start')} → {done.get('swap_free_kb_end')} kB")
        print(f"reporte JSON: {out_path}")
        return 0 if verdict == "PASS" else 1
    finally:
        if keep_vault:
            print(f"vault temporal conservado en: {vault}")
        else:
            shutil.rmtree(vault, ignore_errors=True)


def main() -> int:
    """CLI: `--driver` corre la medición en el subproceso; default orquesta y reporta."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--driver", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--keep", action="store_true", help="conservar el vault temporal")
    parser.add_argument("--out", type=Path, default=None, help="ruta del JSON de resultado")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="gate de CI: 1 búsqueda con umbral generoso (5000 ms); NO calcula p95 ni etapas",
    )
    args = parser.parse_args()
    if args.driver is not None:
        _driver(args.driver, args.smoke)
        return 0
    return _parent(args.keep, args.out, args.smoke)


if __name__ == "__main__":
    raise SystemExit(main())
