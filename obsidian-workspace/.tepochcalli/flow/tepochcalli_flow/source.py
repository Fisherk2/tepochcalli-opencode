"""Capa de fuentes: walk filtrado de N raíces del vault con skips tipados (T2).

Sirve specs/spec-rag-engine.md §Fuentes (ADR-010):

* **N raíces por llamada**, relativas al vault (`walk_sources(vault_root,
  roots)`); `00-resources/` es el valor por omisión. `roots.normalize_roots`
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

Decisión T3 (reemplaza la de T7): los documentos binarios (`pdf/docx/pptx/xlsx/
xls`) se extraen con markitdown en `parsers.extract_text`; el walk los entrega
como cualquier archivo de la whitelist y un fallo del extractor se reporta como
`SkipReason.EXTRACTION_FAILED` (con `probe_extraction=True`) sin abortar el
pase. Los `.md/.markdown/.txt` conservan la lectura UTF-8 estricta.

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
from functools import cache
from pathlib import Path
from typing import Final

from cocoindex.connectors import localfs
from cocoindex.resources.file import FilePathMatcher, PatternFilePathMatcher

from .citation import SOURCE_OFFSETS_DOC_KINDS, DocKind, doc_kind_for, normalize_source_path
from .roots import IndexRoot, normalize_roots
from .walk_skips import unvisited_skips

DEFAULT_MAX_FILE_BYTES: Final = 100 * 1024 * 1024
"""Umbral `>100MB → skipped` de spec-rag-engine.md §Fuentes (F5); inyectable en tests."""

WHITELIST_PATTERNS: Final[tuple[str, ...]] = (
    "**/*.md",
    "**/*.markdown",
    "**/*.txt",
    "**/*.pdf",
    "**/*.docx",
    "**/*.pptx",
    "**/*.xlsx",
    "**/*.xls",
)
"""Whitelist de las 8 extensiones soportadas (§Fuentes, D43). Un solo lugar."""

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

    EXTRACTION_FAILED = "extraction_failed"
    """markitdown no pudo extraer texto (corrupto, cifrado, o sin capa de texto).

    T3/D48: un documento binario cuyo extractor falla no aborta el pase; se
    emite con este motivo y `detail` distingue «corrupto/cifrado» de «sin capa
    de texto (posible escaneado, OCR manual)». Un documento sin texto JAMÁS se
    indexa como fila vacía (OM-11).
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
    probe_extraction: bool = True,
) -> list[WalkItem]:
    """Recorre las `roots` del vault (recursivo) y clasifica cada archivo (§Fuentes).

    Wrapper fino sobre `scan_items` —el MISMO ensamblado (conector + classify +
    silenciosas) que consume el componente por fichero del engine—, para que
    verificador y engine no diverjan en qué archivos existen (P7, P26).

    `roots` es una secuencia de rutas **relativas al vault**; `None` indexa
    `00-resources/` (ADR-010 §4.1). Cada raíz se valida antes de tocar el disco
    (dentro del vault, sin `..`, existente) y una raíz puede ser un fichero
    suelto. Devuelve UNA lista con ambas caras del pase —entradas indexables y
    descartes con `SkipReason`— ordenada por `source_path` (pase determinista).
    Un archivo problemático jamás aborta el pase: se emite como `SkippedSource`.

    `probe_extraction` (default True, T3): prueba a extraer los documentos
    binarios para reportar `EXTRACTION_FAILED` en el walk de diagnóstico. El
    engine lo deja en False — la extracción vive DENTRO de `index_file` y el
    memo por fichero evita re-parsear: un probe en el walk duplicaría el coste.

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
            probe_extraction=probe_extraction,
        )
    )
    return sorted(items, key=lambda item: item.source_path)


async def scan_items(
    vault_root: Path,
    roots: Sequence[str | Path] | None = None,
    *,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    path_matcher: FilePathMatcher | None = None,
    probe_extraction: bool = False,
) -> tuple[list[WalkItem], int]:
    """Core del pase multi-raíz: candidatos + clasificación + entradas silenciosas.

    Valida y deduplica `roots` ANTES de caminar (fail-fast atómico, D65) y
    devuelve `(items, scanned)`: entradas indexables y descartes con motivo
    (incluidas las que el conector TRAGA EN SILENCIO — symlink roto, directorio
    ilegible—), más el total visitado para la identidad
    `scanned == indexed + skipped` del RefreshReport (hallazgo #5 de CP-B).
    Una raíz-fichero se emite como entrada única y NUNCA se pasa a `walk_dir`.

    `probe_extraction` desactivado por defecto: el engine extrae dentro de
    `index_file` (memoizado); el walk no duplica el parseo de documentos.
    """
    matcher = build_path_matcher() if path_matcher is None else path_matcher
    items: list[WalkItem] = []
    scanned = 0
    for root in normalize_roots(vault_root, roots):
        if root.is_file:
            items.append(
                classify_file(
                    vault_root,
                    root.path,
                    max_file_bytes=max_file_bytes,
                    probe_extraction=probe_extraction,
                )
            )
            scanned += 1
            continue
        scanned += await _scan_directory(
            vault_root, root, items, max_file_bytes, matcher, probe_extraction
        )
    return items, scanned


async def _scan_directory(
    vault_root: Path,
    root: IndexRoot,
    items: list[WalkItem],
    max_file_bytes: int,
    matcher: FilePathMatcher,
    probe_extraction: bool,
) -> int:
    """Camina UNA raíz-directorio: candidatos + clasificación + silenciosas."""
    candidates = await _connector_candidates(root.path, matcher)
    resolved_parents: dict[Path, Path] = {}
    for candidate in candidates:
        parent = candidate.parent
        resolved = resolved_parents.get(parent)
        if resolved is None:
            # Resolve del padre UNA vez por directorio único (W4/P-01): los
            # ficheros del mismo directorio lo comparten; el chequeo D47 de
            # cada fichero cae a UN `islink` en el camino común.
            resolved = resolved_parents[parent] = parent.resolve()
        items.append(
            classify_file(
                vault_root,
                candidate,
                max_file_bytes=max_file_bytes,
                probe_extraction=probe_extraction,
                resolved_parent=resolved,
            )
        )
    silent = unvisited_skips(vault_root, root.path, path_matcher=matcher)
    items.extend(silent)
    return len(candidates) + len(silent)


@cache
def _resolve_vault(vault_root: Path) -> Path:
    """Raíz del VAULT resuelta UNA vez por ruta y proceso (W4/P-01).

    `Path.resolve()` recorre los ancestros con `lstat` — por fichero eran
    ~descenso syscalls repetidos sobre la MISMA raíz en cada `classify_file`.
    El vault no se mueve durante una pasada; las llamadas directas de
    test/verify usan raíces tmp únicas, así que la clave-ruta no se cruza.
    """
    return vault_root.resolve()


def classify_file(
    vault_root: Path,
    file_path: Path,
    *,
    max_file_bytes: int,
    size_bytes: int | None = None,
    probe_extraction: bool = False,
    resolved_parent: Path | None = None,
) -> WalkItem:
    """Aplica la regla F5 a un archivo y devuelve su entrada o su skip con motivo.

    `source_path` se cita relativo al VAULT (D41) y la frontera de symlinks es
    el vault (D47). Orden de motivos: objetivo fuera del vault → ilegible →
    oversized → extracción fallida (solo con `probe_extraction=True`). Cualquier
    error de `stat()`/lectura se traduce en un `SkipReason` en vez de propagarse
    (§Fuentes: «se registran como `skipped`, no fallan el delta»). `size_bytes`
    permite reutilizar un tamaño ya conocido (p. ej. `FileLike.size()` en T6)
    sin volver a hacer `stat()`. `resolved_parent` (W4/P-01): el padre del
    fichero ya resuelto — `_scan_directory` lo computa UNA vez por directorio
    único y el chequeo D47 evita re-resolver el fichero (ver
    `_symlink_escape_target`); `None` cae al resolve completo de siempre.

    `probe_extraction` (T3): para los binarios, ejecuta el extractor y convierte
    un fallo en `EXTRACTION_FAILED`. El engine lo deja en False — la extracción
    real ocurre una sola vez, dentro de `index_file` memoizado.
    """
    escaped = _symlink_escape_target(file_path, _resolve_vault(vault_root), resolved_parent)
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
    if probe_extraction and kind not in SOURCE_OFFSETS_DOC_KINDS:
        from .parsers import ExtractionError, extract_text

        try:
            extract_text(file_path)
        except ExtractionError as exc:
            return SkippedSource(
                file_path,
                source_path,
                SkipReason.EXTRACTION_FAILED,
                exc.detail,
            )
    return SourceEntry(file_path, source_path, kind, observed_size)


def _symlink_escape_target(
    file_path: Path,
    resolved_vault: Path,
    resolved_parent: Path | None = None,
) -> Path | None:
    """Target resuelto si escapa del VAULT, o `None` si vive dentro (frontera D47).

    `resolved_parent` (W4/P-01): el DIRECTORIO PADRE ya resuelto — UNA vez por
    directorio único (`_scan_directory` lo cachea), no por fichero. Para un
    fichero que NO es symlink (I `lstat` por fichero, el camino común), el
    target es exactamente `resolved_parent/name`: toda la cadena de symlinks
    relevante vive en la del padre, ya resuelta. Si el padre no llega (llamadas
    directas de test/verify) o el fichero ES symlink, se resuelve la cadena
    COMPLETA como antes — semántica D47 intacta para el caso que la necesita.

    shortcut: SIN early-return is_symlink — el conector emite candidatos YA
    RESUELTOS (links fuera del vault llegan como rutas regulares externas) y
    el `vault_root` sí está pre-resuelto (un resolve menos por fichero).
    """
    if resolved_parent is not None and not os.path.islink(file_path):
        target = resolved_parent / file_path.name
    else:
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
