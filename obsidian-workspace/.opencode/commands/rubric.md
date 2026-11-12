---
description: "Build the research rubric: central question, objectives, scope, source criteria."
agent: nezahualcoyotl
---

## Phase 0: Clarify Intent

1. **Load** the `interview-me` skill to extract user's request, histories, key goals and non-goals (what they want to avoid), preferences, and constraints.
2. **Load** `brainstorming` or `scientific-brainstorming` skill in case of user don't know what they want and need to explore options.
3. Use the `question` tool to clarify the user's intent and goals.

## Phase 1: Refine user definitions

**Load** `idea-refine` skill to generate and evaluate options for the central question, objectives, scope, and source criteria. If the brainstorming yields several candidate questions or the question stays vague, **Load** `scientific-problem-selection` skill to turn intuition into one central question with risks and success metrics (problem-framing/decision-tree modules only).

Use the `question` tool to clarify interactively this new options, refine objectives, scope, inclusion/exclusion criteria for sources, and the method to apply:

1. **Objective and target users** — what does success look like? Who is this for?
2. **Core goals and acceptance criteria** — must-have vs nice-to-have?
3. **Preferences and constraints** — any existing commitments?
4. **Boundaries** — what to always do, ask first about, and never do

**Always use the `question` tool to let the user confirm what goals or constraints they needs include in the research — never decide automatically, even if the specifications or user instructions seem clear or trivial.** The user must answer doubts, suggestions, and ambiguities before proceeding.

## Phase 2: Definition

**Load** `planning-and-task-breakdown` skill.

1. Enter plan mode — read only, no file changes
2. Write ONE rubric note in `01-tasks/rubric.md` with frontmatter `{command, agent, date}`.
3. Write tasks with acceptance criteria and verification steps. **Load** `obsidian-markdown` + `obsidian-vault` skills for valid frontmatter, wikilinks and no broken links (format, not content). **Load** `markdown-mermaid-writing` skill to draw diagrams.
4. Suggest what subagents should invoke the main agent to complete each task, analyze and asign the most appropriate subagents and write them to `01-tasks/` files, can be multiple subagents per task (parallel/sequential) or none, you must explain what tasks should be delegate in parallel or sequentially (only if it's multiple subagents per task) and if it's a sequential delegation, you must explain the order of the subagents delegation. You should use **ONLY** subagents, **NOT** main agents, the available subagents are:

!`for f in agents/*.md; do printf '%s :: %.90s\n' "$(basename "$f" .md)" "$(sed -n '/^---$/,/^---$/p' "$f" | grep -m1 '^description: ' | sed 's/^description: //; s/^"//; s/"$//')"; done`

5. Scan and suggest what skills should load the subagents (or main builder if applicable) to complete each task, analyze and asign the most appropriate skills and write them to `01-tasks/` files, can be multiple skills per task or none.
6. Detect and scan MCPs/Plugins configured in this workspace, and suggest what tools should use the subagents (or main agent if applicable) to complete each task, analyze and asign the most appropriate tools and write them to `01-tasks/` files, can be multiple tools per task or none, the asignment of subagents, skills and tools to each task should be in a table format.
7. Add checkpoints between phases within `01-tasks/rubric.md` and `01-tasks/todo.md` — quality gates that must pass before moving to the next phase; when drafting each quality gate, **Load** `what-if-oracle` skill for one adverse scenario + decision trigger per gate (the stress-test planning does not do).
8. Present a brief summary of the plan for human review before saving.
9. **Research planification is done — do NOT touch or write anything. Only plan and write to `01-tasks/` files.**
10. Use the `question` tool to confirm plan with the user before saving to `01-tasks/plan.md` and `01-tasks/todo.md`
11. Commit all changes with a descriptive message (only if you have git installed in the vault, if not, skip this step).

## Rules

- Never write outside `01-tasks/`, you only write rubrics and tasks.
- Anchor corpus claims only as `source_path » heading (chars x–y)`, using fields that `search` returned.
- Any `E_*` from `tepochcalli-rag`: call `rag_status()` and report its `fix_hint` — never the raw error.
Doubt about intent or arguments: `question`.
- If `01-tasks/`, `01-tasks/rubric.md` and/or `01-tasks/todo.md` does not exist, create it.

## Suggested Next Step
> Rubric saved. Run `/research` to start the research process.

---