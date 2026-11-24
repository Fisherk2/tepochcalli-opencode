"""Traducción `TEPOCHCALLI_ROOT` → `TEPOCHCALLI_VAULT_ROOT` en el composition root (T9).

El contrato MCP (spec-mcp-server §Carga de configuración) nombra la raíz del
vault `TEPOCHCALLI_ROOT`: es lo que `obsidian-workspace/opencode.json` inyecta
en `mcp.servers.tepochcalli-rag.environment`. El flow de Phase 1 resuelve con
`TEPOCHCALLI_VAULT_ROOT`. **Un solo nombre para el vault:** la traducción vive
en `tepochcalli_mcp/server.py` — el composition root, único módulo que conoce
ambos lados (ADR-005: el flow jamás ve `TEPOCHCALLI_ROOT`).

Lección F-T7-2b (T7): `monkeypatch.delenv(raising=False)` sobre una clave
AUSENTE no registra undo en su stack — y la traducción ESCRIBE esa clave
durante el test, que sobreviviría al teardown. Por eso el baile
`setenv` → `delenv`: deja la clave ausente CON undo registrado.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from tepochcalli_mcp import server


def test_contract_root_env_is_translated_to_the_flow_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`TEPOCHCALLI_ROOT` puesto y `TEPOCHCALLI_VAULT_ROOT` ausente ⇒ la raíz es la del contrato."""
    monkeypatch.setenv("TEPOCHCALLI_VAULT_ROOT", "sentinel")  # registra undo (F-T7-2b)
    monkeypatch.delenv("TEPOCHCALLI_VAULT_ROOT")  # ausente, pero el undo queda anclado
    monkeypatch.setenv("TEPOCHCALLI_ROOT", str(tmp_path))

    assert server._vault_root() == tmp_path

    # La traducción queda en la env del proceso: el flow (p. ej.
    # `refresh_blocking` → `resolve_vault_root`) ve el MISMO vault sin
    # conocer nunca `TEPOCHCALLI_ROOT`.
    assert os.environ["TEPOCHCALLI_VAULT_ROOT"] == str(tmp_path)


def test_the_flow_root_env_wins_when_both_names_are_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Con ambos nombres, manda el del flow (tests/`verify.py` ya lo usan): no se pisa."""
    monkeypatch.setenv("TEPOCHCALLI_VAULT_ROOT", str(tmp_path))
    monkeypatch.setenv("TEPOCHCALLI_ROOT", "/otra/raiz/que/no/debe/ganar")

    assert server._vault_root() == tmp_path
    assert os.environ["TEPOCHCALLI_VAULT_ROOT"] == str(tmp_path)


def test_the_returned_root_is_resolved_even_when_the_env_is_relative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review Phase 2 (eje 7): env RELATIVA al cwd ⇒ raíz ABSOLUTA devuelta (`.resolve()`).

    El harness puede lanzar el server stdio desde cualquier cwd con una raíz
    tipo `.` (es el literal de `opencode.json`); paths/walks/written_to no
    pueden depender del directorio de lanzamiento.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TEPOCHCALLI_VAULT_ROOT", "recursos-relativos")

    root = server._vault_root()

    assert root.is_absolute()
    assert root == (tmp_path / "recursos-relativos").resolve()
