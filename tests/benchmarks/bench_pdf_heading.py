r"""Bench del impacto de D54: la cita de PDF **sin `heading`** — Phase 6 T10 (TD-27).

Mide las **dos capas** que D54 mezcla, porque son cosas distintas y solo una se puede
cambiar con un ADR:

1. **Capa de política (código nuestro).** `parsers._to_document_chunk` fuerza
   `heading=None` para todo `doc_kind` extraído (`if kind in SOURCE_OFFSETS_DOC_KINDS
   else None`). Ahí la fracción de citas sin heading es **1,0 por construcción**, no
   por el corpus: se cuenta igualmente (`chunks_with_heading`) para que el 1,0 quede
   medido y no afirmado.
2. **Capa de extracción (markitdown).** Si el extracto de markitdown **no contiene
   líneas ATX** (`#`, `##`…), revertir D54 en el código no produciría ni un heading:
   el coste sería del extractor, no de la política. Esto es lo que discrimina, y se
   mide con el MISMO escáner del dominio (`citation.HeadingScanner`), no con una
   regex propia: `headings_in_extract` es lo que `heading_before` devolvería si la
   política lo permitiera.

Además, para una consulta cuyo único material es un PDF (`--phase query`), publica
los campos reales que le quedan al agente: `source_path`, `doc_kind`, `heading`,
`char_start`/`char_end`, `offsets_ref`, `score` y el `text` persistido.

Protocolo (docs/TRD.md §6.1; método publicado con la cifra, D-P6-7):

* Extracción en proceso con `MarkItDown().convert(path).markdown` (`markitdown==0.1.9`,
  el extractor del payload, no una imitación).
* Chunking con el pipeline real (`parsers.chunk_document`, 1536/192 bytes, D11).
* `headings_in_extract` = transiciones del escáner del dominio línea a línea (O(n):
  el cursor `HeadingScanner` es incremental y solo avanza).
* `query` = índice real en un vault temporal (modelo cacheado por `link_model_cache`,
  offline), `refresh_blocking()` + `LanceDBChunkReader.search(top_k=5)` — el camino
  exacto del server, sin IPC — más la identidad F1 re-verificada por resultado.

Fases (una llamada de primer plano por fase; nada en segundo plano)::

    just python-bench-pdf-heading --phase extract --pdf tests/fixtures/pdf/16-pages.pdf
    just python-bench-pdf-heading --phase corpus-sample --n 20
    just python-bench-pdf-heading --phase query --pdf tests/fixtures/pdf/16-pages.pdf \\
        --query "…"
    just python-bench-pdf-heading --phase report

Cada fase escribe `<WORK_DIR>/<fase>-<slug>.json`; `report` los une. No corre en CI
(no es `test_*`). No toca `obsidian-workspace/.tepochcalli/{db,models}` ni el payload:
el vault es temporal bajo `--dir` y se borra salvo `--keep`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from model_cache import link_model_cache, offline_env, resolve_model_cache  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_PDF = REPO_ROOT / "tests" / "fixtures" / "pdf"
PAYLOAD_FLOW = REPO_ROOT / "obsidian-workspace" / ".tepochcalli" / "flow"
DEFAULT_DIR = Path("/tmp/opencode/phase6-t10")
DEFAULT_CORPUS_SAMPLE = Path("/tmp/opencode/phase6-corpus/00-Resources/pdfs")
DEFAULT_N = 20
TOP_K = 5

# Línea con forma de sección numerada ("2.3 Medidas de resultado"): la precisión
# que SÍ sobrevive en el texto extraído aunque el campo `heading` sea nulo.
_SECTION_LINE = re.compile(r"^\s{0,6}\d{1,3}(?:\.\d{1,3}){0,3}\.?\s+\S")

# Subrayado setext (`===` / `---` en su propia línea): jerarquía que NUESTRO escáner
# (solo ATX, limitación documentada) no reconoce. Se cuenta para no sobreafirmar que
# el extractor no entrega ninguna jerarquía.
_SETEXT_LINE = re.compile(r"^ {0,3}(?:=+|-{2,})\s*$")


def _vm_hwm_kib() -> int:
    """Pico de RSS del proceso (`VmHWM` del kernel, no un muestreo)."""
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmHWM:"):
            return int(line.split()[1])
    return 0


def _host_block() -> dict[str, Any]:
    """Host y método, para que la cifra viaje con su procedencia (D-P6-7)."""
    return {
        "host": {
            "cpus": os.cpu_count(),
            "rss_peak_kib": _vm_hwm_kib(),
            "python": sys.version.split()[0],
        },
        "method": {
            "extractor": "markitdown==0.1.9 MarkItDown().convert(path).markdown",
            "chunker": "parsers.chunk_document (1536/192 bytes, D11)",
            "heading_scanner": "citation.HeadingScanner (el del pipeline, no una regex)",
        },
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def _extract(path: Path) -> tuple[str, float]:
    """Extrae con markitdown (el extractor real) y devuelve (texto, ms)."""
    from markitdown import MarkItDown

    started = time.monotonic()
    text = MarkItDown().convert(path).markdown
    return text, round((time.monotonic() - started) * 1000, 1)


def _headings_in(text: str) -> list[dict[str, Any]]:
    """Headings que el dominio derivaría sobre `text` si la política los dejara pasar.

    Usa `HeadingScanner` (el mismo cursor que `chunk_document`), avanzando por línea:
    una transición del valor devuelto es una línea ATX que el escáner reconoce.
    """
    from tepochcalli_flow.citation import HeadingScanner

    scanner = HeadingScanner(text)
    found: list[dict[str, Any]] = []
    previous: str | None = None
    offset = 0
    for line in text.splitlines(keepends=True):
        offset += len(line)
        heading = scanner.heading_before(offset)
        if heading is not None and heading != previous:
            found.append({"char_start": offset - len(line), "heading": heading})
            previous = heading
    return found


def _headings_per_chunk(text: str, chunks: list[Any]) -> int:
    """Chunks que tendrían heading si la política NO forzara `None` en extraídos.

    Es el delta exacto de D54 en la capa de código: `heading_before` sobre el
    extracto, sin el gate de `doc_kind` de `parsers._to_document_chunk`.
    """
    from tepochcalli_flow.citation import HeadingScanner

    scanner = HeadingScanner(text)
    return sum(1 for chunk in chunks if scanner.heading_before(chunk.char_start) is not None)


def _analyse(path: Path, source_path: str) -> dict[str, Any]:
    """Analiza un PDF: extracción, headings disponibles, chunks y precisión restante."""
    from tepochcalli_flow.parsers import chunk_document

    text, extract_ms = _extract(path)
    headings = _headings_in(text)
    chunks = chunk_document(text, source_path)
    if_policy_allowed = _headings_per_chunk(text, chunks)
    sections = [line.strip() for line in text.splitlines() if _SECTION_LINE.match(line)]
    lines = text.splitlines()
    setext = [
        f"{lines[i - 1].strip()[:40]} ← {lines[i].strip()}"
        for i in range(1, len(lines))
        if _SETEXT_LINE.match(lines[i]) and lines[i - 1].strip()
    ]
    return {
        "pdf": str(path),
        "bytes": path.stat().st_size,
        "extract_ms": extract_ms,
        "chars": len(text),
        "lines": len(text.splitlines()),
        "page_breaks": text.count("\x0c"),
        "headings_in_extract": len(headings),
        "headings_sample": headings[:5],
        "numbered_section_lines": len(sections),
        "numbered_section_sample": sections[:5],
        "setext_candidates": len(setext),
        "setext_sample": setext[:3],
        "chunks": len(chunks),
        "chunks_with_heading": sum(1 for chunk in chunks if chunk.heading is not None),
        "chunks_with_heading_if_policy_allowed": if_policy_allowed,
        "distinct_headings_in_chunks": len(
            {chunk.heading for chunk in chunks if chunk.heading is not None}
        ),
        "first_chunk": chunks[0].text[:120] if chunks else "",
    }


def _phase_extract(paths: list[Path], work: Path) -> int:
    """`extract`: un registro por PDF, en el padre (sin hijos: markitdown en proceso)."""
    for path in paths:
        record = {**_host_block(), "phase": "extract", **_analyse(path, path.name)}
        _emit(record, f"extract-{path.stem}", work)
    return 0


def _phase_corpus_sample(directory: Path, n: int, work: Path) -> int:
    """`corpus-sample`: n PDFs del corpus de T1 (primeros n por orden lexicográfico)."""
    pdfs = sorted(p for p in directory.glob("*.pdf"))[:n]
    if not pdfs:
        raise SystemExit(f"sin PDFs en {directory}")
    records = [_analyse(path, path.name) for path in pdfs]
    totals = {
        "pdfs": len(records),
        "chunks": sum(r["chunks"] for r in records),
        "chunks_with_heading": sum(r["chunks_with_heading"] for r in records),
        "pdfs_with_headings_in_extract": sum(1 for r in records if r["headings_in_extract"]),
        "page_breaks": sum(r["page_breaks"] for r in records),
        "numbered_section_lines": sum(r["numbered_section_lines"] for r in records),
    }
    _emit(
        {
            **_host_block(),
            "phase": "corpus-sample",
            "directory": str(directory),
            "selection": f"primeros {n} por orden lexicográfico",
            "totals": totals,
            "per_file": records,
        },
        "corpus-sample",
        work,
    )
    return 0


def _measure_env(vault: Path) -> None:
    """Env de la fase de consulta: vault temporal + cache de modelo + offline."""
    from tepochcalli_flow.app import VAULT_ROOT_ENV

    models = vault / ".tepochcalli" / "models"
    os.environ[VAULT_ROOT_ENV] = str(vault)
    os.environ["HF_HOME"] = str(models)
    os.environ["SENTENCE_TRANSFORMERS_HOME"] = str(models)
    os.environ.update(offline_env(resolve_model_cache()))
    os.environ.pop("COCOINDEX_DB", None)


def _phase_query(pdf: Path, query: str, work: Path) -> int:
    """`query`: indexa un vault cuyo ÚNICO material es el PDF y devuelve las citas."""
    from tepochcalli_flow import app as flow_app
    from tepochcalli_flow.adapters.lancedb_reader import LanceDBChunkReader
    from tepochcalli_flow.citation import doc_kind_for, verify_slice_identity
    from tepochcalli_flow.config import load_config
    from tepochcalli_flow.layout import DB_RELPATH
    from tepochcalli_mcp.backend import _read_embedder

    vault = work / "vault-single-pdf"
    if vault.exists():
        shutil.rmtree(vault)
    resources = vault / "00-resources"
    resources.mkdir(parents=True)
    shutil.copy2(pdf, resources / pdf.name)
    models_link = link_model_cache(vault, resolve_model_cache())
    _measure_env(vault)

    report = flow_app.refresh_blocking()
    if report.locked or report.indexed != 1:
        raise SystemExit(f"refresh inesperado: {report}")

    config = load_config(vault)
    config.apply_model_cache_env()
    reader = LanceDBChunkReader(vault / DB_RELPATH, embed=_read_embedder(config))
    chunks = asyncio.run(reader.search(query, TOP_K))

    extract, _ = _extract(pdf)
    citations = []
    for chunk in chunks:
        citations.append(
            {
                "source_path": chunk.source_path,
                "doc_kind": doc_kind_for(chunk.source_path),
                "heading": chunk.heading,
                "char_start": chunk.char_start,
                "char_end": chunk.char_end,
                "offsets_ref": chunk.offsets_ref,
                "score": round(chunk.score, 6),
                "text_head": chunk.text[:100].replace("\n", " "),
                "f1_ok": verify_slice_identity(
                    extract, chunk.char_start, chunk.char_end, chunk.text
                ),
            }
        )
    _emit(
        {
            **_host_block(),
            "phase": "query",
            "pdf": str(pdf),
            "vault": str(vault),
            "models_cache": str(models_link.resolve()),
            "query": query,
            "top_k": TOP_K,
            "refresh": {
                "scanned": report.scanned,
                "indexed": report.indexed,
                "elapsed_ms": report.elapsed_ms,
            },
            "citations": citations,
            "distinct_source_paths": len({c["source_path"] for c in citations}),
            "citations_with_heading": sum(1 for c in citations if c["heading"] is not None),
            "f1_ok": sum(1 for c in citations if c["f1_ok"]),
        },
        "query",
        work,
    )
    return 0


def _phase_report(work: Path) -> int:
    """`report`: une los JSON de las fases en un único documento archivadle."""
    files = [p for p in sorted(work.glob("*.json")) if p.name != "pdf-heading.json"]
    if not files:
        raise SystemExit(f"sin JSON en {work}; corre las fases primero")
    merged = {"phases": [json.loads(path.read_text(encoding="utf-8")) for path in files]}
    target = work / "pdf-heading.json"
    target.write_text(json.dumps(merged, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"merged": str(target), "phases": len(files)}))
    return 0


def _write_docx(path: Path) -> None:
    """`.docx` mínimo con Heading1/Heading2 (el caso en que markitdown SÍ emite `#`).

    Sin dependencias (zipfile + OOXML a mano): el mismo shape que usa
    `tests/e2e/test_format_matrix.py` para la celda `docx`.
    """
    import zipfile

    prose = (
        "Prosa introductoria del informe con texto citable, deliberadamente larga para "
        "que el splitter canonico de 1536 bytes produzca varios chunks y la seccion se "
        "pueda citar por su heading igual que en un markdown. "
    ) * 8
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
        "<w:r><w:t>Informe Trimestral</w:t></w:r></w:p>"
        f"<w:p><w:r><w:t>{prose}</w:t></w:r></w:p>"
        '<w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr>'
        "<w:r><w:t>Resultados</w:t></w:r></w:p>"
        f"<w:p><w:r><w:t>{prose}</w:t></w:r></w:p>"
        "</w:body></w:document>"
    )
    types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.'
        'relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
        'relationships/officeDocument" Target="word/document.xml"/></Relationships>'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document)


def _emit(record: dict[str, Any], slug: str, work: Path) -> None:
    """Imprime el registro y lo archiva en `<WORK_DIR>/<fase>-<slug>.json`."""
    work.mkdir(parents=True, exist_ok=True)
    (work / f"{record['phase']}-{slug}.json").write_text(
        json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(record, ensure_ascii=False))


def main() -> int:
    """CLI: una fase por llamada, en primer plano."""
    parser = argparse.ArgumentParser(description="D54/TD-27: impacto de la cita PDF sin heading")
    parser.add_argument(
        "--phase", required=True, choices=["extract", "corpus-sample", "query", "report"]
    )
    parser.add_argument("--pdf", action="append", default=[], help="PDF a analizar (repeatable)")
    parser.add_argument("--dir", default=str(DEFAULT_DIR), help="work dir (btrfs, fuera del repo)")
    parser.add_argument("--corpus", default=str(DEFAULT_CORPUS_SAMPLE))
    parser.add_argument("--n", type=int, default=DEFAULT_N)
    parser.add_argument("--query", default="¿de qué trata el documento?")
    parser.add_argument(
        "--docx", action="store_true", help="genera y analiza un .docx con Heading1/Heading2"
    )
    args = parser.parse_args()

    work = Path(args.dir)
    if args.phase == "extract":
        paths = [Path(p) for p in args.pdf] or sorted(FIXTURES_PDF.glob("*-pages.pdf"))
        if args.docx:
            work.mkdir(parents=True, exist_ok=True)
            path = work / "informe-heading.docx"
            _write_docx(path)
            paths.append(path)
        return _phase_extract(paths, work)
    if args.phase == "corpus-sample":
        return _phase_corpus_sample(Path(args.corpus), args.n, work)
    if args.phase == "query":
        if not args.pdf:
            raise SystemExit("--phase query exige --pdf")
        return _phase_query(Path(args.pdf[0]), args.query, work)
    return _phase_report(work)


if __name__ == "__main__":
    raise SystemExit(main())
