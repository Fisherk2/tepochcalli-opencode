"""Genera un PDF mínimo a mano (sin dependencias) — fixture T7.

Estructura PDF clásica: header, objetos (catalog, pages, page, 2 fuentes
Type1 base-14, content stream con operadores Tj), xref con offsets reales y
trailer. Título 20pt y secciones 14pt en Helvetica-Bold para que el layout
model de Docling los clasifique como Title/SectionHeader → heading ATX.

La prosa rellena lo justo para que el markdown extraído supere el
presupuesto de chunk (1536 bytes, D11) y produzca VARIOS chunks — así el
test puede afirmar `heading` no nulo en los chunks de sección.

También genera el PDF ADVERSO **con tabla** del presupuesto (T7):
`python gen_fixture_pdf.py tablas_t7.pdf --tabla` — título + heading +
caption "Tabla 1." + rejilla 6×3 con líneas rayadas (`re`/`f`) y celdas de
Helvetica: el caption encima y las reglas laterales son lo que Docling
(TableFormer) necesita para emitir una tabla markdown. `build_table_pdf()`
serializa con el MISMO ensamblador que `build_pdf()` (xref real, latin-1).
"""

from __future__ import annotations

TITLE = "Tepochcalli Fixture Document"
SECTIONS: dict[str, tuple[str, ...]] = {
    "Metodo de prueba": (
        "Este documento PDF de una pagina sirve como fixture real de la ruta "
        "PDF del flow: Docling lo convierte a markdown conservando la "
        "jerarquia de headings, y los offsets de cita se miden sobre ese "
        "markdown extraido, nunca sobre el binario del PDF. La prosa es "
        "deliberadamente simple y continua para producir mas de un chunk de "
        "texto bajo el presupuesto de bytes del splitter canonico.",
        "Segundo apartado: la identidad F1 exige que el slice del markdown "
        "extraido reproduzca exactamente cada chunk citado, por lo que este "
        "bloque de prosa permite verificar solapes y cortes entre chunks de "
        "un documento con estructura de secciones bien definida.",
    ),
    "Resultados": (
        "Los chunks producidos citan la seccion que los contiene: el heading "
        "se deriva escaneando las lineas ATX previas al offset de inicio de "
        "cada chunk, con el mismo cursor incremental que para Markdown y txt.",
        "Tercer apartado: el parseo corre en CPU sin opciones GPU, dentro del "
        "alcance v1 que solo promete el texto embebido del PDF; el OCR "
        "completo queda fuera de scope y los PDFs grandes se excluyen del "
        "presupuesto del delta.",
    ),
    "Implicaciones": (
        "Cuarto apartado: el markdown extraido es el texto de referencia de "
        "los offsets de cita, por lo que la identidad F1 se cumple sobre la "
        "salida de Docling y no sobre los bytes del archivo PDF. Esta "
        "referencia unica es lo que permite re-parsear el documento en una "
        "backfill y obtener exactamente los mismos chunks citados.",
        "Quinto apartado: la memoizacion del parseo por contenido evita "
        "repetir el coste del layout model sobre un PDF inmutable, de modo "
        "que solo los documentos nuevos o modificados pagan el parseo completo.",
    ),
}


def _escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _text_op(font: str, size: int, x: int, y: int, text: str) -> str:
    return f"BT /{font} {size} Tf {x} {y} Td ({_escape(text)}) Tj ET\n"


def _wrap(text: str, width: int = 78) -> list[str]:
    """Parta en líneas en bordes de palabra: cortar a media palabra ensucia el merge de Docling."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".lstrip()
    if current:
        lines.append(current)
    return lines


def _build_content() -> str:
    stream = _text_op("F1", 20, 54, 720, TITLE)
    stream += _text_op(
        "F2", 11, 54, 694, "Documento de prueba para la ruta PDF con Docling en CPU."
    )
    y = 660
    for heading, paragraphs in SECTIONS.items():
        stream += _text_op("F1", 14, 54, y, heading)
        y -= 24
        for paragraph in paragraphs:
            for line in _wrap(paragraph):
                stream += _text_op("F2", 11, 54, y, line)
                y -= 16
            y -= 10
        y -= 14
    return stream


TABLE_TITLE = "Tepochcalli Tabla Fixture"
"""Título del PDF adverso con tabla (fixture de presupuesto T7)."""

TABLE_HEADING = "Presupuestos de latencia"
"""Heading de sección del PDF con tabla."""

TABLE_CAPTION = "Tabla 1. Presupuestos por etapa de la busqueda en milisegundos."
"""Caption INMEDIATAMENTE ENCIMA de la rejilla — el ancla de caption-matching de TableFormer."""

TABLE_ROWS: tuple[tuple[str, str, str, str], ...] = (
    ("Etapa", "Presupuesto", "Medido", "Nota"),
    ("Embed p50", "120 ms", "directo", "MiniLM"),
    ("Embed p95", "120 ms", "directo", "frio+cpu"),
    ("Embed max", "120 ms", "directo", "1 frase"),
    ("ANN+FTS p50", "200 ms", "hibrido", "RRF K=60"),
    ("ANN+FTS p95", "200 ms", "hibrido", "prefiltro"),
    ("ANN+FTS max", "200 ms", "hibrido", "100k filas"),
    ("JSON p50", "30 ms", "serial", "ensamblado"),
    ("JSON p95", "30 ms", "serial", "truncado"),
    ("JSON max", "30 ms", "serial", "ensure_ascii"),
    ("IPC p50", "150 ms", "stdio", "por llamada"),
    ("IPC p95", "150 ms", "stdio", "margen"),
    ("Total", "500 ms", "criterio 3", "p95 < 500"),
)
"""13 filas × 4 columnas — la rejilla que Docling debe detectar como tabla markdown.

Celdas ≤18 caracteres (11pt Helvetica ≈ 6 px/char en columnas de 126 px) para
que la tabla quepa en la página y el markdown emitido supere el presupuesto de
chunk (≥2 chunks cercanos a 1536 bytes — el fixture PDF también ejerce el tope
D11, no solo el fixture `.md` denso).
"""

TABLE_TOP = 610.0
"""Y superior de la rejilla (punto de anclaje de las líneas y de la primera fila)."""

TABLE_ROW_H = 22.0
"""Alto de fila en puntos."""

TABLE_COLS = (54.0, 180.0, 306.0, 432.0, 558.0)
"""Bordes de las 4 columnas: x0 (borde izq.), x1, x2, x3, x4 (borde der.)."""


def _build_table_content() -> str:
    """Construye el contenido de la página con título, heading, caption y rejilla RAYADA.

    Las líneas de la rejilla (`re` + `f`, negro) son lo que el layout model de
    Docling y TableFormer usan para detectar la tabla en modo *ruling lines*;
    el caption encima cubre el modo *caption match*. Celdas con prosa corta en
    Helvetica (F1 bold en la cabecera, F2 en el cuerpo).
    """
    stream = _text_op("F1", 20, 54, 720, TABLE_TITLE)
    stream += _text_op(
        "F2", 11, 54, 694, "PDF adverso del presupuesto: una tabla rejillada de trece filas."
    )
    stream += _text_op("F1", 14, 54, 648, TABLE_HEADING)
    stream += _text_op("F2", 11, 54, 626, TABLE_CAPTION)

    bottom = TABLE_TOP - TABLE_ROW_H * len(TABLE_ROWS)
    stream += "0 0 0 rg\n"
    for row in range(len(TABLE_ROWS) + 1):  # 7 líneas horizontales (borde superior + filas)
        y = TABLE_TOP - TABLE_ROW_H * row
        stream += f"54 {y - 1:.0f} 504 1 re f\n"
    for x in TABLE_COLS:  # 4 líneas verticales (bordes de columna)
        stream += f"{x:.0f} {bottom:.0f} 1 {TABLE_TOP - bottom:.0f} re f\n"
    for index, cells in enumerate(TABLE_ROWS):
        baseline = TABLE_TOP - TABLE_ROW_H * index - 15
        for column, text in enumerate(cells):
            font = "F1" if index == 0 else "F2"
            stream += _text_op(font, 11, TABLE_COLS[column] + 6, baseline, text)
    return stream


def _serialize(objects: list[bytes]) -> bytes:
    """Ensambla objetos numerados 1..N con tabla xref real, trailer y EOF."""
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_offset = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n"
    ).encode()
    return bytes(out)


def _assemble_pdf(content: str) -> bytes:
    """Serializa el content stream a un PDF de 1 página con xref real (latin-1)."""
    encoded = content.encode("latin-1")
    return _serialize(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
            b"/Encoding /WinAnsiEncoding >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Length "
            + str(len(encoded)).encode()
            + b" >>\nstream\n"
            + encoded
            + b"\nendstream",
        ]
    )


def _build_page_content(page: int, total: int) -> str:
    """Página numerada que repite las secciones con una marca de página en el texto."""
    stream = _text_op("F1", 20, 54, 720, TITLE)
    stream += _text_op("F2", 11, 54, 694, f"Documento de {total} paginas: pagina {page}.")
    y = 660
    for heading, paragraphs in SECTIONS.items():
        stream += _text_op("F1", 14, 54, y, heading)
        y -= 24
        for paragraph in paragraphs:
            for line in _wrap(paragraph):
                stream += _text_op("F2", 11, 54, y, line)
                y -= 16
            y -= 10
        y -= 14
    stream += _text_op("F2", 11, 54, 60, f"Fin de la pagina {page} de {total}.")
    return stream


def _assemble_multipage(contents: list[str]) -> bytes:
    """Ensambla N páginas: catálogo, árbol de páginas, 2 fuentes y un par page/content por hoja."""
    kids = " ".join(f"{5 + 2 * i} 0 R" for i in range(len(contents)))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(contents)} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    for index, content in enumerate(contents):
        encoded = content.encode("latin-1")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
            f"/Contents {6 + 2 * index} 0 R >>".encode()
        )
        objects.append(
            b"<< /Length "
            + str(len(encoded)).encode()
            + b" >>\nstream\n"
            + encoded
            + b"\nendstream"
        )
    return _serialize(objects)


def build_pdf() -> bytes:
    """Genera el PDF de fixture (prosa, 1 página) en bytes, listo para escribir."""
    return _assemble_pdf(_build_content())


def build_table_pdf() -> bytes:
    """Genera el PDF ADVERSO con tabla rejilla (fixture `tablas_t7.pdf` de T7)."""
    return _assemble_pdf(_build_table_content())


def build_multipage_pdf(pages: int) -> bytes:
    """Genera un PDF válido de `pages` páginas con texto extraíble (bench de documentos).

    On-demand, nunca fixture de CI: `bench_documents.py` lo usa para el caso de
    30 páginas de TD-2. `build_pdf()` (1 página) queda intacto byte a byte.
    """
    if pages < 1:
        raise ValueError(f"pages debe ser >= 1, no {pages}")
    return _assemble_multipage([_build_page_content(i, pages) for i in range(1, pages + 1)])


if __name__ == "__main__":
    import sys

    destino = sys.argv[1] if len(sys.argv) > 1 else "fixture.pdf"
    pages = 1
    if "--pages" in sys.argv:
        pages = int(sys.argv[sys.argv.index("--pages") + 1])
    if "--tabla" in sys.argv:
        pdf = build_table_pdf()
    else:
        pdf = build_pdf() if pages == 1 else build_multipage_pdf(pages)
    with open(destino, "wb") as handle:
        handle.write(pdf)
    print(f"{destino}: {len(pdf)} bytes")
