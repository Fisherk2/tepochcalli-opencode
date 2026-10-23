"""Resolución del cache de modelo estable FUERA del repo (patrón T6/T8/T9/T10).

Fuentes de verdad:

* specs/spec-embeddings.md + ADR-006 — el binario del embedder
  (`paraphrase-multilingual-MiniLM-L12-v2`, ~470 MB) vive en un cache
  estable, jamás en `obsidian-workspace/.tepochcalli/models/` (payload, D14).
* tasks/todo.md → T11 — «caché HF por revisión pineada» en CI. Corolario
  probado por simulación EN ESTE T11: una ruta hardcodeada en el `/tmp` de un
  solo desarrollador no puede ser un REQUISITO de la suite — un runner de
  GitHub Actions no tiene `/tmp/opencode/tepochcalli-t1-spike/` y la suite
  debe poder correr en verde allí (primera corrida en frío incluida).

Cadena de resolución (en este orden):

1. `HF_HOME` externo si está fijado — CI fija `~/.cache/huggingface` y lo
   persiste con `actions/cache` (clave derivada de `uv.lock`); una máquina
   ajena manda sobre el spike del host de desarrollo.
2. El cache del spike T1 SOLO si ya existe (`is_dir`): evita la re-descarga
   en el host donde se desarrolló; jamás se crea desde cero (antes `mkdir`
   + symlink incondicional reproducía el spike en cada máquina limpia).
3. `~/.cache/huggingface` (el `HF_HOME` nativo de huggingface_hub):
   fallback neutro de máquina para una corrida sin env y sin spike.

`offline_env()` fuerza `HF_HUB_OFFLINE=1` SOLO cuando el snapshot del modelo
ya vive en el cache resuelto: en frío (primera corrida de CI) se permite UNA
descarga —justo la que `actions/cache` persiste— y a partir de ahí la suite
corre sin red, preservando el sello de hermeticidad de M3(b)
(test_pipeline_integration). Un `HF_HUB_OFFLINE` externo se respeta tal cual.
"""

from __future__ import annotations

import os
from pathlib import Path

from tepochcalli_flow.config import DEFAULT_EMBEDDING_MODEL

SPIKE_MODEL_CACHE = Path("/tmp/opencode/tepochcalli-t1-spike/models")
"""Cache estable del spike T1 (MiniLM ~470 MB); solo existe en el host de desarrollo."""

DEFAULT_HF_CACHE = Path.home() / ".cache" / "huggingface"
"""Cache nativo de huggingface_hub — fallback neutro de máquina (HF_HOME por defecto)."""


def resolve_model_cache() -> Path:
    """Cadena `HF_HOME` externo → spike T1 si existe → cache HF nativo."""
    external = os.environ.get("HF_HOME")
    if external:
        return Path(external)
    if SPIKE_MODEL_CACHE.is_dir():
        return SPIKE_MODEL_CACHE
    return DEFAULT_HF_CACHE


def link_model_cache(vault: Path, cache: Path) -> Path:
    """Symlink `<vault>/.tepochcalli/models` → `cache` (el binario vive fuera del repo)."""
    cache.mkdir(parents=True, exist_ok=True)
    models_link = vault / ".tepochcalli" / "models"
    models_link.parent.mkdir(parents=True, exist_ok=True)
    models_link.symlink_to(cache, target_is_directory=True)
    return models_link


def offline_env(cache: Path) -> dict[str, str]:
    """`{"HF_HUB_OFFLINE": "1"}` si el modelo ya está en `cache`; `{}` en frío.

    En frío se permite UNA descarga al cache resuelto (la que CI persiste con
    `actions/cache`); con el modelo cacheado, la suite corre sin red. Un
    `HF_HUB_OFFLINE` externo se respeta sin interpretarlo.
    """
    external = os.environ.get("HF_HUB_OFFLINE")
    if external is not None:
        return {"HF_HUB_OFFLINE": external}
    if _snapshot_cached(cache):
        return {"HF_HUB_OFFLINE": "1"}
    return {}


def _snapshot_cached(cache: Path) -> bool:
    """Indica si el snapshot de MiniLM ya vive en `cache` (layout ST o hub de HF).

    T11 (hallazgo por probe): sentence-transformers 6.x prefija el repo con
    `sentence-transformers/` cuando el id no lleva org — el dir real es
    `models--sentence-transformers--<modelo>`, no `models--<modelo>`. Se
    comprueban ambos slugs (si la config nombra `org/model` ya no hay doble
    prefijo) y ambas raíces: `cache/` (ST usa `SENTENCE_TRANSFORMERS_HOME`
    como raíz de cache hub v1: refs/blobs/snapshots ahí) y `cache/hub/`
    (`HF_HUB_CACHE` por defecto bajo `HF_HOME`; ahí vive Docling).
    """
    model = DEFAULT_EMBEDDING_MODEL.replace("/", "--")
    slugs = (f"models--{model}", f"models--sentence-transformers--{model}")
    return any((root / slug).is_dir() for root in (cache, cache / "hub") for slug in slugs)
