# Implementation Plan — Tepochcalli v1
**Date:** 2026-10-21 | **Author:** Arquitecto (entrevista /spec) | **Methodology:** Especificación-driven, fases con gates (doc para `/plan`)

> Cada fase tiene: objetivo, entregables, dependencias, métricas de cierre y **gate** — la fase
> siguiente NO arranca sin gate verde. Los contratos (specs) se congelan en Phase 0; cambiar
> un contrato en vuelo requiere ADR, no solo código.

## 1. Phase Overview

| Phase | Nombre | Objetivo | Gate (criterio de salida, medible) |
|---|---|---|---|
| 0 | Foundations | Specs/ADRs aprobadas y congeladas | APROBACIÓN: usuario confirma este set de docs; D1-D6 sin cambios; ADR-001..006 Accepted |
| 1 | Engine + Flow | Flujo CocoIndex indexa un vault real incrementalmente | `cocoindex update` sobre vault muestra: Δ <30s; filas en LanceDB queryables con `{source_path,heading,char_start,char_end}`; bench PDF-exclusión documentado |
| 2 | MCP Server | `tepochcalli-rag` conecta a OpenCode con contratos D6 | opencode listá tools; `search` devuelve chunks citados <500ms en fixture; asserts de token-budget (≤1600 payload) en tests; errores tipados cubiertos |
| 3 | Wizard | Instalador Rust atomico end-to-end | VM limpia (Linux/macOS/Windows, sin Python/Node) → `curl \| sh` → vault instalado + índice inicial + `mcp.servers` validados, con un comando; prueba de idempotencia (2 corridas) |
| 4 | Payload + Skills audit | Template distribuible coherente y skills saneadas | `obsidian-workspace/` = payload versión-release con muestras md+PDF; acciones Anexo A ejecutadas (duplicados consolidados, gaps Jupyter/R/Graphviz-PlantUML/LaTeX instalados o declarados won't); alias 00-Resources resuelto (TD-8) |
| 5 | E2E Acceptance | Validar los 7 criterios de UH.md sobre sistema completo | Aceptación: tabla §5.3 toda verde en HW mínimo (8GB CPU-only) y corpus 10k/1k; docs de producto alineados |

## 2. Phase Breakdown

### Phase 0 — Foundations (esta entrega)

* Entregables: SPEC.md + 7 specs modulares + 6 ADRs + docs núcleo (ARCHITECTURE/PRD/TRD/APPFLOW/CODE_STYLE/SECURITY/TECH_DEBT/WORKFLOW) + AGENTS.md.
* Dependencias: docs/UH.md (inmutable). Métricas: checklist de quality-bar del set. Gate: revisión y aprobación humana del usuario (status → Approved en SPEC.md index).

### Phase 1 — Engine + Flow

* Objetivo: `.tepochcalli/flow/` funcional (source localfs `00-Resources/**` → Docling/md → RecursiveSplitter(1024/128) → MiniLM → LanceDB ANN+FTS).
* Tareas clave: pipeline declarativo con `@coco.fn(memo=True)`; exclusión de rutas-punto y >100MB; campo `model` en filas; lockfile pineado; benches de Δ.
* Dependencias: Phase 0; decisión abierta de spec-embeddings (env SBERT_HOME) se resuelve aquí.
* Métricas de cierre: Δ<30s (p95, 20 corridas, corpus muestra); 100% filas con metadatos de cita no nulos; 0 LLM calls observables en indexación.
* Gate: fixtures de spec-rag-engine §Testing verdes en CI.

### Phase 2 — MCP Server

* Objetivo: `.tepochcalli/mcp/` con `search/index_refresh/add_source` según spec-mcp-server (shapes JSON, errores, presupuestos).
* Tareas clave: handlers + validación de borde; token-budget determinista; medición `took_ms`; `add_source` integrado con markitdown-venv; entrypoint `tepochcalli-mcp`.
* Dependencias: Phase 1 (tabla de datos estable).
* Métricas: contract tests verdes; `search` <500ms p95 en fixture 100x; payload ≤1600 tokens adversos; OpenCode V2 conecta vía `opencode.json` real del workspace.
* Gate: e2e "pregunta → tool-call → JSON citado" grabado como fixture.

### Phase 3 — Wizard

* Objetivo: crate Rust `tepochcalli` + cargo-dist (ADR-003) ejecutando las 8 fases atómicas con rollback/`--resume`/`--offline`/`--skip-model`.
* Tareas clave: fases con execute/compensate; merge conservador de `opencode.json` con `.bak`; UX TUI; matriz CI multi-OS; release `v*` de prueba.
* Dependencias: Phase 1+2 estables (el wizard los invoca); payload base de Phase 4 puede solaparse.
* Métricas: VM limpia → instalado en 1 comando; fallo inducido en cada fase → compensación correcta; 2 corridas → sin duplicados.
* Gate: release tag de test con assets + `install.sh` funcionando en las 3 plataformas.

### Phase 4 — Payload + Skills audit

* Objetivo: `obsidian-workspace/` listo como asset de release (mirror del modelo `template/` de codice-opencode): muestras en `00-Resources/` (md+PDF, opcionalmente docx para TD de markitdown), `.gitignore` del vault, AGENTS.md del vault con reglas MCP-first, y ejecución del saneamiento del Anexo A (spec-agent-workflow).
* Dependencias: Phase 2 (contratos) + Phase 3 (payload se instala con wizard).
* Métricas: inventario final de skills ≤ objetivo (<60 en payload base); acciones de gaps documentadas; alias `00-Resources` resuelto (renombrar scaffold o soporte explícito en wizard).
* Gate: `install` sobre el payload final → golden vault e2e pasa.

### Phase 5 — E2E Acceptance (los 7 criterios)

* Objetivo: validación integral contra docs/UH.md sobre sistema instalado como lo tendría un usuario.
* Metodología: [docs/TRD.md](TRD.md) §6 (protocolos 30s/500ms/2000tok/10k-1k) + checklist de criterio 1 (no-interferencia, spec-vault-structure §Testing).
* Tabla §5.3 de salida (llenar en la corrida):

| Criterio UH.md | Test | Result |
|---|---|---|
| 1. Sin interferencias | checklist Vault-OK post-instalación (0 puertos, `.obsidian/` intacto, UI limpia) | ☐ |
| 2. Δ <30s | bench `index_refresh` 20 corridas típicas | ☐ |
| 3. Búsqueda <500ms | bench `search` p95 sobre corpus 10k/1k | ☐ |
| 4. ≤2000 tokens/consulta | fixture adverso + medidor e2e del harness | ☐ |
| 5. Citas precisas | golden answers: 100% con `source_path`+`heading`+offsets reproducibles | ☐ |
| 6. 10k notas + 1k PDFs | stress corpus + regresión de latencia vs 10% | ☐ |
| 7. Multi-formato | matriz conversión (docx/xlsx/html/url) → indexable | ☐ |

* Dependencias: Phases 1-4 verdes. Métricas: tabla completa; TECH_DEBT re-revisado.
* Gate: **v1 release** (o rollback de phase con nota en este documento).

## 3. Testing Strategy per Phase

| Phase | Tool | Scope | Success |
|---|---|---|---|
| 1 | pytest + cocoindex runtime | flujo unit/integración | como §Phase 1 métricas |
| 2 | pytest + fixture vault | contracts MCP, presupuestos | shapes + cotas duras assertadas |
| 3 | cargo test + VM matrix | fases/rollback/idempotencia | sin datos del usuario perdidos en fallo |
| 4 | smoke e2e | payload instalado | golden vault consulta citada OK |
| 5 | suite TRD §6 + manual | criterios 1-7 | toda la tabla verde |

## 4. Formal Technical Reviews (FTRs)

| Gate | Artefacto | Checklist | Participantes |
|---|---|---|---|
| Phase 0→1 | specs/ + ADRs | consistencia D1-D6, links, mermaid | Usuario + arquitecto |
| Phase 2→3 | contratos vs código | shapes = spec-mcp-server | arquitecto |
| Phase 4→5 | payload + skills | Anexo A acciones ejecutadas | Usuario |

## 5. Risk Management

| Riesgo | Prob | Impacto | Mitigación | Contingencia |
|---|---|---|---|---|
| Bump roto de cocoindex/lancedb | med | alto | pineos, CI con lock, capa fina TD-1 | pin downgrade; target migration (ADR-002) |
| Criterio 3 falla en HW mínimo | med | crítico | presupuesto por etapas (spec-mcp-server), ANN tuning | top_k default 3 + re-ranking ligero; revisar ADR-006 (dimensión) |
| Wizard multi-OS complejo | med | alto | CI matrix temprana (Phase 3), `--resume` | Windows en v1.1 si bloquea (Linux/macOS first) |
| Skills audit toca `.opencode/` prohibido ahora | baja | medio | cambios solo vía Phase 4 autorizada | mantener inventario actual + TD-7 nota |

## 6. Progress Metrics

* Δ-time de refresh p95, latencia search p95, tokens/consulta p95 — post-instalados en fixtures, tendencial por release.
* Done per layer: flow (filas correctas) → server (contrato) → wizard (VM limpia) → payload (golden e2e) → aceptación (tabla §5).

## 7. Schedule and Milestones

* Hitos: M0 (specs aprobadas) → M1 índice vivo → M2 agente cita → M3 un comando instala todo → M4 payload limpio → M5 v1.
* Sin fechas comprometidas (proyecto individual); orden de dependencias como grafo de Phases arriba.

## 8. Change Control and Lessons Learned

* Cualquier desviación de un contrato = ADR nuevo (inmutabilidad Accepted).
* Cambios de scope solo con aprobación usuario; se registran al final de este documento.
* Lessons learned: sección a llenar tras cada gate (fallas de benches, sorpresas de plataformas).
