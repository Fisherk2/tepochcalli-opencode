---
description: Turn validated evidence into thematic axes and the outline that drives drafting.
agent: nezahualcoyotl
---

**UH phase:** Analysis. **Arguments:** `$ARGUMENTS` = the scope or angle to structure (default: the whole rubric).

## Pre-Flight
Tool catalog: skill `tepochcalli-mcp` (the 7 `tepochcalli-rag` tools — `search`, `index_refresh`, `add_source`, `convert_document`, `convert_base64`, `list_formats`, `rag_status`; call only the ones this phase uses).
If freshness is doubtful call `index_refresh()`; then `search` (top_k ≤ 8) before reading raw `00-Resources/` or the research notes.

## Phase: Analysis
1. Read validated evidence only: notes in `01-tasks/research/` and reports in `04-review/` with `verdict` ok/ok_con_avisos. Material without a verdict is NOT input — list it as pending `/validate`.
2. Build thematic axes and patterns from that evidence; each axis carries the `source_path » heading (chars x–y)` anchors that support it.
3. Produce the outline: sections, order, and the argument of each section. No prose drafting here.
4. Write ONE outline note in `01-tasks/` with frontmatter `{command, agent, phase, date}`.
5. Reading across trays is allowed; write nowhere else. If you find user files in trays 01–05, WARN and continue (non-contamination).

## Escalation
Any `E_*` from `tepochcalli-rag`: call `rag_status()` and report its `fix_hint` — never the raw error.
Doubt about intent or arguments: `question`.

## Suggested Next Step
> Outline ready. Run `/cite` and `/draft` (either order), then `/review`.
