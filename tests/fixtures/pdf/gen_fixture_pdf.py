"""Genera un PDF mínimo a mano (sin dependencias) — fixture T7.

Estructura PDF clásica: header, objetos (catalog, pages, page, 2 fuentes
Type1 base-14, content stream con operadores Tj), xref con offsets reales y
trailer. Título 20pt y secciones 14pt en Helvetica-Bold para que el layout
model de Docling los clasifique como Title/SectionHeader → heading ATX.

La prosa rellena lo justo para que el markdown extraído supere el
presupuesto de chunk (1536 bytes, D11) y produzca VARIOS chunks — así el
test puede afirmar `heading` no nulo en los chunks de sección.
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


def build_pdf() -> bytes:
    """Genera el PDF de fixture en bytes, listo para escribir."""
    content = _build_content().encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]
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


if __name__ == "__main__":
    import sys

    pdf = build_pdf()
    destino = sys.argv[1] if len(sys.argv) > 1 else "fixture.pdf"
    with open(destino, "wb") as handle:
        handle.write(pdf)
    print(f"{destino}: {len(pdf)} bytes")
