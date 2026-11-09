---
description: Write the draft from the approved outline and the compiled citations.
agent: tlacuilo
---

**UH phase:** Writing. **Arguments:** `$1` = outline note in `01-tasks/`; `$ARGUMENTS` = optional section focus.

## Pre-Flight
Tool catalog: skill `tepochcalli-mcp` (the 7 `tepochcalli-rag` tools — `search`, `index_refresh`, `add_source`, `convert_document`, `convert_base64`, `list_formats`, `rag_status`; call only the ones this phase uses).
Before quoting any corpus passage, confirm it with `search` (top_k ≤ 8); if freshness is doubtful call `index_refresh()` first.

## Phase: Writing
1. Start ONLY from the `/synthesize` outline (`$1`) and from evidence that `/validate` accepted; a section without anchors is flagged, not invented.
2. Take references from `03-citations/` and keep them exactly as delivered — the format `source_path » heading (chars x–y)` and the compiled entry are contract; never paraphrase an anchor.
3. No browsing: state what the corpus and the cited sources say, nothing else. Missing evidence is reported to the user, not filled.
4. Write the draft in `02-drafts/` with frontmatter `{command, agent, outline, date}`.
5. Read from `01-tasks/`, `03-citations/` and `04-review/`; write nowhere else. If you find user files in trays 01–05, WARN and continue (non-contamination).

## Escalation
Any `E_*` from `tepochcalli-rag`: call `rag_status()` and report its `fix_hint` — never the raw error.
Doubt about intent or arguments: `question`.

## Suggested Next Step
> Draft written. Run `/review` on it.
