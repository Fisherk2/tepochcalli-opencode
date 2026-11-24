"""Bench Δ indexación <30 s (métrica de fase M1, T10) — 20 corridas, nearest-rank p95.

Fuente de verdad del protocolo: **docs/TRD.md §6 criterio 2** — «Corridas ×20:
tocar/crear 1-50 archivos md en `00-resources/`, luego `index_refresh()`;
registrar `elapsed_ms`»; pass = **p95 < 30 000 ms**; «PDFs grandes excluidos y
reportados aparte».

Qué mide y qué no
-----------------
* Mide el Δ **caliente** de un corpus de **50** ficheros pequeños md/txt bajo
  `00-resources/` de un **vault temporal** (`/tmp/opencode/...`, btrfs/NVMe):
  la indexación inicial (fría, incluye la carga del modelo) se ejecuta y se
  reporta, pero **queda FUERA de las 20 muestras del presupuesto** — el
  presupuesto M1 es el Δ de refresco, no el arranque en frío.
* **PDFs excluidos del presupuesto y reportados aparte (hand-off M5):** este
  bench NO ingiere PDFs ni carga Docling. El coste de PDFs se cita de la
  medición de T7 (no estimado aquí): PDF de 30 páginas = **49-51 s en caliente**
  (≈1,6-1,7 s/página, RSS 2048-2189 MiB); carga en frío del modelo Docling =
  **29-37 s**. Nunca mezclar esa cifra con el p95 md/txt de este bench.
* Punto de medición: `RefreshReport.elapsed_ms` de `refresh_blocking()`
  (spec-mcp-server §Tool `index_refresh`) — `time.monotonic()` dentro del
  entrypoint, candado de refresh + update incluidos (spec-mcp-server §latencia).
  Se cruza con un reloj de pared externo (`wall_ms`) como sanity check.

Definición del percentil (nearest-rank, declarada a propósito)
--------------------------------------------------------------
p95 por nearest-rank: `sorted_samples[ceil(0.95 * n) - 1]`. Con **n = 20**,
`ceil(19) = 19` ⇒ el p95 es el **valor ordenado nº 19** (el segundo mayor de
20). Consecuencias para los outliers, aprendidas con el dolor en n=10 (donde
p95 colapsaba al máximo): con n=20 **un único pico aislado NO determina el
p95** — el máximo puede ser cualquier cosa y el p95 sigue siendo el 19º; PERO
las DOS corridas más lentas pesan (la 19ª entra entera), así que un p95 alto
significa siempre «al menos dos corridas lentas», no un suspiro de un solo
run. Se reportan los 20 samples crudos para que el lector pueda juzgarlos.

Reproducibilidad (todos los knobs, fijos por defecto)
-----------------------------------------------------
* Corpus determinista: vocabulario fijo + `random.Random(SEED)`, tamaños
  1 500-4 000 bytes, mix ES/EN, md/txt alternos.
* Repartición de modificaciones: corrida `i` (0-idx) reescribe
  `1 + (i * 49) // 19` ficheros (los primeros del orden canónico): rampa
  lineal 1→50, determinista.
* Contenido modificado: párrafo de versión con el índice de corrida ⇒ hash de
  contenido nuevo ⇒ re-parse + re-embed real (semántica Δ de
  spec-rag-engine §Semántica incremental).
* Modelo: `paraphrase-multilingual-MiniLM-L12-v2` vía defaults de
  `tepochcalli_flow.config` (sin `tepochcalli.toml` ⇒ defaults), device cpu,
  cache de modelo SYMLINK al cache que resuelve `model_cache` (`HF_HOME`
  externo > spike T1 si existe > `~/.cache/huggingface`; patrón T6/T9:
  HF_HOME al symlink dentro del vault temporal; el repo jamás — T11).
* Proceso: UN subproceso para las 21 pasadas (environment global de cocoindex,
  patrón T8); pasadas sucesivas EN EL MISMO proceso y vault funcionan (sonda T8).

Garantías de idempotencia (nunca ensucia el repo)
--------------------------------------------------
* Vault bajo `/tmp/opencode/tepochcalli-t1-spike/bench/` (tmp-dir temporal,
  borrado al final salvo `--keep`); `tests/fixtures/` intacto.
* `obsidian-workspace/.tepochcalli/{db,models}` (payload) NO se crea: el padre
  lo verifica al terminar y aborta si existieran.

Uso (host de referencia de fase 1; ver desviación del VM limpio TRD en el
reporte):
    cd obsidian-workspace/.tepochcalli
    UV_PROJECT_ENVIRONMENT=venv uv run python ../../tests/benchmarks/bench_delta.py
    UV_PROJECT_ENVIRONMENT=venv uv run python ../../tests/benchmarks/bench_delta.py --smoke

Modo smoke (`--smoke`) — el ÚNICO gate de Δ que corre en CI
----------------------------------------------------------
`--smoke` ejecuta UNA sola corrida de Δ (reescribe 10 de los 50 ficheros ⇒
re-parse + re-embed reales, no triviales) con umbral generoso de 60 000 ms y
NO calcula percentil alguno: el p95 M1 de arriba es una medición LOCAL
documentada (TRD §6) y jamás corre en CI (tasks/todo.md → T11 AC: «smoke Δ
de 1 corrida con umbral generoso; el p95 no corre en CI»). Sin `--smoke`,
el comportamiento por defecto es EXACTAMENTE el de T10 — 20 corridas, p95
nearest-rank < 30 000 ms — así los números publicados siguen reproducibles.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from model_cache import link_model_cache, offline_env, resolve_model_cache  # noqa: E402

SEED = 20261022
"""Semilla del corpus: con este entero el corpus y los cambios son idénticos."""

N_FILES = 50
"""Tamaño del corpus md/txt (TRD §6: «1-50 archivos» ⇒ corpus de 50)."""

N_RUNS = 20
"""Corridas del presupuesto (TRD §6: «Corridas ×20»)."""

BUDGET_MS = 30_000
"""Gate M1: p95 (nearest-rank, n=20) < 30 000 ms."""

SMOKE_RUNS = 1
"""Corridas del modo `--smoke` (gate de CI): UN solo Δ, sin percentil."""

SMOKE_MODIFIED_FILES = 10
"""Ficheros que reescribe la corrida smoke (de 50): un Δ real, no trivial."""

SMOKE_BUDGET_MS = 10_000
"""Umbral del smoke, delimitado a un margen ~8x sobre la medición local (1261 ms
por pasada Δ de fyi: margen razonable en el runner CI compartido): caza
regresiones de un orden de magnitud sin dejar pasar el gate con 60 s de
holgura, que ya no moriría regresiones. El gate M1 real (p95 < 30 000 ms)
sigue siendo una medición LOCAL documentada (TRD §6) y NO corre en CI (T11)."""

BENCH_DIR = Path("/tmp/opencode/tepochcalli-t1-spike/bench")
"""Donde viven los vaults temporales del bench (btrfs/NVMe, fuera del repo).

Directorio TEMPORAL — se crea con `mkdir -p` en cualquier host; no es un
requisito de cache (el cache de modelo lo resuelve `model_cache`, T11).
"""

REPO_ROOT = Path(__file__).resolve().parents[2]

PAYLOAD_DB = REPO_ROOT / "obsidian-workspace" / ".tepochcalli" / "db"
PAYLOAD_MODELS = REPO_ROOT / "obsidian-workspace" / ".tepochcalli" / "models"

WORDS = (
    "notas citas offsets índice lancedb cocoindex chunking vacío daemon "
    "puerto stdio mcp busqueda semantica embeddings modelo local cpu cache "
    "vault obsidian recursos revisión salida agente flujo delta refresh "
    "incremental fences heading párrafo documento texto fuente confianza "
    "prompt inyección seguridad bash script workflow phase checkpoint "
    "medida percentil latencia presupuesto gateway parser marcado listas "
    "tablas unicode nfd normalización identidad fila tabla índice ann fts "
).split()


def _corpus_text(i: int, rng: random.Random) -> str:
    """Cuerpo determinista de ~1,5-4 KB para el fichero nº `i` (ES/EN mix)."""
    target = rng.randint(1_500, 4_000)
    title = f"Nota {i:02d}"
    lines = [f"# {title}", ""]
    size = len(title) + 4
    para = 0
    while size < target:
        para += 1
        if para % 4 == 0:
            lines.append(f"## Sección {para // 4}")
            lines.append("")
        words = [rng.choice(WORDS) for _ in range(rng.randint(40, 90))]
        # Frase capitalizada + punto final: texto plausible para el parser.
        body = " ".join(words)
        body = body[0].upper() + body[1:] + "."
        lines.append(body)
        lines.append("")
        size += len(body) + 4 + 40
    return "\n".join(lines)


def _driver(vault: Path, smoke: bool) -> None:
    """Corre en el subproceso: indexación inicial + los Δ, emite JSON por línea.

    `smoke=True` hace UNA sola corrida reescribiendo `SMOKE_MODIFIED_FILES`
    ficheros; el default es la rampa de 20 corridas de T10, idéntica byte a
    byte (los números publicados siguen reproducibles).
    """
    from tepochcalli_flow import app as flow_app

    runs = SMOKE_RUNS if smoke else N_RUNS
    rng = random.Random(SEED)
    resources = vault / "00-resources"
    resources.mkdir(parents=True, exist_ok=True)
    names: list[str] = []
    for i in range(N_FILES):
        name = f"nota-{i:02d}." + ("md" if i % 2 == 0 else "txt")
        (resources / name).write_text(_corpus_text(i, rng), encoding="utf-8")
        names.append(name)

    # Sampler de swap + loadavg: si el host entra en presión de swap durante el
    # bench, el p95 sería inflado y hay que poder DEMOSTRARLO (hallazgo T10).
    swap_free: list[int] = []
    stop = threading.Event()

    def _sample() -> None:
        while not stop.is_set():
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("SwapFree:"):
                    swap_free.append(int(line.split()[1]))
                    break
            time.sleep(0.25)

    sampler = threading.Thread(target=_sample, daemon=True)
    sampler.start()

    def _emit(obj: dict[str, Any]) -> None:
        print(json.dumps(obj), flush=True)

    def _refresh(tag: str, modified: int) -> None:
        wall_start = time.monotonic()
        report = flow_app.refresh_blocking()
        wall_ms = int((time.monotonic() - wall_start) * 1000)
        _emit(
            {
                "kind": "refresh",
                "tag": tag,
                "modified_files": modified,
                "report": {
                    "scanned": report.scanned,
                    "indexed": report.indexed,
                    "skipped": report.skipped,
                    "elapsed_ms": report.elapsed_ms,
                    "locked": report.locked,
                },
                "wall_ms": wall_ms,
                "loadavg": list(os.getloadavg()),
            }
        )
        if report.locked:
            raise SystemExit(f"[{tag}] refresh inesperadamente locked=True")
        if report.scanned != N_FILES:
            raise SystemExit(f"[{tag}] scanned={report.scanned} != {N_FILES}")
        if tag != "initial" and report.indexed != modified:
            raise SystemExit(f"[{tag}] indexed={report.indexed} != ficheros modificados={modified}")

    _emit({"kind": "start", "python": platform.python_version(), "pid": os.getpid()})
    _refresh("initial", N_FILES)
    for i in range(runs):
        if smoke:
            k = SMOKE_MODIFIED_FILES  # Δ real sobre 10 de los 50 ficheros
        else:
            k = 1 + (i * (N_FILES - 1)) // (N_RUNS - 1)  # rampa lineal determinista 1→50
        for j in range(k):  # los primeros k del orden canónico
            path = resources / names[j]
            base = path.read_text(encoding="utf-8")
            path.write_text(
                base + f"\n\n## Actualización (corrida {i})\n\n"
                f"Reescritura determinista de la corrida {i} sobre el fichero {j} "
                "para forzar re-parse y re-embed de SU contenido.\n",
                encoding="utf-8",
            )
        _refresh(f"run-{i:02d}", k)
    stop.set()
    sampler.join(timeout=2)
    _emit(
        {
            "kind": "done",
            "swap_free_kb_samples": len(swap_free),
            "swap_free_kb_min": min(swap_free) if swap_free else None,
        }
    )


def _nearest_rank_p(samples_ms: list[int], p: float) -> int:
    """Percentil nearest-rank: `sorted[ceil(p*n) - 1]` (1-idx ⇒ nº ceil(p*n))."""
    ordered = sorted(samples_ms)
    return ordered[math.ceil(p * len(ordered)) - 1]


def _host_block(vault: Path) -> dict[str, Any]:
    """Descripción del host y del fs del vault: todo observado, nada estimado."""
    cpu_model = "?"
    for line in Path("/proc/cpuinfo").read_text().splitlines():
        if line.startswith("model name"):
            cpu_model = line.split(":", 1)[1].strip()
            break
    meminfo: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, _, rest = line.partition(":")
        if key in ("MemTotal", "SwapTotal", "SwapFree"):
            meminfo[key] = int(rest.split()[0])
    df = subprocess.run(
        ["df", "-T", str(vault)], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    return {
        "cpu_model": cpu_model,
        "cpu_count_logical": os.cpu_count(),
        "mem_total_kb": meminfo.get("MemTotal"),
        "swap_total_kb": meminfo.get("SwapTotal"),
        "swap_free_kb_at_start": meminfo.get("SwapFree"),
        "vault_filesystem": df[1].split()[1] if len(df) > 1 else "?",
        "vault_device": df[1].split()[0] if len(df) > 1 else "?",
        "platform": platform.platform(),
    }


def _parent(keep_vault: bool, out_path: Path | None, smoke: bool) -> int:
    runs = SMOKE_RUNS if smoke else N_RUNS
    budget_ms = SMOKE_BUDGET_MS if smoke else BUDGET_MS
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    vault = Path(tempfile.mkdtemp(prefix="bench-delta-", dir=BENCH_DIR))
    try:
        cache = resolve_model_cache()
        models_link = link_model_cache(vault, cache)

        host = _host_block(vault)
        env = {
            **os.environ,
            "TEPOCHCALLI_VAULT_ROOT": str(vault),
            "HF_HOME": str(models_link),
            "SENTENCE_TRANSFORMERS_HOME": str(models_link),
            # Sin red solo si el cache resuelto ya tiene el modelo (T11): en
            # frío (runner limpio) el driver descarga UNA vez al cache de CI.
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

        refreshes: list[dict[str, Any]] = []
        done: dict[str, Any] = {}
        for line in proc.stdout.splitlines():
            stripped = line.strip()
            if not stripped.startswith("{"):
                continue
            record = json.loads(stripped)
            if record["kind"] == "refresh":
                refreshes.append(record)
            elif record["kind"] == "done":
                done = record
        if len(refreshes) != runs + 1:
            raise SystemExit(f"esperaba {runs + 1} refreshes, llegaron {len(refreshes)}")

        initial = refreshes[0]
        cycles = refreshes[1:]
        samples = [c["report"]["elapsed_ms"] for c in cycles]
        wall_samples = [c["wall_ms"] for c in cycles]
        if smoke:
            # Sin percentil en modo smoke: el p95 es medición local (TRD §6).
            verdict = "PASS" if samples[0] < budget_ms else "FAIL"
            p95: int | None = None
        else:
            p95 = _nearest_rank_p(samples, 0.95)
            verdict = "PASS" if p95 < budget_ms else "FAIL"

        mem_after = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, _, rest = line.partition(":")
            if key == "SwapFree":
                mem_after["swap_free_kb_at_end"] = int(rest.split()[0])

        # Verificación de limpieza del payload (garantía de idempotencia T10).
        payload_created = [str(p) for p in (PAYLOAD_DB, PAYLOAD_MODELS) if p.exists()]
        if payload_created:
            raise SystemExit(f"el payload fue contaminado: {payload_created}")

        result = {
            "metric": (
                f"smoke Δ CI: 1 corrida vs umbral generoso {budget_ms} ms (sin percentil)"
                if smoke
                else "M1 Δ indexación p95 (nearest-rank, n=20) vs 30000 ms"
            ),
            "verdict": verdict,
            "budget_ms": budget_ms,
            # `p95_ms`/`percentile_definition` solo en el modo T10: el p95
            # jamás se calcula ni se reporta en la corrida de CI (T11 AC).
            **(
                {
                    "p95_ms": p95,
                    "percentile_definition": (
                        "nearest-rank: sorted[ceil(0.95*n)-1]; con n=20 es el 19º valor "
                        "ordenado (segundo mayor) — un outlier aislado no lo determina"
                    ),
                }
                if not smoke
                else {}
            ),
            "stats_ms": {
                "min": min(samples),
                "median": sorted(samples)[len(samples) // 2],
                "mean": sum(samples) // len(samples),
                "max": max(samples),
            },
            "samples_ms": samples,
            "wall_ms_samples": wall_samples,
            "samples_detail": [
                {
                    "run": c["tag"],
                    "modified_files": c["modified_files"],
                    "elapsed_ms": c["report"]["elapsed_ms"],
                    "indexed": c["report"]["indexed"],
                }
                for c in cycles
            ],
            "initial_cold_ms": initial["report"]["elapsed_ms"],
            "initial_report": initial["report"],
            "host": host,
            "swap_during_run_kb": {
                "min_free": done.get("swap_free_kb_min"),
                "samples": done.get("swap_free_kb_samples"),
                **mem_after,
            },
            "bench_started_utc": bench_start.isoformat(),
            "seed": SEED,
            "n_files": N_FILES,
            "n_runs": runs,
            "pdf_policy": (
                "PDFs EXCLUIDOS del presupuesto Δ y del bench mismo (sin Docling). "
                "Coste aparte según medición T7 (no re-meditido aquí): PDF 30 págs "
                "= 49-51 s en caliente (≈1,6-1,7 s/pág, RSS 2048-2189 MiB); carga "
                "en frío Docling = 29-37 s."
            ),
            "deviation_from_trd_reference_host": (
                "TRD §6 fija VM limpia 8GB SSD como referencia; esta medición es "
                "sobre el host de desarrollo fase 1 (ver host block) — declarado "
                "como desviación, no como VM de referencia."
            ),
        }
        out_path = out_path or BENCH_DIR / (
            f"bench-run-{bench_start.strftime('%Y%m%dT%H%M%SZ')}.json"
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        if smoke:
            print(f"=== smoke Δ (1 corrida, umbral generoso) — {verdict} ===")
            print(
                f"Δ: {samples[0]} ms < {budget_ms} ms "
                "(sin percentil: el p95 M1 es medición local, nunca CI)"
            )
        else:
            print(f"=== bench Δ M1 — {verdict} ===")
            print(f"p95 (nearest-rank, n=20, 19º valor): {p95} ms < {BUDGET_MS} ms")
        print(
            f"min/median/mean/max: {min(samples)}/"
            f"{sorted(samples)[len(samples) // 2]}/{result['stats_ms']['mean']}/{max(samples)} ms"
        )
        if not smoke:
            print(f"20 samples (ms): {samples}")
        print(
            f"initial cold index: {initial['report']['elapsed_ms']} ms "
            f"(scanned={initial['report']['scanned']}, indexed={initial['report']['indexed']})"
        )
        print(
            f"swap min free durante run: {done.get('swap_free_kb_min')} KB "
            f"(total {host['swap_total_kb']} KB; start {host['swap_free_kb_at_start']} KB, "
            f"end {result['swap_during_run_kb'].get('swap_free_kb_at_end')} KB)"
        )
        print(f"reporte JSON: {out_path}")
        return 0 if verdict == "PASS" else 1
    finally:
        if keep_vault:
            print(f"vault temporal conservado en: {vault}")
        else:
            shutil.rmtree(vault, ignore_errors=True)


def main() -> int:
    """CLI: `--driver` corre las pasadas en el subproceso; default orquesta y reporta."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--driver", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--keep", action="store_true", help="conservar el vault temporal")
    parser.add_argument("--out", type=Path, default=None, help="ruta del JSON de resultado")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="gate de CI: 1 corrida de Δ con umbral generoso (60 s); NO calcula p95",
    )
    args = parser.parse_args()
    if args.driver is not None:
        _driver(args.driver, args.smoke)
        return 0
    return _parent(args.keep, args.out, args.smoke)


if __name__ == "__main__":
    raise SystemExit(main())
