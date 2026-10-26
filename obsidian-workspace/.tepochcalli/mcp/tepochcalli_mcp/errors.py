"""Taxonomía de errores del server `tepochcalli-rag` — payloads canónicos (plan §5).

Dominio puro del server (hexagonal: la dependencia apunta hacia dentro): sin
`mcp` ni infraestructura — cada constructor devuelve el DICT que el handler
serializa en `content[0].text` (spec-mcp-server §Manejo de errores: «nunca
texto libre»). Dos dialectos congelados:

* **Legado** `{error:{code,message,details}}` — `VALIDATION_ERROR`,
  `INDEX_EMPTY`, `INTERNAL` (T5 añadirá `ENGINE_LOCKED` y
  `SOURCE_UNREACHABLE` con esta misma forma).
* **`E_*`** `{error:{code,message,fix_hint}}` (D7.3/ADR-007) —
  `E_MODEL_MISMATCH` lleva además `details.legacy_code = "INDEX_STALE_MODEL"`,
  el alias heredado que viaja en el payload (spec-mcp-server §Códigos de error
  estructurados); `E_NO_EMBEDDER` (T3) es el segundo de la serie. T6 añadirá
  los tres `E_*` restantes.

El orden de claves es parte del contrato (Hyrum, ADR-005): los constructores
lo fijan y los contract tests lo pinan. El traceback de un fallo inesperado
vive en el LOG del server (stderr), jamás en el payload al cliente —
`internal_guard` es quien lo garantiza (G1).
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Awaitable, Callable
from typing import Final

logger = logging.getLogger(__name__)

INDEX_STALE_MODEL_ALIAS: Final = "INDEX_STALE_MODEL"
"""Alias legado de `E_MODEL_MISMATCH`, viaja en `details.legacy_code` (spec §Códigos)."""

FIX_NO_EMBEDDER: Final = "Ejecuta `tepochcalli config embedder` y luego `index_refresh()`"
"""Solución exacta de spec §rag_status para `E_NO_EMBEDDER` — única fuente de verdad.

La usan el payload `errors.no_embedder()` Y `health.fix_hint` de la tool
`rag_status` (T4): los textos de `fix_hint` se escriben UNA vez (D7.3 obliga
al agente a reportar este texto, no un error crudo).
"""

FIX_MODEL_MISMATCH: Final = (
    "Reconstruye el índice con el modelo configurado: "
    "`tepochcalli reindex --confirm` (spec-embeddings §swap)"
)
"""Solución de `E_MODEL_MISMATCH` (comando literal de spec §INDEX_STALE_MODEL).

Misma dualidad que `FIX_NO_EMBEDDER`: payload de error Y `health.fix_hint` de
`rag_status` (T4) — un solo texto para ambas superficies.
"""


def validation_error(message: str, details: object = None) -> dict[str, object]:
    """`VALIDATION_ERROR` legado — argumentos inválidos en el borde MCP (plan §5)."""
    return {"error": {"code": "VALIDATION_ERROR", "message": message, "details": details}}


def index_empty() -> dict[str, object]:
    """`INDEX_EMPTY` legado — tabla `chunks` inexistente; la guía es `index_refresh()`."""
    return {
        "error": {
            "code": "INDEX_EMPTY",
            "message": "El índice no existe; ejecute index_refresh().",
            "details": None,
        }
    }


def model_mismatch(index_models: set[str], expected: str) -> dict[str, object]:
    """`E_MODEL_MISMATCH` (D7.3) con el alias legado en `details.legacy_code`.

    `index_models` es el conjunto de `model` de las filas: se NOMBRA, sin cruzar
    dims (spec-mcp-server §E_MODEL_MISMATCH: `search` se niega a cruzar dims).
    """
    listed = ", ".join(sorted(index_models))
    return {
        "error": {
            "code": "E_MODEL_MISMATCH",
            "message": (
                f"El índice fue construido con [{listed}] y la config actual usa "
                f"{expected!r}; no se cruzan dims de modelos distintos."
            ),
            "fix_hint": FIX_MODEL_MISMATCH,
            "details": {"legacy_code": INDEX_STALE_MODEL_ALIAS},
        }
    }


def internal() -> dict[str, object]:
    """Devuelve el payload legado `INTERNAL`: fallo inesperado; el detalle vive en el log."""
    return {
        "error": {
            "code": "INTERNAL",
            "message": "Error interno del server; revisa el log local (stderr) del proceso.",
            "details": None,
        }
    }


def no_embedder() -> dict[str, object]:
    """Devuelve `E_NO_EMBEDDER` (D7.3): sin modelo local ni API configurada (modo `none`).

    Segundo `E_*` de la serie, con la solución exacta de
    spec-mcp-server §rag_status en el `fix_hint` (la regla del vault obliga al
    agente a reportarla, no el error crudo). Sin `details`: solo
    `E_MODEL_MISMATCH` lleva el alias legado.
    """
    return {
        "error": {
            "code": "E_NO_EMBEDDER",
            "message": "No hay embedder configurado (modo `none`): no puedo incrustar ni indexar.",
            "fix_hint": FIX_NO_EMBEDDER,
        }
    }


def internal_guard[**P](
    handler: Callable[P, Awaitable[dict[str, object]]],
) -> Callable[P, Awaitable[dict[str, object]]]:
    """Guarda compartida G1: envuelve un handler COMPLETO → fallo ⇒ `INTERNAL` canónico.

    El patrón ÚNICO de los tools del server (aplicado en `search` — fase de
    estado Y arranque de seams— e `index_refresh` desde T3; T4 y T5 lo usan en
    vez de reimplementarlo): captura `Exception` —nunca `BaseException`, para
    que Ctrl-C siga escapando—, manda el traceback al LOG vía
    `logger.exception` (stderr; stdout es solo JSON-RPC) y devuelve
    `errors.internal()`: el cliente recibe JSON parseable con `is_error = true`,
    jamás texto libre ni stack traces (spec-mcp-server §Manejo de errores).
    Los `ValueError` de validación NO llegan aquí: los handlers los capturan
    ANTES y responden `VALIDATION_ERROR` con su mensaje accionable.
    """

    @functools.wraps(handler)
    async def guarded(*args: P.args, **kwargs: P.kwargs) -> dict[str, object]:
        try:
            return await handler(*args, **kwargs)
        except Exception:
            logger.exception("internal_guard: fallo inesperado en %s", handler.__qualname__)
            return internal()

    return guarded
