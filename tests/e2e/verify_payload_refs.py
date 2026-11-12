#!/usr/bin/env python3
"""TD-34 gate: every skill/subagent named by the payload exists (Phase 6, T12).

Standalone: the name does not start with `test_`, so `just python-test` never
collects it.

    python3 tests/e2e/verify_payload_refs.py              # repo payload
    python3 tests/e2e/verify_payload_refs.py <vault>      # installed vault (T15)

Scans the 9 commands and the 5 primary agents, extracts every typed reference
(backticked `x` followed by "skill"/"subagent", a command's `agent:`
frontmatter, and each `action: subagent` + `resource:` permission pair) and
resolves the name against `.opencode/skills/` and `.opencode/agents/`. Exit
code is non-zero with one `FAIL: ...` line per broken reference: a command
that loads a non-existent name fails only at harness runtime, invisible to
`just ci`.

Extraction is deliberately narrow (no AST, no dependencies): an inline-code
span is typed by the text that follows it up to the next span, so
"`a` + `b` skills" makes both skills while "`x` MCP" stays a non-reference.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PAYLOAD = Path(__file__).resolve().parents[2] / "obsidian-workspace"

PRIMARY_AGENTS = ("itzamna", "nezahualcoyotl", "pochteca", "chilam", "tlacuilo")

_SPAN = re.compile(r"`([^`\n]+)`")
_NAME = re.compile(r"[a-z0-9][a-z0-9-]+")
_TYPED = re.compile(r"^\s*(skills?|subagents?)\b")
_CONNECTOR = re.compile(r"^\s*(?:\+|,|or|and)\s*$")
_FENCE = re.compile(r"^\s*(?:```|~~~)")
_AGENT_KEY = re.compile(r"^agent:\s*\"?'?([a-z0-9-]+)'?\"?\s*$")
_PERM_ACTION = re.compile(r"^\s*-\s*action:\s*subagent\s*$")
_PERM_RESOURCE = re.compile(r"^\s*resource:\s*\"?([a-z0-9-]+)\"?\s*$")


def typed_refs(text: str) -> list[tuple[int, str, str]]:
    """Return `(line, kind, name)` for every typed reference in `text`.

    kind is `skill`, `subagent` or `agent` (frontmatter and permission
    resources); the name comes back unvalidated on purpose.
    """
    lines = text.splitlines()
    refs: list[tuple[int, str, str]] = []
    state = "front" if lines and lines[0].strip() == "---" else "body"
    in_fence = False
    perm_pending = False
    for lineno, line in enumerate(lines, 1):
        if state == "front":
            if lineno > 1 and line.strip() == "---":
                state = "body"
                continue
            match = _AGENT_KEY.match(line)
            if match:
                refs.append((lineno, "agent", match.group(1)))
                continue
            if _PERM_ACTION.match(line):
                perm_pending = True
                continue
            if perm_pending:
                resource = _PERM_RESOURCE.match(line)
                if resource:
                    refs.append((lineno, "agent", resource.group(1)))
                perm_pending = False
            continue
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        spans = [(m.start(), m.end(), m.group(1)) for m in _SPAN.finditer(line)]
        kinds: list[str | None] = []
        for idx, (_, end, _) in enumerate(spans):
            last = idx + 1 < len(spans)
            tail = line[end : spans[idx + 1][0]] if last else line[end : end + 40]
            typed = _TYPED.match(tail)
            if typed and typed.group(1).startswith("skill"):
                kinds.append("skill")
            elif typed:
                kinds.append("subagent")
            elif _CONNECTOR.match(tail):
                kinds.append("connector")
            else:
                kinds.append(None)
        for idx in range(len(spans) - 1, -1, -1):  # a chain inherits right-to-left
            if kinds[idx] == "connector":
                kinds[idx] = kinds[idx + 1] if idx + 1 < len(kinds) else None
            name = spans[idx][2]
            if kinds[idx] in ("skill", "subagent") and _NAME.fullmatch(name):
                refs.append((lineno, str(kinds[idx]), name))
    return refs


def inventory(root: Path) -> tuple[dict[str, Path], dict[str, Path]]:
    """Map name to path for the skills and agents actually present under `root`."""
    opencode = root / ".opencode"
    skills = {p.name: p for p in (opencode / "skills").iterdir() if p.is_dir()}
    agents = {p.stem: p for p in (opencode / "agents").glob("*.md")}
    return skills, agents


def mode_of(path: Path) -> str:
    """Return the agent frontmatter `mode:` value ('?' when absent)."""
    for line in path.read_text(encoding="utf-8").splitlines()[1:60]:
        if line.strip() == "---":
            break
        if line.startswith("mode:"):
            return line.split(":", 1)[1].strip()
    return "?"


def verify(root: Path) -> tuple[list[str], int, int]:
    """Return `(failures, refs_checked, skills_count)` for the payload at `root`."""
    skills, agents = inventory(root)
    opencode = root / ".opencode"
    targets = sorted((opencode / "commands").glob("*.md"))
    targets += [opencode / "agents" / f"{name}.md" for name in PRIMARY_AGENTS]
    failures = [
        f"FAIL: {name} has no SKILL.md"
        for name, path in sorted(skills.items())
        if not (path / "SKILL.md").is_file()
    ]
    checked = 0
    for path in targets:
        where = path.relative_to(opencode)
        if not path.is_file():
            failures.append(f"FAIL: {where} is missing")
            continue
        is_command = path.parent.name == "commands"
        for lineno, kind, name in typed_refs(path.read_text(encoding="utf-8")):
            checked += 1
            if kind == "skill":
                if name not in skills:
                    failures.append(
                        f"FAIL: {where}:{lineno} loads skill `{name}` - not in .opencode/skills/"
                    )
            elif name not in agents:
                failures.append(
                    f"FAIL: {where}:{lineno} names agent `{name}` - not in .opencode/agents/"
                )
            elif is_command and kind == "agent" and mode_of(agents[name]) != "primary":
                failures.append(
                    f"FAIL: {where}:{lineno} binds agent: {name}"
                    f" - mode {mode_of(agents[name])}, not primary"
                )
            elif kind == "subagent" and mode_of(agents[name]) != "subagent":
                failures.append(
                    f"FAIL: {where}:{lineno} delegates to `{name}`"
                    f" - mode {mode_of(agents[name])}, not subagent"
                )
    return failures, checked, len(skills)


def main(argv: list[str] | None = None) -> int:
    """Run the check: 0 when every reference resolves, 1 on orphans, 2 on bad root."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=PAYLOAD,
        help="vault (or payload) root holding .opencode/ (default: repo payload)",
    )
    args = parser.parse_args(argv)
    root: Path = args.root.resolve()
    if not (root / ".opencode").is_dir():
        print(f"FAIL: {root}/.opencode/ not found", file=sys.stderr)
        return 2
    failures, checked, skills = verify(root)
    for failure in failures:
        print(failure)
    _, agents = inventory(root)
    print(
        f"{len(failures)} failure(s); {checked} reference(s) checked against "
        f"{skills} skill(s) and {len(agents)} agent(s) in {root}"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
