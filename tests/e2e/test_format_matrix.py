"""T8: el criterio 7 como contrato ejecutable — matriz de 9 formatos y sus GAP.

Fuentes de verdad:

* docs/BACKLOG.md §1 / C7: «Pueda procesar distintos formatos
  de texto, si no, utilizar el convertidor Markdown para que pueda manipularse
  adecuadamente».
* specs/spec-rag-engine.md §Fuentes — la whitelist del índice son **8**
  extensiones (md/markdown/txt/pdf/docx/pptx/xlsx/xls); un `.html` no se indexa.
* specs/spec-markitdown.md §Catálogo + §Cadena de fallback — el conversor cubre 13
  extensiones; `.doc`/`.ppt` NO tienen convertidor en `markitdown==0.1.9`; sin OCR,
  un PDF escaneado es `SOURCE_UNREACHABLE` con `GUIDE_OCR`.
* docs/adr/adr-009-*.md (D28/D36) — el conversor devuelve SOLO el resumen de 5
  claves: el `.md` escrito es un artefacto en disco, **no** una cita.
* docs/adr/adr-010-*.md (D41/D49) — se indexan los ORIGINALES: `convert_*` no
  indexa; la cita de un binario apunta al binario con `offsets_ref="extract"`.
* tasks/plan.md §Task T8 — la matriz de 9 entradas, por celda: resultado,
  `doc_kind`, `offsets_ref`, indexabilidad y `source_path` resultante.

Qué se mide y por qué así:

* **Una sola matriz, ejecutada**: los valores por celda se leen del índice real
  (columna `doc_kind` de LanceDB) y del wire (`search` por stdio: `source_path`,
  `offsets_ref`, `heading`). Las expectativas viven en `CELLS`, derivadas de
  `citation.DocKind`/`offsets_ref_for` — no de memoria.
* **`html` entra por el conversor** y su `.html` original NUNCA es citable (no
  está en la whitelist del índice): el artefacto `.md` sí, **tras**
  `index_refresh` — la conversión por sí sola no indexa (D49), y eso se ejecuta
  en este módulo (search antes y después del refresh).
* **`url` es GAP declarado**: el host de la suite corre con el canario `nonet`
  (cero red) y `paths._deny_internal_host` rechaza loopback/privadas por diseño
  (SSRF, W-02) — un servidor HTTP local no puede servir el camino feliz. Se
  ejecuta lo que SÍ es ejecutable: el borde rechaza un `http://127.0.0.1` con
  `VALIDATION_ERROR` antes de conectar o escribir. No se marca PASS.
* **GAP no se simula**: `.doc`, `.ppt` y el PDF escaneado se declaran con su
  mensaje real del wire (catálogo o `GUIDE_OCR`), ejecutado, no inventado.
* **Sin dependencias nuevas** (R1): los fixtures se generan con la stdlib
  (`zipfile`, `struct`) y con los extras YA instalados de markitdown
  (`openpyxl`, `python-pptx`). El `.xls` es un BIFF2 mínimo escrito con `struct`
  (`xlwt` no está instalado: no se añade nada).
* **Sin latencia** (regla anti-flake): aquí solo se afirma formato y cita.

La tabla publicada en `docs/TRD.md` §6.3 la IMPRIME este módulo (misma fuente):
`test_published_matrix_matches_docs_trd` falla si el documento y la medición
divergen, así que la tabla no se escribe a mano.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import struct
import zipfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final

import pytest
from mcp import ClientSession
from openpyxl import Workbook
from pptx import Presentation
from pptx.util import Inches
from support.mcp_server import index_vault, running_server, server_env, wire_payload
from tepochcalli_flow import citation
from tepochcalli_mcp.tools import list_formats as list_formats_handler

FIXTURE_PDF = Path(__file__).parents[1] / "fixtures" / "pdf" / "articulo_t7.pdf"
"""PDF real de 1 página con texto extraíble (el MISMO fixture de T3/T11)."""

TRD = Path(__file__).parents[2] / "docs" / "TRD.md"
"""Documento cuya §6.3 debe coincidir literalmente con la salida de este test."""

EVIDENCE_ENV = "TEPOCHCALLI_FORMAT_MATRIX_EVIDENCE"
"""Ruta del JSON de evidencia; ausente ⇒ el test solo afirma (no escribe nada)."""

BLANK_PDF: Final = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
    b"xref\n"
    b"0 4\n"
    b"0000000000 65535 f\x20\n"
    b"0000000009 00000 n\x20\n"
    b"0000000052 00000 n\x20\n"
    b"0000000101 00000 n\x20\n"
    b"trailer<</Size 4/Root 1 0 R>>\n"
    b"startxref\n"
    b"160\n"
    b"%%EOF\n"
)
"""PDF sintético de una página SIN capa de texto: el caso «escaneado sin OCR»."""

HEADER: Final = (
    "formato",
    "entrada",
    "resultado",
    "doc_kind",
    "offsets_ref",
    "indexable",
    "source_path",
    "nota",
)


@dataclass(frozen=True)
class Cell:
    """Una fila de la matriz: formato, borde de entrada y lo prometido por la spec."""

    format: str
    entry: str
    """Borde por el que entra: `índice` (whitelist del flow) o `conversor` (3 tools)."""
    resultado: str
    doc_kind: str
    offsets_ref: str
    indexable: str
    source_path: str
    nota: str


CELLS: Final[tuple[Cell, ...]] = (
    Cell("md", "índice", "PASS", "md", "source", "sí", "00-resources/nota.md", "—"),
    Cell("txt", "índice", "PASS", "txt", "source", "sí", "00-resources/prosa.txt", "—"),
    Cell(
        "pdf",
        "índice",
        "PASS",
        "pdf",
        "extract",
        "sí",
        "00-resources/articulo.pdf",
        "heading nulo (D54)",
    ),
    Cell(
        "docx",
        "índice",
        "PASS",
        "docx",
        "extract",
        "sí",
        "00-resources/informe.docx",
        "heading nulo pese al `#` del original (D54)",
    ),
    Cell(
        "pptx",
        "índice",
        "PASS",
        "pptx",
        "extract",
        "sí",
        "00-resources/diapositivas.pptx",
        "heading nulo (D54)",
    ),
    Cell(
        "xlsx",
        "índice",
        "PASS",
        "xlsx",
        "extract",
        "sí",
        "00-resources/hoja.xlsx",
        "heading nulo (D54)",
    ),
    Cell(
        "xls",
        "índice",
        "PASS",
        "xls",
        "extract",
        "sí",
        "00-resources/legado.xls",
        "BIFF2 mínimo generado con `struct` (sin `xlwt`)",
    ),
    Cell(
        "html",
        "conversor",
        "PASS",
        "md",
        "source",
        "sí, tras index_refresh",
        "00-resources/pagina.md",
        "el `.html` original no está en la whitelist: nunca es citable",
    ),
    Cell(
        "url",
        "conversor",
        "GAP",
        "—",
        "—",
        "no verificado",
        "—",
        "sin egress (`nonet`) y el guard SSRF rechaza loopback; exige host con red "
        "o allowlist (ADR)",
    ),
)
"""Las 9 celdas del AC, con el valor que la spec promete y el test comprueba."""

GAPS: Final[tuple[Cell, ...]] = (
    Cell(
        ".doc",
        "índice/conversor",
        "GAP",
        "—",
        "—",
        "no",
        "—",
        "sin convertidor legacy en markitdown 0.1.9: `VALIDATION_ERROR` + catálogo; "
        "guarda como `.docx` o pasa el texto a `.md`",
    ),
    Cell(
        ".ppt",
        "índice/conversor",
        "GAP",
        "—",
        "—",
        "no",
        "—",
        "sin convertidor legacy en markitdown 0.1.9: `VALIDATION_ERROR` + catálogo; "
        "guarda como `.pptx` o pasa el texto a `.md`",
    ),
    Cell(
        "pdf escaneado",
        "índice/conversor",
        "GAP",
        "—",
        "—",
        "no",
        "—",
        "sin capa de texto y sin OCR: `skipped` al indexar y `SOURCE_UNREACHABLE` + "
        "`GUIDE_OCR` al convertir (OCR manual y reintenta)",
    ),
)
"""Lo que el sistema NO puede procesar, con el mensaje que el wire realmente da."""

MARKERS: Final[dict[str, str]] = {
    "md": "marcamdalfa",
    "txt": "marcatxtbeta",
    "pdf": "Tepochcalli Fixture Document",
    "docx": "marcadocxgamma",
    "pptx": "marcapptxdelta",
    "xlsx": "marcaxlsxepsilon",
    "xls": "marcaxlszeta",
    "html": "marcahtmlomega",
}
"""Texto único por fixture: la consulta con la que se comprueba qué es citable."""

SOURCES: Final[dict[str, str]] = {
    "md": "00-resources/nota.md",
    "txt": "00-resources/prosa.txt",
    "pdf": "00-resources/articulo.pdf",
    "docx": "00-resources/informe.docx",
    "pptx": "00-resources/diapositivas.pptx",
    "xlsx": "00-resources/hoja.xlsx",
    "xls": "00-resources/legado.xls",
}
"""`source_path` esperado de cada celda del índice — el original, no un derivado."""

HTML_ARTIFACT: Final = "00-resources/pagina.md"
"""Destino por omisión de `convert_document` (`00-resources/<slug>.md`, D37)."""


def _write_docx(path: Path, marker: str) -> None:
    """`.docx` real con `zipfile` (el extra de markitdown solo lee, no escribe)."""
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/'
        'vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/'
        'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/'
        '2006/relationships/officeDocument" Target="word/document.xml"/>'
        "</Relationships>"
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body><w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
        "<w:r><w:t>Titulo Docx</w:t></w:r></w:p>"
        f"<w:p><w:r><w:t>{marker} con texto citable.</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document)


def _write_pptx(path: Path, marker: str) -> None:
    """`.pptx` real con `python-pptx` (una diapositiva con un cuadro de texto)."""
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])  # en blanco
    slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1)).text_frame.text = marker
    presentation.save(path)


def _write_xlsx(path: Path, marker: str) -> None:
    """`.xlsx` real con `openpyxl` (una celda con la marca)."""
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append([marker])
    workbook.save(path)


def _write_xls(path: Path, marker: str) -> None:
    """`.xls` BIFF2 mínimo escrito con `struct` (`xlwt` no está instalado, R1).

    Layout: BOF de hoja (0x0009: versión 0x0002, stream 0x0010), LABEL_B2
    (0x0004: fila, columna, 3 bytes de atributos, longitud de 1 byte, texto) y
    EOF. `xlrd` 2.0.2 —el motor de `XlsConverter`— lee BIFF2 sin contenedor OLE2.
    """

    def record(code: int, data: bytes) -> bytes:
        return struct.pack("<HH", code, len(data)) + data

    def label(row: int, col: int, text: str) -> bytes:
        payload = text.encode("latin-1")
        return record(
            0x0004,
            struct.pack("<HH", row, col) + b"\x00\x00\x00" + bytes([len(payload)]) + payload,
        )

    path.write_bytes(
        record(0x0009, struct.pack("<HH", 0x0002, 0x0010))
        + label(0, 0, marker)
        + label(1, 0, "Valor legado")
        + record(0x000A, b"")
    )


def _build_vault(tmp_path: Path) -> Path:
    """Vault con los 7 fixtures indexables, el escaneado y las fuentes del conversor."""
    vault = tmp_path / "vault"
    resources = vault / citation.RESOURCES_DIR
    resources.mkdir(parents=True)
    staging = vault / "staging"
    staging.mkdir()
    (resources / "nota.md").write_text(
        f"# Nota de matriz\n\n{MARKERS['md']} de prosa markdown citable.\n", encoding="utf-8"
    )
    (resources / "prosa.txt").write_text(f"{MARKERS['txt']} en texto plano.\n", encoding="utf-8")
    shutil.copy(FIXTURE_PDF, resources / "articulo.pdf")
    (resources / "escaneado.pdf").write_bytes(BLANK_PDF)
    _write_docx(resources / "informe.docx", MARKERS["docx"])
    _write_pptx(resources / "diapositivas.pptx", MARKERS["pptx"])
    _write_xlsx(resources / "hoja.xlsx", MARKERS["xlsx"])
    _write_xls(resources / "legado.xls", MARKERS["xls"])
    (staging / "pagina.html").write_text(
        f"<html><body><h1>{MARKERS['html']}</h1></body></html>", encoding="utf-8"
    )
    (staging / "legado.doc").write_bytes(b"\xd0\xcf\x11\xe0 binario legacy sin convertidor")
    (staging / "anticuado.ppt").write_bytes(b"\xd0\xcf\x11\xe0 binario legacy sin convertidor")
    return vault


def _rows_by_source(vault: Path) -> dict[str, list[dict[str, object]]]:
    """Filas de `chunks` agrupadas por `source_path` (solo lectura, patrón T3/T7)."""
    import lancedb
    from tepochcalli_flow.layout import DB_RELPATH, TABLE_NAME

    async def _go() -> list[dict[str, object]]:
        connection = await lancedb.connect_async(str(vault / DB_RELPATH))
        try:
            table = await connection.open_table(TABLE_NAME)
            return (await table.to_arrow()).to_pylist()
        finally:
            connection.close()

    grouped: dict[str, list[dict[str, object]]] = {}
    for row in asyncio.run(_go()):
        grouped.setdefault(str(row["source_path"]), []).append(row)
    return grouped


def _hit(results: list[dict[str, object]], source_path: str) -> dict[str, object]:
    """El primer resultado del top-k que cita `source_path` (falla si no aparece)."""
    hits = [r for r in results if r["source_path"] == source_path]
    assert hits, (
        f"{source_path} no está en el top-k; devueltos: {[r['source_path'] for r in results]}"
    )
    return hits[0]


def _paths(results: list[dict[str, object]]) -> list[str]:
    """Los `source_path` citados por una respuesta de `search` (en orden)."""
    return [str(result["source_path"]) for result in results]


async def _search(session: ClientSession, marker: str) -> list[dict[str, object]]:
    """`search(marker)` por stdio: los resultados del wire (no del adaptador)."""
    result = await session.call_tool("search", {"query": marker, "top_k": 5})
    payload = wire_payload(result)
    assert not result.is_error, payload
    return list(payload["results"])


async def _convert(session: ClientSession, path: str) -> dict[str, object]:
    """`convert_document(path)` por stdio: resumen de 5 claves o payload de error."""
    return wire_payload(await session.call_tool("convert_document", {"path": path}))


@dataclass(frozen=True)
class Measurement:
    """Lo medido: citas del wire, artefactos, GAP ejecutados, refresh y filas."""

    rows: dict[str, list[dict[str, object]]]
    cited: dict[str, dict[str, object]]
    converted: dict[str, dict[str, object]]
    gaps: dict[str, dict[str, object]]
    docx_after_search: list[dict[str, object]]
    html_before_refresh: list[dict[str, object]]
    refresh: dict[str, object]


def _measure(vault: Path, models: Path) -> Measurement:
    """Una sola corrida: índice → wire → conversiones → GAP → refresh → citas."""

    async def journey() -> Measurement:
        cited: dict[str, dict[str, object]] = {}
        async with running_server(server_env(vault, models)) as session:
            for name, source in SOURCES.items():
                cited[name] = _hit(await _search(session, MARKERS[name]), source)
            converted = {
                "docx": await _convert(session, SOURCES["docx"]),
                "html": await _convert(session, "staging/pagina.html"),
            }
            # D49: la conversión NO indexa ⇒ el `.md` recién escrito no es cita todavía.
            docx_after = await _search(session, MARKERS["docx"])
            html_before = await _search(session, MARKERS["html"])
            # El refresh es el paso documentado para citar el artefacto `.md` (ADR-010).
            refresh = wire_payload(await session.call_tool("index_refresh", {}))
            cited["html"] = _hit(await _search(session, MARKERS["html"]), HTML_ARTIFACT)
            gaps = {
                ".doc": await _convert(session, "staging/legado.doc"),
                ".ppt": await _convert(session, "staging/anticuado.ppt"),
                "pdf escaneado": await _convert(session, "00-resources/escaneado.pdf"),
                "url": wire_payload(
                    await session.call_tool("add_source", {"uri": "http://127.0.0.1:9/pag.html"})
                ),
            }
        return Measurement(
            rows={},
            cited=cited,
            converted=converted,
            gaps=gaps,
            docx_after_search=docx_after,
            html_before_refresh=html_before,
            refresh=refresh,
        )

    measured = asyncio.run(journey())
    return replace(measured, rows=_rows_by_source(vault))


@pytest.fixture(scope="module")
def matrix(tmp_path_factory: pytest.TempPathFactory) -> Measurement:
    """Construye el vault, lo indexa y mide la matriz una sola vez por módulo."""
    vault = _build_vault(tmp_path_factory.mktemp("vault-t8-matrix"))
    return _measure(vault, index_vault(vault))


def _measured(measured: Measurement, name: str) -> dict[str, str]:
    """La celda medida: resultado, `doc_kind`, `offsets_ref`, indexabilidad y path."""
    if name == "url":
        assert "error" in measured.gaps["url"], measured.gaps["url"]
        return {
            "resultado": "GAP",
            "doc_kind": "—",
            "offsets_ref": "—",
            "indexable": "no verificado",
            "source_path": "—",
        }
    if name == "html":
        cited = measured.cited["html"]
        return {
            "resultado": "PASS",
            "doc_kind": str(measured.rows[HTML_ARTIFACT][0]["doc_kind"]),
            "offsets_ref": str(cited["offsets_ref"]),
            "indexable": "sí, tras index_refresh",
            "source_path": str(cited["source_path"]),
        }
    rows = measured.rows.get(SOURCES[name], [])
    if not rows:
        return {
            "resultado": "GAP",
            "doc_kind": "—",
            "offsets_ref": "—",
            "indexable": "no",
            "source_path": "—",
        }
    cited = measured.cited[name]
    return {
        "resultado": "PASS",
        "doc_kind": str(rows[0]["doc_kind"]),
        "offsets_ref": str(cited["offsets_ref"]),
        "indexable": "sí",
        "source_path": str(cited["source_path"]),
    }


def _cell_values(cell: Cell) -> dict[str, str]:
    """Lo que la spec promete para la celda, con las mismas claves que `_measured`."""
    return {
        "resultado": cell.resultado,
        "doc_kind": cell.doc_kind,
        "offsets_ref": cell.offsets_ref,
        "indexable": cell.indexable,
        "source_path": cell.source_path,
    }


@pytest.mark.parametrize("cell", CELLS, ids=[cell.format for cell in CELLS])
def test_each_cell_matches_the_spec(matrix: Measurement, cell: Cell) -> None:
    """Cada celda: lo medido (índice + wire) == lo que la spec promete."""
    assert _measured(matrix, cell.format) == _cell_values(cell)


def test_the_original_is_the_citation_and_the_converted_md_is_not(
    matrix: Measurement,
) -> None:
    """D28/D49: `written_to` es un artefacto; la cita de un binario es el ORIGINAL."""
    payload = matrix.converted["docx"]
    assert "error" not in payload, payload
    assert payload["written_to"] == "00-resources/informe.md"
    assert payload["source_uri"] == SOURCES["docx"]
    assert "00-resources/informe.md" not in _paths(matrix.docx_after_search), (
        "convert_document no indexa (D49): el artefacto no puede ser la cita del docx"
    )
    assert matrix.cited["docx"]["source_path"] == SOURCES["docx"]
    assert matrix.cited["docx"]["offsets_ref"] == "extract"


def test_html_is_citable_only_after_refresh_and_never_as_html(matrix: Measurement) -> None:
    """El `.html` no está en la whitelist: lo citable es el `.md`, y solo tras refrescar."""
    payload = matrix.converted["html"]
    assert "error" not in payload, payload
    assert payload["written_to"] == HTML_ARTIFACT
    assert HTML_ARTIFACT not in _paths(matrix.html_before_refresh), (
        "convert_document no indexa (D49): el artefacto no puede ser cita antes del refresh"
    )
    assert matrix.cited["html"]["source_path"] == HTML_ARTIFACT
    assert matrix.cited["html"]["offsets_ref"] == "source"
    assert not any(path.endswith((".html", ".htm")) for path in matrix.rows)


@pytest.mark.parametrize("cell", GAPS, ids=[cell.format for cell in GAPS])
def test_unsupported_inputs_are_declared_gaps_with_the_real_message(
    matrix: Measurement, cell: Cell
) -> None:
    """`.doc`, `.ppt` y escaneado: lo ejecutado da el mensaje accionable, no un PASS."""
    payload = matrix.gaps[cell.format]
    assert "error" in payload, f"{cell.format} no debería convertirse: {payload}"
    error = payload["error"]
    assert isinstance(error, dict)
    if cell.format == "pdf escaneado":
        assert error["code"] == "SOURCE_UNREACHABLE"
        assert "OCR" in str(error["message"]), error
        assert not matrix.rows.get("00-resources/escaneado.pdf"), (
            "un escaneado nunca indexa una fila vacía (OM-11)"
        )
    else:
        assert error["code"] == "VALIDATION_ERROR"
        details = error["details"]
        assert isinstance(details, dict)
        assert details["formats"] == list_formats_handler.list_formats()["formats"]
        assert not any(path.endswith(cell.format) for path in matrix.rows)


def test_url_is_a_declared_gap_rejected_before_any_fetch(matrix: Measurement) -> None:
    """`url`: sin egress y loopback denegado por el guard SSRF ⇒ GAP, nunca PASS."""
    error = matrix.gaps["url"]["error"]
    assert isinstance(error, dict)
    assert error["code"] == "VALIDATION_ERROR"
    assert "red interna" in str(error["message"]) or "userinfo" in str(error["message"])
    assert not any("pag.html" in path for path in matrix.rows), (
        f"el guard SSRF rechaza antes de convertir y escribir: {sorted(matrix.rows)}"
    )


def _render(rows: tuple[Cell, ...]) -> str:
    """Tabla markdown de la matriz — la MISMA que se publica en `docs/TRD.md`."""
    lines = [
        "| " + " | ".join(HEADER) + " |",
        "| " + " | ".join("---" for _ in HEADER) + " |",
    ]
    for cell in rows:
        lines.append(
            "| "
            + " | ".join(
                (
                    cell.format,
                    cell.entry,
                    cell.resultado,
                    cell.doc_kind,
                    cell.offsets_ref,
                    cell.indexable,
                    cell.source_path,
                    cell.nota,
                )
            )
            + " |"
        )
    return "\n".join(lines)


def test_published_matrix_matches_docs_trd(matrix: Measurement) -> None:
    """La tabla de `docs/TRD.md` §6.3 sale de este test: divergir ⇒ rojo."""
    for cell in CELLS:
        assert _measured(matrix, cell.format) == _cell_values(cell), cell.format
    rendered = _render(CELLS)
    gaps = _render(GAPS)
    _write_evidence(matrix, rendered, gaps)
    document = TRD.read_text(encoding="utf-8")
    assert rendered in document, (
        "docs/TRD.md §6.3 no coincide con la salida del test; pega esta tabla:\n" + rendered
    )
    assert gaps in document, "docs/TRD.md §6.3 no declara los GAP medidos:\n" + gaps


def _write_evidence(matrix: Measurement, rendered: str, gaps: str) -> None:
    """Vuelca la matriz medida al JSON de evidencia si el env lo pide (AC de T8)."""
    target = os.environ.get(EVIDENCE_ENV)
    if not target:
        return
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "command": f'{EVIDENCE_ENV}="{path}" just python-test-file format_matrix',
        "vault": "temporal: 7 fixtures indexables + escaneado + fuentes del conversor",
        "indexed_sources": sorted(matrix.rows),
        "cells": {cell.format: _measured(matrix, cell.format) for cell in CELLS},
        "gaps": {
            cell.format: {
                "code": matrix.gaps[cell.format]["error"]["code"],
                "message": matrix.gaps[cell.format]["error"]["message"],
            }
            for cell in GAPS
        },
        "refresh_after_conversions": matrix.refresh,
        "url_cell": {
            "result": "GAP",
            "executed": matrix.gaps["url"]["error"]["code"],
            "reason": "sin egress (canario nonet) y el guard SSRF rechaza loopback por diseño",
        },
        "table_markdown": rendered,
        "gaps_markdown": gaps,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
