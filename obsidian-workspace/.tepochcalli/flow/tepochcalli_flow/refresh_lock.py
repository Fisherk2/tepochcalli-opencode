"""Candado de refresh de UN solo escriptor: fd lock exclusivo del SO (T8, ADR-003).

Extraído de `app.py` (P7): app es wiring del engine; el candado es mecanismo
propio sin motor. La semántica stale vive en el docstring de `layout.LOCK_RELPATH`
(decisión T8): el lock es EXCLUSIVO DEL SO sobre el fd — un crash no puede
retenerlo y el lock file residual se reutiliza; jamás se borra (el par
`unlink`/`create` introduce carreras entre adquirentes).
"""

from __future__ import annotations

import errno
import logging
import os
import sys
from pathlib import Path

from .layout import LOCK_RELPATH

logger = logging.getLogger(__name__)

_NOFOLLOW: int = getattr(os, "O_NOFOLLOW", 0)
"""Anti-symlink del propio lock file (POSIX): un `refresh.lock` enlazado es
material hostil (frontera de confianza); en win32 el flag no existe (0)."""


def _try_exclusive_lock(fd: int) -> None:
    """Lock exclusivo NO bloqueante sobre `fd`; `OSError` de bloqueo = ya retenido."""
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _release_os_lock(fd: int) -> None:
    """Libera el lock del SO; la rama Windows exige volver a la posición 0."""
    if sys.platform == "win32":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)


def acquire_refresh_lock(vault_root: Path) -> int | None:
    """Devuelve el fd del candado de refresh retenido, o `None` si OTRO proceso lo retiene ya.

    Semántica de stale: el candado es el lock del SO, no el archivo — un crash
    no puede dejarlo retenido y el lock file residual se REUTILIZA sin leer su
    contenido. El pid se escribe solo como diagnóstico, tras retener. Un error
    de bloqueo distinto de «ya retenido» se propaga: un disco roto no es un
    refresh concurrente.
    """
    path = vault_root / LOCK_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | _NOFOLLOW, 0o644)
    try:
        _try_exclusive_lock(fd)
    except OSError as exc:
        os.close(fd)
        if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK):
            return None
        raise
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())
    except OSError:
        # Sin esta liberación, un write fallido (disco lleno) FUGA el fd y el
        # candado queda retenido por este proceso muerto lógicamente (T8/r2).
        os.close(fd)
        raise
    return fd


def release_refresh_lock(fd: int) -> None:
    """Suelta el candado y cierra el fd; el lock file persiste a propósito."""
    try:
        _release_os_lock(fd)
    finally:
        os.close(fd)
