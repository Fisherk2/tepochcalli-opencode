"""Escritura atómica e idempotente del conversor (D31/D66) — compartida con `add_source`.

Una sola implementación (T7 AC (f)): el temporal vive en el MISMO directorio de
destino — un temporal en `/tmp` cruzaría dispositivos y el rename dejaría de
ser atómico — y cierra con `os.replace`.

Idempotencia (D66): si el destino existe con los MISMOS bytes no se escribe y
se devuelve el mismo path (reintentar la misma conversión no falla); con bytes
distintos se lanza `paths.VaultPathError` — que el borde mapea a
`VALIDATION_ERROR` — con un nombre alternativo propuesto. **Nunca** se
sobrescribe material del usuario.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from tepochcalli_mcp import paths


def write_atomic(target: Path, content: str) -> Path:
    """Escribe `content` en `target`, o devuelve el destino si ya tiene esos bytes.

    `target` debe venir ya validado contra el vault (frontera B′, `paths`): aquí
    solo se decide si hay algo que escribir.
    """
    data = content.encode("utf-8")
    if target.exists():
        if target.is_dir():
            raise paths.VaultPathError(
                f"el destino es un directorio: {target.name}",
                {
                    "requested": target.name,
                    "exists": True,
                    "expected": "file",
                    "found": "directory",
                },
            )
        if target.read_bytes() == data:
            return target
        alternative = _alternative(target)
        raise paths.VaultPathError(
            f"el destino existe con contenido distinto: elige otro output_path "
            f"(p. ej. {alternative!r}); nada se sobrescribe",
            {"requested": target.name, "exists": True, "suggested": alternative},
        )
    _write_temporary(target, data)
    return target


def _alternative(target: Path) -> str:
    """Primer nombre libre del mismo directorio, reutilizando `paths.available_name` (D37)."""
    candidate = paths.available_name(target.stem, lambda name: (target.parent / name).exists())
    return Path(candidate).with_suffix(target.suffix).name


def _write_temporary(target: Path, data: bytes) -> None:
    """Temporal junto al destino + `os.replace`; ante cualquier fallo lo limpia y re-lanza.

    `shortcut: la comprobación `exists()` y el rename no son una transacción — dos
    escritores simultáneos podrían pisarse (TD CR-7); el caso multiusuario real
    pediría `O_EXCL` sobre el destino, no un parámetro `overwrite`.
    """
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp_path, target)
    except BaseException:  # limpiar el temporal y re-lanzar (Ctrl-C incluido; el guard no lo toca)
        tmp_path.unlink(missing_ok=True)
        raise
