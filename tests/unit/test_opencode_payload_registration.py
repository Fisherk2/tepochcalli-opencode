"""Contrato del `opencode.json` del payload y merge conservador de F8 (T9).

Cierra **TD-30**: el test anterior comparaba el payload consigo mismo. Ahora el
merge se demuestra sobre una entrada **fabricada**
(`tests/fixtures/opencode_payload_synthetic.json`) que ningún paso del producto
genera, y el payload real se audita contra el contrato de D-P5-4:

* el array global `permissions` (313 reglas, last-match-wins) **sí** existe y se
  concatena antes del bloque inline de cada agente (ADR-012; ver
  `spec-payload-permissions` §Enmienda 2026-11-12);
* `instructions` son rutas **relativas al vault** y cada una existe dentro de
  `obsidian-workspace/` (D-P5-4);
* los 5 agentes primarios siguen ahí sin arrays de permisos, y `mcp.servers` /
  `references` quedan como estaban (el merge es del wizard, no del payload).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
VAULT_ROOT = REPO_ROOT / "obsidian-workspace"
PAYLOAD_JSON = VAULT_ROOT / "opencode.json"
SYNTHETIC_JSON = (
    Path(__file__).resolve().parents[1] / "fixtures" / "opencode_payload_synthetic.json"
)

PRIMARY_AGENTS = ("itzamna", "nezahualcoyotl", "pochteca", "chilam", "tlacuilo")
INSTRUCTIONS = (
    ".opencode/skills/obsidian-markdown/SKILL.md",
    ".opencode/skills/obsidian-cli/SKILL.md",
    ".opencode/skills/obsidian-vault/SKILL.md",
    ".opencode/skills/markdown-mermaid-writing/SKILL.md",
)

# Forma EXACTA que F8 escribe (spec-installer-wizard §Merge). D17: `python -m`,
# nunca el console script `venv/bin/tepochcalli-mcp` (el bit exec se pierde en
# NTFS/fuseblk). El `environment` conserva las claves del usuario (D32) y solo
# impone `TEPOCHCALLI_ROOT`.
# Única fuente de verdad del comando del server (Rule of Three: 3 usos abajo).
RAG_COMMAND = [".tepochcalli/venv/bin/python", "-m", "tepochcalli_mcp"]

RAG_ENTRY: dict[str, Any] = {
    "type": "local",
    "command": RAG_COMMAND,
    "cwd": ".",
    "environment": {
        "INDEXER_DIR": "fake-notes",
        "TEPOCHCALLI_TOP_K": "7",
        "TEPOCHCALLI_ROOT": ".",
    },
    "disabled": False,
}


def _f8_merge(doc: dict[str, Any]) -> None:
    """Espejo del merge de F8 (`phase8.rs::merge_servers`) en Python.

    Quita la entrada obsoleta `markitdown` (D29: conversión en proceso) y
    reescribe SOLO `tepochcalli-rag`: el `environment` previo del usuario se
    conserva en su orden y `TEPOCHCALLI_ROOT` se impone a `"."`.
    """
    servers = doc.setdefault("mcp", {}).setdefault("servers", {})
    servers.pop("markitdown", None)
    environment = dict(servers.get("tepochcalli-rag", {}).get("environment", {}))
    environment["TEPOCHCALLI_ROOT"] = "."
    servers["tepochcalli-rag"] = {
        "type": "local",
        "command": RAG_COMMAND,
        "cwd": ".",
        "environment": environment,
        "disabled": False,
    }


def test_merge_on_synthetic_input_leaves_the_rest_untouched() -> None:
    """F8 sobre una entrada fabricada: resto byte-idéntico + entrada contractual."""
    original = json.loads(SYNTHETIC_JSON.read_text(encoding="utf-8"))
    merged = json.loads(SYNTHETIC_JSON.read_text(encoding="utf-8"))

    _f8_merge(merged)
    entry = merged["mcp"]["servers"]["tepochcalli-rag"]

    # (a) Mismo serializador a ambos lados ⇒ estructura Y orden de claves. Un
    # diff aquí significa que el merge tocó algo que no gestiona.
    for key in ("markitdown", "tepochcalli-rag"):
        original["mcp"]["servers"].pop(key)
    merged["mcp"]["servers"].pop("tepochcalli-rag")

    assert json.dumps(merged, indent=2, ensure_ascii=False) == json.dumps(
        original, indent=2, ensure_ascii=False
    ), "el merge conservador exige que el resto del documento quede byte-idéntico"

    # (b) Forma exacta del contrato, incluidas las claves de usuario del env.
    assert entry == RAG_ENTRY

    # (c) D29: sin server standalone de markitdown.
    assert "markitdown" not in merged["mcp"]["servers"]


def test_payload_is_clean_and_contractual() -> None:
    """El payload real cumple el contrato: global 313, instructions resolubles."""
    doc = json.loads(PAYLOAD_JSON.read_text(encoding="utf-8"))

    assert len(doc["permissions"]) == 313, (
        "el bloque global de 313 reglas es la política de secretos"
    )
    assert doc["default_agent"] == "itzamna"
    assert tuple(doc["instructions"]) == INSTRUCTIONS
    for relative in INSTRUCTIONS:
        assert (VAULT_ROOT / relative).is_file(), f"instrucción irresoluble: {relative}"

    agents = doc["agents"]
    for name in PRIMARY_AGENTS:
        assert name in agents, f"falta el agente primario {name}"
        assert "permissions" not in agents[name], f"{name} debe llevar su política en el .md"

    servers = doc["mcp"]["servers"]
    assert servers["excel"]["disabled"] is True
    assert servers["jupyter"]["disabled"] is True
    assert "anydoc" in servers
    assert servers["tepochcalli-rag"] == {
        "type": "local",
        "command": RAG_COMMAND,
        "cwd": ".",
        "environment": {
            # Payload v1 usa el scaffold en minúsculas; la spec-vault-structure
            # (§Nota de convención) tiene abierta la acción de alinearlo.
            "INDEXER_DIR": "00-resources",
            "TEPOCHCALLI_ROOT": ".",
            "TEPOCHCALLI_TOP_K": "5",
        },
        "disabled": False,
    }
    assert "markitdown" not in servers
    assert doc["references"], "references se conserva sin cambios"
