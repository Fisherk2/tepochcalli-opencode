---
description: Compile and format references behind a deterministic provenance gate; nothing unresolved is compiled.
agent: chilam
---

**Load** `tepochcalli-mcp` skill.

## Pre-Flight

1. Collect every external reference cited by the target document and by its evidence notes in @01-tasks/research/. Each one must carry `origin`.
2. Build a numbered inventory `R1..Rn`: quote each reference verbatim as cited, plus its `origin`, plus its state. Nothing compiles outside this inventory.
3. Normalize states with rules only — no model judgement, no network: `checked` compiles; `web_search_unconfirmed` is included MARKED with its state (never as confirmed); `no_found` / `inaccessible` are DROPPED with a log entry, each labelled separately (`inaccessible` ≠ absent). The legacy label `inaccesible` is accepted only as a logged alias and normalized to `inaccessible`.
4. DETERMINISTIC GATE — rules over states: a reference WITHOUT `origin` makes the gate FAIL NAMING the culprit and the bibliography is NOT emitted (zero partial output). If no reference survives, **STOP** and report with the user, the workflow FAILS instead of emitting an empty bibliography.

## Phase 1: Bibliographic Management

**Load** `citation-management` skill when deduplicating same DOI/URL, for its dedup conventions — NEVER its network scripts (Google Scholar/PubMed/CrossRef forbidden by the gate). Use it to consistent formatting with logged fallback.

1. Normalize metadata of every surviving reference: DOI, URL, author-year. Keep the verbatim quote from `R1..Rn` alongside the normalized form.
2. Deduplicate: same DOI/URL = one entry. Log the duplicate list (`Ra ≡ Rb`) in the note and drop the copies. 
3. Format with $1 (if not APA|MLA|Chicago specified, use APA by default; an unsupported $1 falls back to APA with the fallback logged explicitly). Internal corpus citations (`source_path » heading (chars x–y)`) were anchored by @04-review/ reports; do not re-validate them here.
4. Keep claim→source traceability in every entry: each formatted entry names the claim(s) it supports and its `Rn` id. Split the output into two sections: internal-corpus section (already anchored, no revalidation) vs compiled external bibliography.

## Phase 2: Write Bibliography

1. Build ONE bibliography note skeleton in `03-citations/` with frontmatter `{command, agent, style, date}` and one section per state (checked / web_search_unconfirmed-marked / dropped-log).
2. Anti-prose-audit verification before saving: the note is a bibliography, not a synthesis — entries plus traceability plus logs, no added argument, no verdict prose (audit prose belongs to `04-review/` files, drafting prose to `02-drafts/` files).
3. **Delegate** `obsidian-vault-writer` subagent and save the single note in `03-citations/` and nothing else. **Load** `obsidian-markdown` + `obsidian-vault` skills when creating/saving the single note, for duplicate-free vault management plus file operations.
4. Present a brief summary of the bibliography for human review.
5. **Bibliography is done — do NOT touch or write anything. Only citations tasks and files written to `03-citations/` files.**
6. Commit all changes with a descriptive message (only if you have git installed in the vault, if not, skip this step).

## Rules

- If `03-citations/` directory does not exist, create it.
- Never write outside `03-citations/`, you only write bibliography notes in this directory. 
- Any `E_*` from `tepochcalli-rag`: call `rag_status()` and report its `fix_hint` — never the raw error. Doubt about intent or arguments: `question`.

## Suggested Next Step
> Bibliography ready. Run `/draft` to integrate it.
