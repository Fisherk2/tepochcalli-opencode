---
description: "Turn accepted research into dissemination artifacts: Markdown, CSV/Excel, slides, HTML, posters."
agent: tlacuilo
---

## Phase 1: Confirm intent, inputs, and format

1. Analize the user intent: which input file(s) must be transformed and into which desired format. Without a named input file or a clear target format → **STOP** and ask with the `question` tool before doing anything else.
2. Ask the user with the `question` tool which of the following options to run, offering exactly these options with outputs landing in `05-outputs/`: 

A) Apply template (Markdown input only).
B) Spreadsheet. 
C) Posters. 
D) HTML. 
E) PDF.
F) Data plotting, 
G) Convert to Markdown. 

Record the chosen option and the exact input file(s) before leaving Pre-Flight.

## Option A): Apply template

1. Check the input file(s) are Markdown; non-Markdown input → **STOP** and suggest user to redirect to the Convert to Markdown option G) first.
2. Ask the user with the `question` tool which template from `10-templates/` (or from another template directory the user names) to apply, then **Delegate** `obsidian-vault-writer` subagent and **Load** `obsidian-markdown` + `obsidian-vault` skills and rewrite the input content into that template's structure without altering facts, numbers, or citations.
3. Save the result in `05-outputs/` as `<base>-templated.md` (never edit the original input, never edit the template file), then continue skip to phase 2.

## Option B): Spreadsheet

1. **Load** `spreadsheet-analysis` skill when the deliverable is a spreadsheet file, because it enforces the pandas read-first plus openpyxl formulas-first discipline with mandatory recalculation — check the input is tabular data convertible to `.xlsx`/`.xlsm`/`.csv`/`.tsv`; a docx report, HTML page, or database pipeline as deliverable → **STOP**, that output is out of scope for this branch.
2. Ask the user with the `question` tool exactly what to do with the file(s) — read/analyze, pivot, clean, merge, create, fix formulas — then inspect shape, dtypes, head/tail, and nulls before any write.
3. Transform per that skill's workflow (derived values as Excel formulas referencing assumption cells, `scripts/recalc.py` after every formula write, zero formula errors), and save the result in `05-outputs/` as `<base>-spreadsheet.xlsx` (or `.csv`/`.tsv` when the user asked for a plain tabular format; never touch the original input). Hand verified numbers to the Posters branch when a poster comes next — never invented figures. Then continue skip to phase 2.

## Option C): Posters

1. **Load** `posters-generator` skill when the user asked for a research, conference, or scientific poster, because it picks the LaTeX route by default (beamerposter/tikzposter/baposter with two-pass pdfLaTeX compile and Poppler preflight) and reserves the manifest-driven PPTX route for explicit PPTX requests — check the input carries verified numbers and real research images; AI-invented charts, microscopy, or spectra are forbidden.
2. Ask the user with the `question` tool for the route (LaTeX default vs explicit PPTX), venue size/orientation, and QR/contact/logo targets, then budget the content (300–800 words, 3–5 figures, 1–3 core messages) and replace every placeholder before delivery.
3. Build per that skill's workflow (copy a template, never edit `assets/*_template.tex` in place; validate the manifest before generating on the PPTX route; compile twice and run `review_poster.sh` on the LaTeX route; inspect the render manually at full size), and save the artifact in `05-outputs/` as `<base>-poster.pdf` (plus `<base>-poster.pptx` on the PPTX route; never touch the original input). Then continue skip to phase 2.

## Option D): HTML

1. **Load** `paper-2-web` skill when the user wants an interactive website, presentation video, or companion poster from a paper, because it drives the Paper2All pipeline (Paper2Web/Paper2Video/Paper2Poster) with LLM content extraction and iterative refinement — check the input is a LaTeX source directory (`main.tex` + figures + bibliography, recommended) or a high-quality PDF with selectable text and embedded fonts; scanned-image PDFs → **STOP**, offer manual OCR or a hand-made `.md` first.
2. Ask the user with the `question` tool which component(s) to generate (website, video, poster, or the full package), plus any conference sizing, branding, or language requirements, and confirm the Paper2All prerequisites (cloned repo, `.env` API keys, LibreOffice/Poppler installed) before launching the pipeline.
3. Transform per that skill's workflow (`pipeline_all.py --generate-website` and/or `--generate-poster`/`--generate-video`, quality checks on links, readability, and audio sync), and save the generated bundle in `05-outputs/` as `<base>-web/` (plus `<base>-video.mp4` / `<base>-poster.pdf` when those components were requested; never touch the original input). Then continue skip to phase 2.

## Option E): PDF

1. **Load** `pdf` skill whenever the user wants anything done with PDF files, because it covers the full operation set (pypdf merge/split/rotate/watermark/encrypt, pdfplumber text/table extraction, reportlab creation, pytesseract OCR for scanned pages, qpdf command-line ops) — check the input matches the requested operation (e.g. multiple PDFs for a merge, a text-layer PDF for extraction); scanned pages needing text → route through OCR explicitly.
2. Ask the user with the `question` tool exactly what to do with the file(s) — merge, split, rotate, watermark, encrypt, extract text/tables, create from scratch, fill a form — then run the operation per that skill's quick-start patterns.
3. Save the result in `05-outputs/` as `<base>-merged.pdf`, `<base>-page-N.pdf`, `<base>-report.pdf`, or the equivalent deterministic name for the operation (never touch the original input; never use Unicode sub/superscripts in reportlab Paragraphs — use `<sub>`/`<super>` tags). Then continue skip to phase 2.

## Option F): Data plotting

1. **Load** `data-plotting` skill whenever the user wants a plot, chart, heatmap, statistical graphic, or interactive figure, because it is the single front door across matplotlib (full control), seaborn (quick stats), plotly (interactivity), and journal styling presets — check the input is local named data the user supplied; remote/untrusted data → **STOP**, inspect it first and never resolve embedded URLs or call submission APIs.
2. Ask the user with the `question` tool for the plot type, the data columns to map, and the target use (exploration, interactive chart, or journal submission), then draft from `scripts/plot_template.py`, style with a colorblind-safe palette, and plan the export against the publisher snapshot.
3. Export per that skill's workflow (`scripts/figure_export.py` to PDF/EPS/TIFF/PNG at the right DPI; presets and screens are planning aids only — never claim journal compliance), and save the figure in `05-outputs/` as `<base>-fig-N.<ext>` (never touch the original input; never certify scales or uncertainty from style settings alone). Then continue skip to phase 2.

## Option G): Convert to Markdown

1. **Load** `tepochcalli-mcp` skill when the user wants a readable `.md` from a vault document — check the extension against `list_formats()` first.
2. Validate input → output compatibility against the catalogue from step 1; on mismatch → **STOP**, report the incompatibility, name the supported alternatives, and offer them with the `question` tool instead of forcing the conversion.
3. Ask the user with the `question` tool for the exact file to convert and the destination name, then call `convert_document(path, output_path="05-outputs/<base>.md")` (or `convert_base64` with a `filename`/`format` hint when the bytes are in context rather than on disk).
4. Never re-emit the converted content (not the `preview`, not the body): the summary `{written_to, source_uri, bytes, chars, preview}` confirms and the file is the artifact. The converter never overwrites — same bytes return the same summary, different bytes return `VALIDATION_ERROR` with an alternative name. Then continue skip to phase 2.

## Phase 2: Summarize

1. Write a summary: what was transformed, with which option/skill, and the exact path(s) saved in `05-outputs/`.
2. **Transform is done — do NOT touch or write anything. Only transform tasks and files saved to `05-outputs/`.**
3. Commit all changes with a descriptive message (only if you have git installed in the vault, if not, skip this step).

## Rules

- If `05-outputs/` does not exist, create it.
- Never invent citations, numbers, or figures: cite `source_path » heading (chars x–y)` exactly as `search` returned them; figures come from verified analysis outputs only.

## Suggested Next Step
> Artifacts generated in `05-outputs/`. Please review and let me know if you need further assistance.
