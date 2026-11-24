"""T14: el verificador de la corrida D9 nace sabiendo fallar (patrón TDD).

Ejecuta el script standalone `verify_methodology_evidence.py` contra la evidencia
sintética de `tests/fixtures/methodology_evidence/`: verde en `good/` y exit != 0
en cada defecto, con el punto (a)-(d) que corresponda nombrado en la salida.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("verify_methodology_evidence.py")
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "methodology_evidence"


def _run(case: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(FIXTURES / case)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_methodology_good_evidence_exits_zero() -> None:
    """La evidencia bien formada pasa los cuatro puntos con exit 0."""
    proc = _run("good")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PASS (a)" in proc.stdout
    assert "PASS (b)" in proc.stdout
    assert "PASS (c)" in proc.stdout
    assert "PASS (d)" in proc.stdout


@pytest.mark.parametrize(
    ("case", "point", "name"),
    [
        ("bad-tray", "(a)", "02-drafts/rubric.md"),
        ("bad-frontmatter", "(b)", "style"),
        ("bad-transcript", "(c)", "07-review-transcript.txt"),
        ("bad-mcp-first", "(d)", "00-resources/fotosintesis.md"),
    ],
)
def test_methodology_defect_exits_nonzero(case: str, point: str, name: str) -> None:
    """Cada defecto sintético pone el verificador en rojo por su punto."""
    proc = _run(case)
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert f"FAIL {point}" in proc.stdout, proc.stdout
    assert name in proc.stdout, proc.stdout
