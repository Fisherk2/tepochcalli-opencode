# TODO — Phase 6 (aceptación E2E de los 7 criterios)

> **Fecha:** 2026-11-11 · **Orquestador:** Moctezuma · **Plan:** [tasks/plan.md](plan.md)
> **Fase:** Phase 6 — E2E Acceptance (los 7 criterios de `docs/UH.md`) · **Gate:** FTR de aceptación + gate v1 release
> **Decisiones del dueño (2026-11-11):** D-P6-1…D-P6-8 — ver `tasks/plan.md` §2.
> **Precedente (D-P5-7):** este fichero **sobrescribe** el TODO de Phase 5; el de Phase 5 queda en git (`93d0060`).

## Reglas de la fase

- **Se mide, no se estima.** Toda cifra de esta fase lleva **n, método, host y comando**. La jerarquía
  de D8 manda: `medido > estimado > declarado`. Un número sin su comando no entra en `docs/`.
- **La frontera de escritura (D-P6-1):**
  - **CONGELADO (solo lectura):** `obsidian-workspace/.opencode/` (5 agentes, 9 comandos, 40 skills),
    `obsidian-workspace/AGENTS.md`, `obsidian-workspace/opencode.json`.
  - **EDITABLE:** `obsidian-workspace/.tepochcalli/flow/`, `obsidian-workspace/.tepochcalli/mcp/`,
    `crates/`, `tests/`, `docs/`, `specs/`, `SPEC.md`, `CHANGELOG.md`, `tasks/`.
  - Si una referencia del payload está **errónea**: se reporta y se corrige **en la spec** con
    enmienda fechada — **nunca** se reescribe el fichero del payload.
- **Referencia de medición = btrfs** (`/tmp/opencode`, NVMe). fuseblk/NTFS-3G (`/mnt/HDDFish`) se mide
  igual y se documenta como **límite conocido** con su cifra (D-P6-3).
- **Los umbrales se fijan antes de medir** (D-P6-8): recall y deriva FTS se escriben en
  `docs/TRD.md` §6.2 en T0 y no se ajustan después.
- **Remediar es permitido** cuando un criterio o un gate sale rojo — pero un contrato `Accepted`
  (ADR-001/002/005/010/011) exige **ADR nuevo**, nunca una edición (regla §8 de `docs/WORKFLOW.md`).
- **La corrida D9 la ejecuta el QA humano** (D-P6-2): los comandos se activan por input del usuario.
  Ningún subagente la simula.
- **Commits atómicos:** uno por calpulli, Conventional Commits ≤ 72 cols, trailer `Co-Authored-By`.
- **Benchmarks fuera del gate:** los benches de la fase **no** entran en `just ci` (regla anti-flake
  y coste deminutes-to-hours); se corren a mano y su JSON se archiva como evidencia.
- **`just coverage` solo en el cierre de fase** (T16): ~1 h de suite instrumentada y calienta el
  host hasta apagarlo. **No está en `just ci`** (decisión del dueño 2026-11-12): es una corrida
  local de desarrollo, no un gate. Por tarea basta `just quality`, `just python-test` o la receta
  dirigida (`just python-test-unit`, `just python-test-file <patrón>`); la cobertura se
  reconcilia en T16.

## Leyenda

- `[ ]` pendiente · `[~]` en curso · `[x]` hecho y verificado · `[!]` bloqueado (motivo en la línea)
- **No se avanza al siguiente checkpoint en rojo.**

---

## Ola 0 — Fundaciones de medición

### [x] T0 — Protocolo de aceptación, umbrales y auditoría de huecos

- Subagente: `codebase-archaeologist` → `performance-benchmarker` (secuencial) · Skills: `documentation-and-adrs`, `source-driven-development`, `planning-and-task-breakdown`, `context-engineering` · Tools: `codebase-memory-mcp`, `vercel-grep`
- [x] `docs/acceptance/protocol.md`: host de referencia (btrfs/NVMe, 12 vCPU, 15,5 GiB RAM, CPython 3.12.14) y `/mnt/HDDFish` como filesystem de contraste
- [x] Los 7 criterios de `docs/UH.md` copiados literalmente + el gate D9 marcado como *no criterio 8*
- [x] Por criterio: bench/test que lo mide hoy (o `no existe`), cifra actual con su método, calpulli que lo cierra
- [x] Tabla §6.3 copiada con columna `Result` vacía y columna nueva **`origen de la cifra`**
- [x] **Umbrales fijados ANTES de medir** en `docs/TRD.md` §6.2: recall (propuesta recall@5 = 1.0) y deriva FTS (propuesta: caída de recall ES > 10 % relativo)
- [x] `docs/TRD.md` §6 gana las subsecciones §6.1 (método) y §6.2 (umbrales) — la casa ya cita «TRD §6.2»
- [x] Deuda re-declarada: en alcance TD-2/13/15/27/28/29/34 + D-b · fuera M6 y TD-32, con su motivo
- [x] `git status --short` solo muestra `docs/acceptance/protocol.md`, `docs/TRD.md`, `tasks/`
- Deps: — · Verificación: cada afirmación lleva su comando · **revisión del dueño (CP-0)**
- **Hecho (2026-11-12):** `docs/acceptance/protocol.md` (193 líneas, §1-§8) + `docs/TRD.md` §6.1/§6.2 (umbrales recall@5 = 1.0 y deriva FTS > 10 % relativo, `md-lint` 0). Cero mediciones.

### [x] T1 — Corpus de escala reutilizable con manifiesto

- Subagente: `performance-benchmarker` · Skills: `performance-analysis`, `bash-defensive-patterns`, `test-driven-development`, `design-patterns` · Tools: —
- [x] Corpus de **10 000 md** (10 subdirs) + **1 000 PDF** de 1 página válidos, determinista, en `--dir` (btrfs)
- [x] `corpus-manifest.json`: por fichero → ruta relativa, sha256, bytes, tipo + seed + versión del generador + totales
- [x] **Reproducibilidad**: dos materializaciones → manifiesto **idéntico** (hash del árbol, no comparación de carpetas)
- [x] Reutilizable sin reindexar: el manifiesto verificado salta la materialización
- [x] `obsidian-workspace/.tepochcalli/{db,models}` **nunca** tocados (verificado al terminar)
- [x] Tamaño en disco y **tiempo de materialización** publicados
- [x] Sigue fuera del gate de `just ci` (no es `test_*`)
- Deps: T0 · Verificación: `sha256sum` del árbol == manifiesto · `just ci` verde
- **Hecho (2026-11-12):** `tests/support/corpus.py` + manifiesto canónico; 3 materializaciones con `tree_sha256 27a20c05…3ecd2` idéntico y 11 000 hashes iguales al generador de `HEAD`; **2 677 ms** / **45 M** / 11 001 ficheros en `/tmp/opencode/phase6-corpus` (btrfs); reutilización verificada (`reused: true`, `mtime_ns` intactos). Informe: `docs/acceptance/corpus.md`.

### [x] T2 — Coste real de un PDF de 30 páginas con markitdown (TD-2)

- Subagente: `performance-benchmarker` · Skills: `performance-analysis`, `observability-and-instrumentation`, `bash-defensive-patterns` · Tools: —
- [x] Fixture **PDF de 30 páginas** válido (xref correcto, texto extraíble) **extendiendo** `tests/fixtures/pdf/gen_fixture_pdf.py` — sin dependencia nueva
- [x] Medición con **n ≥ 3**: extracción + indexación, con **RSS pico** (`VmHWM`) al lado; n, método y host publicados
- [x] Cifra **separada** del Δ de texto (D51): no cuenta contra el presupuesto de 30 s
- [x] **Coste por página** publicado y contrastado con los PDF de 1 página (la extrapolación se declara como derivación)
- [x] Etiqueta **`medido`** (D8)
- [x] **Condición de TD-2 resuelva con dato**: si rompe la percepción del Δ ⇒ se abre tarea de remediación (límite de tamaño / caché de parseo) con su ADR; si no ⇒ TD-2 se cierra con la cifra
- [x] El fixture de 30 págs no entra en `just ci`
- Deps: T0 · Verificación: JSON del bench archivado + cifra en `docs/TRD.md` §6
- **Hecho (2026-11-12):** `bench_documents.py` + `gen_fixture_pdf.py --pages`; PDF de 30 págs **3 144 ms** p50 (n=3), 335 págs **50 557 ms**, 1313 págs **128 015 ms**; RSS pico 191-255 MiB; ms/página **no** monótono (221 → 97,5) ⇒ extrapolar es inválido. Propuesta de remediación A-D redactada; **decisión del dueño 2026-11-12: opción A+B** (ver T2-bis; C y D no se abren). Informe: `docs/acceptance/documents.md`.

### [x] T2-bis — Traza de progreso en `index_refresh` (TD-2 opción **A+B**, firmada 2026-11-12)

- Subagente: `rag-pipeline-engineer` · Skills: `test-driven-development`, `observability-and-instrumentation`, `clean-code`, `source-driven-development` · Tools: `read`/`grep`, `codebase-memory-mcp`
- [x] **A**: D51 se queda — los documentos binarios siguen **fuera** del Δ de 30 s y se publican aparte
- [x] **B**: `progress.py` traza por **documento binario** (inicio, `extraído en N ms` real), inicio del ciclo con las raíces, `candado retenido` honesto y cierre con las cuentas del reporte
- [x] Contrato MCP **intacto**: el JSON conserva exactamente `{scanned, indexed, skipped, elapsed_ms, locked, roots}`
- [x] Progreso **solo por `stderr`** (`logging`); `stdout` sigue siendo el canal JSON-RPC — test que lo afirma
- [x] `.md`/`.txt` **no** se trazan uno a uno (10 000 notas serían 10 000 líneas de ruido)
- [x] Tests: `tests/unit/test_progress.py` (3) + `tests/integration/test_mcp_refresh_progress.py` (3) — **6 passed**
- [x] **C y D no se abren** (ni límite de páginas ni caché de parseo); se reabre con ADR nuevo si hay quejas reales de latencia
- Deps: T2 · Verificación: `just python-test` verde + `spec-mcp-server` §`index_refresh` enmendada + TD-2 cerrada en `docs/TECH_DEBT.md`

### [x] T3 — Eval de relevancia con consultas etiquetadas (TD-15)

- Subagente: `search-relevance-engineer` · Skills: `test-driven-development`, `source-driven-development`, `clean-code` · Tools: `tepochcalli-rag` (payload, stdio)
- [x] **10 consultas etiquetadas** (query → `source_path` esperado + `heading` cuando aplique) en mix ES/EN, como **datos** en `tests/fixtures/`
- [x] Test de integración **en subproceso** (patrón `index_vault` de `tests/support/mcp_server.py`): `search(top_k=5)` → **recall@5 = 1.0**
- [x] **Sin** aserciones de latencia (regla anti-flake)
- [x] Umbral (1.0) y método publicados en `docs/TRD.md` §6.2 — **el de T0**, sin ajustar
- [x] **RED demostrado** antes de implementar
- [x] El test **falla** si el golden vault se vacía o si una etiqueta cambia (no es tautología)
- Deps: T0 · Verificación: `just python-test` verde · recall publicado con n = 10
- **Hecho (2026-11-12):** fixture propio `tests/fixtures/relevance_vault/` (**20 notas ES/EN**, 5 familias de 4 con distractores cercanos) + `tests/fixtures/relevance_queries.json` (n = 10, 5 ES/5 EN, 10 ficheros distintos) + `tests/integration/test_search_relevance.py` (**5 tests**, subproceso, sin latencia). **recall@5 = 1.00 (10/10)**, todas en el puesto 1; etiquetas desplazadas ⇒ **0.00** (la métrica discrimina); vault vacío ⇒ `INDEX_EMPTY` y 0.00 (el gate cae, no `skip`). Comando: `just python-test-file relevance` (5 passed, 83,6 s). Umbral de §6.2 intacto (D-P6-8); RED archivado en el informe del calpulli

### [x] Checkpoint CP-0 — Protocolo y umbrales aprobados

- [x] Protocolo publicado con host, FS de referencia, n y método por criterio
- [x] **umbrales de recall y deriva FTS escritos en `docs/TRD.md` §6.2 y aprobados por el dueño** (CP-0, 2026-11-12: recall@5 = 1.0 · deriva FTS > 10 % relativo, sin cambios)
- [x] Tabla de huecos completa: cada criterio tiene su calpulli
- [x] Tabla §6.3 copiada con la columna `origen de la cifra`

### [x] Checkpoint CP-1 — Fundaciones de medición (tras T1, T2, T3)

- [x] Corpus de 11 000 entradas reproducible **byte a byte** (manifiesto verificado 2×)
- [x] Coste del PDF de 30 páginas **medido** (n ≥ 3, RSS pico, `medido`) y la condición de TD-2 resuelta
- [x] Recall@5 = 1.0 con el **umbral de T0**
- [x] `just ci` verde (ya **sin** cobertura: `python-sync → lint → fmt-check → typecheck → test → bench-smoke → rust-ci`; la cobertura es medición local y se reconcilia en T16)
- **Hecho (2026-11-12):** `just ci` **verde en 31:54** (`CARGO_TARGET_DIR=/tmp/opencode/cargo-target`): 872 passed + 3 deselected, smoke Δ **850 ms** < 10 000 ms, `rust-ci` verde. La cobertura sale de `ci` por decisión del dueño (2026-11-12) y pasa a corrida local en T16.

---

## Ola 1 — Los 7 criterios, medidos

### [x] T4 — Criterio 3 a escala (10k/1k) y deriva del índice FTS ES/EN

- Subagente: `performance-benchmarker` → `search-relevance-engineer` (secuencial) · Skills: `performance-analysis`, `observability-and-instrumentation`, `source-driven-development` · Tools: `tepochcalli-rag` (payload, stdio), `context7`
- [x] `search` sobre el corpus **10 000 md + 1 000 PDF** con **n = 100 queries** muestreadas, `top_k=5`, nearest-rank declarado
- [x] Publicadas **las dos** cifras: `p95_client_ms` (puerta de gate) y `p95_server_took_ms` (punto de la spec)
- [x] Tabla **por etapa** (embed / ANN+FTS / ensamblado / IPC) con su margen
- [x] **Deriva FTS medida**: recall ES con FTS activa vs **solo ANN**, mismo corpus y mismas queries
- [x] Si supera el umbral de T0 ⇒ config bilingüe del FTS evaluada contra la **doc de la versión pineada** (R3) e implementada **o** límite documentado con su cifra
- [x] Decisión escrita en `docs/TRD.md` §6.2 y `docs/TECH_DEBT.md`
- Deps: T0, T1, T3 · Verificación: JSON del bench archivado como evidencia
- **Hecho (2026-11-12):** corpus de T1 verificado + copiado (`tree_sha256 27a20c05…`), índice **11 006 chunks** en **543 645 ms** (`VmHWM` 3,78 GiB), **p95 cliente 97 ms / server 94 ms** (n=100, nearest-rank 95.º, 500 ms ⇒ **PASS**); etapas p95 embed 27,0 · ANN+FTS 24,5 · ensamblado 4,6 · IPC 3,0 (+ `index_state` 36,5, fuera de la tabla de la spec) → suma 95,6 ≈ 97 ms. Deriva: recall@5 híbrido **0,19** vs solo ANN **0,15** ⇒ **−26,7 %** (umbral >10 %, **no se dispara**; pierna FTS sola: 19/100 en top-5, 75/100 fuera del top-50); PDF 14/14 vs md 5/86 (corpus de vocabulario fijo: mide el signo, no la calidad). Sonda ES/EN medida: índice inglés **4/7** pares flexivos ES vs español **6/7** y controles EN **2/2 → 0/2** ⇒ v1 mantiene `language="English"` y el límite queda como **TD-35** (ADR nuevo para cualquier cambio). JSON: `docs/acceptance/search-scale.json`; informe: `docs/acceptance/search-scale.md`; bench por fases: `just python-bench-search-scale --phase prepare|index|queries|stages|legs|probe|report`.

### [x] T5 — Criterio 6: escala 10k/1k y comparación 10 % vs 100 %

- Subagente: `performance-benchmarker` · Skills: `performance-analysis`, `observability-and-instrumentation`, `documentation-and-adrs` · Tools: `tepochcalli-rag` (payload, stdio)
- [x] **Δ p95** (n=20, nearest-rank) sobre 11 000 entradas en **btrfs (referencia)** + diferencia declarada frente a la baseline P-02 (26 967 ms)
- [x] **Comparación 10 % vs 100 %**: Δ **y** latencia de `search` en ambos brazos; regresión publicada como **ratio**; PASS = ratio ≤ 2×
- [x] **Walk-only** medido aparte (sin embed, sin Δ)
- [x] **fuseblk/NTFS-3G**: medición repetida y publicada como **límite conocido**, con la causa (walk de 11k entradas) y la recomendación al usuario
- [x] La cifra que decide el criterio es la de **btrfs**; NTFS va a la columna de límites — **no** se maquilla el FAIL
- [x] Costes de documentos (D51) aparte (T2 aporta la cifra)
- [x] El bench sigue **fuera** del gate de pytest
- Deps: T0, T1, T4 · Verificación: JSON con ambos FS y los dos brazos
- **Hecho (2026-11-13):** `tests/benchmarks/bench_scale_ratio.py` (por fases y por tramos: `prepare|index10|search|walk|delta|ntfs|report`). Brazo 10 % **derivado del manifiesto de T1** (1 de cada 10 por tipo ⇒ 1 000 md + 100 PDF, `tree_sha256 66a194d5…701d65a`, índice propio en frío **60 716 ms**, 1 101 chunks). **Δ p95 btrfs: 15 695 ms (100 %, 11k) vs 2 543 ms (10 %, 1,1k) ⇒ ratio 6,17× = FAIL** de la cota 2× (el 100 % sí cabe en 30 s al 52 %; **−41,8 % frente a P-02 26 967 ms**); **`search` p95 cliente 87 ms vs 51 ms ⇒ ratio 1,71× = PASS** (n=100, las 100 consultas de T4, 500 ms); **walk-only 6 115 ms vs 555 ms ⇒ 11,0×** (n=5) = mecanismo: walk lineal sin watcher (ADR-002) ⇒ **TD-36**. **fuseblk/NTFS-3G: Δ p95 52 996 ms = FAIL** (1,77× el presupuesto; walk 22 945 ms; índice en frío 944 019 ms), publicado como **límite conocido** D-P6-3 con causa y recomendación; **descartado** copiar el índice de btrfs al FS (el memo no cruza la ruta ⇒ re-embed completo, 96-204 s por ciclo). JSON: `docs/acceptance/scale-ratio.json`; informe: `docs/acceptance/scale-ratio.md`; bench: `just python-bench-scale-ratio --phase …`.

### [x] T6 — Criterio 4: tokens por consulta (<2000 con contexto)

- Subagente: `llm-architect` → `test-engineer` (secuencial) · Skills: `source-driven-development`, `test-driven-development`, `error-handling-patterns` · Tools: `tepochcalli-rag` (payload, stdio), `context7`
- [x] Medición e2e: `search` real (`top_k=5`) + query + esqueleto de respuesta con citas, con **tokenizador real** nombrado con versión y fuente
- [x] Fixture **adverso** (unicode, CJK, emoji, tablas, listas largas) reusando `tests/integration/test_mcp_budget_adversarial.py`
- [x] **Dos cifras** con desglose: (a) payload del server ≤1600 (invariante del contrato) y (b) **total e2e < 2000** (criterio UH)
- [x] Publicadas con n, tokenizador y método en `docs/TRD.md` §6
- [x] Si el total excede 2000 ⇒ el contrato MCP **no se toca** (ADR-005): el ajuste es del techo del server, con decisión explícita del dueño
- [x] Test e2e que **falla** si el total supera 2000 (guarda viva)
- Deps: T0 · Verificación: `just python-test` verde
- **Hecho (2026-11-13):** medidor `tests/support/token_budget.py` (tokenizador **`cl100k_base` de `tiktoken 0.14.0`**, ya en el venv; `o200k_base` publicado al lado; fuente `github.com/openai/tiktoken`) + guarda viva `tests/integration/test_mcp_token_budget.py` (3 tests, fixture adverso **reusado** de T7, sin marcadores `slow`). **Cifras (n=7 caras, `top_k=5` y `top_k=20`):** (a) payload **1 600 por el estimador** del contrato y **1 789 reales**; (b) **total e2e 1 995 < 2 000** en el peor caso (query 7 + payload 1 789 + respuesta citada 199) y 1 675 en la dorada ⇒ **PASS**, con **5 tokens de margen** (`o200k`: 1 785). La respuesta se modela con el formato que prescribe el payload (`source_path » heading (chars x–y)`, una afirmación por resultado, `(sin heading)` en PDF). Sonda de sensibilidad: 2 frases/resultado ⇒ **2 023** (el guard no es vacío); RED archivado (ModuleNotFoundError primero, luego la aserción disparada). Hallazgo **F-T6-1**: el 1 600 es del estimador (envoltura JSON ≈190 tokens fuera de la fórmula + `chars/4` optimista en ES) — si el payload crece, la decisión (bajar el techo a ~1 500) es **del dueño**; contrato MCP intacto y sin dependencias nuevas. Evidencia: `docs/acceptance/token-budget.{md,json}` + TRD §6.2 + WORKFLOW §6.3

### [x] T7 — Criterio 5: citas precisas y re-verificación contra el archivo vivo (TD-13)

- Subagente: `rag-pipeline-engineer` → `test-engineer` (secuencial) · Skills: `test-driven-development`, `incremental-implementation`, `debugging-and-error-recovery`, `clean-code` · Tools: `tepochcalli-rag` (payload, stdio), `codebase-memory-mcp`
- [x] `verify.py --spot-check N`: relee el `source_path` y afirma la identidad F1 **reusando** `citation.verify_slice_identity` (no se duplica)
- [x] `offsets_ref` respetado: `source` ⇒ slice contra el archivo original; `extract` ⇒ contra el texto extraído
- [x] **Solo lectura conservada**: snapshot de `(mtime_ns, size)` de `db/` antes/después ⇒ **0** cambios
- [x] **Golden answers ampliado**: md, txt y pdf con `source_path` real + `heading` (nullable) + offsets **reproducibles**
- [x] Para **pdf**, `heading is None` (D54) afirmado explícitamente: el golden **no** exige heading en PDF
- [x] Cobertura del gate: el código nuevo del CLI entra en la superficie medida ⇒ se reconcilia con `just coverage` **en el cierre de fase (T16)**; en T7 basta `just python-test`
- [x] Si el spot-check encuentra citas rotas ⇒ la **tasa** se documenta (no se maquilla) y se abre la remediación si > 0 (TD-4)
- Deps: T0, T3 · Verificación: test que **edita** el archivo post-indexación y espera **exit ≠ 0**
- **Hecho (2026-11-13):** `verify.py --spot-check N` (`LanceDBChunkReader.sample_rows` → `table.head`) re-verifica la identidad F1 **reutilizando `citation.verify_slice_identity`**; `source` corta el original, `extract` re-extrae con markitdown (D50); severidades `OK`/`BROKEN`/`MISSING` y **exit 1** si hay roturas. **Medido** (golden md + txt + pdf indexado en subproceso): **6/6 (100 %), 0 rotas, exit 0**; **edición externa tras indexar ⇒ 3/6 (50 %), exit 1**; txt borrado ⇒ `MISSING`, exit 1; snapshot de `db/` sin cambios en las 3 corridas. Golden ampliado a md + txt + pdf en el e2e del wire (txt y pdf con `heading is None`; refresh `(3,0,3)`). **Tasa de citas rotas publicada: 0 %** (el caso que debe fallar falla ⇒ el 0 no es tautología). RED archivado (argparse `unrecognized arguments: --spot-check`). Evidencia: `docs/acceptance/citations.{md,json}` + TRD §6.2 + README de aceptación; TD-13 cerrada. `coverage` **no** ejecutado (T16).

### [x] T8 — Criterio 7: matriz de conversión multi-formato

- Subagente: `test-engineer` · Skills: `test-driven-development`, `api-and-interface-design`, `documentation-and-adrs` · Tools: `tepochcalli-rag` (payload, stdio)
- [x] Matriz de **9 entradas**: md, txt, pdf, docx, pptx, xlsx, xls (índice) + html, url (convertidor)
- [x] Por celda: resultado, `doc_kind`, `offsets_ref`, indexabilidad, `source_path` resultante
- [x] La matriz se ejecuta como **test**, no como tabla escrita a mano
- [x] Los formatos no soportados (`.doc`, `.ppt`, PDF escaneado) se declaran **GAP** con mensaje accionable — **no** se simulan
- [x] `html` y `url`: se afirma que el `.md` **convertido no es la fuente citable** y que el original indexado sí
- [x] Matriz publicada en `docs/TRD.md` §6, coincidente con la salida del test
- [x] Sin dependencias nuevas (R1)
- Deps: T0 · Verificación: test e2e verde
- **Hecho (2026-11-13):** `tests/e2e/test_format_matrix.py` (16 tests, ~2 min, sin `slow`): vault temporal con los 7 formatos del índice + PDF escaneado + fuentes del conversor, medido en **un** servidor por stdio (wire real). **8/9 celdas PASS medidas** — `md/txt` `offsets_ref=source`; `pdf/docx/pptx/xlsx/xls` `extract` con `heading` nulo (D54) y `source_path` = **el original**; `html` entra por el conversor, su `.html` **nunca** es citable y el artefacto `00-Resources/pagina.md` lo es **solo tras `index_refresh`** (refresh medido: `scanned 10, indexed 2, skipped 8`). **Celda `url` = GAP declarado**, no PASS: la suite corre con `nonet` y el guard SSRF rechaza loopback por diseño (el positivo con servidor local se retiró en Phase 2); lo ejecutado es el rechazo `VALIDATION_ERROR` «red interna» sin escritura, y el método que haría falta (host con red o allowlist, ADR) queda escrito. **3 GAP ejecutados** con mensaje literal del wire: `.doc`/`.ppt` ⇒ `VALIDATION_ERROR` «formato no soportado» + catálogo (el borde corta antes de markitdown) y PDF escaneado ⇒ `SOURCE_UNREACHABLE` + `GUIDE_OCR`, sin fila vacía al indexar (OM-11). `.xls` se **ejecuta de verdad** con un BIFF2 mínimo escrito con `struct` (`xlwt` no está): sin dependencias nuevas (R1). La tabla se **imprime desde el test** y `test_published_matrix_matches_docs_trd` pone el gate rojo si `docs/TRD.md` §6.3 diverge (RED archivado: 15 passed / 1 failed antes de publicar). Evidencia: `docs/acceptance/format-matrix.{md,json}` + TRD §6.3 + README de aceptación. Contrato de las 3 tools y payload intactos; `coverage` no ejecutado (T16).

### [ ] T9 — Criterio 1: no-interferencia con Obsidian

- Subagente: `test-engineer` → `security-architect` (secuencial) · Skills: `test-driven-development`, `bash-defensive-patterns`, `security-and-hardening`, `observability-and-instrumentation` · Tools: `tepochcalli-rag` (payload, stdio)
- [ ] Script sobre un vault **instalado de verdad** por el wizard (`install --non-interactive --skip-model`)
- [ ] (a) `.obsidian/` **byte-idéntico** antes/después de `index_refresh()` + `search` (hash de árbol)
- [ ] (b) **0** puertos nuevos escuchando; la lista `ss -ltnp` antes/después se **publica y archiva**
- [ ] (c) **0** ficheros con prefijo punto en el árbol visible (`.tepochcalli/`, `.obsidian/`, `.git/`)
- [ ] (d) el vault sigue siendo válido (`opencode.json` parseable + `AGENTS.md` + bandejas)
- [ ] El script **falla** (exit ≠ 0) si `.obsidian/` cambia o aparece un puerto
- [ ] Checklist de `spec-vault-structure.md` §Testing **ejecutado** y referenciado
- Deps: T0 · Verificación: salida archivada como evidencia del criterio 1

### [x] Checkpoint CP-2 — Criterios 3 y 6 a escala (tras T4, T5)

- [x] `search` p95 sobre 10k/1k con n = 100 nearest-rank; gate = `p95_client_ms`
- [x] Deriva FTS ES/EN medida contra el umbral de T0; decisión escrita
- [x] Δ p95 a escala + **ratio 10 % vs 100 %** ≤ 2× + walk-only
- [x] NTFS-3G medido y **declarado límite** con cifra y causa
- [x] Cifras de los dos criterios en §6.3 con su origen
- **Hecho (2026-11-12):** `p95_client_ms` **97 ms** (T4) y **87 ms** (T5, n=100, 11k) ⇒ criterio 3 **PASS**. Deriva FTS **no se dispara** (−26,7 % a favor del híbrido; mecanismo probado con sonda, TD-35). Criterio 6: Δ **15 695 ms** vs **2 543 ms** = **6,17×** > 2× ⇒ **FAIL medido** (TD-36), Δ absoluto dentro de 30 s; NTFS **52 996 ms** como límite. Ningún umbral se tocó.

### [ ] Checkpoint CP-3 — Los 7 criterios con evidencia medida (tras T6, T7, T8, T9)

- [ ] Tokens: payload ≤1600 y **total e2e < 2000** con tokenizador real nombrado
- [ ] Citas: 100 % con `source_path` real + offsets reproducibles; `--spot-check` exit 0 / ≠ 0
- [ ] Matriz de 9 formatos con resultado por celda y GAP declarados
- [ ] No-interferencia: `.obsidian/` byte-idéntico, **0** puertos nuevos (lista archivada)
- [ ] Las **7 filas** de §6.3 tienen cifra y origen

---

## Ola 2 — Deuda y decisiones

### [ ] T10 — TD-27: el fate de la cita PDF sin heading (D54)

- Subagente: `rag-pipeline-engineer` → `software-architect` (secuencial) · Skills: `documentation-and-adrs`, `source-driven-development`, `performance-analysis`, `doubt-driven-development` · Tools: `tepochcalli-rag` (payload, stdio), `codebase-memory-mcp`
- [ ] **Medición del impacto**: fracción de citas de PDF en top-5 **sin** `heading` sobre el corpus de T1, y qué pasa con una query cuyo único material es un PDF
- [ ] **Decisión con dato**: (a) reafirmar D54 con la cifra y el coste de revertir documentados, o (b) revertir ADR-011 ⇒ **ADR-013** que reemplace §4.3 + re-sincronización de las 4 specs
- [ ] La decisión queda **escrita con fecha**; TD-27 **cerrada con evidencia**
- [ ] **No reescribe el payload** (D-P6-1) ni toca el contrato MCP sin ADR
- [ ] La **firma es del dueño** (cambia una decisión `Accepted`): el subagente prepara la opción con el dato
- Deps: T0, T1 · Verificación: cifra reproducible con su comando

### [ ] T11 — TD-28 + TD-29: hygiene del wizard y del modelo local

- Subagentes: `rust-refactoring-specialist` **∥** `python-pro` (paralelo — ficheros, lenguajes y suites distintos, cero estado compartido) · Skills: `refactoring-patterns`, `clean-code`, `design-patterns`, `test-driven-development`, `incremental-implementation` · Tools: —
- [ ] **(a)** `embedder_menu.rs` de 894 → **<500** líneas, partiendo por responsabilidad, **sin cambiar ni un mensaje** pinneado por `e2e_cli_help`/`int_*`
- [ ] **(a)** `cargo fmt` limpio, `clippy -D warnings` limpio, `cargo test` verde con el **mismo número de tests**
- [ ] **(b)** `require_local_model` valida el snapshot **real** (`config.json` + pesos), no «el directorio no está vacío» ⇒ `E_MODEL_INVALID` donde hoy no se emite
- [ ] **(b)** Test que falla con snapshot a medias y con snapshot de otra revisión (RED demostrado)
- [ ] `just coverage` ≥ 95 % **se verifica en el cierre de fase (T16)**, no en este calpulli; aquí basta `just python-test`
- [ ] `wc -l` de ambos ficheros y recuento de tests publicados (TD-28 y TD-29 **cerradas**)
- Deps: T0 · Verificación: `just rust-ci` verde · `just python-test` verde (cobertura en el cierre)

### [ ] T12 — TD-34: refs a skills/subagentes del payload (solo lectura)

- Subagente: `codebase-archaeologist` · Skills: `codebase-memory`, `documentation-and-adrs`, `context-engineering` · Tools: `vercel-grep`, `codebase-memory-mcp`
- [ ] `ls .opencode/skills` (40) cotejado con **todos** los nombres citados en los **9 comandos** y los **5 agentes** ⇒ **0 huérfanos**
- [ ] Tabla nombre → fichero → línea → presente
- [ ] `grep` de carga por comando: cada skill se carga **en el comando que la cita**; cada `agent:` resuelve a un primario existente
- [ ] `git diff --stat -- obsidian-workspace` **vacío** antes y después (D-P6-1)
- [ ] Si hay un nombre equivocado ⇒ **no se reescribe el payload**: se reporta y se corrige en la spec con enmienda fechada **o** se acepta como GAP declarado
- [ ] El informe desbloquea el gate de T15
- Deps: T0 · Verificación: tabla nombre→fichero→presente · `git diff --stat` vacío

### [ ] T13 — D-b: estado de soporte de Windows en v1

- Subagente: `technical-writer` · Skills: `documentation-and-adrs`, `changelog-generate`, `technical-writer` · Tools: `gitmcp`
- [ ] Estado **verificado / no verificado** enumerado (target compilable, `install.ps1`, layout `Scripts/`, D20) y **nunca ejecutado** (instalador, smoke, CI)
- [ ] **Decisión de soporte v1** escrita con fecha: *no soportado en v1* o *soportado con verificación pendiente*, con la **consecuencia para el usuario** y qué haría falta para revertirla
- [ ] Propagación a `docs/TRD.md` §2, `specs/spec-installer-wizard.md`, `docs/APPFLOW.md`, `CHANGELOG.md`
- [ ] **No** se toca `README.md` ni `LICENSE` (lista de «nunca» del `AGENTS.md`)
- [ ] `docs/TECH_DEBT.md` §D-b **cerrada** con la decisión y su fecha
- [ ] `just md-lint` 0
- Deps: T0 · Verificación: decisión citada en TRD §2 y APPFLOW · enlaces resuelven

### [ ] Checkpoint CP-4 — Deuda y decisiones cerradas (tras T10, T11, T12, T13)

- [ ] TD-27 decidido **con el dato** (ADR-013 o nota de cierre con la cifra)
- [ ] `embedder_menu.rs` **<500** con el mismo número de tests; `require_local_model` valida el snapshot
- [ ] TD-34: **0** skills huérfanas; `git diff --stat -- obsidian-workspace` vacío
- [ ] D-b: decisión escrita y propagada; `just md-lint` 0
- [ ] M6 y TD-32 **siguen abiertas** y declaradas

---

## Ola 3 — Gate del agente y cierre

### [ ] T14 — Scaffolding de la corrida D9 (TD-31): evidencia verificable

- Subagente: `technical-writer` → `test-engineer` (secuencial) · Skills: `documentation-and-adrs`, `test-driven-development`, `bash-defensive-patterns`, `doubt-driven-development` · Tools: `vercel-grep`
- [ ] Runbook **nuevo** `tests/phase6-methodology-runbook.md` con los **9 comandos** en su formato vigente (Pre-Flight, `procedencia` de 4 estados, `/validate` en 4 fases, `/transform` A-G con `list_formats` antes de prometer, `/update` quirúrgico, `chilam` sin bandejas)
- [ ] El runbook de Phase 5 se conserva como histórico (no se sobrescribe)
- [ ] Script `tests/e2e/verify_methodology_evidence.py`: (a) cada artefacto en **su** bandeja y ninguna bandeja ajena con ficheros, (b) frontmatter con los campos del formato vigente, (c) transcripción de los **9** comandos, (d) regla **MCP-first** (`search` antes de leer crudo `00-Resources/`); exit ≠ 0 + informe por punto
- [ ] El script **no juzga la prosa** (solo lo mecánico)
- [ ] **Evidencia sintética de ejemplo** en `tests/fixtures/`: verde en la forma buena y **exit ≠ 0** ante cada defecto (bandeja ajena, frontmatter ausente, transcript faltante, MCP-first no observado)
- [ ] Plantilla de checklist con las columnas del formato vigente + columna de evidencia
- [ ] La corrida **no** se ejecuta aquí (D-P6-2)
- Deps: T0, T12 · Verificación: el script verde en la forma buena y ≠ 0 en cada defecto

### [ ] T15 — Corrida D9 ejecutada por el QA + evidencia verificada

- Subagentes: `testing-evidence-collector` → `testing-reality-checker` (secuencial: recoger → juzgar) · Skills: `doubt-driven-development`, `document-verification`, `testing-evidence-collector` · Tools: `tepochcalli-rag` (payload, stdio)
- [ ] **El QA ejecuta** los 9 comandos en el harness sobre un vault instalado, con el corpus de fotosíntesis del runbook
- [ ] Evidencia archivada en `tests/evidence/phase6/`: `<NN>-<comando>-transcript.txt` + `<NN>-<comando>-artifact.md` + `vault-tree.txt` + `checklist.md` (transcript **crudo**)
- [ ] `python3 tests/e2e/verify_methodology_evidence.py tests/evidence/phase6` ⇒ **exit 0**
- [ ] Checklist del runbook **relleno** con evidencia enlazada; puntos no mecánicos con veredicto del QA
- [ ] Lo no verificado se escribe como **no verificado** (lección de Phase 3.5 (b))
- [ ] Si la corrida **no** se ejecuta ⇒ §6.3 marca el gate como `NO EJECUTADO` con motivo y TD-31 **sigue abierta**
- Deps: T14 · Verificación: script verde sobre la evidencia real · 45/45 puntos con evidencia

### [ ] T16 — Cierre documental + FTR de aceptación

- Subagentes: `docs-writer` → `code-reviewer` (secuencial: cierre → revisión cruzada) · Skills: `documentation-and-adrs`, `changelog-generate`, `code-review-and-quality`, `git-workflow-and-versioning` · Tools: `vercel-grep`, `codebase-memory-mcp`
- [ ] `docs/WORKFLOW.md` §Phase 6: **tabla §6.3 rellena** (cifra medida + origen + veredicto) + gate D9 con su estado real; sección **< 700 líneas**
- [ ] `docs/TRD.md` §6: protocolo, **umbrales** y cifras de la fase publicados
- [ ] `docs/TECH_DEBT.md`: **re-revisión formal** — TD-2/13/15/27/28/29/34 y D-b con su estado medido; **M6** y **TD-32 siguen abiertas** con su motivo
- [ ] `SPEC.md`: los 7 criterios pasan a **verificados** con fecha y enlace a la evidencia
- [ ] `CHANGELOG.md`: entrada de Phase 6
- [ ] `docs/ARCHITECTURE.md`: **sin** diagrama nuevo salvo que T10/T13 alteren el inventario
- [ ] **FTR de aceptación**: checklist de los 7 criterios + el gate D9, cada fila con cifra y comando reproducible
- [ ] `just ci` verde (suite + cobertura ≥ 95 % + bench-smoke + rust-ci) y `just md-lint` 0
- [ ] **Revisión cruzada**: cada número en WORKFLOW/TRD/TECH_DEBT/SPEC es el **mismo** y su comando está a mano
- Deps: T2, T4, T5, T6, T7, T8, T9, T10, T11, T12, T13, T15 · Verificación: segundo par de ojos · gates verdes

### [ ] Checkpoint CP-5 — Gate del agente (tras T14, T15)

- [ ] El verificador de evidencia pasa en la forma buena y **falla** en cada defecto
- [ ] Corrida D9: **9/9** con transcript archivado y checklist firmado, **o** `NO EJECUTADO` con motivo

### [ ] Checkpoint CP-6 — FTR de aceptación (tras T16)

- [ ] Checklist de los 7 criterios + el gate D9 con **cifra y comando** en cada fila
- [ ] WORKFLOW, TRD, TECH_DEBT, SPEC y CHANGELOG con **cifras medidas**; cada número, un valor
- [ ] `just ci` verde + `just md-lint` 0
- [ ] Decisión del dueño sobre el **gate de v1 release** (release o rollback con nota en `docs/WORKFLOW.md`)

---

## Trazabilidad con la deuda y los gates heredados

| Ítem | Origen | Calpulli | Estado al cerrar |
| --- | --- | --- | --- |
| TD-2 · coste del PDF de 30 págs | `docs/TECH_DEBT.md` | T2 | Cerrada con cifra o con remediación abierta (condición resuelta) |
| TD-13 · `verify.py --spot-check` | `docs/TECH_DEBT.md` | T7 | Cerrada con test e2e |
| TD-15 · eval de relevancia (recall@5) | `docs/TECH_DEBT.md` | T3 | Cerrada con n = 10 y umbral publicado |
| TD-27 · PDF sin heading (D54) | `docs/TECH_DEBT.md` | T10 | Cerrada con decisión firmada (ADR-013 o nota) |
| TD-28 · `embedder_menu.rs` <500 | `docs/TECH_DEBT.md` | T11 | Cerrada con `wc -l` |
| TD-29 · `require_local_model` | `docs/TECH_DEBT.md` | T11 | Cerrada con test |
| TD-34 · refs de skills del payload | `docs/TECH_DEBT.md` | T12 | Cerrada con tabla |
| D-b · Windows | `docs/TECH_DEBT.md` | T13 | Cerrada con decisión escrita |
| TD-31 · corrida D9 (D-P5-10) | `docs/TECH_DEBT.md` | T14, T15 | Cerrada con evidencia, o **NO EJECUTADO** declarado |
| M6 · CI y release | `docs/TECH_DEBT.md` | — | **Sigue abierta** (fuera de alcance, D-P6-4) |
| TD-32 · `installer.rs` / `int_phase_f8_mcp_merge.rs` | `docs/TECH_DEBT.md` | — | **Sigue abierta** (fuera de alcance, D-P6-4) |
| Alineación spec↔payload de permisos (hallazgo de T1) | `specs/spec-payload-permissions.md` | T1-bis | Enmendada 2026-11-12 (la política de secretos vive en el global); **856 passed / 0 failed**; GAP declarado: `.tepochcalli/config/**` = `allow` |
| P-02 · baseline de escala NTFS vs btrfs | `docs/TECH_DEBT.md` §Review 5-ejes | T5 | Convertido en límite documentado |
| Deriva FTS ES/EN | `docs/TECH_DEBT.md` §Review 5-ejes | T4 | Medida y decidida |
| Criterios 1-7 de `docs/UH.md` | `docs/WORKFLOW.md` §6.3 | T4-T9 | Con cifra y origen |
