"""T7 (Phase 6): `verify.py --spot-check N` — la cita se re-verifica contra el archivo VIVO.

Fuentes de verdad: `tasks/plan.md` §Task T7 · `docs/TECH_DEBT.md` TD-13 ·
`specs/spec-mcp-server.md` §`search` (`offsets_ref`) · `specs/spec-rag-engine.md` §cita.

Decisiones de test, documentadas a propósito:

* **El vault se COPIA del golden grabado y se indexa UNA vez en subproceso**
  (`index_vault`, patrón T8/T9: el environment de cocoindex no admite dos
  vaults en el mismo proceso). Cada test trabaja sobre una copia propia —con
  su `db/`— para poder editar/borrar archivos sin contaminar a los demás.
* **El par que exige el AC vive en un solo test:** sin edición ⇒ exit 0;
  edición posterior a la indexación ⇒ exit 1. Un `--spot-check` que nunca
  falla no demuestra nada.
* **Solo lectura:** snapshot `(mtime_ns, size)` de `db/` antes/después de cada
  corrida ⇒ 0 cambios (patrón de T9/`test_read_port`).
* **`offsets_ref` no se mezcla:** el golden trae md/txt (`source`) y pdf
  (`extract`); la corrida limpia debe afirmar los DOS espacios de
  coordenadas. El PDF se re-extrae con markitdown, nunca se corte el binario.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from support.mcp_server import index_vault

GOLDEN_VAULT = Path(__file__).parents[1] / "fixtures" / "golden_vault"
"""Vault golden GRABADO (md + txt + pdf) — se copia, jamás se regenera."""

GOLDEN_MD = "00-Resources/nota_dorada.md"
GOLDEN_TXT = "00-Resources/transcripcion_dorada.txt"
GOLDEN_PDF = "00-Resources/articulo_dorado.pdf"

SPOT_SAMPLE = 100
"""Pide más filas que las indexadas: el muestreo cubre TODOS los chunks del golden."""

EVIDENCE_ENV = "TEPOCHCALLI_CITATIONS_EVIDENCE"
"""Ruta del JSON de evidencia; ausente ⇒ el test solo afirma (no escribe nada)."""


@dataclass(frozen=True)
class IndexedGolden:
    """Vault golden ya indexado (una sola vez por módulo) y su cache de modelo."""

    vault: Path
    model_cache: Path


@pytest.fixture(scope="module")
def indexed_golden(tmp_path_factory: pytest.TempPathFactory) -> IndexedGolden:
    """Copia el golden y lo indexa en subproceso (md + txt + pdf)."""
    vault = tmp_path_factory.mktemp("vault-t7-golden")
    shutil.copytree(GOLDEN_VAULT, vault, dirs_exist_ok=True)
    return IndexedGolden(vault=vault, model_cache=index_vault(vault))


@pytest.fixture()
def vault_copy(indexed_golden: IndexedGolden, tmp_path: Path) -> Path:
    """Copia por test del vault YA indexado (índice + symlink de modelo incluidos)."""
    copy = tmp_path / "vault"
    shutil.copytree(indexed_golden.vault, copy, symlinks=True)
    return copy


def _spot_check(vault: Path, model_cache: Path) -> subprocess.CompletedProcess[str]:
    """Corre el CLI real (`python -m tepochcalli_flow.verify --spot-check`) sobre `vault`."""
    env = {
        **os.environ,
        "HF_HOME": str(model_cache),
        "SENTENCE_TRANSFORMERS_HOME": str(model_cache),
        "HF_HUB_OFFLINE": "1",
    }
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "tepochcalli_flow.verify",
            str(vault),
            "--spot-check",
            str(SPOT_SAMPLE),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def _snapshot(root: Path) -> dict[str, tuple[int, int | None]]:
    """(mtime_ns, size) por ruta relativa — detecta cualquier escritura o creación."""
    out: dict[str, tuple[int, int | None]] = {}
    for path in sorted(root.rglob("*")):
        out[str(path.relative_to(root))] = (
            path.stat().st_mtime_ns,
            path.stat().st_size if path.is_file() else None,
        )
    return out


def _summarise(proc: subprocess.CompletedProcess[str]) -> dict[str, object]:
    """Resume una corrida del spot-check para la evidencia (cifras, no prosa)."""
    rows = [line for line in proc.stdout.splitlines() if line.startswith("  [")]
    rate = re.search(
        r"Tasa de citas reproducibles: (\d+/\d+ \([\d.]+%\)) — (\d+) rotas", proc.stdout
    )
    return {
        "rows_sampled": len(rows),
        "source_rows": sum("offsets_ref=source" in line for line in rows),
        "extract_rows": sum("offsets_ref=extract" in line for line in rows),
        "rate": rate.group(1) if rate else None,
        "broken": int(rate.group(2)) if rate else None,
        "exit_code": proc.returncode,
    }


def _write_evidence(
    clean: subprocess.CompletedProcess[str], broken: subprocess.CompletedProcess[str]
) -> None:
    """Vuelca las cifras medidas al JSON de evidencia si el env lo pide (AC de T7)."""
    target = os.environ.get(EVIDENCE_ENV)
    if not target:
        return
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "command": f'{EVIDENCE_ENV}="{path}" just python-test-file spot_check',
                "vault": "tests/fixtures/golden_vault (md + txt + pdf)",
                "spot_check_requested": SPOT_SAMPLE,
                "read_only": "snapshot (mtime_ns, size) de db/ sin cambios en las 3 corridas",
                "clean": _summarise(clean),
                "after_external_edit": {
                    "edited_file": GOLDEN_MD,
                    **_summarise(broken),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_spot_check_verifies_every_sampled_row_and_never_writes(
    vault_copy: Path, indexed_golden: IndexedGolden
) -> None:
    """Sin edición: 100 % de las filas reproducibles, ambos `offsets_ref`, `db/` intacto."""
    db_dir = vault_copy / ".tepochcalli" / "db"
    before = _snapshot(db_dir)

    proc = _spot_check(vault_copy, indexed_golden.model_cache)

    assert proc.returncode == 0, (
        f"spot-check falló sobre un golden limpio:\n{proc.stdout}\n{proc.stderr}"
    )
    assert "Spot-check" in proc.stdout
    # Los dos espacios de coordenadas del contrato aparecen y NINGUNO sale roto.
    assert "offsets_ref=source" in proc.stdout, "el md/txt debe citarse contra el original"
    assert "offsets_ref=extract" in proc.stdout, "el pdf debe citarse contra el texto extraído"
    assert "BROKEN" not in proc.stdout and "MISSING" not in proc.stdout, proc.stdout
    assert re.search(r"Tasa de citas reproducibles: (\d+)/\1 \(100\.0%\)", proc.stdout), (
        f"la tasa debe ser 100 % sobre el golden limpio:\n{proc.stdout}"
    )
    # Las tres fuentes del golden están cubiertas por el muestreo.
    for source in (GOLDEN_MD, GOLDEN_TXT, GOLDEN_PDF):
        assert source in proc.stdout, f"{source} no entró en el muestreo:\n{proc.stdout}"

    assert _snapshot(db_dir) == before, (
        "el spot-check modificó .tepochcalli/db/ (¡el verificador solo lee!)"
    )


def test_spot_check_exits_nonzero_when_a_cited_file_changes_after_indexing(
    vault_copy: Path, indexed_golden: IndexedGolden
) -> None:
    """El PAR del AC: exit 0 sin edición → exit 1 tras editar el archivo citado."""
    db_dir = vault_copy / ".tepochcalli" / "db"
    before = _snapshot(db_dir)

    clean = _spot_check(vault_copy, indexed_golden.model_cache)
    assert clean.returncode == 0, f"baseline limpio debe salir 0:\n{clean.stdout}\n{clean.stderr}"

    # Edición EXTERNA posterior a la indexación: los offsets guardados ya no
    # reproducen el texto del archivo. El índice no se toca (TD-4/TD-13).
    edited = vault_copy / GOLDEN_MD
    original = edited.read_text(encoding="utf-8")
    edited.write_text("# Encabezado añadido tras indexar\n\n" + original, encoding="utf-8")

    broken = _spot_check(vault_copy, indexed_golden.model_cache)

    assert broken.returncode == 1, (
        f"una cita que ya no existe en el archivo vivo debe salir ≠ 0:\n{broken.stdout}"
    )
    assert "[BROKEN]" in broken.stdout, broken.stdout
    assert GOLDEN_MD in broken.stdout, "el informe debe nombrar el archivo editado"
    assert re.search(r"Tasa de citas reproducibles: \d+/\d+ \((?!100\.0%)\d", broken.stdout), (
        f"la tasa debe bajar del 100 % y publicarse:\n{broken.stdout}"
    )

    assert _snapshot(db_dir) == before, "el spot-check no debe tocar `db/` ni al detectar roturas"

    _write_evidence(clean, broken)


def test_spot_check_reports_missing_source_as_broken(
    vault_copy: Path, indexed_golden: IndexedGolden
) -> None:
    """Un `source_path` ausente es una cita rota (severidad MISSING), no un crash."""
    (vault_copy / GOLDEN_TXT).unlink()

    proc = _spot_check(vault_copy, indexed_golden.model_cache)

    assert proc.returncode == 1, proc.stdout
    assert f"[MISSING] {GOLDEN_TXT}" in proc.stdout, proc.stdout
    assert "Traceback" not in proc.stderr, proc.stderr
