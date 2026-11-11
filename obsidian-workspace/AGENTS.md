# Agent Guide — Obsidian Vault

> Required reference for any agent operating in this vault.

This guide defines how to create, edit, organize, and connect Markdown notes so the vault stays consistent, searchable, and fully rendered in Obsidian.

## 1. Vault Principles

- One concept per note; keep notes atomic and self-contained.
- Prefer structure over prose: headers, lists, tables, and visuals.
- Every note is discoverable: frontmatter, tags, and links to related notes.
- Never break existing links when renaming or moving notes.
- Write for reading view: what renders in Obsidian is the source of truth.

## 2. Naming (Files, Dirs, Tags)

### Files

- Lowercase with hyphens: `postgresql-setup.md`
- No spaces or special characters.
- Shape: `descriptive-name.md`

### Directories

- Numbered from 10 upward, two digits: `10-templates`, `20-projects`, `21-aws`
- Lowercase with hyphens: `20-devops-docker`
- No spaces or special characters.
- Numbers `00-09` are reserved for system workflows; do not create new dirs in that range.

### Tags

- Hierarchical: `#databases/postgresql`, `#devops/docker`
- Simple: `#recipe`, `#resources`
- Place tags in frontmatter or inline.

## 3. Write notes with Obsidian syntax

Do not inline syntax in this guide. Always load the skill for current syntax.

- MUST **Load** `obsidian-markdown` and `obsidian-vault` for every vault write.
- **Load** `markdown-mermaid-writing` only when diagrams are needed.
- **Load** `math-typesetting-guide` only when LaTeX sintax is needed.

## 4. Frontmatter Contract

Every note starts with this block:

```yaml
---
title: Descriptive Name
date: YYYY-MM-DD
tags: [category, subcategory]
aliases: [alternative name]
---
```

> No frontmatter means no metadata, so the note will not appear in filtered searches.

## 5. Templates

- Create every new note from `10-templates/` using the matching template.
- Do not modify the originals in `10-templates/` unless the user explicitly asks.

Keep both blocks short, factual, and inside the note body or a dedicated section.

## 6. Operation Rules

### Always

1. Search for an existing note before creating a new one.
2. Use the matching template from `10-templates/`.
3. Include complete frontmatter.
4. Connect to related notes with wikilinks.
5. Use the full Obsidian rendering: tables, callouts, code blocks, diagrams.
6. Design visually: less dense prose, more structure and graphics.

### Never

1. Create duplicate notes.
2. Break existing wikilinks when renaming or moving.
3. Write text-only notes with no structural or visual aids.
4. Skip frontmatter.
5. Read, analyze, or modify excluded files (see section 9).

> **Note:** If the user needs to perform a specialized tasks, **Delegate** CLI operations to the `obsidian-vault-writer` subagent and **Load** `obsidian-cli` skill, execute `obsidian help` to see available commands before using them (if are available).

## 7. Search and Linking

Vault-native methods only:

1. **By name:** follow or type `[[note-name]]` and use backlinks to find references.
2. **By tag:** browse `#category` or `#category/subcategory` via the tag pane.
3. **By text:** use the obsidian cli search (if are available) for phrases and headings or use glob/grep tools.
4. **By folder:** browse the numbered directory structure top-down.
5. **By graph:** use graph view to spot clusters, orphans, and missing links.
6. Link every new note to at least one related note; add backlinks at the bottom when useful.

## 8. Excluded Files

> Ignore these completely: do not read, analyze, or modify them. Extend this placeholder table as needed.

| Pattern | Reason |
|---|---|
| `.obsidian/` | Obsidian settings and cache |
| `.gitignore` | Version control exclusions |
| `.opencode/` | OpenCode settings |
 `.tepochcalli/` | Tepochcalli RAG settings |
| `.git/` | Version control metadata |
| `.DS_Store` | OS metadata file |
| `*.tmp`, `*.bak`, `*.swp` | Temporary and backup files |

## 9. Note writing workflow

1. **Receive** the user request.
2. **Search** for an existing note before creating one.
3. **Apply** the matching template from `10-templates/` (if applicable).
4. **Write** the note with full frontmatter and Obsidian rendering.
5. **Connect** to related notes with wikilinks.
6. **Verify** no existing links are broken.

---

## REFERENCES

Use this reliable resources to support your notes:

- [Insert your references here]
