"""Generador multi-página del bench T2: 30 páginas con xref REAL y texto extraíble."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

TESTS_DIR = Path(__file__).resolve().parents[1]
GEN_PATH = TESTS_DIR / "fixtures" / "pdf" / "gen_fixture_pdf.py"


def _generator() -> ModuleType:
    """Carga el generador por ruta (no es un paquete; mismo patrón que el e2e bulk)."""
    spec = importlib.util.spec_from_file_location("gen_fixture_pdf_t2", GEN_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_multipage_pdf_xref_resolves_and_text_is_present() -> None:
    """El PDF de 30 páginas no es un dummy: cada offset del xref apunta a su objeto."""
    pdf = _generator().build_multipage_pdf(30)

    assert pdf.startswith(b"%PDF-1.4")
    assert b"/Count 30" in pdf
    assert pdf.count(b"/Type /Page ") == 30

    startxref = re.search(rb"startxref\n(\d+)\n%%EOF\n$", pdf)
    assert startxref is not None, "falta startxref/%%EOF al final"
    xref_start = int(startxref.group(1))
    assert pdf[xref_start : xref_start + 4] == b"xref"

    lines = pdf[xref_start:].split(b"\n")
    size = int(lines[1].split()[1])
    offsets = [int(line.split()[0]) for line in lines[3 : 3 + size - 1]]
    assert len(offsets) == size - 1 == 4 + 2 * 30
    for number, offset in enumerate(offsets, start=1):
        assert pdf[offset:].startswith(f"{number} 0 obj\n".encode())

    assert b"(Fin de la pagina 30 de 30.) Tj" in pdf
