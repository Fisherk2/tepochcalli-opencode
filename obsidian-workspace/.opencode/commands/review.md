---
description: "Peer-review a draft: spelling, argument coherence, clarity, and substantive improvements."
agent: chilam
---

**UH phase:** Refinement. **Arguments:** `$1` = draft path in `02-drafts/`.

## Pre-Flight
Tool catalog: skill `tepochcalli-mcp` (the 7 `tepochcalli-rag` tools — `search`, `index_refresh`, `add_source`, `convert_document`, `convert_base64`, `list_formats`, `rag_status`; call only the ones this phase uses).
`search` (top_k ≤ 8) for any claim whose support looks thin before writing a finding; `index_refresh()` if freshness is doubtful.

## Phase: Refinement
1. Review `$1` without editing it: the draft belongs to Tlacuilo, a reviewer never rewrites in place.
2. Assess spelling and grammar, argument coherence, clarity, structure, and evidence coverage; every finding names its location (heading or quoted fragment).
3. Re-check anchors: a claim whose `source_path » heading (chars x–y)` citation no longer resolves via `search` is reported as `sin_ancla`, never silently fixed.
4. Write ONE review report in `04-review/` with frontmatter `{command, agent, target_doc, verdict}`; `verdict` ∈ {ok, ok_con_avisos, rechazado}.
5. Reading across trays is allowed; write nowhere else. If you find user files in trays 01–05, WARN and continue (non-contamination).

## Escalation
Any `E_*` from `tepochcalli-rag`: call `rag_status()` and report its `fix_hint` — never the raw error.
Doubt about intent or arguments: `question`.

## Suggested Next Step
> Review filed. Run `/update` for targeted fixes, then `/transform` once the draft is accepted.
