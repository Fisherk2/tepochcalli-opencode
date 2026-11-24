"""Ciclo del candado extraído a `refresh_lock.py`: acquire/release + write fallido."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from tepochcalli_flow import app as flow_app


def test_acquire_and_release_roundtrip_keeps_lock_file(tmp_path: Path) -> None:
    """Acquire → fd válido y lock file con el pid; release → archivo residual persiste (T8)."""
    fd = flow_app._acquire_refresh_lock(tmp_path)
    assert fd is not None
    content = os.pread(fd, 64, 0)
    flow_app._release_refresh_lock(fd)
    assert content.startswith(str(os.getpid()).encode())
    # el lock file residual persiste a propósito; la siguiente pasada lo reutiliza
    lock_file = tmp_path / ".tepochcalli" / "db" / "refresh.lock"
    assert lock_file.is_file()
    assert lock_file.read_text(encoding="utf-8") == f"{os.getpid()}\n"


def test_second_acquire_in_the_same_process_is_locked(tmp_path: Path) -> None:
    """Segundo acquire → `None` (flock exclusivo), sin lanzar."""
    first = flow_app._acquire_refresh_lock(tmp_path)
    assert first is not None
    try:
        assert flow_app._acquire_refresh_lock(tmp_path) is None
    finally:
        flow_app._release_refresh_lock(first)


def test_failed_diag_write_closes_fd_and_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un `os.write` de diagnóstico fallido NO puede fugar el fd reteniendo el candado."""
    closed: list[int] = []
    real_close = os.close

    def _record_close(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    def _boom(fd: int, data: bytes) -> int:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "close", _record_close)
    monkeypatch.setattr(os, "write", _boom)

    with pytest.raises(OSError, match="No space left"):
        flow_app._acquire_refresh_lock(tmp_path)

    assert len(closed) == 1, "el fd del candado quedó sin cerrar: fuga de retención"
    assert (tmp_path / ".tepochcalli" / "db" / "refresh.lock").exists()
