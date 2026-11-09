---
description: Compile and format references behind a deterministic provenance gate; nothing unresolved is compiled.
agent: chilam
---

**UH phase:** Bibliographic management. **Arguments:** `$1` = style (APA|MLA|Chicago; default APA).

## Pre-Flight
Tool catalog: skill `tepochcalli-mcp` (the 7 `tepochcalli-rag` tools — `search`, `index_refresh`, `add_source`, `convert_document`, `convert_base64`, `list_formats`, `rag_status`; call only the ones this phase uses).
Chilam does not browse: this command NEVER calls `websearch`/`webfetch`. `search` only on an explicit re-traceability request; the gate runs on the evidence produced by `/research`.

## Phase: Bibliographic Management
1. Collect every external reference cited by the target document and by its evidence notes in `01-tasks/research/`. Each one must carry `procedencia`.
2. DETERMINISTIC GATE — rules over states, no model judgement, no network: `verificada` compiles; `web_search_unconfirmed` is included MARKED with its state (never as confirmed); `no_encontrada`/`inaccesible` are DROPPED with a log entry, each labelled separately (inaccesible ≠ absent). A reference WITHOUT `procedencia` makes the gate FAIL NAMING the culprit and the bibliography is NOT emitted (zero partial output). If no reference survives, the command FAILS instead of emitting an empty bibliography.
3. Format with `$1`, deduplicate, and keep claim→source traceability in every entry. Internal corpus citations (`source_path » heading (chars x–y)`) were anchored by `/validate`; do not re-validate them here.
4. Write ONE bibliography note in `03-citations/` with frontmatter `{command, agent, style, date}`.
5. Write nowhere else; if you find user files in trays 01–05, WARN and continue (non-contamination).

## Escalation
Any `E_*` from `tepochcalli-rag`: call `rag_status()` and report its `fix_hint` — never the raw error.
Doubt about intent or arguments: `question`.

## Suggested Next Step
> Bibliography ready. Run `/draft` to integrate it, or `/transform` for dissemination artifacts.
