"""Smoke test for the `tepochcalli_flow` package scaffold (Phase 1, task T2)."""

from __future__ import annotations

import tomllib
from pathlib import Path

import tepochcalli_flow
import tepochcalli_mcp

PAYLOAD = Path(__file__).resolve().parents[2] / "obsidian-workspace" / ".tepochcalli"


def test_package_imports_and_exports_version() -> None:
    """`tepochcalli_flow` imports and exposes a non-empty `__version__` string."""
    version = tepochcalli_flow.__version__
    assert isinstance(version, str)
    assert version


def test_payload_and_mcp_versions_match() -> None:
    """Ambas versiones importadas coinciden con `[project].version` del payload."""
    with (PAYLOAD / "pyproject.toml").open("rb") as fh:
        version = tomllib.load(fh)["project"]["version"]
    assert tepochcalli_flow.__version__ == version
    assert tepochcalli_mcp.__version__ == version
    for package in ("flow", "mcp"):
        source = PAYLOAD / package / f"tepochcalli_{package}" / "__init__.py"
        assert '__version__ = "' not in source.read_text(encoding="utf-8")
