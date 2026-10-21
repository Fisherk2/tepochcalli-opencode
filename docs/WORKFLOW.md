# Implementation Plan — Tepochcalli v1
**Date:** 2026-10-21 (rev. 2 — conforma D7/D8/D9) | **Author:** Arquitecto (entrevista /spec) | **Methodology:** Especificación-driven, fases con gates (doc para `/plan`)

> Cada fase tiene: objetivo, entregables, dependencias, métricas de cierre y **gate** — la fase
> siguiente NO arranca sin gate verde. Los contratos (specs) se congelan en Phase 0; cambiar
> un contrato en vuelo requiere ADR, no solo código.

## 1. Phase Overview

| Phase | Nombre | Objetivo | Gate (criterio de salida, medible) |
|---|---|---|---|
| 0 | Foundations | Specs/ADRs aprobadas y congeladas | APROBACIÓN: usuario confirma este set de docs; D1-D9 sin cambios; ADR-001..008 Accepted |
| 1 | Engine + Flow | Flujo CocoIndex indexa un vault real incrementalmente | `cocoindex update` sobre vault muestra: Δ <30s; filas en LanceDB queryables con `{source_path,heading,char_start,char_end}`; bench PDF-exclusión documentado |
| 2 | MCP Server | `tepochcalli-rag` conecta a OpenCode con contratos D6 — 4 tools: `search`, `index_refresh`, `add_source`, `rag_status` | opencode listá tools; `search` devuelve chunks citados <500ms en fixture; asserts de token-budget (≤1600 payload) en tests; taxonomía `E_*` + precedencia `INDEX_EMPTY` cubiertas (contract tests D7.3) |
| 3 | Wizard | Instalador Rust atomico end-to-end | VM limpia (Linux/macOS/Windows, sin Python/Node) → `curl \| sh` → vault instalado + índice inicial + `mcp.servers` validados, con un comando; prueba de idempotencia (2 corridas); instalación con menú de embedder (D7.1) en sus 5 salidas |
| 4 | Payload + Skills audit | Template distribuible coherente y skills saneadas | `obsidian-workspace/` = payload versión-release con muestras md+PDF; acciones Anexo A ejecutadas (duplicados consolidados, gaps Jupyter/R/Graphviz-PlantUML/LaTeX instalados o declarados won't); alias 00-Resources resuelto (TD-8); Validación del agent workflow (D9) verde: permission fixtures + methodology e2e |
| 5 | E2E Acceptance | Validar los 7 criterios de UH.md sobre sistema completo | Aceptación: tabla §5.3 toda verde en HW mínimo (8GB CPU-only) y corpus 10k/1k; docs de producto alineados |

## 2. Phase Breakdown

### Phase 0 — Foundations (esta entrega)

* Entregables: SPEC.md + 7 specs modulares + 8 ADRs + docs núcleo (ARCHITECTURE/PRD/TRD/APPFLOW/CODE_STYLE/SECURITY/TECH_DEBT/WORKFLOW) + AGENTS.md.
* Dependencias: docs/UH.md (inmutable). Métricas: checklist de quality-bar del set. Gate: revisión y aprobación humana del usuario (status → Approved en SPEC.md index).
* Nota (rev. 2): las olas D7 (ADR-007), D8 (ADR-008) y D9 (trays/propiedad — sin ADR, por decisión explícita del usuario) conformaron estas specs post-Phase-0; decisiones tomadas 2026-10-21 y registradas en §8 Change Control.

### Phase 1 — Engine + Flow

* Objetivo: `.tepochcalli/flow/` funcional (source localfs `00-Resources/**` → Docling/md → RecursiveSplitter(1024/128) → MiniLM → LanceDB ANN+FTS).
* Tareas clave: pipeline declarativo con `@coco.fn(memo=True)`; exclusión de rutas-punto y >100MB; campo `model` en filas; lockfile pineado; benches de Δ.
* Dependencias: Phase 0; decisión abierta de spec-embeddings (env SBERT_HOME) se resuelve aquí.
* Métricas de cierre: Δ<30s (p95, 20 corridas, corpus muestra); 100% filas con metadatos de cita no nulos; 0 LLM calls observables en indexación.
* Gate: fixtures de spec-rag-engine §Testing verdes en CI.

### Phase 2 — MCP Server

* Objetivo: `.tepochcalli/mcp/` con las 4 tools `search/index_refresh/add_source/rag_status` según spec-mcp-server (shapes JSON, taxonomía `E_*`, presupuestos).
* Tareas clave: handlers + validación de borde; token-budget determinista; medición `took_ms`; `add_source` integrado con markitdown-venv; entrypoint `tepochcalli-mcp`; contract tests D7.3: `rag_status` con shape exacto de los 4 bloques y <200 tokens; los cinco códigos `E_*` con payload `{error:{code,message,fix_hint}}`.
* Dependencias: Phase 1 (tabla de datos estable).
* Métricas: contract tests verdes; `search` <500ms p95 en fixture 100x; payload ≤1600 tokens adversos; instalación degraded (salida 5 de D7.1) → `search` = `E_NO_EMBEDDER` + `rag_status` = `degraded` con `fix_hint`; OpenCode V2 conecta vía `opencode.json` real del workspace.
* Gate: e2e "pregunta → tool-call → JSON citado" grabado como fixture.

### Phase 3 — Wizard

* Objetivo: crate Rust `tepochcalli` + cargo-dist (ADR-003) ejecutando las 8 fases atómicas con rollback/`--resume`/`--offline`/`--skip-model` — el menú embedder es la fase 6 (no añade una 9ª fase; spec-installer-wizard §Fases). Semántica `--skip-model` = salida-5 degraded (ADR-007 D7.1-5), NO `INDEX_EMPTY`.
* Tareas clave: fases con execute/compensate; merge conservador de `opencode.json` con `.bak`; UX TUI; matriz CI multi-OS; release `v*` de prueba; paso Embedding provider D7.1 (5 salidas, default `paraphrase-multilingual-MiniLM-L12-v2` preseleccionado); `presets.toml` embebido vía `include_str!` (D7.2); portero test-embed con RSS medido para todo camino local (D8.1); detección de host `sysinfo` + probe `nvidia-smi`/`rocm-smi` con badges `recommended`/`viable`/`no recomendado` (D8.2; fixture: host 4GB → fila `BAAI/bge-m3` badge `no recomendado` PERO seleccionable — warn-never-block D8.3); flujo degraded salida-5 (instalación COMPLETA sin fase 7 + checklist de re-entrada); swap atómico D8.4 (`tepochcalli config embedder` / `tepochcalli reindex --confirm` / `--keep-previous` / auto-GC del modelo viejo; fracaso inducido → cero cambio de estado).
* Dependencias: Phase 1+2 estables (el wizard los invoca); payload base de Phase 4 puede solaparse.
* Métricas: VM limpia → instalado en 1 comando; fallo inducido en cada fase → compensación correcta; 2 corridas → sin duplicados; VM limpia con salida-5 → vault completo + RAG degraded + checklist re-entrada; swap fixture: índice viejo servable durante reindex; modelo viejo purgado solo tras éxito.
* Gate: release tag de test con assets + `install.sh` funcionando en las 3 plataformas; incluye paths 1-5 del menú embedder en la matrix CI.

### Phase 4 — Payload + Skills audit

* Objetivo: `obsidian-workspace/` listo como asset de release (mirror del modelo `template/` de codice-opencode): muestras en `00-Resources/` (md+PDF, opcionalmente docx para TD de markitdown), `.gitignore` del vault, AGENTS.md del vault con reglas MCP-first, ejecución del saneamiento del Anexo A (spec-agent-workflow), scaffold alineado a la convención de carpetas con `04-review/` y `05-outputs/` creadas (Action Item spec-vault-structure), y validación explícita del agent workflow (D9, bloque abajo). Ejecución según blueprint [specs/spec-payload-vault.md](../specs/spec-payload-vault.md).
* Dependencias: Phase 2 (contratos) + Phase 3 (payload se instala con wizard).

#### Validación del agent workflow (D9 — gate explícito de Phase 4)

* **(a) Permission fixtures** (spec-agent-workflow §Testing D9.3, config `tools`/`permission` por agente verificada en fixtures OpenCode):
  * Pochteca: escritura permitida **solo** bajo `01-tasks/research/` y **denegada en todo lo demás** (root `01-tasks/`, `02-drafts/`, `03-citations/`, `04-review/`, `05-outputs/`, `00-Resources/` y carpetas personales: denegadas); navegación web permitida — desviación documentada del UH, decisión usuario 2026-10-21.
  * Tlacuilo: sin web; escritura en sus bandejas `02-drafts/` y `05-outputs/` (mapa D9.2).
  * Chilam: lectura total; escritura limitada a registros de auditoría, bases de citas y notas de revisión — bandejas `03-citations/` y `04-review/` (mapa D9.2).
  * Itzamná: lectura/escritura de contexto (enruta, NO ejecuta el pipeline).
  * Nezahualcóyotl: escritura solo de planificación (rúbricas, esquemas) en `01-tasks/`; sin web ni redacción final.
* **(b) Methodology e2e (golden vault)**: corrida completa `/rubric → /research → /validate → /synthesize → /cite → /draft → /review → /transform → /update` assertando: cada artefacto aterriza en SU bandeja única (mapa D9.2); frontmatter `{agent, timestamp, fuentes, método}` en las notas de `01-tasks/research/` y `{command, agent, target_doc, verdict}` en los informes de `04-review/`; cero contaminación cruzada entre bandejas; regla MCP-first observada (`search` antes de lectura cruda de `00-Resources/`); regla no-contaminación observada (el agente WARN si encuentra archivos depositados por el usuario dentro de las bandejas 01-05).

* Métricas: inventario final de skills ≤ objetivo (<60 en payload base); acciones de gaps documentadas; alias `00-Resources` resuelto (renombrar scaffold o soporte explícito en wizard); permission fixtures (a) y methodology e2e (b) verdes.
* Gate: `install` sobre el payload final → golden vault e2e pasa; + permission fixtures D9.3 y methodology e2e (D9) verdes.

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

**Gate adicional (no criterio UH)** — no forma parte de la tabla de 7 criterios de UH.md (no se renumeran ni se añade un "criterio 8"):

| Gate | Test | Result |
|---|---|---|
| Methodology e2e (§Phase 4 Validación D9) completo en corpus golden | corrida `/rubric→/update` con bandeajes D9.2 + permission fixtures D9.3 + frontmatters assertados | ☐ |

* Dependencias: Phases 1-4 verdes. Métricas: tabla completa; TECH_DEBT re-revisado.
* Gate: **v1 release** (o rollback de phase con nota en este documento).

## 3. Testing Strategy per Phase

| Phase | Tool | Scope | Success |
|---|---|---|---|
| 1 | pytest + cocoindex runtime | flujo unit/integración | como §Phase 1 métricas |
| 2 | pytest + fixture vault | contracts MCP, presupuestos, contrato `rag_status` + códigos `E_*` | shapes + cotas duras assertadas |
| 3 | cargo test + VM matrix | fases/rollback/idempotencia, menú embedder paths 1-5, swap D8.4 | sin datos del usuario perdidos en fallo |
| 4 | smoke e2e + permission fixtures + methodology e2e (D9) | payload instalado | golden vault consulta citada OK; bandejas/frontmatters D9.2 assertados |
| 5 | suite TRD §6 + manual | criterios 1-7 | toda la tabla verde |

## 4. Formal Technical Reviews (FTRs)

| Gate | Artefacto | Checklist | Participantes |
|---|---|---|---|
| Phase 0→1 | specs/ + ADRs | consistencia D1-D9, links, mermaid | Usuario + arquitecto |
| Phase 2→3 | contratos vs código | shapes = spec-mcp-server | arquitecto |
| Phase 4→5 | payload + skills | Anexo A acciones ejecutadas + permission fixtures + methodology e2e verdes | Usuario |

## 5. Risk Management

| Riesgo | Prob | Impacto | Mitigación | Contingencia |
|---|---|---|---|---|
| Bump roto de cocoindex/lancedb | med | alto | pineos, CI con lock, capa fina TD-1 | pin downgrade; target migration (ADR-002) |
| Criterio 3 falla en HW mínimo | med | crítico | presupuesto por etapas (spec-mcp-server), ANN tuning | top_k default 3 + re-ranking ligero; revisar ADR-006 (dimensión) |
| Wizard multi-OS complejo | med | alto | CI matrix temprana (Phase 3), `--resume` | Windows en v1.1 si bloquea (Linux/macOS first) |
| Skills audit toca `.opencode/` prohibido ahora | baja | medio | cambios solo vía Phase 4 autorizada | mantener inventario actual + TD-7 nota |
| Modelo HF custom inválido/erróneo elegido (D8) | med | medio | portero test-embed + badges D8.2 + warn-never-block (D8.3) | swap rápido vía `tepochcalli config embedder` (D8.4) sin reinstalar |

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

### Registro de olas de scope (2026-10-21)

| Ola | Qué decidió | Aprobó | Artefactos afectados |
|---|---|---|---|
| **D7** (ADR-007, Accepted 2026-10-21) | Selección de embedder en instalación: menú "Embedding provider" 5 salidas con default preseleccionado; `presets.toml` como datos; modo degraded + `rag_status` y taxonomía `E_*`; re-entrada `tepochcalli config embedder` / `tepochcalli reindex --confirm`. Reemplaza solo ADR-006 §4.1 | Usuario vía follow-up entrevista /spec (question tool) | specs/adr/adr-007*, spec-embeddings, spec-installer-wizard, spec-mcp-server, ARCHITECTURE, AGENTS, SPEC, TECH_DEBT |
| **D8** (ADR-008, Accepted 2026-10-21; refina D7 sin reemplazarlo) | Transparencia de hardware: `medido` > `estimado` > `declarado` + fórmula de RAM; autodetección de host (`sysinfo`, `nvidia-smi`/`rocm-smi`) con badges `recommended`/`viable`/`no recomendado`; warn-never-block; swap de modelo atómico sin reinstalar (`--keep-previous`, auto-GC) | Usuario vía question tool (4 opciones "Recommended") | specs/adr/adr-008*, spec-embeddings, spec-installer-wizard, APPFLOW, ARCHITECTURE, AGENTS, SPEC |
| **D9** (sin ADR, por decisión explícita del usuario — spec-only) | Semántica de carpetas: tres zonas de propiedad (entrada del usuario / bandejas del agente / biblioteca personal); set de bandejas 6 con mapa comandos→bandejas total y único (`04-review/`, `05-outputs/`); desviación documentada del UH: Pochteca escribe solo `01-tasks/research/` | Usuario vía question tool | specs/spec-vault-structure, specs/spec-agent-workflow, docs/APPFLOW, AGENTS, SPEC, docs/WORKFLOW (esta ola de conformación, rev. 2) |
