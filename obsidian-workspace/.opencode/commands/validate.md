---
description: "Audit one document: contradictions, bias, and a deterministic claim-by-claim check against the index."
agent: chilam
---

**UH phase:** Critical evaluation. **Arguments:** `$1` = target document path (in `02-drafts/` or `01-tasks/research/`).

## Pre-Flight
Tool catalog: skill `tepochcalli-mcp` (the 7 `tepochcalli-rag` tools — `search`, `index_refresh`, `add_source`, `convert_document`, `convert_base64`, `list_formats`, `rag_status`; call only the ones this phase uses).
If freshness is doubtful call `index_refresh()`; then `search` (top_k ≤ 8) before trusting any anchor.

## Phase: Critical Evaluation
1. Read `$1`. For each claim carrying a `source_path » heading (chars x–y)` citation:
   a. Re-run `search` with the claim's key fragment (top_k ≤ 8).
   b. Check DETERMINISTICALLY that the cited `source_path` and `heading` appear in the results and that the chunk text supports the claim.
2. Classify every claim: `respaldada` (anchor found, chunk supports), `sin_ancla` (citation absent from results), `cita_ajena` (chunk exists, does not support), `sin_cita` (no anchor at all). Ambiguity or analysis failure NEVER counts as `respaldada` — it falls to the nearest problematic class and is listed.
3. Cross-check provenance from `01-tasks/research/`: contradictions, bias, obsolescence, source authority. A `web_search_unconfirmed` reference cited as strong proof is a FINDING, not a warning.
4. Write the report in `04-review/` with frontmatter `{command, agent, target_doc, verdict}`; `verdict` ∈ {ok, ok_con_avisos, rechazado}. `ok` is IMPOSSIBLE with `sin_ancla` or `sin_cita` claims.
5. Write nowhere else; if you find user files in trays 01–05, WARN and continue (non-contamination).

## Escalation
Any `E_*` from `tepochcalli-rag`: call `rag_status()` and report its `fix_hint` — never the raw error.
Doubt about intent or arguments: `question`.

## Suggested Next Step
> Report filed. Run `/synthesize` on the accepted material, or back to `/research` if evidence is missing.
