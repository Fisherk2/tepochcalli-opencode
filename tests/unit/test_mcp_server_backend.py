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

import asyncio
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


def test_unreadable_table_yields_no_rows_instead_of_propagating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ValueError` de lancedb al abrir la tabla ⇒ sin filas, nunca excepción.

    El borde de solo lectura del backend distingue «índice inexistente» por
    `rows == 0`/`models == ∅`: una tabla con esquema incompatible se trata
    igual (lectura barata, jamás un `INTERNAL` en `rag_status`/`search` antes
    de su propia precedencia).
    """
    import lancedb
    from tepochcalli_flow.config import load_config
    from tepochcalli_flow.layout import DB_RELPATH

    (tmp_path / DB_RELPATH).mkdir(parents=True)  # la DB existe: el fallo es de LECTURA

    class _UnreadableDb:
        """Conexión cuyo `open_table` lanza el `ValueError` observado en lancedb 0.40.0."""

        async def open_table(self, name: str) -> object:
            raise ValueError(f"tabla {name} ilegible (esquema incompatible)")

        def close(self) -> None:
            """`close()` sync sin anotar en lancedb 0.40.0 — el backend no lo espera."""

    async def _connect(_uri: str) -> _UnreadableDb:
        return _UnreadableDb()

    monkeypatch.setattr(lancedb, "connect_async", _connect)
    backend = server._VaultSearchBackend(tmp_path, load_config(tmp_path))

    assert asyncio.run(backend.index_models()) == set()

    meta = asyncio.run(backend.index_meta())
    assert (meta["rows"], meta["models"], meta["last_refresh"]) == (0, set(), None)
