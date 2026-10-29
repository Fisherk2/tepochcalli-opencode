"""Fábrica de provider del flow (T6): Strategy en `app.py` — local | litellm | none.

Fuentes ancladas contra la fuente INSTALADA (source-driven-development):

* `cocoindex==1.0.25`, `venv/.../cocoindex/ops/litellm.py` —
  `LiteLLMEmbedder(model, *, max_inflight_requests=None, timeout=None, **kwargs)`:
  los `**kwargs` se pasan «to every ``litellm.aembedding`` call (e.g.,
  ``api_key``…)», así que `LiteLLMEmbedder(model, api_key=…)` es el camino
  canónico del plan §6 T6. El constructor NO hace red: la dim se descubre con
  un embed real SOLO dentro de `__coco_vector_schema__` (durante el update,
  con los retries de cocoindex).
* `cocoindex/ops/sentence_transformers.py` — `SentenceTransformerEmbedder(
  model_name_or_path, *, device, trust_remote_code)` con atributos
  `_model_name_or_path`/`_device` (los pinna este test).
* `specs/spec-embeddings.md` §Matriz + plan §6 T6 — `none` ⇒ error tipado en
  el flow (el MCP emite `E_NO_EMBEDDER` ANTES de llegar aquí); `litellm` sin
  la clave de `api_key_env` ⇒ error tipado cuyo mensaje nombra SOLO la
  variable, nunca el valor (riesgo crítico plan §9).
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from cocoindex.ops.sentence_transformers import SentenceTransformerEmbedder
from tepochcalli_flow import app as flow_app
from tepochcalli_flow.config import (
    DEFAULT_API_KEY_ENV,
    DEFAULT_EMBEDDING_DEVICE,
    DEFAULT_EMBEDDING_MODEL,
    Config,
    EmbeddingConfig,
)

LITELLM_MODEL = "openai/text-embedding-3-small"
FAKE_KEY = "sk-t6-fake-key-nunca-real"
LEAK_SECRET = "sk-LEAK-TEST-fichero-flow"

LLM_MODULES = frozenset({"litellm", "openai", "anthropic"})


@pytest.fixture(autouse=True)
def _scrub_llm_modules() -> Iterator[None]:
    """Estos tests EJERCITAN la rama litellm (exige importar `litellm` en serio).

    El canario «cero LLM» de Phase 1 (M3) afirma que NINGÚN cliente LLM está
    en `sys.modules` — una verdad sobre el FLUJO que el HARNESS de T6 rompería
    para siempre: este teardown restituye la sesión tras cada test, y el import
    de `LiteLLMEmbedder` vive DENTRO de los tests (nunca a la colección) para
    que una corrida con `-k` que excluya este fichero ni siquiera lo cargue.
    """
    yield
    for name in [n for n in list(sys.modules) if n.split(".")[0] in LLM_MODULES]:
        del sys.modules[name]


def _config(
    provider: str, *, model: str = DEFAULT_EMBEDDING_MODEL, api_key: str | None = None
) -> Config:
    """Config de prueba — igual que la del loader, construida directa (sin toml)."""
    return Config(
        models_dir=Path("/vault/.tepochcalli/models"),
        embedding=EmbeddingConfig(provider=provider, model=model, api_key=api_key),
    )


def test_local_provider_builds_sentence_transformer_with_model_and_device() -> None:
    """`local` ⇒ `SentenceTransformerEmbedder(model, device=…)` pineado (ADR-006/E1)."""
    embedder = flow_app._build_embedder(_config("local"))

    assert isinstance(embedder, SentenceTransformerEmbedder)
    assert embedder._model_name_or_path == DEFAULT_EMBEDDING_MODEL
    assert embedder._device == DEFAULT_EMBEDDING_DEVICE


def test_litellm_provider_builds_lite_llm_embedder_with_key_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`litellm` ⇒ `LiteLLMEmbedder(model, api_key=…)` con la clave de `api_key_env`.

    La clave sale SOLO del entorno (config guarda el nombre de la variable,
    jamás el valor — spec-embeddings §Security); el constructor es inerte
    (sin llamada a la API ⇒ cero red en el test). Import perezoso del tipo:
    cargar `litellm` a la colección contaminaría los canarios M3 (ver fixture).
    """
    from cocoindex.ops.litellm import LiteLLMEmbedder

    monkeypatch.setenv(DEFAULT_API_KEY_ENV, FAKE_KEY)

    embedder = flow_app._build_embedder(_config("litellm", model=LITELLM_MODEL))

    assert isinstance(embedder, LiteLLMEmbedder)
    assert embedder.__coco_memo_key__() == (LITELLM_MODEL, {"api_key": FAKE_KEY})


def test_litellm_provider_reads_the_key_from_the_toml_when_the_env_is_unset(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Sin env var, `[embedding].api_key` (lo que escribe el wizard) alimenta el embedder.

    Prove-It del defecto cross-layer: `swap.rs`/`embedder_menu.rs` persisten la
    clave literal en el toml gitignored y este reader solo miraba el entorno ⇒
    `provider = "litellm"` roto de punta a punta.
    """
    from cocoindex.ops.litellm import LiteLLMEmbedder

    monkeypatch.delenv(DEFAULT_API_KEY_ENV, raising=False)

    embedder = flow_app._build_embedder(
        _config("litellm", model=LITELLM_MODEL, api_key=LEAK_SECRET)
    )

    assert isinstance(embedder, LiteLLMEmbedder)
    assert embedder.__coco_memo_key__() == (LITELLM_MODEL, {"api_key": LEAK_SECRET})
    assert LEAK_SECRET not in caplog.text


def test_litellm_provider_prefers_the_env_key_over_the_toml(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Un único resolver (env > fichero): la misma precedencia que el loader."""
    from cocoindex.ops.litellm import LiteLLMEmbedder

    env_secret = "sk-LEAK-TEST-entorno-gana"
    monkeypatch.setenv(DEFAULT_API_KEY_ENV, env_secret)

    embedder = flow_app._build_embedder(
        _config("litellm", model=LITELLM_MODEL, api_key=LEAK_SECRET)
    )

    assert isinstance(embedder, LiteLLMEmbedder)
    assert embedder.__coco_memo_key__() == (LITELLM_MODEL, {"api_key": env_secret})
    assert LEAK_SECRET not in caplog.text


def test_litellm_without_the_env_key_raises_typed_error_naming_only_the_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sin `api_key_env` en el entorno ⇒ error tipado, SIN red y SIN nombrar valores.

    El chequeo es un `os.environ.get` — nunca se llega a litellm. El mensaje
    nombra SOLO el nombre de la variable; una cebo en OTRA variable demuestra
    que ningún valor de clave puede filtrarse.
    """
    monkeypatch.delenv(DEFAULT_API_KEY_ENV, raising=False)
    monkeypatch.setenv("OTRA_VAR_CON_CLAVE", FAKE_KEY)  # cebo

    with pytest.raises(flow_app.EmbeddingApiKeyMissingError) as exc_info:
        flow_app._build_embedder(_config("litellm", model=LITELLM_MODEL))

    message = str(exc_info.value)
    assert DEFAULT_API_KEY_ENV in message, "nombra QUÉ variable falta (accionable)"
    # Veraz sobre la fuente: el fallback del fichero también es una vía de clave.
    assert "api_key" in message
    assert FAKE_KEY not in message
    assert FAKE_KEY not in repr(exc_info.value)


def test_none_provider_raises_typed_error_without_building_anything() -> None:
    """`none` (D15) ⇒ error tipado en el flow: nada se construye a medias."""
    with pytest.raises(flow_app.EmbedderNotConfiguredError):
        flow_app._build_embedder(_config("none"))
