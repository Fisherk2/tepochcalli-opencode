"""Capa de fuentes: walk filtrado de `00-Resources/` con skips tipados (Phase 1, T5).

Sirve specs/spec-rag-engine.md §Fuentes:

* Whitelist `.md/.markdown/.txt/.pdf` y exclusiones de segmentos-punto y
  `.git/` vía `PatternFilePathMatcher` de cocoindex — **F3**: los include
  patterns por sí solos NO excluyen directorios-punto (el globset de Rust hace
  casar `*` a segmentos con punto inicial), así que `excluded_patterns` es
  obligatorio y explícito.
* **F5**: `localfs.walk_dir` no ofrece límite de tamaño ni hook de errores — el
  conector se traga en silencio los symlinks rotos y solo loguea un error ante
  un archivo chmod-000. La regla «>100MB / symlink roto / ilegible →
  `skipped` con motivo, sin abortar el delta» es NUESTRA: el chequeo por archivo
  vive aquí, delante del candado `stat()` (la opción que la propia spec F5
  sanciona: *custom matcher con `stat()` o chequeo sobre `FileLike`*). Elegimos
  el chequeo sobre la ruta ya resuelta —y no un `FilePathMatcher`— porque el
  matcher solo ve paths que el conector decide entregar: un symlink roto ni
  siquiera llega al matcher (verificado empíricamente), por lo que tampoco
  podría reportarse con motivo.
* Para poder emitir `broken_symlink` con motivo, este módulo combina el walk
  real del conector (que aporta los candidatos según el globset) con un
  barrido ligero de symlinks que solo lee dirents, nunca contenidos.
* **T8 (hallazgo #5 de CP-B):** `unvisited_skips` amplía ese barrido con los
  **directorios ilegibles** que `localfs` descarta con `except
  PermissionError: continue` —motivo nuevo `SkipReason.UNREADABLE_DIR`— para
  que la métrica `scanned` del refresh no los subestime (spec-mcp-server
  §`index_refresh`); `walk_sources` (T5) conserva su salida intacta.
* **Frontera de confianza (decisión 2026-10-22):** el conector sigue los
  symlinks que funcionan (archivo y directorio), así que un vault sincronizado
  o manipulado podría contener `secreto.md -> ~/.ssh/id_rsa`. `classify_file`
  rechaza cualquier symlink cuyo target RESUELTO (cadena completa) salga de
  `00-Resources/` con motivo `symlink_escape`; los links que se quedan dentro
  se indexan con normalidad (documentado en docs/SECURITY.md).

Decisión T7 (reemplaza la de T5): los `.pdf` se parsean con Docling en
`parsers.extract_text` — el walk ya NO los descarta, así que `classify_file`
trata un PDF exactamente como cualquier archivo de la whitelist (whitelist de
cuatro extensiones, umbral de tamaño incluido).

Esta capa ES infraestructura (a diferencia de `citation`/`config`, dominio con
frontera prohibida para el motor): importa `cocoindex` deliberadamente — el
matchear y el walk son los del conector real, no una reimplementación.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from cocoindex.connectors import localfs
from cocoindex.resources.file import FilePathMatcher, PatternFilePathMatcher

from .citation import RESOURCES_DIR, DocKind, doc_kind_for, normalize_source_path

DEFAULT_MAX_FILE_BYTES: Final = 100 * 1024 * 1024
"""Umbral `>100MB → skipped` de spec-rag-engine.md §Fuentes (F5); inyectable en tests."""

WHITELIST_PATTERNS: Final[tuple[str, ...]] = ("**/*.md", "**/*.markdown", "**/*.txt", "**/*.pdf")
"""Whitelist de extensiones del recurso (§Fuentes). Un solo lugar para ampliarla."""

EXCLUDED_PATTERNS: Final[tuple[str, ...]] = ("**/.*", "**/.git/**")
"""Exclusiones obligatorias: segmentos-punto y `.git/` (F3).

Sin ellas el globset real incluye rutas ocultas — verificado con el conector.
"""


class SkipReason(StrEnum):
    """Motivo tipado de descarte por archivo (§Fuentes: «skipped, no falla el delta», F5)."""

    OVERSIZED = "oversized"
    """Archivo sobre `max_file_bytes` (100MB por defecto)."""

    BROKEN_SYMLINK = "broken_symlink"
    """Symlink cuyo objetivo no existe — el conector lo omite en silencio (F5)."""

    UNREADABLE = "unreadable"
    """Sin permiso de lectura u otro error de E/S al acceder al archivo (F5)."""

    SYMLINK_ESCAPE = "symlink_escape"
    """Symlink (de archivo o directorio) cuyo target resuelto sale de `00-Resources/`.

    Frontera de confianza (decisión 2026-10-22): el conector sigue los symlinks
    que funcionan, así que el contenido de fuera del recurso jamás debe llegar
    al índice ni a las respuestas de `search`.
    """

    UNREADABLE_DIR = "unreadable_dir"
    """Directorio que el conector se traga en silencio (`except PermissionError: continue`).

    T8/hallazgo #5 de CP-B: `localfs.walk_dir` omite el directorio SIN entregar
    ni sus archivos ni un motivo, lo que subestimaba `scanned`. Lo contamos como
    UNA entrada de la pasada —sus archivos internos son inenumerables y no se
    inventan— para que `{scanned, indexed, skipped}` no mienta (spec-mcp-server).
    """


@dataclass(frozen=True)
class SourceEntry:
    """Archivo indexable dentro de `00-Resources/`, listo para `extract_text`."""

    path: Path
    """Ruta absoluta en disco."""

    source_path: str
    """Cita POSIX canónica `00-Resources/...` vía `citation.normalize_source_path` (D9.1)."""

    doc_kind: DocKind
    """Tipo derivado de la extensión vía `citation.doc_kind_for` (§Chunking)."""

    size_bytes: int
    """Tamaño observado en el `stat()` del pase (auditoría y métricas de refresh)."""


@dataclass(frozen=True)
class SkippedSource:
    """Archivo descartado con motivo explícito: el pase NUNCA aborta por un solo archivo (F5)."""

    path: Path
    """Ruta absoluta en disco (aunque el archivo no sea legible)."""

    source_path: str
    """Cita POSIX canónica `00-Resources/...` para localizar el descarte."""

    reason: SkipReason
    """Motivo tipado — contrato para las métricas `scanned/indexed/skipped` (spec-mcp-server)."""

    detail: str
    """Explicación humana del motivo, para el log del refresh (§Rollback / Monitoring)."""


type WalkItem = SourceEntry | SkippedSource
"""Elemento de un pase de walk: entrada indexable o descarte con motivo (§Fuentes)."""


def build_path_matcher() -> PatternFilePathMatcher:
    """Construye el matcher de rutas del recurso: whitelist + exclusiones (§Fuentes, F3).

    Ejemplo (contrato F3 verificado con el globset real):

        matcher = build_path_matcher()
        matcher.is_file_included(Path(".oculto/ignorar.md"))  # False
        matcher.is_file_included(Path("sub/carpeta/a.md"))    # True
    """
    return PatternFilePathMatcher(
        included_patterns=list(WHITELIST_PATTERNS),
        excluded_patterns=list(EXCLUDED_PATTERNS),
    )


def walk_sources(
    vault_root: Path,
    *,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    path_matcher: FilePathMatcher | None = None,
) -> list[WalkItem]:
    """Recorre `<vault_root>/00-Resources/` recursivo y clasifica cada archivo (§Fuentes).

    Devuelve UNA lista con ambas caras del pase —entradas indexables y
    descartes con `SkipReason`— ordenada por `source_path` (pase
    determinista, idempotente entre ejecuciones). Un archivo problemático
    jamás aborta el pase: se emite como `SkippedSource` y el resto sigue.

    `max_file_bytes` hace inyectable el umbral de 100MB de la spec para poder
    probar «oversized» con ficheros diminutos (F5); `path_matcher` permite
    reproducir el control F3 con un matcher de solo-inclusión. La raíz
    ausente lanza `FileNotFoundError`: un vault sin `00-Resources/` es una
    instalación rota y el fallo debe ser ruidoso.

    Nota (T5): conduce el `DirWalker` de cocoindex con `asyncio.run`; el flow
    de T6 consumirá `build_path_matcher` + `classify_file` dentro de su propio
    loop, sin re-ejecutar este walk.
    """
    resources_dir = vault_root / RESOURCES_DIR
    if not resources_dir.is_dir():
        raise FileNotFoundError(
            f"No existe el recurso indexable {resources_dir} — se exigía {RESOURCES_DIR}/"
        )
    matcher = build_path_matcher() if path_matcher is None else path_matcher
    candidates = asyncio.run(_connector_candidates(resources_dir, matcher))
    items = [
        classify_file(resources_dir, candidate, max_file_bytes=max_file_bytes)
        for candidate in candidates
    ]
    items.extend(_broken_symlink_skips(resources_dir, matcher))
    return sorted(items, key=lambda item: item.source_path)


def unvisited_skips(
    resources_dir: Path,
    *,
    path_matcher: FilePathMatcher | None = None,
) -> list[SkippedSource]:
    """Entradas que el walk del conector NUNCA entrega, recuperadas con motivo (T8).

    El conector se traga dos casos en silencio —sin candidato y sin `SkipReason`—
    y la métrica `scanned` del refresh los dejaría invisibles (hallazgo #5 de
    CP-B): el **symlink roto** (ni `is_file()` lo sigue) y el **directorio
    ilegible** (`except PermissionError: continue` en `localfs/_source.py`).
    Este barrido ligero —solo dirents, nunca contenidos— los emite con su
    motivo para que `app._indexable_items` los cuente en `scanned`/`skipped`.

    `path_matcher` respeta la misma whitelist/exclusiones que el walk real
    (default: `build_path_matcher()`): un symlink apuntando fuera de la
    whitelist o un directorio-punto no son asunto de esta capa.
    """
    matcher = build_path_matcher() if path_matcher is None else path_matcher
    skips = _broken_symlink_skips(resources_dir, matcher)
    skips.extend(_unreadable_dir_skips(resources_dir, matcher))
    return skips


def classify_file(
    resources_dir: Path,
    file_path: Path,
    *,
    max_file_bytes: int,
    size_bytes: int | None = None,
) -> WalkItem:
    """Aplica la regla F5 a un archivo y devuelve su entrada o su skip con motivo.

    Orden de motivos: objetivo fuera del recurso (frontera de confianza contra
    symlinks que escapan) → ilegible → oversized. Cualquier error de
    `stat()`/lectura se traduce en un `SkipReason` en vez de propagarse
    (§Fuentes: «se registran como `skipped`, no fallan el delta»).
    `size_bytes` permite reutilizar un tamaño ya conocido (p. ej. `FileLike.size()`
    en T6) sin volver a hacer `stat()`.
    """
    escaped = _symlink_escape_target(file_path, resources_dir)
    if escaped is not None:
        return SkippedSource(
            file_path,
            _escape_reference(file_path, resources_dir),
            SkipReason.SYMLINK_ESCAPE,
            f"resuelve fuera de {RESOURCES_DIR}/ ({escaped}) — frontera de confianza: "
            "el recurso no ingiere material de fuera",
        )
    source_path = normalize_source_path(file_path.relative_to(resources_dir))
    kind = doc_kind_for(file_path)
    stat_result = _stat_or_skip(file_path, source_path)
    if isinstance(stat_result, SkippedSource):
        return stat_result
    observed_size = stat_result.st_size if size_bytes is None else size_bytes
    if not os.access(file_path, os.R_OK):
        return SkippedSource(
            file_path,
            source_path,
            SkipReason.UNREADABLE,
            "sin permiso de lectura (chmod/propiedad) — el pase continúa sin él (F5)",
        )
    if observed_size > max_file_bytes:
        return SkippedSource(
            file_path,
            source_path,
            SkipReason.OVERSIZED,
            f"{observed_size} bytes superan el umbral de {max_file_bytes} bytes (F5)",
        )
    return SourceEntry(file_path, source_path, kind, observed_size)


def _symlink_escape_target(file_path: Path, resources_dir: Path) -> Path | None:
    """Target resuelto si escapa de `00-Resources/`, o `None` si vive dentro (frontera).

    `Path.resolve()` sigue la cadena completa de symlinks —de archivo o de
    directorio— y compara contra la raíz RESUELTA, de modo que un vault bajo un
    path enlazado no produce falsos positivos (decisión 2026-10-22).
    """
    target = file_path.resolve()
    return None if target.is_relative_to(resources_dir.resolve()) else target


def _escape_reference(file_path: Path, resources_dir: Path) -> str:
    """Referencia localizable de un symlink que escapa: la cita del LINK si cabe, si no el target.

    El conector emite candidatos ya resueltos (`FilePath.__fspath__` resuelve
    los symlinks), en cuyo caso no hay cita posible y el target absoluto es lo
    único que localiza el descarte; una ruta-del-link pasada directamente a
    `classify_file` sí produce su cita `00-Resources/...`.
    """
    try:
        return normalize_source_path(file_path.relative_to(resources_dir))
    except ValueError:
        return file_path.resolve().as_posix()


def _stat_or_skip(file_path: Path, source_path: str) -> os.stat_result | SkippedSource:
    """`stat()` defensivo: desaparecido → `broken_symlink`, error de E/S → `unreadable` (F5)."""
    try:
        return file_path.stat()
    except FileNotFoundError:
        return SkippedSource(
            file_path,
            source_path,
            SkipReason.BROKEN_SYMLINK,
            "symlink roto: el objetivo no existe — el conector lo omite en silencio (F5)",
        )
    except OSError as exc:
        return SkippedSource(
            file_path,
            source_path,
            SkipReason.UNREADABLE,
            f"stat() falló ({exc.strerror or exc}) — el pase continúa sin él (F5)",
        )


async def _connector_candidates(resources_dir: Path, matcher: FilePathMatcher) -> list[Path]:
    """Candidatos del walk REAL de cocoindex: `localfs.walk_dir` recursivo (§Fuentes)."""
    walker = localfs.walk_dir(resources_dir, recursive=True, path_matcher=matcher)
    return [Path(os.fspath(entry.file_path)) async for entry in walker]


def _broken_symlink_skips(resources_dir: Path, matcher: FilePathMatcher) -> list[SkippedSource]:
    """Barrido ligero de symlinks rotos que el conector traga en silencio (F5).

    Solo lee dirents (nunca contenidos) y respeta el matcher: un symlink
    apuntando fuera de la whitelist o hacia un directorio excluido no es
    asunto de esta capa. Los directorios-punto se podan del descenso para no
    recorrer `.obsidian/` ni `.git/`.
    """
    skips: list[SkippedSource] = []
    for dirpath, dirnames, filenames in os.walk(resources_dir):
        relative_dir = Path(dirpath).relative_to(resources_dir)
        dirnames[:] = [name for name in dirnames if matcher.is_dir_included(relative_dir / name)]
        for name in filenames:
            path = Path(dirpath) / name
            if not path.is_symlink() or path.exists():
                continue
            relative = path.relative_to(resources_dir)
            if not matcher.is_file_included(relative):
                continue
            skips.append(
                SkippedSource(
                    path,
                    normalize_source_path(relative),
                    SkipReason.BROKEN_SYMLINK,
                    "symlink roto: el objetivo no existe — el conector lo omite en silencio (F5)",
                )
            )
    return skips


def _unreadable_dir_skips(resources_dir: Path, matcher: FilePathMatcher) -> list[SkippedSource]:
    """Directorios que `localfs.walk_dir` descarta con `except PermissionError` (T8).

    El conector hace `continue` SIN entregar el directorio ni sus archivos
    (verificado en la fuente `connectors/localfs/_source.py`); este barrido
    usa el `onerror` de `os.walk` para emitir cada uno como UNA entrada
    `SkipReason.UNREADABLE_DIR`. Solo cuenta `PermissionError` —el único error
    que el conector traga— para que una carrera `ENOENT` no se finja descarte.
    """
    skips: list[SkippedSource] = []

    def _onerror(exc: OSError) -> None:
        if not isinstance(exc, PermissionError) or not exc.filename:
            return
        dirpath = Path(exc.filename)
        try:
            relative = dirpath.relative_to(resources_dir)
        except ValueError:
            return
        if not matcher.is_dir_included(relative):
            return
        skips.append(
            SkippedSource(
                dirpath,
                normalize_source_path(relative),
                SkipReason.UNREADABLE_DIR,
                f"directorio ilegible ({exc.strerror or exc}) — el conector lo omite en "
                "silencio; sus archivos no enumerables se representan con esta entrada (T8)",
            )
        )

    for dirpath, dirnames, _filenames in os.walk(resources_dir, onerror=_onerror):
        relative_dir = Path(dirpath).relative_to(resources_dir)
        dirnames[:] = [name for name in dirnames if matcher.is_dir_included(relative_dir / name)]
    return skips
