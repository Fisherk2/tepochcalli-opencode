---
description: Inject new information or correct specific data in an existing draft without restarting the workflow.
agent: tlacuilo
---

## Pre-Flight: Target and scope

1. Analize user intent and identify targer files to update, use the `question` tool to clarify; without a resolved target, **STOP** — no reading, no writing.
2. Record the input inventory: the file's base name plus its current revision (`none` for a plain `*.md` file, otherwise the trailing `-revX` suffix), because the output name in Phase 2 derives deterministically from it. Classify the request into exactly one surgical scope — `inject-new-info` (add a fact or paragraph), `correct-data` (fix a value or wording), or `refresh-stale-cite` (replace a dead anchor) — and touch only the targeted sections; everything else stays byte-identical. Re-planning the outline or re-drafting unrelated sections is prohibited.
3. Check freshness before collecting anything: if the update comes from new material, **Load** `tepochcalli-mcp` skill and call `index_refresh()` first; `add_source` only when the user explicitly asks to ingest it.

## Phase 1: Collect new information

1. **Delegate** appropriate specialist subagents (sequentially or in parallel) and use the following sources in order to collect updated evidence for the targeted sections only, using all available sources if any single method does not provide what is needed:
- **Search**: **Load** `tepochcalli-mcp` skill and use `tepochcalli-rag` MCP to search the indexed material for the targeted change, ingesting new material if needed. **Delegate** `search-specialist` subagent when `search` (top_k ≤ 8) returns nothing useful, because it crafts advanced queries + curates sources before widening context.
- **Plugins**: Analyze what plugins are installed and use them to collect sources for the targeted change.
- **Web Search**: Use `websearch`/`webfetch` tool if the information is not in the indexed material; ingest sources with `tepochcalli-rag` if they are reliable.
- **MCP**: Analyze what other MCPs are available and use them to acquire more information for the targeted change.
- **OSINT TOOLS**: ONLY if the request requires verifying a source's identity/authenticity: **Load** `osint-skills` skill because it verifies source provenance, never judging content.
- **Citations**: Use `03-citations/` (if it exists) files in the vault as known sources and use them to acquire more information for the targeted change.
- **Vault**: Search the obsidian vault for related information. If you find reliable files, ask the user with the `question` tool whether they want to copy the file (only if it is a markdown file) or convert it to markdown into `INDEXER_DIR` and ingest it with `tepochcalli-rag`.
- **Skills**: Analyze and load available skills (if the request requires specialized knowledge).
- **Tools**: Analyze what other tools are available and summon them to acquire knowledge.

⚠️ **Last resort:** If no other search engine tools are available, use these tools:
  - For academic external evidence: **Load** `literature-search-engine` skill when discovering papers, because it returns unified results with provenance (endpoint + identifiers + access date) feeding `verified`/`web_search_unconfirmed` + `origin`; read its `references/` before calling any API. **Delegate** `scientific-literature-researcher` subagent when the targeted change needs papers, because it returns candidates with DOI + provenance without drafting.
  - For non-academic external evidence: **Load** `websearch-engine` skill when the evidence lies outside academic databases, because it gives recall freshness with each claim cited inline + Sources.

2. Every new claim needs an anchor: confirm it with `search` (top_k ≤ 8) and cite it as `source_path » heading (chars x–y)`; re-query once with an alternative fragment before declaring `no_anchor`. Without an anchor, flag the sentence as `unsupported` — never assert it.
3. Keep the draft's existing citations and frontmatter untouched; update only `{command: update, agent: tlacuilo, date, revision_note}` recording what changed and why.

## Phase 2: Rewriting

1. Use `question` tool to confirm the scope of the change: what sections need updating, diff information, and what is the new claim. If the scope or wording is ambiguous, resolve it with the user.
1. If user confirms the change, apply only the confirmed changes; then **Delegate** `obsidian-vault-writer` subagent and **Load** `obsidian-markdown` + `obsidian-vault` skills, because the writer owns valid vault writes — frontmatter, wikilinks, no broken links — and write the updated document in `02-drafts/`.
2. Name the output by the deterministic revision rule, never touching the input file: `*.md` becomes `*-revA.md`, and any `*-revA.md` becomes `*-revB.md` — in general increment the last letter `A→B→…→Z`, and past `Z` continue with `revAA` (that ceiling is documented, not silently capped).
3. Keep the diff minimal and verifiable: only the targeted sections differ from the input; the rest of the file stays byte-identical.
4. Present a brief summary of what was updated and why, for human review.
5. **Update is done — do NOT touch or write anything else. Only update tasks and files written to `02-drafts/` files.** 
6. Commit all changes with a descriptive message (only if git is installed in the vault; if not, skip this step).

## Rules

- Never write outside the `02-drafts/` directory.
- If `02-drafts/` does not exist, create it.
- Never invent numbers or citations; every new figure or claim carries its `search` anchor, otherwise it is flagged `unsupported`.
- Never re-plan the outline or re-draft unrelated sections; this command patches, it does not redesign.
- Any `E_*` from `tepochcalli-rag`: call `rag_status()` and report its `fix_hint` — never the raw error. Doubt about intent or arguments: `question`.
- If the update comes from new material, call `index_refresh()` first; `add_source` only when the user explicitly asks to ingest it; `search` (top_k ≤ 8) before reading raw `INDEXER_DIR`.

## Suggested Next Step

> Update applied. Run `/review` to re-check the updated draft, or `/transform` to generate artifacts.
