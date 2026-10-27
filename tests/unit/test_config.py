"""Tests del config loader del flow (Phase 1, T3) — escrito en rojo antes del módulo.

Fuentes de verdad de claves y defaults:

* specs/spec-embeddings.md §"Estructura de `tepochcalli.toml` (config/)" (D11):
  MiniLM / 1536 bytes / 192 bytes / top_k 5 y la alternativa litellm comentada.
* specs/spec-rag-engine.md §Embeddings — E1: `[embedding] device`, default "cpu".
* ADR-006: 384 dims para el modelo default (constante, no es clave TOML).
"""

from __future__ import annotations

import logging
import os
import tomllib
from pathlib import Path

import pytest
from tepochcalli_flow import config as flow_config

CONFIG_RELPATH = Path(".tepochcalli/config/tepochcalli.toml")
EXAMPLE_PATH = (
    Path(__file__).resolve().parents[2]
    / "obsidian-workspace"
    / ".tepochcalli"
    / "tepochcalli.toml.example"
)


def _write_config(vault_root: Path, content: str) -> Path:
    """Materializa el `tepochcalli.toml` real dentro del vault temporal."""
    path = vault_root / CONFIG_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _module_messages(caplog: pytest.LogCaptureFixture, level: int = logging.WARNING) -> list[str]:
    """Mensajes emitidos por `tepochcalli_flow.config` en el nivel dado o superior."""
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == "tepochcalli_flow.config" and record.levelno >= level
    ]


def test_defaults_when_no_config_file(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Sin archivo: defaults canónicos completos y silencio de warnings."""
    caplog.set_level(logging.WARNING, logger="tepochcalli_flow.config")

    cfg = flow_config.load_config(tmp_path)

    assert cfg.embedding.provider == "local"
    assert cfg.embedding.model == "paraphrase-multilingual-MiniLM-L12-v2"
    assert flow_config.DEFAULT_EMBEDDING_DIMS == 384  # ADR-006; no es clave TOML
    assert cfg.embedding.device == "cpu"  # E1 (D11)
    assert cfg.embedding.api_key_env == "TEPOCHCALLI_EMBED_API_KEY"
    assert cfg.chunking.max_chunk_size == 1536  # BYTES, no chars (F4/D11)
    assert cfg.chunking.overlap == 192
    assert cfg.search.top_k_default == 5
    assert cfg.models_dir == tmp_path / ".tepochcalli" / "models"
    assert _module_messages(caplog) == []


def test_partial_section_merges_with_defaults(tmp_path: Path) -> None:
    """Una sección parcial no pisa el resto: lo demás conserva sus defaults."""
    _write_config(tmp_path, "[chunking]\nmax_chunk_size = 1024\n")

    cfg = flow_config.load_config(tmp_path)

    assert cfg.chunking.max_chunk_size == 1024  # override aplicado
    assert cfg.chunking.overlap == 192  # default de la misma sección
    assert cfg.embedding.model == "paraphrase-multilingual-MiniLM-L12-v2"
    assert cfg.embedding.device == "cpu"
    assert cfg.search.top_k_default == 5


def test_malformed_toml_warns_and_falls_back_to_defaults(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """TOML malformado nunca lanza: warning + defaults completos."""
    caplog.set_level(logging.WARNING, logger="tepochcalli_flow.config")
    _write_config(tmp_path, "[embedding\nmodel = ")  # sintaxis inválida

    cfg = flow_config.load_config(tmp_path)

    assert cfg == flow_config.load_config(tmp_path / "sin-archivo")
    messages = _module_messages(caplog)
    assert any("malformado" in message for message in messages)


def test_non_utf8_toml_warns_and_falls_back_to_defaults(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Bytes no-UTF-8 en el toml: warning + defaults, nunca lanza (contrato T3)."""
    caplog.set_level(logging.WARNING, logger="tepochcalli_flow.config")
    path = tmp_path / CONFIG_RELPATH
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\xfe[embedding]")

    cfg = flow_config.load_config(tmp_path)

    assert cfg == flow_config.load_config(tmp_path / "sin-archivo")
    assert any("malformado" in message for message in _module_messages(caplog))


def test_empty_model_string_falls_back_to_default(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """`model = ""` se trata como ausente: no sobrevive al merge, va al default."""
    caplog.set_level(logging.WARNING, logger="tepochcalli_flow.config")
    _write_config(tmp_path, '[embedding]\nmodel = ""\ndevice = "cuda"\n')

    cfg = flow_config.load_config(tmp_path)

    assert cfg.embedding.model == "paraphrase-multilingual-MiniLM-L12-v2"
    assert cfg.embedding.device == "cuda"
    assert _module_messages(caplog)


def test_unknown_key_warns_and_is_ignored(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Clave fuera del contrato canónico (p.ej. typo): warning + default del campo."""
    caplog.set_level(logging.WARNING, logger="tepochcalli_flow.config")
    _write_config(tmp_path, "[search]\ntopk = 9\n")

    cfg = flow_config.load_config(tmp_path)

    assert cfg.search.top_k_default == 5
    assert any("desconocida" in message for message in _module_messages(caplog))


def test_unknown_section_warns_and_is_ignored(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Sección fuera del contrato canónico: warning + defaults intactos."""
    caplog.set_level(logging.WARNING, logger="tepochcalli_flow.config")
    _write_config(tmp_path, "[bench]\nfoo = 1\n")

    cfg = flow_config.load_config(tmp_path)

    assert cfg.embedding.model == "paraphrase-multilingual-MiniLM-L12-v2"
    assert any("Sección desconocida" in message for message in _module_messages(caplog))


def test_invalid_provider_falls_back_to_local_but_keeps_sibling_keys(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """`provider` fuera de {local, litellm} → default solo en ese campo, con warning."""
    caplog.set_level(logging.WARNING, logger="tepochcalli_flow.config")
    _write_config(tmp_path, '[embedding]\nprovider = "azure"\ndevice = "cuda"\n')

    cfg = flow_config.load_config(tmp_path)

    assert cfg.embedding.provider == "local"
    assert cfg.embedding.device == "cuda"  # claves válidas hermanas se respetan
    assert any("provider" in message for message in _module_messages(caplog))


def test_invalid_value_type_warns_and_uses_default(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Tipo erróneo (texto donde debe haber entero) → warning + default del campo."""
    caplog.set_level(logging.WARNING, logger="tepochcalli_flow.config")
    _write_config(tmp_path, '[search]\ntop_k_default = "5"\n')

    cfg = flow_config.load_config(tmp_path)

    assert cfg.search.top_k_default == 5
    assert _module_messages(caplog)


def test_api_key_env_value_never_reaches_renderings_or_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """El valor real de la env var no aparece en repr/str/f-string ni en logs; el símbolo sí."""
    sentinel = "sk-SENTINEL-secreto-NO-IMPRIMIBLE"
    monkeypatch.setenv("TEPOCHCALLI_EMBED_API_KEY", sentinel)
    caplog.set_level(logging.DEBUG, logger="tepochcalli_flow.config")
    _write_config(
        tmp_path,
        '[embedding]\nprovider = "litellm"\n'
        'model = "openai/text-embedding-3-small"\n'
        'api_key_env = "TEPOCHCALLI_EMBED_API_KEY"\n',
    )

    cfg = flow_config.load_config(tmp_path)

    for rendering in (repr(cfg), str(cfg), f"{cfg}"):
        assert "TEPOCHCALLI_EMBED_API_KEY" in rendering  # el nombre sí
        assert sentinel not in rendering  # el valor nunca
    logs = "\n".join(_module_messages(caplog, level=logging.DEBUG))
    assert "TEPOCHCALLI_EMBED_API_KEY" in logs  # el nombre sí se loggea
    assert sentinel not in logs


def test_model_cache_env_resolves_under_vault(tmp_path: Path) -> None:
    """`models_dir` y las dos env vars del cache apuntan a `<vault>/.tepochcalli/models`.

    Guarda y restaura las dos claves A MANO (no con `monkeypatch.delenv`):
    pytest no registra nada en su stack de undo cuando la clave NO existe
    (`delitem` solo apenda si `name in dic`), así que el `os.environ[...] =`
    crudo de `apply_model_cache_env` sobreviviría al teardown y fugaría
    `HF_HOME`/`SENTENCE_TRANSFORMERS_HOME` al resto de la suite —
    `resolve_model_cache()` confiaría en un cache fantasma y los hijos con
    `HF_HUB_OFFLINE=1` no encontrarían sus modelos (raíz del fallo de PDFs
    en suite, 2026-10-27).
    """
    saved = {key: os.environ.pop(key, None) for key in ("SENTENCE_TRANSFORMERS_HOME", "HF_HOME")}
    try:
        expected = tmp_path / ".tepochcalli" / "models"

        cfg = flow_config.load_config(tmp_path)
        assert cfg.models_dir == expected

        # El entrypoint llamará a esto ANTES de construir ningún embedder (E1/T3).
        cfg.apply_model_cache_env()

        assert Path(os.environ["SENTENCE_TRANSFORMERS_HOME"]) == expected
        assert Path(os.environ["HF_HOME"]) == expected
        assert expected.is_dir()
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_unreadable_config_file_warns_and_falls_back_to_defaults(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Contrato del loader (nunca lanza): config ilegible → defaults + warning «No se pudo leer».

    Un `tepochcalli.toml` que existe pero no se puede leer produce un `OSError`
    distinto de `FileNotFoundError` (aquí un directorio con el nombre del
    archivo ⇒ `IsADirectoryError`): el arranque del flow no se rompe, se
    descartan TODAS las overrides y el motivo queda en el log para diagnóstico.
    """
    caplog.set_level(logging.WARNING, logger="tepochcalli_flow.config")
    (tmp_path / CONFIG_RELPATH).mkdir(parents=True)  # read_text() → IsADirectoryError

    cfg = flow_config.load_config(tmp_path)

    assert cfg == flow_config.load_config(tmp_path / "sin-archivo")
    assert any("No se pudo leer" in message for message in _module_messages(caplog))


def test_section_that_is_not_a_table_warns_and_is_ignored(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Contrato del loader: una sección que no es tabla TOML se ignora con warning.

    `embedding = "local"` es TOML válido (clave de primer nivel con string),
    pero no es la tabla `[embedding]` del contrato (spec-embeddings.md): se
    descarta la sección entera y se usan los defaults del dataclass, sin
    abortar el arranque ni arrastrar un tipo ajeno al merge.
    """
    caplog.set_level(logging.WARNING, logger="tepochcalli_flow.config")
    _write_config(tmp_path, 'embedding = "local"\n')

    cfg = flow_config.load_config(tmp_path)

    assert cfg.embedding == flow_config.EmbeddingConfig()
    assert any("no es una tabla TOML" in message for message in _module_messages(caplog))


def test_example_file_matches_canonical_template() -> None:
    """El `.example` commiteado reproduce exactamente las claves de la spec (D11)."""
    raw = tomllib.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))

    assert raw["embedding"] == {
        "provider": "local",
        "model": "paraphrase-multilingual-MiniLM-L12-v2",
        "device": "cpu",
    }
    assert raw["chunking"] == {"max_chunk_size": 1536, "overlap": 192}
    assert raw["search"] == {"top_k_default": 5}
