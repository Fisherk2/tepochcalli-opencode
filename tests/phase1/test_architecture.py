"""Test de arquitectura: el dominio del flow nunca depende de infraestructura (CP-B, T9).

Enuncia executablemente la regla hexagonal de ADR-005 («la dependencia apunta
hacia dentro»): `tepochcalli_flow.citation`, `tepochcalli_flow.config` y
`tepochcalli_flow.ports` son código de dominio puro y su cierre transitivo de
imports **nunca** puede alcanzar
la infraestructura del motor de indexación (`cocoindex`) ni del indexador
vectorial (`lancedb`). El propio `tepochcalli_flow/__init__.py` también está bajo
la regla —importar el paquete lo ejecuta—; el resto del paquete (`models`,
`app`, `source`, `parsers`, `verify` y `adapters/`) ES infraestructura y sí puede importar el engine —
este test no lo toca. T9 añade `ports` al conjunto protegido (el puerto de
lectura que Phase 2 consume) y, en la dirección opuesta, afirma que el
adaptador `adapters/lancedb_reader` SÍ alcanza `lancedb`: la frontera corre
exactamente entre `ports.py` y `adapters/`, ni un módulo más allá.

Garantías que ofrece, y cómo:

* **Negativa (banned roots).** Un recorrido BFS sobre los imports resueltos con
  `ast` (sin ejecutar ni importar los módulos analizados) sigue solo las aristas
  «in-project» (`tepochcalli_flow.*`, incluidas relativas `from .x import ...`)
  y falla naming la cadena exacta del alias, p. ej.
  `tepochcalli_flow.citation -> tepochcalli_flow.models -> cocoindex`.
  Un grep directo sobre un solo archivo NO detectaría esa cadena: la violación
  es transitive por diseño. `BANNED_INFRA_ROOTS` es una constante de módulo
  extensible (T9 podrá añadir, p. ej., `litellm` sin reestructurar nada).
* **Positiva (allowlist de dominio).** El mismo cierre transitivo de los
  módulos de dominio debe importar ÚNICAMENTE stdlib
  (`sys.stdlib_module_names`) + módulos in-project (`tepochcalli_flow.*`).
  Decisión de allowlist documentada aquí: stdlib + in-project y nada más — así
  un contribuidor futuro no puede colar numpy (ni ningún tercero) en el dominio
  ni siquiera vía un helper in-project.
* **Sanidad del propio walker.** Comprueba que el recorrido sí resuelve aristas
  in-project reales (citation -> config), para que un fallo de resolución de
  paths no convierta los otros dos tests en vacíamente verdes.
* **Límite declarado, no adversarial.** El walker solo ve `ast.Import` y
  `ast.ImportFrom`: los imports dinámicos (`importlib.import_module("cocoindex")`,
  `__import__(...)`) quedan FUERA del recorrido — este test no los detectaría.

Fuentes de verdad: ADR-005 (hexagonal), ADR-002 (sin demonios/red), los
docstrings de `citation.py` y `config.py` («código de dominio: NO importa
cocoindex ni lancedb») y tasks/todo.md → gate CP-B.
"""

from __future__ import annotations

import ast
import sys
from collections import deque
from pathlib import Path
from typing import Final

import pytest
import tepochcalli_flow

# --- constantes de la regla ----------------------------------------------------

PACKAGE: Final = "tepochcalli_flow"
"""Raíz del paquete in-project cuyo cierre transitivo se analiza."""

_PACKAGE_DIR: Final = Path(tepochcalli_flow.__file__).resolve().parent
"""Directorio del paquete instalado (resuelto, no hardcodeado)."""

BANNED_INFRA_ROOTS: Final[frozenset[str]] = frozenset({"cocoindex", "lancedb"})
"""Raíces de import prohibidas para el dominio (ADR-005). Extensible por T9."""

STDLIB_ROOTS: Final[frozenset[str]] = frozenset(sys.stdlib_module_names)
"""Raíces permitidas por ser stdlib de CPython 3.12 (incluye `tomllib`, `__future__`)."""

PERMITTED_DOMAIN_ROOTS: Final[frozenset[str]] = STDLIB_ROOTS | {PACKAGE}
"""Allowlist del dominio: stdlib + in-project, y nada más (docstring del módulo)."""

DOMAIN_MODULES: Final[tuple[str, ...]] = (
    PACKAGE,
    f"{PACKAGE}.citation",
    f"{PACKAGE}.config",
    f"{PACKAGE}.ports",
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


# --- motor AST (sin importar los módulos analizados) ---------------------------


def _module_source(dotted: str) -> Path | None:
    """Resuelve un nombre punteado in-project a su archivo fuente, o None.

    `tepochcalli_flow.citation` -> `<pkg>/citation.py`; el propio paquete ->
    `<pkg>/__init__.py`; cualquier otro root (tercero, stdlib) -> None: el
    recorrido nunca intenta recursar dentro de paquetes ajenos.
    """
    if dotted != PACKAGE and not dotted.startswith(f"{PACKAGE}."):
        return None
    base = _PACKAGE_DIR.joinpath(*dotted.split(".")[1:])
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
            targets.update(
                f"{base}.{alias.name}" if base else alias.name for alias in node.names
            )
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
            if target.split(".")[0] == PACKAGE:
                child = _module_source(target)
                if child is not None:
                    queue.append([*chain, target])
            results.append((chain, target))
    return results


def _describe(chain: list[str], target: str) -> str:
    """Cadena de dependencia legible para el mensaje de fallo."""
    return " -> ".join([*chain, target])


# --- tests ---------------------------------------------------------------------


@pytest.mark.parametrize("module", DOMAIN_MODULES)
def test_domain_modules_never_reach_banned_infrastructure(module: str) -> None:
    """Ningún import alcanzable desde un módulo de dominio tiene raíz prohibida.

    Transitive por construcción: si `citation` importara un helper in-project
    que importa `cocoindex`, el BFS lo alcanzaría y reportaría la cadena entera.
    """
    for chain, target in _walk_imports(module):
        root = target.split(".")[0]
        assert root not in BANNED_INFRA_ROOTS, (
            f"El módulo de dominio {module} alcanza infraestructura prohibida: "
            f"{_describe(chain, target)} (raíces prohibidas: "
            f"{', '.join(sorted(BANNED_INFRA_ROOTS))})"
        )


@pytest.mark.parametrize("module", DOMAIN_MODULES)
def test_domain_transitive_imports_stay_stdlib_and_in_project(module: str) -> None:
    """El cierre transitivo del dominio solo importa stdlib + `tepochcalli_flow.*`.

    Allowlist cerrada (decisión documentada en el docstring del módulo): además
    de las raíces prohibidas explícitas, ningún tercero — p. ej. numpy — puede
    entrar al dominio ni siquiera a través de un módulo in-project.
    """
    for chain, target in _walk_imports(module):
        root = target.split(".")[0]
        assert root in PERMITTED_DOMAIN_ROOTS, (
            f"El módulo de dominio {module} importa un tercero no permitido: "
            f"{_describe(chain, target)} (allowlist: stdlib + {PACKAGE})"
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
    reached = {
        target for _chain, target in _walk_imports(f"{PACKAGE}.adapters.lancedb_reader")
    }
    assert "lancedb" in reached, (
        "el adaptador LanceDB debe importar lancedb: ES infraestructura (ADR-005)"
    )
    assert f"{PACKAGE}.ports" in reached, (
        "el adaptador implementa el puerto: lo importa"
    )
