---
name: planning-and-task-breakdown
description: "Turn a research or learning goal into an ordered, traceable work plan. Use when the user faces a thesis, literature review, state of the art, research design, reading plan, synthesis, or fieldwork preparation that feels too large to start. Use when dependencies between questions, sources, and drafts are unclear, when scope must be estimated, or when work can be split across sessions."
---

# Planning and Task Breakdown

## Overview

Turn a vague research question into a traceable plan: every task answers one
question, names its materials, and states how you will know it is done.
The reader is a researcher or student, not an engineer. The output is a plan
document, never the research itself. Each task must be small enough to complete
in one focused session and leave behind an inspectable artefact (a note, a
matrix row, a memo, a draft section).

A good plan answers, in order: what is the guiding question, what corpus will
settle it, through which lens, in what order, at what cost, and how each step
is checked.

## When to Use

- Scoping a thesis, dissertation chapter, article, or essay
- Preparing a state of the art or literature review
- Designing a study: question, corpus, method, and validation
- Building a reading plan over weeks with limited hours
- Sequencing a synthesis from fiches to draft
- Preparing fieldwork, archival visits, or interviews
- Splitting a large investigation across sessions or collaborators

## When NOT to Use

Single-question lookups with obvious scope, or a plan that already has
well-defined tasks. This skill does not cover software work: not for coding,
features, releases, sprints, pull requests, or deploys. If the request is to
build software, stop and use an engineering planning skill instead.

## Process

### Phase 1 — Scope the Investigation

Before writing any task, work read-only: read the question and the available
materials, do not start researching yet.

Fix four elements in writing:

1. **Guiding question** — one sentence, falsifiable. If it contains "and",
   it is two questions; split it.
2. **Corpus** — what sources count (archives, journals, books, interviews,
   datasets) and what is explicitly excluded, with a date or boundary.
3. **Lens** — the theoretical or methodological frame (e.g., social history,
   institutional economics, close reading). Name it so later choices stay
   consistent.
4. **Risks and unknowns** — inaccessible sources, language gaps, contested
   concepts, time limits. Note them now; they drive the critical path.

Output of this phase: one paragraph each for question, corpus, lens, risks.

### Phase 2 — Map the Dependency Graph

Research has a natural order: later work consumes earlier artefacts.

```
guiding question
    │
    ├── corpus delimitation
    │       │
    │       ├── source search
    │       │       │
    │       │       ├── fiches / reading notes
    │       │       │       │
    │       │       │       ├── comparison matrix
    │       │       │       │       │
    │       │       │       │       ├── pilot memo (one page)
    │       │       │       │       │       │
    │       │       │       │       │       └── draft section
```

Order tasks along this chain: nothing that consumes an artefact comes before
the task that produces it. Delimit the corpus before searching; fiche before
comparing; compare before drafting. A task that needs no prior artefact can
run in parallel; everything else is sequential.

### Phase 3 — Slice Into Complete Arcs

Slice by research question, not by activity layer. Each task must close one
small arc: question asked, materials consulted, artefact produced.

**Bad (slicing by layer):**

```
Task 1: Read everything about the topic
Task 2: Take all notes
Task 3: Compare all authors
Task 4: Write it all up
```

Each task is unbounded, produces nothing checkable, and blocks everything.

**Good (slicing by question):**

```
Task 1: Settle how the 1870 press law changed provincial printing —
        corpus list + 3 fiches + one-paragraph finding
Task 2: Settle whether rotary presses reached the provinces before 1880 —
        catalogue check + 2 fiches + one-paragraph finding
Task 3: Draft the 800-word section combining Tasks 1-2 with citations
```

Each arc is independently verifiable and leaves the plan in a usable state
even if later tasks stall.

### Phase 4 — Write Tasks

Use the Task Van template for every task:

```markdown
## Task [N]: [Question this task settles]

**Settles:** One sentence — the question answered, not the activity done.

**Completion criteria:**
- [ ] [Observable condition, e.g., "3 fiches filed with full citations"]
- [ ] [Observable condition, e.g., "finding paragraph states a claim + evidence"]

**Check (reread + traceability):**
- [ ] Reread the finding aloud; claim follows from the cited fiches
- [ ] Every claim traces to a source note with page or location

**Depends on:** [Task numbers, or "None"]

**Materials:** [Exact sources, archives, call numbers, or search bounds]

**Effort:** [XS: <1h | S: 1-2h | M: half day | L: 1-2 days | XL: too large, split]
```

Rules:

- One question per task. "And" in the Settles line means two tasks.
- Completion criteria are artefacts (fiches, rows, memos, words drafted),
  never feelings ("understand", "explore", "look into").
- Materials must be concrete enough that a fresh session could start cold.
- Effort L or larger gets split before the plan is approved.
- If acceptance needs more than 3 bullets, the task is two tasks.

### Phase 5 — Critical Path and Checkpoints

Arrange tasks so that:

1. Dependencies are satisfied (corpus before search, fiches before matrix).
2. Each task leaves an artefact a later session can pick up.
3. High-risk tasks come early: the hardest archive, the contested concept,
   the source that may not exist. Fail fast, replan cheap.
4. Checkpoints fall after every 2-3 tasks.

Checkpoint template:

```markdown
## Checkpoint: After Tasks 1-3
- [ ] Every fiche has a full citation (author, year, pages, location)
- [ ] Matrix rows cite their fiches; no orphan claims
- [ ] Pilot memo still answers the guiding question, or the question is revised
- [ ] Review with human before proceeding
```

A checkpoint may revise the guiding question. That is normal: record the old
question, the reason for change, and the new question in one line each.

### Phase 6 — Estimate and Parallelize

Estimate by cognitive load and access cost, not file counts:

| Effort | Meaning | Example |
|--------|---------|---------|
| **XS** | <1 hour, sources at hand | Fiche one short article |
| **S** | 1-2 hours, one sitting | Fiche a chapter; draft 400 words from ready notes |
| **M** | Half day, moderate synthesis | Assemble a 5-author comparison matrix |
| **L** | 1-2 days, heavy synthesis or travel | Archival morning + fiches; draft a full section |
| **XL** | Unbounded — split before approving | "Review the literature" |

Parallelization rules:

- **Safe to parallelize:** independent fiches on different sources, independent
  matrix rows, proofreading finished sections.
- **Must be sequential:** anything consuming another task's artefact (matrix
  needs fiches; draft needs matrix; conclusions need the draft).
- **Needs coordination:** shared corpus boundaries or shared citation format —
  freeze those first, then split the work.

## Research Task Types

| Type | Produces | Done when |
|------|----------|-----------|
| **Corpus delimitation** | Inclusion/exclusion list with bounds | Bounds written; exclusions justified in one line each |
| **Source search** | Located items with call numbers or links | Each item retrievable by a stranger |
| **Fiche / reading note** | One note per source: claim + evidence + citation | Reread passes; pages recorded |
| **Comparison matrix** | Authors × positions table | Every cell cites a fiche |
| **Pilot memo** | One-page argument sketch | Guiding question answered in miniature with citations |
| **Draft section** | Continuous prose with citations | Word target met; every paragraph traceable |

## Plan Document Template

```markdown
# Research Plan: [Topic]

## Guiding question
[One falsifiable sentence]

## Corpus
[What counts, what is excluded, date/boundary]

## Lens
[Theoretical or methodological frame in one line]

## Novelty – Feasibility – Scope – Ethics – Citability
- Novelty: [What this adds beyond existing work]
- Feasibility: [Access, languages, hours available]
- Scope: [What is deliberately left out]
- Ethics: [Consent, sensitive material, archival rules]
- Citability: [Citation style + where full references live]

## Tasks
- [ ] Task 1: ...
- [ ] Task 2: ...

## Checkpoint: After Tasks 1-3
- [ ] Fiches cited, matrix traceable, question still holds

## Risks
| Risk | Impact | Mitigation |
|------|--------|------------|
| [e.g., archive closed] | [High/Med/Low] | [Fallback source or narrowed question] |

## Open Questions
- [Question needing human input]
```

## Definition of Done

A research plan is done when:

- Every task settles exactly one question with named materials
- Every task has completion criteria stated as artefacts, not activities
- Every claim path is traceable: draft → matrix → fiche → source location
- Checkpoints exist every 2-3 tasks with a reread step
- The human has reviewed scope, risks, and the guiding question

## Example A — State of the Art (19th-Century Press)

```markdown
## Task 1: Settle the legal frame of provincial printing after 1870

**Settles:** How the 1870 press law changed what provincial printers could publish.

**Completion criteria:**
- [ ] Corpus bounds filed (imprints 1870-1880, 2 provinces, exclusions noted)
- [ ] 3 fiches with article numbers and page citations
- [ ] One-paragraph finding stating the change with evidence

**Check (reread + traceability):**
- [ ] Finding reread aloud; claim follows from fiches
- [ ] Each legal claim traces to article + page

**Depends on:** None
**Materials:** Press law text; provincial imprint catalogue 1870-1880
**Effort:** S
```

## Example B — Three-Week Microeconomics Reading Plan

```markdown
## Task 2: Settle how the course frames elasticity vs. the textbook

**Settles:** Where lecture notes diverge from the textbook on price elasticity.

**Completion criteria:**
- [ ] 2 fiches (lecture notes week 3; textbook chapter 4) with page citations
- [ ] Matrix row comparing definitions, assumptions, examples
- [ ] One-paragraph finding naming the divergence

**Check (reread + traceability):**
- [ ] Finding reread aloud; divergence stated precisely
- [ ] Each cell traces to a fiche with pages

**Depends on:** Task 1 (corpus bounds)
**Materials:** Lecture notes week 3; textbook ch. 4, pp. 88-112
**Effort:** S
```

## Anti-Patterns

| Anti-pattern | Why it hurts | Do instead |
|---|---|---|
| "Read everything, then write" | Unbounded task with no artefact for weeks | Slice by question; fiche per source per task |
| Tasks as activities ("explore X") | No way to know when done | State the question settled + artefact produced |
| Drafting before fiches exist | Claims without traceable evidence | Fiche first; matrix second; draft third |
| Skipping the checkpoint reread | Errors compound into the draft | Reread every 2-3 tasks; revise the question openly |
| One giant literature task (XL) | Blocks the whole plan; hides dependencies | Split until each task fits one session |

## Tone

Direct, scholarly, economical. Name the question, the materials, and the check;
then stop. Prefer concrete nouns (archive, page, author, year) over abstract
ones (thoroughness, depth, understanding). When scope must shrink, say what is
cut and why in one line.

## Verification

Before starting the research, confirm:

- [ ] A single guiding question is written and falsifiable
- [ ] Corpus bounds and exclusions are explicit
- [ ] Every task settles one question with named materials
- [ ] Every task has artefact-based completion criteria
- [ ] Traceability holds: draft → matrix → fiche → source
- [ ] Checkpoints with reread exist every 2-3 tasks
- [ ] The human has reviewed and approved the plan
