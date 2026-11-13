# Technical Diagnoses

This directory documents technical diagnoses for issues identified in the project. Each diagnosis follows a structured format for consistency and traceability.

## Purpose

- Capture root cause analysis for bugs, incidents, and technical issues
- Provide a searchable record of past diagnoses for future reference
- Track recurring patterns that may need automation or systemic fixes

## Index

| File | Issue | Date | Severity |
| --- | --- | --- | --- |
| [phase6-protocol.md](phase6-protocol.md) | Protocolo de aceptación Phase 6 (protocolo, no diagnóstico) | 2026-11-12 | — |
| [phase6-corpus.md](phase6-corpus.md) | Corpus de escala 10k/1k con manifiesto (T1) | 2026-11-12 | — |
| [phase6-documents.md](phase6-documents.md) | Coste de extracción de documentos binarios (T2) | 2026-11-12 | — |
| [phase6-payload-refs.md](phase6-payload-refs.md) | Refs del payload a skills/subagentes (T13/TQA) | 2026-11-12 | — |
| [phase6-search-scale.md](phase6-search-scale.md) | Criterio 3 a escala + deriva FTS ES/EN (T4) | 2026-11-12 | — |

<!-- Add entries here as diagnoses are created -->

## Workflow

1. An issue is identified (user report, automated alert, code review)
2. Run `/diagnosis` to analyze and document the root cause
3. Run `/plan` to create an execution plan for the fix
4. Update the diagnosis if the fix reveals additional insights

## Template

Use `diagnosis-template.md` as a starting point for new diagnoses.

## Naming Convention

<!-- markdownlint-disable MD040 -->
```
fix<NNN>-<short-description>.md
```
<!-- markdownlint-enable MD040 -->

Where `<NNN>` is a sequential number (01, 02, ...) and `<short-description>` is a kebab-case summary of the issue.
