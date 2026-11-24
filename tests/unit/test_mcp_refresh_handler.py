"""T3+T8: handler `index_refresh` — reporte tal cual, raíces configuradas y precedencias.

Fuentes de verdad:

* tasks/plan.md §6 T3 — `asdict(RefreshReport)` SIN recalcular; `locked:true`
  ⇒ tres ceros y sin update; `E_NO_EMBEDDER` precede a `INDEX_EMPTY`;
  idempotencia; handler no bloqueante.
* tasks/todo.md T8 AC (a)-(j) — las raíces configuradas (`INDEXER_DIR`) se
  validan en el borde ANTES de la costura (`paths.validate_roots`, puro) ⇒
  `VALIDATION_ERROR`, nunca `INTERNAL` (OM-15); fail-fast atómico (D65);
  `VALIDATION_ERROR` precede a `E_NO_EMBEDDER`; la respuesta conserva las 5
  claves y añade `roots`.
* specs/spec-mcp-server.md §Tool `index_refresh`.

Decisiones de capa, documentadas:

* El handler NO importa `tepochcalli_flow.models` ni `app` (importan
  `cocoindex`: test de arquitectura lo prohíbe en `tepochcalli_mcp.tools.*`).
  El composition root (`server.py`, exento) entrega el DTO ya serializado con
  `dataclasses.asdict` — el handler lo devuelve TAL CUAL, sin tocar cuentas.
* `refresh` es síncrono y bloqueante ⇒ el handler lo corre con
  `asyncio.to_thread` (AC: no satura el event loop) y recibe las raíces ya
  normalizadas (tupla relativa al vault), no el argumento crudo.
* **Costura `E_NO_EMBEDDER`:** `embedder_available` es un seam inyectado. La
  PRECEDENCIA se demuestra con el fake, sin tocar `flow/`. El borde de raíces
  corre ANTES (AC g): un argumento mal escrito se responde como
  `VALIDATION_ERROR` aunque el embedder esté apagado.
* Los tests usan un vault REAL de `tmp_path` (con `00-resources/` y dos
  carpetas) porque `validate_roots` exige existencia y tipo: validar con un
  fake de `paths` probaría el fake, no el borde.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from mcp.server.mcpserver.utilities.func_metadata import func_metadata
from tepochcalli_mcp import errors, server
from tepochcalli_mcp.tools import index_refresh as refresh_tool
from tepochcalli_mcp.tools import json_result

WELL_FORMED_REPORT: dict[str, object] = {
    "scanned": 2,
    "indexed": 1,
    "skipped": 1,
    "elapsed_ms": 42,
    "locked": False,
    "roots": ["00-resources"],
}

LOCKED_REPORT: dict[str, object] = {
    "scanned": 0,
    "indexed": 0,
    "skipped": 0,
    "elapsed_ms": 0,
    "locked": True,
    "roots": ["00-resources"],
}


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """Vault real mínimo: el default `00-resources/` existe (el borde lo exige)."""
    (tmp_path / "00-resources").mkdir()
    return tmp_path


def _call(
    *,
    vault_root: Path,
    refresh: Callable[[tuple[str, ...]], dict[str, object]],
    embedder_available: Callable[[], bool],
    index_exists: Callable[[], bool],
    default_roots: Callable[[], tuple[str, ...]] = lambda: ("00-resources",),
) -> dict[str, object]:
    """Invoca el handler sin argumentos (el conjunto lo fija la costura)."""
    return asyncio.run(
        refresh_tool.index_refresh(
            vault_root=lambda: vault_root,
            default_roots=default_roots,
            refresh=refresh,
            embedder_available=embedder_available,
            index_exists=index_exists,
        )
    )


def _const[T](value: T) -> Callable[[], T]:
    """Seam constante para lecturas que no interesan en el test."""
    return lambda: value


# --- reporte tal cual (asdict en el composition root) -------------------------------


def test_report_is_returned_tal_cual_with_the_exact_key_order(vault: Path) -> None:
    """El DTO pasa intacto: orden `{scanned,indexed,skipped,elapsed_ms,locked,roots}`."""
    payload = _call(
        vault_root=vault,
        refresh=lambda _roots: WELL_FORMED_REPORT,
        embedder_available=_const(True),
        index_exists=_const(True),
    )

    assert payload is WELL_FORMED_REPORT, "ni recalcular ni copiar: devolver tal cual"
    assert list(payload) == ["scanned", "indexed", "skipped", "elapsed_ms", "locked", "roots"]


def test_report_counts_are_never_recomputed_even_if_inconsistent(vault: Path) -> None:
    """El handler NO hace aritmética sobre las cuentas del reporte.

    La identidad `scanned == indexed + skipped` es garantía de Phase 1 (por
    construcción), no del server: un reporte con cuentas «imposibles» sale SIN
    corregir — si el handler restara, esto fallaría.
    """
    inconsistent = {
        "scanned": 10,
        "indexed": 3,
        "skipped": 3,
        "elapsed_ms": 0,
        "locked": False,
        "roots": ["00-resources"],
    }

    payload = _call(
        vault_root=vault,
        refresh=lambda _roots: inconsistent,
        embedder_available=_const(True),
        index_exists=_const(True),
    )

    assert payload == inconsistent


def test_locked_report_short_circuits_without_consulting_the_index(vault: Path) -> None:
    """`locked: true` ⇒ tres ceros tal cual y NO se consulta el estado del índice.

    La adquisición del candado vive DENTRO de `refresh_blocking` (Phase 1):
    el seam `refresh` sí se invoca —él decide no ejecutar update—, pero el
    handler no debe mirar el índice de un refresh que no corrió.
    """
    consulted: list[str] = []

    def _index_exists() -> bool:
        consulted.append("index_exists")
        return False

    payload = _call(
        vault_root=vault,
        refresh=lambda _roots: LOCKED_REPORT,
        embedder_available=_const(True),
        index_exists=_index_exists,
    )

    assert payload == LOCKED_REPORT
    assert payload["locked"] is True
    assert (payload["scanned"], payload["indexed"], payload["skipped"]) == (0, 0, 0)
    assert consulted == [], "el estado del índice no se consulta con el candado puesto"


# --- raíces del índice: SOLO las declaradas por el usuario (INDEXER_DIR) --------------


def test_default_roots_are_00_resources(vault: Path) -> None:
    """AC (a): costura por omisión ⇒ `("00-resources",)` — el default del producto."""
    seen: list[tuple[str, ...]] = []

    def _refresh(roots: tuple[str, ...]) -> dict[str, object]:
        seen.append(roots)
        return WELL_FORMED_REPORT

    payload = _call(
        vault_root=vault,
        refresh=_refresh,
        embedder_available=_const(True),
        index_exists=_const(True),
    )

    assert seen == [("00-resources",)]
    assert payload["roots"] == ["00-resources"]


def test_default_roots_come_from_the_seam_not_from_the_literal(
    vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El borde valida las raíces de la costura (`config.indexer_roots`), no un literal.

    `INDEXER_DIR` se declara en `opencode.json`; el handler no repite el literal
    `("00-resources",)` — lo recibe por costura, igual que `last_refresh_roots`.
    """
    (vault / "materiales").mkdir()
    validated: list[Sequence[str] | None] = []
    real_validate_roots = refresh_tool.paths.validate_roots

    def _spy(directories: Sequence[str] | None, vault_root: Path) -> tuple[str, ...]:
        validated.append(directories)
        return real_validate_roots(directories, vault_root)

    monkeypatch.setattr(refresh_tool.paths, "validate_roots", _spy)
    seen: list[tuple[str, ...]] = []

    def _refresh(roots: tuple[str, ...]) -> dict[str, object]:
        seen.append(roots)
        return {**WELL_FORMED_REPORT, "roots": list(roots)}

    payload = _call(
        vault_root=vault,
        refresh=_refresh,
        embedder_available=_const(True),
        index_exists=_const(True),
        default_roots=_const(("materiales",)),
    )

    assert validated == [("materiales",)], "el borde valida la raíz de la costura tal cual"
    assert seen == [("materiales",)]
    assert payload["roots"] == ["materiales"]


def test_no_arguments_index_the_configured_two_roots(vault: Path) -> None:
    """Sin argumentos en el wire, se indexa EXACTAMENTE el conjunto configurado."""
    (vault / "materiales").mkdir()
    (vault / "documentos").mkdir()
    seen: list[tuple[str, ...]] = []

    def _refresh(roots: tuple[str, ...]) -> dict[str, object]:
        seen.append(roots)
        return {**WELL_FORMED_REPORT, "roots": list(roots)}

    payload = _call(
        vault_root=vault,
        refresh=_refresh,
        embedder_available=_const(True),
        index_exists=_const(True),
        default_roots=_const(("materiales", "documentos")),
    )

    assert seen == [("materiales", "documentos")]
    assert payload["roots"] == ["materiales", "documentos"]


def test_removed_directories_argument_is_ignored_by_the_sdk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El argumento retirado NO tiene efecto: el SDK descarta claves desconocidas.

    `FuncMetadata.validate_arguments` hace `model_validate` sobre una firma vacía
    y `model_dump_one_level`; `{"directories": [...]}` se descarta y la tool se
    llama sin argumentos ⇒ indexa el conjunto declarado en `INDEXER_DIR`, no lo
    pedido. Si una versión futura del SDK lo rechazara, este test lo delata
    (fallaría la validación). No se añade un guard que devuelva error: el fallo
    seguro —indexar el conjunto declarado— ya es el comportamiento correcto.
    """
    (tmp_path / "00-resources").mkdir()
    (tmp_path / "documentos").mkdir()
    monkeypatch.setenv("TEPOCHCALLI_VAULT_ROOT", str(tmp_path))
    monkeypatch.setenv("INDEXER_DIR", "00-resources")
    seen: list[tuple[str, ...]] = []

    def _refresh(roots: tuple[str, ...]) -> dict[str, object]:
        seen.append(roots)
        return {**WELL_FORMED_REPORT, "roots": list(roots)}

    monkeypatch.setattr(server, "_refresh_once", _refresh)
    monkeypatch.setattr(server, "_embedder_available", lambda: True)
    monkeypatch.setattr(server, "_index_exists", lambda: True)

    meta = func_metadata(server.index_refresh)
    kwargs = meta.validate_arguments({"directories": ["documentos"]})
    assert kwargs == {}, "el SDK descarta la clave desconocida (firma vacía)"
    result = asyncio.run(meta.call_fn(server.index_refresh, True, kwargs))
    payload = json.loads(result.content[0].text)

    assert seen == [("00-resources",)], "indexa el conjunto configurado, no lo pedido"
    assert payload["roots"] == ["00-resources"]


def test_configured_roots_are_normalized_and_forwarded_to_the_seam(vault: Path) -> None:
    """AC (d): las raíces validadas (relativas al vault) llegan al motor tal cual."""
    (vault / "materiales").mkdir()
    (vault / "documentos").mkdir()
    seen: list[tuple[str, ...]] = []

    def _refresh(roots: tuple[str, ...]) -> dict[str, object]:
        seen.append(roots)
        return {**WELL_FORMED_REPORT, "roots": list(roots)}

    payload = _call(
        vault_root=vault,
        refresh=_refresh,
        embedder_available=_const(True),
        index_exists=_const(True),
        default_roots=_const(("materiales", "documentos")),
    )

    assert seen == [("materiales", "documentos")]
    assert payload["roots"] == ["materiales", "documentos"]


def test_missing_root_is_validation_error_before_the_seam(vault: Path) -> None:
    """AC (b)/(h): raíz inexistente en la costura ⇒ `VALIDATION_ERROR` — nunca `INTERNAL`.

    El pre-chequeo corre en el borde ANTES de la costura: `walk_dir` del motor
    lanzaría `ValueError` y el `internal_guard` lo volvería `INTERNAL` (OM-15).
    """
    (vault / "documentos").mkdir()
    calls: list[tuple[str, ...]] = []

    payload = _call(
        vault_root=vault,
        refresh=lambda roots: calls.append(roots) or WELL_FORMED_REPORT,
        embedder_available=_const(True),
        index_exists=_const(True),
        default_roots=_const(("Documentos",)),
    )

    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert payload["error"]["details"] == {
        "requested": "Documentos",
        "exists": False,
        "suggestions": ["documentos"],
        "vault_dirs": ["00-resources", "documentos"],
    }
    assert calls == [], "una raíz mala no debe llegar al motor"


def test_one_bad_root_among_three_indexes_nothing(vault: Path) -> None:
    """AC (h)/D65: fail-fast atómico — una raíz mala ⇒ las otras tampoco se indexan."""
    (vault / "materiales").mkdir()
    (vault / "documentos").mkdir()
    calls: list[tuple[str, ...]] = []

    payload = _call(
        vault_root=vault,
        refresh=lambda roots: calls.append(roots) or WELL_FORMED_REPORT,
        embedder_available=_const(True),
        index_exists=_const(True),
        default_roots=_const(("materiales", "documentos", "no-existe")),
    )

    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert payload["error"]["details"]["requested"] == "no-existe"  # type: ignore[index]
    assert calls == [], "fallo atómico: ninguna raíz se indexa si una falla"


def test_validation_error_precedes_e_no_embedder(vault: Path) -> None:
    """AC (g): la configuración se juzga ANTES de mirar el provider."""
    payload = _call(
        vault_root=vault,
        refresh=lambda _roots: WELL_FORMED_REPORT,
        embedder_available=_const(False),
        index_exists=_const(False),
        default_roots=_const(("no-existe",)),
    )

    assert payload["error"]["code"] == "VALIDATION_ERROR", (
        "una raíz mal escrita es corregible: no la tapa `E_NO_EMBEDDER`"
    )


def test_escaped_root_is_validation_error_not_internal(vault: Path) -> None:
    """`..` fuera del vault ⇒ `VALIDATION_ERROR` en el borde (frontera B′)."""
    payload = _call(
        vault_root=vault,
        refresh=lambda _roots: WELL_FORMED_REPORT,
        embedder_available=_const(True),
        index_exists=_const(True),
        default_roots=_const(("../fuera",)),
    )

    assert payload["error"]["code"] == "VALIDATION_ERROR"


# --- precedencia: E_NO_EMBEDDER > INDEX_EMPTY ----------------------------------------


def test_no_embedder_precedes_index_empty_and_skips_the_refresh(vault: Path) -> None:
    """Sin embedder → `E_NO_EMBEDDER` ANTES de refrescar y sin mirar el índice."""
    calls: list[str] = []

    def _refresh(_roots: tuple[str, ...]) -> dict[str, object]:
        calls.append("refresh")
        return WELL_FORMED_REPORT

    payload = _call(
        vault_root=vault,
        refresh=_refresh,
        embedder_available=_const(False),
        index_exists=_const(False),
    )

    assert payload == errors.no_embedder()
    assert payload["error"]["code"] == "E_NO_EMBEDDER"
    assert calls == [], "sin embedder no se ejecuta el ciclo Δ (precedencia)"


def test_index_empty_when_the_refresh_leaves_no_index(vault: Path) -> None:
    """Con embedder y sin tabla tras el refresh → `INDEX_EMPTY` legado."""
    payload = _call(
        vault_root=vault,
        refresh=lambda _roots: WELL_FORMED_REPORT,
        embedder_available=_const(True),
        index_exists=_const(False),
    )

    assert payload == errors.index_empty()


# --- no bloquear el event loop ---------------------------------------------------------


def test_refresh_runs_in_a_worker_thread_not_on_the_event_loop(vault: Path) -> None:
    """`asyncio.to_thread`: el ciclo bloqueante NUNCA corre en el hilo del loop."""
    loop_thread = threading.get_ident()
    refresh_thread: list[int] = []

    def _refresh(_roots: tuple[str, ...]) -> dict[str, object]:
        refresh_thread.append(threading.get_ident())
        return WELL_FORMED_REPORT

    payload = _call(
        vault_root=vault,
        refresh=_refresh,
        embedder_available=_const(True),
        index_exists=_const(True),
    )

    assert payload == WELL_FORMED_REPORT
    assert refresh_thread and refresh_thread[0] != loop_thread, (
        f"refresh corrió en el hilo del event loop ({loop_thread}): saturaría el server"
    )


# --- la guarda compartida (G1) también cubre este handler --------------------------------


def test_unexpected_refresh_failure_is_canonical_internal(vault: Path) -> None:
    """Un fallo inesperado del ciclo Δ → `INTERNAL` canónico con `is_error = true`."""

    def _refresh(_roots: tuple[str, ...]) -> dict[str, object]:
        raise RuntimeError("update revienta con detalle privado")

    payload = _call(
        vault_root=vault,
        refresh=_refresh,
        embedder_available=_const(True),
        index_exists=_const(True),
    )

    result = json_result(payload)
    assert result.is_error is True
    error = json.loads(result.content[0].text)["error"]
    assert list(error) == ["code", "message", "details"]
    assert error["code"] == "INTERNAL"
    assert "detalle privado" not in error["message"]


def test_failed_embedder_seam_is_canonical_internal_not_a_crash(vault: Path) -> None:
    """El seam de precedencia también vive bajo la guarda (arranque de config)."""

    def _available() -> bool:
        raise OSError("tepochcalli.toml ilegible")

    payload = _call(
        vault_root=vault,
        refresh=lambda _roots: WELL_FORMED_REPORT,
        embedder_available=_available,
        index_exists=_const(True),
    )

    assert payload["error"]["code"] == "INTERNAL"
    assert "ilegible" not in str(payload["error"]["message"])
