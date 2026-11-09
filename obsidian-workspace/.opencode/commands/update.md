---
description: Inject new information or correct specific data in an existing draft without restarting the workflow.
agent: tlacuilo
---

**UH phase:** Maintenance. **Arguments:** `$1` = draft path or section in `02-drafts/`; `$ARGUMENTS` = the new information or correction.

## Pre-Flight
Tool catalog: skill `tepochcalli-mcp` (the 7 `tepochcalli-rag` tools — `search`, `index_refresh`, `add_source`, `convert_document`, `convert_base64`, `list_formats`, `rag_status`; call only the ones this phase uses).
If the update comes from new material call `index_refresh()` first; `add_source` only when the user explicitly asks to ingest it; `search` (top_k ≤ 8) before reading raw `00-Resources/`.

## Phase: Maintenance
1. Locate `$1` in `02-drafts/`; if it does not resolve to exactly one draft, ask with `question`.
2. Apply only the change in `$ARGUMENTS`: no re-planning, no re-drafting of unrelated sections, no new workflow phase.
3. New claims need anchors: confirm them with `search` and cite as `source_path » heading (chars x–y)`; without an anchor, flag the sentence as unsupported instead of asserting it.
4. Keep the draft's existing citations and frontmatter; update `{command, agent, date, revision_note}` and record what changed and why.
5. Write only that draft in `02-drafts/`; reading across trays is allowed. If you find user files in trays 01–05, WARN and continue (non-contamination).

## Escalation
Any `E_*` from `tepochcalli-rag`: call `rag_status()` and report its `fix_hint` — never the raw error.
Doubt about intent or arguments: `question`.

## Suggested Next Step
> Update applied. Run `/review` to re-check the draft, or `/transform` to refresh the artifacts.
