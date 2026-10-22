# TODO — Phase 1: Engine + Flow

> Detalle completo en [tasks/plan.md](plan.md). Orden imposed por el grafo de dependencias.
> Regla de la casa: **una calpulli = un camino completo**, con criterio de aceptación y verificación.
> Nada de Phase 2 (MCP), Phase 3 (wizard) ni payload de agents/commands/skills.

**Rama:** `feat/workspace-obsidian` · **Fuente:** [docs/WORKFLOW.md](../docs/WORKFLOW.md) §Phase 1
**Rama de código:** `obsidian-workspace/.tepochcalli/` · **Rama de tests:** `tests/phase1/`

---

## Sub-fase A — Anclaje y cimientos

- [x] **T1 · Spike: anclar la API real de CocoIndex v1 y enmendar la spec congelada** ✅ *hecho — `0978790`*
  - Subagentes: `python-pro`, `tool-evaluator`, `minimal-change-engineer` · Skills: `source-driven-development`, `find-docs`, `documentation-and-adrs`, `clean-code`
  - AC: venv 3.12 con `cocoindex==1.0.25`; spike `localfs → split → embed → LanceDB → update_blocking` verde; **hallazgos documentados** (offsets de chunk, purga al borrar, `PatternFilePathMatcher`); `specs/spec-rag-engine.md` §Proposed Solution actualizado a API v1; `docs/WORKFLOW.md` §8 con entrada **D11** (no-ADR); `docs/UH.md` / `README.md` / `LICENSE` / `opencode.json` / `obsidian-workspace/.opencode/` intactos
  - Verificar: script del spike sin `ImportError`/`AttributeError`; **la enmienda no introduce errores markdownlint nuevos** (baseline pre-existente: 63 = 58 MD060 + 3 MD034 + 1 MD038 + 1 MD022); `git diff --stat` toca solo `specs/`, `docs/` y `.markdownlint.json`
  - ⚠️ **AC de lint redefinido por el usuario (2026-10-21):** el repo **no tenía** `.markdownlint.json` aunque `docs/CODE_STYLE.md` prometía «MD013 desactivado». T1 lo crea (solo `MD013:false`, para no apagar reglas que señalan fallos reales) y el AC pasa de «markdownlint limpio» a **«cero errores nuevos»**; los 63 pre-existentes quedan como deuda pre-existente. Amplía el diff de T1 a `.markdownlint.json` — autorizado explícitamente.
  - 📌 **Hechos verificados por spike (RED antes de GREEN, 9/9 aserciones):** F1 `chunk.start.char_offset` da cita exacta 51/51, `heading` **derivado** (no campo de `Chunk`) → recae sobre **T4** · F2 purga automática (target gestionado + `mount_each` + `IdGenerator`) · **F3 trampa**: `included_patterns` solos **NO** excluyen dirs-punto → `excluded_patterns=["**/.*"]` obligatorio → recae sobre **T5** · **F4 splitter mide BYTES** → presupuesto **1536/192** (decisión usuario) · **F5 `localfs` sin límite de tamaño ni hook** → el ">100MB skipped con motivo" es nuestro → recae sobre **T5** · F6 `normalize_embeddings` va en `embed()` · **E1 GPU `sm_61` sin kernels** → `[embedding] device` default `"cpu"` (decisión usuario) → recae sobre **T3/T6** · E2 idempotencia se lee del data plane, no del total.
  - 📦 Versions ancladas: `cocoindex==1.0.25` · `lancedb==0.40.0` · `sentence-transformers==6.2.0` · `torch==2.14.1` · CPython 3.12.14. Extras **con guion**: `cocoindex[lancedb,sentence-transformers]`.
  - Dep.: — · Tamaño: M

- [x] **T2 · Cimientos del paquete: pyproject pineado, uv.lock, venv 3.12, gitignore del runtime** ✅ *hecho — `3716d99` + `3f1b292`*
  - Subagentes: `python-pro`, `dependency-manager` · Skills: `source-driven-development`, `dependency-audit`, `env-setup`, `clean-code`
  - AC: pines `cocoindex==1.0.25` (+extra `lancedb`), `sentence-transformers>=3.3.1,<4`, `docling>=2,<3` (sin GPU); `uv.lock` commiteado; `.python-version`=3.12; `tepochcalli_flow` importable; `.gitignore` ignora `{venv,db,models,bin,config}` y **no** ignora `{flow,pyproject.toml,uv.lock}`; ruff `ANN` activo y limpio; auditoría de CVEs en el commit
  - Verificar: `rm -rf .tepochcalli/venv && uv sync && uv run pytest` desde cero; `git check-ignore -v` en ambas direcciones
  - Dep.: T1 · Tamaño: M
  - ✅ **Verificado:** `uv.lock` con `cocoindex[lancedb,sentence-transformers]==1.0.25` + `docling>=2,<3`; `lancedb`/`pyarrow` **no** pineados aparte; `.python-version`=3.12; paquete editable con `__version__`; `git check-ignore` en ambas direcciones (con barra final — sin ella git no reconoce dirs inexistentes); ruff `ANN` + `line-length=100` limpio; auditoría CVE/licencia **sin bloqueantes** (las 9 versiones no afectadas, licencias MIT/Apache-2.0, compatibles con el LICENSE MIT del repo) cerrada en `3f1b292`.
  - 📌 **Hallazgos que recaen en tareas posteriores:**
    * **NTFS rompe los bits ejecutables** — `/mnt/HDDFish` es `fuseblk`, `chmod +x` devuelve `644`. Los scripts de `venv/bin/` son inejecutables → `uv run pytest` / `uv run ruff` caen al Python global 3.14. **Workarounds: `uv run python -m <mod>` y `uvx ruff@<lock>`** (servidos desde ext4). ⚠️ Afecta a **Phase 3**: el `venv/bin/tepochcalli-mcp` será inejecutable si el vault del usuario vive en NTFS bajo Linux → nota en ADR-004 / spec-mcp-server.
    * **`UV_PROJECT_ENVIRONMENT=venv` es obligatorio** — uv 0.12.9 rechaza `project-environment` en `[tool.uv]`; solo existe vía env var. T3+ y el wizard de Phase 3 deben exportarlo.
    * **torch a ruedas CPU** (`3f1b292`): venv **6,3 GB → 2,0 GB**, paquetes CUDA en lock **19 → 0**, `torch 2.14.1+cpu`. Requiere declarar `torch`/`torchvision` como dependencias **directas** porque `tool.uv.sources` no aplica a transitivas (upstream `astral-sh/uv#9446`); `torchvision` debía moverse también (ABI CUDA → `operator torchvision::nms does not exist`, revienta solo al parsear PDF → habría estallado en **T7**). Las 9 aserciones del spike re-verificadas en verde bajo CPU.
    * **TRD §4 queda stale** — planifica `sentence-transformers >=3,<4` pero el lock fija **6.2.0**. Decisión pendiente del usuario en un cambio aparte (T2 no lo editó por alcance).
    * **docling pineado por rango** `>=2,<3` (advisory de la auditoría): el `uv.lock` es la única garantía de reproducibilidad.

- [x] **T3 · Config loader y resolución del cache de modelos (cierra la decisión `SBERT_HOME`)** ✅ *hecho — `ba0fad5`*
  - Subagentes: `python-pro`, `security-auditor` · Skills: `solid`, `clean-code`, `test-driven-development`, `security-and-hardening`
  - AC: `tomllib` con fallbacks a default (**MiniLM / 384d / `chunk_size=1536` / `overlap=192` bytes / `top_k=5`** — *corregido por D11*); `provider` ∈ {local, litellm}; **`device` default `"cpu"`** (E1, añadido por D11); `api_key_env` **nunca** en `repr`/logs; `SENTENCE_TRANSFORMERS_HOME` y `HF_HOME` → `<vault>/.tepochcalli/models`; `tepochcalli.toml.example` commiteado y **conforme a `spec-embeddings.md` §tepochcalli.toml** (que ya lleva 1536/192 y `device`)
  - Verificar: `UV_PROJECT_ENVIRONMENT=venv uv run python -m pytest tests/phase1/test_config.py -v` verde *(NTFS: sin `python -m` no funciona)*
  - Dep.: T2 · Tamaño: S
  - ✅ **Verificado:** `load_config(vault_root) -> Config` con `tomllib` (stdlib, 0 deps nuevas); política **nunca lanza** (ausente→defaults, malformado/clave desconocida/tipo erróneo/provider inválido→warning+default); `config.py` **sin** `cocoindex`/`lancedb` (frontera que verifica T9); `apply_model_cache_env()` único punto que fija `SENTENCE_TRANSFORMERS_HOME`/`HF_HOME`; `api_key_env` guarda solo el **nombre** y un test con sentinela afirma que no aparece en `repr`/`str`/f-string/logs; **11 passed**, ruff limpio; `git check-ignore` en ambos sentidos (`.example` NO ignorado, real SÍ).
  - 📌 **Nota de ubicación:** el `.example` va en la raíz de `.tepochcalli/`, **no** en `config/` — la regla T2 ignora el directorio entero y un `.example` ahí dentro sería engullido. Es el patrón de `.env.example`; en Phase 3 el wizard escribe el archivo real, que el usuario final probablemente no copie a mano.

### ✅ CP-A · Cimientos — **5/5 GREEN (sub-fase A completa)**
- [x] API v1 probada y spec corregida ✅ *(T1, `0978790`)*
- [x] Revisión humana de la enmienda ✅ *(usuario: «Continua», 2026-10-21)*
- [x] `uv sync` reproducible desde cero ✅ *(T2, `3716d99`)*
- [x] Pines exactos + ruff limpio ✅ *(T2; auditoría CVE sin bloqueantes en `3f1b292`)*
- [x] `tepochcalli.toml` real nunca commiteable ✅ *(T3, `ba0fad5` — verificado en ambas direcciones)*
- ▶️ **Desbloquea T4 · Dominio de cita** — inicio de la Sub-fase B.

---

## Sub-fase B — Camino Markdown completo

- [x] **T4 · Dominio de cita (puro): source_path, heading, char_start/char_end, doc_kind, model** ✅ *hecho — `af3a7d1`*
  - Subagentes: `rag-pipeline-engineer`, `nlp-engineer` · Skills: `solid`, `clean-code`, `test-driven-development`, `clean-ddd-hexagonal`, `design-patterns`
  - AC: `source_path` POSIX relativo al vault con prefijo `00-Resources/`; `heading` = último heading padre; offsets de **carácter** verificables contra el texto extraído; `doc_kind` ∈ {md, markdown, txt, pdf}; `model` = embedder configurado; 100% cobertura del módulo
  - Verificar: `uv run pytest tests/phase1/test_citation.py --cov=tepochcalli_flow.citation --cov-fail-under=100`
  - Dep.: T3 · Tamaño: M
  - ✅ **Verificado:** `citation.py` (205 líneas) con **0 imports** de `cocoindex`/`lancedb` (grep) — API solo con primitivos; **cobertura 100%** (92 statements, 0 perdidos); **34 tests nuevos → 45 en la suite**, sin regresiones; ruff limpio; literal del modelo en `config.py` **una sola vez**.
  - 🔑 **Decisiones FROZEN heredables:**
    * **`heading` es `None` (nunca `""`) sin padre → el esquema de LanceDB de T6 DEBE permitir null.**
    * `heading_before(text, char_start)` — solo ATX `#`..`######`; **setext NO soportado** (limitación documentada); NO cuentan headings dentro de bloques cercados ni code spans inline ni `#` posteriores al offset; YAML frontmatter ignorado.
    * `validate_offsets` lanza `CitationError`; `doc_kind_for` lanza `UnsupportedDocKindError` en extensión desconocida (**nunca** degrada a `txt`).
    * `verify_slice_identity(text, char_start, char_end, chunk_text) -> bool` — assert barato para T5/T6 (identidad F1 verificada 51/51).
    * `model_id(config)` importa `DEFAULT_EMBEDDING_MODEL` de `config.py`.
  - ⚠️ **Desviación de plan registrada:** la segunda mitad del plan (revisión `nlp-engineer` sobre derivación de headings) **se pliega al gate CP-B**, que ya exige `code-reviewer` sobre el diff de la sub-fase — con 34 tests y cobertura 100% incluyendo los casos de fence/code-span, un pase aparte redundaría. CP-B debe scrutinizar explícitamente la derivación de `heading`.
  - 📌 **Ruta de test corregida:** desde `obsidian-workspace/.tepochcalli/` los tests se referencian como `../../tests/phase1/` (repo-root-relative en las ACs no resuelven desde ahí).

- [x] **T5 · Fuentes y parseo Markdown/TXT: whitelist, exclusiones y chunks en memoria** ✅ *hecho — `b7c8f09`*
  - Subagentes: `data-engineer`, `rag-pipeline-engineer`, `test-engineer` · Skills: `test-driven-development`, `clean-code`, `solid`, `design-patterns`, `clean-ddd-hexagonal`
  - AC: `localfs.walk_dir` recursivo con whitelist y exclusión de segmentos con punto y `.git/**`; >100MB / symlink roto / ilegible → `skipped` con motivo sin abortar; **`RecursiveSplitter(chunk_size=1536, chunk_overlap=192)` en BYTES** (*corregido por D11*); chunks con `source_path`, `char_start`, `char_end`, `doc_kind` **no nulos** y `heading` **presente (nullable, D13)**; fixture de anidamiento libre (2 indexados, 1 excluido)
  - Verificar: `UV_PROJECT_ENVIRONMENT=venv uv run python -m pytest ../../tests/phase1/test_parsers.py -v` *(desde `.tepochcalli/`; NTFS: sin `python -m` no funciona)*
  - Dep.: T4 · Tamaño: M
  - ✅ **Verificado:** **65 passed** (45+20), ruff limpio, `EXCLUDED_PATTERNS=("**/.*","**/.git/**")` con su propio test, cita **no** duplicada (importada de `.citation`), frontera de dominio intacta, fixture con `.oculto/` y `blob.bin`.
  - 📌 **Hallazgos y decisiones de T5:**
    * `source.SkipReason(StrEnum)`: `oversized` (umbral **inyectable**, default 100MB — evita fixtures de 100MB), `broken_symlink`, `unreadable`, `pdf_parser_pending` (alcance T5: `.pdf` en whitelist pero se salta con motivo hasta T7).
    * **F5 refino:** el chequeo va sobre la **ruta resuelta**, no en un `FilePathMatcher`, porque `walk_dir` descarta los symlinks rotos **antes** de que el matcher los vea — `walk_sources` combina el walk real con un barrido de dirents. Empírico, no supuesto.
    * **Comportamiento del splitter medido:** corte **limpio** en fronteras de heading `##` (holgura 2 bytes, **sin overlap**) mientras la prosa sí se solapa hasta el presupuesto (78/116 B). Coherente con la intención del spec: el overlap protege el corte a media frase, no la frontera de sección. *No es un bug — no «arreglar».*
    * ⚠️ **Commit message desviado** del previsto en la tabla: era *"Indexa Markdown y TXT desde 00-Resources"* y T5 **no persiste**; decir "indexa" habría sido engañoso.

- [x] **T6 · Embeddings y target LanceDB: escritura de la fila completa** ✅ *hecho — `d74a8a5` + D14 `1724b0d`*
  - Subagentes: `rag-pipeline-engineer`, `nlp-engineer`, `data-engineer` · Skills: `source-driven-development`, `clean-ddd-hexagonal`, `design-patterns`, `test-driven-development`, `clean-code`
  - AC: `SentenceTransformerEmbedder(model_name_or_path=..., device=...)` en el lifespan con `ContextKey(detect_change=True)`, dims=384; esquema exacto `{id, source_path, doc_kind, heading, char_start, char_end, text, vector[384], model, indexed_at}` con **`heading` nullable (D13)**; base `.tepochcalli/db/tepochcalli.lance` tabla `chunks`; **M2** = `source_path`/`char_start`/`char_end`/`doc_kind` **no nulos** + `heading` presente en 100% de filas; índices ANN + FTS sobre `text`; **M3** 0 llamadas LLM (test que bloquea la red)
  - Verificar: `UV_PROJECT_ENVIRONMENT=venv uv run python -m pytest ../../tests/phase1/test_pipeline_integration.py -v` + inspección de la tabla
  - Dep.: T5 · Tamaño: M
  - ✅ **Verificado:** **100 tests** totales. Fila escrita con los 10 campos; dims resueltas por `Annotated[NDArray, EMBEDDER]` (sin literal `384`); índices `IvfPq` sobre `embedding` + `FTS` sobre `text`, ambos consultados; F2 trio completo; **M2** probado fila a fila re-sliceando desde disco (5/5); **M3** probado por dos vías y con **canario** (guard con dientes, `urlopen` bloqueado y registrado); D13 verificado en ambas direcciones (3 filas `heading=null` + 2 con ATX).
  - 🔑 **D14 (hallazgo de mi verificación):** el estado del engine (LMDB) quedaba en `.tepochcalli/flow/cocoindex`, directorio que la spec declara **código fuente commiteable** → un usuario que `git init` su vault commitearía LMDB. Movido a **`.tepochcalli/db/cocoindex/`** (ya gitignored, ya hogar del dato derivado), con lo que el rollback de `spec-rag-engine` (*"borrar `db/` reconstruye todo"*) queda literalmente verdadero. Corregido el comentario contradictorio de `spec-vault-structure` §Layout; D14 en `WORKFLOW §8`.

### ✅ CP-B · Camino Markdown — **5/5 GREEN (sub-fase B completa)**
- [x] Un `.md` produce filas completas en LanceDB ✅ *(T6, `d74a8a5` — 100 filas-probe y el fixture escribe 5/5)*
- [x] **M2** — `source_path`/`char_start`/`char_end`/`doc_kind` no nulos + `heading` presente en 100% de filas *(D13; probado fila a fila re-sliceando desde disco, 5/5)*
- [x] **M3** — 0 llamadas LLM observables ✅ *(dos vías: sin `litellm`/`openai`/`anthropic` en `sys.modules` + `socket.connect` bloqueado con **canario** que prueba que el guard muerde)*
- [x] Test de arquitectura: el dominio no importa infra ✅ *(**trasladado de T9 a aquí** — corregido un defecto de secuencia del plan; test transitivo por `ast` con RED demostrado en las dos direcciones)*
- [x] **`code-reviewer` aprueba el diff de la sub-fase** ✅ — *REQUEST CHANGES con 0 blockers → **`1724b0d` aplicó los 7 should-fix** y quedó en verde* (100 tests)
- 📌 **Lo que aportó la revisión** (no duplicar el esfuerzo en C): decoder unificado en UTF-8 estricto, BOM ya no falsea el frontmatter, ids entre ficheros fijados, `__init__` en el cierre de arquitectura, `heading_before` ahora O(documento), frontera de symlinks, sección de symlinks en SECURITY.md.
- 📌 **Defecto de plan detectado y corregido:** CP-B exigía el test de arquitectura pero el plan lo asignaba a T9 (sub-fase siguiente) — un gate no puede depender de una tarea posterior.
- ▶️ **Desbloquea Sub-fase C: T7 (PDF), T8 (Δ), T9 (puerto de lectura) — paralelizables entre sí.**

---

## Sub-fase C — PDF, incrementalidad y puerto de lectura

- [ ] **T7 · Ruta PDF con Docling (CPU) y exclusión por tamaño**
  - Subagentes: `data-engineer`, `rag-pipeline-engineer`, `performance-benchmarker` · Skills: `source-driven-development`, `performance-analysis`, `test-driven-development`, `clean-code`
  - AC: Docling en CPU con jerarquía de headings conservada; `doc_kind="pdf"`; offsets referidos al **markdown extraído** (documentado); **M5** costo real medido y reportado; PDF >100MB → `skipped` sin abortar el delta; fixture PDF real (1-2 páginas) con heading no nulo
  - ➕ **AC añadido por la revisión de CP-B (hallazgo #5):** **retirar `SkipReason.PDF_PARSER_PENDING` de `source.classify_file`** — si T7 solo añade la rama Docling en `parsers.extract_text`, los PDFs seguirán saltándose en silencio con solo un warning. Hay que desactivar esa exclusión **y** testear que un PDF real ya no se salta.
  - ➕ **AC añadido:** `parsers.extract_text` debe emitir **UTF-8 estricto con BOM incluido** (igual que `file.read_text(encoding="utf-8", errors="strict")` del camino de escritura) — docstring de `parsers.py` ya lo apunta como contrato para T7. Un decoder distinto rompería M2.
  - Verificar: `UV_PROJECT_ENVIRONMENT=venv uv run python -m pytest ../../tests/phase1/test_pdf.py -v`; tiempo de parseo en el commit
  - Dep.: T6 · Tamaño: M

- [ ] **T8 · Semántica incremental Δ, lock de un solo proceso y métricas**
  - Subagentes: `rag-pipeline-engineer`, `python-pro`, `test-engineer` · Skills: `test-driven-development`, `solid`, `clean-code`, `error-handling-patterns`, `observability-and-instrumentation`
  - AC: 2ª pasada sin cambios → `indexed=0`; modificado → solo sus chunks; borrado → filas purgadas (o reconciliación explícita documentada); refresh concurrente → `locked:true` **sin escribir**; métricas `{scanned, indexed, skipped, elapsed_ms, locked}` con reloj monotónico; retorno tipado sin `Any`, reutilizable tal cual por el MCP de Phase 2
  - ➕ **AC añadidos por la revisión de CP-B (hallazgos #5) y por mi sonda:**
    * **TOCTOU classify→read:** `classify_file` decide y `index_file` lee *después*; un borrado o `chmod` entre medias lanza dentro del componente memoizado. El "nunca aborta" de F5 vale solo en la fase de clasificación → T8 debe asegurar **aislamiento de error por fichero** (o usar el manejo de excepciones del engine) y testear la desaparición a mitad de pasada.
    * **`scanned`/`skipped` subestiman:** (a) el conector se salta en silencio los **directorios ilegibles** (`except PermissionError: continue` en `localfs/_source.py`); (b) un fichero **no-UTF-8** hoy aterriza en un **log** (`component build failed`) y **no** en un `SkipReason` → **no contará en `skipped`**. *Verificado con sonda: el delta NO aborta (CocoIndex aísla el fallo) y el fichero sano sí se indexa.* T8 debe decidir cómo contabilizarlos para que `{scanned,indexed,skipped}` no mienta — es el contrato que leerá el MCP.
    * **Idempotencia:** leerla del **data plane** (`process_file: unchanged=N, adds=0, deletes=0, reprocess=0`), no del total — los componentes de traversa reportan `reprocess=1` por diseño (E2).
  - Verificar: `UV_PROJECT_ENVIRONMENT=venv uv run python -m pytest ../../tests/phase1/test_delta.py -v`
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
