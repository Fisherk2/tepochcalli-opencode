"""T13 (Phase 3.5) — e2e bulk de ~1 000 páginas + RE-MEDICIÓN del motor (marcado `slow`).

Fuentes de verdad: `tasks/todo.md` → T13 AC (a)-(i); `docs/TRD.md` §6 (protocolo:
n=20, nearest-rank, PDFs/binarios aparte); `specs/spec-rag-engine.md` §Presupuesto
de escala y §Semántica incremental; `specs/adr/adr-010-indice-multi-raiz-cita-vault.md`
§4.1/§4.6 (D51: los binarios se miden aparte del Δ de 30 s); `docs/WORKFLOW.md`
§Phase 1 (M1/M5) y §Phase 2 (M2), formato de cifras publicadas.

Qué se mide aquí y con qué método
---------------------------------
* **Conversión (AC b/c/d):** 21 llamadas REALES por stdio (`convert_document`):
  20 familias + el bulk de ~1 000 páginas. Cada una devuelve el resumen de 5
  claves (+`truncated`), `preview` ≤500 y **ningún cuerpo**: el artefacto
  completo queda en disco y se verifica contra él (`chars`, `bytes`, preview
  como prefijo, y el final del cuerpo AUSENTE del wire). Presupuesto por
  respuesta (`SUMMARY_CHAR_CEILING`=1 400 chars, `PAYLOAD_TOKEN_CEILING`) y
  **por suma** de las 21 respuestas.
* **Δ de texto (AC e):** n=20 ciclos como `bench_delta`, **raíces múltiples**
  (`["00-resources", "documentos"]`), rampa 1→50, cronómetro
  `RefreshReport.elapsed_ms`; p95 **nearest-rank** `sorted[ceil(0.95·n)−1]`
  (con n=20 = 19.º valor ordenado; helper REUTILIZADO de `bench_delta`).
  Metadatos de cita al **100 %** leídos de la tabla `chunks`: `source_path`
  vault-relativo + existente, offsets válidos, `heading` presente (nullable),
  `offsets_ref` según D50 y — para md/txt — identidad F1 re-sliceando el original.
* **Documentos (AC f, D51):** el coste de indexar 15 documentos (de las 20
  familias, las 8 extensiones de la whitelist del motor) se mide en su PROPIO
  refresh y NO se suma al Δ de texto; el Δ de un documento modificado (`.docx`)
  se mide también. **RSS pico:** `VmHWM` de `/proc/self/status` del PROPIO
  proceso del flow en cuatro puntos (texto inicial, documentos, Δ texto, Δ
  documento). `VmHWM` es un máximo histórico del proceso ⇒ el valor de cada
  fase es una **cota superior** que arrastra el pico anterior; se publica junto
  a `VmRSS` para que el incremento sea visible (nunca se presenta como
  «pico aislado»).
* **Venv (AC g, método T4/M9):** `du -sb`/`du -sh` y `*.dist-info` del venv
  **canónico** `obsidian-workspace/.tepochcalli/venv/` (NUNCA `.venv/`, que es
  el artefacto paralelo de uv).
* **Bulk (AC h):** el tiempo de conversión se mide y se publica; **ninguna
  aserción de latencia** (regla anti-flake). El único umbral asertado es el
  presupuesto de la casa para el Δ de texto (M1: p95 < 30 000 ms), que no es un
  umbral de reloj fino sino el criterio del producto.

Garantías de idempotencia: vault temporal bajo `/tmp/opencode/tepochcalli-t1-spike/`
(borrado al final), modelo por `model_cache` (nunca en el repo), y aborto si el
payload `obsidian-workspace/.tepochcalli/{db,models}` aparece contaminado.
Sin red: `offline_env` + canario `nonet` en el server del conversor.
Sin `time.sleep` y sin dependencias nuevas: los `.docx/.xlsx/.pptx` se generan
con `zipfile` (stdlib), el `.pdf` reutiliza el generador de fixtures del repo,
y el resto es texto. `.xls` (legacy, BIFF) NO se genera — best-effort declarado:
no hay escritor stdlib y su ruta queda cubierta por los contract tests.
"""

from __future__ import annotations

import asyncio
import dataclasses
import importlib.util
import io
import json
import os
import platform
import random
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

import pytest

TESTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TESTS_DIR))
sys.path.insert(0, str(TESTS_DIR / "benchmarks"))

from bench_delta import _corpus_text, _host_block, _nearest_rank_p  # noqa: E402
from model_cache import link_model_cache, offline_env, resolve_model_cache  # noqa: E402
from support.mcp_server import running_server, server_env, wire_payload  # noqa: E402
from tepochcalli_mcp import budget, summary  # noqa: E402

pytestmark = pytest.mark.slow
"""Nunca entra en la suite de corrección (`-m "not slow"`); solo `just python-test-slow`."""

SEED = 20261103
"""Semilla del corpus md/txt y de las páginas del bulk: el fixture es determinista."""

N_TEXT_FILES = 50
"""Tamaño del corpus md/txt del Δ (protocolo TRD §6: «1-50 archivos»)."""

N_RUNS = 20
"""Corridas del Δ (protocolo congelado: n=20, nearest-rank)."""

DELTA_BUDGET_MS = 30_000
"""M1: p95 < 30 000 ms para el Δ de TEXTO (los documentos se miden aparte, D51)."""

BULK_PAGES = 1_000
"""Páginas del fixture bulk: cada página = heading + prosa separada por `---`."""

BULK_MIN_BYTES = 1_000_000
"""AC (a): el fixture bulk pesa ≥1 MB realmente (se afirma al construirlo)."""

TEXT_ROOT = "00-resources"
DOC_ROOT = "documentos"
STAGING = "entrada"
OUTPUT = "salida"

DOC_OUTPUT_CASE = "10-informe.docx"
"""Documento que muta la corrida de Δ de documentos (re-parse + re-embed real)."""

BENCH_DIR = Path("/tmp/opencode/tepochcalli-t1-spike/bench-bulk")
"""Vaults/reportes temporales del bench (btrfs/NVMe, fuera del repo — patrón T10/T7)."""

REPO_ROOT = Path(__file__).resolve().parents[2]
VENV = REPO_ROOT / "obsidian-workspace" / ".tepochcalli" / "venv"
PAYLOAD_DB = REPO_ROOT / "obsidian-workspace" / ".tepochcalli" / "db"
PAYLOAD_MODELS = REPO_ROOT / "obsidian-workspace" / ".tepochcalli" / "models"

SUMMARY_FIELDS = ["written_to", "source_uri", "bytes", "chars", "preview"]
"""Orden congelado del resumen (spec-mcp-server §Tools del conversor / D36)."""

SOURCE_KINDS = {"md", "markdown", "txt"}
"""Extensiones cuyos offsets citan el original (`offsets_ref="source"`, D50)."""

ALL_DOC_KINDS = SOURCE_KINDS | {"pdf", "docx", "pptx", "xlsx", "xls"}
"""Conjunto cerrado de `doc_kind` (D43), espejo de la whitelist del motor."""


# --- generadores de fixtures (stdlib: zipfile + texto) ------------------------------------


def _docx(paragraphs: list[str], table: list[list[str]] | None = None) -> bytes:
    """`.docx` mínimo de OOXML (mammoth lo convierte: verificado en el pin 0.1.9)."""
    body = "".join(f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in paragraphs)
    if table is not None:
        rows = "".join(
            "<w:tr>"
            + "".join(f"<w:tc><w:p><w:r><w:t>{cell}</w:t></w:r></w:p></w:tc>" for cell in row)
            + "</w:tr>"
            for row in table
        )
        body += f"<w:tbl>{rows}</w:tbl>"
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.'
        'relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-'
        'officedocument.wordprocessingml.document.main+xml"/></Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
        'relationships/officeDocument" Target="word/document.xml"/></Relationships>'
    )
    return _zip_bytes(
        {
            "[Content_Types].xml": content_types,
            "_rels/.rels": rels,
            "word/document.xml": document,
        }
    )


def _xlsx(sheets: dict[str, list[list[str | int]]]) -> bytes:
    """`.xlsx` mínimo con N hojas (openpyxl/pandas lo abren: verificado en el pin)."""
    sheet_xml: list[tuple[str, str]] = []
    for index, rows in enumerate(sheets.values(), start=1):
        cells = ""
        for row_index, row in enumerate(rows, start=1):
            parts = []
            for column, value in enumerate(row):
                ref = f"{chr(ord('A') + column)}{row_index}"
                if isinstance(value, int):
                    parts.append(f'<c r="{ref}"><v>{value}</v></c>')
                else:
                    parts.append(f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is></c>')
            cells += f'<row r="{row_index}">{"".join(parts)}</row>'
        sheet_xml.append(
            (
                f"xl/worksheets/sheet{index}.xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f"<sheetData>{cells}</sheetData></worksheet>",
            )
        )
    sheet_entries = "".join(
        f'<sheet name="{name}" sheetId="{index}" r:id="rId{index}"/>'
        for index, name in enumerate(sheets, start=1)
    )
    rel_entries = "".join(
        f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/'
        f'officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, len(sheets) + 1)
    )
    overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/'
        'vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, len(sheets) + 1)
    )
    return _zip_bytes(
        {
            "[Content_Types].xml": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.'
                'relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.'
                f'openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>{overrides}'
                "</Types>"
            ),
            "_rels/.rels": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
                'relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
                'officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                "</Relationships>"
            ),
            "xl/workbook.xml": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                f"<sheets>{sheet_entries}</sheets></workbook>"
            ),
            "xl/_rels/workbook.xml.rels": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
                f'relationships">{rel_entries}</Relationships>'
            ),
            **dict(sheet_xml),
        }
    )


def _pptx(slides: list[str]) -> bytes:
    """`.pptx` mínimo con N diapositivas de título (python-pptx lo abre: verificado)."""
    ns = (
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    )
    slide_ids = "".join(
        f'<p:sldId id="{255 + index}" r:id="rId{index}"/>' for index in range(1, len(slides) + 1)
    )
    slide_rels = "".join(
        f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/'
        f'officeDocument/2006/relationships/slide" Target="slides/slide{index}.xml"/>'
        for index in range(1, len(slides) + 1)
    )
    overrides = "".join(
        f'<Override PartName="/ppt/slides/slide{index}.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.presentationml.slide+xml"/>'
        for index in range(1, len(slides) + 1)
    )
    entries: dict[str, str] = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.'
            'relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.'
            f'openxmlformats-officedocument.presentationml.presentation.main+xml"/>{overrides}'
            "</Types>"
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
            'relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
            'officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>'
            "</Relationships>"
        ),
        "ppt/presentation.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f"<p:presentation {ns}><p:sldIdLst>{slide_ids}</p:sldIdLst>"
            '<p:sldSz cx="9144000" cy="6858000"/></p:presentation>'
        ),
        "ppt/_rels/presentation.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
            f'relationships">{slide_rels}</Relationships>'
        ),
    }
    for index, title in enumerate(slides, start=1):
        entries[f"ppt/slides/slide{index}.xml"] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f"<p:sld {ns}><p:cSld><p:spTree>"
            '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            "<p:grpSpPr/>"
            '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Title 1"/><p:cNvSpPr><a:spLocks noGrp="1"/>'
            '</p:cNvSpPr><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr>'
            '<p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="9144000" cy="6858000"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
            f"<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>{title}</a:t></a:r></a:p>"
            "</p:txBody></p:sp></p:spTree></p:cSld></p:sld>"
        )
    return _zip_bytes(entries)


def _zip_bytes(entries: dict[str, str]) -> bytes:
    """Serializa las partes OOXML en memoria (sin tocar disco, sin dependencias)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _fixture_pdf(*, table: bool = False) -> bytes:
    """Reutiliza el generador de PDF del repo (fixture real, sin dependencias nuevas)."""
    path = TESTS_DIR / "fixtures" / "pdf" / "gen_fixture_pdf.py"
    spec = importlib.util.spec_from_file_location("gen_fixture_pdf", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_table_pdf() if table else module.build_pdf()


NOTA = "# Nota de campo\n\n## Contexto\n\nProsa citable sobre el altiplano y sus ciclos.\n"
ARTICULO = "# Artículo\n\nTexto del artículo familiar `markdown` con cites.\n"
PLANO = "Texto plano sin headings: la cita cae en offsets, no en el heading.\n"
UNICODE = "# 東京\n\n" + ("检索与观测的度量衡，文本以字符计数。🚀 " * 40).rstrip() + "\n"
LARGO = "# Largo\n\n" + ("palabra de relleno para superar el preview. " * 60).rstrip() + "\n"
MEDIO = "# Medio\n\n" + ("prosa media para el presupuesto del resumen. " * 12).rstrip() + "\n"
HTML = "<html><body><h1>Informe de campo</h1><p>Prosa HTML citable.</p></body></html>"
HTML_TABLE = (
    "<html><body><h2>Métrica</h2><table><tr><th>clave</th><th>valor</th></tr>"
    "<tr><td>IPC</td><td>4 ms</td></tr></table></body></html>"
)
CSV = "region,hallazgo\naltiplano,aridez\nvalle,riego\n"
JSON_DOC = '{"hallazgo": "aridez del altiplano", "region": "valle"}'
JSONL = '{"registro": 1, "texto": "primera linea"}\n{"registro": 2, "texto": "segunda"}\n'

DOC_FAMILIES: tuple[tuple[str, str | bytes, str | None], ...] = (
    ("01-nota.md", NOTA, None),
    ("02-articulo.markdown", ARTICULO, None),
    ("03-plano.txt", PLANO, None),
    ("04-unicode.md", UNICODE, None),
    ("05-informe.html", HTML, "Informe de campo"),
    ("06-tabla.htm", HTML_TABLE, "Métrica"),
    ("07-datos.csv", CSV, "region"),
    ("08-estructura.json", JSON_DOC, "hallazgo"),
    ("09-registros.jsonl", JSONL, "registro"),
    ("10-informe.docx", _docx(["Marcador docx familiar.", "Segundo párrafo."]), "Marcador docx"),
    (
        "11-tabla.docx",
        _docx(["Marcador tabla docx."], table=[["clave", "valor"], ["IPC", "4 ms"]]),
        "Marcador tabla docx",
    ),
    (
        "12-libro.xlsx",
        _xlsx({"Hoja1": [["clave", "valor"], ["IPC", 4], ["Marcador xlsx", 1]]}),
        "Marcador xlsx",
    ),
    (
        "13-hojas.xlsx",
        _xlsx({"Uno": [["a", 1]], "Dos": [["Marcador hoja dos", 2]]}),
        "Marcador hoja dos",
    ),
    ("14-charla.pptx", _pptx(["Marcador pptx"]), "Marcador pptx"),
    (
        "15-charla-dos.pptx",
        _pptx(["Primera diapositiva", "Marcador segunda diapositiva"]),
        "Marcador segunda diapositiva",
    ),
    ("16-articulo.pdf", _fixture_pdf(), "Tepochcalli Fixture Document"),
    ("17-tablas.pdf", _fixture_pdf(table=True), "IPC p95"),
    ("18-largo.md", LARGO, None),
    ("19-largo.txt", LARGO, None),
    ("20-medio.md", MEDIO, None),
)
"""Las 20 familias (12 extensiones del catálogo menos `.xls`, más variantes de contenido).

`marker=None` ⇒ la fuente es md/markdown/txt y el markdown convertido debe ser
IDÉNTICO al original; con marker ⇒ binario, y el markdown debe contener el texto
que insertamos (prueba de que el cuerpo íntegro se extrajo y quedó en disco).
"""

BULK_NAME = "bulk-1000-paginas.md"


def _bulk_markdown() -> str:
    """Fixture bulk determinista: `BULK_PAGES` páginas (heading + prosa + `---`)."""
    rng = random.Random(SEED)
    words = (
        "archivo fuente cita offset índice motor documento corpus página medida "
        "presupuesto latencia vector chunk raíz vault agente flujo búsqueda"
    ).split()
    parts = ["# Bulk de 1 000 páginas\n\n"]
    for page in range(1, BULK_PAGES + 1):
        prose = " ".join(rng.choice(words) for _ in range(170))
        parts.append(f"## Página {page}\n\n{prose}.\n\n---\n\n")
    return "".join(parts)


def _build_vault(vault: Path) -> None:
    """Materializa el vault del test: corpus md/txt, 20 familias, bulk y destinos."""
    for name in (TEXT_ROOT, DOC_ROOT, STAGING, OUTPUT):
        (vault / name).mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    for index in range(N_TEXT_FILES):
        suffix = "md" if index % 2 == 0 else "txt"
        (vault / TEXT_ROOT / f"nota-{index:02d}.{suffix}").write_text(
            _corpus_text(index, rng), encoding="utf-8"
        )
    for name, payload, _marker in DOC_FAMILIES:
        target = vault / DOC_ROOT / name
        if isinstance(payload, bytes):
            target.write_bytes(payload)
        else:
            target.write_text(payload, encoding="utf-8")
    bulk = _bulk_markdown()
    assert len(bulk.encode("utf-8")) >= BULK_MIN_BYTES, "el bulk no llega a 1 MB"
    (vault / STAGING / BULK_NAME).write_text(bulk, encoding="utf-8")


def _indexable_documents(vault: Path) -> int:
    """Documentos de `documentos/` que la whitelist del MOTOR indexa (no el conversor)."""
    from tepochcalli_flow.citation import UnsupportedDocKindError, doc_kind_for

    count = 0
    for path in (vault / DOC_ROOT).rglob("*"):
        if path.is_file():
            try:
                doc_kind_for(path)
            except UnsupportedDocKindError:
                continue
            count += 1
    return count


# --- fase de conversión (21 llamadas reales por stdio) -------------------------------------


def _convert(vault: Path) -> dict[str, Any]:
    """Las 21 conversiones + aserciones de forma, cuerpo-en-disco y presupuesto."""
    env = server_env(vault)  # el conversor no toca el embedder
    cases = [
        (f"{DOC_ROOT}/{name}", f"{OUTPUT}/{Path(name).with_suffix('.md').name}", marker)
        for name, _payload, marker in DOC_FAMILIES
    ]
    cases.append((f"{STAGING}/{BULK_NAME}", f"{OUTPUT}/{BULK_NAME}", None))

    async def journey() -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        async with running_server(env) as session:
            for source, destination, marker in cases:
                started = time.perf_counter()
                result = await session.call_tool(
                    "convert_document", {"path": source, "output_path": destination}
                )
                took_ms = round((time.perf_counter() - started) * 1000, 1)
                wire = result.content[0].text if result.content else ""
                payload = wire_payload(result)
                assert not result.is_error, f"{source}: {wire}"
                assert list(payload)[:5] == SUMMARY_FIELDS, source
                assert set(payload) <= {*SUMMARY_FIELDS, "truncated"}, source
                assert len(wire) <= summary.SUMMARY_CHAR_CEILING, source
                assert len(str(payload["preview"])) <= summary.PREVIEW_CHARS, source
                assert budget.estimate_tokens(wire) <= budget.PAYLOAD_TOKEN_CEILING, (
                    f"{source}: presupuesto de tokens por respuesta"
                )

                written = vault / str(payload["written_to"])
                body = written.read_text(encoding="utf-8")
                assert payload["chars"] == len(body), source
                assert payload["bytes"] == written.stat().st_size, source
                assert payload["preview"] == body[: summary.PREVIEW_CHARS], source
                assert body.strip(), f"{source}: el artefacto en disco está vacío"
                if marker is None:
                    original = (vault / source).read_text(encoding="utf-8")
                    assert body == original, f"{source}: el cuerpo íntegro no quedó en disco"
                else:
                    assert marker in body, f"{source}: falta el marcador {marker!r} en disco"
                if source == f"{STAGING}/{BULK_NAME}":
                    assert body.count("## Página ") == BULK_PAGES, "el bulk no tiene sus páginas"
                if len(body) > summary.SUMMARY_CHAR_CEILING:
                    assert body[-500:] not in wire, f"{source}: cuerpo en el wire"
                records.append(
                    {
                        "source": source,
                        "written_to": str(payload["written_to"]),
                        "source_bytes": (vault / source).stat().st_size,
                        "chars": len(body),
                        "wire_chars": len(wire),
                        "tokens": budget.estimate_tokens(wire),
                        "truncated": bool(payload.get("truncated", False)),
                        "convert_ms": took_ms,
                    }
                )
        return records

    return {"cases": asyncio.run(journey()), "n": len(cases)}


# --- medición del motor (driver en subproceso: environment global de cocoindex) ------------


def _emit(record: dict[str, Any]) -> None:
    """Un registro JSON por línea (el padre parsea; stdout del driver solo es JSON)."""
    print(json.dumps(record), flush=True)


def _vm() -> dict[str, int]:
    """`VmHWM`/`VmRSS` del proceso actual en MiB (Linux; vacío si no existe /proc)."""
    values: dict[str, int] = {}
    status = Path("/proc/self/status")
    if not status.exists():
        return values
    for line in status.read_text().splitlines():
        if line.startswith(("VmHWM:", "VmRSS:")):
            key, _, rest = line.partition(":")
            values[key.strip()] = int(rest.split()[0]) // 1024
    return values


def _read_rows(vault: Path) -> list[dict[str, Any]]:
    """Lee la tabla `chunks` completa (solo lectura), patrón de `test_multi_root_e2e`."""
    import lancedb
    from tepochcalli_flow.layout import DB_RELPATH

    async def _go() -> list[dict[str, Any]]:
        connection = await lancedb.connect_async(str(vault / DB_RELPATH))
        try:
            table = await connection.open_table("chunks")
            arrow = await table.to_arrow()
            return arrow.to_pylist()
        finally:
            connection.close()

    return asyncio.run(_go())


def _check_citations(vault: Path, rows: list[dict[str, Any]]) -> list[str]:
    """Metadatos de cita al 100 %: `source_path` vault-relativo + offsets + D50/D54."""
    from tepochcalli_flow import citation

    problems: list[str] = []
    for row in rows:
        source_path = str(row.get("source_path") or "")
        kind = str(row.get("doc_kind") or "")
        if "heading" not in row:
            problems.append(f"{source_path}: falta la clave `heading`")
        if (
            not source_path
            or Path(source_path).is_absolute()
            or ".." in Path(source_path).parts
            or not (vault / source_path).is_file()
        ):
            problems.append(f"source_path no vault-relativo o inexistente: {source_path!r}")
            continue
        if Path(source_path).parts[0] not in {TEXT_ROOT, DOC_ROOT}:
            problems.append(f"{source_path}: fuera de las raíces declaradas")
        if kind not in ALL_DOC_KINDS:
            problems.append(f"{source_path}: doc_kind inválido {kind!r}")
        start, end = row.get("char_start"), row.get("char_end")
        if start is None or end is None or int(end) <= int(start):
            problems.append(f"{source_path}: offsets inválidos ({start}, {end})")
            continue
        expected_ref = "source" if kind in SOURCE_KINDS else "extract"
        # `offsets_ref` NO es columna: el contrato la DERIVA de `doc_kind` al leer
        # (ports.CitedChunk/adaptador, D50). Se comprueba la derivación, no un campo ausente.
        if citation.offsets_ref_for(kind) != expected_ref:  # type: ignore[arg-type]
            problems.append(f"{source_path}: offsets_ref_for({kind!r}) != {expected_ref}")
        if kind in SOURCE_KINDS:
            original = (vault / source_path).read_text(encoding="utf-8")
            if not citation.verify_slice_identity(
                original, int(start), int(end), str(row.get("text") or "")
            ):
                problems.append(f"{source_path}: identidad F1 rota")
        elif row.get("heading") is not None:
            problems.append(f"{source_path}: binario con heading (D54)")
    return problems


def _mutate_docx(path: Path) -> None:
    """Añade un párrafo al `.docx` (cambia el hash ⇒ re-parse + re-embed del Δ)."""
    with zipfile.ZipFile(path) as source:
        entries = {name: source.read(name) for name in source.namelist()}
    document = entries["word/document.xml"].decode("utf-8")
    extra = "<w:p><w:r><w:t>Actualización del delta de documentos.</w:t></w:r></w:p>"
    entries["word/document.xml"] = document.replace("</w:body>", extra + "</w:body>").encode()
    with zipfile.ZipFile(path, "w") as target:
        for name, data in entries.items():
            target.writestr(name, data)


def _driver(vault: Path) -> None:
    """Índice multi-raíz, 20 Δ de texto, documentos aparte, Δ de documento y citas."""
    from tepochcalli_flow import app as flow_app

    roots = [TEXT_ROOT, DOC_ROOT]
    expected_docs = _indexable_documents(vault)
    resources = vault / TEXT_ROOT
    names = sorted(path.name for path in resources.iterdir())

    def refresh(tag: str, modified: int, active_roots: list[str] | None = None) -> None:
        started = time.monotonic()
        report = flow_app.refresh_blocking(active_roots or roots)
        wall_ms = round((time.monotonic() - started) * 1000, 1)
        if report.locked:
            raise SystemExit(f"[{tag}] refresh inesperadamente locked=True")
        if tag.startswith("run-") and report.indexed != modified:
            raise SystemExit(f"[{tag}] indexed={report.indexed} != {modified}")
        _emit(
            {
                "kind": "refresh",
                "tag": tag,
                "modified_files": modified,
                "report": dataclasses.asdict(report),
                "wall_ms": wall_ms,
                "vm": _vm(),
            }
        )

    _emit({"kind": "start", "python": platform.python_version(), "pid": os.getpid()})

    # (1) índice de texto en frío, sola la raíz de texto.
    refresh("text-index", N_TEXT_FILES, [TEXT_ROOT])
    # (2) primera declaración de `documentos/`: COSTE DE LOS DOCUMENTOS, medido aparte (D51).
    started = time.monotonic()
    report = flow_app.refresh_blocking(roots)
    _emit(
        {
            "kind": "documents-index",
            "expected_documents": expected_docs,
            "report": dataclasses.asdict(report),
            "wall_ms": round((time.monotonic() - started) * 1000, 1),
            "vm": _vm(),
        }
    )
    # (3) n=20 ciclos de texto con RAÍCES MÚLTIPLES (protocolo TRD §6.2, rampa 1→50).
    for run in range(N_RUNS):
        modified = 1 + (run * (N_TEXT_FILES - 1)) // (N_RUNS - 1)
        for index in range(modified):
            path = resources / names[index]
            base = path.read_text(encoding="utf-8")
            path.write_text(
                base + f"\n\n## Actualización (corrida {run})\n\n"
                f"Reescritura determinista de la corrida {run} sobre el fichero {index}.\n",
                encoding="utf-8",
            )
        refresh(f"run-{run:02d}", modified)
    # (4) Δ de UN documento binario (coste aparte, D51) con el índice ya caliente.
    _mutate_docx(vault / DOC_ROOT / DOC_OUTPUT_CASE)
    refresh("document-delta", 1)
    # (5) citas: se leen DESPUÉS de los picos para no contaminar `VmHWM`.
    rows = _read_rows(vault)
    problems = _check_citations(vault, rows)
    _emit(
        {
            "kind": "citations",
            "rows": len(rows),
            "sources_n": len({str(row.get("source_path")) for row in rows}),
            "problems_n": len(problems),
            "problems": problems[:5],
        }
    )
    _emit({"kind": "done"})


# --- orquestación del padre ----------------------------------------------------------------


def _measure_engine(vault: Path, cache: Path) -> dict[str, Any]:
    """Lanza el driver con el entorno canónico y agrega las muestras (n=20, p95)."""
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
        [sys.executable, str(Path(__file__).resolve()), "--driver", str(vault)],
        env=env,
        capture_output=True,
        text=True,
        timeout=3600,
        check=False,
    )
    if proc.returncode != 0:
        print(proc.stderr[-8000:], file=sys.stderr)
        raise AssertionError(f"el driver del motor falló (rc={proc.returncode})")

    records = [
        json.loads(line) for line in proc.stdout.splitlines() if line.strip().startswith("{")
    ]
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_kind.setdefault(record["kind"], []).append(record)
    cycles = [record for record in by_kind.get("refresh", []) if record["tag"].startswith("run-")]
    assert len(cycles) == N_RUNS, f"esperaba {N_RUNS} ciclos, llegaron {len(cycles)}"
    samples = [int(record["report"]["elapsed_ms"]) for record in cycles]
    text_index = by_kind["refresh"][0]
    documents = by_kind["documents-index"][0]
    document_delta = next(r for r in by_kind["refresh"] if r["tag"] == "document-delta")
    citations = by_kind["citations"][0]

    for record in cycles:
        report = record["report"]
        assert report["roots"] == [TEXT_ROOT, DOC_ROOT], "el Δ debe declarar las dos raíces"
        assert report["scanned"] == report["indexed"] + report["skipped"]
    assert documents["report"]["indexed"] == documents["expected_documents"], (
        "los documentos se indexan exactamente una vez: "
        f"indexed={documents['report']['indexed']} expected={documents['expected_documents']}"
    )

    return {
        "text_index": text_index,
        "documents_index": documents,
        "cycles": cycles,
        "samples_ms": samples,
        "p95_ms": _nearest_rank_p(samples, 0.95),
        "document_delta": document_delta,
        "citations": citations,
    }


def _measure_venv() -> dict[str, Any]:
    """Tamaño del venv canónico y nº de paquetes (método T4/M9: `du` + `*.dist-info`)."""
    assert VENV.is_dir(), f"no existe el venv canónico {VENV}"
    size_bytes = int(
        subprocess.run(
            ["du", "-sb", str(VENV)], capture_output=True, text=True, check=True
        ).stdout.split()[0]
    )
    size_human = subprocess.run(
        ["du", "-sh", str(VENV)], capture_output=True, text=True, check=True
    ).stdout.split()[0]
    packages = sum(1 for _ in VENV.glob("lib/python*/site-packages/*.dist-info"))
    return {
        "path": str(VENV.relative_to(REPO_ROOT)),
        "size_bytes": size_bytes,
        "size_gib": round(size_bytes / 1024**3, 3),
        "du_sh": size_human,
        "dist_info_packages": packages,
        "note": "venv canónico `venv/` (el `.venv/` paralelo de uv no se mide: artefacto local)",
    }


def _percentile_method() -> str:
    """Método publicado junto al número (regla de la casa: n + método siempre)."""
    return (
        "nearest-rank: sorted[ceil(0.95*n)-1]; con n=20 es el 19.º valor ordenado "
        "(segundo mayor) — un outlier aislado no lo determina, las 2 corridas más "
        "lentas pesan"
    )


def _report(vault: Path, conversion: dict[str, Any], engine: dict[str, Any]) -> dict[str, Any]:
    """Informe completo (se escribe a disco y se imprime un resumen legible)."""
    cases = conversion["cases"]
    bulk = cases[-1]
    host = _host_block(vault)
    return {
        "metric": "T13 Phase 3.5 — e2e bulk 1 000 páginas + re-medición del motor",
        "host": host,
        "corpus": {
            "text_files": N_TEXT_FILES,
            "documents": len(DOC_FAMILIES),
            "indexable_documents": engine["documents_index"]["expected_documents"],
            "bulk_pages": BULK_PAGES,
            "bulk_bytes": bulk["source_bytes"],
        },
        "conversion": {
            "calls": conversion["n"],
            "per_response_ceiling_chars": summary.SUMMARY_CHAR_CEILING,
            "per_response_max_chars": max(case["wire_chars"] for case in cases),
            "per_response_max_tokens": max(case["tokens"] for case in cases),
            "sum_chars": sum(case["wire_chars"] for case in cases),
            "sum_tokens": sum(case["tokens"] for case in cases),
            "sum_body_bytes": sum(case["chars"] for case in cases),
            "cases": cases,
        },
        "engine": {
            "n": N_RUNS,
            "percentile_definition": _percentile_method(),
            "p95_delta_text_ms": engine["p95_ms"],
            "budget_ms": DELTA_BUDGET_MS,
            "verdict": "PASS" if engine["p95_ms"] < DELTA_BUDGET_MS else "FAIL",
            "samples_ms": engine["samples_ms"],
            "roots": [TEXT_ROOT, DOC_ROOT],
            "text_index_ms": engine["text_index"]["report"]["elapsed_ms"],
            "documents_index_ms": engine["documents_index"]["report"]["elapsed_ms"],
            "documents_indexed": engine["documents_index"]["report"]["indexed"],
            "document_delta_ms": engine["document_delta"]["report"]["elapsed_ms"],
            "document_delta_indexed": engine["document_delta"]["report"]["indexed"],
            "rss_vmhwm_mib": {
                "text_index": engine["text_index"]["vm"].get("VmHWM"),
                "documents_index": engine["documents_index"]["vm"].get("VmHWM"),
                "text_delta_end": engine["cycles"][-1]["vm"].get("VmHWM"),
                "document_delta": engine["document_delta"]["vm"].get("VmHWM"),
            },
            "rss_method": (
                "VmHWM de /proc/self/status del proceso del flow; es un máximo histórico "
                "⇒ cada cifra es una COTA SUPERIOR que arrastra los picos previos "
                "(VmRSS por fase en los registros crudos)"
            ),
            "citations": engine["citations"],
        },
        "venv": _measure_venv(),
    }


def test_bulk_pages_conversions_and_engine_reprofile() -> None:
    """T13: 21 conversiones reales + re-medición del motor + venv, todo publicado."""
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    vault = Path(tempfile.mkdtemp(prefix="bench-bulk-", dir=BENCH_DIR))
    try:
        _build_vault(vault)
        cache = resolve_model_cache()
        conversion = _convert(vault)
        engine = _measure_engine(vault, cache)
        report = _report(vault, conversion, engine)

        # AC (b/c/d): 21 conversiones, resumen-only y presupuesto por respuesta y por suma.
        assert conversion["n"] == len(DOC_FAMILIES) + 1
        assert report["conversion"]["per_response_max_chars"] <= summary.SUMMARY_CHAR_CEILING
        assert (
            report["conversion"]["sum_chars"] <= conversion["n"] * summary.SUMMARY_CHAR_CEILING
        ), "la suma de las 21 respuestas cabe en el techo por respuesta"
        assert report["conversion"]["cases"][-1]["chars"] >= BULK_MIN_BYTES

        # AC (e): p95 con raíces múltiples + citas al 100 % (source_path vault-relativo).
        assert engine["p95_ms"] < DELTA_BUDGET_MS, (
            f"Δ p95 {engine['p95_ms']} ms ≥ {DELTA_BUDGET_MS} ms (M1) — muestras "
            f"{engine['samples_ms']}"
        )
        assert engine["citations"]["problems_n"] == 0, engine["citations"]["problems"]
        assert engine["citations"]["rows"] > 0
        assert engine["document_delta"]["report"]["indexed"] == 1

        # AC (g): el venv canónico se mide (no se estima).
        assert report["venv"]["size_bytes"] > 0 and report["venv"]["dist_info_packages"] > 0

        # Garantía de idempotencia: el payload del repo no se toca.
        contaminated = [str(path) for path in (PAYLOAD_DB, PAYLOAD_MODELS) if path.exists()]
        assert not contaminated, f"el payload fue contaminado: {contaminated}"

        out_path = BENCH_DIR / "phase35-bulk-latest.json"
        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        _print_report(report, out_path)
    finally:
        shutil.rmtree(vault, ignore_errors=True)


def _print_report(report: dict[str, Any], out_path: Path) -> None:
    """Resumen legible (se ve con `-s`; el JSON completo queda en `out_path`)."""
    host = report["host"]
    engine = report["engine"]
    conversion = report["conversion"]
    venv = report["venv"]
    print("\n=== T13 Phase 3.5 — bulk 1 000 páginas + re-medición del motor ===")
    print(
        f"host: {host['cpu_model']} · {host['cpu_count_logical']} hilos · "
        f"{host['mem_total_kb'] / 1024**2:.1f} GiB · {host['platform']} · "
        f"fs {host['vault_filesystem']}"
    )
    print(
        f"corpus: {report['corpus']['text_files']} md/txt + "
        f"{report['corpus']['documents']} familias "
        f"({report['corpus']['indexable_documents']} indexables) + bulk "
        f"{report['corpus']['bulk_pages']} págs / {report['corpus']['bulk_bytes']} B"
    )
    print(
        f"conversión: {conversion['calls']} llamadas · máx {conversion['per_response_max_chars']}"
        f"/{summary.SUMMARY_CHAR_CEILING} chars · suma {conversion['sum_chars']} chars"
        f" ({conversion['sum_tokens']} tokens) · cuerpos en disco"
        f" {conversion['sum_body_bytes']} chars"
    )
    print(
        f"Δ texto: p95 {engine['p95_delta_text_ms']} ms (n={engine['n']}, nearest-rank)"
        f" < {engine['budget_ms']} ms ⇒ {engine['verdict']}"
    )
    print(f"  muestras (ms): {engine['samples_ms']}")
    print(
        f"documentos: índice {engine['documents_index_ms']} ms "
        f"({engine['documents_indexed']}) · Δ doc {engine['document_delta_ms']} ms — aparte (D51)"
    )
    print(f"RSS VmHWM (MiB): {engine['rss_vmhwm_mib']}")
    print(
        f"citas: {engine['citations']['rows']} filas / "
        f"{engine['citations']['sources_n']} fuentes · problemas "
        f"{engine['citations']['problems_n']}"
    )
    print(
        f"venv: {venv['du_sh']} ({venv['size_gib']} GiB) · "
        f"{venv['dist_info_packages']} paquetes · {venv['path']}"
    )
    print(f"reporte JSON: {out_path}\n")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--driver":
        _driver(Path(sys.argv[2]))
    else:
        raise SystemExit("uso: python test_phase35_bulk.py --driver <vault>")
