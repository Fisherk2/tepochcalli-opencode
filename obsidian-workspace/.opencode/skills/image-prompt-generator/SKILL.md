---
name: image-prompt-generator
description: Craft and edit image-generation prompts for FLUX, Nano Banana, Qwen-Image-2.1, or any Replicate model. Use when creating text-to-image prompts, editing images with words, rendering text/typography, matching brand colors, compositing multi-reference scenes, validating Qwen payloads, or running an anti-slop quality gate on generated imagery.
---

# Image Prompt Generator

Skill for image prompt creation and editing across backends. One workflow,
backend-specific dialects. Default to natural descriptive prose, never keyword lists.

## When to Use / When NOT

| Use for | Do NOT use for |
|---|---|
| Writing text-to-image (T2I) prompts for any backend | Choosing a Replicate model ID or price (query the API live instead) |
| Editing images with words (I2I), outpainting, inpainting | Video generation parameters |
| Text/typography inside images, brand hex colors | Committing or deploying anything |
| Multi-reference compositing, character consistency | Running validation scripts unprompted (offline/CI only) |
| Anti-slop review of generated imagery | Auditing a full site (narrow to the generated surface) |

## Model Router

Pick the backend by intent, then apply its dialect. Never assume a model exists;
verify IDs against the provider API at run time.

| Intent | Backend | Dialect pointer |
|---|---|---|
| Fastest preview / rapid iteration | FLUX.2 [klein] (4B/9B, ≤4 refs) | Narrative prose, 40–70 words, front-loaded subject |
| Highest quality / hero image | FLUX.2 [max] (≤8–10 refs, grounding search) | Technical + descriptive, camera/lens/film specs |
| Balanced production work | FLUX.2 [pro] (≤8 refs, upsampling) | Balanced detail, template-friendly |
| Readable text / posters / signage | FLUX.2 [flex] (steps 30–50, guidance 4–7) | Quoted text + font/placement (see Typography) |
| Local / free / non-commercial dev | FLUX.2 [dev] | Same patterns as [pro] |
| Legacy inpainting only | FLUX.1 Fill | Describe the fill region, not the removal |
| Legacy context editing | FLUX.1 Kontext | Prefer FLUX.2 with references instead |
| Conversational / multi-turn photo edit | Nano Banana (Gemini 2.5 Flash Image) | 50–100 words, one change per turn |
| Long dense scene spec (400–500 words, JSON payload) | Qwen-Image-2.1 | Observer prose + `wh_ratio` / `ratio_follow` |
| Unknown / mixed fleet on Replicate | Model-agnostic | Transferable principles only (see below) |

Full matrices: [rules/model-selection-guide.md](rules/model-selection-guide.md),
[rules/flux2-models.md](rules/flux2-models.md), [rules/flux1-models.md](rules/flux1-models.md).

## Unified Prompt Formula

All backends share one skeleton; each backend tunes length and voice:

```text
[Subject + Attributes] + [Action/Pose] + [Style/Medium] + [Context/Setting]
+ [Lighting] + [Composition/Camera/Technical] + [Aspect handling]
```

| Rule | Why | Detail |
|---|---|---|
| Prose, not keywords | Models parse grammar, not tags | Full sentences; `woman standing in alley` beats `woman, alley, dusk` |
| Front-load the subject | Early tokens win | Most important element first; critical details never last |
| Specify lighting always | Biggest quality lever | Source + direction + quality + shadows (golden hour, softbox, rim, volumetric) |
| Name subjects directly | Pronouns confuse models | `the woman with short black hair`, never `she` |
| State materials, not nouns | Richer latent match | `brushed stainless steel`, not `steel`; `coarse linen`, not `cloth` |
| No quality boosters | Empty hype adds noise | Never `8K`, `masterpiece`, `award-winning`; describe optics instead |
| No negative prompts (FLUX/Qwen) | Unsupported; backfires | Describe the wanted alternative (see Negative Alternatives) |

Foundations: [rules/core-principles.md](rules/core-principles.md),
[rules/t2i-prompting.md](rules/t2i-prompting.md),
[references/cheat_sheet.md](references/cheat_sheet.md) (medium/style/material/spatial/lighting vocabulary).
Section ordering rationale: [rules/_sections.md](rules/_sections.md).

### Length & framing per backend

| Backend | Length | Framing |
|---|---|---|
| FLUX | 30–80 words (≤512 tokens) | Photographer/describer voice |
| Nano Banana | 50–100 words recommended; 10–20 quick, 100–200 max control | Shot-type template + aspect ratio in prompt |
| Qwen T2I | ~20 sentences, ~400–500 words, one paragraph | Observer voice, 20-word anchor opener, 8–14 positional anchors, lighting sentence, one-sentence composition close; ratio lives ONLY in `wh_ratio` |
| Replicate-agnostic | Long detailed prompts OK (thousands of tokens) but each added requirement risks a miss | Start simple, iterate; describe whole scene unless masked-region mode |

Qwen 8-step framework: [references/t2i_rules.md](references/t2i_rules.md).

## T2I / I2I / Editing / Multi-Reference

### T2I by genre (templates)

- **Portrait:** subject + age-as-stage (`in her thirties`, never a number) + garments with color/material + pose/gaze + lens (`85mm f/1.4`) + lighting setup.
- **Product:** exact materials + surface + 45° diffused studio light + camera angle for the hero feature + sharp-focus detail.
- **Landscape:** location + time + weather + foreground anchor + lens/vantage + composition rule + grading + mood.
- **Complex multi-element scene:** draft JSON first (`subjects[]` with IDs, `scene`, `composition.depth_layers`, `technical`), then flatten to flowing prose. See [rules/json-structured-prompting.md](rules/json-structured-prompting.md).

### I2I editing rules (all backends)

1. One change per turn; iterate instead of mega-edits.
2. Name what changes AND what stays (`maintaining exact composition`, `keeping pose and expression unchanged`).
3. Choose verbs precisely: `change/replace/add` for local edits; avoid `transform` unless a full rework is wanted.
4. For removals, describe what fills the exposed region.
5. For style transfer, name the exact style/movement and lock `keep the original composition`.
6. For text edits: `Change 'old text' to 'new text'`, match character count, preserve font unless told otherwise.
7. Perspective/angle changes are the hardest class; expect model variance, try another backend rather than fighting the prompt.

FLUX I2I detail (refs via URL, up to 4/8/10 by model): [rules/i2i-prompting.md](rules/i2i-prompting.md).

### Qwen edit protocol (attribute disentanglement)

- Edit named attributes at full unmistakable strength; hold everything else with a blanket preservation clause (name untargeted content by type/position/role, do not repaint its appearance).
- Identity (face, product markings, rendering medium) survives unless explicitly targeted.
- `N>=2` inputs: mandatory `<image1>`, `<image2>` tags; `N=1`: natural reference (`the image`), no tags.
- Output size is mutually exclusive: `wh_ratio` set XOR `ratio_follow: "<imageX>"`. Single edit with no stated size follows the canvas (`ratio_follow`); outpainting infers a new ratio from direction; no-canvas group scenes pick by semantics (group photo `3:2`, portrait/poster `2:3`, wallpaper `16:9`).
- Full language/size/JSON rules: [references/edit_rules.md](references/edit_rules.md).

### Multi-reference compositing

- Assign each image a role: `image 1 = identity`, `image 2 = pose`, `image 3 = style`, `image 4 = environment`.
- Reference by index (`the face from image 1, the outfit from image 2`) and state interactions explicitly.
- Enforce lighting consistency (`main light upper left across all elements`).
- Character consistency: point at the reference image rather than re-describing features; repeat exact descriptions across panels for storyboards (`2x2 grid`, `series`, per-panel specs).
- Watch total megapixels (refs + output) against the model limit.
- Detail: [rules/multi-reference-editing.md](rules/multi-reference-editing.md).

## Typography + Hex Colors

### Typography

| Rule | Practice |
|---|---|
| Quote exact text | `"SUMMER SALE 2025"` in straight double quotes, original script preserved |
| Specify font | serif / sans-serif / script / display / monospace + weight; reference a known cut (`bold condensed grotesque`) over `nice font` |
| Hierarchy + placement | Headline/subhead/body sizes; `centered in upper third`, `bottom right corner`; front-load text early in prompt |
| Keep it short | 1–4 words render best; Nano Banana ≤25 chars / 2–3 phrases; Qwen commits every quoted char, blurs unreadable microcopy instead of inventing letters |
| Contrast + size | Large simple type, high background contrast; FLUX [flex] for critical work |
| Troubleshooting | Misspelled → shorten, repeat exact string; missing → front-load + de-clutter prompt |

Detail: [rules/typography-text.md](rules/typography-text.md).

### Hex colors

- Syntax `#RRGGBB` always paired with a name: `#FF6B6B (coral pink)`; attach each color to its object (`the LEFT chair in #...`); 3–5 colors max.
- Gradients state start→end; harmonies by scheme (complementary / analogous / triadic / monochrome).
- If color drifts: fewer colors, explicit object binding, `maintaining exact color #XXXXXX`.
- Detail: [rules/hex-color-prompting.md](rules/hex-color-prompting.md).

## Negative-Prompt Alternatives + Anti-Slop Gate

### Negative alternatives (no-negative-prompt backends)

Invert each `no X` into the wanted state:

| Instead of | Write |
|---|---|
| no people / crowds | `deserted`, `solitary`, `empty`, `secluded` |
| no makeup / blemishes | `natural clear skin`, `fresh-faced`, `smooth complexion` |
| no glasses / hat | `visible eyes`, `clear gaze`, `bare head`, `visible hair` |
| no color / bright | `monochrome`, `muted earth tones`, `desaturated palette` |
| no text / watermark | `clean unmarked surfaces`, `pristine`, `unbranded` |
| not modern / CGI | `traditional`, `vintage`, `photorealistic`, `organic` |
| no blur / noise | `tack-sharp`, `crisp details`, `clean render` |
| not dark / no rain | `bright well-lit`, `clear blue sky`, `sunny` |
| no clutter | `minimal focused composition`, `isolated subject` |

Example: `Portrait of a woman, no glasses, no makeup` →
`Portrait of a woman with natural clear skin and visible bright eyes, fresh-faced with a healthy glow`.
Full table: [rules/negative-prompt-alternatives.md](rules/negative-prompt-alternatives.md).

### Anti-slop gate (run on every generated image)

Slop is a reflex choice, not a style. Flag a choice when several hold: pasteable into an
unrelated product unchanged; repeats a familiar generated pattern; conflicts with the local
system; communicates nothing; competes with content or weakens trust.

Compact gates before keeping any choice: **System** (uses local type/color/spacing
language?) · **Hierarchy** (primary content obvious without decorative labels?) ·
**Composition** (alignment/proximity/negative space intentional?) · **Typography**
(roles distinct, no forced display treatment?) · **Color/material** (every gradient/glow/glass
layer has a role?) · **Product truth** (imagery/copy/metrics honest, no invented proof?) ·
**Interaction** (needed states present?) · **Motion/access** (motion explains state, respects
reduced-motion?).

Removal test: name the suspect element → state its job → remove it mentally; if meaning
survives and clarity improves, delete it; else smallest correction in the existing system.
Never invent customers, metrics, testimonials, or screens. Report material removals and why.
Pattern library: [ARTICLE.md](ARTICLE.md); source list: [REFERENCES.md](REFERENCES.md).

## Backend Examples (one per backend)

**FLUX (pro, balanced):**

```text
A modern minimalist living room with floor-to-ceiling windows overlooking
a city skyline at dusk, clean white furniture with subtle textures, a single
statement plant in the corner, warm ambient lighting from hidden sources,
architectural photography style with clean lines and balanced composition.
```

**Nano Banana (multi-turn photo edit):**

```text
Professional corporate headshot of mid-30s woman with shoulder-length brown hair
in charcoal blazer, smiling warmly at camera against soft gray backdrop. Shot with
85mm f/2.0, studio three-point lighting defining facial features. 1:1 format.
```

Then iterate one change per turn (`Change background to modern office` →
`Add warmer lighting`). Aspect ratios: `1:1` social, `16:9` landscape, `9:16` story,
`4:5` portrait post. Visual reference: [assets/nano-banana.png](assets/nano-banana.png).

**Qwen-Image-2.1 (API mode, strict JSON only):**

```json
{"rewritten_prompt": "The image is a wide cinematic photograph of a cat sitting on a sunlit windowsill, rain streaking the glass behind it. The lighting is soft diffused daylight from the left. The overall composition feels tranquil and balanced.", "wh_ratio": "16:9"}
```

**Replicate-agnostic (edit with preservation):**

```text
Change the background to a tropical beach at sunset while keeping the person in
the exact same position; maintain identical subject placement, camera angle,
framing, and perspective. Only replace the environment around them.
```

## Scripts, Validation & Budgets

- `scripts/validate_prompt.py` ([scripts/validate_prompt.py](scripts/validate_prompt.py)) checks
  Qwen payloads: required fields, `wh_ratio` (`W:H`) vs `ratio_follow` (`<imageX>`) mutual
  exclusivity, single-paragraph (no `\n`), balanced straight quotes, no booster words
  (`8k`, `4k`, `masterpiece`, `award-winning`). Usage:
  `python scripts/validate_prompt.py '<json>'` or `python scripts/validate_prompt.py --test`.
  Offline/CI/regression use only — never run unprompted for standard interactive requests.
- Pre-submit checklist: subject + action + setting + lighting + mood + medium + size field;
  complete sentences; one consistent style; quoted text verified char-for-char.
- Budgets/latency: FLUX ≈ $0.014–0.10/image by model and megapixels (klein cheapest, max
  premium; verify at provider pricing page); Qwen targets standard 2K output, never infer
  ratio from `4K/8K` quality words; keep ref+output megapixels under the model cap; prefer
  FLUX.2 (24 concurrent) over Kontext Max (6) for throughput.

## Reference Index

| File | Covers |
|---|---|
| [references/cheat_sheet.md](references/cheat_sheet.md) | Medium/style/material/spatial/lighting vocabulary, `wh_ratio` matrix |
| [references/t2i_rules.md](references/t2i_rules.md) | Qwen T2I 8-step observer framework |
| [references/edit_rules.md](references/edit_rules.md) | Qwen edit disentanglement, language decisions, canvas/size rules |
| [rules/_sections.md](rules/_sections.md) | Section ordering and impact levels |
| [rules/core-principles.md](rules/core-principles.md) | Positive-only, formula, specificity, prose, lighting, front-loading |
| [rules/model-selection-guide.md](rules/model-selection-guide.md) | Decision matrix/tree, speed/quality/cost, use-case pipelines |
| [rules/flux2-models.md](rules/flux2-models.md) | klein/max/pro/flex/dev voices, reference-image editing |
| [rules/flux1-models.md](rules/flux1-models.md) | 1.1 pro, Kontext/Max, Fill (legacy guidance) |
| [rules/t2i-prompting.md](rules/t2i-prompting.md) | Subject types, lighting/camera/composition catalogs |
| [rules/i2i-prompting.md](rules/i2i-prompting.md) | Edit patterns, preservation, step-wise escalation |
| [rules/json-structured-prompting.md](rules/json-structured-prompting.md) | JSON scene templates, flatten-to-prose |
| [rules/hex-color-prompting.md](rules/hex-color-prompting.md) | Hex syntax, palettes, brand schemes, drift fixes |
| [rules/typography-text.md](rules/typography-text.md) | Quoting, fonts, hierarchy, effects, flex settings |
| [rules/multi-reference-editing.md](rules/multi-reference-editing.md) | Roles, indexing, consistency, blending fixes |
| [rules/negative-prompt-alternatives.md](rules/negative-prompt-alternatives.md) | Positive-rewrite tables |
| [scripts/validate_prompt.py](scripts/validate_prompt.py) | Qwen JSON validator + self-tests |
| [assets/nano-banana.png](assets/nano-banana.png) | Nano Banana visual reference |
| [agents/openai.yaml](agents/openai.yaml) | Agent metadata for this skill |
| [ARTICLE.md](ARTICLE.md) | Anti-slop pattern library |
| [REFERENCES.md](REFERENCES.md) | Anti-slop source list |
