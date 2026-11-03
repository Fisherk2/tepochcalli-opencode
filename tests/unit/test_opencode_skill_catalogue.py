"""La skill `tepochcalli-mcp` sigue siendo VERDADERA sobre el server real (T15).

La skill del payload (`obsidian-workspace/.opencode/skills/tepochcalli-mcp/
SKILL.md`) es la tabla de decisiones del agente: si una tool se renombra, se
retira o cambia su firma, la skill miente y NADA del código falla (los AC de
T15 se verificaron a mano). Este test la gradúa contra la fuente real:

* el frontmatter YAML parsea: `name` identifica la skill y `description`
  (el gatillo de invocación) no está vacía;
* el catálogo `## Tools` menciona EXACTAMENTE las tools que el server
  registra, con los mismos argumentos;
* el contrato rev. 2 de `index_refresh()` (SIN argumentos, ADR-010) no
  admite que la skill presente `directories` como parámetro válido.

**Fuente de las tools reales, y por qué:** `server.list_tools()` en proceso —
el MISMO camino que el handler de wire `_handle_list_tools` de mcp 2.3.0, así
que el nombre y el `input_schema` son los que vería el harness. Se descarta
lanzar el subproceso de `tests/e2e/test_mcp_contract.py` (vault + stdio solo
para leer el registro) y parsear el fuente de `server.py` (un `add_tool(...)`
dinámico o un `name=` en el decorador quedaría fuera del regex/AST). Aquí el
registro real se importa igual que ya hacen `test_mcp_server_backend` y
`test_mcp_vault_root_env`.

Payload CONGELADO hasta Phase 5: este test SOLO lee.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import yaml
from tepochcalli_mcp.server import server as rag_server

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_MD = (
    REPO_ROOT / "obsidian-workspace" / ".opencode" / "skills" / "tepochcalli-mcp" / "SKILL.md"
)

CATALOGUE_ROW = re.compile(r"^\|\s*`([a-z0-9_]+)\(([^)]*)\)`", re.MULTILINE)
"""Fila de la tabla `## Tools`: nombre de tool + firma entre paréntesis."""

RETIRED_MARKERS = re.compile(r"retired|no effect", re.IGNORECASE)
"""Marcadores que dejan constancia de que `directories` es un argumento retirado."""


def _frontmatter(text: str) -> dict[str, object]:
    """Primer bloque `--- … ---` del fichero, parseado como YAML."""
    assert text.startswith("---"), "SKILL.md sin frontmatter YAML"
    data = yaml.safe_load(text.split("---", 2)[1])
    assert isinstance(data, dict), "el frontmatter no es un mapa YAML"
    return data


def _catalogue(text: str) -> dict[str, list[str]]:
    """Tools de la sección `## Tools` → sus argumentos en orden de firma."""
    assert "## Tools" in text, "desapareció la sección de catálogo `## Tools`"
    section = text.split("## Tools", 1)[1].split("\n## ", 1)[0]
    rows = CATALOGUE_ROW.findall(section)
    assert rows, "la tabla del catálogo no listó ninguna tool"
    return {
        name: [arg.split("=")[0].strip() for arg in params.split(",") if arg.strip()]
        for name, params in rows
    }


def _declared_tools() -> dict[str, list[str]]:
    """Tools registradas en el server → propiedades de su `input_schema` (orden real)."""
    tools = asyncio.run(rag_server.list_tools())
    return {tool.name: list(tool.input_schema.get("properties", {})) for tool in tools}


def test_skill_frontmatter_declares_the_name_and_a_description() -> None:
    """Frontmatter presente: `name` identifica la skill y `description` no está vacía."""
    data = _frontmatter(SKILL_MD.read_text(encoding="utf-8"))

    assert data.get("name") == "tepochcalli-mcp"
    description = data.get("description")
    assert isinstance(description, str) and description.strip(), (
        "sin `description` la skill no tiene gatillo de invocación"
    )


def test_skill_catalogue_lists_exactly_the_tools_the_server_declares() -> None:
    """El catálogo == el registro real: ni una tool de más ni de menos."""
    catalogue = _catalogue(SKILL_MD.read_text(encoding="utf-8"))
    declared = _declared_tools()

    assert set(catalogue) == set(declared), (
        f"la skill miente sobre el conjunto de tools: catálogo={sorted(catalogue)} "
        f"registro real={sorted(declared)}"
    )


def test_skill_catalogue_signatures_match_the_real_input_schemas() -> None:
    """Cada firma del catálogo repite los argumentos y su ORDEN en el schema real."""
    catalogue = _catalogue(SKILL_MD.read_text(encoding="utf-8"))
    declared = _declared_tools()

    for name, args in catalogue.items():
        assert name in declared, f"el catálogo inventa la tool `{name}`"
        assert args == declared[name], (
            f"`{name}`: firma de la skill {args} != propiedades reales {declared[name]}"
        )


def test_skill_never_presents_the_retired_directories_argument_as_valid() -> None:
    """`index_refresh()` rev. 2 es SIN argumentos: `directories` solo como retirado."""
    text = SKILL_MD.read_text(encoding="utf-8")

    assert re.search(r"index_refresh\s*\(\s*directories", text) is None, (
        "la skill vuelve a invocar `index_refresh(directories=…)` (retirado, ADR-010 rev. 2)"
    )
    assert "directories=" not in text, (
        "la skill presenta `directories=` como valor de un argumento válido"
    )
    for lineno, line in enumerate(text.splitlines(), start=1):
        if "directories" in line:
            assert RETIRED_MARKERS.search(line), (
                f"línea {lineno}: `directories` sin marcar como retirado — "
                "rev. 2: `index_refresh()` no acepta argumentos"
            )
