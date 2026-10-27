"""Validación de rutas en el borde MCP: glob de `search`, `subdir`/slug/`file:` de `add_source`.

Dominio puro del server (SPEC.md §Boundaries: «validar entradas en el borde
MCP»). Fuentes de verdad:

* tasks/plan.md §5 — `path_filter` absoluto o con `..` → `VALIDATION_ERROR`;
  `subdir` normalizado, sin `..`, sin absolutos, destino siempre dentro de
  `00-Resources/`, por omisión `_inbox`; nombre slug + `.md` con sufijo
  numérico ante colisión (plan §T5).
* specs/spec-mcp-server.md §Security — path traversal → `VALIDATION_ERROR`.
* D16 (ratificado 2026-10-26, docs/WORKFLOW.md §8) — `file:` FUERA del vault
  ⇒ RECHAZADO con `VALIDATION_ERROR`: la versión estricta del conflicto
  spec-mcp-server §Security vs spec-markitdown §Testing. markitdown puede
  leer cualquier archivo accesible al proceso (spec-markitdown §Seguridad
  del canal), así que este borde es la ÚNICA puerta que decide qué `file:`
  llega al conversor.

Decisión documentada: ESTE módulo valida la FORMA de las rutas, pero NO traduce
el glob a SQL — la traducción `*`→`%` vive y se congela en
`tepochcalli_flow.adapters.lancedb_reader.path_filter_to_like_predicate` y el
adaptador la aplica (importarla aquí arrastraría `lancedb` al paquete del
server; test de arquitectura). El adaptador además re-valida en su propio
borde: defensa en profundidad SIN duplicar la traducción.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Final
from urllib.parse import unquote, urlparse

from tepochcalli_flow.citation import RESOURCES_DIR

DEFAULT_SUBDIR: Final = "_inbox"
"""Subdirectorio canónico de destino de `add_source` cuando no se nombra uno (plan §T5)."""

MAX_SLUG_LENGTH: Final = 80
"""Tope del slug derivado del URI: nombres de archivo Observables, no muros de texto."""

MAX_SLUG_SUFFIX: Final = 1000
"""Sufijo numérico máximo ante colisiones: un directorio saturado es INTERNAL, no un bucle."""


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


def _slugify_text(text: str) -> str:
    """Normaliza texto libre a slug: alnum se conservan (unicode incluido), resto → `-`."""
    collapsed = "".join(char if char.isalnum() else "-" for char in text)
    dedashed = "-".join(part for part in collapsed.split("-") if part)
    return dedashed.lower()[:MAX_SLUG_LENGTH].rstrip("-")


def slugify_uri(uri: str) -> str:
    """Slug del nombre de archivo candidato derivado del URI (plan §T5: slug + `.md`).

    El nombre sale del ÚLTIMO segmento del path SIN extensión (percent-decode
    incluido: `ruiz%20final.pdf` → `ruiz-final`); sin segmento útil se cae al
    hostname y, en último término, a `source`. Puro: no toca el filesystem —
    la colisión la resuelve `available_name`.
    """
    parsed = urlparse(uri)
    stem = PurePosixPath(unquote(parsed.path)).stem
    slug = _slugify_text(stem)
    if slug:
        return slug
    host = parsed.hostname or ""
    return _slugify_text(host) or "source"


def available_name(slug: str, taken: Callable[[str], bool]) -> str:
    """Primer nombre libre: `<slug>.md` o `<slug>-N.md` con N creciente (plan §T5).

    `taken` es la costura del filesystem (¿existe ya ese nombre en el
    destino?): la lógica de colisión queda PURA y testeable sin directorios.
    Un destino saturado más allá de `MAX_SLUG_SUFFIX` lanza `RuntimeError` —
    el `internal_guard` lo convierte en `INTERNAL`, nunca en un bucle infinito.
    """
    candidate = f"{slug}.md"
    suffix = 2
    while taken(candidate):
        if suffix > MAX_SLUG_SUFFIX:
            raise RuntimeError(f"sin nombres libres para el slug {slug!r} tras {MAX_SLUG_SUFFIX}")
        candidate = f"{slug}-{suffix}.md"
        suffix += 1
    return candidate


def validate_source_uri(uri: str, vault_root: Path) -> None:
    """Valida el `uri` de `add_source` en el borde: `http(s):` o `file:` DENTRO del vault.

    Esquema desconocido, `http(s)` sin host o `file:` fuera del vault (D16,
    vía `resolve_file_uri`) ⇒ `ValueError` → el handler responde
    `VALIDATION_ERROR` ANTES de que el conversor vea nada — markitdown con
    `file:` leería cualquier archivo accesible al proceso (spec-markitdown
    §Seguridad del canal).
    """
    parsed = urlparse(uri)
    if parsed.scheme == "file":
        resolve_file_uri(uri, vault_root)  # D16: lanza si queda fuera del vault
    elif parsed.scheme in ("http", "https"):
        if not parsed.netloc:
            raise ValueError(f"{parsed.scheme}: debe incluir host: {uri!r}")
    else:
        raise ValueError(f"uri debe empezar por http://, https:// o file:: {uri!r}")


def resolve_file_uri(uri: str, vault_root: Path) -> Path:
    """Resuelve un `file:` a una ruta absoluta DENTRO del vault, o `ValueError` (D16).

    Frontera de confianza de `add_source`: markitdown con `file:` puede leer
    cualquier archivo accesible al proceso (spec-markitdown §Seguridad del
    canal), así que este borde aplica la versión estricta ratificada en D16 —
    TODO lo que quede fuera del vault se RECHAZA aquí, antes de convertir.
    `resolve()` (no-strict) colapsa `..` y symlinks: un enlace DENTRO del
    vault que apunta FUERA también cae rechazado.
    """
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise ValueError(f"solo `file:` se resuelve como ruta local: {uri!r}")
    if parsed.netloc:
        raise ValueError(f"`file:` sin host (usa file:///ruta/absoluta): {uri!r}")
    local = Path(unquote(parsed.path))
    if not local.is_absolute():
        raise ValueError(f"`file:` debe ser una ruta absoluta: {uri!r}")
    resolved = local.resolve()
    if not resolved.is_relative_to(vault_root.resolve()):
        raise ValueError(f"D16: `file:` fuera del vault rechazado: {uri!r}")
    return resolved


def ensure_within(base: Path, target: Path) -> Path:
    """Defensa en profundidad (T5): `target` resuelto debe caer dentro de `base`.

    Último chequeo ANTES de escribir, tras componer el destino final — si una
    refactor futura de slug/colisión dejara componer una ruta que escapa,
    aquí se corta con `ValueError`. **Ese `ValueError` NO es de validación de
    usuario:** en `add_source` la validación real (`validate_source_uri`/
    `validate_subdir`) ya corrió ANTES con su `VALIDATION_ERROR`; si ESTE
    chequeo dispara, la cadena anterior falló — un bug nuestro, y el handler
    deja que `@errors.internal_guard` lo convierta en `INTERNAL` ruidoso
    (corrección T6 al docstring, riesgo R3 de CP-B): la defensa en
    profundidad debe SONAR, no disfrazarse de error de argumento.
    """
    resolved = target.resolve()
    if not resolved.is_relative_to(base.resolve()):
        raise ValueError(f"destino fuera de {base}: {target}")
    return resolved
