---
description: Write the draft from the approved outline and the compiled citations.
agent: tlacuilo
---

## Pre-Flight: Confirm the three inputs

1. Inventory the three inputs before compiling — fresh outline in @01-tasks/ (axes + claims Ci + anchors), bibliography in @03-citations/ (entries `R1..Rn` + states), and research notes in @01-tasks/research/ each with a @04-review/ verdict of `ok`/`ok_with_warnings` (evidence collected per research file, validated per validate file). Without outline, without citations, or with a `rejected`/missing verdict → **STOP**, report to user this observation, list what is pending, and suggest user to call `/synthesize`, `/cite`, or `/research` + `/validate` according to what is missing.
2. **Load** `tepochcalli-mcp` skill when confirming freshness and anchors, because it is the single door to `search`/`index_refresh`/`rag_status` — doubt about freshness → call `index_refresh()` first, then re-confirm any quoted passage with `search` (top_k ≤ 8) before it enters the draft.

## Phase 1: Compilation

1. Map every outline section → its claims `Ci` + anchors + supporting `R` entries, using the confirmed inventory only; a section without anchors is flagged, not invented.
2. Freeze references exactly as delivered from @03-citations/ — the format `source_path » heading (chars x–y)` and the compiled entry are contract; never paraphrase an anchor.
3. No browsing: state what the corpus and the cited sources say, nothing else. Missing evidence is reported to the user, not filled.

## Phase 2: Drafting

1. **Load** `scientific-writing` skill when turning compiled bullets into flowing prose, because it enforces full paragraphs with citation discipline and never bullet-point manuscripts — prose shape only, never its research-lookup (the corpus is closed, zero new browsing).
2. **Delegate** `obsidian-vault-writer` subagent and **Load** `obsidian-markdown` + `obsidian-vault` skills when writing the draft file, because the specialist plus the two vault skills guarantee valid frontmatter/wikilinks with no broken links — write in `02-drafts/` with frontmatter `{command, agent, outline, date}` following the section skeleton of the outline, prose only from what Phase 1 compiled.
3. **Load** `markdown-mermaid-writing` skill only when the outline calls for a diagram, because it keeps the figure as version-checked text without prose invention — and **Load** `math-typesetting-guide` skill only when the draft needs equations, because it fixes LaTeX numbering/cross-references without touching the evidence.
4. Verify against invention before saving: every assertion carries its anchor or its `R` cite, zero new browsing; then present a brief summary of the draft for human review.
5. **Draft is done — do NOT touch or write anything. Only drafting tasks and files written to `02-drafts/` files.**
6. Commit all changes with a descriptive message (only if you have git installed in the vault, if not, skip this step).

## Rules

- If `02-drafts/` directory does not exist, create it.
- Never write outside `02-drafts/`, you only write drafts in this directory. 
- Any `E_*` from `tepochcalli-rag`: call `rag_status()` and report its `fix_hint` — never the raw error. Doubt about intent or arguments: `question`.
- Before quoting any corpus passage, confirm it with `search` (top_k ≤ 8); if freshness is doubtful call `index_refresh()` first.

## Suggested Next Step
> Draft written. Run `/review` on it.
