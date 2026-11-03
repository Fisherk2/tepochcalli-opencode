"""Handler de `index_refresh`: el ciclo Δ de Phase 1 como tool (T3 + T8, plan §6).

Exponer el delta SIN reinterpretarlo: el reporte sale `tal cual` de
`RefreshReport` (identidad `scanned == indexed + skipped` POR CONSTRUCCIÓN en
`models.py`; `elapsed_ms` monótono; `locked` ⇒ tres ceros sin update) y el
handler no hace aritmética alguna sobre las cuentas. El campo aditivo `roots`
(ADR-010 §4.1) viaja en el mismo DTO: el handler no lo fabrica.

El handler NO importa `tepochcalli_flow.app` ni `.models` — ambos alcanzan
`cocoindex`, prohibido en `tepochcalli_mcp.tools.*` (test de arquitectura T2).
El composition root (`server.py`, exento) inyecta cuatro seams:

* `vault_root`: raíz del vault para el borde de raíces (`paths.validate_roots`).
* `refresh`: ciclo bloqueante YA serializado con `dataclasses.asdict`, que
  recibe las raíces **normalizadas** (tupla relativa al vault) → el handler lo
  corre con `asyncio.to_thread` (AC: no satura el event loop).
* `embedder_available`: costura de la precedencia `E_NO_EMBEDDER >
  INDEX_EMPTY` — se demuestra con FAKE en el unit test.
* `index_exists`: ¿queda la tabla `chunks` tras el refresh? False ⇒
  `INDEX_EMPTY` (vault sin indexables: la tool lo dice en vez de mentir).

**`directories` se valida en el BORDE, ANTES de la costura** (T8/D44/D64/D65):
`paths.validate_roots` es puro y comprueba existencia, tipo, `..` y escape del
vault; su `VaultPathError` se mapea a `VALIDATION_ERROR` con
`details.suggestions`. Dejarlo al motor convertiría una carpeta mal escrita en
`INTERNAL` por el `ValueError` de `walk_dir` (OM-15). El fallo es atómico: una
raíz mala ⇒ no se indexa ninguna. `VALIDATION_ERROR` precede a
`E_NO_EMBEDDER` — el argumento se juzga antes de mirar el provider.

**Raíces por omisión (`default_roots`):** `directories` vacío/`None` ⇒ las
raíces de la costura (`Config.indexer_roots`, que sale de `INDEXER_DIR` en
`opencode.json`), validadas igual que las explícitas. El handler no repite el
literal `("00-Resources",)`: el composition root pasa la costura.

La guarda compartida `@errors.internal_guard` (G1) envuelve el handler
completo: cualquier fallo inesperado (refresh, seams) → `INTERNAL` canónico
con traceback en el log stderr, nunca texto libre al cliente (T4/T5 reusan
esta misma guarda).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

from tepochcalli_mcp import embedder, errors, paths


@errors.internal_guard
async def index_refresh(
    directories: list[str] | None = None,
    *,
    vault_root: Callable[[], Path],
    default_roots: Callable[[], tuple[str, ...]],
    refresh: Callable[[tuple[str, ...]], dict[str, object]],
    embedder_available: Callable[[], bool],
    index_exists: Callable[[], bool],
) -> dict[str, object]:
    """Devuelve `{scanned, indexed, skipped, elapsed_ms, locked, roots}`.

    Precedencia: `VALIDATION_ERROR` (raíces mal escritas, antes de tocar el
    motor) → `E_NO_EMBEDDER` (sin embedder ni se refresca) → reporte del
    refresh (con candado ⇒ tres ceros, sin mirar el índice) → `INDEX_EMPTY` si
    la tabla sigue ausente → si no, el reporte DEVUELTO TAL CUAL. Un
    directorio vacío no es error: sale `scanned: 0` y el agente no lo lee como
    fallo. `directories` omitido/vacío ⇒ raíces de `default_roots`
    (`Config.indexer_roots`, declaradas en `INDEXER_DIR`).
    """
    try:
        roots = paths.validate_roots(directories or default_roots(), vault_root())
    except paths.VaultPathError as exc:
        return errors.validation_error(str(exc), exc.details)
    if not embedder_available():
        return errors.no_embedder()  # precede a todo: sin embedder no hay ciclo Δ
    try:
        report = await asyncio.to_thread(refresh, roots)  # bloqueante ⇒ FUERA del event loop
    except embedder.EmbedderAuthError as exc:
        # T6: el composition root tradujo la clave ausente del flow (litellm
        # sin api_key_env) — el dialecto E_API_AUTH en vez de INTERNAL.
        return errors.api_auth(str(exc))
    if report.get("locked"):
        return report  # candado retenido: Phase 1 ya garantiza los ceros y el no-update
    if not index_exists():
        return errors.index_empty()
    return report
