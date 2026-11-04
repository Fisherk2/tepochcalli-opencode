"""Test de arquitectura: el dominio del flow y del server nunca dependen de infraestructura.

CP-B, T9 (Phase 1) + extensión T2 al paquete `tepochcalli_mcp`.

Enuncia executablemente la regla hexagonal de ADR-005 («la dependencia apunta
hacia dentro»): `tepochcalli_flow.citation`, `tepochcalli_flow.config` y
`tepochcalli_flow.ports` son código de dominio puro y su cierre transitivo de
imports **nunca** puede alcanzar
la infraestructura del motor de indexación (`cocoindex`) ni del indexador
vectorial (`lancedb`). El propio `tepochcalli_flow/__init__.py` también está bajo
la regla —importar el paquete lo ejecuta—; el resto del paquete (`models`,
`app`, `source`, `parsers`, `verify` y `adapters/`) ES infraestructura y sí puede
importar el engine —
este test no lo toca. T9 añade `ports` al conjunto protegido (el puerto de
lectura que Phase 2 consume) y, en la dirección opuesta, afirma que el
adaptador `adapters/lancedb_reader` SÍ alcanza `lancedb`: la frontera corre
exactamente entre `ports.py` y `adapters/`, ni un módulo más allá.

**Extensión T2 al paquete `tepochcalli_mcp`** (decisión registrada aquí, como
Phase 1 registró la suya): el AC de T2 «el server no importa `cocoindex` ni
`lancedb`» es inalcanzable al pie de la letra — algo tiene que construir el
lector. La frontera se dibuja como en Phase 1:

* **Protegidos (banned roots + allowlist):** `tepochcalli_mcp` (`__init__`),
  `errors`, `budget`, `paths` (dominio puro: ni `mcp` SDK ni engines) y
  `tools`/`tools.search` (handlers: sin `cocoindex`/`lancedb`/`markitdown`/
  `litellm` — el SDK `mcp.types` SÍ está permitido en `tools/__init__.py`,
  que es donde el resultado se empaqueta en `CallToolResult`).
* **Exento (composition root):** `tepochcalli_mcp.server`, análogo a Phase 1
  donde `app`/`adapters/` son infraestructura: es el ÚNICO módulo del server
  que puede importar el SDK, el flow con motor y `lancedb` — el test positivo
  de abajo afirma que `server` SÍ alcanza `lancedb`, exactamente igual que el
  `adapters` del flow.

Garantías que ofrece, y cómo:

* **Negativa (banned roots).** Un recorrido BFS sobre los imports resueltos con
  `ast` (sin ejecutar ni importar los módulos analizados) sigue solo las aristas
  «in-project» (`tepochcalli_flow.*` y `tepochcalli_mcp.*`, incluidas relativas
  `from .x import ...`) y falla naming la cadena exacta del alias, p. ej.
  `tepochcalli_flow.citation -> tepochcalli_flow.models -> cocoindex`.
  Un grep directo sobre un solo archivo NO detectaría esa cadena: la violación
  es transitive por diseño. `BANNED_INFRA_ROOTS` es una constante de módulo
  extensible (T9 pudo añadir `litellm` sin reestructurar nada).
* **Positiva (allowlist de dominio).** El mismo cierre transitivo de los
  módulos de dominio debe importar ÚNICAMENTE stdlib
  (`sys.stdlib_module_names`) + módulos in-project (`tepochcalli_flow.*` /
  `tepochcalli_mcp.*`).
  Decisión de allowlist documentada aquí: stdlib + in-project y nada más — así
  un contribuidor futuro no puede colar numpy (ni ningún tercero) en el dominio
  ni siquiera vía un helper in-project.
* **Sanidad del propio walker.** Comprueba que el recorrido sí resuelve aristas
  in-project reales (citation -> config; tools.search -> budget), para que un
  fallo de resolución de paths no convierta los otros tests en vacíamente verdes.
* **Límite declarado, no adversarial.** El walker solo ve `ast.Import` y
  `ast.ImportFrom`: los imports dinámicos (`importlib.import_module("cocoindex")`,
  `__import__(...)`) quedan FUERA del recorrido — este test no los detectaría.

Fuentes de verdad: ADR-005 (hexagonal), ADR-002 (sin demonios/red), los
docstrings de `citation.py` y `config.py` («código de dominio: NO importa
cocoindex ni lancedb») y tasks/todo.md → gate CP-B (T2 cierra la extensión al
server).
"""

from __future__ import annotations

import ast
import sys
from collections import deque
from pathlib import Path
from typing import Final

import pytest
import tepochcalli_flow
import tepochcalli_mcp

# --- constantes de la regla ----------------------------------------------------

PACKAGE: Final = "tepochcalli_flow"
"""Raíz del paquete in-project cuyo cierre transitivo se analiza."""

MCP_PACKAGE: Final = "tepochcalli_mcp"
"""Segundo paquete in-project: el server MCP (extensión T2)."""

_PACKAGE_DIRS: Final[dict[str, Path]] = {
    PACKAGE: Path(tepochcalli_flow.__file__).resolve().parent,
    MCP_PACKAGE: Path(tepochcalli_mcp.__file__).resolve().parent,
}
"""Directorios de ambos paquetes instalados (resueltos, no hardcodeados)."""

BANNED_INFRA_ROOTS: Final[frozenset[str]] = frozenset(
    {"cocoindex", "lancedb", "markitdown", "litellm"}
)
"""Raíces de import prohibidas para el dominio (ADR-005; T2 añade markitdown/litellm)."""

STDLIB_ROOTS: Final[frozenset[str]] = frozenset(sys.stdlib_module_names)
"""Raíces permitidas por ser stdlib de CPython 3.12 (incluye `tomllib`, `__future__`)."""

PERMITTED_DOMAIN_ROOTS: Final[frozenset[str]] = STDLIB_ROOTS | {PACKAGE}
"""Allowlist del dominio del flow: stdlib + in-project, y nada más (docstring del módulo)."""

MCP_PERMITTED_DOMAIN_ROOTS: Final[frozenset[str]] = STDLIB_ROOTS | {PACKAGE, MCP_PACKAGE}
"""Allowlist del dominio puro del server: stdlib + los dos paquetes in-project.

`errors`/`budget`/`paths` pueden importar `tepochcalli_flow.ports`/`citation`
—el puerto congelado ES su contrato— pero ni el SDK `mcp` ni engines (docstring).
"""

DOMAIN_MODULES: Final[tuple[str, ...]] = (
    PACKAGE,
    f"{PACKAGE}.citation",
    f"{PACKAGE}.config",
    f"{PACKAGE}.ports",
    f"{PACKAGE}.layout",
)
"""Módulos de dominio bajo la regla: el `__init__` del paquete y los módulos puros.

Importar `tepochcalli_flow.citation` EJECUTA `tepochcalli_flow/__init__.py` —el paquete
entero forma parte del cierre transitivo en runtime—, así que el `__init__` se analiza
igual que cualquier módulo de dominio. `ports.py` se añade en T9: es el PUERTO de lectura
(ADR-005) y debe permanecer sin motor — si el engine entrara por él, Phase 2 perdería la
garantía de que el contrato `search` sobrevive a un cambio de motor. El resto del paquete
(`models`, `app`, `source`, `parsers`, `verify` y `adapters/`) ES infraestructura y sí
puede importar el engine — este test no lo toca.
"""

MCP_PURE_DOMAIN_MODULES: Final[tuple[str, ...]] = (
    MCP_PACKAGE,
    f"{MCP_PACKAGE}.errors",
    f"{MCP_PACKAGE}.budget",
    f"{MCP_PACKAGE}.paths",
)
"""Dominio puro del server T2: banned roots + allowlist estricta (docstring)."""

MCP_TOOL_MODULES: Final[tuple[str, ...]] = (
    f"{MCP_PACKAGE}.tools",
    f"{MCP_PACKAGE}.tools.search",
    f"{MCP_PACKAGE}.tools.index_refresh",
    f"{MCP_PACKAGE}.tools.rag_status",
    f"{MCP_PACKAGE}.tools.add_source",
    f"{MCP_PACKAGE}.tools.convert_document",
    f"{MCP_PACKAGE}.tools.convert_base64",
    f"{MCP_PACKAGE}.tools.list_formats",
)
"""Handlers T2-T5: banned roots (engines), pero `mcp.types` permitido en `tools/__init__.py`.

Sin allowlist de terceros aquí a propósito: el empaquetado en `CallToolResult`
es frontera del SDK y vive en `tools/__init__.py`; lo que NO puede entrar es
el motor (`cocoindex`/`lancedb`) ni los conversores (`markitdown`/`litellm`).
T4 añade `tools.rag_status` y REPARA el hueco de T3: `tools.index_refresh`
existía pero no estaba en la parametrización (la sanity de abajo es la que
impide que un módulo ausente pase vacío). T5 añade `tools.add_source`: su
conversor (`convert.py`, con `markitdown`) se cablea desde el composition
root vía costura — la desviación `TOOLS → CONV` del plan §5, documentada en
el propio handler.

**Enmienda T6 a esta regla (documentada como Phase 1 documentó la suya):**
`tepochcalli_mcp.embedder` ES la **fábrica de provider** del plan §5 — su
import perezoso de `litellm`/`sentence_transformers` es el ÚNICO permitido
dentro del paquete, y los handlers solo la usan por sus HECHOS
(`mode`/`is_available`) y sus excepciones de dominio. El walker, partiendo de
los handlers, **registra la arista hacia `embedder` pero NO traspasa su
frontera** (`MCP_BOUNDARY_MODULES`): sin eso, `tools.search → embedder →
litellm` parecería una violación de los handlers que no lo es. El CONTENIDO de
la frontera se chequea con su propio test y banned-set adaptado (sin
`litellm`; engines igualmente proscritos). `server` sigue exento entero.
"""

MCP_COMPOSITION_ROOT: Final = f"{MCP_PACKAGE}.server"
"""Composition root del server: EXENTO de la regla (análogo a `app`/`adapters`)."""

MCP_PROVIDER_MODULE: Final = f"{MCP_PACKAGE}.embedder"
"""La fábrica de provider (plan §5): frontera de infraestructura del paquete (T6).

Su contenido se chequea CON su banned-set adaptado (abajo): `litellm` y
`sentence_transformers` son SU oficio; los engines siguen proscritos.
"""

MCP_BOUNDARY_MODULES: Final[frozenset[str]] = frozenset({MCP_PROVIDER_MODULE, MCP_COMPOSITION_ROOT})
"""Fronteras que el walker REGISTRA pero NO traspasa desde dominio/handlers (T6).

Ver enmienda T6 del docstring: `embedder` importa `litellm` perezosamente y un
recorrido que la traspasara marcaría a cada handler como violador del dialecto
que él mismo consume. La sanidad de abajo afirma que la arista SÍ se resuelve
(llega a `embedder`) y que NO se traspasa (no llega a `litellm`).
"""

BANNED_PROVIDER_ROOTS: Final[frozenset[str]] = frozenset({"cocoindex", "lancedb", "markitdown"})
"""Engines también prohibidos en la fábrica — `litellm`/`sentence_transformers` no (su oficio)."""

PERMITTED_PROVIDER_ROOTS: Final[frozenset[str]] = STDLIB_ROOTS | {
    PACKAGE,
    MCP_PACKAGE,
    "litellm",
    "sentence_transformers",
}
"""Allowlist de la fábrica: stdlib + in-project + los dos providers de lectura/escritura."""


# --- motor AST (sin importar los módulos analizados) ---------------------------


def _module_source(dotted: str) -> Path | None:
    """Resuelve un nombre punteado in-project (cualquiera de los dos paquetes) a fuente.

    `tepochcalli_flow.citation` -> `<flow>/citation.py`; `tepochcalli_mcp.tools`
    -> `<mcp>/tools/__init__.py`; el propio paquete -> su `__init__.py`; cualquier
    otro root (tercero, stdlib) -> None: el recorrido nunca intenta recursar
    dentro de paquetes ajenos.
    """
    package_dir = _PACKAGE_DIRS.get(dotted.split(".")[0])
    if package_dir is None:
        return None
    base = package_dir.joinpath(*dotted.split(".")[1:])
    module_py = base.with_suffix(".py")
    if module_py.is_file():
        return module_py
    package_init = base / "__init__.py"
    if package_init.is_file():
        return package_init
    return None


def _resolve_from(current_module: str, node: ast.ImportFrom) -> str:
    """Nombre absoluto base de un `from X import Y` (resuelve `level` relativo).

    `from .config import Config` en `tepochcalli_flow.citation` ->
    `tepochcalli_flow.config`; `from dataclasses import ...` -> `dataclasses`.
    Un nivel que escaparía del paquete se recorta a raíz (imports ilegales que
    Python rechazaría en runtime de todos modos).
    """
    if node.level == 0:
        return node.module or ""
    parts = current_module.split(".")
    keep = (len(parts) - 1) - (node.level - 1)  # el layout del flow es plano
    base = parts[: max(keep, 0)]
    if node.module:
        base = [*base, *node.module.split(".")]
    return ".".join(base)


def _import_targets(tree: ast.Module, current_module: str) -> set[str]:
    """Nombres punteados que `tree` importa, con relativas resueltas a absolutas.

    `ast.walk` cubre imports anidados (try/TYPE_CHECKING/funciones): conservador
    a propósito — un import condicional también es una dependencia. Para
    `from pkg import sub` se emit tanto `pkg` como `pkg.sub` para que el walker
    siga el submódulo in-project si existe.
    """
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_from(current_module, node)
            if base:
                targets.add(base)
            targets.update(f"{base}.{alias.name}" if base else alias.name for alias in node.names)
    return targets


def _walk_imports(start: str) -> list[tuple[list[str], str]]:
    """Cierre transitivo de imports de `start` siguiendo solo aristas in-project.

    BFS con `visited` (grafo cíclico seguro). Devuelve pares
    `(cadena_de_módulos, import_alcanzado)` donde la cadena documenta el camino
    completo desde el módulo de dominio hasta el módulo que hace el import —
    el fallo se diagnostica con ` -> `.join(cadena + [import]), p. ej.
    `tepochcalli_flow.citation -> tepochcalli_flow.models -> cocoindex`.
    """
    results: list[tuple[list[str], str]] = []
    queue: deque[list[str]] = deque([[start]])
    visited: set[str] = set()
    while queue:
        chain = queue.popleft()
        module = chain[-1]
        if module in visited:
            continue
        visited.add(module)
        source = _module_source(module)
        if source is None:
            continue
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for target in sorted(_import_targets(tree, module)):
            if target.split(".")[0] in _PACKAGE_DIRS:
                child = _module_source(target)
                # Frontera T6: la arista SE REGISTRA pero no se traspasa (docstring).
                if child is not None and target not in MCP_BOUNDARY_MODULES:
                    queue.append([*chain, target])
            results.append((chain, target))
    return results


def _describe(chain: list[str], target: str) -> str:
    """Cadena de dependencia legible para el mensaje de fallo."""
    return " -> ".join([*chain, target])


# --- tests ---------------------------------------------------------------------


@pytest.mark.parametrize("module", DOMAIN_MODULES + MCP_PURE_DOMAIN_MODULES + MCP_TOOL_MODULES)
def test_domain_modules_never_reach_banned_infrastructure(module: str) -> None:
    """Ningún import alcanzable desde un módulo de dominio tiene raíz prohibida.

    Transitive por construcción: si `citation` importara un helper in-project
    que importa `cocoindex`, el BFS lo alcanzaría y reportaría la cadena entera.
    Extiende en T2 al dominio y a los handlers de `tepochcalli_mcp`; el
    composition root (`server.py`) queda FUERA por decisión documentada.
    """
    for chain, target in _walk_imports(module):
        root = target.split(".")[0]
        assert root not in BANNED_INFRA_ROOTS, (
            f"El módulo de dominio {module} alcanza infraestructura prohibida: "
            f"{_describe(chain, target)} (raíces prohibidas: "
            f"{', '.join(sorted(BANNED_INFRA_ROOTS))})"
        )


@pytest.mark.parametrize(
    ("module", "permitted"),
    [
        *((module, PERMITTED_DOMAIN_ROOTS) for module in DOMAIN_MODULES),
        *((module, MCP_PERMITTED_DOMAIN_ROOTS) for module in MCP_PURE_DOMAIN_MODULES),
    ],
)
def test_domain_transitive_imports_stay_stdlib_and_in_project(
    module: str, permitted: frozenset[str]
) -> None:
    """El cierre transitivo del dominio solo importa stdlib + paquetes in-project.

    Allowlist cerrada (decisión documentada en el docstring del módulo): además
    de las raíces prohibidas explícitas, ningún tercero — p. ej. numpy — puede
    entrar al dominio ni siquiera a través de un módulo in-project. Para el
    dominio puro del server la allowlist añade `tepochcalli_flow.*` (el puerto
    congelado es SU contrato) pero sigue sin admitir el SDK `mcp`.
    """
    for chain, target in _walk_imports(module):
        root = target.split(".")[0]
        assert root in permitted, (
            f"El módulo de dominio {module} importa un tercero no permitido: "
            f"{_describe(chain, target)} (allowlist: {', '.join(sorted(permitted))})"
        )


CONVERT_BANNED_ROOTS: Final[frozenset[str]] = frozenset({"cocoindex", "lancedb"})
"""W-13 (a): engines proscritos TAMBIÉN para la costura del conversor.

`tepochcalli_mcp.convert` ES infraestructura (importa `markitdown` EN PROCESO,
su oficio — por eso no entra en `BANNED_INFRA_ROOTS`), pero la costura no toca
motores de índice: no es un pretexto para alcanzar `cocoindex`/`lancedb`.
"""


@pytest.mark.parametrize("module", [f"{MCP_PACKAGE}.convert"])
def test_converter_reaches_neither_engine(module: str) -> None:
    """W-13 (a): `convert.py` (markitdown in-process) NO alcanza motores de índice.

    Parametrización a parte de la de dominio porque `markitdown` es SU oficio:
    la frontera invariante es `cocoindex`/`lancedb` — la costura del conversor
    no es un pretexto para crear un índice.
    """
    for chain, target in _walk_imports(module):
        root = target.split(".")[0]
        assert root not in CONVERT_BANNED_ROOTS, (
            f"La costura del conversor {module} alcanza un engine: {_describe(chain, target)}"
        )


def test_converter_reach_is_markitdown_only() -> None:
    """Sanidad del mismo test: `convert` SÍ importa `markitdown` (su oficio).

    Sin esta ancla, un `_module_source` roto volvería el test parametrizado de
    arriba vacío-verde.
    """
    reached = {target for _chain, target in _walk_imports(f"{MCP_PACKAGE}.convert")}
    assert "markitdown" in reached, "el conversor importa la librería EN PROCESO"


@pytest.mark.parametrize("module", MCP_TOOL_MODULES)
def test_tool_handlers_allow_mcp_types_only_never_the_sdk_server(module: str) -> None:
    """W-13 (b): en los handlers `mcp.types` sí (empaquetado); `mcp.server.*` JAMÁS.

    Los handlers construyen dicts; SOLO el composition root habla con el SDK.
    El walker corrige imports en ambos sentidos: `import mcp.types` (permitido
    en `tools/__init__.py`) no debe tapar un `mcp.server.*` colado más tarde.
    """
    for chain, target in _walk_imports(module):
        if target == "mcp" or target.startswith("mcp."):
            allowed = target == "mcp.types" or target.startswith("mcp.types.")
            assert allowed, (
                f"El handler {module} alcanza el SDK fuera de `mcp.types`: "
                f"{_describe(chain, target)} — el SDK del server vive solo en `server.py`"
            )


def test_walker_follows_in_project_import_edges_transitively() -> None:
    """El walker sí resuelve aristas in-project: citation -> config es alcanzable.

    Guarda anti-falso-verde: si `_module_source` dejara de resolver paths, los
    dos tests anteriores pasarían sin analizar nada; esta sanidad los ancla a la
    realidad del layout del paquete.
    """
    reached = {target for _chain, target in _walk_imports(f"{PACKAGE}.citation")}
    assert f"{PACKAGE}.config" in reached


def test_ports_reaches_config_but_never_the_engine() -> None:
    """`ports.py` sí resuelve su arista in-project (config) — sanidad de walker.

    Análoga a la de citation→config: si la resolución de paths de `ports`
    fallara, el test parametrizado sobre `ports` pasaría vacío. Además afirma
    que el puerto no importa `adapters`: la dependencia apunta hacia dentro.
    """
    reached = {target for _chain, target in _walk_imports(f"{PACKAGE}.ports")}
    assert f"{PACKAGE}.config" in reached
    assert not any(target.startswith(f"{PACKAGE}.adapters") for target in reached)


def test_lancedb_adapter_is_allowed_to_reach_lancedb() -> None:
    """Dirección OPUESTA: `adapters/lancedb_reader` SÍ alcanza `lancedb` (infra).

    Prueba el otro lado de la frontera de T9: si el walker no viera el import
    del adaptador —p. ej. por una rotura en `_module_source`—, los tests
    negativos sobre el dominio darían falsos positivos de seguridad. La
    frontera exacta es ports.py (sin motor) ← adapters/ (con motor).
    """
    reached = {target for _chain, target in _walk_imports(f"{PACKAGE}.adapters.lancedb_reader")}
    assert "lancedb" in reached, (
        "el adaptador LanceDB debe importar lancedb: ES infraestructura (ADR-005)"
    )
    assert f"{PACKAGE}.ports" in reached, "el adaptador implementa el puerto: lo importa"


def test_walker_covers_the_second_package_transitively() -> None:
    """Sanidad T2/T4: el walker resuelve aristas de `tepochcalli_mcp` (anti-falso-verde).

    `tools.search` debe alcanzar `budget` y el puerto `tepochcalli_flow.ports`
    por aristas reales; sin esta ancla, los tests parametrizados sobre el
    segundo paquete pasarían vacíos si `_PACKAGE_DIRS` dejara de resolver.
    T4 extiende la sanidad a los tools añadidos después: cada `tools.*` nuevo
    tiene que resolver sus propias aristas in-project — si el módulo no existe
    (o su path no resuelve), el recorrido sale VACÍO y este test FALLA en vez
    de dejar pasar la parametrización sin analizar nada.
    """
    reached = {target for _chain, target in _walk_imports(f"{MCP_PACKAGE}.tools.search")}
    assert f"{MCP_PACKAGE}.budget" in reached
    assert f"{MCP_PACKAGE}.paths" in reached
    assert f"{PACKAGE}.ports" in reached

    reached_refresh = {
        target for _chain, target in _walk_imports(f"{MCP_PACKAGE}.tools.index_refresh")
    }
    assert f"{MCP_PACKAGE}.errors" in reached_refresh, "index_refresh (T3) usa la guarda de errors"

    reached_status = {target for _chain, target in _walk_imports(f"{MCP_PACKAGE}.tools.rag_status")}
    assert f"{MCP_PACKAGE}.embedder" in reached_status, (
        "rag_status (T4) consume el mapeo mode/dims/provider de embedder"
    )
    assert f"{PACKAGE}.config" in reached_status

    reached_add = {target for _chain, target in _walk_imports(f"{MCP_PACKAGE}.tools.add_source")}
    assert f"{MCP_PACKAGE}.errors" in reached_add, "add_source (T5) usa la guarda y sus payloads"
    assert f"{MCP_PACKAGE}.paths" in reached_add, "add_source (T5) delega validación/ slug en paths"
    assert f"{MCP_PACKAGE}.convert" not in reached_add, (
        "desviación TOOLS→CONV: el handler NO importa convert.py (markitdown); va por costura"
    )
    assert "markitdown" not in {target.split(".")[0] for target in reached_add}, (
        "add_source es dominio del server: el conversor se cablea desde el composition root"
    )

    reached_convert = {
        target for _chain, target in _walk_imports(f"{MCP_PACKAGE}.tools.convert_document")
    }
    assert f"{MCP_PACKAGE}.summary" in reached_convert, "T9: el resumen vive en summary.py"
    assert f"{MCP_PACKAGE}.writer" in reached_convert, "T9: la escritura es la compartida"
    assert "markitdown" not in {target.split(".")[0] for target in reached_convert}, (
        "convert_document (T9) va por costura: tools/ NUNCA importa markitdown"
    )

    reached_base64 = {
        target for _chain, target in _walk_imports(f"{MCP_PACKAGE}.tools.convert_base64")
    }
    assert f"{MCP_PACKAGE}.summary" in reached_base64, "T10: el resumen vive en summary.py"
    assert f"{MCP_PACKAGE}.writer" in reached_base64, "T10: la escritura es la compartida"
    assert f"{MCP_PACKAGE}.convert" not in reached_base64, (
        "convert_base64 (T10) va por costura: tools/ NUNCA importa convert.py"
    )
    assert "markitdown" not in {target.split(".")[0] for target in reached_base64}, (
        "convert_base64 (T10) va por costura: tools/ NUNCA importa markitdown"
    )

    reached_formats = {
        target for _chain, target in _walk_imports(f"{MCP_PACKAGE}.tools.list_formats")
    }
    assert f"{MCP_PACKAGE}.formats" in reached_formats, (
        "list_formats (T11) lee el catálogo de formats.py: dato puro"
    )
    assert "markitdown" not in {target.split(".")[0] for target in reached_formats}, (
        "list_formats (T11) publica DATO: nunca importa el conversor"
    )


def test_mcp_composition_root_is_allowed_to_reach_lancedb() -> None:
    """Dirección OPUESTA T2/T6: `server.py` SÍ alcanza `lancedb` y `cocoindex` (root exento).

    Mismo papel que `test_lancedb_adapter_is_allowed_to_reach_lancedb` en Phase 1:
    prueba el otro lado de la frontera del server — si el walker no viera el
    import del composition root, los tests negativos sobre `errors`/`budget`/
    `paths`/`tools` darían falsos positivos. La frontera exacta es
    `tools/`+dominio (sin motor) ← `server.py` (con motor y SDK). T5 añade el
    otro lado de la costura: el composition root SÍ alcanza `markitdown` (vía
    `convert.py`, importado dentro de `_convert_seam`) — si no lo alcanzara,
    el wiring de `add_source` estaría roto. T6 añade `cocoindex`: la op del
    embedder (`SentenceTransformerEmbedder`/`LiteLLMEmbedder`) se construye
    SOLO aquí y se inyecta a `embedder.build_read_cut` (D59).
    """
    reached = {target for _chain, target in _walk_imports(MCP_COMPOSITION_ROOT)}
    assert "lancedb" in reached, "el composition root construye el lector: importa lancedb"
    assert "cocoindex" in reached, "el composition root construye la op del embedder (T6/D59)"
    assert f"{MCP_PACKAGE}.tools.search" in reached, "registra el handler de search: lo importa"
    assert f"{PACKAGE}.config" in reached, "carga la config del vault: lo importa"
    assert f"{MCP_PACKAGE}.convert" in reached, "cablea la costura de add_source: importa convert"
    assert "markitdown" in reached, "convert.py importa markitdown: el root exento sí lo alcanza"


def test_embedder_module_stays_inside_its_allowlist() -> None:
    """T6/D59: el módulo `embedder` no toca engines ni providers; su oficio es la estrategia.

    Desde T6 las ops (`SentenceTransformerEmbedder`/`LiteLLMEmbedder`) se
    construyen en el composition root y se inyectan como factories: `embedder`
    se queda con `mode`/`is_available`/`build_read_cut` y el dialecto `E_*`.
    Los engines siguen proscritos aquí; `litellm`/`sentence_transformers`
    siguen permitidos por si una versión futura vuelve a construir la op, pero
    hoy no se importan (el test no exige alcanzarlos).
    """
    for chain, target in _walk_imports(MCP_PROVIDER_MODULE):
        root = target.split(".")[0]
        assert root not in BANNED_PROVIDER_ROOTS, (
            f"la fábrica {MCP_PROVIDER_MODULE} alcanza un engine: {_describe(chain, target)}"
        )
        assert root in PERMITTED_PROVIDER_ROOTS, (
            f"la fábrica {MCP_PROVIDER_MODULE} importa algo fuera de su allowlist: "
            f"{_describe(chain, target)}"
        )


def test_handlers_record_the_provider_boundary_without_crossing_it() -> None:
    """Sanidad T6 de la frontera: `tools.search` LLEGA a `embedder` y NO a `litellm`.

    Si la arista dejara de resolverse, el banned test de `tools.*` pasaría sin
    mirar la fábrica; si el walker traspasara la frontera, cada handler
    «alcanzaría» `litellm` y la regla T2 original se volvería inaplicable a T6.
    """
    reached = {target for _chain, target in _walk_imports(f"{MCP_PACKAGE}.tools.search")}
    assert f"{MCP_PACKAGE}.embedder" in reached, "la arista a la fábrica SÍ se registra"
    assert "litellm" not in reached, "la frontera NO se traspasa desde los handlers"
