"""T3: handler `index_refresh` — reporte tal cual, precedencia `E_*` y candado (plan §6).

Fuentes de verdad:

* tasks/plan.md §6 T3 — `asdict(RefreshReport)` SIN recalcular; `locked:true`
  ⇒ tres ceros y sin update; `E_NO_EMBEDDER` precede a `INDEX_EMPTY`;
  idempotencia; handler no bloqueante.
* specs/spec-mcp-server.md §Tool `index_refresh` — forma
  `{scanned, indexed, skipped, elapsed_ms, locked}`.
* `tepochcalli_flow/models.RefreshReport` (Phase 1) — identidad
  `scanned == indexed + skipped` POR CONSTRUCCIÓN; `elapsed_ms` monótono.

Decisiones de capa, documentadas:

* El handler NO importa `tepochcalli_flow.models` ni `app` (importan
  `cocoindex`: test de arquitectura lo prohíbe en `tepochcalli_mcp.tools.*`).
  El composition root (`server.py`, exento) entrega el DTO ya serializado con
  `dataclasses.asdict` — el handler lo devuelve TAL CUAL, sin tocar cuentas.
* `refresh` es síncrono y bloqueante ⇒ el handler lo corre con
  `asyncio.to_thread` (AC: no satura el event loop del server).
* **Costura `E_NO_EMBEDDER`:** `embedder_available` es un seam inyectado. Hoy
  `embedder.is_available(config)` devuelve SIEMPRE True porque el loader
  `flow/config.py` — VEDADO hasta T6 — aún no puede expresar `none` (D15);
  la PRECEDENCIA se demuestra aquí con el fake, sin tocar `flow/`. T6 cierra
  la costura ligándola al provider real.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Callable

from tepochcalli_mcp import errors
from tepochcalli_mcp.tools import index_refresh as refresh_tool
from tepochcalli_mcp.tools import json_result

WELL_FORMED_REPORT: dict[str, object] = {
    "scanned": 2,
    "indexed": 1,
    "skipped": 1,
    "elapsed_ms": 42,
    "locked": False,
}

LOCKED_REPORT: dict[str, object] = {
    "scanned": 0,
    "indexed": 0,
    "skipped": 0,
    "elapsed_ms": 0,
    "locked": True,
}


def _call(
    refresh: Callable[[], dict[str, object]],
    *,
    embedder_available: Callable[[], bool],
    index_exists: Callable[[], bool],
) -> dict[str, object]:
    """Invoca el handler en su propio loop (cada test, aislado)."""
    return asyncio.run(
        refresh_tool.index_refresh(
            refresh=refresh,
            embedder_available=embedder_available,
            index_exists=index_exists,
        )
    )


def _const[T](value: T) -> Callable[[], T]:
    """Seam constante para lecturas que no interesan en el test."""
    return lambda: value


# --- reporte tal cual (asdict en el composition root) -------------------------------


def test_report_is_returned_tal_cual_with_the_exact_key_order() -> None:
    """El DTO pasa intacto: orden `{scanned,indexed,skipped,elapsed_ms,locked}`."""
    payload = _call(
        lambda: WELL_FORMED_REPORT,
        embedder_available=_const(True),
        index_exists=_const(True),
    )

    assert payload is WELL_FORMED_REPORT, "ni recalcular ni copiar: devolver tal cual"
    assert list(payload) == ["scanned", "indexed", "skipped", "elapsed_ms", "locked"]


def test_report_counts_are_never_recomputed_even_if_inconsistent() -> None:
    """El handler NO hace aritmética sobre las cuentas del reporte.

    La identidad `scanned == indexed + skipped` es garantía de Phase 1 (por
    construcción), no del server: un reporte con cuentas «imposibles» sale SIN
    corregir — si el handler restara, esto fallaría.
    """
    inconsistent = {"scanned": 10, "indexed": 3, "skipped": 3, "elapsed_ms": 0, "locked": False}

    payload = _call(
        lambda: inconsistent,
        embedder_available=_const(True),
        index_exists=_const(True),
    )

    assert payload == inconsistent


def test_locked_report_short_circuits_without_consulting_the_index() -> None:
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
        lambda: LOCKED_REPORT,
        embedder_available=_const(True),
        index_exists=_index_exists,
    )

    assert payload == LOCKED_REPORT
    assert payload["locked"] is True
    assert (payload["scanned"], payload["indexed"], payload["skipped"]) == (0, 0, 0)
    assert consulted == [], "el estado del índice no se consulta con el candado puesto"


# --- precedencia: E_NO_EMBEDDER > INDEX_EMPTY ----------------------------------------


def test_no_embedder_precedes_index_empty_and_skips_the_refresh() -> None:
    """Sin embedder → `E_NO_EMBEDDER` ANTES de refrescar y sin mirar el índice.

    Costura para D15 (`provider = "none"`, pendiente en T6): el seam fake
    expresa el modo `none` que el loader real aún no puede — la precedencia
    queda probada sin tocar `flow/config.py`.
    """
    calls: list[str] = []

    def _refresh() -> dict[str, object]:
        calls.append("refresh")
        return WELL_FORMED_REPORT

    payload = _call(
        _refresh,
        embedder_available=_const(False),
        index_exists=_const(False),
    )

    assert payload == errors.no_embedder()
    assert payload["error"]["code"] == "E_NO_EMBEDDER"
    assert calls == [], "sin embedder no se ejecuta el ciclo Δ (precedencia)"


def test_index_empty_when_the_refresh_leaves_no_index() -> None:
    """Con embedder y sin tabla tras el refresh → `INDEX_EMPTY` legado."""
    payload = _call(
        lambda: WELL_FORMED_REPORT,
        embedder_available=_const(True),
        index_exists=_const(False),
    )

    assert payload == errors.index_empty()


# --- no bloquear el event loop ---------------------------------------------------------


def test_refresh_runs_in_a_worker_thread_not_on_the_event_loop() -> None:
    """`asyncio.to_thread`: el ciclo bloqueante NUNCA corre en el hilo del loop."""
    loop_thread = threading.get_ident()
    refresh_thread: list[int] = []

    def _refresh() -> dict[str, object]:
        refresh_thread.append(threading.get_ident())
        return WELL_FORMED_REPORT

    payload = _call(
        _refresh,
        embedder_available=_const(True),
        index_exists=_const(True),
    )

    assert payload == WELL_FORMED_REPORT
    assert refresh_thread and refresh_thread[0] != loop_thread, (
        f"refresh corrió en el hilo del event loop ({loop_thread}): saturaría el server"
    )


# --- la guarda compartida (G1) también cubre este handler --------------------------------


def test_unexpected_refresh_failure_is_canonical_internal() -> None:
    """Un fallo inesperado del ciclo Δ → `INTERNAL` canónico con `is_error = true`.

    Misma guarda (`errors.internal_guard`) que `search` — T4/T5 la reutilizarán
    en vez de reimplementarla; el traceback queda en el log, nunca en el payload.
    """

    def _refresh() -> dict[str, object]:
        raise RuntimeError("update revienta con detalle privado")

    payload = _call(
        _refresh,
        embedder_available=_const(True),
        index_exists=_const(True),
    )

    result = json_result(payload)
    assert result.is_error is True
    error = json.loads(result.content[0].text)["error"]
    assert list(error) == ["code", "message", "details"]
    assert error["code"] == "INTERNAL"
    assert "detalle privado" not in error["message"]


def test_failed_embedder_seam_is_canonical_internal_not_a_crash() -> None:
    """El seam de precedencia también vive bajo la guarda (arranque de config)."""

    def _available() -> bool:
        raise OSError("tepochcalli.toml ilegible")

    payload = _call(
        lambda: WELL_FORMED_REPORT,
        embedder_available=_available,
        index_exists=_const(True),
    )

    assert payload["error"]["code"] == "INTERNAL"
    assert "ilegible" not in str(payload["error"]["message"])
