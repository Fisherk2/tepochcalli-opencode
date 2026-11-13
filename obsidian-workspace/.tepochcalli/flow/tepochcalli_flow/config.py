"""Configuración del flow: carga de `tepochcalli.toml` con fallbacks a defaults (T3).

Fuentes de verdad de claves y defaults:

* specs/spec-embeddings.md §"Estructura de `tepochcalli.toml` (config/)" (D11):
  plantilla canónica — MiniLM / 1536 bytes / 192 bytes / top_k 5.
* specs/spec-rag-engine.md §Embeddings — E1: `[embedding] device`, default `"cpu"`.
* ADR-006: 384 dims para el modelo default (constante, NO es clave TOML).

Política de errores (decisión T3): el loader **nunca lanza**. Archivo ausente =
defaults silenciosos; TOML malformado = warning + defaults (se pierden todas las
overrides); clave/sección desconocida, tipo erróneo o `provider` fuera de
{local, litellm, none} = warning + default de ese campo (las overrides hermanas se
respetan). Todo se loggea con `logging.getLogger(__name__)`.

Config por entorno: además del toml, `load_config` lee `INDEXER_DIR` (raíces
indexables por omisión, `Config.indexer_roots`). `TEPOCHCALLI_TOP_K` (el default
de `search`) NO se lee aquí: lo consume `tepochcalli_mcp.budget` en import,
donde tampoco hay vault del que leer el toml.

Seguridad: dos fuentes de clave, env > fichero (fix cross-layer 2026-10-28). `api_key_env` es el
NOMBRE de la variable; `api_key` es la clave literal que el wizard escribe en el
toml gitignored. Ninguna de las dos se renderiza: `api_key` lleva `repr=False` y
el log del loader solo nombra `api_key_env` (docs/SECURITY.md;
spec-embeddings.md §Security Considerations).

Este módulo es código de dominio: NO importa `cocoindex` ni `lancedb` (test de
arquitectura, T9).
"""

from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import Field, dataclass, field, fields, replace
from pathlib import Path
from typing import Any, ClassVar, Final, Protocol

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
DEFAULT_INDEXER_ROOTS: Final[tuple[str, ...]] = ("00-resources",)
"""Raíces indexadas cuando `INDEXER_DIR` no declara ninguna (`citation.RESOURCES_DIR`).

Literal propio porque `citation` importa este módulo (el dominio apunta hacia
dentro): un import inverso sería circular.
"""

INDEXER_DIR_ENV: Final = "INDEXER_DIR"
"""Raíces a indexar declaradas en `opencode.json` (`mcp.servers.*.environment`).

Multi-valor separado por COMAS — nunca `os.pathsep`: `:` colisiona con `C:\\`.
Las rutas son relativas al vault; el borde (`paths.validate_roots`) rechaza las
que caen fuera (B′).
"""

TOP_K_ENV: Final = "TEPOCHCALLI_TOP_K"
"""Nombre de la env con el default de `search.top_k` (`opencode.json` → `environment`).

La consume `tepochcalli_mcp.budget` en import (aquí no: el toml no la declara).
"""

MODEL_REVISION: Final = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
"""SHA del commit del modelo HF default (`paraphrase-multilingual-MiniLM-L12-v2`,
obtenido del API de HuggingFace 2026-10-23). Es el default de
`[embedding].revision`; ambos caminos (write y read) materializan y cargan el
MISMO directorio `<models>/<slug>@<sha>/` (T6/D59)."""


def model_slug(model: str) -> str:
    """Nombre de directorio seguro para un id de modelo (sin `/` ni separadores).

    Los ids de HuggingFace pueden llevar `org/nombre` (`BAAI/bge-m3`): el `/`
    se sustituye por `__` para que `<models>/<slug>@<sha>/` sea UN nivel de
    directorio y no una ruta anidada. La fórmula la comparte el wizard (F6) al
    materializar el modelo.
    """
    return model.replace("/", "__")


EMBEDDING_PROVIDERS: Final = ("local", "litellm", "none")
"""Valores aceptados de `[embedding].provider` — `none` es el 3.er valor (D15, T6).

`none` (instalación degradada, salida 5 del wizard) era inexpressable hasta
T6: el loader lo advertía y caía a `local` EN SILENCIO justamente cuando la
config degradada lo escribe. Es corrección de hechos (ADR-007 ya había
decidido el estado `none`) ⇒ sin ADR nuevo (plan §2 D15).
"""
_KNOWN_SECTIONS: Final = ("embedding", "chunking")


@dataclass(frozen=True)
class EmbeddingConfig:
    """Sección `[embedding]` — spec-embeddings.md §tepochcalli.toml; device: E1 (D11).

    `api_key_env` es el nombre de la variable y `api_key` la clave literal que
    el wizard escribe en el toml gitignored; solo se usan con
    `provider = "litellm"` y SIEMPRE vía `resolve_api_key()`.
    """

    provider: str = DEFAULT_EMBEDDING_PROVIDER
    model: str = DEFAULT_EMBEDDING_MODEL
    revision: str = MODEL_REVISION
    """SHA de la revisión HF del modelo — `[embedding].revision` (T6/D59).

    El default es el SHA del MiniLM default; un modelo custom DEBE declarar su
    propia revisión. El path estable del snapshot se deriva de `model+revision`.
    """

    device: str = DEFAULT_EMBEDDING_DEVICE
    api_key_env: str = DEFAULT_API_KEY_ENV
    api_key: str | None = field(default=None, repr=False)
    """Clave LITERAL del toml (el wizard la escribe en el fichero gitignored).

    `repr=False`: ni `repr(EmbeddingConfig())` ni `repr(Config())` la exponen —
    en logs sale solo el símbolo `api_key_env`. Se resuelve siempre vía
    `resolve_api_key()`, nunca leyendo el campo a pelo.
    """

    def resolve_api_key(self) -> str | None:
        """Clave del proveedor: env nombrada por `api_key_env`, si no `api_key`, si no `None`.

        Única implementación de la precedencia (env > fichero) para los dos
        readers (`app.py` y `tepochcalli_mcp/embedder.py`). Recorta espacios y
        trata la cadena vacía como ausente; devuelve SOLO el valor a mano, que
        nunca debe concatenarse en mensajes, `repr` ni logs.
        """
        from_env = os.environ.get(self.api_key_env, "").strip()
        if from_env:
            return from_env
        return (self.api_key or "").strip() or None


@dataclass(frozen=True)
class ChunkingConfig:
    """Sección `[chunking]` — en BYTES, no chars (F4/D11, spec-rag-engine.md §Chunking)."""

    max_chunk_size: int = DEFAULT_MAX_CHUNK_SIZE
    overlap: int = DEFAULT_CHUNK_OVERLAP


@dataclass(frozen=True)
class Config:
    """Configuración resuelta del flow para un vault.

    La igualdad compara las secciones parseadas, no `models_dir` (dos configs con
    la misma configuración sobre raíces de vault distintas son iguales).
    """

    models_dir: Path = field(compare=False)
    embedding: EmbeddingConfig = EmbeddingConfig()
    chunking: ChunkingConfig = ChunkingConfig()
    indexer_roots: tuple[str, ...] = DEFAULT_INDEXER_ROOTS
    """Raíces indexables por omisión (`INDEXER_DIR`), relativas al vault (ADR-010)."""

    @property
    def embedding_model_path(self) -> Path:
        """Snapshot local estable del embedder: `<models>/<slug>@<sha>/` (T6/D59).

        Es la ÚNICA referencia de ambos caminos: el write path materializa/carga
        este directorio y el read path lo exige (sin descargar). `embedding.model`
        sigue siendo el ID para mostrar/`rag_status`; el SHA viene de
        `embedding.revision`.
        """
        return self.models_dir / f"{model_slug(self.embedding.model)}@{self.embedding.revision}"

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

    Migración: `[search]` ya no es una sección del contrato (`top_k` se declara
    en `opencode.json` vía `TEPOCHCALLI_TOP_K`); un toml viejo que la traiga
    solo recibe el warning de sección desconocida — el loader sigue sin lanzar.
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
        indexer_roots=_indexer_roots_from_env(),
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


def _indexer_roots_from_env() -> tuple[str, ...]:
    """Raíces de `INDEXER_DIR`: split por `,`, `strip()` y descarta vacíos.

    Ausente, vacía o solo separadores ⇒ `DEFAULT_INDEXER_ROOTS`. No se valida
    ninguna ruta aquí (el loader no hace I/O ni lanza): el borde MCP
    (`paths.validate_roots`) exige existencia y que la raíz caiga dentro del
    vault, aceptando una absoluta que resuelva dentro (B′/D47).
    """
    raw = os.environ.get(INDEXER_DIR_ENV, "")
    roots = tuple(part.strip() for part in raw.split(",") if part.strip())
    return roots or DEFAULT_INDEXER_ROOTS


def _read_toml(config_path: Path) -> dict[str, object]:
    """Devuelve el TOML parseado o `{}` si el archivo falta, es ilegible o está malformado."""
    try:
        raw: dict[str, object] = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except UnicodeDecodeError as exc:
        logger.warning(
            "TOML malformado en %s (%s); se descartan las overrides y se usan los defaults",
            config_path,
            exc,
        )
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


class _DataclassSection(Protocol):
    """Protocolo estructural de una sección de config (siempre un dataclass frozen).

    `dataclasses.fields`/`dataclasses.replace` exigen `DataclassInstance` —el
    protocolo interno de typeshed— y una `SectionT` sin cota no lo satisface
    (`--strict` lo rechaza en el borde). Se declara aquí el ÚNICO miembro que
    ese protocolo inspecciona, de modo que la cota del TypeVar de
    `_merge_section` sea real sin relajar el chequeo ni introducir `cast`.
    """

    __dataclass_fields__: ClassVar[dict[str, Field[Any]]]


def _merge_section[SectionT: _DataclassSection](
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
        if expected is type(None):
            expected = str  # campo `str | None` (default None): solo acepta texto
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
    """Mergea `[embedding]` y valida `provider` ∈ {local, litellm, none} (spec, D15)."""
    embedding = _merge_section("embedding", EmbeddingConfig(), values, config_path)
    if not embedding.model:  # `model = ""` se trata como ausente (fallback al default)
        logger.warning(
            "model vacío en [embedding] de %s; se usa el default '%s'",
            config_path,
            DEFAULT_EMBEDDING_MODEL,
        )
        embedding = replace(embedding, model=DEFAULT_EMBEDDING_MODEL)
    if not embedding.revision:  # `revision = ""` ⇒ SHA del modelo default
        logger.warning(
            "revision vacía en [embedding] de %s; se usa el SHA default '%s'",
            config_path,
            MODEL_REVISION,
        )
        embedding = replace(embedding, revision=MODEL_REVISION)
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
