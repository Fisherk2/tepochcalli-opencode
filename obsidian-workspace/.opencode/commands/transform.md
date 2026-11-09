---
description: "Turn accepted research into dissemination artifacts: CSV/Excel, slides, mind map, figures."
agent: tlacuilo
---

**UH phase:** Dissemination. **Arguments:** `$1` = target format; `$ARGUMENTS` = what to transform and for whom.

## Pre-Flight
Tool catalog: skill `tepochcalli-mcp` (the 7 `tepochcalli-rag` tools — `search`, `index_refresh`, `add_source`, `convert_document`, `convert_base64`, `list_formats`, `rag_status`; call only the ones this phase uses).
Call `list_formats` before promising any format; `search` (top_k ≤ 8) to confirm the content you export; `index_refresh()` if freshness is doubtful.

## Phase: Dissemination
1. Source content from `02-drafts/` and `03-citations/` only; an artifact never introduces claims absent from the draft.
2. Use only skills that exist today: `spreadsheet-analysis`/`data-analysis` (CSV/Excel), `posters-generator` (presentations), `markdown-mermaid-writing` (mind map via Mermaid `mindmap`), `data-plotting` (figures), `pdf`/`image-prompt-generator` (ad-hoc conversion).
3. Jupyter notebook, R, Graphviz/PlantUML and LaTeX manuscript are GAPS: declare them as pending Phase 5 (Annex A) — never invent a skill name or fake the output.
4. `convert_document`/`convert_base64` write a readable `.md` to disk; that file is not the citable source (the original stays indexed via `index_refresh`).
5. Write the artifacts in `05-outputs/` plus a manifest note with frontmatter `{command, agent, source_draft, formats, date}`; citations inside artifacts keep `source_path » heading (chars x–y)`.
6. Write nowhere else; if you find user files in trays 01–05, WARN and continue (non-contamination).

## Escalation
Any `E_*` from `tepochcalli-rag`: call `rag_status()` and report its `fix_hint` — never the raw error.
Doubt about intent or arguments: `question`.

## Suggested Next Step
> Artifacts in `05-outputs/`. Run `/update` if the source draft changes.
