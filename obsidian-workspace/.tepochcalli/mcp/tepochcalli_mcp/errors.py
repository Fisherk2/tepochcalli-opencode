"""Taxonomía de errores del server `tepochcalli-rag` — payloads canónicos (plan §5).

Dominio puro del server (hexagonal: la dependencia apunta hacia dentro): sin
`mcp` ni infraestructura — cada constructor devuelve el DICT que el handler
serializa en `content[0].text` (spec-mcp-server §Manejo de errores: «nunca
texto libre»). Dos dialectos congelados:

* **Legado** `{error:{code,message,details}}` — `VALIDATION_ERROR`,
  `INDEX_EMPTY`, `INTERNAL` (T3/T5 añadirán `ENGINE_LOCKED` y
  `SOURCE_UNREACHABLE` con esta misma forma).
* **`E_*`** `{error:{code,message,fix_hint}}` (D7.3/ADR-007) —
  `E_MODEL_MISMATCH` lleva además `details.legacy_code = "INDEX_STALE_MODEL"`,
  el alias heredado que viaja en el payload (spec-mcp-server §Códigos de error
  estructurados). T6 añadirá los cuatro `E_*` restantes.

El orden de claves es parte del contrato (Hyrum, ADR-005): los constructores
lo fijan y los contract tests lo pinan. El traceback de un fallo inesperado
vive en el LOG del server (stderr), jamás en el payload al cliente.
"""

from __future__ import annotations

from typing import Final

INDEX_STALE_MODEL_ALIAS: Final = "INDEX_STALE_MODEL"
"""Alias legado de `E_MODEL_MISMATCH`, viaja en `details.legacy_code` (spec §Códigos)."""


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
            "fix_hint": (
                "Reconstruye el índice con el modelo configurado: "
                "`tepochcalli reindex --confirm` (spec-embeddings §swap)"
            ),
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
