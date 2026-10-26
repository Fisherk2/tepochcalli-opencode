"""Handler de `index_refresh`: el ciclo Δ de Phase 1 como tool (T3, plan §6).

Exponer el delta SIN reinterpretarlo: el reporte sale `tal cual` de
`RefreshReport` (identidad `scanned == indexed + skipped` POR CONSTRUCCIÓN en
`models.py`; `elapsed_ms` monótono; `locked` ⇒ tres ceros sin update) y el
handler no hace aritmética alguna sobre las cuentas.

El handler NO importa `tepochcalli_flow.app` ni `.models` — ambos alcanzan
`cocoindex`, prohibido en `tepochcalli_mcp.tools.*` (test de arquitectura T2).
El composition root (`server.py`, exento) inyecta tres seams:

* `refresh`: ciclo bloqueante de Phase 1 YA serializado con `dataclasses.asdict`
  → el handler lo corre con `asyncio.to_thread` (AC: no satura el event loop).
* `embedder_available`: costura de la precedencia `E_NO_EMBEDDER >
  INDEX_EMPTY` — hoy True para cualquier config real porque `none` (D15) no es
  expresable hasta T6 (`embedder.is_available`); se demuestra con FAKE en el
  unit test, sin tocar `flow/config.py`.
* `index_exists`: ¿queda la tabla `chunks` tras el refresh? False ⇒
  `INDEX_EMPTY` (vault sin indexables: la tool lo dice en vez de mentir).

La guarda compartida `@errors.internal_guard` (G1) envuelve el handler
completo: cualquier fallo inesperado (refresh, seams) → `INTERNAL` canónico
con traceback en el log stderr, nunca texto libre al cliente (T4/T5 reusan
esta misma guarda).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from tepochcalli_mcp import errors


@errors.internal_guard
async def index_refresh(
    *,
    refresh: Callable[[], dict[str, object]],
    embedder_available: Callable[[], bool],
    index_exists: Callable[[], bool],
) -> dict[str, object]:
    """Devuelve `{scanned, indexed, skipped, elapsed_ms, locked}` — el reporte tal cual.

    Precedencia: `E_NO_EMBEDDER` (sin embedder ni se refresca) → reporte del
    refresh (con candado ⇒ tres ceros, sin mirar el índice) → `INDEX_EMPTY` si
    la tabla sigue ausente → si no, el reporte DEVUELTO TAL CUAL.
    """
    if not embedder_available():
        return errors.no_embedder()  # precede a todo: sin embedder no hay ciclo Δ
    report = await asyncio.to_thread(refresh)  # bloqueante ⇒ FUERA del event loop
    if report.get("locked"):
        return report  # candado retenido: Phase 1 ya garantiza los ceros y el no-update
    if not index_exists():
        return errors.index_empty()
    return report
