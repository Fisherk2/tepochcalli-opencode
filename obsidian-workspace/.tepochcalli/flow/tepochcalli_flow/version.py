"""Lee la versión canónica del payload desde `[project].version` de `pyproject.toml`."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import cast

_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def payload_version() -> str:
    """Devuelve la versión declarada en el pyproject del payload (única fuente)."""
    try:
        with _PYPROJECT.open("rb") as fh:
            version = tomllib.load(fh)["project"]["version"]
    except (OSError, tomllib.TOMLDecodeError, KeyError, TypeError) as exc:
        raise RuntimeError(f"No se pudo leer [project].version de {_PYPROJECT}: {exc}") from exc
    return cast(str, version)
