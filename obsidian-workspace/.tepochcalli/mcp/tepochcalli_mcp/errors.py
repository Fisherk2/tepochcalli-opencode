"""Taxonomía de errores del server `tepochcalli-rag` — payloads canónicos (plan §5).

Dominio puro del server (hexagonal: la dependencia apunta hacia dentro): sin
`mcp` ni infraestructura — cada constructor devuelve el DICT que el handler
serializa en `content[0].text` (spec-mcp-server §Manejo de errores: «nunca
texto libre»). Dos dialectos congelados:

* **Legado** `{error:{code,message,details}}` — `VALIDATION_ERROR`,
  `INDEX_EMPTY`, `INTERNAL`, y desde T5 `ENGINE_LOCKED` y
  `SOURCE_UNREACHABLE` con esta misma forma.
* **`E_*`** `{error:{code,message,fix_hint}}` (D7.3/ADR-007) —
  `E_MODEL_MISMATCH` lleva además `details.legacy_code = "INDEX_STALE_MODEL"`,
  el alias heredado que viaja en el payload (spec-mcp-server §Códigos de error
  estructurados); desde T6 el dialecto está **5/5**: `E_NO_EMBEDDER` (T3),
  `E_MODEL_MISMATCH` (T2) y `E_API_AUTH` + `E_MODEL_INVALID` +
  `E_OFFLINE_NO_CACHE` (T6, con `FIX_*` single-homed como los dos primeros).

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

from tepochcalli_mcp.paths import redact_uri

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

FIX_API_AUTH: Final = (
    "Ejecuta `tepochcalli config embedder` y re-ingresa la clave; "
    "la clave nunca se registra en logs"
)
"""Texto LITERAL de spec-mcp-server §Códigos para `E_API_AUTH` (T6) — única fuente."""

FIX_MODEL_INVALID: Final = (
    "Verifica `[embedding].model` y materializa el snapshot con "
    "`tepochcalli config embedder`; si el índice era de otro modelo, "
    "reconstruye con `tepochcalli reindex --confirm`."
)
"""Guía de `E_MODEL_INVALID` (T6).

La spec §Códigos da el SIGNIFICADO («no es embedding model / models/ corrompido»)
pero no un texto literal de `fix_hint` para este código: esta guía lo compone
accionable y directo; T8 la fija en los contract tests.
"""

FIX_OFFLINE_NO_CACHE: Final = (
    "Sin red no puedo descargar el modelo: quita el modo offline o precarga "
    "`.tepochcalli/models/` con `tepochcalli config embedder`."
)
"""Guía de `E_OFFLINE_NO_CACHE` (T6) — derivada de spec-embeddings §Matriz de edge cases.

«`--offline` sin `models/` cacheado ⇒ quitar `--offline` o `tepochcalli config
embedder`» — la matriz da la acción; este texto la vuelve reportable.
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


GUIDE_MANUAL_SAVE: Final = (
    "Guárdalo manualmente en una raíz declarada en `INDEXER_DIR` (p. ej. 00-Resources/) "
    "y ejecuta `index_refresh`."
)
"""Guía de `SOURCE_UNREACHABLE` paso 3 para el fallback (ADR-010: solo se indexa
lo declarado en `INDEXER_DIR` — guardar fuera ⇒ indexar 0 silenciosamente)."""

GUIDE_OCR: Final = (
    "Sin OCR: el documento no tiene capa de texto; guárdalo como `.md` a mano o "
    "pásalo por un OCR y reintenta la conversión."
)
"""Guía de `SOURCE_UNREACHABLE` cuando la causa es un escaneado (T7, OM-11/D39).

El conversor la pasa por `guide=` sin cambiar la forma del payload: se informa al
usuario y se le ofrece el camino manual, nunca una conversión vacía.
"""

GUIDE_RETRY_SECONDS: Final = "Reintenta en segundos o ejecuta `index_refresh` después."
"""Guía de spec-mcp-server §Manejo de errores para `ENGINE_LOCKED` («reintentar en segundos»)."""


def source_unreachable(
    uri: str, cause: str | None = None, *, guide: str | None = None
) -> dict[str, object]:
    """`SOURCE_UNREACHABLE` legado (T5): fetch/convert falló; la guía es la literal de la spec.

    `cause` es SOLO el nombre del tipo de la excepción (nunca el traceback ni
    texto arbitrario): accionable para el agente y seguro para el cliente —
    el traceback completo vive en el log stderr del server.

    `guide` sustituye la guía por defecto por la que corresponda a la causa
    (p. ej. `GUIDE_OCR`): la forma del payload no cambia (T7 AC (g)).

    Review Phase 2 (eje 4): el URI entra REDACTADO (`paths.redact_uri`) — el
    payload es la superficie de observabilidad del fallo y jamás ecoa
    credenciales (userinfo/query secreta).
    """
    return {
        "error": {
            "code": "SOURCE_UNREACHABLE",
            "message": (
                f"No se pudo convertir {redact_uri(uri)} a Markdown. {guide or GUIDE_MANUAL_SAVE}"
            ),
            "details": {"cause": cause} if cause else None,
        }
    }


def engine_locked(details: object = None) -> dict[str, object]:
    """`ENGINE_LOCKED` legado (T5): el refresh quedó bloqueado por otro proceso en `add_source`.

    La forma de `add_source` no tiene campo `locked` (el sub-objeto `indexed`
    congela 4 campos, plan §5), así que el candado se reporta COMO ERROR con
    `details` — p. ej. `{"written_to": …}`: el archivo sí se escribió; lo que
    falló fue el ciclo Δ, reintentable.
    """
    return {
        "error": {
            "code": "ENGINE_LOCKED",
            "message": f"El refresh quedó bloqueado por otro proceso. {GUIDE_RETRY_SECONDS}",
            "details": details,
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


def api_auth(api_key_env: str) -> dict[str, object]:
    """`E_API_AUTH` (T6): clave ausente o rechazada al incrustar — nombra la ENV VAR.

    `api_key_env` es SOLO el nombre de la variable (config guarda el nombre,
    jamás el valor — spec-embeddings §Security): un valor de clave es
    estructuralmente imposible en este payload (plan §9 riesgo crítico).
    Cubre la ausencia local (chequeo sin red) y el 401/403 de la API.
    """
    return {
        "error": {
            "code": "E_API_AUTH",
            "message": (
                f"La clave de API declarada en `{api_key_env}` falta o fue rechazada "
                "al incrustar la query."
            ),
            "fix_hint": FIX_API_AUTH,
        }
    }


def model_invalid() -> dict[str, object]:
    """`E_MODEL_INVALID` (T6): el modelo no es materializable — dos causas, una guía.

    Descarga fallida o no-es-modelo de embeddings (la causa tipada con el
    detalle vive en el log vía el guard; al cliente va la guía, no el
    traceback). Sin `details`: solo `E_MODEL_MISMATCH` lleva el alias.
    """
    return {
        "error": {
            "code": "E_MODEL_INVALID",
            "message": (
                "El modelo de embeddings no es materializable (descarga fallida "
                "o no es un modelo de embeddings)."
            ),
            "fix_hint": FIX_MODEL_INVALID,
        }
    }


def offline_no_cache() -> dict[str, object]:
    """`E_OFFLINE_NO_CACHE` (T6): modo offline sin el modelo en cache ni config de API.

    Spec-mcp-server §Códigos + spec-embeddings §Matriz de edge cases: la
    instalación offline sin `models/` cacheado falla limpio con esta guía.
    """
    return {
        "error": {
            "code": "E_OFFLINE_NO_CACHE",
            "message": (
                "Modo offline sin el modelo en `.tepochcalli/models/` "
                "(ni config de API disponible)."
            ),
            "fix_hint": FIX_OFFLINE_NO_CACHE,
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
