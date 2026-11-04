"""Bench de escala de criterio 6 (W4/P-02): 10 000 md + 1 000 PDFs sintéticos.

Qué mide
--------
* El mismo protocolo de `bench_delta.py` (métrica de fase M1, criterio 2)
  LLEVADO A ESCALA: corpus determinista de **10 000** notas md pequeñas y
  **1 000** PDFs reales mínimos (1 página, xref computado — no dummies
  vacíos; los Pants spec-rag-engine §Escala admite), en un vault temporal
  bajo `--dir` (default: `/tmp/opencode`, btrfs/NVMe; segunda pasada con
  `--dir` sobre fuseblk/NTFS si el host lo tiene accesible).
* **20 corridas Δ** (mismo nearest-rank n=20 que M1) reescribiendo **10** md
  por corrida con rotación determinista. Desviación declarada de la rampa
  de `bench_delta.py` (1→50): a escala, la rampa reescribiría hasta 10 000
  ficheros en la corrida 19 — eso es la métrica de criterio 2, no de
  criterio 6; aquí el presupuesto carga el **walk de 11 000 entradas**,
  que es lo que el eje perf extrapoló a NTFS frío.
* **Walk-only aparte:** UNA medición de `source.scan_items` (sin conector
  Δ, sin embed) después de la inicial — aísla el coste del walk de 11k
  entradas sobre el FS real; es la cifra que la extrapolación del review
  intentaba estimar a mano.

Qué NO es
---------
* NO corre en CI ni en `just ci` (como `bench_delta` completado): es
  herramienta de medición one-shot. Runtime dominado por la indexación
  inicial fría (~10 min en el host de referencia) — mucho más de 60 s, así
  que NUNCA cae en el gate de pytest (no es un `test_*`); se corre a mano:

      cd obsidian-workspace/.tepochcalli
      UV_PROJECT_ENVIRONMENT=venv uv run python \
          ../../tests/benchmarks/bench_delta_scale.py            # btrfs
      UV_PROJECT_ENVIRONMENT=venv uv run python \
          ../../tests/benchmarks/bench_delta_scale.py \
          --dir /mnt/HDDFish/tepochcalli-bench-tmp               # fuseblk/NTFS

Garantías de idempotencia: igual que `bench_delta.py` — vault temporal
borrado al final (salvo `--keep`), `obsidian-workspace/.tepochcalli/{db,models}`
del payload NUNCA tocado (verificado al terminar).
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
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from model_cache import link_model_cache, offline_env, resolve_model_cache  # noqa: E402

SEED = 20261103
N_MD_FILES = 10_000
N_PDF_FILES = 1_000
N_RUNS = 20
MODIFIED_PER_RUN = 10
BUDGET_MS = 30_000
DRIVER_TIMEOUT_S = 7200

DEFAULT_DIR = Path("/tmp/opencode/tepochcalli-t1-spike")

REPO_ROOT = Path(__file__).resolve().parents[2]
PAYLOAD_DB = REPO_ROOT / "obsidian-workspace" / ".tepochcalli" / "db"
PAYLOAD_MODELS = REPO_ROOT / "obsidian-workspace" / ".tepochcalli" / "models"

WORDS = (
    "notas citas offsets índice lancedb cocoindex chunking vault obsidian "
    "recursos agente flujo delta refresh incremental heading párrafo "
    "documento texto fuente confianza percentil latencia presupuesto parser "
    "tablas unicode identidad fila tabla índice ann fts benchmark escala "
).split()

PDF_WORDS = (
    "brisa orfandad oficina temblor rincon laurel noria aldeas comercio "
    "tablas escala nota credito inviernos nieblas arboles cortijo "
).split()
"""Vocab ASCII del cuerpo del PDF: Helvetica + `Tj` sin escaping ni encoding raro."""


def _corpus_text(i: int, rng: random.Random) -> str:
    """Cuerpo determinista y PEQUEÑO (~0,5-1,2 KB ⇒ 1 chunk con el split 1536/192)."""
    target = rng.randint(500, 1_100)
    title = f"Nota {i:05d}"
    lines = [f"# {title}", ""]
    size = len(title) + 4
    while size < target:
        body = " ".join(rng.choice(WORDS) for _ in range(rng.randint(30, 60)))
        body = body[0].upper() + body[1:] + "."
        lines.append(body)
        lines.append("")
        size += len(body) + 4
    return "\n".join(lines)


def _minimal_pdf(title: str, body_lines: list[str]) -> bytes:
    """PDF 1 página VÁLIDO (xref correcto, offsets computados) — no dummy vacío.

    Sin dependencias nuevas: los objetos mínimos de PDF-1.4 que un extractor
    real (pdfminer vía markitdown) parsea con texto extraíble en `contents`.
    El vocabulario usa solo ASCII sin `(`/`)` ⇒ no hay escaping en `Tj`.
    """
    content = b"BT\n/F1 12 Tf\n72 720 Td\n"
    content += b"".join(f"({line}) Tj\n0 -14 Td\n".encode("ascii") for line in body_lines)
    content += b"ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref_pos = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref_pos,
    )
    return bytes(out)


def _seed_corpus(vault: Path) -> tuple[list[Path], list[Path]]:
    """Escribe 10k md (10 subdirs × 1k) + 1k PDFs (1 subdir); deterministic."""
    rng = random.Random(SEED)
    resources = vault / "00-Resources"
    md_paths: list[Path] = []
    for block in range(10):
        sub = resources / f"notas-{block:02d}"
        sub.mkdir(parents=True, exist_ok=True)
        for j in range(1_000):
            i = block * 1_000 + j
            path = sub / f"nota-{i:05d}.md"
            path.write_text(_corpus_text(i, rng), encoding="utf-8")
            md_paths.append(path)
    pdfs = resources / "pdfs"
    pdfs.mkdir(parents=True, exist_ok=True)
    pdf_paths: list[Path] = []
    for i in range(1_000):
        rng_pdf = random.Random(SEED + i)
        title = f"Informe PDF {i:05d}"
        lines = [
            title,
            *[rng_pdf.choice(PDF_WORDS).capitalize() for _ in range(5)],
        ]
        path = pdfs / f"informe-{i:05d}.pdf"
        path.write_bytes(_minimal_pdf(title, lines))
        pdf_paths.append(path)
    return md_paths, pdf_paths


def _driver(vault: Path) -> None:
    """Corre en el subproceso: inicial + walk-only + 20 Δ, emite JSON por línea."""
    import asyncio

    from tepochcalli_flow import app as flow_app
    from tepochcalli_flow import source

    md_paths, pdf_paths = _seed_corpus(vault)
    assert len(md_paths) == N_MD_FILES and len(pdf_paths) == N_PDF_FILES

    def _emit(obj: dict[str, Any]) -> None:
        print(json.dumps(obj), flush=True)

    _emit({"kind": "start", "python": platform.python_version(), "pid": os.getpid()})

    def _refresh(tag: str, modified: int) -> dict[str, Any]:
        report = flow_app.refresh_blocking()
        assert report.scanned == N_MD_FILES + N_PDF_FILES, report
        _emit(
            {
                "kind": "refresh",
                "tag": tag,
                "modified": modified,
                "elapsed_ms": report.elapsed_ms,
                "indexed": report.indexed,
            }
        )
        if tag != "initial" and report.indexed != modified:
            raise SystemExit(f"[{tag}] indexed={report.indexed} != {modified}")
        return {"elapsed_ms": report.elapsed_ms}

    initial = _refresh("initial", N_MD_FILES + N_PDF_FILES)

    # Walk-only: UN sample de scan_items puro (sin embed, sin Δ) — la cifra
    # que la extrapolación de NTFS intentaba estimar a mano (hallazgo W4).
    # scan_items no toca el env de cocoindex: loop propio con asyncio.run.
    walk_start = time.monotonic()
    items, _walked_scanned = asyncio.run(source.scan_items(vault))
    walk_ms = int((time.monotonic() - walk_start) * 1000)
    _emit({"kind": "walk-only", "walk_ms": walk_ms, "items": len(items)})

    for run in range(N_RUNS):
        for k in range(MODIFIED_PER_RUN):
            path = md_paths[(run * 97 + k * 13) % N_MD_FILES]
            path.write_text(
                _corpus_text(k, random.Random(SEED + run * 1000 + k))
                + f"\n\nCorrida {run}: reescritura determinista del fichero {path.name}.\n",
                encoding="utf-8",
            )
        _refresh(f"run-{run:02d}", MODIFIED_PER_RUN)
    _emit({"kind": "done", "initial_ms": initial["elapsed_ms"]})


def _nearest_rank_p(samples_ms: list[int], p: float) -> int:
    ordered = sorted(samples_ms)
    return ordered[math.ceil(p * len(ordered)) - 1]


def _host_block(vault: Path) -> dict[str, Any]:
    df = subprocess.run(
        ["df", "-T", str(vault)], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    cpu_model = next(
        (
            line.split(":", 1)[1].strip()
            for line in Path("/proc/cpuinfo").read_text().splitlines()
            if line.startswith("model name")
        ),
        "?",
    )
    return {
        "cpu_model": cpu_model,
        "vault_filesystem": df[1].split()[1] if len(df) > 1 else "?",
        "vault_device": df[1].split()[0] if len(df) > 1 else "?",
        "platform": platform.platform(),
    }


def _parent(base_dir: Path, keep_vault: bool) -> int:
    base_dir.mkdir(parents=True, exist_ok=True)
    vault = Path(tempfile.mkdtemp(prefix="bench-scale-", dir=base_dir))
    try:
        cache = resolve_model_cache()
        models_link = link_model_cache(vault, cache)
        host = _host_block(vault)
        env = {
            **os.environ,
            "TEPOCHCALLI_VAULT_ROOT": str(vault),
            "HF_HOME": str(models_link),
            "SENTENCE_TRANSFORMERS_HOME": str(models_link),
            **offline_env(cache),
        }
        env.pop("COCOINDEX_DB", None)
        cmd = [sys.executable, str(Path(__file__).resolve()), "--driver", str(vault)]
        proc = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=DRIVER_TIMEOUT_S,
            check=False,
        )
        if proc.returncode != 0:
            print(proc.stderr[-4000:], file=sys.stderr)
            raise SystemExit(f"el driver del bench-scale falló (rc={proc.returncode})")

        refreshes: list[dict[str, Any]] = []
        walk_only: dict[str, Any] = {}
        for line in proc.stdout.splitlines():
            record: dict[str, Any]
            if not line.strip().startswith("{"):
                continue
            record = json.loads(line)
            if record["kind"] == "refresh":
                refreshes.append(record)
            elif record["kind"] == "walk-only":
                walk_only = record
        cycles = refreshes[1:]
        samples = [c["elapsed_ms"] for c in cycles]
        p95 = _nearest_rank_p(samples, 0.95)
        verdict = "PASS" if p95 < BUDGET_MS else "FAIL"

        payload_created = [str(p) for p in (PAYLOAD_DB, PAYLOAD_MODELS) if p.exists()]
        if payload_created:
            raise SystemExit(f"el payload fue contaminado: {payload_created}")

        result = {
            "metric": (
                f"criterio 6 (escala): Δ p95 (nearest-rank, n={N_RUNS}) "
                f"con {N_MD_FILES} md + {N_PDF_FILES} pdf vs {BUDGET_MS} ms"
            ),
            "verdict": verdict,
            "budget_ms": BUDGET_MS,
            "percentile_definition": "nearest-rank: sorted[ceil(0.95*n)-1] (como M1)",
            "stats_ms": {
                "min": min(samples),
                "median": sorted(samples)[len(samples) // 2],
                "mean": sum(samples) // len(samples),
                "max": max(samples),
            },
            "samples_ms": samples,
            "samples_detail": [
                {"run": c["tag"], "modified": c["modified"], "elapsed_ms": c["elapsed_ms"]}
                for c in cycles
            ],
            "initial_ms": refreshes[0]["elapsed_ms"],
            "walk_only_ms": walk_only.get("walk_ms"),
            "walk_only_items": walk_only.get("items"),
            "host": host,
            "seed": SEED,
            "n_md_files": N_MD_FILES,
            "n_pdf_files": N_PDF_FILES,
            "n_runs": N_RUNS,
            "modified_per_run": MODIFIED_PER_RUN,
            "deviations_from_m1_protocol": [
                "sin rampa: 10 ficheros por corrida con rotación determinista",
                "corpus md pequeño (~0.5-1.2 KB) y PDF 1 página real mínimo",
                "sin sampler de swap (medición one-shot local de eje perf, no gate)",
                "PDF generado in-process, sin dependencias nuevas (no dummy vacío)",
            ],
            "bench_started_utc": datetime.now(UTC).isoformat(),
        }
        out = base_dir / (
            f"bench-scale-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-"
            f"{host['vault_filesystem']}.json"
        )
        out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"=== bench-scale ({host['vault_filesystem']}) — {verdict} ===")
        print(f"p95 (nearest-rank, n={N_RUNS}): {p95} ms vs {BUDGET_MS} ms")
        print(f"min/median/mean/max: {result['stats_ms']} ms")
        print(f"walk-only (scan_items, 11k entradas): {walk_only.get('walk_ms')} ms")
        print(f"initial cold: {refreshes[0]['elapsed_ms']} ms")
        print(f"reporte JSON: {out}")
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
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR, help="base dir del vault temporal")
    parser.add_argument("--keep", action="store_true", help="conservar el vault temporal")
    args = parser.parse_args()
    if args.driver is not None:
        _driver(args.driver)
        return 0
    return _parent(args.dir, args.keep)


if __name__ == "__main__":
    raise SystemExit(main())
