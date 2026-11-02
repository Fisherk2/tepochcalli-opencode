"""T3 e2e: documentos nativos con markitdown — indexado y skips tipados.

Fuentes de verdad:

* specs/spec-rag-engine.md §Ruta de documentos — `docx/pptx/xlsx/xls/pdf` se
  extraen con `markitdown` **en su forma original** (D49: sin convertir a `.md`
  antes); los offsets citan el texto extraído (`offsets_ref="extract"`).
* specs/adr/adr-011-*.md §4.3 (D54): todo documento binario pierde la jerarquía
  de headings ⇒ `heading` nulo aunque markitdown emita `#` para un `.docx`.
* tasks/todo.md → T3 AC (e): un extractor que falla no aborta el pase; el
  documento queda en `skipped` y NUNCA produce una fila vacía.

Los `.docx`/`.xlsx` se generan EN EL TEST: el `.xlsx` con `openpyxl` (extra de
markitdown) y el `.docx` con `zipfile` de la stdlib (el extra solo lee docx, no
escribe): no se añaden dependencias ni binarios al repo. El indexado corre en
subproceso (patrón T8/T9).
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from model_cache import link_model_cache, offline_env, resolve_model_cache
from openpyxl import Workbook
from support.mcp_server import index_vault
from tepochcalli_flow import app as flow_app
from tepochcalli_flow import citation, parsers
from tepochcalli_flow.layout import DB_RELPATH, TABLE_NAME

DOCX_TEXT = "Cuerpo del informe docx con texto citable."
XLSX_CELLS = ("Nombre", "Valor", "cita", "42")

BLANK_PDF = (
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
"""PDF sintético con una página SIN capa de texto."""

CORRUPT_BYTES = bytes(range(256)) * 4
"""Binario que ningún convertidor de markitdown puede decodificar."""

REFRESH_SCRIPT = """
import dataclasses, json
from tepochcalli_flow.app import refresh_blocking
print(json.dumps(dataclasses.asdict(refresh_blocking())), flush=True)
"""


def _write_docx(path: Path) -> None:
    """Genera un `.docx` real con la stdlib (`zipfile`); el extra de markitdown solo lee."""
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
        f"<w:p><w:r><w:t>{DOCX_TEXT}</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document)


def _write_xlsx(path: Path) -> None:
    """Genera un `.xlsx` real con una tabla mínima (openpyxl)."""
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(list(XLSX_CELLS[:2]))
    sheet.append(list(XLSX_CELLS[2:]))
    workbook.save(path)


@pytest.fixture(scope="module")
def indexed_documents(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Vault con `.md` + `.docx` + `.xlsx` indexado en subproceso (una sola corrida)."""
    vault = tmp_path_factory.mktemp("vault-t3-docs")
    resources = vault / citation.RESOURCES_DIR
    resources.mkdir()
    (resources / "nota.md").write_text("# Nota\n\nProsa markdown citable.\n", encoding="utf-8")
    _write_docx(resources / "informe.docx")
    _write_xlsx(resources / "hoja.xlsx")
    index_vault(vault)
    return vault


def test_docx_and_xlsx_are_indexed_from_the_original_with_extract_offsets(
    indexed_documents: Path,
) -> None:
    """Binarios tal cual: `doc_kind` propio, `heading` nulo y slice sobre el extracto."""
    rows = _read_rows(indexed_documents)
    by_source = {str(row["source_path"]): row for row in rows}

    assert set(by_source) == {
        "00-Resources/nota.md",
        "00-Resources/informe.docx",
        "00-Resources/hoja.xlsx",
    }

    for source_path, expected_kind in (
        ("00-Resources/informe.docx", "docx"),
        ("00-Resources/hoja.xlsx", "xlsx"),
    ):
        rows_of = [row for row in rows if row["source_path"] == source_path]
        assert rows_of
        extracted = parsers.extract_text(indexed_documents / source_path)
        for row in rows_of:
            assert row["doc_kind"] == expected_kind
            assert citation.offsets_ref_for(expected_kind) == "extract"
            assert row["heading"] is None, (
                "D54: markitdown no conserva headings; no se inventa el del fichero"
            )
            assert citation.verify_slice_identity(
                extracted,
                int(str(row["char_start"])),
                int(str(row["char_end"])),
                str(row["text"]),
            ), f"identidad F1 rota en {source_path}"

    docx_text = parsers.extract_text(indexed_documents / "00-Resources/informe.docx")
    assert DOCX_TEXT in docx_text
    xlsx_text = parsers.extract_text(indexed_documents / "00-Resources/hoja.xlsx")
    assert all(cell in xlsx_text for cell in XLSX_CELLS)


def test_extraction_failures_are_skipped_without_rows_and_do_not_abort_the_pass(
    tmp_path: Path,
) -> None:
    """Corrupto y sin capa de texto: `skipped`, sin filas, el `.md` sano sí indexa."""
    vault = tmp_path / "vault"
    resources = vault / citation.RESOURCES_DIR
    resources.mkdir(parents=True)
    (resources / "sana.md").write_text("# Sana\n\nprosa.\n", encoding="utf-8")
    (resources / "escaneado.pdf").write_bytes(BLANK_PDF)
    (resources / "corrupto.pdf").write_bytes(CORRUPT_BYTES)

    proc = _refresh(vault)

    assert proc.returncode == 0, f"el pase abortó por un documento:\n{proc.stderr}"
    report = json.loads(proc.stdout.strip().splitlines()[-1])
    assert (report["scanned"], report["indexed"], report["skipped"]) == (3, 1, 2)
    assert report["scanned"] == report["indexed"] + report["skipped"]

    rows = _read_rows(vault)
    assert {str(row["source_path"]) for row in rows} == {"00-Resources/sana.md"}
    assert "extraction_failed" in proc.stderr
    assert "escaneado.pdf" in proc.stderr and "sin capa de texto" in proc.stderr
    assert "corrupto.pdf" in proc.stderr and "corrupto" in proc.stderr


def _refresh(vault: Path) -> subprocess.CompletedProcess[str]:
    """Ejecuta `refresh_blocking()` en subproceso con el vault y el cache de modelo dados."""
    cache = resolve_model_cache()
    models_link = link_model_cache(vault, cache)
    env = {
        **os.environ,
        flow_app.VAULT_ROOT_ENV: str(vault),
        "HF_HOME": str(models_link),
        "SENTENCE_TRANSFORMERS_HOME": str(models_link),
        **offline_env(cache),
    }
    env.pop("COCOINDEX_DB", None)
    return subprocess.run(
        [sys.executable, "-c", REFRESH_SCRIPT],
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )


def _read_rows(vault: Path) -> list[dict[str, object]]:
    """Lee la tabla `chunks` completa desde disco (solo lectura)."""
    import lancedb

    async def _go() -> list[dict[str, object]]:
        connection = await lancedb.connect_async(str(vault / DB_RELPATH))
        try:
            table = await connection.open_table(TABLE_NAME)
            arrow = await table.to_arrow()
            return arrow.to_pylist()
        finally:
            connection.close()

    return asyncio.run(_go())
