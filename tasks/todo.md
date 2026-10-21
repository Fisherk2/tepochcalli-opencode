# TODO — Phase 1: Engine + Flow

> Detalle completo en [tasks/plan.md](plan.md). Orden imposed por el grafo de dependencias.
> Regla de la casa: **una calpulli = un camino completo**, con criterio de aceptación y verificación.
> Nada de Phase 2 (MCP), Phase 3 (wizard) ni payload de agents/commands/skills.

**Rama:** `feat/workspace-obsidian` · **Fuente:** [docs/WORKFLOW.md](../docs/WORKFLOW.md) §Phase 1
**Rama de código:** `obsidian-workspace/.tepochcalli/` · **Rama de tests:** `tests/phase1/`

---

## Sub-fase A — Anclaje y cimientos

- [ ] **T1 · Spike: anclar la API real de CocoIndex v1 y enmendar la spec congelada**
  - Subagentes: `python-pro`, `tool-evaluator`, `minimal-change-engineer` · Skills: `source-driven-development`, `find-docs`, `documentation-and-adrs`, `clean-code`
  - AC: venv 3.12 con `cocoindex==1.0.25`; spike `localfs → split → embed → LanceDB → update_blocking` verde; **hallazgos documentados** (offsets de chunk, purga al borrar, `PatternFilePathMatcher`); `specs/spec-rag-engine.md` §Proposed Solution actualizado a API v1; `docs/WORKFLOW.md` §8 con entrada **D11** (no-ADR); `docs/UH.md` / `README.md` / `LICENSE` / `opencode.json` / `obsidian-workspace/.opencode/` intactos
  - Verificar: script del spike sin `ImportError`/`AttributeError`; **la enmienda no introduce errores markdownlint nuevos** (baseline pre-existente: 63 = 58 MD060 + 3 MD034 + 1 MD038 + 1 MD022); `git diff --stat` toca solo `specs/`, `docs/` y `.markdownlint.json`
  - ⚠️ **AC de lint redefinido por el usuario (2026-10-21):** el repo **no tenía** `.markdownlint.json` aunque `docs/CODE_STYLE.md` prometía «MD013 desactivado». T1 lo crea (solo `MD013:false`, para no apagar reglas que señalan fallos reales) y el AC pasa de «markdownlint limpio» a **«cero errores nuevos»**; los 63 pre-existentes quedan como deuda pre-existente. Amplía el diff de T1 a `.markdownlint.json` — autorizado explícitamente.
  - Dep.: — · Tamaño: M

- [ ] **T2 · Cimientos del paquete: pyproject pineado, uv.lock, venv 3.12, gitignore del runtime**
  - Subagentes: `python-pro`, `dependency-manager` · Skills: `source-driven-development`, `dependency-audit`, `env-setup`, `clean-code`
  - AC: pines `cocoindex==1.0.25` (+extra `lancedb`), `sentence-transformers>=3.3.1,<4`, `docling>=2,<3` (sin GPU); `uv.lock` commiteado; `.python-version`=3.12; `tepochcalli_flow` importable; `.gitignore` ignora `{venv,db,models,bin,config}` y **no** ignora `{flow,pyproject.toml,uv.lock}`; ruff `ANN` activo y limpio; auditoría de CVEs en el commit
  - Verificar: `rm -rf .tepochcalli/venv && uv sync && uv run pytest` desde cero; `git check-ignore -v` en ambas direcciones
  - Dep.: T1 · Tamaño: M

- [ ] **T3 · Config loader y resolución del cache de modelos (cierra la decisión `SBERT_HOME`)**
  - Subagentes: `python-pro`, `security-auditor` · Skills: `solid`, `clean-code`, `test-driven-development`, `security-and-hardening`
  - AC: `tomllib` con fallbacks a default (MiniLM/384d/1024/128/top_k=5); `provider` ∈ {local, litellm}; `api_key_env` nunca en `repr`/logs; `SENTENCE_TRANSFORMERS_HOME` y `HF_HOME` → `<vault>/.tepochcalli/models`; `tepochcalli.toml.example` commiteado
  - Verificar: `uv run pytest tests/phase1/test_config.py -v` verde
  - Dep.: T2 · Tamaño: S

### ⛔ CP-A · Cimientos
- [ ] API v1 probada y spec corregida
- [ ] `uv sync` reproducible desde cero
- [ ] Pines exactos + ruff limpio
- [ ] `tepochcalli.toml` real nunca commiteable
- [ ] Revisión humana de la enmienda de la spec

---

## Sub-fase B — Camino Markdown completo

- [ ] **T4 · Dominio de cita (puro): source_path, heading, char_start/char_end, doc_kind, model**
  - Subagentes: `rag-pipeline-engineer`, `nlp-engineer` · Skills: `solid`, `clean-code`, `test-driven-development`, `clean-ddd-hexagonal`, `design-patterns`
  - AC: `source_path` POSIX relativo al vault con prefijo `00-Resources/`; `heading` = último heading padre; offsets de **carácter** verificables contra el texto extraído; `doc_kind` ∈ {md, markdown, txt, pdf}; `model` = embedder configurado; 100% cobertura del módulo
  - Verificar: `uv run pytest tests/phase1/test_citation.py --cov=tepochcalli_flow.citation --cov-fail-under=100`
  - Dep.: T3 · Tamaño: M

- [ ] **T5 · Fuentes y parseo Markdown/TXT: whitelist, exclusiones y chunks en memoria**
  - Subagentes: `data-engineer`, `rag-pipeline-engineer`, `test-engineer` · Skills: `test-driven-development`, `clean-code`, `solid`, `design-patterns`, `clean-ddd-hexagonal`
  - AC: `localfs.walk_dir` recursivo con whitelist y exclusión de segmentos con punto y `.git/**`; >100MB / symlink roto / ilegible → `skipped` con motivo sin abortar; `RecursiveSplitter(1024/128)`; chunks con los 5 metadatos no nulos; fixture de anidamiento libre (2 indexados, 1 excluido)
  - Verificar: `uv run pytest tests/phase1/test_parsers.py -v`
  - Dep.: T4 · Tamaño: M

- [ ] **T6 · Embeddings y target LanceDB: escritura de la fila completa**
  - Subagentes: `rag-pipeline-engineer`, `nlp-engineer`, `data-engineer` · Skills: `source-driven-development`, `clean-ddd-hexagonal`, `design-patterns`, `test-driven-development`, `clean-code`
  - AC: `SentenceTransformerEmbedder` en el lifespan con `ContextKey(detect_change=True)`, dims=384; esquema exacto `{id, source_path, doc_kind, heading, char_start, char_end, text, vector[384], model, indexed_at}`; base `.tepochcalli/db/tepochcalli.lance` tabla `chunks`; **M2** 100% metadatos no nulos; índices ANN + FTS sobre `text`; **M3** 0 llamadas LLM (test que bloquea la red)
  - Verificar: `uv run pytest tests/phase1/test_pipeline_integration.py -v` + inspección de la tabla
  - Dep.: T5 · Tamaño: M

### ⛔ CP-B · Camino Markdown
- [ ] Un `.md` produce filas completas en LanceDB
- [ ] M2 (100% metadatos de cita no nulos)
- [ ] M3 (0 llamadas LLM observables)
- [ ] Test de arquitectura: el dominio no importa infra
- [ ] `code-reviewer` aprueba el diff de la sub-fase

---

## Sub-fase C — PDF, incrementalidad y puerto de lectura

- [ ] **T7 · Ruta PDF con Docling (CPU) y exclusión por tamaño**
  - Subagentes: `data-engineer`, `rag-pipeline-engineer`, `performance-benchmarker` · Skills: `source-driven-development`, `performance-analysis`, `test-driven-development`, `clean-code`
  - AC: Docling en CPU con jerarquía de headings conservada; `doc_kind="pdf"`; offsets referidos al **markdown extraído** (documentado); **M5** costo real medido y reportado; PDF >100MB → `skipped` sin abortar el delta; fixture PDF real (1-2 páginas) con heading no nulo
  - Verificar: `uv run pytest tests/phase1/test_pdf.py -v`; tiempo de parseo en el commit
  - Dep.: T6 · Tamaño: M

- [ ] **T8 · Semántica incremental Δ, lock de un solo proceso y métricas**
  - Subagentes: `rag-pipeline-engineer`, `python-pro`, `test-engineer` · Skills: `test-driven-development`, `solid`, `clean-code`, `error-handling-patterns`, `observability-and-instrumentation`
  - AC: 2ª pasada sin cambios → `indexed=0`; modificado → solo sus chunks; borrado → filas purgadas (o reconciliación explícita documentada); refresh concurrente → `locked:true` **sin escribir**; métricas `{scanned, indexed, skipped, elapsed_ms, locked}` con reloj monotónico; retorno tipado sin `Any`, reutilizable tal cual por el MCP de Phase 2
  - Verificar: `uv run pytest tests/phase1/test_delta.py -v`
  - Dep.: T6 · Tamaño: M

- [ ] **T9 · Puerto de lectura `ChunkReader` + adaptador LanceDB (fila queryable)**
  - Subagentes: `software-architect`, `search-relevance-engineer`, `python-pro` · Skills: `clean-ddd-hexagonal`, `api-and-interface-design`, `design-patterns`, `test-driven-development`, `clean-code`
  - AC: protocolo `ChunkReader` sin deps de LanceDB/CocoIndex; adaptador devuelve `{text, source_path, heading, char_start, char_end, score}` (campos congelados de `spec-mcp-server`); `score` ∈ [0,1] con orden descendente; `path_filter` como glob relativo al vault; verificador CLI ejecutable; test de arquitectura con `ast`; búsqueda ANN+FTS <500ms p95 en corpus dorado (preliminar)
  - Verificar: `uv run pytest tests/phase1/test_read_port.py -v` + verificador manual
  - Dep.: T6 · Tamaño: M

### ⛔ CP-C · PDF + Δ + lectura
- [ ] PDF produce chunks con heading
- [ ] Δ verde en los 5 escenarios (add/modify/delete/idempotencia/lock)
- [ ] M4 (fila queryable con los 4 campos)
- [ ] M5 con costo real medido
- [ ] Puerto `ChunkReader` congelado para Phase 2

---

## Sub-fase D — Medición, CI y cierre

- [ ] **T10 · Bench Δ<30s p95 (20 corridas) + reporte del costo de PDF**
  - Subagentes: `performance-benchmarker`, `data-engineer` · Skills: `performance-analysis`, `performance-optimization`, `observability-and-instrumentation`, `documentation-and-adrs`
  - AC: script reproducible con corpus de 50 md/txt y 20 corridas; **M1** p95 < 30.000 ms con host documentado; PDFs grandes excluidos y reportados aparte; cifra **medida** en `docs/WORKFLOW.md`; bench idempotente sobre vault temporal
  - Verificar: el número publicado es idéntico al del output del script
  - Dep.: T8 · Tamaño: S

- [ ] **T11 · CI de Phase 1 (ruff + unit/integration smoke)**
  - Subagentes: `devops-engineer`, `python-pro` · Skills: `ci-cd-and-automation`, `source-driven-development`, `clean-code`
  - AC: `.github/workflows/phase1.yml` en PR y push (`uv sync --frozen` → ruff check → ruff format --check → `pytest -m "not slow"`); caché HF por revisión pineada; smoke Δ de 1 corrida con umbral generoso (el p95 **no** corre en CI); el workflow no toca `db/models/config/venv` del repo
  - Verificar: push → workflow verde; PR con lint roto → workflow rojo (el gate **muerde**)
  - Dep.: T6, T10 · Tamaño: S

- [ ] **T12 · Cierre de fase: FTR, métricas, deuda técnica y status de specs**
  - Subagentes: `technical-writer`, `code-reviewer`, `security-auditor`, `minimal-change-engineer` · Skills: `documentation-and-adrs`, `code-review-and-quality`, `git-workflow-and-versioning`, `architecture-diagrams`, `security-and-hardening`
  - AC: `docs/WORKFLOW.md` §Phase 1 con M1/M2/M3 medidas + §8 Lessons learned; `docs/TECH_DEBT.md` re-revisado (TD-1..TD-4); `SPEC.md` con `spec-rag-engine` y `spec-embeddings` en `Approved`; FTR Phase 0→1 con checklist D1-D9 y mermaid válido; `docs/ARCHITECTURE.md` con inventory + diagrama de componentes; checklist pre-commit de `AGENTS.md` verificado (`.opencode/` intacto); `git status --short` sin `venv/db/models/bin/config`; **M7** aprobación explícita del usuario
  - Verificar: `markdownlint docs specs AGENTS.md SPEC.md` → 0 errores; `git diff --stat main...HEAD` solo lo previsto
  - Dep.: T10, T11 · Tamaño: M

### ⛔ CP-D · Gate Phase 1 → Phase 2
- [ ] M1 (p95 < 30s) con cifra y máquina documentadas
- [ ] M6 (CI verde y **muerde**)
- [ ] FTR Phase 0→1 con checklist D1-D9
- [ ] `SPEC.md` y `docs/TECH_DEBT.md` al día
- [ ] **M7: aprobación explícita del usuario para arrancar Phase 2**

---

## Registro de commits (Conventional Commits, uno por tarea)

| # | Task | Mensaje previsto | Trailer |
|---|---|---|---|
| 1 | T1 | `docs: Ancla la API v1 de CocoIndex y corrige la spec del flow` | `Co-Authored-By: Moctezuma <dev@fisherk2.com>` |
| 2 | T2 | `build: Funda el runtime .tepochcalli con deps pineadas y uv.lock` | `Co-Authored-By: Moctezuma <dev@fisherk2.com>` |
| 3 | T3 | `feat: Añade config loader y cache de modelos del flow` | `Co-Authored-By: Moctezuma <dev@fisherk2.com>` |
| 4 | T4 | `feat: Deriva metadatos de cita de cada chunk del flow` | `Co-Authored-By: Moctezuma <dev@fisherk2.com>` |
| 5 | T5 | `feat: Indexa Markdown y TXT desde 00-Resources con exclusiones` | `Co-Authored-By: Moctezuma <dev@fisherk2.com>` |
| 6 | T6 | `feat: Escribe chunks citados con embeddings en LanceDB` | `Co-Authored-By: Moctezuma <dev@fisherk2.com>` |
| 7 | T7 | `feat: Parsea PDF con Docling en CPU para chunks citados` | `Co-Authored-By: Moctezuma <dev@fisherk2.com>` |
| 8 | T8 | `feat: Indexa solo el delta con lock de un proceso y metricas` | `Co-Authored-By: Moctezuma <dev@fisherk2.com>` |
| 9 | T9 | `feat: Expone el puerto de lectura ChunkReader sobre LanceDB` | `Co-Authored-By: Moctezuma <dev@fisherk2.com>` |
| 10 | T10 | `test: Mide el bench de delta p95 y documenta el resultado` | `Co-Authored-By: Moctezuma <dev@fisherk2.com>` |
| 11 | T11 | `ci: Anade el workflow de Phase 1 con unit e integracion smoke` | `Co-Authored-By: Moctezuma <dev@fisherk2.com>` |
| 12 | T12 | `docs: Cierra la Phase 1 con metricas, deuda revisada y gate` | `Co-Authored-By: Moctezuma <dev@fisherk2.com>` |
