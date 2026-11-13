"""TD-2 opción B (2026-11-12): traza de progreso del refresh — en stderr, no en el contrato.

Fuente de verdad: `docs/acceptance/documents.md` §6 — un libro de 335
páginas tarda **50,6 s solo en extraerse** (108,5 s con indexación) y el
usuario veía silencio; el PDF de 30 páginas (3,14 s) sí cabe en el Δ de 30 s
(D51). La decisión del dueño es **D51 + traza por documento binario**, sin
tocar el contrato MCP (ADR-005).

Tres invariantes, uno por test:

1. `index_refresh` nombra en **stderr** cada documento binario procesado con su
   tiempo de extracción; los `.md` NO generan una línea cada uno (un vault de
   10 000 notas serían 10 000 líneas de ruido).
2. El JSON de respuesta conserva EXACTAMENTE
   `{scanned, indexed, skipped, elapsed_ms, locked, roots}` — cero campos
   nuevos, mismo orden (el shape congelado de `asdict(RefreshReport)`).
3. **stdout queda limpio**: es el canal del JSON-RPC; una línea de log ahí
   rompe el protocolo. Se demuestra con el refresh en subproceso
   (`REFRESH_SCRIPT`), donde stdout se lee byte a byte.

El candado se traza con honestidad: si otro proceso retiene el flock, la traza
lo dice y NO anuncia documentos que no se van a procesar.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from model_cache import link_model_cache, resolve_model_cache
from support.mcp_server import running_server, server_env, warm_model
from tepochcalli_flow import app as flow_app
from tepochcalli_flow import citation

REPORT_FIELDS = ["scanned", "indexed", "skipped", "elapsed_ms", "locked", "roots"]
"""Orden exacto de `asdict(RefreshReport)` — el contrato NO cambia con la traza."""

FIXTURE_PDF = Path(__file__).parents[1] / "fixtures" / "pdf" / "articulo_t7.pdf"
"""PDF real de 1 página (el caso con extractor markitdown, el que tarda)."""

NOTA = "# Nota\n\nProsa markdown: se extrae en microsegundos y no se traza una a una.\n"

REFRESH_SCRIPT = """
import dataclasses, json, logging, sys
logging.basicConfig(stream=sys.stderr, level=logging.INFO)  # igual que __main__.main()
from tepochcalli_flow.app import refresh_blocking
print(json.dumps(dataclasses.asdict(refresh_blocking())), flush=True)
"""
"""Refresh en subproceso con stdout observable: prueba de que el log NO lo toca."""


@pytest.fixture(scope="module")
def model_cache(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Cache del modelo calentado UNA vez (la descarga en frío no es de este test)."""
    warm_model(tmp_path_factory.mktemp("vault-progress-warm"))
    return resolve_model_cache()


def _vault_with_md_and_pdf(root: Path, cache: Path) -> tuple[Path, Path]:
    """Vault mínimo del caso lento: 1 `.md` (sin traza) + 1 `.pdf` (con traza)."""
    resources = root / citation.RESOURCES_DIR
    resources.mkdir(parents=True)
    (resources / "nota.md").write_text(NOTA, encoding="utf-8")
    shutil.copy(FIXTURE_PDF, resources / "ejemplo.pdf")
    return root, link_model_cache(root, cache)


def test_index_refresh_traces_the_pdf_in_stderr_and_keeps_the_json_shape(
    tmp_path: Path, model_cache: Path
) -> None:
    """El PDF se nombra en stderr con su tiempo; el JSON sigue con las 6 claves exactas."""
    vault, models_link = _vault_with_md_and_pdf(tmp_path, model_cache)
    stderr = tempfile.TemporaryFile()

    async def go() -> dict[str, object]:
        async with running_server(server_env(vault, models_link), errlog=stderr) as session:
            result = await session.call_tool("index_refresh", {})
            assert not result.is_error, result.content[0].text
            return json.loads(result.content[0].text)

    try:
        report = asyncio.run(go())
        stderr.seek(0)
        trace = stderr.read().decode("utf-8", "replace")
    finally:
        stderr.close()

    assert list(report) == REPORT_FIELDS, f"la traza no puede añadir campos: {list(report)}"
    assert (report["scanned"], report["indexed"], report["skipped"]) == (2, 2, 0)

    flat = " ".join(trace.split())  # el handler del hijo ajusta líneas: se compara el contenido
    assert "ejemplo.pdf" in flat, f"el documento binario debe nombrarse en stderr:\n{trace}"
    assert re.search(r"documento .*ejemplo\.pdf.*extraído en \d+ ms", flat), (
        # el hueco entre nombre y tiempo es la columna `progress.py:NN` del handler
        f"la traza del documento lleva su tiempo de extracción:\n{trace}"
    )
    assert "nota.md" not in flat, f"los markdown no se trazan uno a uno:\n{trace}"
    assert f"scanned={report['scanned']}" in flat, trace
    assert f"elapsed_ms={report['elapsed_ms']}" in flat, trace


def test_refresh_stdout_carries_only_the_json_report(tmp_path: Path, model_cache: Path) -> None:
    """Solo el JSON del reporte sale por stdout: el log jamás toca el canal del JSON-RPC."""
    vault, models_link = _vault_with_md_and_pdf(tmp_path, model_cache)
    proc = subprocess.run(
        [sys.executable, "-c", REFRESH_SCRIPT],
        env=server_env(vault, models_link),
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr

    stdout_lines = [line for line in proc.stdout.splitlines() if line.strip()]
    assert len(stdout_lines) == 1, f"stdout debe llevar SOLO el JSON del reporte: {stdout_lines}"
    assert list(json.loads(stdout_lines[0])) == REPORT_FIELDS
    assert "ejemplo.pdf" in proc.stderr, f"la traza vive en stderr:\n{proc.stderr}"


def test_locked_refresh_traces_the_lock_and_announces_no_documents(
    tmp_path: Path, model_cache: Path
) -> None:
    """Candado retenido ⇒ la traza lo dice y no finge progreso de documentos."""
    vault, models_link = _vault_with_md_and_pdf(tmp_path, model_cache)
    lock_fd = flow_app._acquire_refresh_lock(vault)
    assert lock_fd is not None, "nadie retenía el candado: el acquire debe triunfar"
    stderr = tempfile.TemporaryFile()

    async def go() -> dict[str, object]:
        async with running_server(server_env(vault, models_link), errlog=stderr) as session:
            result = await session.call_tool("index_refresh", {})
            assert not result.is_error, result.content[0].text
            return json.loads(result.content[0].text)

    try:
        report = asyncio.run(go())
        stderr.seek(0)
        trace = stderr.read().decode("utf-8", "replace")
    finally:
        stderr.close()
        flow_app._release_refresh_lock(lock_fd)

    assert list(report) == REPORT_FIELDS
    assert report["locked"] is True
    assert "candado" in trace.lower(), f"la traza debe declarar el bloqueo:\n{trace}"
    assert "ejemplo.pdf" not in trace, f"sin update no hay documento que anunciar:\n{trace}"
