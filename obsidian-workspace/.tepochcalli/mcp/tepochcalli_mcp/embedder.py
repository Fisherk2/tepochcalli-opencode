"""Hechos del embedder por provider — hoy SOLO `local` real (T6 añadirá litellm/none).

Patrón Strategy + Factory (plan §8, fila T6): el composition root pide un
embedder según `config.embedding.provider`. En T2-T4 existe una sola rama
REAL — `SentenceTransformer` local pineado a `config.MODEL_REVISION`, el único
binario que reproduce los embeddings del índice (spec-embeddings §provenance)
— sin código muerto ni ramas que aún no existen: T6 añadirá `litellm` y
`none` (ADR-007) y aquí creará el dialecto `E_*` correspondiente.

**Módulo LIGERO en import:** `sentence_transformers` (⇒ torch) se importa
DENTRO de `build_embedder` — `tools/rag_status.py` importa `mode`/`is_available`
y el arranque stdio del server no debe pagar torch hasta la primera búsqueda
(mismo criterio de pereza que `_backend()` en `server.py`).

El cache de modelos del vault debe estar aplicado ANTES de construir el corte
(`config.apply_model_cache_env()`, spec-rag-engine §Embeddings E1/T3): los
pesos caen en `<vault>/.tepochcalli/models`, jamás en `~/.cache` del usuario.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from tepochcalli_flow import citation
from tepochcalli_flow.config import MODEL_REVISION, Config

type EmbedderMode = Literal["local", "api", "none"]
"""Vocabulario D7.3/ADR-007 de `rag_status.embedder.mode` (spec §rag_status)."""


def build_embedder(config: Config) -> Callable[[str], list[float]]:
    """Corte texto→vector del provider configurado (en T2: solo `local`).

    El modelo sale de `citation.model_id(config)` —el mismo id que la fila
    del índice guarda en `model`— y se pinea a `MODEL_REVISION` para que la
    query se vectorice con el MISMO binario que indexó (ADR-006). El import de
    `sentence_transformers` vive aquí (perezoso): torch solo en el primer uso.
    """
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(
        citation.model_id(config),
        device=config.embedding.device,
        revision=MODEL_REVISION,
    )
    return lambda text: model.encode(text).tolist()


def mode(config: Config) -> EmbedderMode:
    """Hecho rico D7.3: el `mode` del embedder para `config` — de aquí deriva `is_available`.

    Mapeo (spec §rag_status): `provider = "litellm"` ⇒ `"api"`;
    `"local"` ⇒ `"local"`; `"none"` ⇒ `"none"`.

    **`none` es hoy inalcanzable vía loader:** `flow/config.py` — VEDADO hasta
    T6 (D15, plan §2) — solo acepta `local|litellm` y cualquier otro valor cae
    a default con warning. La rama existe porque un `Config` construido a mano
    (tests: la costura de precedencia) sí lo expresa, y T6/D15 la hará real
    sin cambiar ni esta función ni a sus llamantes.
    """
    provider = config.embedding.provider
    if provider == "litellm":
        return "api"
    if provider == "none":
        return "none"
    return "local"


def is_available(config: Config) -> bool:
    """Indica si `config` tiene embedder utilizable — costura `E_NO_EMBEDDER` (T3).

    Derivada de `mode(config)` (una sola fuente de verdad): `none` ⇒ False;
    `local`/`api` ⇒ True. Para todo config REAL el resultado es True mientras
    el loader no admita `none` (D15 pendiente en T6) — la precedencia
    `E_NO_EMBEDDER > INDEX_EMPTY` ya está implementada en
    `tools/index_refresh.py` y probada con seam FAKE, sin tocar `flow/`.
    """
    return mode(config) != "none"
