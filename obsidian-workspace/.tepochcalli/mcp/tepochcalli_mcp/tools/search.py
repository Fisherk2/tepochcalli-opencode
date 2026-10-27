"""Handler de `search`: de la pregunta a los chunks citados dentro del presupuesto (T2).

El camino caliente del producto (tasks/plan.md §6 T2). Depende del PUERTO, no
del motor (ADR-005; §8 del plan): recibe un `SearchBackend` inyectado por el
composition root (`server.py`, el ÚNICO módulo del server que conoce SDK, flow
con motor y config — test de arquitectura extendido en T2).

Flujo del handler, en orden de precedencia (la cadena D7.3 de T6):

1. valida args en el borde — `top_k` ∈ [1,20] (`budget`) y glob relativo
   (`paths`) → `VALIDATION_ERROR` SIN tocar el índice;
2. **R1: costura `embedder_available`** → `E_NO_EMBEDDER` ANTES de construir
   nada ni mirar el índice (`E_NO_EMBEDDER > INDEX_EMPTY >
   E_MODEL_MISMATCH > E_API_AUTH`);
3. **arranque del backend** — la FACTORY inyectada (`_backend()` del composition
   root: resolver vault + config) se invoca AQUÍ, bajo la guarda (G1);
4. estado del índice — vacío → `INDEX_EMPTY`; modelo de las filas ≠ config →
   `E_MODEL_MISMATCH` (alias legado, SIN cruzar dims: el embed de la query ni
   se intenta) — ambos ANTES de buscar;
5. búsqueda por el puerto `ChunkReader` (el ADAPTADOR valida query y VECTORIZA
   la query: `took_ms` incluye el embed por construcción); los fallos del
   corte se traducen AQUÍ: `EmbedderAuthError` → `E_API_AUTH`,
   `EmbedderOfflineError` → `E_OFFLINE_NO_CACHE`, `EmbedderModelError` →
   `E_MODEL_INVALID`, `EmbedderUnavailableError` → `E_NO_EMBEDDER`;
6. presupuesto — corte determinista al techo 1600 (`truncated`), y `took_ms`
   se cierra al terminar de ensamblar el payload, justo antes de serializar.

`ValueError` del borde (adaptador o dominio) → `VALIDATION_ERROR`; cualquier
otro fallo —estado, arranque o búsqueda— lo captura
`@errors.internal_guard` (G1): `INTERNAL` canónico con el traceback en el log
stderr, nunca texto libre al cliente (los fallos de API no cubiertos llegan
como `EmbedderApiError` YA SCRUBEADA: la clave no alcanza el log).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol

from tepochcalli_flow.ports import CitedChunk

from tepochcalli_mcp import budget, embedder, errors, paths


class SearchBackend(Protocol):
    """Puerto fino que el composition root inyecta al handler (decisión T2).

    * `expected_model`: modelo configurado — comparado con `index_models` SIN
      cruzar dims (spec-mcp-server §E_MODEL_MISMATCH).
    * `index_models`: conjunto de `model` de las filas del índice; vacío ⇒ el
      índice no existe aún (`INDEX_EMPTY`).
    * `cited_chunks`: búsqueda por el puerto `ChunkReader` de Phase 1 —
      incluye el embed de la query (spec-mcp-server §Presupuestos de latencia).
    """

    @property
    def expected_model(self) -> str:
        """Modelo de embeddings de la config del vault."""
        ...

    async def index_models(self) -> set[str]:
        """Conjunto de `model` de las filas del índice (solo lectura)."""
        ...

    async def cited_chunks(
        self, query: str, top_k: int, path_filter: str | None
    ) -> list[CitedChunk]:
        """Los `top_k` chunks más relevantes, score descendente (puerto Phase 1)."""
        ...


@errors.internal_guard
async def search(
    query: str,
    top_k: int = budget.TOP_K_DEFAULT,
    path_filter: str | None = None,
    *,
    backend_factory: Callable[[], SearchBackend],
    embedder_available: Callable[[], bool],
) -> dict[str, object]:
    """`{query, took_ms, truncated, results}` — la forma congelada de §search (plan §5).

    Cada resultado trae los 7 campos en su orden congelado; los errores usan la
    taxonomía de `errors` (payloads con clave `error` → el empaquetador marca
    `is_error` en el `CallToolResult`).

    `backend_factory` en vez de la instancia (decisión G1): el arranque del
    backend —`resolve_vault_root()` + `load_config()` en `server._backend()`—
    ocurre DENTRO del handler, bajo `@errors.internal_guard`. Si el composition
    root construye el backend antes de llamar, un fallo ahí escapa al SDK con
    texto libre; con la factory no hay ese punto ciego.

    `embedder_available` (costura R1/T6, REQUIRED para que la precedencia sea
    visible en la firma): `False` ⇒ `E_NO_EMBEDDER` sin construir el backend
    ni mirar el índice — la cadena D7.3 empieza aquí.
    """
    started = time.perf_counter()
    try:
        effective_top_k = budget.effective_top_k(top_k)
        paths.validate_path_filter(path_filter)
    except ValueError as exc:
        return errors.validation_error(str(exc))
    if not embedder_available():
        return errors.no_embedder()  # R1: precede a INDEX_EMPTY y a todo lo demás
    backend = backend_factory()  # arranque BAJO la guarda: un fallo ⇒ INTERNAL (G1)
    try:
        index_models = await backend.index_models()
    except ValueError as exc:
        return errors.validation_error(str(exc))
    if not index_models:
        return errors.index_empty()
    if index_models != {backend.expected_model}:
        return errors.model_mismatch(index_models, backend.expected_model)
    try:
        chunks = await backend.cited_chunks(query, effective_top_k, path_filter)
    except ValueError as exc:
        return errors.validation_error(str(exc))
    except embedder.EmbedderAuthError as exc:
        return errors.api_auth(str(exc))  # str = SOLO el nombre de la env var
    except embedder.EmbedderOfflineError:
        return errors.offline_no_cache()
    except embedder.EmbedderModelError:
        return errors.model_invalid()
    except embedder.EmbedderUnavailableError:
        return errors.no_embedder()
    # El resto (EmbedderApiError ya scrubeado, errores del puerto, cualquier
    # cosa) lo captura el decorador: INTERNAL canónico + traceback al log (G1).
    kept, truncated = budget.apply_budget(chunks)
    results: list[dict[str, object]] = [
        {
            "text": chunk.text,
            "source_path": chunk.source_path,
            "heading": chunk.heading,
            "char_start": chunk.char_start,
            "char_end": chunk.char_end,
            "score": chunk.score,
            "offsets_ref": chunk.offsets_ref,
        }
        for chunk in kept
    ]
    # took_ms se cierra al terminar de ensamblar el payload: desde la ENTRADA
    # del handler (t0) hasta serializar, embed incluido (spec §Presupuestos).
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    return {
        "query": query,
        "took_ms": elapsed_ms,
        "truncated": truncated,
        "results": results,
    }
