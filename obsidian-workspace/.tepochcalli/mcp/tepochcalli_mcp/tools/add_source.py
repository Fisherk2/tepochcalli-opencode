"""Handler de `add_source`: convertir, escribir y reindexar en una llamada (T5, Facade).

El camino de ENTRADA de material nuevo (tasks/plan.md §6 T5, criterio 7 de
UH.md): el usuario da un `uri` http(s)/`file:`, el server lo convierte a
Markdown con markitdown **en proceso** (D-b: misma librería, sin subproceso
ni cliente MCP), lo deja citado en `00-Resources/<subdir|_inbox>/` con
frontmatter de trazabilidad (spec-markitdown §Contrato) y reindexa con el
MISMO ciclo Δ de T3 — una sola tool call, patrón Facade (plan §8).

**Desviación del plan §5 documentada (decisión, no accidente):** el diagrama
del plan dibuja `TOOLS --> CONV` (el handler importando `convert.py`), pero
la regla TEXTUAL del mismo §5 («los módulos de dominio no importan
`markitdown`») y el test de arquitectura ya en pie lo prohíben de forma
 transitiva: `convert.py` importa `markitdown`, raíz prohibida para
`tepochcalli_mcp.tools.*`. Se sigue LA PUERTA: el handler recibe la
costura `convert` (factory/función) inyectada desde `server.py` —el
composition root, único exento— exactamente igual que `SearchBackend`
(T2) y el seam de refresh (T3). La desviación vive también en el wiring de
`server.py`.

Contrato y precedencia, en orden:

1. **Borde de validación** — esquema (`http(s):`/`file:`; D16: `file:` fuera
   del vault ⇒ `VALIDATION_ERROR`, decidido ANTES de que el conversor vea
   la ruta) y `subdir` (`paths.validate_subdir`, anti-traversal);
2. **raíz declarada** — `add_source` escribe SIEMPRE en `00-Resources/`
   (D9.1): si esa raíz no está en `INDEXER_DIR` ⇒ `VALIDATION_ERROR` con
   `details.{requested,allowed,hint}` ANTES de convertir o escribir. La
   comparación normaliza ambos lados (`./00-Resources/` ≡ `00-Resources`);
   `details.allowed` muestra lo declarado tal cual. El MCP no añade raíces al
   índice (el conjunto lo posee el usuario);
3. **corte `E_NO_EMBEDDER`** — sin embedder no hay indexación, y escribir sin
   indexar deja un huérfano en el vault: se corta ANTES de convertir y de
   escribir (spec-mcp-server §Códigos lista también esta tool);
4. **conversión** — la costura inyectada; cualquier fallo de fetch/convert
   ⇒ `SOURCE_UNREACHABLE` con la guía literal de spec-markitdown (el
   traceback va al log stderr, nunca al cliente);
5. **escritura atómica** — slug + `.md` con sufijo numérico ante colisión
   (`paths`), temporal en el MISMO directorio de destino + `os.replace`
   (`writer.write_atomic`, la MISMA función del conversor — D63/D66), con
   `ensure_within` como última defensa antes de escribir. W-01: las raíces
   declaradas se RE-validan con `paths.validate_roots` antes del
   `write_atomic` — una raíz mal escrita explota en el refresh de cola con
   el fichero ya huérfano; el borde respuesta `VALIDATION_ERROR` con
   `details.vault_dirs` + `suggestions` — cero ficheros en el vault;
6. **reindexación** — el MISMO seam de refresh de T3, con EXACTAMENTE las
   raíces configuradas; reporte con `locked` ⇒ `ENGINE_LOCKED` (la forma
   congelada de §5 no tiene campo `locked` en su sub-objeto `indexed`, así
   que el candado viaja COMO ERROR con `details.written_to`: el archivo sí
   quedó, el ciclo Δ es reintentable). Nota de coste (W4/P-03, sin cambio
   de contrato D65): CADA llamada paga UN ciclo Δ completo — no hay flag
   sin-refresh ni debounce —; el Δ memoizado evita re-parse de lo ya
   indexado, pero el walk corre entero por llamada, así que un agente que
   añade N fuentes seguidas paga N walks (y N filas de refresh en el log).

`@errors.internal_guard` (G1) envuelve el handler completo — arranque de
`vault_root` incluido—: cualquier fallo no mapeado ⇒ `INTERNAL` canónico.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from tepochcalli_flow.citation import RESOURCES_DIR

from tepochcalli_mcp import embedder, errors, paths, writer

logger = logging.getLogger(__name__)

INDEXED_FIELDS: tuple[str, ...] = ("scanned", "indexed", "skipped", "elapsed_ms")
"""Los 4 campos del sub-objeto `indexed` de §5 — SIN `locked` (contrato congelado)."""


def _normalized_root(entry: str) -> str:
    """Raíz comparable: `PurePosixPath` resuelve `./` y barras finales.

    `..` NO se normaliza aquí: el borde (`paths.validate_roots`) lo rechaza
    antes de indexar; este helper solo iguala formas equivalentes de la misma
    raíz (`./00-Resources/` ≡ `00-Resources`).
    """
    return PurePosixPath(entry.strip().replace("\\", "/")).as_posix()


@errors.internal_guard
async def add_source(
    uri: str,
    subdir: str | None = None,
    *,
    vault_root: Callable[[], Path],
    convert: Callable[[str], str],
    refresh: Callable[[], dict[str, object]],
    embedder_available: Callable[[], bool],
    allowed_roots: Callable[[], tuple[str, ...]],
) -> dict[str, object]:
    """`{ok, written_to, indexed:{scanned, indexed, skipped, elapsed_ms}}` — forma §5.

    `convert` es la costura de markitdown inyectada por el composition root
    (ver módulo: el plan §5 dibuja `TOOLS → CONV`, la puerta de arquitectura
    impone la costura); `refresh` es el MISMO seam de T3 — el handler no
    importa `tepochcalli_flow.app` (test de arquitectura). `allowed_roots` son
    las raíces declaradas por el usuario (`INDEXER_DIR`), comparadas
    NORMALIZADAS (`./00-Resources/` ≡ `00-Resources`): `add_source` escribe
    SIEMPRE en `00-Resources/`, así que si esa raíz no está declarada se
    rechaza ANTES de escribir nada — el MCP no añade raíces al índice.
    """
    root = vault_root().resolve()
    try:
        paths.validate_source_uri(uri, root)
        subdir_rel = paths.validate_subdir(subdir)
    except ValueError as exc:
        return errors.validation_error(str(exc))
    allowed = allowed_roots()
    if _normalized_root(RESOURCES_DIR) not in {_normalized_root(root) for root in allowed}:
        return errors.validation_error(
            f"add_source escribe en {RESOURCES_DIR}/, pero esa raíz no está declarada "
            f"en INDEXER_DIR; el MCP no añade raíces al índice: {list(allowed)}",
            {
                "requested": RESOURCES_DIR,
                "allowed": list(allowed),
                "hint": (
                    f"Declara {RESOURCES_DIR} en INDEXER_DIR (opencode.json) para usar "
                    "add_source; el conjunto de raíces lo define el usuario."
                ),
            },
        )
    if not embedder_available():
        # VALIDATION_ERROR precede: el borde ya validó, y sin indexación
        # convertir/escribir solo fabricaría huérfanos. Igual que los hermanos.
        return errors.no_embedder()
    try:
        content = await asyncio.to_thread(convert, uri)
    except paths.VaultPathError as exc:
        # W-02: un redirect hacia la red interna sube como `VaultPathError` del
        # guard por hop — entrada mal dirigida que el agente puede corregir
        # (VALIDATION_ERROR), no inalcanzable; `exc.details` viene del guard.
        return errors.validation_error(str(exc), exc.details)
    except Exception as exc:  # fetch/convert: cualquier motivo ⇒ SOURCE_UNREACHABLE
        # Review Phase 2 (eje 4): log y payload REDACTAN el URI (userinfo/query
        # secreta); el original solo queda dentro de esta llamada (fetch ya corrió).
        redacted = paths.redact_uri(uri)
        logger.exception("add_source: fallo de fetch/convert para %s", redacted)
        return errors.source_unreachable(redacted, type(exc).__name__)
    dest_dir = root / paths.resources_destination(subdir_rel)
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        # W-01: una raíz declarada pero MAL escrita explota en el refresh de
        # cola (`normalize_roots` ⇒ FileNotFoundError ⇒ INTERNAL) con el fichero
        # ya escrito — huérfano. El borde la juzga igual que `index_refresh`
        # (VALIDATION_ERROR con `details.vault_dirs` + `suggestions`) antes de
        # la escritura: `00-Resources/_inbox` ya existe (el mkdir la creó), así
        # que una raíz mala es la ÚNICA cosa que puede disparar aquí.
        paths.validate_roots(allowed, root)
    except paths.VaultPathError as exc:
        return errors.validation_error(str(exc), exc.details)
    name = paths.available_name(
        paths.slugify_uri(uri), lambda candidate: (dest_dir / candidate).exists()
    )
    final = paths.ensure_within(root / RESOURCES_DIR, dest_dir / name)
    writer.write_atomic(final, content)
    written_to = final.relative_to(root).as_posix()
    try:
        report = await asyncio.to_thread(refresh)
    except embedder.EmbedderAuthError as exc:
        # T6: clave ausente del flow (litellm sin api_key_env) traducida por el
        # composition root — `E_API_AUTH` (spec §Códigos lista add_source) y no
        # INTERNAL. El archivo YA se escribió: tras reponer la clave basta con
        # `index_refresh` — el texto del fix lo dice.
        return errors.api_auth(str(exc))
    if report.get("locked"):
        return errors.engine_locked(details={"written_to": written_to})
    indexed = {field: report[field] for field in INDEXED_FIELDS}
    return {"ok": True, "written_to": written_to, "indexed": indexed}
