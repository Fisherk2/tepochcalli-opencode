"""Smoke test for the `tepochcalli_flow` package scaffold (Phase 1, task T2)."""

from __future__ import annotations

from pathlib import Path

import tepochcalli_flow

PAYLOAD = Path(__file__).resolve().parents[2] / "obsidian-workspace" / ".tepochcalli"


def test_package_imports_and_exports_version() -> None:
    """`tepochcalli_flow` imports and exposes a non-empty `__version__` string."""
    version = tepochcalli_flow.__version__
    assert isinstance(version, str)
    assert version


def test_payload_and_mcp_versions_match() -> None:
    """The payload version and `tepochcalli_mcp.__version__` cannot diverge."""
    version = next(
        line.split('"')[1]
        for line in (PAYLOAD / "pyproject.toml").read_text(encoding="utf-8").splitlines()
        if line.startswith("version = ")
    )
    declared = next(
        line.split('"')[1]
        for line in (PAYLOAD / "mcp" / "tepochcalli_mcp" / "__init__.py")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.startswith("__version__")
    )
    assert declared == version
