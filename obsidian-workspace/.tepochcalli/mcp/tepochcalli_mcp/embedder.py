"""Fábrica de embedders por provider — hoy SOLO `local` (T6 añadirá litellm/none).

Patrón Strategy + Factory (plan §8, fila T6): el composition root pide un
embedder según `config.embedding.provider`. En T2 existe una sola rama —
`SentenceTransformer` local pineado a `config.MODEL_REVISION`, el único
binario que reproduce los embeddings del índice (spec-embeddings §provenance) —
sin código muerto ni ramas que aún no existen: T6 añadirá `litellm` y `none`
(ADR-007) y aquí creará el dialecto `E_*` correspondiente.

El cache de modelos del vault debe estar aplicado ANTES de construir el corte
(`config.apply_model_cache_env()`, spec-rag-engine §Embeddings E1/T3): los
pesos caen en `<vault>/.tepochcalli/models`, jamás en `~/.cache` del usuario.
"""

from __future__ import annotations

from collections.abc import Callable

from sentence_transformers import SentenceTransformer
from tepochcalli_flow import citation
from tepochcalli_flow.config import MODEL_REVISION, Config


def build_embedder(config: Config) -> Callable[[str], list[float]]:
    """Corte texto→vector del provider configurado (en T2: solo `local`).

    El modelo sale de `citation.model_id(config)` —el mismo id que la fila
    del índice guarda en `model`— y se pinea a `MODEL_REVISION` para que la
    query se vectorice con el MISMO binario que indexó (ADR-006).
    """
    model = SentenceTransformer(
        citation.model_id(config),
        device=config.embedding.device,
        revision=MODEL_REVISION,
    )
    return lambda text: model.encode(text).tolist()
