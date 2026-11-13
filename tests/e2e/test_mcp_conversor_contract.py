"""T12 e2e: forma, presupuesto y negativos del conversor AFIRMADOS EN EL WIRE.

Fuentes de verdad:

* tasks/todo.md → T12 AC (a) — forma y ORDEN de claves de las 3 respuestas
  nuevas, en `content[0].text` (no en el handler).
* tasks/todo.md → T12 AC (b) — respuesta ≤1 400 caracteres serializados,
  `preview` ≤500; el caso CJK documentado.
* tasks/todo.md → T12 AC (d) — negativos: fuera del vault, `..`, raíz
  inexistente (fichero y directorio), tipo equivocado, N raíces con una mala,
  formato no soportado, base64 sin pista, documento sin capa de texto y
  `output_path` ocupado con bytes distintos; TODOS con JSON canónico y NINGUNO
  `INTERNAL` por una ruta mal escrita (OM-15).
* specs/spec-mcp-server.md §Tools del conversor, §index_refresh, §Manejo de
  errores; specs/spec-markitdown.md §Contrato; tasks/plan.md §5.9.

Decisiones de test:

* **Proceso real por stdio** (patrón T8): el contrato se gradúa donde el
  harness lo ve. El conversor no necesita embedder; los negativos de
  `index_refresh` prueban la precedencia del BORDE (validación antes de
  `E_NO_EMBEDDER`), así que el fixture no calienta el modelo.
* **Presupuesto CJK:** `serialize_budget` topa 1 400 CARACTERES serializados,
  y `budget.estimate_tokens` pesa CJK a 1 token/carácter (el `chars/4` de
  ES/EN subestimaría). Con el techo por caracteres, el peor caso CJK queda en
  1 400 + 25 ≈ 1 425 tokens ≤ 1 600: la cota real del resumen es la de
  caracteres, y el estimador confirma que no se cruza la de tokens.
* **Sin aserciones de latencia** (regla anti-flake): la latencia vive en T13.

El `.docx`/`.pdf` de los fixtures se generan/copian en el test: sin binarios
nuevos ni dependencias (patrón T3/T9).
"""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path

import pytest
from support.mcp_server import running_server, server_env, wire_payload
from tepochcalli_mcp import budget, formats, summary

CORTO = "# Corto\n\nDocumento corto con prosa citable.\n"
LARGO = "# Largo\n\n" + ("palabra de relleno para superar el preview. " * 40) + "\n"
CJK = "# 東京\n\n" + ("检索与观测的度量衡，文本以字符计数。🚀 " * 60) + "\n"

BLANK_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
    b"xref\n"
    b"0 4\n"
    b"0000000000 65535 f\x20\n"
    b"0000000009 00000 n\x20\n"
    b"0000000052 00000 n\x20\n"
    b"0000000101 00000 n\x20\n"
    b"trailer<</Size 4/Root 1 0 R>>\n"
    b"startxref\n"
    b"160\n"
    b"%%EOF\n"
)
"""PDF sintético de una página SIN capa de texto (mismo fixture que T3)."""

SUMMARY_FIELDS = ["written_to", "source_uri", "bytes", "chars", "preview"]
"""Orden congelado del resumen de éxito (spec §Tools del conversor / D36)."""


def _vault(tmp_path: Path) -> Path:
    """Vault mínimo con `00-resources/`, `staging/` (fuentes) y `salida/` (destinos)."""
    vault = tmp_path / "vault"
    (vault / "00-resources").mkdir(parents=True)
    (vault / "staging").mkdir()
    (vault / "salida").mkdir()
    (vault / "staging" / "corto.md").write_text(CORTO, encoding="utf-8")
    (vault / "staging" / "largo.md").write_text(LARGO, encoding="utf-8")
    (vault / "staging" / "cjk.md").write_text(CJK, encoding="utf-8")
    (vault / "staging" / "raro.bin").write_text("contenido sin conversor", encoding="utf-8")
    (vault / "staging" / "escaneado.pdf").write_bytes(BLANK_PDF)
    (vault / "salida" / "ocupado.md").write_text("contenido distinto\n", encoding="utf-8")
    return vault


# --- (a) forma exacta de las 3 respuestas nuevas, en el wire ------------------------------


def test_the_three_new_tools_answer_the_frozen_shape_over_the_wire(tmp_path: Path) -> None:
    """5 claves en orden fijo (+`truncated` SOLO al recortar) y `list_formats` con 3 claves."""
    vault = _vault(tmp_path)
    env = server_env(vault)  # el conversor no toca el embedder

    async def journey() -> dict[str, object]:
        payloads: dict[str, object] = {}
        async with running_server(env) as session:
            result = await session.call_tool(
                "convert_document",
                {"path": "staging/corto.md", "output_path": "salida/corto.md"},
            )
            corto = wire_payload(result)
            assert not result.is_error, corto
            assert list(corto) == SUMMARY_FIELDS

            result = await session.call_tool(
                "convert_document",
                {"path": "staging/largo.md", "output_path": "salida/largo.md"},
            )
            largo = wire_payload(result)
            assert not result.is_error, largo
            assert list(largo) == [*SUMMARY_FIELDS, "truncated"]
            assert largo["truncated"] is True
            assert len(str(largo["preview"])) == summary.PREVIEW_CHARS

            data = base64.b64encode(CORTO.encode("utf-8")).decode("ascii")
            result = await session.call_tool(
                "convert_base64",
                {"data": data, "filename": "corto.md", "output_path": "salida/b64.md"},
            )
            b64 = wire_payload(result)
            assert not result.is_error, b64
            assert list(b64) == SUMMARY_FIELDS, "mismo resumen de 5 claves que convert_document"

            result = await session.call_tool("list_formats", {})
            listed = wire_payload(result)
            assert not result.is_error, listed
            assert list(listed) == ["formats", "count", "notes"]
            assert listed["count"] == len(listed["formats"]) == len(formats.SUPPORTED_FORMATS)
            assert isinstance(listed["notes"], str) and "OCR" in listed["notes"]

            payloads.update(corto=corto, largo=largo, b64=b64, listed=listed)
        return payloads

    payloads = asyncio.run(journey())

    corto = payloads["corto"]  # type: ignore[assignment]
    assert corto["written_to"] == "salida/corto.md"
    assert corto["source_uri"] == "staging/corto.md"
    assert corto["bytes"] == len(CORTO.encode("utf-8"))
    assert corto["chars"] == len(CORTO)
    assert corto["preview"] == CORTO
    assert "truncated" not in corto

    b64 = payloads["b64"]  # type: ignore[assignment]
    assert b64["source_uri"] == "corto.md"
    assert b64["preview"] == CORTO, "los bytes en contexto producen el mismo markdown"


# --- (b) presupuesto de caracteres y tokens, ES/EN y CJK ----------------------------------


def test_summaries_stay_within_the_character_budget_for_latin_and_cjk(tmp_path: Path) -> None:
    """≤1 400 chars serializados y `preview` ≤500; CJK a 1 token/car no cruza 1 600.

    El resumen se mide sobre `content[0].text` (lo que viaja). El techo es de
    CARACTERES (1400); con el peso CJK del estimador (1 token/carácter) el peor
    caso sigue en 1400 + 25 = 1425 tokens ≤ 1600, así que la cota es real en los
    cuatro scripts aunque el `chars/4 + 25` de ES/EN no describa el CJK.
    """
    vault = _vault(tmp_path)
    env = server_env(vault)

    async def journey() -> dict[str, str]:
        raw: dict[str, str] = {}
        async with running_server(env) as session:
            for name in ("largo", "cjk"):
                result = await session.call_tool(
                    "convert_document",
                    {"path": f"staging/{name}.md", "output_path": f"salida/{name}-b.md"},
                )
                assert not result.is_error, result.content[0].text
                payload = wire_payload(result)
                text = result.content[0].text
                assert len(text) <= summary.SUMMARY_CHAR_CEILING, name
                assert len(str(payload["preview"])) <= summary.PREVIEW_CHARS, name
                assert budget.estimate_tokens(text) <= budget.PAYLOAD_TOKEN_CEILING, name
                raw[name] = text
        return raw

    raw = asyncio.run(journey())
    assert len(raw["cjk"]) <= summary.SUMMARY_CHAR_CEILING


# --- (d) negativos: JSON canónico, código correcto y NUNCA `INTERNAL` ---------------------


CONVERT_CASES: dict[str, tuple[str, dict[str, object], str]] = {
    "path_inexistente": ("convert_document", {"path": "staging/no-existe.md"}, "VALIDATION_ERROR"),
    "path_directorio": ("convert_document", {"path": "staging"}, "VALIDATION_ERROR"),
    "path_traversal": ("convert_document", {"path": "../fuera.md"}, "VALIDATION_ERROR"),
    "path_absoluto_externo": ("convert_document", {"path": "/etc/hostname"}, "VALIDATION_ERROR"),
    "formato_no_soportado": (
        "convert_document",
        {"path": "staging/raro.bin", "format": ".exe"},
        "VALIDATION_ERROR",
    ),
    "salida_fuera_del_vault": (
        "convert_document",
        {"path": "staging/corto.md", "output_path": "../escape.md"},
        "VALIDATION_ERROR",
    ),
    "destino_contenido_distinto": (
        "convert_document",
        {"path": "staging/corto.md", "output_path": "salida/ocupado.md"},
        "VALIDATION_ERROR",
    ),
    "documento_sin_capa_de_texto": (
        "convert_document",
        {"path": "staging/escaneado.pdf"},
        "SOURCE_UNREACHABLE",
    ),
    "b64_sin_pista": (
        "convert_base64",
        {"data": base64.b64encode(CORTO.encode("utf-8")).decode("ascii")},
        "VALIDATION_ERROR",
    ),
    "b64_corrupto": (
        "convert_base64",
        {"data": "@@@no-base64@@@", "format": "md"},
        "VALIDATION_ERROR",
    ),
    "b64_formato_no_soportado": (
        "convert_base64",
        {"data": base64.b64encode(b"x").decode("ascii"), "format": "exe"},
        "VALIDATION_ERROR",
    ),
    "b64_salida_fuera_del_vault": (
        "convert_base64",
        {
            "data": base64.b64encode(CORTO.encode("utf-8")).decode("ascii"),
            "format": "md",
            "output_path": "../escape.md",
        },
        "VALIDATION_ERROR",
    ),
}
"""Nombre → (tool, args, código esperado). Todos son argumentos corregibles (D39)."""

INDEXER_DIR_CASES: dict[str, tuple[str, str | None]] = {
    "raiz_inexistente_fichero": ("staging/no-existe.md", "staging/no-existe.md"),
    "raiz_inexistente_directorio": ("no-existe", "no-existe"),
    "raiz_traversal": ("../fuera", None),
    "N_raices_una_mala": ("staging,no-existe", "no-existe"),
}
"""Nombre → (`INDEXER_DIR`, `details.requested` esperado; `None` = sin details).

Las raíces del índice las declara el USUARIO en `INDEXER_DIR`: la tool no tiene
parámetro, así que cada negativo levanta su propio server hijo.
"""


def test_invalid_arguments_return_canonical_json_and_never_internal(tmp_path: Path) -> None:
    """Cada negativo sale `is_error` con JSON canónico, su código y NUNCA `INTERNAL`.

    OM-15: una ruta mal escrita es un argumento que el agente corrige, no un
    fallo interno del motor. La validación corre en el borde ANTES de tocar
    disco/markitdown, así que la ausencia de `.tepochcalli/db/` demuestra que
    los negativos no indexaron nada (fail-fast atómico, D65).
    """
    vault = _vault(tmp_path)
    env = server_env(vault)

    async def calls() -> dict[str, tuple[bool, dict[str, object]]]:
        out: dict[str, tuple[bool, dict[str, object]]] = {}
        async with running_server(env) as session:
            for name, (tool, arguments, _code) in CONVERT_CASES.items():
                result = await session.call_tool(tool, arguments)
                out[name] = (bool(result.is_error), wire_payload(result))
        return out

    results = asyncio.run(calls())

    for name, (_tool, _arguments, expected) in CONVERT_CASES.items():
        is_error, payload = results[name]
        assert is_error, f"{name}: debe ser error"
        assert list(payload) == ["error"], f"{name}: JSON canónico"
        error = payload["error"]
        assert isinstance(error, dict), name
        assert error["code"] == expected, f"{name}: {error}"
        assert error["code"] != "INTERNAL", f"{name}: ruta mal escrita jamás es INTERNAL (OM-15)"
        assert list(error) == ["code", "message", "details"], name

    # Detalles accionables de los cubos de §5.9 (no solo el código).
    directorio = results["path_directorio"][1]["error"]["details"]
    assert directorio == {
        "requested": "staging",
        "exists": True,
        "expected": "file",
        "found": "directory",
    }

    formato = results["formato_no_soportado"][1]["error"]["details"]
    assert formato["formats"] == list(formats.SUPPORTED_FORMATS)

    assert "OCR" in results["documento_sin_capa_de_texto"][1]["error"]["message"]
    assert not (vault / ".tepochcalli" / "db").exists(), (
        "fail-fast atómico: una raíz mala no deja media indexación hecha"
    )


@pytest.mark.parametrize(
    ("indexer_dir", "requested"),
    INDEXER_DIR_CASES.values(),
    ids=INDEXER_DIR_CASES,
)
def test_invalid_indexer_dir_roots_are_validation_error_and_never_internal(
    tmp_path: Path, indexer_dir: str, requested: str | None
) -> None:
    """Raíces mal declaradas en `INDEXER_DIR` ⇒ `VALIDATION_ERROR`, jamás `INTERNAL`.

    La tool no acepta raíces: el conjunto lo declara el usuario en el entorno
    del server hijo. Una raíz inexistente (fichero o directorio), con `..` o
    una mala entre varias ⇒ fallo atómico antes del motor y cero filas.
    """
    vault = _vault(tmp_path)
    env = {**server_env(vault), "INDEXER_DIR": indexer_dir}

    async def go() -> tuple[bool, dict[str, object]]:
        async with running_server(env) as session:
            result = await session.call_tool("index_refresh", {})
            return bool(result.is_error), wire_payload(result)

    is_error, payload = asyncio.run(go())

    assert is_error, f"INDEXER_DIR={indexer_dir!r}: debe ser error"
    assert list(payload) == ["error"], "JSON canónico"
    error = payload["error"]
    assert error["code"] == "VALIDATION_ERROR", error
    assert error["code"] != "INTERNAL", "una raíz mal escrita jamás es INTERNAL (OM-15)"
    assert list(error) == ["code", "message", "details"], error
    if requested is None:
        assert error["details"] is None, "un escape del vault no inventa detalles"
    else:
        assert error["details"]["requested"] == requested
        assert error["details"]["exists"] is False
        assert isinstance(error["details"]["suggestions"], list)
    assert not (vault / ".tepochcalli" / "db").exists(), (
        "fail-fast atómico: una raíz mala no deja media indexación hecha"
    )
