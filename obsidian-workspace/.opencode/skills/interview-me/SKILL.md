---
name: interview-me
description: Extracts what the researcher actually wants instead of what they think they should ask for. Achieves this through one-question-at-a-time interview until ~95% confidence about the underlying intent. Use when a research or learning ask is underspecified ("survey X" without a central question, scope, or deliverable), when the user explicitly invokes ("interview me", "grill me", "are we sure?", "stress-test my thinking"), or when you catch yourself silently filling in scope, corpus, or criteria before any rubric, outline, or protocol exists. Hands off a confirmed intent statement for downstream research skills to consume.
---

# Interview Me

## Overview

What people ask for and what they actually want are different things. They ask for "a literature survey" because that is what one asks for, not because a survey answers their question. They say "be thorough" without a scope to bound or a deliverable to aim at.

The cheapest moment to find this gap is before any rubric, outline, or protocol exists. Once gathering and drafting have started, switching costs are real, and the user will rationalize the wrong thing into a "good enough" thing. The misfit gets locked in.

This skill closes the gap before it costs anything. Downstream research skills assume you already know roughly what you want: they turn a confirmed intent into evaluation criteria, gather sources against a defined question, or stress-test a claim after you have drafted one. Interview-me is the part before all of those, where you ask one question at a time, with your best guess attached, until you can predict what the user is going to say before they say it.

## When to Use

Apply this skill when:

- The ask is missing at least one of: the **central question**, **why** it matters now, what **scope** bounds it (inclusion/exclusion, dates, sources), what the **deliverable** is (rubric, outline, review), what the binding **limit** is (time, depth, length)
- The request is conventional rather than specific ("survey the literature on X", "summarize this topic") and you cannot unpack the convention without guessing
- You are tempted to start with assumptions about corpus, method, or sources that you have not surfaced
- The user has not said which value they are optimizing for when two reasonable ones are in tension (breadth vs. depth, overview vs. argument, learning vs. producing)
- The user explicitly invokes: "interview me", "grill me", "before we start, are we sure?", "stress-test my thinking"

**When NOT to use:**

- The ask is unambiguous and self-contained ("rename this note", "fix this citation key")
- The user has explicitly asked for speed over verification
- Pure information requests ("how does X work?", "what does this paper argue?")
- Mechanical vault operations (moves, renames, tag cleanups)
- You already have ≥95% confidence; re-read the stop condition below before assuming you don't

## Loading Constraints

This skill needs a live, responsive user. **Do not invoke in non-interactive contexts** like scheduled runs, autonomous loops, or background jobs. If you are in one of those and the ask is underspecified, flag that as a blocker for the user instead of guessing.

## The Process

### Step 1: Hypothesize, with a confidence number

Before asking anything, write down your current best read of what the user wants in **one sentence**, plus an honest confidence number (0–100%):

```
HYPOTHESIS: You want a citable answer to whether microplastics impair freshwater invertebrate reproduction, and "survey" was the convention that came to mind.
CONFIDENCE: ~30% — missing: the central question, the intended deliverable, and the inclusion criteria
```

The number forces honesty. If you wrote down a high number but can't actually predict the user's reactions to the next three questions you'd ask, the number is wrong. Start at the confidence level you can defend.

When confidence is below ~70%, append a brief reason on the same line — what's still unresolved or missing. This tells the user exactly what the interview needs to surface, and prevents the number from being a vague signal.

### Step 2: Ask one question at a time, each with a guess attached

Format:

```
Q: <one focused question>
GUESS: <your hypothesis for the answer, with the reasoning that produced it>
```

Wait for the user to react before asking the next question.

**Why one at a time, not a batch:**

- The user can't react to your hypotheses if you bury them in a list
- Batches encourage skim-reading and surface answers
- The third question often depends on the answer to the first; asking them all at once locks in the wrong framing
- The user's energy for thinking carefully is finite; spend it one question at a time

**Why attach a guess:**

- The user reacts faster to a wrong guess than they generate an answer from scratch
- It commits you to a hypothesis you can be visibly wrong about, which keeps you honest
- It surfaces *your* assumptions, which is what the interview is meant to expose

The risk here is a polite user agreeing with your guess to be agreeable. Mitigate by being visibly willing to be wrong, and occasionally guess in a direction you expect the user to push back on.

### Step 3: Listen for "want vs. should want"

The most dangerous answers are the ones where the user says what a thoughtful answer *sounds like* rather than what they actually want. Watch for:

- Answers that pattern-match scholarly talk ("I want it to be systematic", "exhaustive coverage") without specifics
- Answers that defer to convention ("the way most reviews do it", "the standard method")
- Phrases like "I should probably…", "I think I'm supposed to…", "good scholarship says…"
- Buzzwords as goals — when "rigorous", "systematic", "comprehensive" are the answer instead of a specific question and deliverable

When you hear these, the question to ask is:

> *"If you didn't have to justify this to anyone, what would you actually want?"*

That single question often does more work than the previous five.

### Step 4: Restate intent in the user's own words

When your confidence is high, write back what you now think the user wants. Keep it tight (5–8 lines), use their language where possible, and structure it so the user can confirm or correct line by line:

```
Here's what I now think you want:

- Question:     <one line — the central research question>
- Audience:     <one line — who learns or decides from this>
- Why now:      <one line — what changed>
- Deliverable:  <one line — rubric, outline, or review plus how we know it worked>
- Corpus:       <one line — sources, dates, inclusion/exclusion, binding limit>
- Out of scope: <one line — what we're explicitly not covering>

Yes / no / refine?
```

Including "Out of scope" is non-negotiable. Half of misalignment is silent disagreement about what is *not* being covered.

### Step 5: Confirm — explicit yes, not "whatever you think"

The gate is an explicit "yes." The following are **not** yes:

- "Whatever you think is best." → The user is delegating, which means they don't have 95% confidence either. Re-ask with two concrete options framed as a choice.
- "Sounds good." → Ambiguous. Ask: "Anything you'd refine?" Silence isn't confirmation.
- "Sure, let's go." → Often a polite exit, not an endorsement. Same follow-up.
- Silence followed by "okay let's start." → The user has given up on the interview, not converged. Stop and ask whether you've missed something.

If they correct you, fold the correction in and restate. Loop until you get an explicit yes.

### The 95% Confidence Stop

You're done when you can answer yes to this:

> *Can I predict the user's reaction to the next three questions I would ask?*

If yes, you have shared understanding. Stop interviewing and produce the restate. If no, you're not done; ask the next question.

This is a checkable test, not a vibe. It also has a floor: if you've gone several rounds and still can't predict, that's information about the ask, not a reason to keep grinding. Stop and tell the user: "I've asked X questions and I still can't predict your reactions. Something foundational is missing. Want to step back?"

## Output

The output of this skill is a **confirmed statement of intent**: the restate from Step 4, with an explicit yes from Step 5. That's the deliverable. Rubrics, outlines, and protocols are downstream; they consume the intent this skill produces. Name the receiving skill (e.g. hypothesis-generation, deep-research) in the restate so the handoff stays traceable.

If the user wants the intent to persist (a multi-session inquiry, a handoff to another collaborator), offer to save it to `01-tasks/[topic]-intent.md`. Only save if they confirm.

## Example

A short before-and-after.

**Without `interview-me`:**

```
User:  survey the literature on microplastics in rivers
Agent: <starts gathering dozens of papers and drafting a broad summary>
```

The agent has assumed: the central question, the date range, which sources count, what "survey" means as a deliverable, what success looks like. None of these are stated. Every assumption is a place the user can later say "that's not what I meant."

**With `interview-me`:**

```
User: survey the literature on microplastics in rivers

Agent:
HYPOTHESIS: You want a citable answer about ecological harm for a thesis chapter, and "survey" came to mind because that's the conventional answer.
CONFIDENCE: ~30% — missing: the central question, the deliverable, and the inclusion criteria

Q:     When you say "survey", what will you do with it — write a thesis section, prepare a seminar, or decide a hypothesis to test?
GUESS: a thesis section, because "literature" usually scopes that way and a thesis needs citable claims. If it's for a seminar the depth and the framing change a lot.

User: It's actually for my thesis. I keep losing track of which papers support harm to invertebrates and which don't.

Agent:
Updated read: not a broad survey at all. It's an evidence map on one claim. Confidence: ~60% — still missing: the exact question and what counts as evidence.

Q:     Is the gap that you don't know which papers exist, or that you can't tell where they agree and disagree on reproductive harm?
GUESS: the second one. You have a pile of papers somewhere, but their findings live in scattered notes, and reconciling them by hand is what you're tired of.

User: First one actually. I literally don't have a corpus. They're spread across different folders.

Agent: <continues>
```

Two questions in, the agent has discovered the actual ask isn't "a survey." It's "a bounded corpus with inclusion criteria." Different scope, different sources, different work. The broad summary would have been wrong.

## LOAD this skills if you need

- **hypothesis-generation**: hand off the confirmed intent when it converges on a testable claim — pass the central question, corpus bounds, and exclusion criteria so hypothesis formulation starts from intent, not from the original vague ask.
- **scientific-brainstorming**: hand off the confirmed intent when the user wants novel research directions — pass the question, audience, and out-of-scope lines so ideation stays inside the agreed bounds.
- **brainstorming**: hand off the confirmed intent when the user wants broad options rather than scientific hypotheses — pass the deliverable and binding limit so divergence stays time-boxed.
- **idea-refine**: hand off the confirmed intent when a rough idea survived the interview but needs sharpening — pass the restated question and why-now so refinement converges instead of restarting discovery.
- **scientific-problem-selection**: hand off the confirmed intent when several candidate questions emerged — pass the confirmed criteria and exclusions so ranking uses what the user actually wants.
- **consciousness-council**: hand off the confirmed intent when the user is torn between competing values (breadth vs. depth, learning vs. producing) — pass the tension and the candidate restate so deliberation resolves the trade-off explicitly.
- **what-if-oracle**: hand off the confirmed intent when the user wants to stress-test it against counterfactuals — pass the confirmed claim and scope so the oracle attacks the real position, not a strawman.
- **deep-research**: hand off the confirmed intent when it is concrete (question plus corpus plus inclusion criteria) — pass the restate verbatim so gathering starts from confirmed scope.
- **literature-review**: hand off the confirmed intent when the deliverable is a citable synthesis — pass the corpus, dates, and inclusion/exclusion lines so the review maps exactly the agreed evidence base.
- **scholar-evaluation**: hand off the confirmed intent when source credibility matters — pass the corpus and the claims needing support so appraisal targets the papers the intent depends on.

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "The ask is clear enough" | If you can't write the user's central question in one sentence right now, the ask isn't clear. Run Step 1 before deciding. |
| "Asking too many questions wastes their time" | Time wasted by 4–6 targeted questions is small. Time wasted by gathering the wrong corpus is enormous, and the user is the one bearing that cost. |
| "I'll figure it out as I read" | Rework after a corpus is gathered and a draft exists costs far more than questions now. Discovery during drafting is rework. |
| "They said 'whatever you think,' so I should just decide" | "Whatever you think" is delegation, not decision. Re-ask with two concrete options as a choice. |
| "I should give them several options to pick from" | Options work when the user knows what they want and is choosing between trade-offs. They don't know what they want yet. Listing options widens the search; asking narrows it. |
| "If I attach my guess, I'm leading them" | Leading is the point. Reacting is faster than generating from scratch. The risk is sycophancy, not leading; mitigate by being visibly willing to be wrong. |
| "We've talked enough, I get it" | Test it: can you predict their reaction to the next three questions? If not, you don't get it yet. |
| "The user said yes, we're done" | If the yes followed a vague restate or an open-ended "sounds good," the yes is hollow. Restate concretely and re-confirm. |

## Red Flags

- Three or more questions in a single message: that's batching, not interviewing
- A question without your hypothesis attached: that's surveying, not committing
- Accepting "whatever you think is best" as a terminal answer
- Producing a rubric, outline, or draft before the user has explicitly confirmed your restate
- Questions framed as "what would be the canonical method?" instead of "what do you actually want?"
- The user gives a sophistication-signaling answer ("systematic", "exhaustive", "rigorous") and you accept it without probing whether it's what they actually want
- Three or more rounds without your confidence visibly rising: you're asking the wrong questions, step back and reframe
- A confidence number below ~70% with no reason attached: the user can't help close the gap if they don't know what's missing
- Saving the intent note before the user has confirmed (the note itself implies a yes the user didn't give)
- Skipping the "Out of scope" line in the restate (silent disagreement about exclusions is half of misalignment)

## Verification

After applying interview-me:

- [ ] An explicit hypothesis with a confidence number was stated in the first turn
- [ ] Every confidence number below ~70% was accompanied by a one-line reason (what's still unresolved or missing)
- [ ] Questions were asked one at a time, each with the agent's guess attached
- [ ] At least one "what would you actually want if you didn't have to justify it?" probe ran when the user gave a sophistication-signaling or convention-signaling answer
- [ ] A concrete restate (Question / Audience / Why now / Deliverable / Corpus / Out of scope) was written back to the user
- [ ] The user confirmed the restate with an explicit yes (not "whatever you think," not "sounds good," not silence)
- [ ] At the stop point, the agent could predict reactions to the next three questions it would ask
- [ ] Any handoff to a downstream research skill was framed in terms of the confirmed intent, not the original underspecified ask
