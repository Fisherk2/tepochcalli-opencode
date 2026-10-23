# Implementation Plan — Tepochcalli v1
**Date:** 2026-10-21 (rev. 4 — estado de fases: Phase 1 completada 2026-10-23, Phase 2 listo para planeación; rev. 3 renumeró Payload→5, E2E→6) | **Author:** Arquitecto (entrevista /spec) | **Methodology:** Especificación-driven, fases con gates (doc para `/plan`)

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
| 4 | Diseño del agent workflow (blueprint) | Completar specs/spec-payload-vault.md hasta Approved: system prompts definitivos de los 5 agentes, permisos YAML (last-match-wins), templates de los 9 comandos, tabla de invocación 9×4 y matriz de conflictos contra el inventario REAL de skills — documentación pura, cero escritura de payload | BLUEPRINT APPROVED por el usuario (status → Approved en SPEC.md index); matriz cubre el 100% del inventario (recuento ls vs filas); cero skills/subagents inventados; permisos sin campos legacy V2 |
| 5 | Payload + Skills audit (ejecución) | Ejecución LITERAL del blueprint Approved sobre `obsidian-workspace/` | `obsidian-workspace/` = payload versión-release generado del blueprint; muestras md+PDF; acciones Anexo A ejecutadas (duplicados consolidados, gaps Jupyter/R/Graphviz-PlantUML/LaTeX instalados o declarados won't); alias 00-Resources resuelto (TD-8); Validación del agent workflow (D9) verde: permission fixtures + methodology e2e |
| 6 | E2E Acceptance | Validar los 7 criterios de UH.md sobre sistema completo | Aceptación: tabla §6.3 toda verde en HW mínimo (8GB CPU-only) y corpus 10k/1k; docs de producto alineados |

> **Estado (2026-10-23):** Phase 1 **completada** (§Phase 1); Phase 2 (server MCP) **listo para planeación, no empezada** (§Phase 2); el resto de fases sin arrancar.

## 2. Phase Breakdown

### Phase 0 — Foundations (esta entrega)

* Entregables: SPEC.md + 8 specs modulares + 8 ADRs + docs núcleo (ARCHITECTURE/PRD/TRD/APPFLOW/CODE_STYLE/SECURITY/TECH_DEBT/WORKFLOW) + AGENTS.md. (8 specs desde la ola del blueprint specs/spec-payload-vault.md.)
* Dependencias: docs/UH.md (inmutable). Métricas: checklist de quality-bar del set. Gate: revisión y aprobación humana del usuario (status → Approved en SPEC.md index).
* Nota (rev. 2): las olas D7 (ADR-007), D8 (ADR-008) y D9 (trays/propiedad — sin ADR, por decisión explícita del usuario) conformaron estas specs post-Phase-0; decisiones tomadas 2026-10-21 y registradas en §8 Change Control.

### Phase 1 — Engine + Flow

* **Estado (2026-10-23): COMPLETADA.** Gate de cierre verde: `just ci` (**164 passed**; smoke Δ **991 ms** < 10 000 ms), `just coverage` **98 %** (`fail_under=95`), mypy strict y ruff dentro del pipeline; revisión multi-eje (5 ejes) cerrada con **24 hallazgos aplicados en 16 commits**. Estas cifras de cierre **sustituyen** a las intermedias T10/T11 de las métricas de abajo (137 passed, smoke Δ 1 757 ms), que se conservan como registro histórico. Pendiente del usuario (**NO hecho**): **push de la rama** — ~29 commits sin publicar; el workflow de GitHub Actions sigue sin haber corrido (M6).
* Objetivo: `.tepochcalli/flow/` funcional (source localfs `00-Resources/**` → Docling/md → RecursiveSplitter(1536/192 bytes) → MiniLM → LanceDB ANN+FTS).
* Tareas clave: pipeline declarativo con `@coco.fn(memo=True)`; exclusión de rutas-punto y >100MB; campo `model` en filas; lockfile pineado; benches de Δ.
* Dependencias: Phase 0; decisión abierta de spec-embeddings (env SBERT_HOME) se resuelve aquí.
* Métricas de cierre — **medidas** (T10/T11, 2026-10-22/23; ninguna estimación aquí):
  * **M1 — Δ p95 < 30 s: PASS con margen 5×.** p95 = **5 385 / 5 466 / 5 952 ms** en 3 corridas (gate 30 000 ms; variación ≤10 %). Percentil **nearest-rank** sobre n=20 (el 19.º valor ordenado). Protocolo TRD §6.2: corpus determinista de 50 md/txt (seed 20261022) en un vault temporal, 20 ciclos sobre una rampa 1→50, cronómetro `RefreshReport.elapsed_ms` (monótono; incluye lock + update). Host observado: Intel i7-8750H 6C/12T, 15,8 GiB RAM, zram swap de 7 913 MB **sin presión** durante las corridas (muestreo cada 250 ms), vault en btrfs/NVMe, CPython 3.12.14. **Desviación declarada:** es el host de desarrollo de Phase 1, no la VM de referencia de TRD §6. **Salvedad honesta:** la indexación *inicial fría* varió mucho más — 34 227 / 33 358 / **70 694 ms** —; queda fuera del presupuesto por el protocolo, pero se reporta.
  * **M2 — metadatos de cita al 100 %.** Todas las filas llevan `source_path`, `char_start`, `char_end` y `doc_kind` no nulos, y `heading` presente; `heading` es **nullable (D13)** — `null` cuando el documento no tiene heading padre. Verificado fila por fila re-sliceando desde disco (5/5).
  * **M3 — cero llamadas a LLM durante la indexación**, probado dos vías: (a) ningún `litellm`/`openai`/`anthropic` presente en `sys.modules`; (b) `update_blocking()` completado con el `socket.connect` saliente bloqueado (AF_INET/AF_INET6) y **cero intentos de egress** registrados por un canario.
  * Métricas de apoyo: **M4** — filas queryables con `{source_path, heading, char_start, char_end}` vía el verificador CLI, cuyo carácter de solo lectura está probado por snapshot de `(mtime_ns, size)`. **M5** — coste de PDF **medido**: 30 páginas = **49–51 s** en caliente (≈1,6–1,7 s/pág), RSS pico **2 048–2 189 MiB**; en frío la carga de modelos de Docling domina (**29–37 s**) — por encima de la estimación de spec-rag-engine (TD-2 actualizado). **M6** — CI con **solo verificación local**: `.github/workflows/phase1.yml` existe, actionlint v1.7.9 + shellcheck con 0 errores, y los 7 pasos ejecutados localmente en el mismo orden y directorios; suite **137 passed**, smoke Δ 1 757 ms < 60 000 ms. **El workflow nunca ha corrido en GitHub Actions** — decisión del usuario 2026-10-23 de no publicar los 27 commits en un repo público; no se declara CI verde.
  * Contexto operativo: Δ de refresh típico **58–178 ms**; suite completa **~180–250 s** (137 passed, 1 deselected, 1 warning esperada = TD-9).
* Gate: fixtures de spec-rag-engine §Testing verdes **en verificación local** (M6 sin correr en Actions — salvedad arriba) + FTR Phase 0→1 (§4) ejecutado en T12. **M7** (sign-off del usuario para arrancar Phase 2): **concedido el 2026-10-23** — Phase 1 queda cerrada (estado arriba) y Phase 2 habilitada para planeación.

### Phase 2 — MCP Server

* **Estado (2026-10-23): LISTO PARA PLANEACIÓN — no empezada.** Tres precondiciones cumplidas: (1) contrato `search/index_refresh/add_source/rag_status` **congelado** en [spec-mcp-server](../specs/spec-mcp-server.md); (2) `CitedChunk.offsets_ref` resuelto antes del freeze; (3) `adapters.build_reader` (composition root del flow, embedder pineado por `MODEL_REVISION`) listo para que los handlers lo consuman. Aviso de homonimia: esta «Phase 2» es la del plan por fases del **producto**; no confundirla con la «fase 2: TDD» interna de los comandos `/test`, trabajo ya entregado dentro de Phase 1 (pirámide unit/integration/e2e).
* Objetivo: `.tepochcalli/mcp/` con las 4 tools `search/index_refresh/add_source/rag_status` según spec-mcp-server (shapes JSON, taxonomía `E_*`, presupuestos).
* Tareas clave: handlers + validación de borde; token-budget determinista; medición `took_ms`; `add_source` integrado con markitdown-venv; entrypoint `tepochcalli-mcp`; contract tests D7.3: `rag_status` con shape exacto de los 4 bloques y <200 tokens; los cinco códigos `E_*` con payload `{error:{code,message,fix_hint}}`.
* Dependencias: Phase 1 (tabla de datos estable).
* Métricas: contract tests verdes; `search` <500ms p95 en fixture 100x; payload ≤1600 tokens adversos; instalación degraded (salida 5 de D7.1) → `search` = `E_NO_EMBEDDER` + `rag_status` = `degraded` con `fix_hint`; OpenCode V2 conecta vía `opencode.json` real del workspace.
* Gate: e2e "pregunta → tool-call → JSON citado" grabado como fixture.

### Phase 3 — Wizard

* Objetivo: crate Rust `tepochcalli` + cargo-dist (ADR-003) ejecutando las 8 fases atómicas con rollback/`--resume`/`--offline`/`--skip-model` — el menú embedder es la fase 6 (no añade una 9ª fase; spec-installer-wizard §Fases). Semántica `--skip-model` = salida-5 degraded (ADR-007 D7.1-5), NO `INDEX_EMPTY`.
* Tareas clave: fases con execute/compensate; merge conservador de `opencode.json` con `.bak`; UX TUI; matriz CI multi-OS; release `v*` de prueba; paso Embedding provider D7.1 (5 salidas, default `paraphrase-multilingual-MiniLM-L12-v2` preseleccionado); `presets.toml` embebido vía `include_str!` (D7.2); portero test-embed con RSS medido para todo camino local (D8.1); detección de host `sysinfo` + probe `nvidia-smi`/`rocm-smi` con badges `recommended`/`viable`/`no recomendado` (D8.2; fixture: host 4GB → fila `BAAI/bge-m3` badge `no recomendado` PERO seleccionable — warn-never-block D8.3); flujo degraded salida-5 (instalación COMPLETA sin fase 7 + checklist de re-entrada); swap atómico D8.4 (`tepochcalli config embedder` / `tepochcalli reindex --confirm` / `--keep-previous` / auto-GC del modelo viejo; fracaso inducido → cero cambio de estado).
* Dependencias: Phase 1+2 estables (el wizard los invoca); payload base de Phase 5 puede solaparse; el blueprint de Phase 4 (diseño) corre en paralelo sin depender del wizard.
* Métricas: VM limpia → instalado en 1 comando; fallo inducido en cada fase → compensación correcta; 2 corridas → sin duplicados; VM limpia con salida-5 → vault completo + RAG degraded + checklist re-entrada; swap fixture: índice viejo servable durante reindex; modelo viejo purgado solo tras éxito.
* Gate: release tag de test con assets + `install.sh` funcionando en las 3 plataformas; incluye paths 1-5 del menú embedder en la matrix CI.

### Phase 4 — Diseño del agent workflow (blueprint)

* Objetivo: completar specs/spec-payload-vault.md hasta estado **Approved**: system prompts definitivos de los 5 agentes, bloques YAML de permisos (last-match-wins), templates determinísticos de los 9 comandos. AGENDA: (i) §Tabla de invocación por comando — 9 filas × 4 columnas {skills concretas del inventario real, herramientas nativas, MCPs a ejecutar (`tepochcalli-rag` tools por comando; markitdown; excel/jupyter si existen), subagentes permitidos}; (ii) §Matriz de conflictos/redundancias de skills contra el inventario REAL de `obsidian-workspace/.opencode/skills/` (lectura only).
* Naturaleza: **documentación pura — cero escritura de payload**. `obsidian-workspace/` sigue vedado; la prohibición es un deliverable verbal de esta fase, no código.
* Dependencias: Phase 0 (contratos D9); puede correr en paralelo a Phases 1-3 (no los necesita — los contratos MCP ya están Accepted).
* Métricas: la matriz cubre el 100% del inventario (recuento `ls` vs filas); cada skill referenciada en la tabla existe o está marcada GAP; cero skills/subagents inventados; permisos YAML sin campos legacy V2.
* **Gate: BLUEPRINT APPROVED por el usuario** (status de spec-payload-vault → Approved en el índice de SPEC.md). Sin gate verde, Phase 5 NO arranca.

### Phase 5 — Payload + Skills audit (ejecución)

* Ejecución LITERAL del blueprint Approved de Phase 4: los archivos del payload se generan del spec-payload-vault Approved, **sin reinterpretación**; divergencia descubierta en vuelo = volver a Phase 4 (enmienda al blueprint), no parche ad-hoc.
* Objetivo: `obsidian-workspace/` listo como asset de release (mirror del modelo `template/` de codice-opencode): muestras en `00-Resources/` (md+PDF, opcionalmente docx para TD de markitdown), `.gitignore` del vault, AGENTS.md del vault con reglas MCP-first, ejecución del saneamiento del Anexo A (spec-agent-workflow), scaffold alineado a la convención de carpetas con `04-review/` y `05-outputs/` creadas (Action Item spec-vault-structure), y validación explícita del agent workflow (D9, bloque abajo). Ejecución según blueprint [specs/spec-payload-vault.md](../specs/spec-payload-vault.md).
* Dependencias: Phase 2 (contratos) + Phase 3 (payload se instala con wizard) + Phase 4 (blueprint Approved).

#### Validación del agent workflow (D9 — gate explícito de Phase 5)

* **(a) Permission fixtures** (spec-agent-workflow §Testing D9.3, config `tools`/`permission` por agente verificada en fixtures OpenCode):
  * Pochteca: escritura permitida **solo** bajo `01-tasks/research/` y **denegada en todo lo demás** (root `01-tasks/`, `02-drafts/`, `03-citations/`, `04-review/`, `05-outputs/`, `00-Resources/` y carpetas personales: denegadas); navegación web permitida — desviación documentada del UH, decisión usuario 2026-10-21.
  * Tlacuilo: sin web; escritura en sus bandejas `02-drafts/` y `05-outputs/` (mapa D9.2).
  * Chilam: lectura total; escritura limitada a registros de auditoría, bases de citas y notas de revisión — bandejas `03-citations/` y `04-review/` (mapa D9.2).
  * Itzamná: lectura/escritura de contexto (enruta, NO ejecuta el pipeline).
  * Nezahualcóyotl: escritura solo de planificación (rúbricas, esquemas) en `01-tasks/`; sin web ni redacción final.
* **(b) Methodology e2e (golden vault)**: corrida completa `/rubric → /research → /validate → /synthesize → /cite → /draft → /review → /transform → /update` assertando: cada artefacto aterriza en SU bandeja única (mapa D9.2); frontmatter `{agent, timestamp, fuentes, método}` en las notas de `01-tasks/research/` y `{command, agent, target_doc, verdict}` en los informes de `04-review/`; cero contaminación cruzada entre bandejas; regla MCP-first observada (`search` antes de lectura cruda de `00-Resources/`); regla no-contaminación observada (el agente WARN si encuentra archivos depositados por el usuario dentro de las bandejas 01-05).

* Métricas: inventario final de skills ≤ objetivo (<60 en payload base); acciones de gaps documentadas; alias `00-Resources` resuelto (renombrar scaffold o soporte explícito en wizard); permission fixtures (a) y methodology e2e (b) verdes.
* Gate: `install` sobre el payload final → golden vault e2e pasa; + permission fixtures D9.3 y methodology e2e (D9) verdes.

### Phase 6 — E2E Acceptance (los 7 criterios)

* Objetivo: validación integral contra docs/UH.md sobre sistema instalado como lo tendría un usuario.
* Metodología: [docs/TRD.md](TRD.md) §6 (protocolos 30s/500ms/2000tok/10k-1k) + checklist de criterio 1 (no-interferencia, spec-vault-structure §Testing).
* Tabla §6.3 de salida (llenar en la corrida):

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
| Methodology e2e (§Phase 5 Validación D9) completo en corpus golden | corrida `/rubric→/update` con bandeajes D9.2 + permission fixtures D9.3 + frontmatters assertados | ☐ |

* Dependencias: Phases 1-5 verdes. Métricas: tabla completa; TECH_DEBT re-revisado.
* Gate: **v1 release** (o rollback de phase con nota en este documento).

## 3. Testing Strategy per Phase

| Phase | Tool | Scope | Success |
|---|---|---|---|
| 1 | pytest + cocoindex runtime | flujo unit/integración | como §Phase 1 métricas |
| 2 | pytest + fixture vault | contracts MCP, presupuestos, contrato `rag_status` + códigos `E_*` | shapes + cotas duras assertadas |
| 3 | cargo test + VM matrix | fases/rollback/idempotencia, menú embedder paths 1-5, swap D8.4 | sin datos del usuario perdidos en fallo |
| 4 | ls + grep + revisión humana del blueprint | tabla de invocación 9×4 + matriz de conflictos contra el inventario real; permisos YAML V2 | BLUEPRINT APPROVED por el usuario |
| 5 | smoke e2e + permission fixtures + methodology e2e (D9) | payload instalado desde el blueprint Approved | golden vault consulta citada OK; bandejas/frontmatters D9.2 assertados; coherencia blueprint vs archivos generados |
| 6 | suite TRD §6 + manual | criterios 1-7 | toda la tabla verde |

Gate de tipos de Phase 1: `uv run python -m mypy flow` desde `obsidian-workspace/.tepochcalli/`, en modo
`strict`; corre en CI entre `ruff format --check` y `pytest` y su superficie tipada es `flow/` en
v1 ([CODE_STYLE.md](CODE_STYLE.md) §Herramientas y comandos).

### Cobertura

`just coverage` es la ÚNICA cifra honesta: instrumenta también los subprocesos (`refresh` y el CLI
`verify`), vía `sitecustomize` + `[tool.coverage.run] parallel`. `pytest --cov` a secas sub-mide
(`verify.py` 0 %, `app.py` 74 % → real medido: `verify.py` 98 %, `app.py` 93 %,
total 98 %). Gate: `fail_under = 95` en el pyproject del
flow; por debajo, la receta falla.

## 4. Formal Technical Reviews (FTRs)

| Gate | Artefacto | Checklist | Participantes |
|---|---|---|---|
| Phase 0→1 | specs/ + ADRs | consistencia D1-D9, links, mermaid | Usuario + arquitecto |
| Phase 2→3 | contratos vs código | shapes = spec-mcp-server | arquitecto |
| Phase 4→5 | blueprint (spec-payload-vault Approved) | tabla invocación + matriz conflictos + permisos V2 sin legacy | Usuario + arquitecto |
| Phase 5→6 | payload + skills | Anexo A acciones ejecutadas + permission fixtures + methodology e2e verdes + coherencia blueprint vs archivos generados | Usuario |

**FTR Phase 0→1 — ejecutado 2026-10-23 (T12), checklist verde** (corrido sobre `specs/`, `docs/`, `AGENTS.md` y `SPEC.md`):

* **Consistencia D1-D9:** rastreo de cada `Dn` en todos los documentos — sin acepciones contradictorias (rangos `D1-D8`/`D1-D9` y subdecisiones `D7.x`/`D9.x` coherentes con el mapeo de AGENTS.md; D3 se cita solo vía ADR-002, nunca de forma suelta; el «D4» de ADR-002 §riesgos es el piso de RAM del modelo default, coherente con D4). Cero conflictos ⇒ cero notas de mapeo nuevas.
* **Enlaces relativos:** 95 enlaces revisados — los 90 reales resuelven; los 5 que no resuelven son placeholders intencionales `](url)`/`](path)` de `docs/diagnosis/diagnosis-template.md` (plantilla a rellenar).
* **Mermaid:** los **12 bloques** de docs/specs/AGENTS/SPEC renderizados con `mermaid-cli` (headless Chrome) — **12 OK, 0 fallos**, incluido el diagrama de componentes nuevo; labels con caracteres especiales entre comillas.
* **Lint:** `markdownlint-cli2 docs specs AGENTS.md SPEC.md` → **420 antes / 420 después**, mismo conjunto de rule IDs (D12: cero errores nuevos).
* **Efecto del gate:** `spec-rag-engine.md` y `spec-embeddings.md` → **Approved** en el índice de [SPEC.md](../SPEC.md) (metadatos actualizados en ambos archivos). La aprobación de usuario del gate (**M7**) se pidió por separado tras T12 y se concedió el **2026-10-23** (Phase 1 completada; Phase 2 liberada para planeación).

## 5. Risk Management

| Riesgo | Prob | Impacto | Mitigación | Contingencia |
|---|---|---|---|---|
| Bump roto de cocoindex/lancedb | med | alto | pineos, CI con lock, capa fina TD-1 | pin downgrade; target migration (ADR-002) |
| Criterio 3 falla en HW mínimo | med | crítico | presupuesto por etapas (spec-mcp-server), ANN tuning | top_k default 3 + re-ranking ligero; revisar ADR-006 (dimensión) |
| Wizard multi-OS complejo | med | alto | CI matrix temprana (Phase 3), `--resume` | Windows en v1.1 si bloquea (Linux/macOS first) |
| Skills audit toca `.opencode/` prohibido ahora | baja | medio | diseño (Phase 4) propone vía blueprint; ejecución (Phase 5) autorizada; en el repo padre nunca | mantener inventario actual + TD-7 nota |
| Renumeración de fases introduce staleness de referencias cruzadas | med | bajo | auditoría grep por ola (tax de D10; rev. 3 la aplica); refs en ADRs congelados se REPORTAN, no se editan | corregir refs en la misma ola; registro en §8 |
| Modelo HF custom inválido/erróneo elegido (D8) | med | medio | portero test-embed + badges D8.2 + warn-never-block (D8.3) | swap rápido vía `tepochcalli config embedder` (D8.4) sin reinstalar |

## 6. Progress Metrics

* Δ-time de refresh p95, latencia search p95, tokens/consulta p95 — post-instalados en fixtures, tendencial por release.
* Done per layer: flow (filas correctas) → server (contrato) → wizard (VM limpia) → diseño (blueprint Approved) → payload (golden e2e) → aceptación (tabla §6).

## 7. Schedule and Milestones

* Hitos: M0 (specs aprobadas) → M1 índice vivo → M2 agente cita → M3 un comando instala todo → M4 blueprint workflow Approved (diseño) → M5 payload limpio → M6 v1.
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
| **D10** (reestructuración WORKFLOW, rev. 3) | El diseño del agent workflow se convierte en PHASE 4 independiente (documentación pura; gate BLUEPRINT APPROVED); renumeración: Payload→Phase 5 (ejecución literal del blueprint), E2E→Phase 6. Decisión del usuario 2026-10-21 vía question tool, EN CONTRA de la recomendación del arquitecto (sub-fases dentro de Phase 4 rechazadas) | Usuario vía question tool | docs/WORKFLOW.md rev. 3 + referencias cruzadas en specs/docs (spec-vault-structure, spec-agent-workflow, AGENTS, SPEC) + spec-payload-vault como lienzo vivo de Phase 4 + conformación de tax refs (PRD, SECURITY, TECH_DEBT, spec-rag-engine, AGENTS L32) |
| **D11** (sin ADR — corrección documental, NO cambio de decisión) | Corrección de la API de cocoindex (pre-1.0 → v1, pineado `cocoindex==1.0.25`): el esqueleto de spec-rag-engine §Proposed Solution y sus afirmaciones de Fuentes/Chunking/Embeddings se reescriben contra la API v1 verificada por spike: F1 cita vía `chunk.start.char_offset`/`chunk.end.char_offset` y `heading` derivado (no campo de `Chunk`); F2 purga automática de filas al borrar la fuente; F3 `excluded_patterns=["**/.*"]` obligatorio — include-patterns solos NO excluyen dirs-punto; F4 el splitter mide en bytes ⇒ presupuesto **`chunk_size=1536`/`chunk_overlap=192`** (decisión usuario 2026-10-21: ~1024 chars de prosa española, overlap 12,5%); F5 `localfs` sin límite de tamaño ni hook de errores ⇒ regla ">100MB/symlink roto → skipped con motivo" es nuestra; F6 `normalize_embeddings` pertenece a `embed()`, no al constructor (source instalada manda sobre la doc); E1 `device` desde `[embedding]` en `tepochcalli.toml`, **default `"cpu"`** (decisión usuario 2026-10-21); E2 idempotencia leída de stats del data plane, CLI sin paso `setup`. El motor (D1/ADR-001) NO cambia ⇒ corrección de hechos, no de decisión ⇒ **sin ADR nuevo** (regla §8) | Usuario 2026-10-21 | specs/spec-rag-engine.md (§Proposed Solution, §Fuentes, §Chunking, §Embeddings), specs/spec-embeddings.md (§tepochcalli.toml: `[chunking]` 1536/192 bytes, `[embedding] device`), docs/WORKFLOW.md §Phase 1 (objetivo: RecursiveSplitter 1536/192 bytes) |
| **D12** (sin ADR — criterio de aceptación, no decisión técnica) | Creación de `.markdownlint.json` (deshabilita únicamente MD013) y relectura del AC de lint de T1 como "cero errores NUEVOS" sobre la línea base (63 preexistentes en spec-rag-engine + WORKFLOW: 58 MD060, 3 MD034, 1 MD038, 1 MD022) en lugar de "cero errores" absoluto | Usuario 2026-10-21 | `.markdownlint.json`, AC de lint de T1 |
| **D13** (sin ADR — clarificación de esquema y AC, no cambio de decisión) | **Nulabilidad de `heading`:** el campo **siempre está presente** (ADR-005: *"la cita precisa es estructural, no opcional"*) pero su **valor puede ser `null`** cuando el documento no tiene heading padre (`.txt` plano, nota suelta). Los ACs de T5 y la métrica **M2** de T6 pasan de "5 metadatos no nulos" / "100% de filas no nulos" a **"`source_path`, `char_start`, `char_end`, `doc_kind` no nulos + `heading` presente (valor nullable)**". Esquema LanceDB de T6: columna `heading` **nullable**; `heading_before` de T4 ya devolvía `None` y lo tenía testeado, de modo que T4 no cambia. Contradicción resuelta porque tres fuentes divergían (ADR-005 "siempre"/"no opcional" vs spec-rag-engine "último heading padre **visto**" vs ACs "no nulos" vs T4 `None`) | Usuario 2026-10-21 | specs/spec-rag-engine.md (§Target — nulabilidad explícita), `tasks/todo.md` (AC de T5, métrica M2 de T6), contratos T5/T6/T9 |
| **D14** (sin ADR — corrección de layout contradictorio, decisión explícita del usuario) | **Estado del engine en `.tepochcalli/db/cocoindex/`:** spec-vault-structure se contradecía — §Layout comentaba `flow/` como *"definición del pipeline CocoIndex + estado del engine"* mientras §gitignore declara `flow/` **código fuente versionado**; un usuario que `git init` su vault (rutinario en Obsidian) commitearía el **LMDB** del engine — artefacto regenerable, pesado y platform-dependent — dentro del directorio que el producto trata como fuente. Decisión (Usuario 2026-10-21): el estado derivado del engine vive en **`.tepochcalli/db/cocoindex/`** — `db/` ya está gitignored (regla T2, sin duplicar), ya es el hogar del dato derivado (LanceDB), y la promesa de spec-rag-engine §Rollback (*"borrar `.tepochcalli/db/` y re-ejecutar la indexación inicial lo reconstruye entero"*) queda literalmente verdadera. Actualizados `app.py` (`ENGINE_STATE_RELPATH` → `db/cocoindex`; `COCOINDEX_DB` sigue teniendo precedencia) y spec-vault-structure §Layout (solo definición) | Usuario 2026-10-21 | `obsidian-workspace/.tepochcalli/flow/tepochcalli_flow/app.py`, specs/spec-vault-structure.md (§Layout) |

**Nota de mapeo D10 (lectura de ADRs congelados):** los ADR-002 (§4.1 "bench de Phase 5"), ADR-006 (§4.1 "Benchmark Phase 5"), ADR-007 (§8) y ADR-008 (§8) citan "Phase 5" con la numeración PRE-D10, donde significaba **aceptación E2E** — hoy **Phase 6**. Los ADR son Accepted y congelados por la regla de §8/AGENTS (nunca re-editar un ADR Accepted): no se re-editan; este párrafo es el mapeo canónico para quien ejecute sus benchmarks (10k/1k, Δ<30s, <500ms, contract tests D7.3/D8 → correr en Phase 6).

**Nota de mapeo D11 (lectura de ADRs congelados):** el ADR-002 §4.1 *Confirmation* describe su verificación de no-interferencia como "Tras `cocoindex setup`, `.tepochcalli/db/` contiene solo archivos Lance". `setup` es un subcomando de la CLI **pre-1.0**; en `cocoindex==1.0.25` **no existe** — la CLI de v1 expone `drop, init, ls, show, update`, y el estado del engine vive en la variable `COCOINDEX_DB` (D11/E2, verificado por spike). El ADR es Accepted y congelado por la regla de §8/AGENTS: **no se re-edita**; este párrafo es el mapeo canónico — quien ejecute esa confirmación debe leer `cocoindex setup` como `cocoindex update`.

### Lessons learned — Phase 1 (T1-T11, cierre 2026-10-23)

* **(a) Una spec congelada arrastra una API muerta pre-1.0 (D11).** `spec-rag-engine` se aprobó contra la API **pre-1.0** de cocoindex (`cocoindex setup`, campo `heading` en `Chunk`, include-patterns como mecanismo de exclusión); el spike contra el pin `cocoindex==1.0.25` la desmintió en T1 y obligó a la corrección documental **D11**. Los contratos se congelan, los **hechos de API se re-verifican**: una afirmación falsa se corrige sin ADR (es corrección de hechos, no de decisión) y queda mapeada aquí para los ADRs congelados que la heredan.
* **(b) Defecto de secuencia del plan, atrapado en el gate.** CP-B exigía el test de arquitectura (el dominio no importa infra) que el plan asignaba a **T9** — una tarea posterior: un gate no puede depender de un artefacto que aún no existe. Detectado al ejecutar el gate; el test se trasladó a sub-fase B (con RED demostrado en las dos direcciones) y T9 lo extendió poniendo `ports` en el conjunto protegido. Lección: contrastar cada CP contra las tareas que lo alimentan **antes** de ejecutar, no durante el gate.
* **(c) `RecursiveSplitter` mide bytes, y el «p95» con n=10 colapsaba al máximo.** El presupuesto es 1536/192 **bytes** (D11/F4), no chars; y con n=10 el percentil nearest-rank **es** el máximo, así que una sola query con page-fault (Docling ~2 GiB RSS empujando a la swap) hacía fallar la suite completa mientras el test aislado pasaba con holgura. Corrección: separar medición de corrección (marker `slow`, ya prescrito por T11) y publicar siempre **n + método de percentil** junto al número (el p95 de M1 es el 19.º de n=20).
* **(d) Docling cuesta más de lo que la spec estimaba.** spec-rag-engine estimaba «30 págs ≈ 5-30 s»; **medido**: 49–51 s en caliente (≈1,6–1,7 s/pág) + 29–37 s de carga fría de modelos, RSS pico 2 048–2 189 MiB (M5). TD-2 actualizado con la cifra medida. Lección: en specs, todo coste se etiqueta *estimado* hasta medirlo — la propia jerarquía de D8 lo dice: `medido > estimado > declarado`.
* **(e) `sentence-transformers` 6.x renombró el slug de caché y eso desactivó `HF_HUB_OFFLINE` en silencio.** El slug real es `models--sentence-transformers--paraphrase-…` (6.x prefija la org); el nuestro (`models--paraphrase-…`) nunca coincidió, así que el flag **no se fijaba** en el camino de caché cálido y la hermeticidad de M3(b) no probaba lo que creía probar. Corregido en `model_cache.py` con sondas que cubren las 5 ramas. Lección: un flag de hermeticidad se testea comprobando **que se fija**, no solo que el test pasa.
* **(f) El montaje fuseblk/NTFS y la herramienta `edit` mintieron.** `/mnt/HDDFish` (NTFS vía fuseblk) **descarta los bits de ejecución** (p. ej. `python -m` dejó de funcionar sobre rutas del repo) y la herramienta `edit` **reportó éxito sin persistir** la escritura — ambos mordieron durante Phase 1. Regla operativa: releer el archivo **tras cada edición**; si el cambio no está, reescribir por shell; no confiar en el exit code de una edición sobre fuse.
* **(g) El campo es `extend`, no `extends`.** En la config del toolchain (`uvx ruff` sobre `.ruff.toml`), ruff 0.17.1 rechaza `extends` con «unknown field»: el plural que «suena bien» no existe (verificado contra la doc de ruff y empíricamente, commit `a426250`). Relacionado: `extend-exclude` de `.opencode/` no es cosmético — sin él, `ruff check .` ve 2 167 hallazgos de un payload de terceros que AGENTS.md prohíbe tocar. Lección: el nombre del campo se confirma contra la doc del tool, no por intuición morfológica.
