"""Capa de fuentes: walk filtrado de N raíces del vault con skips tipados (T2).

Sirve specs/spec-rag-engine.md §Fuentes (ADR-010):

* **N raíces por llamada**, relativas al vault (`walk_sources(vault_root,
  roots)`); `00-Resources/` es el valor por omisión. `roots.normalize_roots`
  valida y deduplica antes de tocar el disco; una raíz puede ser un **fichero
  suelto** (se emite como entrada única, nunca se pasa a `walk_dir`).
* Whitelist `.md/.markdown/.txt/.pdf` y exclusiones de segmentos-punto y
  `.git/` vía `PatternFilePathMatcher` de cocoindex — **F3**: los include
  patterns por sí solos NO excluyen directorios-punto (el globset de Rust hace
  casar `*` a segmentos con punto inicial), así que `excluded_patterns` es
  obligatorio y explícito. El conector **poda** el subárbol excluido
  (`is_dir_included` antes de encolar), así que indexar el vault entero no
  recorre `.tepochcalli/venv/` ni `.obsidian/` (ADR-010 §4.9).
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
  §`index_refresh`).
* **Frontera de confianza = el VAULT (D16/D47):** el conector sigue los
  symlinks que funcionan (archivo y directorio), así que un vault sincronizado
  o manipulado podría contener `secreto.md -> ~/.ssh/id_rsa`. `classify_file`
  rechaza cualquier symlink cuyo target RESUELTO (cadena completa) salga del
  vault con motivo `symlink_escape`; un link de una raíz a otra es legítimo
  (ambas dentro del vault) y se indexa con normalidad (docs/SECURITY.md).
* **`source_path` es relativo al VAULT (D41):** con N raíces, el relativo a la
  raíz colisionaría (`materiales/a.pdf` y `documentos/a.pdf` ⇒ `a.pdf`).

Decisión T7: los `.pdf` se parsean con Docling en `parsers.extract_text` — el
walk ya NO los descarta, así que `classify_file` trata un PDF exactamente como
cualquier archivo de la whitelist (whitelist de cuatro extensiones, umbral de
tamaño incluido).

Esta capa ES infraestructura (a diferencia de `citation`/`config`, dominio con
frontera prohibida para el motor): importa `cocoindex` deliberadamente — el
matchear y el walk son los del conector real, no una reimplementación.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from cocoindex.connectors import localfs
from cocoindex.resources.file import FilePathMatcher, PatternFilePathMatcher

from .citation import DocKind, doc_kind_for, normalize_source_path
from .roots import IndexRoot, normalize_roots

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
    """Symlink (de archivo o directorio) cuyo target resuelto sale del VAULT.

    Frontera de confianza (D16/D47): el conector sigue los symlinks que
    funcionan, así que el contenido de fuera del vault jamás debe llegar al
    índice ni a las respuestas de `search`. Un link de una raíz a otra es
    legítimo: ambas viven dentro del vault.
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
    """Archivo indexable de una raíz del vault, listo para `extract_text`."""

    path: Path
    """Ruta absoluta en disco."""

    source_path: str
    """Cita POSIX relativa al VAULT vía `citation.normalize_source_path` (D41)."""

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
    """Cita POSIX relativa al vault para localizar el descarte (D41)."""

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
    roots: Sequence[str | Path] | None = None,
    *,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    path_matcher: FilePathMatcher | None = None,
) -> list[WalkItem]:
    """Recorre las `roots` del vault (recursivo) y clasifica cada archivo (§Fuentes).

    Wrapper fino sobre `scan_items` —el MISMO ensamblado (conector + classify +
    silenciosas) que consume el componente por fichero del engine—, para que
    verificador y engine no diverjan en qué archivos existen (P7, P26).

    `roots` es una secuencia de rutas **relativas al vault**; `None` indexa
    `00-Resources/` (ADR-010 §4.1). Cada raíz se valida antes de tocar el disco
    (dentro del vault, sin `..`, existente) y una raíz puede ser un fichero
    suelto. Devuelve UNA lista con ambas caras del pase —entradas indexables y
    descartes con `SkipReason`— ordenada por `source_path` (pase determinista).
    Un archivo problemático jamás aborta el pase: se emite como `SkippedSource`.

    `max_file_bytes` hace inyectable el umbral de 100MB de la spec para poder
    probar «oversized» con ficheros diminutos (F5); `path_matcher` permite
    reproducir el control F3 con un matcher de solo-inclusión. Una raíz
    ausente lanza `FileNotFoundError` y una que escapa del vault `ValueError`:
    un vault roto debe fallar ruidosamente.
    """
    items, _scanned = asyncio.run(
        scan_items(
            vault_root,
            roots,
            max_file_bytes=max_file_bytes,
            path_matcher=path_matcher,
        )
    )
    return sorted(items, key=lambda item: item.source_path)


async def scan_items(
    vault_root: Path,
    roots: Sequence[str | Path] | None = None,
    *,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    path_matcher: FilePathMatcher | None = None,
) -> tuple[list[WalkItem], int]:
    """Core del pase multi-raíz: candidatos + clasificación + entradas silenciosas.

    Valida y deduplica `roots` ANTES de caminar (fail-fast atómico, D65) y
    devuelve `(items, scanned)`: entradas indexables y descartes con motivo
    (incluidas las que el conector TRAGA EN SILENCIO — symlink roto, directorio
    ilegible—), más el total visitado para la identidad
    `scanned == indexed + skipped` del RefreshReport (hallazgo #5 de CP-B).
    Una raíz-fichero se emite como entrada única y NUNCA se pasa a `walk_dir`.
    """
    matcher = build_path_matcher() if path_matcher is None else path_matcher
    items: list[WalkItem] = []
    scanned = 0
    for root in normalize_roots(vault_root, roots):
        if root.is_file:
            items.append(classify_file(vault_root, root.path, max_file_bytes=max_file_bytes))
            scanned += 1
            continue
        scanned += await _scan_directory(vault_root, root, items, max_file_bytes, matcher)
    return items, scanned


async def _scan_directory(
    vault_root: Path,
    root: IndexRoot,
    items: list[WalkItem],
    max_file_bytes: int,
    matcher: FilePathMatcher,
) -> int:
    """Camina UNA raíz-directorio: candidatos + clasificación + silenciosas."""
    candidates = await _connector_candidates(root.path, matcher)
    items.extend(
        classify_file(vault_root, candidate, max_file_bytes=max_file_bytes)
        for candidate in candidates
    )
    silent = unvisited_skips(vault_root, root.path, path_matcher=matcher)
    items.extend(silent)
    return len(candidates) + len(silent)


def unvisited_skips(
    vault_root: Path,
    root: Path,
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

    `root` es el directorio de la raíz; `vault_root` ancla la cita (D41).
    `path_matcher` respeta la misma whitelist/exclusiones que el walk real
    (default: `build_path_matcher()`): un symlink apuntando fuera de la
    whitelist o un directorio-punto no son asunto de esta capa.
    """
    matcher = build_path_matcher() if path_matcher is None else path_matcher
    skips = _broken_symlink_skips(vault_root, root, matcher)
    skips.extend(_unreadable_dir_skips(vault_root, root, matcher))
    return skips


def classify_file(
    vault_root: Path,
    file_path: Path,
    *,
    max_file_bytes: int,
    size_bytes: int | None = None,
) -> WalkItem:
    """Aplica la regla F5 a un archivo y devuelve su entrada o su skip con motivo.

    `source_path` se cita relativo al VAULT (D41) y la frontera de symlinks es
    el vault (D47). Orden de motivos: objetivo fuera del vault → ilegible →
    oversized. Cualquier error de `stat()`/lectura se traduce en un
    `SkipReason` en vez de propagarse (§Fuentes: «se registran como `skipped`,
    no fallan el delta»). `size_bytes` permite reutilizar un tamaño ya conocido
    (p. ej. `FileLike.size()` en T6) sin volver a hacer `stat()`.
    """
    escaped = _symlink_escape_target(file_path, vault_root.resolve())
    if escaped is not None:
        return SkippedSource(
            file_path,
            _escape_reference(file_path, vault_root),
            SkipReason.SYMLINK_ESCAPE,
            f"resuelve fuera del vault ({escaped}) — frontera de confianza: "
            "el vault no ingiere material de fuera",
        )
    try:
        source_path = normalize_source_path(file_path.relative_to(vault_root))
        kind = doc_kind_for(file_path)
    except (OSError, ValueError) as exc:
        # Carrera walk→classify: el archivo desapareció o mutó entre el walk y aquí.
        return SkippedSource(
            file_path,
            str(file_path.name),
            SkipReason.UNREADABLE,
            f"cambió durante el pase: {exc}",
        )
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


def _symlink_escape_target(file_path: Path, resolved_vault: Path) -> Path | None:
    """Target resuelto si escapa del VAULT, o `None` si vive dentro (frontera D47).

    `Path.resolve()` sigue la cadena completa de symlinks —de archivo o de
    directorio— y compara contra la raíz del VAULT resuelta (pasada ya
    resuelta: el llamador la resuelve UNA vez por fichero, no aquí), de modo
    que un vault bajo un path enlazado no produce falsos positivos. Con N
    raíces, un link de `documentos/` a `materiales/` es legítimo.
    shortcut: SIN early-return is_symlink — el conector emite candidatos YA
    RESUELTOS (links fuera del vault llegan como rutas regulares externas) y
    un resolve() del fichero es el único chequeo honesto; el `vault_root` sí
    está pre-resuelto (un resolve menos por fichero).
    """
    target = file_path.resolve()
    return None if target.is_relative_to(resolved_vault) else target


def _escape_reference(file_path: Path, vault_root: Path) -> str:
    """Referencia localizable de un symlink que escapa: la cita del LINK si cabe, si no el target.

    El conector emite candidatos ya resueltos (`FilePath.__fspath__` resuelve
    los symlinks), en cuyo caso no hay cita posible y el target absoluto es lo
    único que localiza el descarte; una ruta-del-link pasada directamente a
    `classify_file` sí produce su cita relativa al vault.
    """
    try:
        return normalize_source_path(file_path.relative_to(vault_root))
    except ValueError:
        return file_path.resolve().as_posix()


def _stat_or_skip(file_path: Path, source_path: str) -> os.stat_result | SkippedSource:
    """`stat()` defensivo: desaparecido → `broken_symlink` o `unreadable`; E/S → `unreadable` (F5).

    Distingue las dos causas de `FileNotFoundError`, que el log NO debe mezclar:
    un **symlink** cuyo objetivo no existe es `BROKEN_SYMLINK` (el conector lo
    traga en silencio, F5), mientras que un archivo **regular** que desapareció
    entre el walk y el classify —carrera walk→classify— es `UNREADABLE` con un
    detalle que dice que el archivo se fue. `UNREADABLE` cubre «sin permiso de
    lectura u otro error de E/S», así que no hace falta un motivo nuevo; el
    recuento `scanned == indexed + skipped` es idéntico en ambos casos.
    """
    try:
        return file_path.stat()
    except FileNotFoundError:
        if file_path.is_symlink():
            return SkippedSource(
                file_path,
                source_path,
                SkipReason.BROKEN_SYMLINK,
                "symlink roto: el objetivo no existe — el conector lo omite en silencio (F5)",
            )
        return SkippedSource(
            file_path,
            source_path,
            SkipReason.UNREADABLE,
            "desapareció durante el pase: ya no existe al hacer stat (el conector "
            "lo entregó; carrera walk→classify, F5)",
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


def _broken_symlink_skips(
    vault_root: Path, root: Path, matcher: FilePathMatcher
) -> list[SkippedSource]:
    """Barrido ligero de symlinks rotos que el conector traga en silencio (F5).

    Solo lee dirents (nunca contenidos) y respeta el matcher: un symlink
    apuntando fuera de la whitelist o hacia un directorio excluido no es
    asunto de esta capa. Los directorios-punto se podan del descenso para no
    recorrer `.obsidian/` ni `.git/`. La cita es relativa al vault (D41).
    """
    skips: list[SkippedSource] = []
    for dirpath, dirnames, filenames in os.walk(root):
        relative_dir = Path(dirpath).relative_to(root)
        dirnames[:] = [name for name in dirnames if matcher.is_dir_included(relative_dir / name)]
        for name in filenames:
            path = Path(dirpath) / name
            if not path.is_symlink() or path.exists():
                continue
            relative = path.relative_to(root)
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


def _unreadable_dir_skips(
    vault_root: Path, root: Path, matcher: FilePathMatcher
) -> list[SkippedSource]:
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

    for dirpath, dirnames, _filenames in os.walk(root, onerror=_onerror):
        relative_dir = Path(dirpath).relative_to(root)
        dirnames[:] = [name for name in dirnames if matcher.is_dir_included(relative_dir / name)]
    return skips
