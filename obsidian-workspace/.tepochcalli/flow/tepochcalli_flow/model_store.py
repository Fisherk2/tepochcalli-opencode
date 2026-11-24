"""Materialización del snapshot local del embedder — una sola función (T6/D59).

El write path (refresh) y el `embed-check` del CLI llaman aquí para garantizar
`<vault>/.tepochcalli/models/<slug>@<sha>/`. El read path (MCP) **no** llama:
solo exige el snapshot con `snapshot_defect` (`tepochcalli_mcp.embedder.require_local_model`)
y nunca descarga.

**Por qué en el flow y no en el wizard (D25):** el wizard Rust no descarga
modelos; ejecuta el CLI Python (`embed-check`), que es el único que habla con
HuggingFace. La descarga usa `revision=<sha>` y una caché TEMPORAL dentro de
`<models>/`; después `SentenceTransformer.save(<stable>)` materializa el
directorio estable y la temporal se borra. Si el estable ya existe y no está
vacío, no se descarga nada (idempotente).

Firma verificada en el pin: `SentenceTransformer(model_name_or_path, *,
cache_folder=None, revision=None, device=None, ...)` (`sentence_transformers/
sentence_transformer/model.py:154-176`) y `SentenceTransformer.save(path: str,
...)` (`sentence_transformers/base/model.py:715-725`), que crea el directorio y
escribe el modelo reutilizable por `SentenceTransformer(path)`.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Final, Protocol

from .config import Config

_WEIGHT_FILES: Final = ("model.safetensors", "pytorch_model.bin")
"""Pesos que la librería acepta (`SAFE_WEIGHTS_NAME`/`WEIGHTS_NAME` de transformers, pin
verificado): `SentenceTransformer.save()` escribe safetensors.

shortcut: no se reconoce el snapshot shardeado (`model.safetensors.index.json`); MiniLM y
bge-m3 son de un solo fichero — añadirlo si se adopta un modelo con shards.
"""

_HUB_SNAPSHOTS_DIR: Final = "snapshots"
"""Nivel del layout de caché hub de HuggingFace: `models--<slug>/snapshots/<sha>/`."""


class _LoadableModel(Protocol):
    """Superficie mínima que usamos del modelo cargado (solo `save`)."""

    def save(self, path: str) -> None:
        """Escribe el modelo y su config en `path` (crea el directorio)."""
        ...


type ModelLoader = Callable[..., _LoadableModel]
"""Cargador inyectable (`SentenceTransformer` en producción; doble en tests)."""


def is_materialized(config: Config) -> bool:
    """Indica si el snapshot estable existe y NO está vacío (sin tocar red)."""
    path = config.embedding_model_path
    return path.is_dir() and any(path.iterdir())


def snapshot_defect(path: Path, revision: str) -> str | None:
    """Qué le falta al snapshot para que la librería lo cargue; `None` si está completo.

    Comprobación **barata** (sin cargar torch): manifiesto `config.json`, un fichero de
    pesos real (`model.safetensors`, el que escribe `save()`, o `pytorch_model.bin`) y
    —si el snapshot es una caché hub de HuggingFace (`snapshots/<sha>/`, layout real del
    cache)— que la revisión resuelta sea la pineada. Una descarga interrumpida deja el
    directorio con entradas y sin pesos: mirar solo «no vacío» lo daba por bueno (TD-29).
    """
    if not path.is_dir():
        return "no existe"
    if not (path / "config.json").is_file():
        return "falta el manifiesto config.json"
    if not any((path / weight).is_file() for weight in _WEIGHT_FILES):
        return f"faltan los pesos ({' o '.join(_WEIGHT_FILES)})"
    resolved = path.resolve()
    if resolved.parent.name == _HUB_SNAPSHOTS_DIR and resolved.name != revision:
        return f"la revisión del snapshot es {resolved.name}, no la configurada {revision}"
    return None


def ensure_local_model(config: Config, *, loader: ModelLoader | None = None) -> Path:
    """Materializa (si falta) y devuelve el path estable `<models>/<slug>@<sha>/`.

    Idempotente: con el directorio ya poblado no llama al loader. Descarga con
    `revision=<sha>` a una caché temporal dentro de `<models>/`, guarda el
    modelo con `save()` en un staging y lo renombra atómicamente al path
    estable. Las temporales se borran siempre — también si la descarga falla.
    """
    stable = config.embedding_model_path
    if is_materialized(config):
        return stable
    config.models_dir.mkdir(parents=True, exist_ok=True)
    download_cache = Path(tempfile.mkdtemp(prefix=".model-cache-", dir=config.models_dir))
    staging = Path(tempfile.mkdtemp(prefix=".model-staging-", dir=config.models_dir))
    try:
        model = (loader or _default_loader)(
            config.embedding.model,
            device=config.embedding.device,
            revision=config.embedding.revision,
            cache_folder=str(download_cache),
        )
        model.save(str(staging))
        try:
            os.replace(staging, stable)
        except OSError:
            # Carrera con otra materialización: si el ganador dejó el path
            # poblado, ese es el bueno; si no, el fallo es real.
            if is_materialized(config):
                return stable
            raise
        return stable
    finally:
        shutil.rmtree(download_cache, ignore_errors=True)
        if staging.exists():  # el rename exitoso lo movió; si no, se descarta
            shutil.rmtree(staging, ignore_errors=True)


def _default_loader(model: str, *, device: str, revision: str, cache_folder: str) -> _LoadableModel:
    """Carga real con `sentence-transformers` (import perezoso: torch pesa)."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model, device=device, revision=revision, cache_folder=cache_folder)
