---
description: "Peer-review a draft: spelling, argument coherence, clarity, and substantive improvements."
agent: chilam
---

## Phase 0: Pre-Flight — resolve the target

1. Resolve the target draft inside `02-drafts/`. List the `*.md` candidates in `02-drafts/`, then use the `question` tool to ask the user which draft to review; without a resolved target there is no review.
2. **Load** `tepochcalli-mcp` skill and check freshness before judging anything, because an anchor can only be trusted against a fresh index: run `index_refresh()` if freshness is doubtful, then re-run `search` (top_k ≤ 8) with each claim's key fragment before classifying its anchor.
3. Record the input inventory: the file's base name plus its current revision (`none` for a plain `*.md` file, otherwise the trailing `-revX` suffix), because the output name in Phase 2 is derived deterministically from it.

## Phase 1: Categorize findings

**Load** `peer-review` skill alongside `scholar-evaluation` skill, use every finding carries location, observation, evidence and a requested action; draws the boundary between authority-of-evidence judgments and mere style preferences, keeping the review developmental and never a publish/reject verdict.

1. Review targeted files without editing them.
2. Assess spelling and grammar, argument coherence, clarity, structure, and evidence coverage; every finding names its location (heading or quoted fragment). When a finding touches the method, design or bias behind a scientific claim, **Load** `scientific-critical-thinking` skill at that moment, because methodology and confounding need its rigor checklist rather than a reviewer's impression; and when a finding disputes numbers, tests or effect sizes.
3. Re-check anchors: a claim whose `source_path » heading (chars x–y)` citation no longer resolves via `search` is reported as `no_anchor`, never silently fixed. When the finding concerns a bibliography entry rather than an index anchor, **Load** `citation-management` skill for local metadata and format validation only. If deeper source evaluation is needed before a finding can be stated fairly, **Delegate** `research-analyst` subagent for that read-only analysis.
4. Categorize findings as `spelling`, `argument`, `clarity`, `structure`, `evidence`, or `no_anchor`
5. Output a list of findings with their categories and locations with specific file:line references and fix recommendations.

Before making reviews, use the `question` tool to resolve ambiguities:
- Flag findings that could be **false positives** — ask the user to confirm
- Ask if any observation is **intentional** — the user may have a valid reason
- Let the user dismiss, accept, or modify each disputed finding

6. Use the `question` tool to ask the user to confirm the review before proceeding with fixes. Without confirmation, **STOP** here: zero writing happens, the input draft stays byte-identical, and no `-revX` file is created.

## Phase 2: Fix drafts into the next revision

1. If the user confirms the review, **Delegate** `obsidian-vault-writer` subagent and **Load** `obsidian-markdown` + `obsidian-vault` skills, because the writer owns valid vault writes — frontmatter, wikilinks, no broken links.
2. Apply only the confirmed findings; every dismissed or modified finding follows the user's ruling, never the original draft text. 
3. When several confirmed findings touch the same passage, **Delegate** `knowledge-synthesizer` subagent first for a read-only merge plan, because overlapping fixes applied independently contradict each other and it synthesizes without editing. 
4. Name the output by the deterministic revision rule, never touching the input file: `*.md` becomes `*-revA.md`, and any `*-revA.md` becomes `*-revB.md` — in general increment the last letter `A→B→…→Z`, and past `Z` continue with `revAA` (that ceiling is documented, not silently capped). 
5. The new file lives in `02-drafts/` and carries updated frontmatter `{command: review, agent: chilam, source, rev}` naming the input file and the new revision letter. When a `clarity` or `structure` fix requires rephrasing a paragraph rather than a mechanical correction.
6. When an applied fix must keep full-paragraph scientific prose intact, **Load** `scientific-writing` skill during the edit, because restructuring must preserve flowing IMRAD prose rather than collapsing into bullets; and when the fix changes the draft's voice, **Load** `article-writing` skill then, because repeated corrections drift in voice without its consistency guidance. 
7. Present a brief summary of the fixed findings for human review.
8. **Review is done — do NOT touch or write anything. Only review/corrections tasks and files written to `02-drafts/` files.**
9. Commit all changes with a descriptive message (only if you have git installed in the vault, if not, skip this step).

## Rules

- If `02-drafts/` does not exist, create it.
- Never write outside of `02-drafts/` directory.
- Every preserved citation keeps its `source_path » heading (chars x–y)` verbatim from the confirmed finding.
- `search` (top_k ≤ 8) for any claim whose support looks thin before writing a finding; `index_refresh()` if freshness is doubtful.
- Any `E_*` from `tepochcalli-rag`: call `rag_status()` and report its `fix_hint` — never the raw error. Doubt about intent or arguments: `question`.

## Suggested Next Step
> Review filed. Run `/transform` if you want to transform the draft into a different format.
