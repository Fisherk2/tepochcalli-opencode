"""T6/D59: un solo path local del modelo para write y read, materializado una vez.

Fuentes de verdad:

* `specs/spec-rag-engine.md` §Embeddings — un solo embedder para indexar y para
  consultar; la referencia es el snapshot local `<models>/<slug>@<sha>/`.
* `tasks/todo.md` → T6 AC (a)(b): write y read resuelven **el mismo path**, no
  solo el mismo nombre; el modelo se materializa una vez y es idempotente.
* Pin instalado: `SentenceTransformer(model, revision=, cache_folder=).save(path)`
  (`sentence_transformers/sentence_transformer/model.py:154-176`,
  `sentence_transformers/base/model.py:715-725`).

Los tests NO descargan: el loader se inyecta con un doble que escribe un
marcador en el directorio estable.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
from tepochcalli_flow import app as flow_app
from tepochcalli_flow import model_store
from tepochcalli_flow.config import Config, EmbeddingConfig
from tepochcalli_mcp import embedder

MODEL = "org/custom-model"
REVISION = "abc123"


OTHER_REVISION = "0ld5ha"


def _write_snapshot(path: Path, *, weights: str = "model.safetensors") -> Path:
    """Snapshot mínimo cargable por `SentenceTransformer(path)`: manifiesto + pesos."""
    path.mkdir(parents=True, exist_ok=True)  # `save()` recibe un staging ya creado
    (path / "config.json").write_text("{}", encoding="utf-8")
    (path / weights).write_bytes(b"pesos")
    return path


class _FakeModel:
    """Doble del modelo cargado: `save` deja un snapshot cargable (config + pesos)."""

    def save(self, path: str) -> None:
        _write_snapshot(Path(path))


class _FakeOp:
    """Doble mínimo de la op async de cocoindex (no se ejecuta en este test)."""

    async def embed(self, _text: str) -> object:
        return [0.0]


def _config(tmp_path: Path) -> Config:
    """Config del vault temporal con el modelo/revisión custom del test."""
    return Config(
        models_dir=tmp_path / ".tepochcalli" / "models",
        embedding=EmbeddingConfig(provider="local", model=MODEL, revision=REVISION),
    )


def _never_api(_model: str, _key: str) -> _FakeOp:
    raise AssertionError("la rama local no construye la op de API")


def test_stable_path_is_slug_at_sha_under_models(tmp_path: Path) -> None:
    """`<models>/<slug>@<sha>/`: el `/` del id se sustituye por `__` (T6)."""
    config = _config(tmp_path)

    assert config.embedding_model_path == (
        tmp_path / ".tepochcalli" / "models" / "org__custom-model@abc123"
    )
    assert config.embedding.model == MODEL, "`model` sigue siendo el id para mostrar"


def test_ensure_local_model_materializes_once_and_cleans_the_temporaries(
    tmp_path: Path,
) -> None:
    """La materialización es idempotente y no deja cachés temporales dentro de `models/`."""
    config = _config(tmp_path)
    calls: list[tuple[str, dict[str, str]]] = []

    def _loader(model: str, **kwargs: str) -> _FakeModel:
        calls.append((model, dict(kwargs)))
        return _FakeModel()

    written = model_store.ensure_local_model(config, loader=_loader)
    again = model_store.ensure_local_model(config, loader=_loader)

    assert written == config.embedding_model_path
    assert again == written
    assert (written / "config.json").is_file()
    assert len(calls) == 1, "la segunda llamada ve el snapshot y no vuelve a cargar"
    assert calls[0][0] == MODEL
    assert calls[0][1]["revision"] == REVISION, "el snapshot se descarga pineado"
    assert not list(config.models_dir.glob(".model-*")), "caché/staging temporales borradas"


def test_write_and_read_resolve_the_exact_same_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Write (`app`) y read (`embedder.build_read_cut`) reciben el MISMO path estable."""
    config = _config(tmp_path)
    written = model_store.ensure_local_model(config, loader=lambda _m, **_k: _FakeModel())

    read_paths: list[Path] = []
    cut = embedder.build_read_cut(
        config,
        local_op_factory=lambda path, _device: read_paths.append(path) or _FakeOp(),
        api_op_factory=_never_api,
    )
    assert callable(cut)

    write_paths: list[str] = []
    monkeypatch.setattr(
        flow_app,
        "SentenceTransformerEmbedder",
        lambda path, device=None: write_paths.append(path) or object(),
    )
    flow_app._build_embedder(config)

    assert read_paths == [written], "el read path exige el path estable materializado"
    assert write_paths == [str(written)], "el write path carga el MISMO path"
    assert str(written) != MODEL, "no se pasa el id del modelo a la op"
    assert written.name.endswith(f"@{REVISION}")


# --- ramas de fallo de la materialización (T6, cobertura del hueco 79 %) ---------------


def test_empty_stable_directory_is_materialized_not_accepted(tmp_path: Path) -> None:
    """Un `<slug>@<sha>/` vacío NO es un snapshot válido: se materializa."""
    config = _config(tmp_path)
    config.embedding_model_path.mkdir(parents=True)  # existe, pero vacío
    calls: list[str] = []

    def _loader(model: str, **_kwargs: str) -> _FakeModel:
        calls.append(model)
        return _FakeModel()

    written = model_store.ensure_local_model(config, loader=_loader)

    assert written == config.embedding_model_path
    assert calls == [MODEL], "un directorio vacío no puede tomarse por materializado"
    assert (written / "config.json").is_file()


def test_rename_failure_propagates_and_cleans_the_temporaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fallo al publicar el staging ⇒ el error sube y no quedan temporales ni path parcial."""
    config = _config(tmp_path)

    def _fail_replace(_src: Path, _dst: Path) -> None:
        raise OSError("rename/publish failed")

    monkeypatch.setattr(model_store.os, "replace", _fail_replace)

    with pytest.raises(OSError, match="rename/publish failed"):
        model_store.ensure_local_model(config, loader=lambda _m, **_k: _FakeModel())

    assert not config.embedding_model_path.exists(), "no se publica un snapshot a medias"
    assert not list(config.models_dir.glob(".model-*")), "staging y caché temporales borrados"


def test_rename_race_with_a_winner_returns_the_materialized_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si otro proceso publicó el path antes del rename, se acepta el ganador (idempotencia)."""
    config = _config(tmp_path)
    stable = config.embedding_model_path

    def _race(_src: Path, dst: Path) -> None:
        Path(dst).mkdir(parents=True)
        (Path(dst) / "winner.json").write_text("{}", encoding="utf-8")
        raise OSError("destination exists (race)")

    monkeypatch.setattr(model_store.os, "replace", _race)

    written = model_store.ensure_local_model(config, loader=lambda _m, **_k: _FakeModel())

    assert written == stable
    assert (stable / "winner.json").is_file(), "se devuelve el snapshot del ganador"
    assert not (stable / "config.json").exists(), "el staging perdedor no se mezcla"
    assert not list(config.models_dir.glob(".model-*"))


def test_loader_failure_cleans_the_temporaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un fallo del loader no deja `.model-cache-*` ni `.model-staging-*` dentro de `models/`."""
    config = _config(tmp_path)
    calls: list[tuple[Path, bool]] = []
    real_rmtree = model_store.shutil.rmtree

    def _tracking_rmtree(path: str | Path, *, ignore_errors: bool = False) -> None:
        calls.append((Path(path), ignore_errors))
        real_rmtree(path, ignore_errors=ignore_errors)

    monkeypatch.setattr(model_store.shutil, "rmtree", _tracking_rmtree)

    def _boom(_model: str, **_kwargs: str) -> _FakeModel:
        raise RuntimeError("download failed")

    with pytest.raises(RuntimeError, match="download failed"):
        model_store.ensure_local_model(config, loader=_boom)

    assert not list(config.models_dir.glob(".model-*"))
    assert len(calls) == 2, "se limpian las DOS temporales (caché y staging)"
    assert all(ignore_errors for _path, ignore_errors in calls), (
        "la limpieza no puede enmascarar el fallo del loader con un error de borrado"
    )


def test_default_loader_pins_the_revision_and_the_temp_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El loader real se llama con `revision=<sha>` y `cache_folder` dentro de `models/`."""
    config = _config(tmp_path)
    recorded: dict[str, object] = {}

    class _FakeSentenceTransformer:
        def __init__(self, model: str, **kwargs: object) -> None:
            recorded["model"] = model
            recorded.update(kwargs)

        def save(self, path: str) -> None:
            Path(path, "config.json").write_text("{}", encoding="utf-8")

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        types.SimpleNamespace(SentenceTransformer=_FakeSentenceTransformer),
    )

    written = model_store.ensure_local_model(config)

    assert written == config.embedding_model_path
    assert recorded["model"] == MODEL
    assert recorded["revision"] == REVISION, "el snapshot se descarga pineado"
    assert str(recorded["cache_folder"]).startswith(str(config.models_dir))
    assert recorded["device"] == config.embedding.device
    assert not list(config.models_dir.glob(".model-*"))


# --- TD-29: el read path exige el snapshot COMPLETO, no un directorio con algo -------------


@pytest.mark.parametrize("present", [["config.json"], ["model.safetensors"]])
def test_incomplete_snapshot_raises_model_invalid(tmp_path: Path, present: list[str]) -> None:
    """Descarga interrumpida: el directorio tiene algo, pero no lo que la carga exige."""
    config = _config(tmp_path)
    stable = config.embedding_model_path
    stable.mkdir(parents=True)
    for name in present:
        (stable / name).write_bytes(b"x")

    with pytest.raises(embedder.EmbedderModelError, match="tepochcalli config embedder"):
        embedder.require_local_model(config)


def test_snapshot_of_another_revision_raises_model_invalid(tmp_path: Path) -> None:
    """Un snapshot completo de OTRA revisión (layout hub de HF) no es el pineado."""
    config = _config(tmp_path)
    snapshot = _write_snapshot(
        config.models_dir / f"models--{MODEL.replace('/', '--')}" / "snapshots" / OTHER_REVISION
    )
    config.embedding_model_path.symlink_to(snapshot, target_is_directory=True)

    with pytest.raises(embedder.EmbedderModelError, match="tepochcalli config embedder"):
        embedder.require_local_model(config)


def test_complete_snapshot_is_accepted_by_the_read_path(tmp_path: Path) -> None:
    """El caso legítimo (manifiesto + pesos) sigue pasando — es el que usa toda la suite."""
    config = _config(tmp_path)
    written = _write_snapshot(config.embedding_model_path)

    assert embedder.require_local_model(config) == written
