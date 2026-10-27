"""R2 (riesgo de CP-B): frescura de la config en el backend cacheado de `server` (T6).

El problema: `_backend_instance` cacheaba `Config` + lector POR PROCESO
mientras `rag_status` recargaba el toml por llamada (T4) — tras un swap de
modelo (ADR-008: `tepochcalli config embedder` + reindex en la MISMA sesión),
`search` nombraría la config VIEJA como «actual» y compararía el índice nuevo
contra el modelo antiguo.

**Decisión (documentada aquí, en `_backend()` y en el reporte T6):**
RE carga barata por invocación (`load_config` = lectura de toml, µs — el
coste caro es el embedder, que sigue perezoso) + RECONSTRUCCIÓN del backend
cuando la config cambió (`Config.__eq__` compara secciones, no `models_dir`).
Así `search` y `rag_status` nombran SIEMPRE la misma config en una sesión, y
el lector/embedder del swap nuevo se construye en la primera búsqueda
posterior (reader perezoso: nada de carga de modelo en el rebuild mismo).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tepochcalli_mcp import server

NEW_MODEL = "openai/text-embedding-3-small"


def _wire_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Vault temporal como raíz del server + reinicio del cache de proceso."""
    monkeypatch.setattr(server, "_backend_instance", None)
    monkeypatch.setenv("TEPOCHCALLI_VAULT_ROOT", str(tmp_path))


def test_backend_is_cached_while_the_config_is_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sin cambios, la factory cachea: una sola construcción por sesión (criterio T2)."""
    _wire_vault(tmp_path, monkeypatch)

    first = server._backend()

    assert server._backend() is first
    assert first.expected_model is not NEW_MODEL


def test_backend_rebuilds_after_a_config_swap_in_the_same_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Swap (ADR-008) en la misma sesión ⇒ backend NUEVO con la config NUEVA (R2)."""
    _wire_vault(tmp_path, monkeypatch)
    first = server._backend()
    config_dir = tmp_path / ".tepochcalli" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "tepochcalli.toml").write_text(
        f'[embedding]\nprovider = "litellm"\nmodel = "{NEW_MODEL}"\n',
        encoding="utf-8",
    )

    swapped = server._backend()

    assert swapped is not first, "R2: el cache viejo NO puede sobrevivir a un swap de config"
    assert swapped.expected_model == NEW_MODEL, "la config nombrada por search es la NUEVA"
    assert server._backend() is swapped, "tras el rebuild vuelve a cachebar (sin rebuild en bucle)"
