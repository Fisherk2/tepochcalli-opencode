"""T8 e2e: «pregunta → tool-call → JSON citado» sobre el vault golden GRABADO (plan §6).

Fuentes de verdad: tasks/todo.md → T8 AC (e2e real + fixture grabado + CP-D);
tasks/plan.md §6 T8; specs/spec-mcp-server.md §search (`source_path` real,
`heading`, `offsets_ref`) y §Testing «Golden answers» (md + PDF con offsets
reproducibles).

Decisiones de test, documentadas a propósito:

* **Fixture golden GRABADO en `tests/fixtures/golden_vault/`** (nota md +
  transcripción txt + PDF): los ficheros viven en el repo y NO se regeneran en
  cada corrida — la prueba solo los COPIA a un tmp y los indexa (el índice sí
  es por corrida, en SUBPROCESO con `index_vault`, patrón T2/T7: el
  environment global de cocoindex no admite dos vaults en el mismo proceso,
  sonda T9).
* **Un solo test = UNA sesión stdio = un viaje completo**: el proceso
  `python -m tepochcalli_mcp` responde `index_refresh` (idempotente sobre el
  índice del fixture), luego las dos preguntas — el estado y el modelo
  cargado viven ENTRE llamadas, como los ve el harness en producción.
* **Cierra el punto 2 heredado de CP-B**: el corte DIRECTO «slice del
  original reproduce `text`» partiendo de un resultado de `search` por el
  WIRE (md y txt) — lo que CP-B aprobó heredado y encargó a T8 — más
  `offsets_ref == "extract"` y `heading` nulo en el PDF (los offsets citan el
  texto extraído por markitdown, nunca el binario: D50/D54). El golden cubre
  los TRES espacios de cita del contrato: md y txt (`source`) + pdf (`extract`).
* **Cero red y cero LLM**: el hijo corre con el canario `nonet` y
  `HF_HUB_OFFLINE=1`; la única ventana sin canario es el indexado del
  fixture en su subproceso (donde en frío se permite la descarga que el
  resto de la suite persiste). Cualquier dial durante el viaje rompería el
  refresh y el test fallaría solo (auto-exigente).
* **Sin aserciones de reloj**: las cuentas del reporte y las formas son
  deterministas; aquí NO se mide latencia (regla anti-flake T3 — el p95 vive
  en `tests/benchmarks/bench_search.py`).
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest
from support.mcp_server import (
    REFRESH_FIELDS,
    SEARCH_RESULT_FIELDS,
    SEARCH_TOP_LEVEL_FIELDS,
    index_vault,
    running_server,
    server_env,
    wire_payload,
)

GOLDEN_VAULT = Path(__file__).parents[1] / "fixtures" / "golden_vault"
"""Vault golden GRABADO (md + PDF) — se copia a tmp, jamás se regenera en la corrida."""

GOLDEN_MD = "00-Resources/nota_dorada.md"
GOLDEN_TXT = "00-Resources/transcripcion_dorada.txt"
GOLDEN_PDF = "00-Resources/articulo_dorado.pdf"

MD_QUERY = "espectrómetro de partículas y reducción de datos"
"""Pregunta sobre el md golden — vocabulario real de `nota_dorada.md`."""

TXT_QUERY = "brújula de inclinación y rumbo magnético"
"""Pregunta sobre el txt golden — prosa continua sin headings (D13: `heading` nulo)."""

PDF_QUERY = "metodo de prueba y resultados del parseo con Docling"
"""Pregunta sobre el PDF golden — vocabulario de sus secciones extraídas."""


def test_journey_from_question_to_cited_json_over_the_stdio_process(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """e2e T8: proceso real por stdio → ciclo Δ → pregunta → JSON citado reproducible.

    Cada resultado trae `source_path` real (el fichero EXISTE en el vault
    golden), `heading` derivado en md y offsets reproducibles: en md el slice
    del archivo original reproduce `text` byte a byte; en el PDF
    `offsets_ref == "extract"` y `heading` nulo (D54; AC de T3).
    """
    vault = tmp_path_factory.mktemp("vault-t8-golden")
    shutil.copytree(GOLDEN_VAULT, vault, dirs_exist_ok=True)
    models_link = index_vault(vault)  # md + PDF indexados en subproceso (ventana sin canario)
    env = server_env(vault, models_link)

    async def journey() -> tuple[dict, dict, dict, dict]:
        async with running_server(env) as session:
            refresh_result = await session.call_tool("index_refresh", {})
            refresh = wire_payload(refresh_result)
            md_result = await session.call_tool(
                "search", {"query": MD_QUERY, "path_filter": GOLDEN_MD}
            )
            md = wire_payload(md_result)
            txt_result = await session.call_tool(
                "search", {"query": TXT_QUERY, "path_filter": GOLDEN_TXT}
            )
            txt = wire_payload(txt_result)
            pdf_result = await session.call_tool(
                "search", {"query": PDF_QUERY, "path_filter": GOLDEN_PDF}
            )
            pdf = wire_payload(pdf_result)
            # Los cuatro pasos del viaje son de éxito: un error aquí es texto de diagnóstico.
            assert not refresh_result.is_error, refresh
            assert not md_result.is_error, md
            assert not txt_result.is_error, txt
            assert not pdf_result.is_error, pdf
            return refresh, md, txt, pdf

    refresh, md, txt, pdf = asyncio.run(journey())

    # 1) Ciclo Δ a través de la tool: idempotente sobre el índice del fixture.
    #    Exactamente los 3 indexables del golden (md + txt + PDF); el PDF cuenta en
    #    scanned — F-T7-2 cerrado, ahora por stdio.
    assert list(refresh) == REFRESH_FIELDS
    assert (refresh["scanned"], refresh["indexed"], refresh["skipped"]) == (3, 0, 3), (
        "el golden tiene exactamente 3 indexables ya memoizados: nada que reescribir"
    )
    assert refresh["locked"] is False

    # 2) md: source_path real + heading + el SLICE DEL ORIGINAL reproduce `text` (CP-B #2).
    assert list(md) == SEARCH_TOP_LEVEL_FIELDS
    md_results = md["results"]
    assert md_results, "la pregunta md debe devolver citas del golden"
    for item in md_results:
        assert list(item) == SEARCH_RESULT_FIELDS
        source = vault / str(item["source_path"])
        assert source.is_file(), f"source_path real ausente: {item['source_path']}"
        original = source.read_text(encoding="utf-8")
        assert original[int(item["char_start"]) : int(item["char_end"])] == item["text"], (
            f"identidad F1 rota en [{item['char_start']}, {item['char_end']}) "
            f"de {item['source_path']}"
        )
        assert item["offsets_ref"] == "source", "md: los offsets citan el archivo original"
    assert any(item["heading"] is not None for item in md_results), (
        "algún chunk md debe citar su heading ATX (D13: heading nullable, no anulado)"
    )

    # 2b) txt: source_path real + offsets contra el ORIGINAL + heading NULO (D13).
    assert list(txt) == SEARCH_TOP_LEVEL_FIELDS
    txt_results = txt["results"]
    assert txt_results, "la pregunta txt debe devolver citas del golden"
    for item in txt_results:
        assert list(item) == SEARCH_RESULT_FIELDS
        assert (vault / str(item["source_path"])).is_file(), item["source_path"]
        assert item["source_path"] == GOLDEN_TXT, "el path_filter acota la cita al txt"
        original = (vault / str(item["source_path"])).read_text(encoding="utf-8")
        assert original[int(item["char_start"]) : int(item["char_end"])] == item["text"], (
            f"identidad F1 rota en [{item['char_start']}, {item['char_end']}) de {GOLDEN_TXT}"
        )
        assert item["offsets_ref"] == "source", "txt: los offsets citan el archivo original"
        assert item["heading"] is None, (
            "D13: prosa sin headings ATX ⇒ `heading` nulo (nunca una cadena vacía)"
        )

    # 3) PDF: source_path real + heading NULO (D54) + offsets_ref == "extract".
    #    La AUSENCIA de heading es el contrato, no un fallo: el golden NO lo exige.
    assert list(pdf) == SEARCH_TOP_LEVEL_FIELDS
    pdf_results = pdf["results"]
    assert pdf_results, "la pregunta pdf debe devolver citas del golden"
    for item in pdf_results:
        assert list(item) == SEARCH_RESULT_FIELDS
        assert (vault / str(item["source_path"])).is_file(), item["source_path"]
        assert item["offsets_ref"] == "extract", (
            "el PDF cita el texto extraído por markitdown, jamás el binario (D50)"
        )
        assert item["heading"] is None, (
            "D54: markitdown no conserva headings; el PDF no inventa uno"
        )
