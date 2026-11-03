"""T5: handler de `add_source` — convertir, escribir y reindexar en una llamada (unit).

Fuentes de verdad:

* tasks/plan.md §6 T5 AC — forma `{ok, written_to, indexed:{scanned, indexed,
  skipped, elapsed_ms}}` (4 campos, SIN `locked`), slug + `.md` con sufijo,
  escritura atómica, `file:` fuera del vault ⇒ `VALIDATION_ERROR` (D16),
  fetch/convert ⇒ `SOURCE_UNREACHABLE`, refresh bloqueado ⇒ `ENGINE_LOCKED`.
* specs/spec-mcp-server.md §Tool `add_source`; specs/spec-markitdown.md
  §Cadena de fallback (guía literal) y §Testing (negativos).

El handler se ejercita con seams FALSOS (patrón T2-T4): `vault_root`,
`convert` y `refresh` los inyecta el composition root en producción; aquí
se prueba el dominio sin markitdown, sin el flow y sin subproceso. La
conversión REAL y el cableado stdio viven en el test de integración
(`tests/integration/test_mcp_add_source.py`).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from tepochcalli_mcp import paths, server
from tepochcalli_mcp.tools import add_source as handler

REPORT = {"scanned": 3, "indexed": 1, "skipped": 2, "elapsed_ms": 800, "locked": False}
"""Reporte Δ con la forma `asdict(RefreshReport)` de Phase 1 (orden congelado)."""


def _notas_uri(vault: Path) -> str:
    """Uri de ejemplo DENTRO del vault; el fichero existe (D64: ruta inexistente ⇒ VALIDATION)."""
    source = vault / "staging" / "notas.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# Nota\n\nfuente real dentro del vault\n", encoding="utf-8")
    return source.as_uri()


def _run(
    uri: str,
    subdir: str | None = None,
    *,
    vault: Path,
    convert: Callable[[str], str] | None = None,
    report: dict[str, object] | None = None,
    allowed_roots: Callable[[], tuple[str, ...]] = lambda: ("00-Resources",),
) -> tuple[dict[str, object], list[str]]:
    """Ejecuta el handler con seams falsos; devuelve `(payload, llamadas a seams)`."""
    calls: list[str] = []

    def fake_convert(given_uri: str) -> str:
        calls.append(given_uri)
        return "# Nota convertida\n\ncontenido de prueba\n"

    def fake_refresh() -> dict[str, object]:
        calls.append("refresh")
        return dict(REPORT if report is None else report)

    payload = asyncio.run(
        handler.add_source(
            uri,
            subdir,
            vault_root=lambda: vault,
            convert=convert or fake_convert,
            refresh=fake_refresh,
            embedder_available=lambda: True,
            allowed_roots=allowed_roots,
        ),
    )
    return payload, calls


def test_success_returns_the_exact_contract_shape_and_writes_the_file(tmp_path: Path) -> None:
    """Camino feliz: shape exacto de §5 y el archivo queda en `00-Resources/_inbox/`."""
    payload, calls = _run(_notas_uri(tmp_path), vault=tmp_path)

    assert list(payload) == ["ok", "written_to", "indexed"]
    assert payload["ok"] is True
    assert payload["written_to"] == "00-Resources/_inbox/notas.md"
    assert list(payload["indexed"]) == ["scanned", "indexed", "skipped", "elapsed_ms"]
    expected = {key: REPORT[key] for key in ("scanned", "indexed", "skipped", "elapsed_ms")}
    assert payload["indexed"] == expected
    written = tmp_path / "00-Resources" / "_inbox" / "notas.md"
    assert written.read_text(encoding="utf-8").startswith("# Nota convertida")
    assert calls == [_notas_uri(tmp_path), "refresh"], "convierte y DESPUÉS reindexa, en ese orden"


def test_custom_subdir_nests_inside_resources(tmp_path: Path) -> None:
    """`subdir` con anidamiento queda dentro de `00-Resources/` (D9.1)."""
    payload, _calls = _run(_notas_uri(tmp_path), "lit-pediatría/ruiz", vault=tmp_path)

    assert payload["written_to"] == "00-Resources/lit-pediatría/ruiz/notas.md"
    assert (tmp_path / payload["written_to"]).is_file()


def test_collision_gets_the_numeric_suffix(tmp_path: Path) -> None:
    """Segunda conversión del mismo nombre ⇒ `<slug>-2.md` (plan §T5)."""
    inbox = tmp_path / "00-Resources" / "_inbox"
    inbox.mkdir(parents=True)
    (inbox / "notas.md").write_text("previa", encoding="utf-8")

    payload, _calls = _run(_notas_uri(tmp_path), vault=tmp_path)

    assert payload["written_to"] == "00-Resources/_inbox/notas-2.md"


def test_atomic_write_leaves_no_temporary_behind(tmp_path: Path) -> None:
    """El temporal vive en el directorio de destino y desaparece tras el rename."""
    _run(_notas_uri(tmp_path), vault=tmp_path)

    inbox = tmp_path / "00-Resources" / "_inbox"
    assert sorted(p.name for p in inbox.iterdir()) == ["notas.md"]


def test_traversal_subdir_is_validation_error_and_writes_nothing(tmp_path: Path) -> None:
    """`subdir` con `..` ⇒ `VALIDATION_ERROR`; ni convert ni refresh se ejecutan."""
    payload, calls = _run(_notas_uri(tmp_path), "../escape", vault=tmp_path)

    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert calls == [], "la validación falla ANTES de convertir ni escribir"
    assert not (tmp_path / "escape").exists()
    assert not (tmp_path / "00-Resources").exists()


def test_absolute_subdir_is_validation_error(tmp_path: Path) -> None:
    """`subdir` absoluto ⇒ `VALIDATION_ERROR` (spec-mcp-server §Security)."""
    payload, _calls = _run(_notas_uri(tmp_path), "/etc", vault=tmp_path)

    assert payload["error"]["code"] == "VALIDATION_ERROR"


def test_file_outside_the_vault_is_rejected_d16(tmp_path: Path) -> None:
    """D16: `file:` FUERA del vault ⇒ `VALIDATION_ERROR` sin convertir (spec §Testing)."""
    payload, calls = _run("file:///etc/hostname", vault=tmp_path)

    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert calls == [], "D16 se decide en el borde: el conversor jamás ve la ruta"


def test_non_http_file_scheme_is_validation_error(tmp_path: Path) -> None:
    """Solo `http(s):` y `file:`; `ftp:` u otro esquema ⇒ `VALIDATION_ERROR`."""
    payload, _calls = _run("ftp://example.org/x.docx", vault=tmp_path)

    assert payload["error"]["code"] == "VALIDATION_ERROR"


def test_file_uri_that_does_not_exist_is_validation_error(tmp_path: Path) -> None:
    """T9 AC (l): `file:` inexistente ⇒ `VALIDATION_ERROR` (ruta mal escrita, D64).

    Antes moría como `SOURCE_UNREACHABLE` culpando al documento; el agente debe
    poder corregir la ruta con `details.suggestions` en un reintento.
    """
    uri = (tmp_path / "staging" / "fantasma.md").as_uri()

    payload, calls = _run(uri, vault=tmp_path)

    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert calls == [], "el borde decide antes de que markitdown vea la ruta"


def test_convert_failure_maps_to_source_unreachable_with_the_literal_guide(
    tmp_path: Path,
) -> None:
    """Fallo de fetch/convert ⇒ `SOURCE_UNREACHABLE` con la guía; el refresh NO corre."""

    def broken_convert(_uri: str) -> str:
        msg = "no suitable converter"
        raise RuntimeError(msg)

    payload, calls = _run(_notas_uri(tmp_path), vault=tmp_path, convert=broken_convert)

    error = payload["error"]
    assert error["code"] == "SOURCE_UNREACHABLE"
    assert "00-Resources/" in error["message"] and "index_refresh" in error["message"]
    assert error["details"] == {"cause": "RuntimeError"}
    assert "refresh" not in calls, "sin conversión no hay archivo que reindexar"
    assert not (tmp_path / "00-Resources").exists()


def test_locked_refresh_reports_engine_locked_but_keeps_the_written_file(tmp_path: Path) -> None:
    """Refresh bloqueado ⇒ `ENGINE_LOCKED` (la forma no tiene `locked`); el archivo SÍ quedó."""
    locked = {**REPORT, "locked": True, "scanned": 0, "indexed": 0, "skipped": 0}
    payload, calls = _run(_notas_uri(tmp_path), vault=tmp_path, report=locked)

    assert payload["error"]["code"] == "ENGINE_LOCKED"
    assert payload["error"]["details"] == {"written_to": "00-Resources/_inbox/notas.md"}
    assert "refresh" in calls
    assert (tmp_path / "00-Resources" / "_inbox" / "notas.md").is_file()


def test_written_to_is_json_serializable_unicode_safe(tmp_path: Path) -> None:
    """El payload completo sobrevive a `json.dumps(ensure_ascii=False)` (medio del contrato)."""
    payload, _calls = _run(_notas_uri(tmp_path), "ñ-日", vault=tmp_path)

    assert json.loads(json.dumps(payload, ensure_ascii=False)) == payload
    assert "ñ-日" in payload["written_to"]


def test_slug_and_subdir_are_reused_from_paths_domain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El handler NO reimplementa slug/subdir: delega en `paths` (una sola fuente)."""
    # Review SSRF 2026-10-27: con la denylist, `http(s)` por nombre se valida
    # vía DNS — se stubbea a pública para mantener la unidad sin red.
    monkeypatch.setattr(
        paths.socket,
        "getaddrinfo",
        lambda *_: [(2, 0, 6, "", ("93.184.216.34", 0))],
    )
    uri = "https://example.org/papers/ruiz-2024.pdf"
    payload, _calls = _run(uri, vault=tmp_path)

    assert payload["written_to"] == f"00-Resources/_inbox/{paths.slugify_uri(uri)}.md"


# --- wiring de reindexación: el refresh declara EXACTAMENTE el conjunto configurado ------


def _seam_calls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, indexer_dir: str | None
) -> list[tuple[str, ...]]:
    """Espía `server._refresh_once` y ejecuta el seam de refresh de `add_source`."""
    monkeypatch.setenv("TEPOCHCALLI_VAULT_ROOT", str(tmp_path))
    if indexer_dir is None:
        monkeypatch.delenv("INDEXER_DIR", raising=False)
    else:
        monkeypatch.setenv("INDEXER_DIR", indexer_dir)
    seen: list[tuple[str, ...]] = []

    def _spy(directories: tuple[str, ...] | None = None) -> dict[str, object]:
        seen.append(() if directories is None else directories)
        return {}

    monkeypatch.setattr(server, "_refresh_once", _spy)
    server._refresh_configured()
    return seen


def test_add_source_refresh_declares_exactly_the_configured_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`INDEXER_DIR="materiales"` ⇒ el refresh declara SOLO `("materiales",)`.

    Ya no se une `00-Resources/`: si no está declarada, `add_source` se rechaza
    en el borde antes de escribir, así que el conjunto configurado es el que el
    target del flow debe reconciliar.
    """
    assert _seam_calls(monkeypatch, tmp_path, "materiales") == [("materiales",)]


def test_add_source_refresh_uses_the_default_root_without_duplicating_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sin `INDEXER_DIR`, una sola raíz: `("00-Resources",)` — sin duplicar."""
    assert _seam_calls(monkeypatch, tmp_path, None) == [("00-Resources",)]


# --- borde: add_source exige que `00-Resources/` esté declarada en INDEXER_DIR ------------


def test_add_source_rejects_when_resources_is_not_indexed(tmp_path: Path) -> None:
    """`INDEXER_DIR="documentos"` ⇒ `VALIDATION_ERROR` y NADA se escribe ni convierte."""
    payload, calls = _run(
        _notas_uri(tmp_path), vault=tmp_path, allowed_roots=lambda: ("documentos",)
    )

    error = payload["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"]["requested"] == "00-Resources"
    assert error["details"]["allowed"] == ["documentos"]
    assert isinstance(error["details"]["hint"], str) and error["details"]["hint"]
    assert calls == [], "sin raíz declarada no se convierte ni se reindexa"
    assert not (tmp_path / "00-Resources").exists(), "no se escribe nada en 00-Resources/"


def test_add_source_accepts_resources_declared_with_dot_slash(tmp_path: Path) -> None:
    """`INDEXER_DIR="./00-Resources/"` declara la raíz: se normaliza antes de comparar."""
    payload, calls = _run(
        _notas_uri(tmp_path), vault=tmp_path, allowed_roots=lambda: ("./00-Resources/",)
    )

    assert payload["ok"] is True
    assert payload["written_to"] == "00-Resources/_inbox/notas.md"
    assert calls[-1] == "refresh", "con la raíz declarada el ciclo Δ sí corre"
    assert (tmp_path / "00-Resources" / "_inbox" / "notas.md").is_file()


def test_refresh_receives_resources_declared_with_dot_slash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El refresh recibe el conjunto declarado TAL CUAL (la normalización es solo del gate)."""
    assert _seam_calls(monkeypatch, tmp_path, "./00-Resources/") == [("./00-Resources/",)]
