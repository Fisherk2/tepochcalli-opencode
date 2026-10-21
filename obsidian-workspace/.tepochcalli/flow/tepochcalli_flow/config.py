"""Configuración del flow: carga de `tepochcalli.toml` con fallbacks a defaults (T3).

Fuentes de verdad de claves y defaults:

* specs/spec-embeddings.md §"Estructura de `tepochcalli.toml` (config/)" (D11):
  plantilla canónica — MiniLM / 1536 bytes / 192 bytes / top_k 5.
* specs/spec-rag-engine.md §Embeddings — E1: `[embedding] device`, default `"cpu"`.
* ADR-006: 384 dims para el modelo default (constante, NO es clave TOML).

Política de errores (decisión T3): el loader **nunca lanza**. Archivo ausente =
defaults silenciosos; TOML malformado = warning + defaults (se pierden todas las
overrides); clave/sección desconocida, tipo erróneo o `provider` fuera de
{local, litellm} = warning + default de ese campo (las overrides hermanas se
respetan). Todo se loggea con `logging.getLogger(__name__)`.

Seguridad: `api_key_env` es solo el NOMBRE de una variable de entorno — este
módulo jamás lee su valor, por lo que ni `repr` ni logs pueden filtrarlo
(docs/SECURITY.md; spec-embeddings.md §Security Considerations).

Este módulo es código de dominio: NO importa `cocoindex` ni `lancedb` (test de
arquitectura, T9).
"""

from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)

CONFIG_RELPATH: Final = Path(".tepochcalli/config/tepochcalli.toml")
MODELS_RELPATH: Final = Path(".tepochcalli/models")

DEFAULT_EMBEDDING_PROVIDER: Final = "local"
DEFAULT_EMBEDDING_MODEL: Final = "paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_EMBEDDING_DIMS: Final = 384
DEFAULT_EMBEDDING_DEVICE: Final = "cpu"
DEFAULT_API_KEY_ENV: Final = "TEPOCHCALLI_EMBED_API_KEY"
DEFAULT_MAX_CHUNK_SIZE: Final = 1536
DEFAULT_CHUNK_OVERLAP: Final = 192
DEFAULT_TOP_K: Final = 5

EMBEDDING_PROVIDERS: Final = ("local", "litellm")
_KNOWN_SECTIONS: Final = ("embedding", "chunking", "search")


@dataclass(frozen=True)
class EmbeddingConfig:
    """Sección `[embedding]` — spec-embeddings.md §tepochcalli.toml; device: E1 (D11).

    `api_key_env` solo se consulta con `provider = "litellm"` y aquí se guarda
    únicamente el nombre de la variable, nunca su valor.
    """

    provider: str = DEFAULT_EMBEDDING_PROVIDER
    model: str = DEFAULT_EMBEDDING_MODEL
    device: str = DEFAULT_EMBEDDING_DEVICE
    api_key_env: str = DEFAULT_API_KEY_ENV


@dataclass(frozen=True)
class ChunkingConfig:
    """Sección `[chunking]` — en BYTES, no chars (F4/D11, spec-rag-engine.md §Chunking)."""

    max_chunk_size: int = DEFAULT_MAX_CHUNK_SIZE
    overlap: int = DEFAULT_CHUNK_OVERLAP


@dataclass(frozen=True)
class SearchConfig:
    """Sección `[search]` — spec-mcp-server.md §presupuestos."""

    top_k_default: int = DEFAULT_TOP_K


@dataclass(frozen=True)
class Config:
    """Configuración resuelta del flow para un vault.

    La igualdad compara las secciones parseadas, no `models_dir` (dos configs con
    la misma configuración sobre raíces de vault distintas son iguales).
    """

    models_dir: Path = field(compare=False)
    embedding: EmbeddingConfig = EmbeddingConfig()
    chunking: ChunkingConfig = ChunkingConfig()
    search: SearchConfig = SearchConfig()

    def apply_model_cache_env(self) -> None:
        """Fija el cache de modelos del vault en el entorno del proceso.

        De llamarse ANTES de construir cualquier embedder (entrypoint/lifespan,
        spec-rag-engine.md §Embeddings — E1/T3): `SENTENCE_TRANSFORMERS_HOME` y
        `HF_HOME` apuntan a `<vault>/.tepochcalli/models` para que la descarga
        ocurra una vez bajo el vault autocontenido y nunca en `~/.cache`
        (spec-embeddings.md §Cache de modelos y §Alternatives Considered).
        Crea el directorio si no existe.
        """
        self.models_dir.mkdir(parents=True, exist_ok=True)
        os.environ["SENTENCE_TRANSFORMERS_HOME"] = str(self.models_dir)
        os.environ["HF_HOME"] = str(self.models_dir)


def load_config(vault_root: Path) -> Config:
    """Resuelve la config del flow para `vault_root` (ver docstring del módulo).

    Lee `<vault_root>/.tepochcalli/config/tepochcalli.toml` (opcional) y lo mergea
    sobre los defaults canónicos; devuelve un `Config` inmutable listo para el
    entrypoint, que debe llamar a `config.apply_model_cache_env()` antes de
    construir el embedder.
    """
    config_path = vault_root / CONFIG_RELPATH
    raw = _read_toml(config_path)
    _warn_unknown_sections(raw, config_path)
    resolved = Config(
        models_dir=vault_root / MODELS_RELPATH,
        embedding=_resolve_embedding(_section(raw, "embedding", config_path), config_path),
        chunking=_merge_section(
            "chunking", ChunkingConfig(), _section(raw, "chunking", config_path), config_path
        ),
        search=_merge_section(
            "search", SearchConfig(), _section(raw, "search", config_path), config_path
        ),
    )
    logger.debug(
        "Config de %s: provider=%s model=%s device=%s api_key_env=%s "
        "(solo se propaga el nombre de la variable, jamás su valor)",
        config_path,
        resolved.embedding.provider,
        resolved.embedding.model,
        resolved.embedding.device,
        resolved.embedding.api_key_env,
    )
    return resolved


def _read_toml(config_path: Path) -> dict[str, object]:
    """Devuelve el TOML parseado o `{}` si el archivo falta, es ilegible o está malformado."""
    try:
        raw: dict[str, object] = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as exc:
        logger.warning(
            "TOML malformado en %s (%s); se descartan las overrides y se usan los defaults",
            config_path,
            exc,
        )
        return {}
    except OSError as exc:
        logger.warning("No se pudo leer %s (%s); se usan los defaults", config_path, exc)
        return {}
    return raw


def _warn_unknown_sections(raw: dict[str, object], config_path: Path) -> None:
    """Advierte sobre secciones fuera del contrato canónico (spec-embeddings.md)."""
    for name in raw:
        if name not in _KNOWN_SECTIONS:
            logger.warning(
                "Sección desconocida [%s] en %s; ignorada (contrato: spec-embeddings.md)",
                name,
                config_path,
            )


def _section(raw: dict[str, object], name: str, config_path: Path) -> dict[str, object]:
    """Extrae la tabla TOML de una sección conocida; `{}` si ausente o no-tabla."""
    value = raw.get(name)
    if value is None:
        return {}
    if not isinstance(value, dict):
        logger.warning("La sección [%s] de %s no es una tabla TOML; ignorada", name, config_path)
        return {}
    return value


def _merge_section[SectionT](
    section_name: str, defaults: SectionT, values: dict[str, object], config_path: Path
) -> SectionT:
    """Aplica las overrides válidas de una sección sobre sus defaults, warning por clave mala."""
    known_fields = {item.name for item in fields(defaults)}
    updates: dict[str, object] = {}
    for key, value in values.items():
        if key not in known_fields:
            logger.warning(
                "Clave desconocida '%s' en [%s] de %s; ignorada", key, section_name, config_path
            )
            continue
        expected = type(getattr(defaults, key))
        if not _matches_type(value, expected):
            logger.warning(
                "Valor de '%s' en [%s] de %s: se esperaba %s y llegó %s; se usa el default",
                key,
                section_name,
                config_path,
                expected.__name__,
                type(value).__name__,
            )
            continue
        updates[key] = value
    return replace(defaults, **updates)


def _matches_type(value: object, expected: type) -> bool:
    """Comprueba el tipo de una override contra el default (`bool` no cuenta como `int`)."""
    if expected is int:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, expected)


def _resolve_embedding(values: dict[str, object], config_path: Path) -> EmbeddingConfig:
    """Mergea `[embedding]` y valida `provider` ∈ {local, litellm} (spec-embeddings.md)."""
    embedding = _merge_section("embedding", EmbeddingConfig(), values, config_path)
    if embedding.provider not in EMBEDDING_PROVIDERS:
        logger.warning(
            "provider inválido '%s' en [embedding] de %s; se usa el default '%s' (valores: %s)",
            embedding.provider,
            config_path,
            DEFAULT_EMBEDDING_PROVIDER,
            ", ".join(EMBEDDING_PROVIDERS),
        )
        return replace(embedding, provider=DEFAULT_EMBEDDING_PROVIDER)
    return embedding
