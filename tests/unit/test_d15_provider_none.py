"""D15: `provider = "none"` como 3.er valor del loader — corrección de hechos, sin ADR (T6).

Fuentes: tasks/plan.md §2 «Decisiones derivadas» D15 (sin ADR: ADR-007 ya
decidió el estado `none`; lo que faltaba era que el loader pudiera EXPRESARLO);
specs/spec-embeddings.md §`tepochcalli.toml` (enmienda de valores de `provider`);
docs/WORKFLOW.md §8 (entrada D15).

Lo que D15 arregla: hasta T6 `config.py:56 EMBEDDING_PROVIDERS` era
`("local", "litellm")` y `_resolve_embedding` ADVERTÍA y caía al default
`local` — un `provider = "none"` se ejecutaba COMO `local` en silencio
justo cuando la instalación degradada (salida 5 del wizard) lo escribe.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from tepochcalli_flow import config as flow_config
from tepochcalli_mcp import embedder

NONE_TOML = '[embedding]\nprovider = "none"\n'
UNKNOWN_TOML = '[embedding]\nprovider = "gpt-no-existe"\n'


def _write_config(vault: Path, content: str) -> None:
    """Escribe `tepochcalli.toml` en el vault temporal."""
    config_dir = vault / ".tepochcalli" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "tepochcalli.toml").write_text(content, encoding="utf-8")


def test_loader_accepts_none_without_silent_fallback(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """`provider = "none"` se acepta: valor conservado Y sin warning de «provider inválido»."""
    _write_config(tmp_path, NONE_TOML)

    with caplog.at_level(logging.WARNING):
        config = flow_config.load_config(tmp_path)

    assert config.embedding.provider == "none", "D15: none es el 3.er valor, no un default"
    assert "provider inválido" not in caplog.text, "la caída silenciosa a local es lo que D15 quita"


def test_absent_config_still_defaults_to_local(tmp_path: Path) -> None:
    """Sin toml (fichero opcional) → default `local`: el comportamiento de Phase 1 intacto."""
    config = flow_config.load_config(tmp_path)

    assert config.embedding.provider == flow_config.DEFAULT_EMBEDDING_PROVIDER


def test_unknown_provider_still_warns_and_falls_back_to_local(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """El guardrail de Phase 1 NO se toca: valores desconocidos siguen cayendo a `local`."""
    _write_config(tmp_path, UNKNOWN_TOML)

    with caplog.at_level(logging.WARNING):
        config = flow_config.load_config(tmp_path)

    assert config.embedding.provider == flow_config.DEFAULT_EMBEDDING_PROVIDER
    assert "provider inválido" in caplog.text


def test_none_config_keeps_the_other_embedding_defaults(tmp_path: Path) -> None:
    """`none` solo cambia el provider: model/device/api_key_env conservan defaults (D11)."""
    _write_config(tmp_path, NONE_TOML)

    config = flow_config.load_config(tmp_path)

    assert config.embedding.model == flow_config.DEFAULT_EMBEDDING_MODEL
    assert config.embedding.device == flow_config.DEFAULT_EMBEDDING_DEVICE
    assert config.embedding.api_key_env == flow_config.DEFAULT_API_KEY_ENV


def test_real_none_config_drives_the_e_no_embedder_seam() -> None:
    """Costura end-to-end con config REAL (antes solo con `Config` construido a mano)."""
    config = flow_config.Config(
        models_dir=Path("/vault/.tepochcalli/models"),
        embedding=flow_config.EmbeddingConfig(provider="none"),
    )

    assert embedder.mode(config) == "none"
    assert embedder.is_available(config) is False, (
        "is_available deriva de mode: none ⇒ no disponible"
    )
