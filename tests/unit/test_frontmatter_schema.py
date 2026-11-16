"""Guardrails de sintaxis/esquema de los frontmatters del payload (solo forma).

Alcance autorizado: únicamente (a) sintaxis/esquema de los frontmatters de
agentes, comandos y skills contra la documentación oficial de OpenCode V2.
Nada de contenido (cuerpos, presupuestos, hash, idioma, citas).

Reglas y fuentes (consultadas el 2026-11-09):

* Agentes — https://opencode.ai/docs/agents/ : el frontmatter es un mapping
  validable como `Config.AgentEncoded` del esquema oficial
  https://opencode.ai/config.json (vendorizado en
  `tests/fixtures/opencode-config.schema.json`). Ese esquema es
  `additionalProperties: false`, así que rechaza de paso las claves V1
  deprecadas (`temperature`, `top_p`, `prompt`, `permission`, `tools`,
  `disable`, `maxSteps`) que la docs prohíbe en V2. `permissions` se valida
  además contra `Permission.Ruleset`: cada regla exige `action`, `resource` y
  `effect`, con `effect` en {allow, ask, deny} y sin claves extra.
* Comandos — https://opencode.ai/docs/commands/ : las claves del frontmatter
  son `Config.CommandEncoded` MENOS `template` ("Do not put template in
  Markdown frontmatter; the body supplies it"). `subtask` sigue siendo
  válido: alias deprecado que la docs acepta, no se rechaza.
* Skills — https://opencode.ai/docs/skills/ : frontmatter presente, `name` y
  `description` strings no vacíos (sin `description` la skill no se anuncia
  al modelo). Sin lista cerrada de claves extra: la docs admite campos de
  portabilidad (`license`, `compatibility`, `metadata`) y el payload real
  trae además `allowed-tools`, `author`, `origin`, `version` y `reference`.
* Invariante `name` == directorio (bug `920acdd`): el `name` de una SKILL.md
  debe igualar al nombre de su directorio padre — un rename desalineado dejó
  el frontmatter divergente y la comprobación fue manual. El guardrail sobre
  el payload real se acompaña de un caso sintético que demuestra que la
  aserción dispara.

Los tests sobre datos reales nacen verdes (los frontmatters ya cumplen): es
la naturaleza de un guardrail. El portero muerde en los controles negativos,
que exigen `jsonschema.ValidationError` sobre instancias mutadas.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PAYLOAD_DIR = REPO_ROOT / "obsidian-workspace" / ".opencode"
AGENTS_DIR = PAYLOAD_DIR / "agents"
COMMANDS_DIR = PAYLOAD_DIR / "commands"
SKILLS_DIR = PAYLOAD_DIR / "skills"
SCHEMA_PATH = REPO_ROOT / "tests" / "fixtures" / "opencode-config.schema.json"

SCHEMA: dict[str, Any] = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

# `$ref` raíz al `$defs` oficial: valida instancias como `Config.AgentEncoded`
# (additionalProperties: false ⇒ las claves V1 deprecadas quedan rechazadas).
AGENT_SCHEMA: dict[str, Any] = {"$ref": "#/$defs/Config.AgentEncoded", "$defs": SCHEMA["$defs"]}

# Derivado de `Config.CommandEncoded`: sin `template` (el cuerpo del .md lo
# aporta) y sin su `required` (solo exigía `template`).
COMMAND_SCHEMA: dict[str, Any] = copy.deepcopy(SCHEMA["$defs"]["Config.CommandEncoded"])
COMMAND_SCHEMA["properties"].pop("template", None)
COMMAND_SCHEMA.pop("required", None)

# Regla mínima de la docs de skills: `name` y `description` no vacíos. Sin
# `additionalProperties: false` a propósito: la docs admite campos extra.
SKILL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["name", "description"],
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "description": {"type": "string", "minLength": 1},
    },
}


def _frontmatter(path: Path) -> dict[str, Any]:
    """Extrae el primer bloque YAML de un `.md` y exige que sea un mapping.

    Patrón del repo (ver `test_payload_permissions.py`): sin frontmatter o
    con un frontmatter que no es mapa ⇒ `AssertionError` con la ruta.
    """
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---"), f"{path}: sin frontmatter YAML"
    data = yaml.safe_load(text.split("---", 2)[1])
    assert isinstance(data, dict), f"{path}: el frontmatter no es un mapping"
    return data


def _validation_errors(paths: list[Path], schema: dict[str, Any]) -> list[str]:
    """Valida el frontmatter de cada ruta contra `schema` y junta los errores.

    Acumula TODOS los fallos (no solo el primero) para que un guardrail rojo
    diga de un vistazo qué ficheros incumplen y por qué.
    """
    errors: list[str] = []
    for path in paths:
        try:
            jsonschema.validate(_frontmatter(path), schema)
        except jsonschema.ValidationError as exc:
            errors.append(f"{path.relative_to(REPO_ROOT)}: {exc.message}")
    return errors


def test_agent_frontmatters_are_valid_against_the_official_agent_schema() -> None:
    """Todo frontmatter de agente valida como `Config.AgentEncoded` (docs de agents)."""
    # shortcut: glob plano — el payload es plano; si algún día se anidan rutas
    # (`.opencode/agents/team/x.md`), pasar a `rglob("*.md")`.
    paths = sorted(AGENTS_DIR.glob("*.md"))
    assert paths, "el payload sin agentes dejaría este guardrail vacío"
    errors = _validation_errors(paths, AGENT_SCHEMA)
    assert not errors, "frontmatters de agente inválidos:\n" + "\n".join(errors)


def test_command_frontmatters_are_valid_against_the_official_command_schema() -> None:
    """Todo frontmatter de comando valida como `CommandEncoded` sin `template` (docs)."""
    paths = sorted(COMMANDS_DIR.glob("*.md"))
    assert paths, "el payload sin comandos dejaría este guardrail vacío"
    errors = _validation_errors(paths, COMMAND_SCHEMA)
    assert not errors, "frontmatters de comando inválidos:\n" + "\n".join(errors)


def test_skill_frontmatters_declare_a_non_empty_name_and_description() -> None:
    """Toda SKILL.md trae `name` y `description` no vacíos (regla mínima de skills)."""
    # shortcut: un solo nivel — la docs de skills dice que un directorio con
    # SKILL.md no se busca dentro; si se añaden directorios de agrupación
    # (`skills/teams/x/SKILL.md`), ampliar el patrón.
    paths = sorted(SKILLS_DIR.glob("*/SKILL.md"))
    assert paths, "el payload sin skills dejaría este guardrail vacío"
    errors = _validation_errors(paths, SKILL_SCHEMA)
    assert not errors, "frontmatters de skill inválidos:\n" + "\n".join(errors)


def _assert_skill_names_match_directories(skills_dir: Path) -> None:
    """Exige que el `name` de cada SKILL.md iguale al nombre de su directorio padre.

    Invariante post-`920acdd`: un skill renombró su carpeta y el frontmatter
    quedó divergente; la verificación fue manual. Acumula TODOS los desajustes
    (mismo patrón que `_validation_errors`) para que un guardrail rojo liste de
    un vistazo qué skills incumplen, con qué valores y en qué ruta.
    """
    # shortcut: un solo nivel — misma razón que el glob del schema de skills.
    paths = sorted(skills_dir.glob("*/SKILL.md"))
    assert paths, f"{skills_dir}: sin skills dejaría este guardrail vacío"
    errors: list[str] = []
    for path in paths:
        directory = path.parent.name
        declared = _frontmatter(path).get("name")
        if declared != directory:
            errors.append(f"{path}: name={declared!r} != directorio={directory!r}")
    assert not errors, "skills con `name` divergente del directorio:\n" + "\n".join(errors)


def test_skill_frontmatter_name_equals_the_parent_directory_name() -> None:
    """Cada SKILL.md real declara `name` == nombre de su directorio (920acdd).

    Guardrail nacido verde (hoy el invariante se cumple): su valor es cortar
    renames a medias como el de `920acdd` antes de que lleguen al payload.
    """
    _assert_skill_names_match_directories(SKILLS_DIR)


def test_skill_name_guardrail_fires_when_name_diverges_from_directory(tmp_path: Path) -> None:
    """Sensibilidad: un `name` distinto del directorio SÍ dispara la aserción.

    Sin este control, el guardrail sobre el payload real pasaría a la primera
    sin probar que la aserción muerde — el caso sintético es la prueba.
    """
    skill_dir = tmp_path / "skill-renombrada"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: skill-original\ndescription: sintética\n---\n\nCuerpo.\n",
        encoding="utf-8",
    )

    with pytest.raises(AssertionError) as excinfo:
        _assert_skill_names_match_directories(tmp_path)
    message = str(excinfo.value)
    assert all(
        fragment in message for fragment in (str(skill_dir), "skill-original", "skill-renombrada")
    ), f"el mensaje debe citar la ruta y ambos valores: {message}"


# --- Controles negativos: la validación DEBE fallar sobre instancias mutadas. ---


def test_agent_schema_rejects_the_deprecated_v1_temperature_key() -> None:
    """`temperature` es clave V1 deprecada que la docs de V2 prohíbe ⇒ rechazada."""
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"description": "x", "temperature": 0.5}, AGENT_SCHEMA)


def test_agent_schema_rejects_an_unknown_mode() -> None:
    """`mode` solo admite primary|subagent|all (enum del esquema oficial)."""
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"mode": "banana"}, AGENT_SCHEMA)


def test_agent_schema_rejects_a_color_that_is_not_a_hex_triplet() -> None:
    """`color` exige `^#[0-9a-fA-F]{6}$` (patrón del esquema oficial)."""
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"color": "red"}, AGENT_SCHEMA)


def test_agent_schema_rejects_zero_steps() -> None:
    """`steps` es entero > 0 (exclusiveMinimum 0 del esquema oficial)."""
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"steps": 0}, AGENT_SCHEMA)


def test_agent_schema_rejects_a_permission_rule_without_effect() -> None:
    """Cada regla de `permissions` exige `action`+`resource`+`effect` (Ruleset)."""
    instance = {"permissions": [{"action": "edit", "resource": "*"}]}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, AGENT_SCHEMA)


def test_command_schema_rejects_template_in_frontmatter() -> None:
    """La docs de commands prohíbe `template` en el frontmatter: el cuerpo lo aporta."""
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"description": "x", "template": "hola"}, COMMAND_SCHEMA)


def test_command_schema_accepts_the_deprecated_subtask_alias() -> None:
    """`subtask` es alias deprecado VÁLIDO (docs): aceptarlo, no rechazarlo."""
    jsonschema.validate({"description": "x", "subtask": True}, COMMAND_SCHEMA)


def test_skill_schema_rejects_a_missing_description() -> None:
    """Sin `description` la skill no se anuncia al modelo (docs de skills)."""
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"name": "x"}, SKILL_SCHEMA)


def test_skill_schema_rejects_an_empty_description() -> None:
    """`description: ""` no cumple el mínimo de string no vacío."""
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"name": "x", "description": ""}, SKILL_SCHEMA)


def test_skill_schema_accepts_extra_portability_fields() -> None:
    """La docs admite `license`/`compatibility`/`metadata` y campos del payload."""
    instance = {
        "name": "x",
        "description": "y",
        "license": "MIT",
        "compatibility": "opencode",
        "metadata": {"k": "v"},
        "allowed-tools": ["Read"],
        "version": "1.0.0",
    }
    jsonschema.validate(instance, SKILL_SCHEMA)
