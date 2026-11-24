"""Guardrail de `obsidian-workspace/opencode.json` contra el esquema oficial V2.

Alcance autorizado: únicamente (b) forma del `opencode.json` del payload —
nada de contenido (agentes, permisos, hashes).

Fuente: https://opencode.ai/config.json descargado el 2026-11-09 y vendorizado
byte a byte en `tests/fixtures/opencode-config.schema.json` (draft 2020-12,
`$id` = esa URL, `additionalProperties: false` en raíz). Validarlo contra el
esquema cubre de paso: claves top-level desconocidas, patrón de `model`
(`provider/model`), forma de `agents.*` (`Config.AgentEncoded`),
`mcp.servers.*` (`Mcp.LocalConfigEncoded` con `disabled` boolean),
`references` (Git/Local) y `plugins` (array).

Además, el fichero debe declarar `"$schema": "https://opencode.ai/config.json"`
— la URL `$id` que el propio esquema oficial declara (fixture `$id`).

Los tests sobre datos reales nacen verdes (el payload ya cumple): es la
naturaleza de un guardrail. El portero muerde en los controles negativos, que
exigen `jsonschema.ValidationError` sobre el payload mutado.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PAYLOAD_JSON = REPO_ROOT / "obsidian-workspace" / "opencode.json"
SCHEMA_PATH = REPO_ROOT / "tests" / "fixtures" / "opencode-config.schema.json"

SCHEMA: dict[str, Any] = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
OFFICIAL_SCHEMA_URL = "https://opencode.ai/config.json"


def _payload() -> dict[str, Any]:
    """Carga el `opencode.json` real del payload (mutaciones parten de él)."""
    return json.loads(PAYLOAD_JSON.read_text(encoding="utf-8"))


def test_payload_opencode_json_validates_against_the_official_schema() -> None:
    """El `opencode.json` del payload valida contra el esquema oficial completo."""
    jsonschema.validate(_payload(), SCHEMA)


def test_payload_opencode_json_declares_the_official_schema_url() -> None:
    """`$schema` declara la URL `$id` del esquema oficial (config docs)."""
    assert _payload().get("$schema") == OFFICIAL_SCHEMA_URL


def test_schema_rejects_an_unknown_top_level_key() -> None:
    """`additionalProperties: false` en raíz ⇒ una clave mal escrita (`formaatter`) falla."""
    mutated = copy.deepcopy(_payload())
    mutated["formaatter"] = {"args": []}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(mutated, SCHEMA)


def test_schema_rejects_a_model_without_provider_slash() -> None:
    """`model` exige `provider/model` (patrón `^[^/#]+/[^#]+(?:#[^#]+)?$`)."""
    mutated = copy.deepcopy(_payload())
    mutated["model"] = "sin-slash"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(mutated, SCHEMA)


def test_schema_rejects_a_non_boolean_mcp_disabled_flag() -> None:
    """`mcp.servers.*.disabled` es booleano (Mcp.LocalConfigEncoded): un string falla."""
    instance = {"mcp": {"servers": {"svc": {"type": "local", "command": ["x"], "disabled": "yes"}}}}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, SCHEMA)
