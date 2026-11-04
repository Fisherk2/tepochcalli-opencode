"""Handler de `rag_status`: diagnóstico barato de los 4 bloques (T4, plan §6).

La tool que D7.3/ADR-007 hacen obligatoria ante cualquier `E_*`: el agente la
llama SIN penalizar la conversación (§Presupuesto: <200 tokens por
construcción) y reporta el `fix_hint` exacto — nunca el error crudo.

El handler depende de seams/DTO (test de arquitectura T2): NO importa
`tepochcalli_flow.app`, `lancedb` ni `cocoindex`. El composition root entrega
`Config` (pereza bajo la guarda), el `IndexMeta` derivado en solo lectura y la
validez del toml. **Las decisiones de contrato, documentadas aquí y en la
descripción de la tool (lo que el agente lee):**

* **`mode`** — fuente única `embedder.mode(config)`: `litellm` ⇒ `api`,
  `local` ⇒ `local`, `none` ⇒ `none` (inalcanzable vía loader hasta T6/D15;
  se prueba con un `Config` construido a mano — la costura).
* **`provider`** — `null` en `local` y `none` (ejemplos LITERALES de la spec
  §rag_status); en `api` = `config.embedding.provider`, hoy solo `litellm`
  (lo único que la config D11 puede nombrar; si nombra el upstream en el
  futuro, este campo lo seguirá — T8 fija el shape, solo aditivo).
* **`dims`** — 384 (`DEFAULT_EMBEDDING_DIMS`) SOLO si `model ==
  DEFAULT_EMBEDDING_MODEL` (único modelo cuyas dims son un hecho conocido
  SIN cargar nada ni preguntar a la red); modelos custom ⇒ `null`; `none` ⇒
  `null`. T6 podrá enriquecerlo para custom sin tocar el shape.
* **`model_matches_config`** — `models ⊆ {config.model}`: índice VACÍO ⇒
  `true` (ejemplo literal de la spec: `rows: 0` con `matches: true`; sin
  filas no hay evidencia de desajuste), con filas ⇒ todas del modelo esperado
  (equivale al `==` del AC en el único caso no vacío).
* **`config.valid`** — `true` si el toml está AUSENTE (opcional: los defaults
  son canónicos) o se parseó limpio **y** `problems` está vacío; `false` si
  existe y no se pudo leer/parsear o si hay problemas de entorno. **No es un
  chequeo de existencia** — el loader nunca falla, el campo mide PARSEO +
  coherencia de la config, y `load_config` no da señal: la checa el
  composition root (`_config_valid` + `_config_problems_seam`).
* **`config.problems`** — mensajes cortos de `diagnostics.config_problems`
  (raíz contractual, cada raíz de `INDEXER_DIR`, `TEPOCHCALLI_TOP_K`), tope 3.
  Hace visible en la PRIMERA llamada lo que antes solo estallaba al indexar.
* **`config.unknown_env`** — nombres que parecen nuestros y no lo son
  (`INDEXER_DRI`, `TEPOCHALLI_ROOT`…): una clave mal escrita no se ignora en
  silencio. Tope 3. Ninguno de los dos degrada `health` (un `INDEXER_DIR` malo
  no rompe `search`: el índice existente sigue sirviendo, D39).
* **`health`** — precedencia `E_NO_EMBEDDER` > `E_MODEL_MISMATCH` > `ok`.
  `reason` solo admite `E_*` (spec §Códigos): un índice vacío con embedder
  sano es `ok` (ningún `E_*` aplica) y `config.valid=false` NO degrada la
  salud — es informativo (ningún `E_*` cubre un toml roto; T6 no cambia esto).
* **`last_refresh`** — `max(indexed_at)` DERIVADO en el composition root (sin
  estado nuevo); `null` si el índice está vacío. Semántica declarada en la
  descripción de la tool: «última indexación efectiva».
* **`last_refresh_roots`** (T8/D42) — raíces de la última indexación **de la
  sesión**, en memoria: `[]` si aún no hubo refresh. NO se persiste (las
  raíces viven solo en la invocación, ADR-010 §4.1); el composition root las
  anota al cerrar un refresh no bloqueado y las entrega por costura.
* **`available_roots`** (T8/D67) — directorios de primer nivel del vault que
  son indexables (`paths.vault_dirs`: fuera los de punto). El agente pregunta
  qué hay en vez de adivinar qué carpeta indexar. Con tres raíces el payload
  sigue bajo el techo de 200 tokens (lo pina el test de presupuesto).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Literal, TypedDict

from tepochcalli_flow import citation
from tepochcalli_flow.config import (
    CONFIG_RELPATH,
    DEFAULT_EMBEDDING_DIMS,
    DEFAULT_EMBEDDING_MODEL,
    Config,
)

from tepochcalli_mcp import embedder, errors


class IndexMeta(TypedDict):
    """DTO de solo lectura del índice que el composition root construye (T4).

    `models` vive DENTRO del DTO (no es JSON: se convierte en
    `model_matches_config` bool antes del payload). La consulta es UNA
    proyección de `model`+`indexed_at` compartida con la de `search`
    (`backend._VaultSearchBackend._select`) — no se reimplementa.
    """

    rows: int
    """Filas de la tabla `chunks` (proyección, no `stats.total`)."""

    models: set[str]
    """Conjunto de `model` de las filas — ∅ si el índice no existe."""

    last_refresh: str | None
    """`max(indexed_at)` ISO-8601 UTC derivado; `null` si no hay filas."""

    db_size_bytes: int
    """Tamaño recursivo de TODO `.tepochcalli/db/` (spec §rag_status: `db/`)."""


def _provider_of(mode: embedder.EmbedderMode, config: Config) -> str | None:
    """`null` en local/none (ejemplos literales de la spec); en api, la clave de config."""
    return config.embedding.provider if mode == "api" else None


def _dims_of(model: str | None) -> int | None:
    """384 solo para el modelo pineado del repo (ADR-006); `null` sin dims conocidas."""
    if model is None:
        return None
    return DEFAULT_EMBEDDING_DIMS if model == DEFAULT_EMBEDDING_MODEL else None


@errors.internal_guard
async def rag_status(
    *,
    config_factory: Callable[[], Config],
    index_meta: Callable[[], Awaitable[IndexMeta]],
    config_valid: Callable[[], bool],
    last_refresh_roots: Callable[[], tuple[str, ...]],
    available_roots: Callable[[], tuple[str, ...]],
    problems: Callable[[], tuple[str, ...]],
    unknown_env: Callable[[], tuple[str, ...]],
) -> dict[str, object]:
    """`{embedder, index, config, health}` — los 4 bloques congelados de §rag_status.

    Los seams se invocan DENTRO del handler, bajo `@errors.internal_guard`
    (G1): cualquier fallo de arranque/lectura ⇒ `INTERNAL` canónico, nunca
    texto libre al cliente. Ver decisiones de contrato en el docstring del
    módulo; las de `mode`/`last_refresh`/`config.valid` se repiten en la
    descripción de la tool porque el agente las interpreta.
    """
    config = config_factory()
    mode = embedder.mode(config)
    model = None if mode == "none" else citation.model_id(config)
    meta = await index_meta()
    config_problems = problems()
    config_unknown = unknown_env()
    matches = meta["models"].issubset({citation.model_id(config)})
    if mode == "none":
        state: Literal["ok", "degraded"] = "degraded"
        reason: str | None = "E_NO_EMBEDDER"
        fix_hint: str | None = errors.FIX_NO_EMBEDDER
    elif not matches:
        state = "degraded"
        reason = "E_MODEL_MISMATCH"
        fix_hint = errors.FIX_MODEL_MISMATCH
    else:
        state = "ok"
        reason = None
        fix_hint = None
    return {
        "embedder": {
            "mode": mode,
            "model": model,
            "dims": _dims_of(model),
            "provider": _provider_of(mode, config),
        },
        "index": {
            "rows": meta["rows"],
            "model_matches_config": matches,
            "last_refresh": meta["last_refresh"],
            "db_size_bytes": meta["db_size_bytes"],
            "last_refresh_roots": list(last_refresh_roots()),
            "available_roots": list(available_roots()),
        },
        # `CONFIG_RELPATH.as_posix()`: relativo POR CONSTRUCCIÓN y siempre con
        # `/` — jamás filtra el home ni cambia de forma con el SO (spec literal).
        "config": {
            "path": CONFIG_RELPATH.as_posix(),
            "valid": config_valid() and not config_problems,
            "problems": list(config_problems),
            "unknown_env": list(config_unknown),
        },
        "health": {"state": state, "reason": reason, "fix_hint": fix_hint},
    }
