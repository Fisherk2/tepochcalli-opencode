"""Barrido sombra del walk: entradas que `localfs.walk_dir` traga en silencio.

Extraído de `source.py` (T3) para mantener el fichero por debajo del umbral de
líneas sin cambiar comportamiento. El conector se traga dos casos —sin
candidato y sin `SkipReason`— y la métrica `scanned` del refresh los dejaría
invisibles (hallazgo #5 de CP-B): el **symlink roto** (ni `is_file()` lo sigue)
y el **directorio ilegible** (`except PermissionError: continue` en
`localfs/_source.py`). Este barrido ligero —solo dirents, nunca contenidos— los
emite con su motivo para que `app._indexable_items` los cuente en
`scanned`/`skipped`.

Los tipos `SkippedSource`/`SkipReason` y el matcher por defecto viven en
`source.py`; se importan dentro de las funciones para no crear un ciclo
`source → walk_skips → source` al importar.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from cocoindex.resources.file import FilePathMatcher

from .citation import normalize_source_path

if TYPE_CHECKING:
    from .source import SkippedSource


def unvisited_skips(
    vault_root: Path,
    root: Path,
    *,
    path_matcher: FilePathMatcher | None = None,
) -> list[SkippedSource]:
    """Entradas que el walk del conector NUNCA entrega, recuperadas con motivo (T8).

    `root` es el directorio de la raíz; `vault_root` ancla la cita (D41).
    `path_matcher` respeta la misma whitelist/exclusiones que el walk real
    (default: `build_path_matcher()`): un symlink apuntando fuera de la
    whitelist o un directorio-punto no son asunto de esta capa.

    W4/P-01: antes eran DOS traversadas completas (symlinks rotos aparte, dirs
    ilegibles aparte); ahora es UNA `os.walk` —internamente `scandir`, con los
    `DirEntry` cacheados por dirent— cuyo `onerror` reporta los directorios
    ilegibles y cuyo descenso encuentra los symlinks rotos. Los
    directorios-punto se podan del descenso para no recorrer `.obsidian/` ni
    `.git/`. Solo dirents, nunca contenidos.
    """
    from .source import SkippedSource, SkipReason, build_path_matcher

    matcher = build_path_matcher() if path_matcher is None else path_matcher
    skips: list[SkippedSource] = []

    def _onerror(exc: OSError) -> None:
        """Directorios que `localfs.walk_dir` descarta con `except PermissionError` (T8).

        Solo cuenta `PermissionError` —el único error que el conector traga—
        para que una carrera `ENOENT` no se finja descarte.
        """
        if not isinstance(exc, PermissionError) or not exc.filename:
            return
        dirpath = Path(exc.filename)
        try:
            relative = dirpath.relative_to(root)
        except ValueError:
            return
        if not matcher.is_dir_included(relative):
            return
        skips.append(
            SkippedSource(
                dirpath,
                normalize_source_path(dirpath.relative_to(vault_root)),
                SkipReason.UNREADABLE_DIR,
                f"directorio ilegible ({exc.strerror or exc}) — el conector lo omite en "
                "silencio; sus archivos no enumerables se representan con esta entrada (T8)",
            )
        )

    for dirpath, dirnames, filenames in os.walk(root, onerror=_onerror):
        relative_dir = Path(dirpath).relative_to(root)
        dirnames[:] = [name for name in dirnames if matcher.is_dir_included(relative_dir / name)]
        for name in filenames:
            path = Path(dirpath) / name
            if not path.is_symlink() or path.exists():
                continue
            relative = relative_dir / name
            if not matcher.is_file_included(relative):
                continue
            skips.append(
                SkippedSource(
                    path,
                    normalize_source_path(path.relative_to(vault_root)),
                    SkipReason.BROKEN_SYMLINK,
                    "symlink roto: el objetivo no existe — el conector lo omite en silencio (F5)",
                )
            )
    return skips
