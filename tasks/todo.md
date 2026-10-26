# TODO — Phase 2: MCP Server `tepochcalli-rag`

> Detalle completo en [tasks/plan.md](plan.md). Orden impuesto por el grafo de dependencias.
> Regla de la casa: **una calpulli = un camino completo**, con criterio de aceptación y
> verificación. Nada de Phase 3 (wizard) ni de Phase 4-5 (payload de agents/commands/skills).

**Rama:** `feat/workspace-obsidian` · **Fuente:** [docs/WORKFLOW.md](../docs/WORKFLOW.md) §Phase 2
**Rama de código:** `obsidian-workspace/.tepochcalli/mcp/` · **Rama de tests:** `tests/`
**Historial:** este fichero sustituye al TODO de Phase 1, que se conserva íntegro en el
historial de git (`git show c4f7db3:tasks/todo.md`).

---

## Sub-fase A — Anclaje

- [x] **T1 · Spike del SDK MCP v2, layout del paquete `mcp/` y esqueleto que anuncia las 4 tools**
  - Subagentes: `mcp-builder` (lead), `python-pro`, `dependency-manager` · Skills: `source-driven-development`, `api-and-interface-design`, `dependency-audit`, `clean-code`, `spec-driven-development`
  - AC: `mcp==2.3.0` + `markitdown-mcp==0.0.1a8` + `litellm>=1.106,<2` pineados; `uv.lock` regenerado; `uv sync --frozen` reproducible; **suite Phase 1 verde**; `packages` con los **dos** paquetes + `package-dir` mapeando `tepochcalli_mcp` → `mcp/`; `[project.scripts] tepochcalli-mcp`; mypy `files = ["flow","mcp"]`; ambos paquetes importables; layout `mcp/tepochcalli_mcp/{__init__,__main__,server}.py`; el server arranca por **stdio** y `tools/list` devuelve las **4 tools** con sus schemas; cada handler devuelve el placeholder con la **forma exacta** de §5 del plan; **stdout solo JSON-RPC** (logs a stderr); `mcp/` versionado (`git check-ignore` en ambos sentidos)
  - Verificar: `uv run python -m tepochcalli_mcp` + cliente del SDK → `tools/list` con 4 tools; `just ci` verde
  - 📌 **Hallazgos del spike a documentar** (el *omen mayor* del plan §3): `FastMCP`→`MCPServer`; `mcp.server.fastmcp.*`→`mcp.server.mcpserver.*` (el import viejo lanza `ModuleNotFoundError`); transporte en `run()`; **`ToolError` NO sirve** (mete texto libre y `structured_content=None`) ⇒ los handlers construyen `CallToolResult` **explícitamente** con `content[0].text` = JSON canónico e `is_error=True` en el fallo
  - Dep.: — · Tamaño: M

### ✅ CP-A · Anclaje — **5/5** ✅ (2026-10-26)
- [x] El servidor arranca por stdio y `tools/list` devuelve las **4 tools** con sus schemas
- [x] `uv sync --frozen` reproducible; **suite de Phase 1 verde** (el lock no se rompió)
- [x] Ambos paquetes importables desde el editable install
- [x] `git check-ignore` en ambos sentidos para `mcp/`
- [x] stdout del proceso contiene **solo** JSON-RPC
- ▶️ **Desbloquea T2, T3 y T5.**

---

## Sub-fase B — Los cuatro caminos

- [ ] **T2 · `search`: de la pregunta a los chunks citados**
  - Subagentes: `mcp-developer` (lead), `rag-pipeline-engineer`, `search-relevance-engineer` · Skills: `test-driven-development`, `clean-ddd-hexagonal`, `design-patterns`, `api-and-interface-design`, `clean-code`, `performance-analysis`
  - AC: `{query, took_ms, truncated, results:[{text, source_path, heading, char_start, char_end, score, offsets_ref}]}` — **7 campos siempre**, `heading` nullable (D13), `score` ∈ [0,1] descendente; consume el puerto `ChunkReader` de Phase 1 (el server **no** importa `cocoindex`/`lancedb`); `took_ms` desde la entrada del handler hasta serializar; `top_k` por omisión 5, fuera de [1,20] → `VALIDATION_ERROR`, efectivo `min(solicitado, 8)`; `path_filter` absoluto o con `..` → `VALIDATION_ERROR`; presupuesto `len(text)//4 + 25` con techo **1600** y `truncated: true` al cortar; índice inexistente → `INDEX_EMPTY`; modelo del índice ≠ config → `E_MODEL_MISMATCH` (+ `details.legacy_code`) **sin** cruzar dims; **cero** red y **cero** LLM
  - Verificar: test de integración contra vault fixture real (100 chunks) + test de arquitectura extendido a `tepochcalli_mcp` + `just quality`
  - Dep.: T1 · Tamaño: M

- [ ] **T3 · `index_refresh`: el ciclo Δ con su reporte honesto**
  - Subagentes: `mcp-developer` (lead), `python-pro` · Skills: `test-driven-development`, `solid`, `error-handling-patterns`, `clean-code`
  - AC: `{scanned, indexed, skipped, elapsed_ms, locked}` serializado **tal cual** desde `RefreshReport`; `locked: true` ⇒ sin update y las tres cuentas a cero; `E_NO_EMBEDDER` (mode `none`) **precede** a `INDEX_EMPTY`; `indexed` del data plane (nunca `stats.total`); `skipped = scanned - indexed`; `elapsed_ms` monótono; idempotencia ⇒ `indexed: 0`
  - Verificar: test de integración (crea → modifica → borra → idempotencia) + prueba del candado (dos refresh concurrentes ⇒ uno `locked: true`)
  - Dep.: T1 · Tamaño: S

- [ ] **T4 · `rag_status`: el diagnóstico que el agente puede llamar sin coste**
  - Subagentes: `mcp-developer` (lead), `api-tester` · Skills: `api-and-interface-design`, `test-driven-development`, `observability-and-instrumentation`, `clean-code`
  - AC: exactamente **4 bloques** (`embedder{mode,model,dims,provider}`, `index{rows,model_matches_config,last_refresh,db_size_bytes}`, `config{path,valid}`, `health{state,reason,fix_hint}`); `state ∈ {ok,degraded}`; `reason` solo de la taxonomía `E_*`; `fix_hint` = la solución exacta; `mode ∈ {local,api,none}`; `model_matches_config` = conjunto de `model` de las filas == config (si no ⇒ `degraded` + `E_MODEL_MISMATCH`); `last_refresh` = `max(indexed_at)` **derivado, sin estado nuevo** (o `null`); `db_size_bytes` = tamaño de `.tepochcalli/db/`; `config.path` **relativa** (nunca absoluta); modo `none` ⇒ `degraded` + `E_NO_EMBEDDER` + fix_hint de `tepochcalli config embedder`; **<200 tokens**
  - Verificar: test de integración con 3 estados (sano / sin embedder / modelo distinto) + assert de tokens <200
  - Dep.: T2, T3 · Tamaño: S

- [ ] **T5 · `add_source`: convertir, escribir y reindexar en una llamada**
  - Subagentes: `mcp-developer` (lead), `python-pro`, `security-auditor` · Skills: `test-driven-development`, `security-and-hardening`, `error-handling-patterns`, `incremental-implementation`, `clean-code`
  - AC: `{ok: true, written_to, indexed: {scanned, indexed, skipped, elapsed_ms}}`; `uri` acepta `http(s):` y `file:`; `subdir` normalizado (sin `..`, sin absolutos) y destino **siempre** dentro de `00-Resources/` (por omisión `_inbox`); conversión con la **biblioteca markitdown en proceso**; frontmatter de trazabilidad (`source_uri`, `converted_at`); nombre slug + `.md` con sufijo ante colisión; escritura **atómica** (temporal + rename); reindexa **internamente**; refresh bloqueado ⇒ `ENGINE_LOCKED`; fallo de fetch/convert ⇒ `SOURCE_UNREACHABLE` con la guía; **`file:` fuera del vault ⇒ RECHAZADO (D16)**; nunca escribe fuera de `00-Resources/`
  - Verificar: tests de integración con `http(s):` (servidor local) y `file:`; negativos: traversal, `subdir` absoluto, formato no convertible, `file:` fuera del vault
  - Dep.: T1, T3 · Tamaño: M

### ✅ CP-B · Los cuatro caminos — **5/5**
- [ ] Las 4 tools responden con la **forma exacta** del plan §5 contra un vault fixture real
- [ ] `search` devuelve citas verificables (offsets reproducibles) y `rag_status` los 4 bloques
- [ ] `add_source` escribe dentro de `00-Resources/` y reindexa
- [ ] `just quality` verde (lint + fmt + mypy `flow`+`mcp` + tests)
- [ ] **`code-reviewer` aprueba el diff de la sub-fase**
- ▶️ **Desbloquea T6 y T7.**

---

## Sub-fase C — Dialecto de errores, proveedor API y presupuestos

- [ ] **T6 · Dialecto `E_*` y el proveedor `none | litellm`**
  - Subagentes: `mcp-developer` (lead), `rag-pipeline-engineer`, `security-auditor`, `error-detective` · Skills: `error-handling-patterns`, `security-and-hardening`, `test-driven-development`, `source-driven-development`, `clean-code`
  - AC: `provider = "none"` como **3.er** valor del loader (D15; config ausente ⇒ `local`, comportamiento de Phase 1 intacto); fábrica de provider (`local` → `SentenceTransformer` pineado a `MODEL_REVISION`; `litellm` → `litellm.embedding` con la clave de `api_key_env`; `none` ⇒ `E_NO_EMBEDDER`); **escritura** con litellm ⇒ `app.py` construye `LiteLLMEmbedder(model, api_key=…)`; **lectura** con litellm ⇒ misma API y mismo modelo/dims (mismatch ⇒ `E_MODEL_MISMATCH` antes de cruzar dims); los **5** `E_*` con payload exacto `{error:{code,message,fix_hint}}`; fallos de API no cubiertos (rate limit/timeout/red) ⇒ `INTERNAL` legacy con `details`; clave **nunca** en logs/`repr`/payload; precedencia `E_NO_EMBEDDER` > `INDEX_EMPTY` > `E_MODEL_MISMATCH` > `E_API_AUTH`; enmienda de `spec-embeddings.md` §`tepochcalli.toml` + entrada en `docs/WORKFLOW.md` §8 (**sin ADR**)
  - Verificar: contract test por código `E_*` (proveedor falso inyectado) + test de que la clave no aparece en logs/`repr`/payload + suite Phase 1 verde tras tocar `app.py`
  - Dep.: T2, T3 · Tamaño: M

- [ ] **T7 · Los dos gates numéricos: ≤1600 tokens y <500 ms**
  - Subagentes: `performance-benchmarker` (lead), `test-engineer` · Skills: `performance-analysis`, `performance-optimization`, `test-driven-development`, `observability-and-instrumentation`
  - AC: fixtures **adversas** (unicode CJK/emoji, query >10 000 chars → `VALIDATION_ERROR`, chunk de 1536 bytes, PDF con tablas, multibyte); payload de `search` **≤1600 tokens** en todas ellas (con `truncated: true` al cortar, orden por score respetado); `rag_status` **<200 tokens**; bench de `search` con **p95 < 500 ms** sobre fixture de 100 archivos, publicando **n y método de percentil** (n=20, *nearest-rank*, p95 = 19.º valor); bench en `tests/benchmarks/bench_search.py` marcado `slow` + smoke con umbral generoso para CI; presupuesto por etapa **medido**: embed ≤120 ms · ANN+FTS ≤200 ms · ensamblado ≤30 ms · IPC ≤150 ms
  - Verificar: `just bench-search` (local, documentado) + `just bench-search --smoke` (CI)
  - Dep.: T2, T6 · Tamaño: M

### ✅ CP-C · Errores, API y presupuestos — **5/5**
- [ ] Los **5** códigos `E_*` emitidos con su payload exacto + precedencia verificada
- [ ] El camino `litellm` funciona en lectura **y** escritura (o queda registrado por qué no)
- [ ] Payload de `search` **≤1600 tokens** en todas las fixtures adversas
- [ ] `search` **p95 < 500 ms** **medido** (n y método publicados)
- [ ] La suite de Phase 1 sigue verde tras tocar `app.py`
- ▶️ **Desbloquea T8.**

---

## Sub-fase D — Contrato, e2e, registro y cierre

- [ ] **T8 · Contract tests D7.3 y e2e «pregunta → tool-call → JSON citado»**
  - Subagentes: `test-automation-engineer` (lead), `api-tester`, `testing-reality-checker` · Skills: `test-driven-development`, `api-spec-generation`, `doubt-driven-development`, `clean-code`
  - AC: shape **exacto** (claves y orden) de las 4 tools; en error `is_error = true` y `content[0].text` **JSON parseable** (nunca texto libre) + `structured_content` coherente; los 5 `E_*` con su payload; `rag_status` con los 4 bloques exactos y <200 tokens; instalación degradada ⇒ `search` = `E_NO_EMBEDDER` y `rag_status` = `degraded` con `fix_hint`; globs de `path_filter` válidos e inválidos (`..`, absoluto) y prefijo `00-Resources/`; **e2e real** (proceso `tepochcalli-mcp` por stdio con cliente del SDK, vault golden md+PDF) con `source_path` real, `heading` y **offsets reproducibles** (slice del original reproduce `text` en md; `offsets_ref == "extract"` en PDF); fixture golden **grabado** en `tests/fixtures/`; cero red, cero LLM
  - Verificar: `uv run python -m pytest ../../tests/e2e -v` + `just test` verde
  - Dep.: T2, T3, T4, T5, T6 · Tamaño: M

- [ ] **T9 · Registro en `opencode.json`, CI y conectividad real con OpenCode V2**
  - Subagentes: `build-engineer` (lead), `devops-engineer` · Skills: `ci-cd-and-automation`, `source-driven-development`, `incremental-implementation`
  - AC: `obsidian-workspace/opencode.json` gana `mcp.servers.tepochcalli-rag` (`type: "local"`, `command: [".tepochcalli/venv/bin/python", "-m", "tepochcalli_mcp"]`, `cwd: "."`, `environment: {"TEPOCHCALLI_ROOT": "."}`) y `mcp.servers.markitdown` (`python -m markitdown_mcp`); forma `python -m` (**no** console script, D17); merge **conservador** (solo `mcp.servers.*`, resto byte a byte); `TEPOCHCALLI_ROOT` → `TEPOCHCALLI_VAULT_ROOT` en el composition root; `.github/workflows/phase1.yml` gana un job `mcp`; `just ci` incluye mypy `flow`+`mcp` y la suite del server; el harness **lista las 4 tools** (M1); el workflow sigue sin correr en GitHub Actions (M6) — **no** se declara CI verde
  - Verificar: listado de tools desde el harness + `just ci` verde
  - Dep.: T1, T8 · Tamaño: S

- [ ] **T10 · Cierre de fase: FTR, docs y CHANGELOG**
  - Subagentes: `docs-writer` (lead), `technical-writer`, `code-reviewer` · Skills: `documentation-and-adrs`, `changelog-generate`, `code-review-and-quality`, `git-workflow-and-versioning`
  - AC: **FTR Phase 2→3** con el usuario (shapes = `spec-mcp-server`); `docs/WORKFLOW.md` §Phase 2 con estado + **métricas medidas** (n y método de percentil) + entradas §8 (D15, D16, D17, D18); `SPEC.md` índice: `spec-mcp-server` → **Approved** (y `spec-markitdown` → Approved si T5 cumple su §Testing); `docs/ARCHITECTURE.md` con el inventario y el diagrama de la capa MCP; `docs/TECH_DEBT.md` re-review TD-1…TD-11 (**TD-1 y TD-3 pagan su deuda**) + TD-12 (peso del venv); `docs/CODE_STYLE.md` (superficie tipada `flow` + `mcp`); `docs/SECURITY.md` (límite de `file:` y clave de API); `CHANGELOG.md`; **cero** cambios en `docs/UH.md`, `README.md`, `LICENSE`, `CODE_OF_CONDUCT.md`, `opencode.json` (raíz) ni `obsidian-workspace/.opencode/`
  - Verificar: `just md-lint` sin errores nuevos + revisión del diff + `git status --short` sin artefactos
  - Dep.: T7, T8, T9 · Tamaño: S

### ✅ CP-D · Gate Phase 2 → Phase 3 — **6/6**
- [ ] Contract tests D7.3 verdes (shapes, `E_*`, `rag_status`, globs)
- [ ] e2e «pregunta → tool-call → JSON citado» **grabado como fixture** y verde
- [ ] OpenCode **lista las 4 tools** desde el `opencode.json` real del workspace
- [ ] `just ci` verde
- [ ] **FTR Phase 2→3** ejecutado con el usuario
- [ ] Docs al día (WORKFLOW, SPEC, ARCHITECTURE, TECH_DEBT, CODE_STYLE, SECURITY, CHANGELOG)
- ▶️ **Desbloquea Phase 3 (wizard).**

---

## Registro de commits (Conventional Commits, uno por tarea)

| # | Tarea | Mensaje |
|---|---|---|
| 1 | T1 | `build: Ancla el SDK MCP v2 y el paquete tepochcalli_mcp` · `Co-Authored-By: Moctezuma <dev@fisherk2.com>` |
| 2 | T2 | `feat: Expone search con citas estructuradas y presupuesto` · `Co-Authored-By: Moctezuma <dev@fisherk2.com>` |
| 3 | T3 | `feat: Expone index_refresh con el reporte delta del flow` · `Co-Authored-By: Moctezuma <dev@fisherk2.com>` |
| 4 | T4 | `feat: Expone rag_status con los cuatro bloques de diagnostico` · `Co-Authored-By: Moctezuma <dev@fisherk2.com>` |
| 5 | T5 | `feat: Expone add_source con markitdown en proceso` · `Co-Authored-By: Moctezuma <dev@fisherk2.com>` |
| 6 | T6 | `feat: Anade el dialecto E_* y el proveedor litellm` · `Co-Authored-By: Moctezuma <dev@fisherk2.com>` |
| 7 | T7 | `test: Mide los presupuestos de tokens y latencia del server` · `Co-Authored-By: Moctezuma <dev@fisherk2.com>` |
| 8 | T8 | `test: Cierra los contract tests D7.3 y el e2e golden` · `Co-Authored-By: Moctezuma <dev@fisherk2.com>` |
| 9 | T9 | `ci: Registra el server MCP en el opencode.json del payload` · `Co-Authored-By: Moctezuma <dev@fisherk2.com>` |
| 10 | T10 | `docs: Cierra la Phase 2 con metricas, deuda revisada y gate` · `Co-Authored-By: Moctezuma <dev@fisherk2.com>` |

---

## Omen mayor (fail-fast en T1)

> El SDK oficial de MCP para Python **renombró su API en la v2** y el camino "fácil" de reportar
> errores no sirve para nuestro contrato:
>
> 1. `FastMCP` → `MCPServer`; `mcp.server.fastmcp.*` → `mcp.server.mcpserver.*` (el import viejo
>    lanza `ModuleNotFoundError`); el transporte se configura en `run()`.
> 2. `ToolError` mete **texto libre** en `content` y deja `structured_content = None`. El
>    contrato congelado exige `content[0].text` = **JSON canónico** con
>    `{error:{code,message,fix_hint}}` — *nunca texto libre*. ⇒ los handlers **no** lanzan
>    `ToolError`: construyen el `CallToolResult` explícitamente.
> 3. **stdout es el canal JSON-RPC** ⇒ todo log a **stderr**.
>
> T1 existe por eso: si la v2 difiere en algo más, el resto del plan se reescribe con el dato
> real en vez de con una suposición.

## Hallazgos del spike T1 (2026-10-26) — datos reales, no supuestos

Verificado contra `mcp==2.3.0` instalado y `setuptools 84.2.1`. Difiere del plan en seis puntos:

| # | Dato real | Consecuencia |
|---|---|---|
| H1 | **El `package-dir` del plan era incoherente con su layout.** `build_py.get_package_dir()` devuelve *verbatim* la clave exacta: `{"tepochcalli_mcp": "mcp"}` pondría los ficheros en `mcp/__init__.py`, contradiciendo §5 (`mcp/tepochcalli_mcp/…`) | Corregido en `pyproject.toml`: `package-dir = {"" = "flow", "tepochcalli_mcp" = "mcp/tepochcalli_mcp"}`; se conserva el **layout** del plan. El AC medible (ambos importables) es lo que se graduó |
| H2 | El editable **dejó** de ser un `.pth` de ruta plana: con dos raízes setuptools instala un **MetaPathFinder** (`__editable___tepochcalli_flow_0_1_0_finder`) que mapea nombre→ruta exacta | El riesgo de shadowing del SDK `mcp` queda descartado **por construcción**; el test anti-shadowing lo sigue vigilando |
| H3 | `mcp/server/fastmcp.py` **existe** como shim, pero solo lanza `ModuleNotFoundError` con mensaje de migración (no tiene API) | Confirma el omen: `mcp.server.fastmcp.*` sigue prohibido |
| H4 | `ToolError` ahora vive en `mcp.server.mcpserver.exceptions` (no en `mcp.types`) | Irrelevante: no se usa |
| H5 | Los tipos se importan de `mcp.types`, que reexporta la dist. hermana `mcp_types==2.3.0` | `from mcp.types import CallToolResult, TextContent` — la forma usada en `server.py` |
| H6 | Un handler anotado `-> CallToolResult` pasa **sin validación** por `convert_result` **y anula el `outputSchema`** (salida *unstructured*) | **T8:** `output_schema`/`structured_content` serán `None` **también en éxito**; el shape vive en `content[0].text` (JSON canónico). El test de T1 ya fija `output_schema is None` |
| H7 | El transporte stdio **reclama fd 1** y desvía a stderr cualquier salida espuria de bibliotecas (`mcp/server/stdio.py`) | Refuerza la regla; el test manda secuencia JSON-RPC cruda por stdin y parsea **cada** línea de stdout |

## Decisiones ya tomadas (2026-10-26, usuario)

| # | Decisión |
|---|---|
| D-a | **LiteLLM completo en Phase 2** (lectura + escritura): los 5 `E_*` son reales, no simulados |
| D-b | **markitdown en proceso** dentro de `add_source` (mismo venv, coste cero adicional) |
| D-c | **Un solo `pyproject.toml`** con los dos paquetes (`package-dir` mapeando `tepochcalli_mcp` → `mcp/`) |
| D-d | Escritura autorizada en `.tepochcalli/mcp/` **y** en `obsidian-workspace/opencode.json`; `.opencode/` del vault sigue vedado |
| D15 | `provider = "none"` como 3.er valor válido (enmienda a `spec-embeddings`, sin ADR) |
| D16 | `add_source` **rechaza** `file:` fuera del vault (versión estricta del conflicto entre `spec-mcp-server` y `spec-markitdown`) |
| D17 | Invocación `python -m tepochcalli_mcp` (el bit de ejecución se pierde en NTFS — lección (f) de Phase 1) |
| D18 | `markitdown-mcp` tal cual (`markitdown[all]`, +142 MB, 49 paquetes) |
