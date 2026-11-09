"""Gate D9 estático del payload (T11): 40 skills congeladas y 15 artefactos.

Contrato ejecutable de `spec-payload-vault` §Testing Strategy y de D-P5-1 sobre
`obsidian-workspace/`:

* el inventario son EXACTAMENTE las 40 skills del congelado, con el hash de
  árbol de T0 y 687 ficheros — 0 modificadas, añadidas o eliminadas;
* ningún artefacto cita una skill que no exista ni una de las 8 retiradas;
* presupuestos de tamaño, higiene de frontmatter, idioma inglés y `opencode.json`
  resolviendo a `itzamna`.

Los artefactos son datos congelados: este test SOLO lee.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
VAULT_ROOT = REPO_ROOT / "obsidian-workspace"
SKILLS_ROOT = VAULT_ROOT / ".opencode" / "skills"
AGENTS_DIR = VAULT_ROOT / ".opencode" / "agents"
COMMANDS_DIR = VAULT_ROOT / ".opencode" / "commands"

PRIMARY_AGENTS = ("itzamna", "nezahualcoyotl", "pochteca", "chilam", "tlacuilo")

# Inventario definitivo congelado 2026-11-09 (D-P5-1), en el orden de `ls`.
SKILLS = (
    "article-writing",
    "brainstorming",
    "citation-management",
    "consciousness-council",
    "data-analysis",
    "data-plotting",
    "database-lookup",
    "doc-coauthoring",
    "experimental-design",
    "hypothesis-generation",
    "idea-refine",
    "image-prompt-generator",
    "interview-me",
    "literature-review",
    "literature-search-engine",
    "markdown-mermaid-writing",
    "obsidian-cli",
    "obsidian-markdown",
    "obsidian-vault",
    "osint-skills",
    "paper-2-web",
    "pdf",
    "peer-review",
    "planning-and-task-breakdown",
    "posters-generator",
    "research-grants",
    "research-search-protocol",
    "scholar-evaluation",
    "scientific-brainstorming",
    "scientific-critical-thinking",
    "scientific-problem-selection",
    "scientific-writing",
    "spreadsheet-analysis",
    "statistical-analysis",
    "statistical-power",
    "tepochcalli-mcp",
    "toon",
    "websearch-engine",
    "what-if-oracle",
    "writing-skills",
)

# Hash del árbol del baseline T0 (`find .opencode/skills -type f | sort | …`).
SKILLS_TREE_SHA256 = "169fe2c99fd58c71566342b076afd9098ae19dd13222ced96634963d617fc398"
SKILLS_FILES = 687

ALLOWED_TOKENS = frozenset(SKILLS) | {"tepochcalli-rag", "tepochcalli-mcp"}

# Skills del blueprint que el congelado eliminó (D-P5-2): no deben citarse.
RETIRED = (
    "xlsx-official",
    "excel-analysis",
    "scientific-slides",
    "pptx-official",
    "matplotlib",
    "scientific-visualization",
    "infographics",
    "markitdown",
)

ARTIFACTS = (
    *(AGENTS_DIR / f"{name}.md" for name in PRIMARY_AGENTS),
    *sorted(COMMANDS_DIR.glob("*.md")),
    VAULT_ROOT / "AGENTS.md",
)

KEBAB = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)+")
INLINE_CODE = re.compile(r"`([^`]+)`")
LEGACY_FIELDS = re.compile(r"temperature|top_p|prompt:|permission:|tools:|disable|maxSteps")
MODEL_FIELD = re.compile(r"^model\s*:", re.MULTILINE)
SPANISH_WORDS = re.compile(
    r"\b(el|la|los|las|para|con|por|una|del|que|cómo|según)\b", re.IGNORECASE
)
SPANISH_MARKERS = ("ñ", "¿", "¡")


def _frontmatter(path: Path) -> dict[str, object]:
    """Primer bloque `--- … ---` del fichero, parseado como YAML."""
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text.split("---", 2)[1])
    assert isinstance(data, dict), f"{path.name}: frontmatter no es un mapa YAML"
    return data


def _skill_dirs() -> tuple[str, ...]:
    """Nombres de los directorios de skill, ordenados."""
    return tuple(sorted(path.name for path in SKILLS_ROOT.iterdir() if path.is_dir()))


def _tree_digest() -> tuple[str, int]:
    """Hash del árbol replicando `find | sort` con `sha256` por fichero."""
    files = sorted(
        (path for path in SKILLS_ROOT.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(REPO_ROOT).as_posix(),
    )
    lines = []
    for path in files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(REPO_ROOT).as_posix()}\n")
    return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest(), len(files)


def _cited_tokens(text: str) -> set[str]:
    """Tokens kebab-case citados dentro de spans de código inline."""
    tokens: set[str] = set()
    for span in INLINE_CODE.findall(text):
        tokens.update(KEBAB.findall(span))
    return tokens


def _without_inline_code(text: str) -> str:
    """Quita los spans de código inline (tokens de enum y nombres propios exentos)."""
    return INLINE_CODE.sub("", text)


def test_skill_inventory_is_exactly_the_frozen_40() -> None:
    """Los directorios de skill son las 40 del congelado, nombre a nombre."""
    assert _skill_dirs() == SKILLS


def test_skill_tree_digest_matches_the_t0_baseline() -> None:
    """El árbol no cambió desde T0: mismo hash y mismos 687 ficheros (D-P5-1)."""
    digest, count = _tree_digest()
    assert count == SKILLS_FILES
    assert digest == SKILLS_TREE_SHA256


def test_no_orphan_skill_citations() -> None:
    """Todo token kebab-case en backticks es una skill real o una de las 2 tools MCP."""
    for artifact in ARTIFACTS:
        orphans = _cited_tokens(artifact.read_text(encoding="utf-8")) - ALLOWED_TOKENS
        assert not orphans, f"{artifact.name}: cita skills inexistentes {sorted(orphans)}"


def test_no_retired_skill_name_is_cited() -> None:
    """Ninguna de las 8 skills retiradas se cita dentro de código inline.

    La prosa puede nombrar la librería `markitdown` (es el conversor real,
    ADR-011); lo prohibido es presentar los 8 nombres como skills disponibles.
    """
    for artifact in ARTIFACTS:
        text = artifact.read_text(encoding="utf-8")
        cited = {
            name
            for span in INLINE_CODE.findall(text)
            for name in RETIRED
            if re.search(rf"\b{re.escape(name)}\b", span)
        }
        assert not cited, f"{artifact.name}: cita skills retiradas {sorted(cited)}"


def test_agent_bodies_stay_within_60_lines() -> None:
    """Cada system prompt (cuerpo tras el frontmatter) cabe en 60 líneas."""
    for name in PRIMARY_AGENTS:
        text = (AGENTS_DIR / f"{name}.md").read_text(encoding="utf-8")
        body = text.split("---", 2)[2].strip("\n")
        assert len(body.splitlines()) <= 60, f"{name}: cuerpo demasiado largo"


def test_command_bodies_stay_within_35_lines() -> None:
    """Cada comando completo cabe en 35 líneas."""
    for path in sorted(COMMANDS_DIR.glob("*.md")):
        assert len(path.read_text(encoding="utf-8").splitlines()) <= 35, path.name


def test_vault_agents_md_stays_within_120_lines() -> None:
    """El `AGENTS.md` del vault cabe en 120 líneas."""
    text = (VAULT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 120


def test_agent_frontmatter_has_only_the_contract_fields() -> None:
    """Los 5 agentes solo declaran `description`, `mode` y `permissions`, primary."""
    for name in PRIMARY_AGENTS:
        data = _frontmatter(AGENTS_DIR / f"{name}.md")
        assert set(data) == {"description", "mode", "permissions"}, name
        assert data["mode"] == "primary", name


def test_no_legacy_frontmatter_fields_anywhere() -> None:
    """Cero campos legacy V1 en los 15 artefactos."""
    for artifact in ARTIFACTS:
        text = artifact.read_text(encoding="utf-8")
        hits = LEGACY_FIELDS.findall(text)
        assert not hits, f"{artifact.name}: campos legacy {hits}"


def test_no_artifact_repeats_the_model() -> None:
    """Cero `model:` en los `.md`: el modelo vive solo en `opencode.json`."""
    for artifact in ARTIFACTS:
        assert MODEL_FIELD.search(artifact.read_text(encoding="utf-8")) is None, artifact.name


def test_commands_do_not_declare_subtask_or_subagent() -> None:
    """Los 9 comandos corren en la sesión: cero `subtask` y cero `subagent:`."""
    for path in sorted(COMMANDS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        assert "subtask" not in text, path.name
        assert "subagent:" not in text, path.name


def test_commands_have_no_shell_blocks_or_at_attachments() -> None:
    """Cero bloques `` !`cmd` `` y cero tokens `@<ruta>` en los 9 comandos."""
    for path in sorted(COMMANDS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        assert re.search(r"!\s*`", text) is None, f"{path.name}: bloque shell inline"
        assert re.search(r"@[\w./-]+", text) is None, f"{path.name}: adjunto @path"


def test_artifacts_are_written_in_english() -> None:
    """Cero marcadores ni palabras sueltas en español fuera del código inline."""
    for artifact in ARTIFACTS:
        text = _without_inline_code(artifact.read_text(encoding="utf-8"))
        for marker in SPANISH_MARKERS:
            assert marker not in text, f"{artifact.name}: marcador español {marker!r}"
        assert not SPANISH_WORDS.findall(text), f"{artifact.name}: palabras españolas"


def test_opencode_json_routes_to_itzamna() -> None:
    """`default_agent` resuelve a `itzamna`, registrado y `mode: primary`."""
    doc = json.loads((VAULT_ROOT / "opencode.json").read_text(encoding="utf-8"))
    assert doc["default_agent"] == "itzamna"
    assert "itzamna" in doc["agents"]
    assert _frontmatter(AGENTS_DIR / "itzamna.md")["mode"] == "primary"
