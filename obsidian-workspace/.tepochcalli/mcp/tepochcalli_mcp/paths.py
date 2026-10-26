"""Validación de rutas en el borde MCP: glob de `search` y `subdir` de `add_source`.

Dominio puro del server (SPEC.md §Boundaries: «validar entradas en el borde
MCP»). Fuentes de verdad:

* tasks/plan.md §5 — `path_filter` absoluto o con `..` → `VALIDATION_ERROR`;
  `subdir` normalizado, sin `..`, sin absolutos, destino siempre dentro de
  `00-Resources/`, por omisión `_inbox` (plan §T5 sobre esta base).
* specs/spec-mcp-server.md §Security — path traversal → `VALIDATION_ERROR`.

Decisión documentada: ESTE módulo valida la FORMA de las rutas, pero NO traduce
el glob a SQL — la traducción `*`→`%` vive y se congela en
`tepochcalli_flow.adapters.lancedb_reader.path_filter_to_like_predicate` y el
adaptador la aplica (importarla aquí arrastraría `lancedb` al paquete del
server; test de arquitectura). El adaptador además re-valida en su propio
borde: defensa en profundidad SIN duplicar la traducción.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Final

from tepochcalli_flow.citation import RESOURCES_DIR

DEFAULT_SUBDIR: Final = "_inbox"
"""Subdirectorio canónico de destino de `add_source` cuando no se nombra uno (plan §T5)."""


def validate_path_filter(path_filter: str | None) -> str | None:
    """Valida la forma del glob `path_filter` y lo devuelve tal cual (sin traducir).

    Relativo al vault, no vacío y sin `..`: un filtro que escape del vault es
    una frontera de confianza (spec-mcp-server §Security). `None` busca en todo
    el índice. `ValueError` → el handler responde `VALIDATION_ERROR`.
    """
    if path_filter is None:
        return None
    normalized = path_filter.replace("\\", "/")
    if not normalized:
        raise ValueError("path_filter vacío: usa None para buscar en todo el índice")
    if normalized.startswith("/"):
        raise ValueError(
            f"path_filter debe ser un glob relativo al vault, no absoluto: {path_filter!r}"
        )
    if ".." in PurePosixPath(normalized).parts:
        raise ValueError(
            f"path_filter no puede contener segmentos '..' (escape del vault): {path_filter!r}"
        )
    return path_filter


def validate_subdir(subdir: str | None) -> str:
    r"""Normaliza `subdir` (borde de `add_source`) a un path POSIX relativo al recurso.

    `None`/vacío/`.`/`00-Resources` → `_inbox` (DEFAULT_SUBDIR); `\` → `/`;
    un subdir que YA empieza por `00-Resources` pierde ese prefijo (el destino
    se compone con `resources_destination`). Absoluto o con `..` → `ValueError`:
    jamás se escribe fuera de `00-Resources/` (D9.1, plan §T5).
    """
    normalized = (subdir or "").strip().replace("\\", "/")
    if normalized.startswith("/"):
        raise ValueError(f"subdir debe ser relativo a {RESOURCES_DIR}/, no absoluto: {subdir!r}")
    parts = [part for part in PurePosixPath(normalized).parts if part not in ("", ".")]
    if ".." in parts:
        raise ValueError(f"subdir no puede contener segmentos '..': {subdir!r}")
    if parts and parts[0] == RESOURCES_DIR:
        parts = parts[1:]
    return "/".join(parts) if parts else DEFAULT_SUBDIR


def resources_destination(subdir: str | None) -> Path:
    """Destino canónico de `add_source`: `00-Resources/<subdir|_inbox>`, relativo al vault."""
    return Path(RESOURCES_DIR) / validate_subdir(subdir)
