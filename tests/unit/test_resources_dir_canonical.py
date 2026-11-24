"""Guarda de caso: el nombre canónico de la entrada del usuario es `00-resources/`.

D9.1 en minúsculas (enmienda 2026-11-13 de `spec-vault-structure.md`; TD-8 es el
precedente con `01-Tasks/` → `01-tasks/`). Una divergencia de caso entre capas es
**invisible en macOS/Windows y silenciosa en Linux**: el wizard crea una carpeta,
el índice apunta a otra y nada falla — lo que el usuario escribe donde el
instalador le dice simplemente no se indexa.

Los tres literales que deben coincidir (y que este gate compara contra el del
flow, que es el que el MCP importa):

* `tepochcalli_flow.citation.RESOURCES_DIR` — raíz por omisión + destino de `add_source`;
* `INDEXER_DIR` de `obsidian-workspace/opencode.json` — el conjunto que indexa el payload;
* `pub const RESOURCES_DIR` de `crates/tepochcalli/src/application/installer.rs` —
  la carpeta que materializa el wizard (se lee como texto: pytest no compila Rust).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from tepochcalli_flow import citation

REPO_ROOT = Path(__file__).resolve().parents[2]
VAULT_JSON = REPO_ROOT / "obsidian-workspace" / "opencode.json"
INSTALLER_RS = REPO_ROOT / "crates" / "tepochcalli" / "src" / "application" / "installer.rs"

EXPECTED = "00-resources"
"""El literal único. Un cambio aquí es una decisión del dueño, no un refactor."""

INSTALLER_CONST = re.compile(r'pub const RESOURCES_DIR: &str = "([^"]+)";')


def test_flow_resources_dir_is_lowercase() -> None:
    """El default del flow (que el MCP hereda) es el literal en minúsculas."""
    assert citation.RESOURCES_DIR == EXPECTED


def test_payload_indexer_dir_includes_the_canonical_folder() -> None:
    """El `INDEXER_DIR` del payload declara exactamente la carpeta que el flow indexa."""
    config = json.loads(VAULT_JSON.read_text(encoding="utf-8"))
    roots = config["mcp"]["servers"]["tepochcalli-rag"]["environment"]["INDEXER_DIR"]
    assert [root.strip() for root in roots.split(",")] == [EXPECTED]


def test_installer_constant_matches_the_flow_literal() -> None:
    """El wizard crea la misma carpeta que indexa el flow (el bug que este gate evita)."""
    source = INSTALLER_RS.read_text(encoding="utf-8")
    match = INSTALLER_CONST.search(source)
    assert match, f"no hay `pub const RESOURCES_DIR` en {INSTALLER_RS}"
    assert match.group(1) == citation.RESOURCES_DIR
