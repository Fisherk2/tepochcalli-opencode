"""T11 integración (AC d): cada extensión publicada llega a una conversión REAL.

Fuentes de verdad:

* tasks/todo.md T11 AC (d) — el test itera el catálogo de `list_formats` y
  convierte un fixture por extensión; lo que no tenga fixture queda declarado
  en `BEST_EFFORT`, nunca omitido en silencio.
* specs/spec-markitdown.md §Catálogo — 13 extensiones contra `markitdown==0.1.9`;
  §Risks exige atar el catálogo a la instalación (si el paquete deja de
  convertir una extensión, este test se pone rojo).

Los fixtures se generan en el test: `.docx` con `zipfile` (stdlib), `.xlsx` con
`openpyxl` y `.pptx` con `python-pptx` (extras de markitdown ya instalados), el
resto es texto plano y el PDF es el fixture del repo. Sin binarios nuevos.

**`.xls` es best-effort declarado:** generar un BIFF real necesita `xlwt`, que no
está instalado (ni en la stdlib); se declara aquí, no se salta en silencio.
"""

from __future__ import annotations

import json
import shutil
import zipfile
from collections.abc import Callable
from pathlib import Path

from openpyxl import Workbook
from pptx import Presentation
from pptx.util import Inches
from tepochcalli_mcp import formats
from tepochcalli_mcp.convert import convert_local
from tepochcalli_mcp.tools import list_formats as list_formats_handler

FIXTURE_PDF = Path(__file__).parents[1] / "fixtures" / "pdf" / "articulo_t7.pdf"
"""PDF real de 1 página, con texto extraíble (fixture compartido con T3)."""

MARKER = "MarcaUnicaT11"
"""Texto que el fixture aporta y que el Markdown convertido debe contener."""

BEST_EFFORT = {".xls": "sin generador de BIFF en la stdlib ni extra instalado (xlwt)"}
"""Extensiones publicadas sin fixture: declaradas, contadas y nunca omitidas."""


def _pdf(path: Path) -> str:
    """Copia el fixture PDF del repo; markitdown extrae su título."""
    shutil.copy(FIXTURE_PDF, path)
    return "Tepochcalli Fixture Document"


def _docx(path: Path) -> str:
    """`.docx` real con `zipfile`: el extra de markitdown solo lee, no escribe."""
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
        f"<w:body><w:p><w:r><w:t>{MARKER}</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document)
    return MARKER


def _pptx(path: Path) -> str:
    """`.pptx` real con `python-pptx` (una diapositiva con un cuadro de texto)."""
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])  # en blanco
    slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1)).text_frame.text = MARKER
    presentation.save(path)
    return MARKER


def _xlsx(path: Path) -> str:
    """`.xlsx` real con `openpyxl` (una celda con la marca)."""
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append([MARKER])
    workbook.save(path)
    return MARKER


def _text(markup: str) -> Callable[[Path], str]:
    """Fixture de texto plano: `markup` es lo que se escribe, con `{marker}` sustituido."""

    def write(path: Path) -> str:
        path.write_text(markup.replace("{marker}", MARKER), encoding="utf-8")
        return MARKER

    return write


_BUILDERS: dict[str, Callable[[Path], str]] = {
    ".pdf": _pdf,
    ".docx": _docx,
    ".pptx": _pptx,
    ".xlsx": _xlsx,
    ".html": _text("<html><body><h1>{marker}</h1></body></html>"),
    ".htm": _text("<html><body><h1>{marker}</h1></body></html>"),
    ".csv": _text("nombre,valor\n{marker},42\n"),
    ".txt": _text("{marker}\n"),
    ".md": _text("# {marker}\n"),
    ".markdown": _text("# {marker}\n"),
    ".json": _text(json.dumps({"clave": "{marker}"})),
    ".jsonl": _text(json.dumps({"clave": "{marker}"}) + "\n"),
}
"""Fixture por extensión publicada; `.xls` vive en `BEST_EFFORT` con su motivo."""


def test_every_published_extension_reaches_a_real_conversion(tmp_path: Path) -> None:
    """Itera lo que la tool PUBLICA: cada extensión produce Markdown con su marca (AC d)."""
    published = list_formats_handler.list_formats()["formats"]
    assert isinstance(published, list) and published == list(formats.SUPPORTED_FORMATS)

    converted: set[str] = set()
    for extension in published:
        build = _BUILDERS.get(extension)
        if build is None:
            assert extension in BEST_EFFORT, f"{extension} sin fixture y sin declarar best-effort"
            continue
        source = tmp_path / f"fixture{extension}"
        marker = build(source)
        markdown = convert_local(source, source_uri=f"staging/fixture{extension}")
        assert marker in markdown, f"markitdown no convierte {extension}: {markdown[:120]!r}"
        converted.add(extension)

    assert sorted(set(published) - converted) == sorted(BEST_EFFORT), (
        "lo no convertido debe ser exactamente lo declarado best-effort"
    )
