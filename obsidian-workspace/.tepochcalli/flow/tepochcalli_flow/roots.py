"""Validación y dedup de las raíces del vault (ADR-010 §4.4/§4.8, T2).

`walk_sources` y `build_flow` reciben N raíces **relativas al vault**. Este
módulo las valida ANTES de tocar el disco —dentro del vault, sin `..` que
escape, sin symlink que salga y con existencia comprobada— y las deduplica:
raíces solapadas (una dentro de otra o repetida) producen una sola pasada, o
`scanned == indexed + skipped` mentiría (D46).

Es infraestructura: no importa el motor de indexación, solo el dominio de cita.
La validación de existencia/tipo "de borde" (con `details.suggestions`) vive en
el MCP (T7); aquí el fallo es ruidoso y tipado.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .citation import RESOURCES_DIR, normalize_source_path
from .config import DEFAULT_INDEXER_ROOTS

DEFAULT_ROOTS: Final[tuple[str, ...]] = DEFAULT_INDEXER_ROOTS
"""Sin argumento, el índice declara `00-resources/` (ADR-010 §4.1).

Es el MISMO default del producto que `Config.indexer_roots`
(`config.DEFAULT_INDEXER_ROOTS`): una sola copia del dato (liquidación del
escaneo de calidad)."""


@dataclass(frozen=True)
class IndexRoot:
    """Una raíz validada y lista para caminar.

    `relative` es la cita POSIX normalizada (`.` para el vault entero), `path`
    la ruta que se recorre y `resolved` la ruta real usada solo para el dedup.
    """

    relative: str
    path: Path
    resolved: Path

    @property
    def is_file(self) -> bool:
        """True ⇔ la raíz es un fichero suelto (nunca se pasa a `walk_dir`)."""
        return self.resolved.is_file()


def normalize_roots(
    vault_root: Path, roots: Sequence[str | Path] | None = None
) -> tuple[IndexRoot, ...]:
    """Valida, normaliza y deduplica las raíces de una pasada (D44/D46/D47).

    Lanza `ValueError` si una raíz es absoluta, escapa del vault por `..` o por
    symlink, y `FileNotFoundError` si no existe. Todas las raíces se validan
    ANTES de que el llamador toque el disco: una raíz mala no indexa ninguna
    (fail-fast atómico, D65). La raíz `.` representa el vault entero.
    """
    resolved_vault = vault_root.resolve()
    candidates: list[IndexRoot] = []
    for root in DEFAULT_ROOTS if roots is None else roots:
        relative = _normalized_relative(root)
        path = resolved_vault if relative == "." else vault_root / relative
        resolved = path.resolve()
        if not path.exists():
            raise FileNotFoundError(
                f"No existe la raíz indexable {path} — se exigía una ruta dentro de "
                f"{vault_root} (por omisión {RESOURCES_DIR}/)"
            )
        if not resolved.is_relative_to(resolved_vault):
            raise ValueError(
                f"La raíz {os.fspath(root)!r} resuelve fuera del vault ({resolved}) — "
                "el índice no ingiere material de fuera"
            )
        candidates.append(IndexRoot(relative=relative, path=path, resolved=resolved))
    return _deduplicated(candidates)


def _normalized_relative(root: str | Path) -> str:
    """Normaliza una raíz a POSIX relativo al vault; `.` es el vault entero."""
    raw = os.fspath(root).replace("\\", "/")
    if raw.startswith("/"):
        raise ValueError(f"la raíz debe ser relativa al vault, no absoluta: {raw!r}")
    if raw.rstrip("/") in ("", "."):
        return "."
    return normalize_source_path(raw)


def _deduplicated(candidates: list[IndexRoot]) -> tuple[IndexRoot, ...]:
    """Elimina repetidas y raíces anidadas dentro de otra más amplia (D46)."""
    kept: list[IndexRoot] = []
    for candidate in candidates:
        if any(candidate.resolved == root.resolved for root in kept):
            continue
        if any(candidate.resolved.is_relative_to(root.resolved) for root in kept):
            continue
        kept = [root for root in kept if not root.resolved.is_relative_to(candidate.resolved)]
        kept.append(candidate)
    return tuple(kept)
