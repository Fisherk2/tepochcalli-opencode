"""T10 integración: un `.docx` en base64 produce el MISMO `.md` que `convert_document`.

Fuentes de verdad:

* tasks/todo.md T10 — integration con un `.docx` real en base64 ⇒ `.md`
  equivalente al de T9 (mismo texto; mismo resumen salvo `source_uri`/
  `written_to`).
* docs/adr/adr-009-conversor-resumen-sin-cuerpo.md §D38 (pista de tipo) y §D36
  (mismo resumen de 5 claves).

El `.docx` se genera con `zipfile` de la stdlib (igual que
`tests/integration/test_documents.py`): sin binarios ni dependencias nuevas.
`convert_document` se ejecuta con `convert_local` (path) y `convert_base64` con
`convert_bytes` (`BytesIO` + `StreamInfo`): la equivalencia prueba que la pista
de tipo elige el MISMO extractor que la extensión del fichero.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import zipfile
from pathlib import Path

from tepochcalli_mcp.convert import convert_bytes, convert_local
from tepochcalli_mcp.tools import convert_base64 as base64_handler
from tepochcalli_mcp.tools import convert_document as document_handler

DOCX_TEXT = "Cuerpo del informe docx con texto citable."
"""Texto reconocible que el `.docx` generado debe aportar al Markdown."""


def _docx_bytes() -> bytes:
    """Genera un `.docx` real en memoria con la stdlib (`zipfile`)."""
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
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def _vault(tmp_path: Path) -> Path:
    """Vault mínimo con `00-resources/` y un `staging/` para el documento original."""
    vault = tmp_path / "vault"
    (vault / "00-resources").mkdir(parents=True)
    (vault / "staging").mkdir()
    return vault


def test_base64_bytes_produce_the_same_markdown_as_the_document_path(tmp_path: Path) -> None:
    """Bytes en base64 y fichero en disco ⇒ mismo texto y mismo resumen (salvo rutas)."""
    vault = _vault(tmp_path)
    original = vault / "staging" / "informe.docx"
    original.write_bytes(_docx_bytes())

    from_bytes = asyncio.run(
        base64_handler.convert_base64(
            base64.b64encode(original.read_bytes()).decode("ascii"),
            filename="informe.docx",
            vault_root=lambda: vault,
            convert=convert_bytes,
        )
    )
    from_path = asyncio.run(
        document_handler.convert_document(
            "staging/informe.docx",
            "00-resources/desde-ruta.md",
            vault_root=lambda: vault,
            convert=convert_local,
        )
    )

    text = (vault / "00-resources" / "informe.md").read_text(encoding="utf-8")
    assert text == (vault / "00-resources" / "desde-ruta.md").read_text(encoding="utf-8")
    assert DOCX_TEXT in text, "markitdown en proceso sobre los bytes en contexto"
    assert not text.startswith("---"), "D36: el conversor NO añade frontmatter"

    assert from_bytes["written_to"] == "00-resources/informe.md"
    assert from_bytes["source_uri"] == "informe.docx"
    assert from_path["source_uri"] == "staging/informe.docx"
    ignorable = {"written_to", "source_uri"}
    assert {k: v for k, v in from_bytes.items() if k not in ignorable} == {
        k: v for k, v in from_path.items() if k not in ignorable
    }, "mismo resumen salvo las dos rutas (T10 integration)"


def test_without_filename_the_destination_and_source_uri_use_the_sha_prefix(
    tmp_path: Path,
) -> None:
    """Sin `filename`: `format` elige el extractor y `base64:<sha256-8>` identifica la entrada."""
    vault = _vault(tmp_path)
    raw = _docx_bytes()
    digest = hashlib.sha256(raw).hexdigest()[:8]

    payload = asyncio.run(
        base64_handler.convert_base64(
            base64.b64encode(raw).decode("ascii"),
            format="docx",
            vault_root=lambda: vault,
            convert=convert_bytes,
        )
    )

    assert payload["source_uri"] == f"base64:{digest}"
    assert payload["written_to"] == f"00-resources/base64-{digest}.docx"
    assert DOCX_TEXT in (vault / "00-resources" / f"base64-{digest}.docx").read_text(
        encoding="utf-8"
    )
