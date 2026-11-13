"""T12 (c) — test transversal: NINGUNA de las 7 tools devuelve el cuerpo convertido.

El defecto que cierra Phase 3.5 (`fix01`, ADR-009) era devolver el markdown
completo por el wire; saturaba la ventana del agente. Este test es el único que
recorre las SIETE tools en una sola sesión con un cuerpo que lleva una marca
única y afirma que la marca no aparece en NINGUNA respuesta.

Diseño:

* Documento de ≥100 000 caracteres con `MARKER` en el centro (fuera del
  `preview` de 500: si apareciera, sería porque el cuerpo cruzó el wire, no
  porque el preview lo mostrara legítimamente).
* Se convierte con `convert_document` y con `convert_base64` a `salida/`, una
  carpeta que NO es raíz del índice (`index_refresh` solo indexa
  `00-resources/`). Así la marca vive en disco y jamás es material indexable:
  `search` no puede devolverla por diseño.
* Después se invocan las 7 tools (las dos conversiones, `index_refresh`,
  `search`, `add_source`, `rag_status`, `list_formats`) y se afirma que la marca
  no está en `content[0].text` de ninguna.

Debe FALLAR si alguien devuelve el markdown: comprobado rompiendo el handler a
propósito y revirtiendo (ver el reporte de T12).
"""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path

from support.mcp_server import running_server, server_env, warm_model, wire_payload

MARKER = "TEPOCHCALLI_TRANSVERSAL_BODY_SENTINEL"
"""Marca única del cuerpo: su presencia en el wire reproduce el defecto `fix01`."""

NOTA = "# Nota\n\nLa geografía del altiplano condiciona el calendario agrícola.\n"
PEQUENO = "# Pequeño\n\nMaterial mínimo para add_source.\n"


def _big_body() -> str:
    """Cuerpo ≥100 000 chars con la marca en el centro (nunca dentro del preview)."""
    return "# Grande\n\n" + ("a" * 50_000) + MARKER + ("b" * 50_000) + "\n"


def test_no_tool_returns_the_converted_body_across_the_seven_tools(tmp_path: Path) -> None:
    """Recorre las 7 tools: la marca está en disco y en NINGUNA respuesta del wire."""
    vault = tmp_path / "vault"
    (vault / "00-resources").mkdir(parents=True)
    (vault / "staging").mkdir()
    (vault / "salida").mkdir()
    (vault / "00-resources" / "nota.md").write_text(NOTA, encoding="utf-8")
    (vault / "staging" / "pequeno.md").write_text(PEQUENO, encoding="utf-8")
    body = _big_body()
    assert len(body) >= 100_000
    (vault / "staging" / "grande.md").write_text(body, encoding="utf-8")

    models_link = warm_model(vault)
    env = server_env(vault, models_link)
    data = base64.b64encode(body.encode("utf-8")).decode("ascii")

    async def journey() -> dict[str, object]:
        payloads: dict[str, object] = {}
        async with running_server(env) as session:
            results = {
                "convert_document": await session.call_tool(
                    "convert_document",
                    {"path": "staging/grande.md", "output_path": "salida/doc.md"},
                ),
                "convert_base64": await session.call_tool(
                    "convert_base64",
                    {"data": data, "format": "md", "output_path": "salida/b64.md"},
                ),
                "index_refresh": await session.call_tool("index_refresh", {}),
                "search": await session.call_tool("search", {"query": "geografía del altiplano"}),
                "add_source": await session.call_tool(
                    "add_source", {"uri": (vault / "staging" / "pequeno.md").as_uri()}
                ),
                "rag_status": await session.call_tool("rag_status", {}),
                "list_formats": await session.call_tool("list_formats", {}),
            }
            for name, result in results.items():
                assert not result.is_error, f"{name}: {result.content[0].text}"
                # wire_payload exige JSON canónico y structured_content None.
                payloads[name] = wire_payload(result)
        return payloads

    payloads = asyncio.run(journey())

    # La conversión ocurrió de verdad: la marca está en los dos ficheros escritos.
    assert MARKER in (vault / "salida" / "doc.md").read_text(encoding="utf-8")
    assert MARKER in (vault / "salida" / "b64.md").read_text(encoding="utf-8")

    # El corpus indexado responde (el test no es vacuo) y NO contiene la marca.
    results = payloads["search"]["results"]
    assert isinstance(results, list) and results, "search debe devolver el corpus indexado"
    assert all(MARKER not in str(item["text"]) for item in results)

    # Transversal: ninguna de las 7 respuestas serializadas contiene la marca.
    for name, payload in payloads.items():
        assert MARKER not in str(payload), f"{name} devolvió el cuerpo por el wire"
