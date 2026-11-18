"""Validación de rutas en el borde MCP: glob de `search`, `subdir`/slug/`file:` de `add_source`.

Dominio puro del server (SPEC.md §Boundaries: «validar entradas en el borde
MCP»). Fuentes de verdad:

* tasks/plan.md §5 — `path_filter` absoluto o con `..` → `VALIDATION_ERROR`;
  `subdir` normalizado, sin `..`, sin absolutos, destino siempre dentro de
  `00-resources/`, por omisión `_inbox`; nombre slug + `.md` con sufijo
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

**Frontera B′ (T7, D31/D64/D65).** `validate_input_path`/`validate_destination`
cubren entrada y salida de las 3 tools del conversor (`validate_vault_path`
queda como dispatcher para los tests del borde): dentro del vault ⇒ ruta
absoluta; absoluta
externa, `..` o symlink que escapa ⇒ `VaultPathError` (el borde lo mapea a
`VALIDATION_ERROR`). Existencia y tipo se deciden AQUÍ, antes de tocar el
disco, porque el `ValueError` de `walk_dir` del motor saldría como `INTERNAL`
por una ruta mal escrita (D64). `validate_roots` aplica las mismas reglas a N
raíces con fail-fast atómico (D65) y `vault_dirs` publica lo que sí existe
(D67, reutilizado por `rag_status` en T8).

Umbral (docs/CODE_STYLE.md): 545 líneas, tramo 501-700 justificable — el split
de `validate` por entrada/destino (2026-11-17) añadió ~40 líneas de API por
claridad; el corte natural a <500 (SSRF/`redact_uri` a `uri_guard.py`) está
bloqueado: `test_mcp_convert_source_fetch.py` monkeypachea
`paths._deny_internal_host` y moverlo rompería el fixture W-02.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Callable, Sequence
from pathlib import Path, PurePosixPath
from typing import Final, Literal
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

from tepochcalli_flow.citation import RESOURCES_DIR
from tepochcalli_flow.config import DEFAULT_INDEXER_ROOTS

from tepochcalli_mcp.suggestions import suggest_names

DEFAULT_SUBDIR: Final = "_inbox"
"""Subdirectorio canónico de destino de `add_source` cuando no se nombra uno (plan §T5)."""

MAX_SLUG_LENGTH: Final = 80
"""Tope del slug derivado del URI: nombres de archivo Observables, no muros de texto."""

MAX_SLUG_SUFFIX: Final = 1000
"""Sufijo numérico máximo ante colisiones: un directorio saturado es INTERNAL, no un bucle."""

MAX_PATH_FILTER_LENGTH: Final = 1024
"""Tope del glob `path_filter` (W-08): un patrón de KBs es DoS de traducción, no una cita."""


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
    if len(normalized) > MAX_PATH_FILTER_LENGTH:  # W-08: el adaptador lo revalida igual
        raise ValueError(
            f"path_filter demasiado largo: {len(normalized)} chars superan el tope "
            f"{MAX_PATH_FILTER_LENGTH}"
        )
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

    `None`/vacío/`.`/`00-resources` → `_inbox` (DEFAULT_SUBDIR); `\` → `/`;
    un subdir que YA empieza por `00-resources` pierde ese prefijo (el destino
    se compone con `resources_destination`). Absoluto o con `..` → `ValueError`:
    jamás se escribe fuera de `00-resources/` (D9.1, plan §T5).
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
    """Destino canónico de `add_source`: `00-resources/<subdir|_inbox>`, relativo al vault."""
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
    parsed = urlsplit(uri)
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

    Revisión Phase 2 (2026-10-27, SSRF): para `http(s)` se RECHAZA además —
    antes de cualquier fetch — userinfo en el URI (`user@host`), hosts de red
    interna (`localhost`, `*.local`) y direcciones loopback/privadas/link-
    local/reservadas, sea literal IP o por resolución DNS (`getaddrinfo`):
    el conversor fetch-ea desde el proceso del vault y un URI apuntando a la
    red interna (p. ej. `169.254.169.254` cloud metadata) es exfiltración,
    no una fuente. La DNS que no resuelve NO se rechaza: fallará en el fetch
    (`SOURCE_UNREACHABLE`), sin superficie SSRF por recorrer.
    """
    parsed = urlsplit(uri)
    if parsed.scheme == "file":
        resolve_file_uri(uri, vault_root)  # D16: lanza si queda fuera del vault
    elif parsed.scheme in ("http", "https"):
        if not parsed.netloc:
            raise ValueError(f"{parsed.scheme}: debe incluir host: {uri!r}")
        if parsed.username is not None:
            raise ValueError(
                f"http(s) con userinfo (usuario@host) rechazado (SSRF/filtración "
                f"de credenciales); sin credenciales inline: {uri!r}"
            )
        _deny_internal_host(uri)
    else:
        raise ValueError(f"uri debe empezar por http://, https:// o file:: {uri!r}")


def redact_uri(uri: str) -> str:
    """URI con credenciales REDACTADAS — para frontmatter, log y payload (review 2026-10-27).

    Configuración de exportación de credenciales de `add_source` (eje 4): el
    URI original queda SOLO para el fetch; toda persistencia/observabilidad
    usa ESTA versión:

    * userinfo (`//usuario:clave@`) → `//***@`;
    * query params cuyo nombre contiene `key`/`token`/`password`/`secret`
      (y de la review 5-ejes: `pwd`/`cred`/`auth`/`sess`/`sig`/`passphrase`)
      → valor `***` (orden y parámetros no secretos intactos);
    * el fragmento (post `#`) ES credencial frecuente (`#access_token=…`) y
      se sustituye completo por `***`;
    * un URI sin credenciales se devuelve BYTE A BYTE (Hyrum: los asserts de
      frontmatter existentes sin credenciales no notan el paso).
    """
    if urlsplit(uri).scheme not in ("http", "https"):
        return uri
    without_userinfo = re.sub(r"//[^/?#]*@", "//***@", uri)
    parsed = urlsplit(without_userinfo)
    if not parsed.query and not parsed.fragment:
        return without_userinfo
    params: list[tuple[str, str]] = []
    for name, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = name.lower()
        params.append(
            (name, "***") if any(word in lowered for word in QUERY_SECRET_WORDS) else (name, value)
        )
    return urlunsplit(
        parsed._replace(
            query=urlencode(params, safe="*"), fragment="***" if parsed.fragment else ""
        )
    )


QUERY_SECRET_WORDS: Final = (
    "key",
    "token",
    "password",
    "secret",
    "pwd",
    "cred",
    "auth",
    "sess",
    "sig",
    "passphrase",
)
"""Ítems query-parameter que delatan credencial para `redact_uri` (review SSRF; W-04)."""


def _deny_internal_host(uri: str) -> None:
    """Rechaza hosts de red interna en un `uri` http(s) — denylist SSRF (review 2026-10-27).

    Cubre (aprobado en la review): `localhost` y `*.local`; `127.0.0.0/8`,
    `::1`, `0.0.0.0`, `169.254.0.0/16`, `10.0.0.0/8`, `172.16.0.0/12` y
    `192.168.0.0/16`. El literal IP se resuelve con `ipaddress`; un hostname
    DNS que RESUELVE a alguna IP sensible también cae (`socket.getaddrinfo`)
    — el fetch del conversor resolvería por el mismo canal y alcanzaría el
    servicio interno. `is_private`/`is_link_local`/`is_reserved` son el
    superseto conservador de esos rangos exactos (más sobres, no menos).
    """
    host = urlsplit(uri).hostname or ""  # hostname ya minúsculas y sin corchetes (urlsplit)
    try:
        literal = ipaddress.ip_address(host) if host else None
    except ValueError:
        literal = None
    if literal is not None and _is_internal_address(literal):
        raise ValueError(_SSRF_MESSAGE.format(uri=redact_uri(uri)))
    if literal is None:
        host_l = host.lower()
        if host_l == "localhost" or host_l.endswith(".local"):
            raise ValueError(_SSRF_MESSAGE.format(uri=redact_uri(uri)))
        for resolved in _resolve_addresses(host):
            if _is_internal_address(resolved):
                raise ValueError(_SSRF_MESSAGE.format(uri=redact_uri(uri)))


def _is_internal_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """¿Es una dirección del espacio de red interna? (review SSRF 2026-10-27)."""
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
        or address.is_multicast  # 224.0.0.0/4 y ff00::/8 (CGNAT/Tailscale abajo)
        or address in ipaddress.ip_network("100.64.0.0/10")  # CGNAT / Tailscale MagicDNS
    )


def _resolve_addresses(hostname: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Resuelve DNS el hostname (`getaddrinfo`); sin resolver ⇒ [] (el fetch fallará)."""
    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    try:
        infos = socket.getaddrinfo(hostname, None)
    except (OSError, UnicodeError):
        return addresses
    for info in infos:
        try:
            addresses.append(ipaddress.ip_address(info[4][0]))
        except ValueError:
            continue
    return addresses


_SSRF_MESSAGE: Final = (
    "URI no aceptable: add_source no alcanza hosts de red interna (localhost, "
    "*.local, loopback o rangos privados/reservados) — usa la URL pública "
    "de la fuente: {uri!r}"
)


def resolve_file_uri(uri: str, vault_root: Path) -> Path:
    """Resuelve un `file:` a una ruta absoluta DENTRO del vault, o `ValueError` (D16).

    Frontera de confianza de `add_source`: markitdown con `file:` puede leer
    cualquier archivo accesible al proceso (spec-markitdown §Seguridad del
    canal), así que este borde aplica la versión estricta ratificada en D16 —
    TODO lo que quede fuera del vault se RECHAZA aquí, antes de convertir.
    `resolve()` (no-strict) colapsa `..` y symlinks: un enlace DENTRO del
    vault que apunta FUERA también cae rechazado. Inexistente o no-fichero ⇒
    `ValueError`: una ruta mal escrita es `VALIDATION_ERROR` (D64), nunca un
    documento ilegible (`SOURCE_UNREACHABLE`).
    """
    parsed = urlsplit(uri)
    if parsed.scheme != "file":
        raise ValueError(f"solo `file:` se resuelve como ruta local: {uri!r}")
    if parsed.netloc:
        raise ValueError(f"`file:` sin host (usa file:///ruta/absoluta): {uri!r}")
    local = Path(unquote(parsed.path))
    if not local.is_absolute():
        raise ValueError(f"`file:` debe ser una ruta absoluta: {uri!r}")
    try:
        resolved = local.resolve()
    except ValueError as exc:  # W-03: null byte (`%00`) del OS — input mal escrito, no bug
        raise VaultPathError(f"ruta invalida: {uri!r} ({exc})") from None
    if not resolved.is_relative_to(vault_root.resolve()):
        raise ValueError(f"D16: `file:` fuera del vault rechazado: {uri!r}")
    if not resolved.is_file():
        raise ValueError(f"`file:` inexistente o no es un fichero (ruta mal escrita): {uri!r}")
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


# --- Frontera B′: entrada y salida dentro del vault (T7, D31/D64/D65) --------------


class VaultPathError(ValueError):
    """Ruta rechazada en el borde B′: el handler la mapea a `VALIDATION_ERROR`.

    Subclase de `ValueError` para que los bordes existentes que ya capturan
    `ValueError` sigan funcionando; `details` es el `details` del payload
    (forma de spec-mcp-server §Manejo de errores).
    """

    def __init__(self, message: str, details: dict[str, object] | None = None) -> None:
        """Fija el mensaje accionable y el `details` estructurado (opcional)."""
        super().__init__(message)
        self.details = details


def vault_dirs(vault_root: Path) -> tuple[str, ...]:
    """Directorios de PRIMER nivel del vault, ordenados y sin los de punto (D67).

    `.tepochcalli/`, `.obsidian/` y `.trash/` no son raíces indexables; el resto
    es lo que `rag_status.index.available_roots` publica y lo que el agente usa
    para corregir una raíz mal escrita.
    """
    if not vault_root.is_dir():
        return ()
    return tuple(
        sorted(
            entry.name
            for entry in vault_root.iterdir()
            if entry.is_dir() and not entry.name.startswith(".")
        )
    )


def _kind(path: Path) -> str:
    """Tipo de una ruta en los términos del contrato: `file`, `directory` u `other`."""
    if path.is_dir():
        return "directory"
    return "file" if path.is_file() else "other"


def _first_missing(resolved: Path, root: Path) -> str:
    """Segmento que falta, el primero que no existe desde la raíz del vault (D64).

    Es el nombre con el que se compara para sugerir: en `Documentos/x.docx` el
    typo está en `Documentos`, no en el fichero — `informe.docx` no se parece a
    ninguna carpeta y no habría sugerencia útil.
    """
    current = root
    for part in resolved.relative_to(root).parts:
        current = current / part
        if not current.exists():
            return part
    return resolved.name


def _missing_details(requested: str, resolved: Path, vault_root: Path) -> dict[str, object]:
    """`details` del cubo «no existe»: qué se pidió, qué se parece y qué hay (D64)."""
    dirs = vault_dirs(vault_root)
    return {
        "requested": requested,
        "exists": False,
        "suggestions": suggest_names(_first_missing(resolved, vault_root), dirs),
        "vault_dirs": list(dirs),
    }


def _wrong_type_details(requested: str, expected: str, found: Path) -> dict[str, object]:
    """`details` del cubo «existe pero no es del tipo pedido» (D64)."""
    return {
        "requested": requested,
        "exists": True,
        "expected": expected,
        "found": _kind(found),
    }


def _resolve_within_vault(raw: str | Path, root: Path) -> tuple[Path, str]:
    """Resuelve `raw` dentro del vault (B′) o lanza `VaultPathError`.

    `root` debe venir ya resuelto (`vault_root.resolve()`). Cubre los rechazos
    comunes de entrada y destino: vacía, `..`, null byte (W-03) y ruta que no
    resuelve dentro del vault. Devuelve la forma ABSOLUTA resuelta y el texto
    pedido (los cubos posteriores lo nombran en su mensaje).
    """
    text = str(raw).strip()
    if not text:
        raise VaultPathError("ruta vacía: indica un path dentro del vault")
    candidate = Path(text.replace("\\", "/"))
    if ".." in candidate.parts:
        raise VaultPathError(f"ruta con segmentos '..' (escape del vault): {text!r}")
    try:
        resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
    except ValueError as exc:  # W-03: null byte (`output_path="a\x00.md"`) — no bug nuestro
        raise VaultPathError(f"ruta invalida: {text!r} ({exc})") from None
    if not resolved.is_relative_to(root):
        raise VaultPathError(f"fuera del vault (B′): {text!r} no resuelve dentro de {root}")
    return resolved, text


def validate_input_path(
    raw: str | Path,
    vault_root: Path,
    *,
    expect: Literal["file", "directory"] | None = None,
) -> Path:
    """Valida una ENTRADA (debe existir) y devuelve su forma ABSOLUTA resuelta.

    Inexistente ⇒ `VaultPathError` con `details.suggestions`; `expect` exige
    además el tipo (el conversor pide `file`, una raíz no exige nada). Absoluta
    externa, `..` o symlink que escapa ⇒ `VaultPathError` sin `details` (el
    mensaje lleva la ruta y el motivo).
    """
    root = vault_root.resolve()
    resolved, text = _resolve_within_vault(raw, root)
    if not resolved.exists():
        raise VaultPathError(f"la ruta no existe: {text!r}", _missing_details(text, resolved, root))
    if expect is not None and _kind(resolved) != expect:
        raise VaultPathError(
            f"se esperaba un {expect} y es un {_kind(resolved)}: {text!r}",
            _wrong_type_details(text, expect, resolved),
        )
    return resolved


def validate_destination(raw: str | Path, vault_root: Path) -> Path:
    """Valida un DESTINO (aún no existe) y devuelve su forma ABSOLUTA resuelta.

    Se valida el **padre**, que debe existir y ser directorio — el fichero
    todavía no existe. Absoluta externa, `..` o symlink que escapa ⇒
    `VaultPathError` sin `details` (el mensaje lleva la ruta y el motivo).
    """
    root = vault_root.resolve()
    resolved, text = _resolve_within_vault(raw, root)
    parent = resolved.parent
    if not parent.is_dir():
        if parent.exists():
            raise VaultPathError(
                f"el padre de {text!r} no es un directorio",
                _wrong_type_details(text, "directory", parent),
            )
        raise VaultPathError(
            f"el directorio padre de {text!r} no existe",
            _missing_details(text, parent, root),
        )
    return resolved


def validate_vault_path(
    raw: str | Path,
    vault_root: Path,
    *,
    must_exist: bool,
    expect: Literal["file", "directory"] | None = None,
) -> Path:
    """Dispatcher del borde B′: entrada (`must_exist=True`) o destino (`False`).

    La lógica ya NO vive en el flag: `validate_input_path` cubre la entrada
    (debe existir, con `expect` opcional) y `validate_destination` el destino
    (se valida el padre). La puerta única se conserva porque los tests del
    borde la llaman directamente (test_paths_frontier.py); los handlers de
    producción ya usan la función específica. Con `must_exist=False`,
    `expect` se ignora — igual que en la versión monolítica.
    """
    if must_exist:
        return validate_input_path(raw, vault_root, expect=expect)
    return validate_destination(raw, vault_root)


def validate_roots(directories: Sequence[str] | None, vault_root: Path) -> tuple[str, ...]:
    """Valida N raíces indexables y devuelve sus rutas RELATIVAS al vault (D32/D44/D65).

    `None` o lista vacía ⇒ `("00-resources",)` (el default del producto, D42 —
    `config.DEFAULT_INDEXER_ROOTS`). Cada raíz pasa las mismas reglas que una
    entrada (`validate_vault_path`) y
    además debe existir: una raíz puede ser un **fichero suelto** (D46). El
    fallo es **atómico**: se lanzan `VaultPathError` —que nombra la raíz mala,
    sus `suggestions` y `vault_dirs`— antes de devolver ninguna, así una raíz
    mal escrita no deja media indexación hecha (D65).
    """
    entries = [str(item).strip() for item in (directories or ())]
    roots: list[str] = []
    for entry in [entry for entry in entries if entry] or list(DEFAULT_INDEXER_ROOTS):
        relative = (
            validate_input_path(entry, vault_root).relative_to(vault_root.resolve()).as_posix()
        )
        if relative == ".":
            raise VaultPathError(
                f"la raíz debe ser una subruta del vault, no el vault entero: {entry!r}"
            )
        roots.append(relative)
    return tuple(roots)
