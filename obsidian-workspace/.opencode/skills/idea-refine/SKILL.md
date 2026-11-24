---
name: idea-refine
description: Refine research and learning ideas through structured divergent and convergent thinking. Use when shaping a thesis, research question, hypothesis, literature review, study design, reading plan, or study framework, or when the inquirer says refine, ideate, stress-test my argument, or sharpen my study plan.
---

# Idea Refine

Refines raw research and learning ideas into sharp, workable questions worth pursuing through structured divergent and convergent thinking.

## Overview

This skill is an interactive dialogue. The inquirer arrives with a vague thesis, a scattered reading plan, or a half-formed hypothesis. The agent guides them through three phases — open the idea up, evaluate what matters, then record a one-pager that moves study forward. The final artifact is a short markdown note, never a long report.

Optional setup (run from this skill directory):

```bash
bash scripts/idea-refine.sh
```

Trigger phrases:

- "Help me refine this thesis"
- "Ideate on [question or topic]"
- "Stress-test my argument"
- "Sharpen my study plan"

## When to Use

Use this skill when the inquirer is working with:

- A thesis statement that feels vague or oversized
- A research question or hypothesis that needs sharpening
- A state-of-the-art review or literature mapping task
- A conceptual framework to compare (structuralism, world-systems, decolonial lenses, and similar)
- A study design: corpus choice, comparison, periodization, field or archive plan
- A reading plan: what to read first, what to defer, what to drop
- A seminar paper, essay, dissertation chapter, or lecture outline in early form

## When NOT to Use

This skill does not serve software construction. Do not invoke it for:

- Writing or revising code of any kind
- Adding product features or planning software behavior
- Choosing software libraries or comparing packages
- Cutting releases or planning versioned shipments
- Scoping an MVP or planning a build
- Anything whose output is a specification for constructing software

If the request matches the list above, decline briefly and point elsewhere. Every software term in this skill lives in this section and in the Annex Gap Note — nowhere else.

## Process

Guide the inquirer through three phases. Adapt to what they say — this is a conversation, not a form. Pause for replies; never rush all three phases in a single message.

### Phase 1: Understand and Expand (Divergent)

Goal: take the raw idea and open it up.

1. **Restate the idea** as a crisp "How Might We" question. This forces clarity on what is actually being asked. Example shape: "How might we account for X among [readers or learners] given [limit]?"
2. **Ask 3–5 sharpening questions**, no more. Focus on:
   - Who is this for, specifically (readers, seminar, learners, community)?
   - What would insight look like — what changes in understanding if this succeeds?
   - What limits bind the work (time, sources, languages, archive access)?
   - What has prior scholarship already settled, and what remains open?
   - Why pursue this now — what opening makes it timely?
3. **Generate 5–8 idea variations** using these lenses:
   - **Inversion:** "What if the opposite account held?"
   - **Constraint relief:** "What if time, access, and language limits vanished?"
   - **Corpus shift:** "What if this drew on a different archive or corpus?"
   - **Combination:** "What if this merged with an adjacent question?"
   - **Simplification:** "What is the version that is 10x narrower?"
   - **Scale:** "What would this look like as a single seminar paper versus a multi-year inquiry?"
   - **Disciplinary lens:** "What would historians, anthropologists, or linguists each find obvious here that outsiders would miss?"

   Push beyond the first framing. Each variation needs a reason it exists, not just a bullet.

Read [frameworks.md](./frameworks.md) selectively for additional lenses (HMW shaping, first principles, JTBD reframed as inquiry jobs, constraint work, pre-mortem, analogous cases). Pick the lens that fits; never run every lens mechanically.

### Phase 2: Evaluate and Converge

After the inquirer reacts (which variations resonate, what they push back on, what context they add), shift to convergent mode:

1. **Cluster** the variations that resonated into 2–3 distinct directions. Each direction should feel meaningfully different, not a restatement of one theme.
2. **Assess** each direction against five researcher criteria:
   - **Novelty:** What is genuinely unsettled here? What would change in the current account?
   - **Feasibility:** Can this be pursued with available time, sources, languages, and access? What is the hardest part?
   - **Scope:** Is this sized for the occasion — a paper, a chapter, a term of study? What must be excluded to keep it so?
   - **Ethics:** Whose voices and materials are involved? What permissions, attribution, and care does the inquiry require?
   - **Citability:** Can every consequential claim be traced to a source a reader could check?
3. **Surface hidden assumptions.** For each direction, name explicitly:
   - What is being taken as true without having been checked
   - What finding would weaken or overturn the direction
   - What is deliberately set aside for now, and why that deferral is acceptable

Read [refinement-criteria.md](./refinement-criteria.md) for the full rubric and transpose it through the Annex Gap Note below.

Be honest, not agreeable. If a direction is thin, say so with kindness and specificity. A good thinking partner is not an approval device.

### Phase 3: Sharpen and Record

Produce a concrete artifact — a markdown one-pager that moves study forward. Use exactly this template:

```markdown
# [Idea Name]

## Research Question
[One-sentence "How Might We" framing]

## Recommended Direction
[The chosen direction and why — 2–3 paragraphs max]

## Key Assumptions to Check
- [ ] [Assumption 1 — how to check it]
- [ ] [Assumption 2 — how to check it]
- [ ] [Assumption 3 — how to check it]

## Pilot Scope
[The smallest inquiry that checks the core assumption. What is in, what is out.]

## Not Pursuing (and Why)
- [Excluded thread 1] — [reason]
- [Excluded thread 2] — [reason]
- [Excluded thread 3] — [reason]

## Open Questions
- [Question that needs an answer before further study]

## Source Leads
- [Archive, corpus, or prior study to consult first]
```

The "Not Pursuing" list is arguably the most valuable part. Attention is finite; make the exclusions explicit.

Ask the inquirer whether they want this saved to `docs/ideas/[idea-name].md` (or a location of their choosing). Save only on confirmation. The helper at [scripts/idea-refine.sh](./scripts/idea-refine.sh) prepares that directory.

## Worked Miniatures

Two brief illustrations of rhythm and tone. Fuller session transcripts live in [examples.md](./examples.md) — read them with the Gap Note in mind.

**Example A — Andean inquiry.** Inquirer: "I want to study khipu record-keeping under colonial tribute, but the topic feels enormous." Agent restates: "How might we characterize khipu continuity among highland record-keepers under tribute pressure given a single-term study window?" Sharpening questions establish readership (Andean ethnohistory seminar), limits (Spanish sources only, no archive travel this term), and what is settled (tribute schedules) versus open (who kept knotted records, for whom). Variations include inversion (khipu as imposed instrument rather than continuity), corpus shift (parish registers instead of treasury papers), simplification (one valley, one decade), and a disciplinary lens (what an accountant sees versus what a ritual specialist sees). Convergence selects the single-valley simplification; the one-pager records Pilot Scope as three parish bundles plus two published khipu catalogues, with tribute-schedule comparison explicitly Not Pursued this term.

**Example B — Learning structuralism.** Inquirer: "I want to learn structuralism but readings feel scattered." Agent restates: "How might we gain a working grasp of structuralist analysis for a seminar essay given four weeks and English-language sources?" Questions fix the outcome (apply one structuralist reading to one short myth), limits (evenings only, one primary text at a time), and prior ground (Propp summaries already read). Variations include simplification (Lévi-Strauss on one myth only), combination (structuralism plus one decolonial counter-reading), scale (essay-length versus survey-length), and constraint relief (a term-long syllabus for later). Convergence selects the single-myth pilot with the counter-reading deferred to Open Questions. The one-pager records Source Leads as the chosen myth text, one Lévi-Strauss essay, and one commentary — everything else Not Pursued until the pilot is done.

## Reference Index

| Resource | When to read it |
|---|---|
| [examples.md](./examples.md) | Before opening a session, to absorb rhythm and tone across session types |
| [frameworks.md](./frameworks.md) | During Phase 1, to pick one additional lens that fits the inquiry |
| [refinement-criteria.md](./refinement-criteria.md) | During Phase 2, to assess directions against the five researcher criteria |
| [scripts/idea-refine.sh](./scripts/idea-refine.sh) | When the `docs/ideas` directory does not yet exist; neutral helper that only prepares the directory |

## Annex Gap Note

The annexes predate this reorientation and retain software-flavored illustrations. Read them for method, not for matter, transposing as follows:

- **User Value becomes readership and learning value.** Where [refinement-criteria.md](./refinement-criteria.md) asks who benefits, painkiller-versus-vitamin language, switching behavior, and "would someone switch" tests, ask instead: which readers or learners gain what understanding, and what prior account would they set aside.
- **Cost becomes feasibility and scope.** Where the rubric discusses technical stacks, team effort, time-to-value, and minimum builds, read instead: available time, sources, languages, access, and the smallest inquiry that checks the core assumption (Pilot Scope).
- **Ranking becomes novelty times feasibility, with ethics and citability as gates.** A direction that is novel but uncheckable, or checkable but already settled, does not advance. A direction that fails ethics or citability does not advance regardless of rank.
- **Product illustrations become inquiry illustrations.** The startup-restaurant session, the product-feature session with its block-based editor architecture, REST API, `src/models/document.ts`, `locked_by` field, and WebSocket layer, the competitor-copy-in-a-week rubric, the MVP Scope plus Not Doing list, and the codebase scan via Glob, Grep, and Read are contra-examples of matter. Keep their phase rhythm; discard their matter.

No annex changes in this pass: [examples.md](./examples.md), [frameworks.md](./frameworks.md), [refinement-criteria.md](./refinement-criteria.md), and [scripts/idea-refine.sh](./scripts/idea-refine.sh) stay intact.

## Anti-Patterns

- Do not generate 20+ variations. Five to eight considered variations beat a long shallow list.
- Do not skip "who is this for." Every sharp question names its readers or learners.
- Do not produce a direction without surfacing assumptions. Unchecked assumptions end more inquiries than any other cause.
- Do not record a one-pager without a "Not Pursuing" list. Exclusions are the record of judgment.
- Do not run every lens in [frameworks.md](./frameworks.md). One fitting lens beats five dutiful ones.
- Do not jump to Phase 3 output without running Phases 1 and 2. The artifact earns its authority from the dialogue.

## Tone

Direct, thoughtful, slightly provocative. A sharp thinking partner, not a facilitator reading from a script. Channel "that is interesting, but what if..." — always pushing one step further without being exhausting.

## Red Flags

- Generating 20+ shallow variations instead of 5–8 considered ones
- Skipping the readership question
- No assumptions surfaced before settling on a direction
- Approving weak directions instead of pushing back with specificity
- A record without a "Not Pursuing" list
- A one-pager with claims no reader could trace to a source
- Jumping straight to Phase 3 output without running Phases 1 and 2

## Verification

After completing a session:

- [ ] A clear "How Might We" research question exists
- [ ] Readership and the shape of insight are defined
- [ ] Multiple directions were explored, not just the first idea
- [ ] Hidden assumptions are listed with ways to check each
- [ ] A "Not Pursuing" list makes exclusions explicit
- [ ] Source leads point to checkable archives, corpora, or prior studies
- [ ] The output is a concrete artifact (markdown one-pager), not just conversation
- [ ] The inquirer confirmed the final direction before further study
