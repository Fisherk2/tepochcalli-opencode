"""Wiring de `app.py` que solo el proceso real ejercita: raíz del vault y frontera (T6/T8).

Importar `tepochcalli_flow.app` arrastra torch/Docling/lancedb (lifespan y
componentes), así que estos tests viven en `integration/` y no en `unit/`: la
superficie es el ARRANQUE del flow, no lógica pura.

Contratos que se pinan:

* **Raíz del vault por defecto** (docs/ARCHITECTURE + docstring de `app.py`):
  sin `TEPOCHCALLI_VAULT_ROOT`, la raíz es la del payload que el wizard
  materializa (`<vault>/.tepochcalli/flow/tepochcalli_flow/app.py` ⇒
  el `obsidian-workspace/`). La suite SIEMPRE la sobreescribe con la env var,
  así que sin este test la derivación por `__file__` —la que usan TODOS los
  vaults reales— quedaría sin cubrir.
* **Frontera de confianza** (decisión 2026-10-22, docs/SECURITY.md): el
  walk que alimenta `mount_each` no puede indexar un symlink cuyo target viva
  fuera de `00-resources/`. Aquí se pina el WIRING (`_indexable_items`), no la
  regla aislada de `classify_file` (ya cubierta en `test_parsers.py`): es la
  regresión que indexaría `~/.ssh/id_rsa` en silencio.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest
from tepochcalli_flow import app, citation

VAULT_ROOT = Path(app.__file__).resolve().parents[3]
"""Raíz derivada por `__file__` — el MISMO cálculo de `resolve_vault_root`."""


def test_resolve_vault_root_derives_the_payload_vault_when_no_env_override_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Contrato de raíz (app.py): sin `TEPOCHCALLI_VAULT_ROOT` la raíz es el payload.

    `Path(app.__file__).resolve().parents[3]` es la derivación documentada:
    `.../tepochcalli_flow/app.py` → `tepochcalli_flow/` → `flow/` →
    `.tepochcalli/` → el vault. Debe ser un directorio real y contener el
    runtime `.tepochcalli/` que el wizard materializa; si no, todo vault
    instalado apuntaría a una raíz inexistente.
    """
    monkeypatch.delenv(app.VAULT_ROOT_ENV, raising=False)

    root = app.resolve_vault_root()

    assert root == VAULT_ROOT
    assert root.name == "obsidian-workspace"
    assert root.is_dir()
    assert (root / ".tepochcalli").is_dir()


def test_indexable_items_skips_a_symlink_that_escapes_the_vault_and_keeps_the_rest(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Contrato de frontera (T2): `_indexable_items` descarta el symlink que escapa del VAULT.

    El walk del conector resuelve el symlink y entregaría el archivo de FUERA;
    el wiring debe clasificarlo como `symlink_escape`, loguearlo como descarte y
    seguir indexando el resto. `scanned` cuenta ambos candidatos (el indexable
    y el descarte) para que `scanned == indexed + skipped` siga siendo verdad.
    Cada `localfs.File` entregado a `index_file` lleva `base_dir=ROOT_KEY`
    explícito (D62): un `Path` pelado usaría el CWD como base.
    """
    caplog.set_level(logging.WARNING, logger="tepochcalli_flow.app")
    vault = tmp_path / "vault"
    resources_dir = vault / citation.RESOURCES_DIR
    resources_dir.mkdir(parents=True)
    (resources_dir / "ok.md").write_text("# Ok\n\nprosa.\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("# Secreto\n\nfuera del vault.\n", encoding="utf-8")
    try:
        (resources_dir / "escape.md").symlink_to(outside / "secret.md")
    except (OSError, NotImplementedError) as exc:  # pragma: no cover - FS sin symlinks
        pytest.skip(f"el filesystem no soporta symlinks: {exc}")

    items, scanned = asyncio.run(app._indexable_items(vault, (citation.RESOURCES_DIR,)))

    keys = {key for key, _file in items}
    assert "00-resources/ok.md" in keys
    assert not any(key.endswith("escape.md") for key in keys)
    assert scanned == 2  # ok.md + el symlink que escapa, ambos visitados
    for _key, file in items:
        assert file.file_path.base_dir is app.ROOT_KEY, (
            "el FilePath debe construirse con base_dir=ROOT_KEY (D62)"
        )
    messages = [record.getMessage() for record in caplog.records]
    assert any("symlink_escape" in message for message in messages), messages


def test_roots_for_defaults_to_resources_and_preserves_explicit_roots() -> None:
    """`refresh_blocking(None)` indexa `00-resources/`; las raíces dadas viajan tal cual (h)."""
    assert app._roots_for(None) == (citation.RESOURCES_DIR,)
    assert app._roots_for(["materiales", "documentos"]) == ("materiales", "documentos")
