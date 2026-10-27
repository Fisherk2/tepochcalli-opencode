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
from tepochcalli_mcp import paths
from tepochcalli_mcp.tools import add_source as handler

REPORT = {"scanned": 3, "indexed": 1, "skipped": 2, "elapsed_ms": 800, "locked": False}
"""Reporte Δ con la forma `asdict(RefreshReport)` de Phase 1 (orden congelado)."""


def _notas_uri(vault: Path) -> str:
    """Uri de ejemplo DENTRO del vault: el fichero no existe — los seams falsos no leen nada."""
    return (vault / "staging" / "notas.md").as_uri()


def _run(
    uri: str,
    subdir: str | None = None,
    *,
    vault: Path,
    convert: Callable[[str], str] | None = None,
    report: dict[str, object] | None = None,
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


def test_atomic_write_cleans_the_temporary_and_reraises_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fallo ANTES del rename ⇒ el `.tmp` se limpia y la excepción sube (⇒ `INTERNAL`).

    Sin esta rama, un rename fallido (disco lleno, permisos) dejaría basura
    `.tmp` en `00-Resources/` — material que el walk de indexación vería.
    """
    inbox = tmp_path / "00-Resources" / "_inbox"
    inbox.mkdir(parents=True)
    target = inbox / "notas.md"

    def _broken_replace(_src: object, _dst: object) -> None:
        raise OSError("cross-device link")

    monkeypatch.setattr(handler.os, "replace", _broken_replace)

    with pytest.raises(OSError, match="cross-device"):
        handler._write_atomic(target, "# contenido\n")

    assert not target.exists(), "el destino no existe: el rename no llegó a correr"
    assert list(inbox.iterdir()) == [], "el temporal se limpia en la rama de fallo"


def test_write_atomic_refuses_to_overwrite_a_target_appeared_in_a_race(
    tmp_path: Path,
) -> None:
    """Review Phase 2 (eje 5, TOCTOU): target en carrera ⇒ RuntimeError, nada se borra.

    `available_name` vio el hueco, la carrera lo ocupó ⇒ `RuntimeError`, que
    sube al guard ⇒ `INTERNAL`; jamás `ok: true` borrando el material.
    """
    inbox = tmp_path / "00-Resources" / "_inbox"
    inbox.mkdir(parents=True)
    target = inbox / "notas.md"
    target.write_text("previa", encoding="utf-8")

    with pytest.raises(RuntimeError, match="TOCTOU|sobrescribe"):
        handler._write_atomic(target, "# nuevo\n")

    assert target.read_text(encoding="utf-8") == "previa", "nada se sobrescribió"


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
