"""Smoke test for the `tepochcalli_flow` package scaffold (Phase 1, task T2)."""

from __future__ import annotations

import tepochcalli_flow


def test_package_imports_and_exports_version() -> None:
    """`tepochcalli_flow` imports and exposes a non-empty `__version__` string."""
    version = tepochcalli_flow.__version__
    assert isinstance(version, str)
    assert version
