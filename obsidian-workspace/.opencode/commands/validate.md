---
description: "Audit the target document(s): contradictions, bias, and a deterministic claim-by-claim check against the index."
agent: chilam
---

**Load** `scholar-evaluation` skill to perform a thorough audit of the target document(s). This includes checking for contradictions, bias, and a deterministic claim-by-claim check against the index.

## Phase 0: Database Index Preparation

**Delegate** `research-analyst` subagent to:

1. Read @01-task/rubric.md and @01-task/todo.md carefully.
2. Analyze sources and target documents.
3. Inspect claims in target documents and their citations.
4. Ensure that the index is comprehensive and accurate.

All of this index will be used to critically evaluate the claims in the target documents.
 
## Phase 1: Critical Claim Evaluation

**Load** `tepochcalli-mcp` skill.

1. Build the claim inventory first: numbered list `C1..Cn`, each with claim text (≤2 lines) plus the citation as written (`source_path » heading (chars x–y)` or `no_citation`).
2. Read all target documents. For each claim carrying a `source_path » heading (chars x–y)` citation:
   a. Re-run `search` with the claim's key fragment (top_k ≤ 8).
   b. If the first fragment returns no anchor, re-query once with an alternative fragment (synonym or shorter span) before judging.
   c. Check DETERMINISTICALLY that the cited `source_path` and `heading` appear in the results and that the chunk text supports the claim.
3. Verify offsets: the cited `chars x–y` must fall inside the returned chunk span; a range outside the chunk or pointing at boilerplate is `no_anchor`.
4. Detect borrowed citations: if the chunk exists but supports a different claim than the one citing it, classify as `external_citation` and name the claim it actually supports (`Cj`), if any.
5. Classify every claim: `backed` (anchor found, chunk supports), `no_anchor` (citation absent from results), `external_citation` (chunk exists, does not support), `no_citation` (no anchor at all). Ambiguity or analysis failure NEVER counts as `backed` — it falls to the nearest problematic class and is listed.

## Phase 2: Content Review

**Load** `peer-review` skill

1. Map contradictions claim-vs-claim: list every pair (`Ci` vs `Cj`) that cannot both hold, quoting both claims with their anchors.
2. Check bias in three forms: selection (one-sided sources), confirmation (contrary evidence ignored), obsolescence (newer indexed material contradicts the claim).
3. Check source authority: provenance (index vs web) plus hierarchy (primary study > review > grey literature); an authority claim with no provenance is downgraded.
4. Check freshness: consultation date vs index state, and cross-check provenance from @01-tasks/research/. If freshness is doubtful, refresh per Rules before trusting any anchor.
5. A `web_search_unconfirmed` reference cited as strong proof is a FINDING, not a warning — record it with severity.

Before make reports, use the `question` tool to resolve ambiguities:
- Flag findings that could be **false positives** — ask the user to confirm
- Ask if any observation is **intentional** — the user may have a valid reason
- Let the user dismiss, accept, or modify each disputed finding

## Phase 3: Report Writing

**Delegate** `obsidian-vault-writer` subagent and **Load** `obsidian-markdown` + `obsidian-vault` skills for valid frontmatter, wikilinks and no broken links (format, not content).

1. Rank findings in a severity table (`critical`: `no_anchor`/`no_citation`; `major`: `external_citation`, contradiction, `web_search_unconfirmed`-as-proof; `minor`: bias, freshness, authority caveats), one row per claim (`Ci`, class, evidence).
2. Set the verdict by rule: `ok` is IMPOSSIBLE with `no_anchor` or `no_citation` claims; `ok_with_warnings` only with at most `minor` findings or a single minor `external_citation`; anything else is `rejected`.
3. List rework incidents for researcher: what to re-request (missing anchor, better source, newer evidence) with the acceptance criterion each must meet.
4. Write the human summary first (3–6 lines: verdict, counts by class, top incidents), then save the report in `04-review/` with frontmatter `{command, agent, target_doc, verdict}`; `verdict` ∈ {ok, ok_with_warnings, rejected}. `ok` is IMPOSSIBLE with `no_anchor` or `no_citation` claims.
5. Present a brief summary of the report findings for human review.
6. **Report is done — do NOT touch or write anything. Only validate tasks and files written to `04-review/` files.**
7. Commit all changes with a descriptive message (only if you have git installed in the vault, if not, skip this step).

## Rules

- Never write outside of `04-review/` directory.
- If `04-review/` does not exist, create it.
- Any `E_*` from `tepochcalli-rag`: call `rag_status()` and report its `fix_hint` — never the raw error. Doubt about intent or arguments: `question`.
- If freshness is doubtful call `index_refresh()`; then `search` (top_k ≤ 8) before trusting any anchor.

## Suggested Next Step
> Report filed. Run `/synthesize` on the accepted material or `/research` again to fix all observations.
