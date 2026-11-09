---
description: "Build the research rubric: central question, objectives, scope, source criteria."
agent: nezahualcoyotl
---

**UH phase:** Definition. **Arguments:** `$ARGUMENTS` = the topic or question to frame.

## Pre-Flight
Tool catalog: skill `tepochcalli-mcp` (the 7 `tepochcalli-rag` tools — `search`, `index_refresh`, `add_source`, `convert_document`, `convert_base64`, `list_formats`, `rag_status`; call only the ones this phase uses).
If freshness is doubtful call `index_refresh()`; then `search` (top_k ≤ 8) before reading raw `00-Resources/`.

## Phase: Definition
1. State the central question from `$ARGUMENTS`; if the scope is ambiguous ask with `question` — never invent it.
2. Fix objectives, scope, inclusion/exclusion criteria for sources, and the method to apply.
3. Write ONE rubric note in `01-tasks/` with frontmatter `{command, agent, date}`.
4. Anchor corpus claims only as `source_path » heading (chars x–y)`, using fields that `search` returned.
5. Never write outside `01-tasks/`; if you find user files in trays 01–05, WARN and continue (non-contamination).

## Escalation
Any `E_*` from `tepochcalli-rag`: call `rag_status()` and report its `fix_hint` — never the raw error.
Doubt about intent or arguments: `question`.

## Suggested Next Step
> Rubric saved. Run `/research` to collect evidence against it.
