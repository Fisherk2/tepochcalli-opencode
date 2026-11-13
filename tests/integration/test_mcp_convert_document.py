"""T9 integración: conversión REAL de un `.docx` y test nuclear (OM-1) por stdio.

Fuentes de verdad:

* tasks/todo.md T9 AC (a), (g), (i) — `convert_local` sin frontmatter ni
  `converted_at`; la respuesta es el resumen de 5 claves; documento ≥100 000
  chars con una marca única ⇒ la marca está en el `.md` escrito y NUNCA en
  `content[0].text`.
* ADR-009 §4.1 Confirmation — el test nuclear se gradúa en el wire: la cadena
  completa (harness → stdio → handler → markitdown → disco → resumen).

El `.docx` se genera con `zipfile` de la stdlib (el extra de markitdown solo
lee, no escribe): sin binarios ni dependencias nuevas (patrón T3).
"""

from __future__ import annotations

import asyncio
import json
import zipfile
from pathlib import Path

from support.mcp_server import running_server, server_env, wire_payload
from tepochcalli_mcp import summary
from tepochcalli_mcp.convert import convert_local
from tepochcalli_mcp.tools import convert_document as handler

DOCX_TEXT = "Cuerpo del informe docx con texto citable."
"""Texto reconocible que el `.docx` generado debe aportar al Markdown."""

SENTINEL = "TEPOCHCALLI_BODY_SENTINEL"
"""Marca única del cuerpo grande: su presencia en el wire sería el defecto de `fix01`."""


def _write_docx(path: Path) -> None:
    """Genera un `.docx` real con la stdlib (`zipfile`); markitdown lo lee en proceso."""
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


def _vault(tmp_path: Path) -> Path:
    """Vault mínimo con `00-resources/` y un `staging/` para las fuentes."""
    vault = tmp_path / "vault"
    (vault / "00-resources").mkdir(parents=True)
    (vault / "staging").mkdir()
    return vault


def test_a_real_docx_is_converted_without_frontmatter_and_returns_the_summary(
    tmp_path: Path,
) -> None:
    """`convert_local` (markitdown en proceso) → `.md` sin `converted_at` → 5 claves."""
    vault = _vault(tmp_path)
    _write_docx(vault / "staging" / "informe.docx")

    payload = asyncio.run(
        handler.convert_document(
            "staging/informe.docx",
            vault_root=lambda: vault,
            convert=convert_local,
        )
    )

    assert list(payload) == ["written_to", "source_uri", "bytes", "chars", "preview"]
    written = vault / "00-resources" / "informe.md"
    text = written.read_text(encoding="utf-8")
    assert DOCX_TEXT in text, "markitdown en proceso sobre el documento original"
    assert not text.startswith("---"), "D36: el conversor NO añade frontmatter"
    assert "converted_at" not in text
    assert payload == summary.build_summary(
        written, source_uri="staging/informe.docx", vault_root=vault
    )


def test_the_body_never_crosses_the_wire_for_a_100k_document(tmp_path: Path) -> None:
    """OM-1: documento ≥100 000 chars ⇒ la marca vive en disco y NO en `content[0].text`."""
    vault = _vault(tmp_path)
    body = "# Grande\n\n" + ("a" * 50_000) + SENTINEL + ("b" * 50_000) + "\n"
    (vault / "staging" / "grande.md").write_text(body, encoding="utf-8")
    assert len(body) >= 100_000

    async def call() -> tuple[object, dict[str, object]]:
        async with running_server(server_env(vault)) as session:
            result = await session.call_tool(
                "convert_document",
                {"path": "staging/grande.md", "output_path": "00-resources/grande.md"},
            )
            return result, wire_payload(result)

    result, payload = asyncio.run(call())

    wire_text = result.content[0].text
    assert SENTINEL not in wire_text, "el cuerpo cruzó el wire: defecto de fix01 reproducido"
    assert len(wire_text) <= summary.SUMMARY_CHAR_CEILING, "presupuesto del resumen (M3)"
    assert len(str(payload["preview"])) <= summary.PREVIEW_CHARS
    assert payload["truncated"] is True
    written = vault / "00-resources" / "grande.md"
    assert SENTINEL in written.read_text(encoding="utf-8"), "el cuerpo íntegro está en disco"
    assert json.loads(wire_text)["chars"] >= 100_000
