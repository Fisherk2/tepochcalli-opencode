---
description: Turn validated evidence into thematic axes and the outline that drives drafting.
agent: nezahualcoyotl
---

## Pre-Flight: Validate evidence

1. Inventory inputs: list every note in @01-tasks/research/ and every report in @04-review/ you will use, each with its `verdict` and date.
2. Filter by verdict: read validated evidence only (`verdict` ok/ok_with_warnings). Material without a verdict, or with any other verdict, is NOT input — **STOP**, inform the user, list it as pending, and suggest running `/research` again.
3. Check freshness: if freshness is doubtful, call `index_refresh()`; then `search` (top_k ≤ 8) before reading raw `INDEXER_DIR` or the research notes.
4. Enforce anchors: every piece of evidence entering the outline must carry its `source_path » heading (chars x–y)` anchor. Without an anchor it does not enter the outline.
5. If evidence is correctly validated, **proceed to Phase 1**.

## Phase 1: Design outline

**Load** `doc-coauthoring` skill.

1. **Load** `tepochcalli-mcp` skill and then, name axes: turn clusters into 3–6 named thematic axes (title + 1-line scope each), each carrying its claims (Ci) plus `source_path » heading (chars x–y)` anchors as given.
2. Allocate claims to sections: place each Ci under exactly one axis/section (mark shared claims as reused, never re-judge truth or support).
3. Order the argument: fix section sequence + 1-line argument per section + 1-line transition to the next.
4. Stop check: outline covers the rubric with zero prose drafting. No prose drafting here.

## Phase 2: Write outline

1. Skeleton note: write ONE outline note with frontmatter `{command, agent, phase, date}`, sections, and bullets carrying anchors — never full paragraphs.
2. **Load** `obsidian-markdown` + `obsidian-vault` skills for valid frontmatter, wikilinks and no broken links (format, not content) and save outline notes to `01-tasks/` only.
3. Present a brief 3–5 line summary of the outline for human review.
4. **Synthetisize is done — do NOT touch or write anything. Only outline tasks and write to `01-tasks/` files.**
5. Commit all changes with a descriptive message (only if you have git installed in the vault, if not, skip this step).

## Rules

- Never write outside `01-tasks/`, you only write outlines.
- If `01-tasks/` directory does not exist, create it.
- If freshness is doubtful call `index_refresh()`; then `search` (top_k ≤ 8) before reading raw `00-Resources/` or the research notes.
- Any `E_*` from `tepochcalli-rag`: call `rag_status()` and report its `fix_hint` — never the raw error. Doubt about intent or arguments: `question`.

## Suggested Next Step
> Outline ready. Run `/cite` and then `/draft` to make the first drafts.
