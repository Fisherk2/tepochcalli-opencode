"""Parser del verificador TD-34 (`tests/e2e/verify_payload_refs.py`).

El verificador no lo recolecta pytest (su nombre no empieza por `test_`); este
test solo cubre la extracción, que es la parte que puede equivocarse en
silencio: un falso negativo deja pasar un huérfano al QA de T15.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "e2e" / "verify_payload_refs.py"
_spec = importlib.util.spec_from_file_location("verify_payload_refs", SCRIPT)
assert _spec and _spec.loader
vpr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vpr)


def test_chain_inherits_skill_kind() -> None:
    """`a` + `b` skills tipa las dos, no solo la que lleva la palabra detrás."""
    refs = vpr.typed_refs("Write tasks. **Load** `obsidian-markdown` + `obsidian-vault` skills.")
    assert sorted(refs) == [
        (1, "skill", "obsidian-markdown"),
        (1, "skill", "obsidian-vault"),
    ]


def test_tool_and_mcp_names_are_not_references() -> None:
    """Solo cuenta lo tipado: `tepochcalli-rag` MCP y `search` tool no son skills."""
    line = "**Load** `tepochcalli-mcp` skill and use `tepochcalli-rag` MCP; `search` tool."
    cited = [name for _, kind, name in vpr.typed_refs(line) if kind == "skill"]
    assert cited == ["tepochcalli-mcp"]


def test_delegate_and_frontmatter_and_permission_pair() -> None:
    """Cubre `agent:`, el par permiso `resource:` y la delegación explícita."""
    text = (
        "---\n"
        "agent: chilam\n"
        "permissions:\n"
        "  - action: subagent\n"
        '    resource: "research-analyst"\n'
        "---\n"
        "**Delegate** `knowledge-synthesizer` subagent.\n"
    )
    assert sorted(vpr.typed_refs(text)) == [
        (2, "agent", "chilam"),
        (5, "agent", "research-analyst"),
        (7, "subagent", "knowledge-synthesizer"),
    ]


def test_fenced_blocks_are_ignored() -> None:
    """Un nombre dentro de un fenced block es ejemplo, no carga."""
    text = "```bash\n# **Load** `not-a-skill` skill\n```\n**Load** `pdf` skill.\n"
    assert vpr.typed_refs(text) == [(4, "skill", "pdf")]
