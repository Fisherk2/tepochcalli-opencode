---
name: posters-generator
description: "Create academic research posters (conference, presentation, print). Use when the user asks for a research poster, conference poster, scientific poster, paper-to-poster adaptation, poster compilation/preflight, or poster QC. Covers two routes: LaTeX (beamerposter, tikzposter, baposter — default for academic venues, best typographic control) merged from latex-posters, and manifest-driven PPTX/HTML (one-slide macro-free .pptx with layout/palette/security checks) merged from pptx-posters. Trigger on poster size, layout, figure, typography, QR, manifest, or print-proof questions. Do NOT trigger for slide decks, papers, or figures alone — those belong to their own skills."
allowed-tools: Read Write Edit Bash
license: MIT
compatibility: LaTeX route needs a TeX Live-class distribution plus Poppler for checks; baposter needs a separately supplied class file. PPTX route pins python-pptx 1.0.2, Pillow 12.3.0, lxml 6.1.3 (see assets/generation_dependencies.json). Optional AI schematics need Python 3.10+, requests, network, and OPENROUTER_API_KEY.
metadata:
  version: "1.0"
  last-reviewed: "2026-11-05"
  skill-author: Tepochcalli consolidation
---

# Posters Generator

## Overview

One entry point for research posters. Pick the route first, then follow it; shared design/content rules and QC apply to both. Origin skills `latex-posters` (LaTeX path) and `pptx-posters` (HTML/PPTX path, now manifest-driven) are retired.

## When to Use

- You are asked for a research, conference, or scientific poster, a paper-to-poster adaptation, or poster compilation/preflight/QC.
- You need poster sizing, multi-column layout, figure integration, typography, QR codes, manifest authoring, or print proofing.

## When Not to Use

- Slide decks, full papers, or standalone figures without a poster request — use the slides, writing, or plotting skills instead.
- Journal-figure export alone without poster layout — use the data-plotting skill.

## Capabilities

- LaTeX route (default): beamerposter, tikzposter, and baposter templates with two-pass pdfLaTeX compile and Poppler-based preflight.
- PPTX route (explicit request only): manifest-driven macro-free one-slide `.pptx` generation plus layout, palette, image-inventory, package-audit, and export-plan checks; optional HTML preview and deterministic/AI schematics.
- Shared: content budgeting, accessible design, placeholder replacement, and venue/printer proofing for both routes.

## Route Selection

| Request | Route |
| --- | --- |
| "poster" / "research poster" / "conference poster" with no format, or LaTeX / beamerposter / tikzposter / baposter mentioned | LaTeX (default) |
| Explicit "PPTX poster" / "PowerPoint poster", editable-in-PowerPoint, or HTML-based poster | PPTX (manifest-driven generator) |

## Shared Rules (Both Routes)

- Budget 300-800 words, 3-5 figures, 1-3 core messages; max 5-6 sections, 50-100 words each. See `references/latex-poster_content_guide.md` and `references/pptx-poster_content_guide.md`.
- Numbers come from verified analysis outputs and original research images — never AI-invented charts, microscopy, or spectra. AI visuals are optional conceptual illustrations only; no AI-image quota. See `references/ai_graphics_for_posters.md`.
- Design: 2-3 column grid, generous whitespace, reading-order flow; contrast and redundant color encoding; body text readable at full-size viewing distance (LaTeX starting range 24-36 pt; PPTX text must survive 25%-scale proof). Details in `references/latex-poster_design_principles.md`, `references/pptx-poster_design_principles.md`, `references/latex-poster_layout_design.md`, `references/pptx-poster_layout_design.md`.
- Accessibility: no color-only encoding, real reading order, alt text, accessible summary when digital access is required. See `references/poster_patterns_and_presentation.md`.
- Replace every placeholder, example citation, contact, QR target, and logo before delivery; real figure dimensions change layout, so recompile and re-inspect.

## Route A — LaTeX (Default)

| Package | Use when | Reviewed target |
| --- | --- | --- |
| beamerposter | Beamer blocks or institutional Beamer themes fit | CTAN 1.13 |
| tikzposter | TikZ styling and auto-stacked blocks help | CTAN 2.0 |
| baposter | A supplied project uses its named boxes | Archived class v2.0 (2011/11/26); upstream unavailable at review |

Templates (all compile under pdfLaTeX TeX Live 2025; missing figures render as draft placeholders): `assets/beamerposter_template.tex`, `assets/tikzposter_template.tex`, `assets/baposter_template.tex`. Copy one into the project, never edit in place. Package keys, themes, and install limits: `references/latex_poster_packages.md`; sizes/figures/typography/QR: `references/latex_poster_reference.md`.

Compile and inspect from the project directory (see `references/compilation_and_quality_control.md`):

```bash
pdflatex -interaction=nonstopmode -halt-on-error poster.tex
pdflatex -interaction=nonstopmode -halt-on-error poster.tex
pdfinfo poster.pdf && pdffonts poster.pdf && pdfimages -list poster.pdf
pdftoppm -scale-to 2000 -singlefile -png poster.pdf poster-preview
rg -n 'Overfull|Underfull|Warning|undefined' poster.log
bash /path/to/skill/scripts/review_poster.sh poster.pdf
```

`review_poster.sh` exit: 0 pass, 1 fail (unreadable/multi-page/unembedded fonts), 2 missing Poppler tools. It does not certify accessibility, PDF/X, science, QR targets, or overlap — inspect the render at all edges manually. Use LuaLaTeX/XeLaTeX only for `fontspec`/OpenType needs; run BibTeX/Biber only when the setup calls for it.

Install: `tlmgr install beamerposter tikzposter qrcode graphics xcolor booktabs`; verify with `kpsewhich <pkg>.sty|cls`. Never assume `tlmgr install baposter` works — supply `baposter.cls` with license and record its revision. Poppler via the platform package manager. Never put credential values in poster sources.

## Route B — PPTX (Manifest-Driven)

The manifest is the only content input: approved text/images, source IDs, asset hashes/licenses, canvas + physical geometry, venue/printer rules, quality thresholds. Template: `assets/poster_manifest_template.json`; strict schema: `references/manifest_spec.md`. Validate before generating: `python scripts/validate_manifest.py manifest.json`. Exact pins: `assets/generation_dependencies.json`.

```bash
python scripts/generate_poster.py manifest.json -o poster.pptx
python scripts/check_layout.py poster.pptx --manifest manifest.json    # bounds, overlap, reading order, final font size
python scripts/check_palette.py --manifest manifest.json               # WCAG contrast + palette separation
python scripts/inventory_images.py --manifest manifest.json            # hashed local-image inventory with effective DPI
python scripts/inspect_pptx.py poster.pptx --output report.json        # read-only package audit, never opens PowerPoint
python scripts/plan_export.py --manifest manifest.json                 # print/export plan vs venue spec
```

Optional HTML preview path: `assets/poster_html_template.html` (36x48 in, three-column; browser print to PDF with background graphics, then convert only if PPTX editing is required).

Figures: `python scripts/generate_schematic.py "…3 boxes MAX, GIANT labels…" -o figures/x.png --doc-type poster` (deterministic path) or `scripts/generate_schematic_ai.py` (iterative AI review; needs `OPENROUTER_API_KEY`). Poster-graphics discipline: max 3-4 elements and ~10 words per graphic, 50%+ whitespace, one message each, text huge (80-150 pt); split 5+-step workflows into multiple graphics. At 25% zoom every figure must read in ~2 seconds or be regenerated.

Security: never open untrusted `.pptx`/templates in PowerPoint to "check" them — audit with `inspect_pptx.py` first. Threat model (VBA, ActiveX, OLE, external relationships, zip traversal/bombs): `references/pptx_security.md`; validation record and pinned-suite evidence: `references/security_validation.md`; upstream basis: `references/source_ledger.md`.

## QC and Proofing (Both Routes)

- Confirm exact dimensions, orientation, one page/slide vs the venue spec; confirm printer color profile, bleed, PDF/X variant; keep the original when compressing/converting and recheck.
- Fonts: every `pdffonts` entry must show embedded (`emb`); raster PPI computed at placed size (300 PPI is a close-inspection starting point, not a universal rule; vector has no PPI).
- Reduced proof: A0-to-A4 is ~25% linear; a 36x48 in poster at 25% is 9x12 in (not Letter) — judge from scale factor x viewing distance.
- Checklists: `assets/latex-poster_quality_checklist.md` (LaTeX) and `assets/pptx-poster_quality_checklist.md` (PPTX). Start-point index for all LaTeX references: `references/README.md`.

## Scripts and References Index

Scripts (relative to skill root): `scripts/_common.py` (shared safety helpers: sizes, hashes, temp files, JSON emit), `scripts/_manifest.py` (strict manifest validation), `scripts/_pptx.py` (generation/layout/inspection primitives), `scripts/generate_poster.py`, `scripts/validate_manifest.py`, `scripts/check_layout.py`, `scripts/check_palette.py`, `scripts/inventory_images.py`, `scripts/inspect_pptx.py`, `scripts/plan_export.py`, `scripts/generate_schematic.py`, `scripts/generate_schematic_ai.py`, `scripts/review_poster.sh` (LaTeX PDF preflight).

References: `references/README.md` (LaTeX index), `references/latex_poster_reference.md`, `references/latex_poster_packages.md`, `references/latex-poster_layout_design.md`, `references/latex-poster_design_principles.md`, `references/latex-poster_content_guide.md`, `references/pptx-poster_layout_design.md`, `references/pptx-poster_design_principles.md`, `references/pptx-poster_content_guide.md`, `references/compilation_and_quality_control.md`, `references/ai_graphics_for_posters.md`, `references/poster_patterns_and_presentation.md`, `references/manifest_spec.md`, `references/pptx_security.md`, `references/security_validation.md`, `references/source_ledger.md`. No annex file excluded — all 8 assets, 16 references, and 13 scripts are cited above.

## Verification

- [ ] Route matches the request (LaTeX default; PPTX only when explicitly asked)
- [ ] Word/section/figure budget kept; placeholders, example citations, QR targets, logos all replaced
- [ ] LaTeX: two-pass compile clean, `review_poster.sh` exit 0, fonts embedded, dimensions exact, render visually inspected
- [ ] PPTX: manifest validated, `check_layout`/`check_palette`/`inventory_images` pass, `inspect_pptx` audit clean
- [ ] Proof judged at correct scale factor; printer profile/bleed confirmed

## Boundaries

- Never invent charts, microscopy, spectra, or numerical results with an image model; AI visuals are conceptual illustrations only.
- Never open untrusted `.pptx` or templates in PowerPoint to inspect them; audit with `scripts/inspect_pptx.py` first.
- Never assume `tlmgr install baposter` works; supply `baposter.cls` with its license and record the revision.
- Never put credential values (for example `OPENROUTER_API_KEY`) in poster sources.
- Never edit the bundled `assets/*_template.tex` files in place; copy one into the project first.
- A passing `review_poster.sh` or layout/palette check does not certify accessibility, PDF/X compliance, scientific accuracy, QR destinations, or overlap absence; inspect the render manually.

## Source Consolidation

Consolidates two origin skills into one poster front door:

- **latex-posters** — LaTeX route (packages, templates, compile/preflight discipline).
- **pptx-posters** — PPTX route (HTML/PPTX design, poster-format AI graphics discipline, quality checklists), now manifest-driven with layout/palette/security validation.
