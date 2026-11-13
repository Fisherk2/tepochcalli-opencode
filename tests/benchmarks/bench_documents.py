"""Bench de extracción e indexación de documentos binarios (Phase 6 T2, cierra TD-2).

Mide en **procesos hijos limpios** el coste real de markitdown (D51: documentos
binarios van APARTE del presupuesto Δ de 30 s de texto) sobre:

* los 5 libros reales de `tests/fixtures/pdf/` (`16/335/444/952/1313-pages.pdf`),
* un PDF generado de 30 páginas (TD-2: la cifra que faltaba; `--pages 30` del
  generador, on-demand en `/tmp/opencode`, nunca fixture de CI),
* una muestra de los PDF de 1 página del corpus de escala de T1 (`--corpus-sample`).

Protocolo (docs/TRD.md §6.1; el método se publica con la cifra, D-P6-7):
* `extract_ms` = reloj **monotónico** alrededor de `MarkItDown()` +
  `MarkItDown().convert(path)` dentro del hijo. Se reportan las dos partes
  (`construct_ms`, `convert_ms`) y la suma, para poder descontar el arranque.
* `rss_peak_mib` = **`VmHWM`** leído de `/proc/self/status` por el propio hijo
  antes de salir: es el pico real del proceso que extrae, no el del padre; no
  es un muestreo que pueda perderse el máximo.
* `index_ms` = `RefreshReport.elapsed_ms` de `flow_app.refresh_blocking()` en un
  vault temporal (parse + embed + upsert; la carga del modelo se paga en un
  warm-up FUERA de las muestras y se reporta como `cold_ms`).
* Percentiles **nearest-rank**: `sorted[ceil(p*n)-1]`, n declarado por fila.
  Con n=3 el p95 es el máximo (el 3º valor ordenado) y el p50 la mediana.
* FS de referencia: btrfs/NVMe `/tmp/opencode` (D-P6-3). Los libros se COPIAN
  ahí antes de medir: leer de NTFS-3G inflaría el tiempo por el filesystem.

No corre en CI (no es `test_*`, coste en minutos-horas). **Un documento por
llamada, en primer plano** (AGENTS.md §Commands: nada en segundo plano); cada
corrida escribe su JSON:

    just python-bench-documents --doc-pages 30 --n 3 --json /tmp/opencode/t2-30p.json
    just python-bench-documents --pdf /tmp/opencode/phase6-docs/335-pages.pdf --n 3 \
        --json /tmp/opencode/t2-335.json
    just python-bench-documents --index /tmp/opencode/phase6-docs/335-pages.pdf --n 3 \
        --json /tmp/opencode/t2-index-335.json

`--matrix` sigue existiendo para una corrida completa observada, pero los 5
libros + 1 313 páginas son ~25 min: se trocea.

Idempotencia: todo lo que escribe vive bajo `--dir` (default
`/tmp/opencode/phase6-t2`) y se borra al terminar salvo `--keep`; el repo, el
payload y `tests/fixtures/` no se tocan (los libros se copian, no se mueven).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
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

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_PDF = REPO_ROOT / "tests" / "fixtures" / "pdf"
GEN_FIXTURE = FIXTURES_PDF / "gen_fixture_pdf.py"
PAYLOAD_FLOW = REPO_ROOT / "obsidian-workspace" / ".tepochcalli" / "flow"

DEFAULT_DIR = Path("/tmp/opencode/phase6-t2")
"""Base del bench: btrfs/NVMe, fuera del repo (D-P6-3)."""

DOCS_DIR = Path("/tmp/opencode/phase6-docs")
"""Copia de los libros en el FS de referencia (no se mide leyendo NTFS-3G)."""

DEFAULT_CORPUS_SAMPLE = Path("/tmp/opencode/phase6-corpus/00-resources/pdfs")
"""Corpus de 1 000 PDF de 1 página materializado por T1 (si existe)."""

GENERATED_PAGES = 30
"""Páginas del PDF generado: la cifra que TD-2 pedía (30 páginas)."""

DEFAULT_N = 3
"""n mínimo obligatorio en el PDF de 30 páginas; los libros declaran su n real."""

EXTRACT_TIMEOUT_S = 3600
"""Techo por muestra: el libro de 1 313 páginas ronda los 4-5 min."""


def _vm_hwm_kib() -> int:
    """Pico de RSS del PROPIO proceso (`VmHWM`, high-water mark del kernel)."""
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmHWM:"):
            return int(line.split()[1])
    return 0


def _driver_extract(pdf: Path) -> None:
    """Hijo limpio: un solo documento, markitdown en proceso, JSON por stdout."""
    from markitdown import MarkItDown

    t0 = time.monotonic()
    converter = MarkItDown()
    t1 = time.monotonic()
    markdown = converter.convert(str(pdf)).markdown
    t2 = time.monotonic()
    print(
        json.dumps(
            {
                "construct_ms": round((t1 - t0) * 1000, 1),
                "convert_ms": round((t2 - t1) * 1000, 1),
                "extract_ms": round((t2 - t0) * 1000, 1),
                "chars": len(markdown),
                "rss_peak_kib": _vm_hwm_kib(),
            }
        ),
        flush=True,
    )


def _driver_index(vault: Path, plan_path: Path) -> None:
    """Hijo: carga el modelo UNA vez y refresca el vault por cada entrada del plan.

    El padre prepara un plan `[{source, target}]`; aquí se copia cada fuente a su
    destino (con un comentario único ya inyectado por el padre) y se corre un
    `refresh_blocking()` — un JSON por refresh, `kind="refresh"`.
    """
    sys.path.insert(0, str(PAYLOAD_FLOW))
    from tepochcalli_flow import app as flow_app

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    for entry in plan:
        shutil.copyfile(entry["source"], entry["target"])
        started = time.monotonic()
        report = flow_app.refresh_blocking()
        wall_ms = round((time.monotonic() - started) * 1000, 1)
        print(
            json.dumps(
                {
                    "kind": "refresh",
                    "file": Path(entry["target"]).name,
                    "elapsed_ms": report.elapsed_ms,
                    "wall_ms": wall_ms,
                    "scanned": report.scanned,
                    "indexed": report.indexed,
                    "skipped": report.skipped,
                    "locked": report.locked,
                    "rss_peak_kib": _vm_hwm_kib(),
                }
            ),
            flush=True,
        )
    print(json.dumps({"kind": "done"}), flush=True)


def _pdf_pages(pdf: Path) -> int:
    """Páginas según `pdfinfo` (metadato real del fichero, no estimación)."""
    out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, check=True).stdout
    for line in out.splitlines():
        if line.startswith("Pages:"):
            return int(line.split()[1])
    raise RuntimeError(f"pdfinfo no reportó páginas para {pdf}")


def _nearest_rank_p(samples: list[float], p: float) -> float:
    """Percentil nearest-rank: `sorted[ceil(p*n) - 1]`."""
    ordered = sorted(samples)
    return ordered[math.ceil(p * len(ordered)) - 1]


def _run_child(
    args: list[str], env: dict[str, str] | None = None, timeout: int = EXTRACT_TIMEOUT_S
) -> dict[str, Any]:
    """Lanza el hijo y devuelve la última línea JSON de stdout (falla ruidosamente)."""
    return _run_child_records(args, env=env, timeout=timeout)[-1]


def _run_child_records(
    args: list[str], env: dict[str, str] | None = None, timeout: int = EXTRACT_TIMEOUT_S
) -> list[dict[str, Any]]:
    """Lanza el hijo y devuelve TODAS sus líneas JSON (un registro por refresh)."""
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        check=False,
    )
    if proc.returncode != 0:
        print(proc.stderr[-4000:], file=sys.stderr)
        raise SystemExit(f"hijo {args[0]} falló (rc={proc.returncode})")
    records = [
        json.loads(line) for line in proc.stdout.splitlines() if line.strip().startswith("{")
    ]
    if not records:
        raise SystemExit(f"hijo {args[0]} no emitió JSON")
    return records


def _measure_extract(pdf: Path, n: int) -> dict[str, Any]:
    """Mide n extracciones en hijos limpios y devuelve muestras y estadísticos."""
    samples = [_run_child(["--driver-extract", str(pdf)]) for _ in range(n)]
    extract = [s["extract_ms"] for s in samples]
    pages = _pdf_pages(pdf)
    chars = samples[0]["chars"]
    print(
        f"  {pdf.name}: {pages} págs, n={n}, p50={_nearest_rank_p(extract, 0.50):.0f} ms, "
        f"p95={_nearest_rank_p(extract, 0.95):.0f} ms",
        file=sys.stderr,
        flush=True,
    )
    return {
        "file": pdf.name,
        "pages": pages,
        "bytes": pdf.stat().st_size,
        "n": n,
        "extract_samples_ms": extract,
        "extract_p50_ms": _nearest_rank_p(extract, 0.50),
        "extract_p95_ms": _nearest_rank_p(extract, 0.95),
        "construct_ms_p50": _nearest_rank_p([s["construct_ms"] for s in samples], 0.50),
        "convert_ms_p50": _nearest_rank_p([s["convert_ms"] for s in samples], 0.50),
        "chars": chars,
        "chars_per_page": round(chars / pages, 1),
        "ms_per_page_p50": round(_nearest_rank_p(extract, 0.50) / pages, 2),
        "ms_per_page_p95": round(_nearest_rank_p(extract, 0.95) / pages, 2),
        "rss_peak_mib": round(max(s["rss_peak_kib"] for s in samples) / 1024, 1),
    }


def _host_block(path: Path) -> dict[str, Any]:
    """Host y FS observados (no estimados), como el resto de benches."""
    cpu_model = "?"
    for line in Path("/proc/cpuinfo").read_text().splitlines():
        if line.startswith("model name"):
            cpu_model = line.split(":", 1)[1].strip()
            break
    df = subprocess.run(["df", "-T", str(path)], capture_output=True, text=True, check=True)
    line = df.stdout.splitlines()[1].split()
    return {
        "cpu_model": cpu_model,
        "cpu_count_logical": os.cpu_count(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "fs": line[1],
        "device": line[0],
    }


def _prepare_docs(sources: list[Path]) -> list[Path]:
    """Copia los libros al FS de referencia; el original queda intacto."""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    copied = []
    for source in sources:
        target = DOCS_DIR / source.name
        if not target.exists():
            shutil.copyfile(source, target)
        copied.append(target)
    return copied


def _generate_pages(pages: int) -> Path:
    """Genera un PDF de `pages` páginas on-demand (mismo intérprete, sin dependencias)."""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    target = DOCS_DIR / f"generated-{pages}-pages.pdf"
    subprocess.run(
        [sys.executable, str(GEN_FIXTURE), str(target), "--pages", str(pages)],
        check=True,
        capture_output=True,
        text=True,
    )
    return target


def _index_rows(pdfs: list[Path], n: int, base_dir: Path) -> dict[str, Any]:
    """Indexación de un representante por doc: warm-up frío aparte + n Δ por doc.

    UN hijo para toda la corrida (el modelo se carga una vez); cada muestra
    escribe una copia con bytes ligeramente distintos (comentario PDF único) en
    `00-resources/`, de modo que el memo por contenido no pueda saltarse parse+embed.
    """
    vault = Path(tempfile.mkdtemp(prefix="bench-docs-", dir=base_dir))
    plan_path = base_dir / f"plan-{vault.name}.json"
    try:
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
        resources = vault / "00-resources"
        staging = vault / "staging"
        resources.mkdir(parents=True, exist_ok=True)
        staging.mkdir(parents=True, exist_ok=True)

        # Warm-up (solo carga del modelo; fuera de las muestras y publicado aparte).
        warm = staging / "warmup.md"
        warm.write_text("# Warm-up\n\nTexto de calentamiento para cargar el modelo.\n")
        plan = [{"source": str(warm), "target": str(resources / "warmup.md")}]
        for pdf in pdfs:
            for k in range(n):
                staged = staging / f"{pdf.stem}-{k}.pdf"
                staged.write_bytes(pdf.read_bytes() + f"\n% sample {k}\n".encode())
                plan.append(
                    {"source": str(staged), "target": str(resources / f"{pdf.stem}-{k}.pdf")}
                )
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        records = _run_child_records(
            ["--driver-index", str(vault), "--plan", str(plan_path)], env=env, timeout=7200
        )
        refreshes = [r for r in records if r.get("kind") == "refresh"]
        if len(refreshes) != len(plan):
            raise SystemExit(f"esperaba {len(plan)} refreshes, llegaron {len(refreshes)}")
        for record in refreshes:
            if record["locked"] or record["scanned"] != record["indexed"] + record["skipped"]:
                raise SystemExit(f"refresh inconsistente ({record['file']}): {record}")
        cold = refreshes[0]
        print(f"  warm-up frío (excluido): {cold['elapsed_ms']} ms", file=sys.stderr, flush=True)
        rows = []
        for index, pdf in enumerate(pdfs):
            samples = refreshes[1 + index * n : 1 + (index + 1) * n]
            elapsed = [s["elapsed_ms"] for s in samples]
            print(
                f"  index {pdf.name}: n={n}, p50={_nearest_rank_p(elapsed, 0.50)} ms, "
                f"p95={_nearest_rank_p(elapsed, 0.95)} ms",
                file=sys.stderr,
                flush=True,
            )
            rows.append(
                {
                    "file": pdf.name,
                    "pages": _pdf_pages(pdf),
                    "n": n,
                    "index_samples_ms": elapsed,
                    "index_p50_ms": _nearest_rank_p(elapsed, 0.50),
                    "index_p95_ms": _nearest_rank_p(elapsed, 0.95),
                    "rss_peak_mib": round(max(s["rss_peak_kib"] for s in samples) / 1024, 1),
                }
            )
        return {"cold_ms": cold, "rows": rows}
    finally:
        shutil.rmtree(vault, ignore_errors=True)
        plan_path.unlink(missing_ok=True)


def _corpus_sample_rows(directory: Path, count: int, n: int) -> list[dict[str, Any]]:
    """Extracción de una MUESTRA determinista (primeros K ordenados) de PDF de 1 página."""
    pdfs = sorted(directory.glob("*.pdf"))[:count]
    return [_measure_extract(pdf, n) for pdf in pdfs]


def _parent(args: argparse.Namespace) -> int:
    """Orquesta: copia, mide extracción (y opcionalmente indexación) y emite JSON."""
    base_dir = args.dir
    base_dir.mkdir(parents=True, exist_ok=True)

    if args.matrix:
        sources = sorted(FIXTURES_PDF.glob("*-pages.pdf"), key=lambda p: int(p.name.split("-")[0]))
        docs = _prepare_docs(sources)
        docs.append(_generate_pages(GENERATED_PAGES))
        index_targets = [p for p in docs if p.name in ("16-pages.pdf", "335-pages.pdf")]
    else:
        docs = [Path(p) for p in args.pdf]
        if args.doc_pages:
            docs.append(_generate_pages(args.doc_pages))
        index_targets = [Path(p) for p in args.index]

    host = _host_block(args.dir)
    result: dict[str, Any] = {
        "metric": "extracción markitdown + indexación de documentos binarios (D51, aparte del Δ)",
        "n_default": args.n,
        "percentile_definition": "nearest-rank: sorted[ceil(p*n)-1] (n declarado por fila)",
        "rss_method": (
            "VmHWM de /proc/self/status leído por el proceso hijo al terminar "
            "(high-water mark del kernel; no muestreo del padre)"
        ),
        "time_method": "time.monotonic() dentro del hijo: construct + convert por muestra",
        "host": host,
        "started_utc": datetime.now(UTC).isoformat(),
        "extraction": [],
    }

    print("== extracción ==", file=sys.stderr, flush=True)
    result["extraction"] = [_measure_extract(pdf, args.n) for pdf in docs]

    if args.corpus_sample is not None and args.corpus_sample.is_dir():
        print("== corpus de 1 página (muestra) ==", file=sys.stderr, flush=True)
        result["corpus_sample"] = {
            "dir": str(args.corpus_sample),
            "count": args.sample_count,
            "rows": _corpus_sample_rows(args.corpus_sample, args.sample_count, args.n),
        }
    else:
        result["corpus_sample"] = {"dir": str(args.corpus_sample), "rows": [], "skipped": True}

    if index_targets:
        print("== indexación ==", file=sys.stderr, flush=True)
        result["indexation"] = _index_rows(index_targets, args.n, base_dir)

    out = args.json or base_dir / (
        f"bench-documents-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"reporte JSON: {out}")
    return 0


def main() -> int:
    """CLI: `--matrix` mide todo; `--pdf` permite mediciones puntuales."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--driver-extract", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--driver-index", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--plan", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--pdf", action="append", default=[], help="PDF a extraer (repetible)")
    parser.add_argument("--index", action="append", default=[], help="PDF a indexar (repetible)")
    parser.add_argument(
        "--matrix", action="store_true", help="libros + 30 págs + muestra del corpus"
    )
    parser.add_argument(
        "--doc-pages", type=int, default=0, help="genera y mide un PDF de N páginas on-demand"
    )
    parser.add_argument("--n", type=int, default=DEFAULT_N, help=f"muestras (default {DEFAULT_N})")
    parser.add_argument("--json", type=Path, default=None, help="ruta del JSON de resultado")
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR, help="base temporal (btrfs)")
    parser.add_argument(
        "--corpus-sample",
        type=Path,
        default=DEFAULT_CORPUS_SAMPLE,
        help="dir con PDF de 1 página de T1 (muestra n>=3)",
    )
    parser.add_argument(
        "--sample-count", type=int, default=3, help="PDF de 1 página medidos en la muestra"
    )
    parser.add_argument("--keep", action="store_true", help="conservar los temporales")
    args = parser.parse_args()
    if args.driver_extract is not None:
        _driver_extract(args.driver_extract)
        return 0
    if args.driver_index is not None:
        if args.plan is None:
            raise SystemExit("--driver-index requiere --plan")
        _driver_index(args.driver_index, args.plan)
        return 0
    if args.n < 1:
        raise SystemExit("--n debe ser >= 1")
    try:
        return _parent(args)
    finally:
        if not args.keep:
            shutil.rmtree(args.dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
