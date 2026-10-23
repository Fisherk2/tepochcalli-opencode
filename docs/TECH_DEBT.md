# Technical Debt Register — Tepochcalli v1
**Date:** 2026-10-21 | **Author:** Arquitecto (entrevista /spec) | **Status:** Active
**Revisión de gate:** Phase 1 (2026-10-23) — ver §Revisión Phase 1 más abajo.
**Cobertura:** abre en Phase 0 y se actualiza en cada gate de [WORKFLOW.md](WORKFLOW.md).

Deuda conocida y aceptada al diseñar el sistema. Cada entrada: descripción, por qué existe,
coste si se ignora, y acción/oráculo para pagarla.

| ID | Deuda | Origen | Impacto si se pospone | Plan de pago |
|---|---|---|---|---|
| **TD-1** | **Autoría del flow + glue MCP**: `cocoindex-code` (el proyecto hermano) solo cubre búsqueda sobre código; **no existe RAG de vault listo** en el ecosistema — la capa entre CocoIndex y `tepochcalli-rag` (flow declarativo + handlers + token budget) es código propio inevitable | ADR-001, ADR-005 | El glue sin tests se rompe en cada bump de cocoindex; shadow de mantenimiento permanente | Tests de contrato + golden vault desde Phase 1-2; pineos estrictos (`uv.lock`); mantener la capa lo más fina posible (adaptadores, no lógica) |
| **TD-2** | **Coste CPU de Docling por PDF grande** (medido 2026-10-22 en Phase 1: 30 páginas = **49–51 s** en caliente, ≈1,6–1,7 s/pág, RSS pico 2 048–2 189 MiB; en frío la carga de modelos domina: 29–37 s — **por encima** de la estimación original de spec-rag-engine, «30 págs ≈ 5-30 s») | ADR-001 (elección de pipeline CPU) | Deltas con PDFs grandes incumplen percepción del criterio "30s"; usuarios con 1k PDFs en lote inicial sufren primera indexación | Excluir PDFs grandes del presupuesto Δ (definición en spec-rag-engine; el bench M1 los excluye y los reporta aparte); progreso visible en `index_refresh`; **la cifra medida manda sobre la estimación de la spec** y vive aquí y en WORKFLOW §Phase 1 (M5); evaluar límite de tamaño/cache de parse en Phase 6 (aceptación E2E) |
| **TD-3** | **Cambio de modelo de embeddings = re-index completo** (vector space distinto; prohibido mezclar dims) | ADR-006, spec-embeddings | El usuario que cambie modelo sin re-indexar obtiene resultados degradados o `INDEX_STALE_MODEL` | Detección automática por campo `model` + mensaje accionable; comando de conveniencia `tepochcalli reindex`; documentar en APPFLOW. **Resuelto en parte (2026-10-21, ADR-007):** D7.2 mueve el catálogo de modelos a `presets.toml` (datos, no UI del wizard) y D7.4 fija el swap como `tepochcalli reindex --confirm` con detección `E_MODEL_MISMATCH` + `rag_status`. **Estado Phase 1 (2026-10-23):** el campo `model` ya se escribe **por fila** (T6) — la detección de mismatch tiene su dato real; el mensaje/`E_MODEL_MISMATCH` llega con Phase 2-3 |
| **TD-4** | **Obsolescencia del índice con editores externos**: cambios por apps distintas a Obsidian (editores, sync) solo se ven cuando `index_refresh()` corre (diseño sin watcher residente) | ADR-002/005 (no demonios) | Búsquedas "viejas" entre refreshes; confusión "¿no está indexado?" | Regla MCP-first: el agente refresca al inicio de tarea; documentar; evaluar `auto_refresh` opt-in en config (riesgo: viola cero-procesos → decisión de spec nueva). **Comportamiento real medido (Phase 1):** un refresh típico cuesta **58–178 ms** (bench de 50 archivos en rampa: p95 5 385–5 952 ms) — refrescar al inicio de tarea es barato, lo que hace la regla viable en la práctica; el diseño sigue **sin watcher** (ADR-002 intacto) |
| **TD-5** | **Opción de migración LEANN sin ejecutar**: si el almacenamiento del índice domina el disco o `leann_mcp` madura, convendría migrar (97% menos storage) pero con riesgo de latencia >500ms en CPU y metadatos de cita delgados | ADR-001 revisit triggers | Payer el cambio sobre flujo probado es más caro cada versión; pero migrar a ciegas rompe criterio 3 | No ejecutar; revisar en revisit date ADR-001 (2027-04) con bench comparativo bajo el mismo contrato de ADR-005 |
| **TD-6** | **MCP-first vive en texto editable (`AGENTS.md` del vault)**: la instrucción es prompt, no código; el usuario puede debilitarla. Evolución prevista en UH.md: plugin/tool de OpenCode V2 que asegure el uso del MCP y deje el fichero como placeholder | docs/UH.md §wizard | Regla incumplida = tokens sin presupuesto y citas opcionales | Mantener contratos estables para que el futuro plugin sea adaptador fino; tracker en Phase 6+ (fuera de v1) |
| **TD-7** | **Skills del payload infladas (208)**: inventario actual incluye ~120 skills out-of-domain y familias duplicadas (pdf×5, office×3, literatura×8+) — coste de contexto y de descarga para el usuario | Anexo A de spec-agent-workflow | Sesiones más caras/lentas; confusión del harness al elegir skill redundante | Decisión de aseo/consolidación en Phase 4 (matriz del blueprint spec-payload-vault); ejecución en Phase 5: retirar del payload base lo out-of-domain (skill pack opcional futuro), consolidar duplicados, instalar gaps (Jupyter/R/Graphviz/PlantUML/LaTeX) |
| **TD-8** | **Alias de carpeta `00-resources/` (scaffold actual) vs `00-Resources/` (canónico en specs)** | specs/spec-vault-structure.md nota | Inconsistencia de rutas entre producto e instalación (SOs sensibles a case) | Decisión de alias en Phase 4 (blueprint), renombrado/creación del scaffold en Phase 5: renombrar el scaffold del template o alias en wizard con validación |
| **TD-9** | **`cocoindex` llama a un método que `sentence-transformers` ya deprecó**: observado al correr la suite de Phase 1 — `FutureWarning: The get_sentence_embedding_dimension method has been renamed to get_embedding_dimension` emitido desde `cocoindex/ops/sentence_transformers.py`. No es código nuestro | ADR-001 (motor) + pineo de `sentence-transformers` vía extra de cocoindex (TRD §4); evidencia medida 2026-10-22 en Phase 1 | Hoy `uv.lock` fija 6.2.0 y el método sigue existiendo. Si una versión futura de `sentence-transformers` lo retira, la resolución de dims del embedder revienta **en tiempo de ejecución** durante la indexación — fallo tardío, no de import | El lock nos protege ahora: al bumpear `sentence-transformers` o `cocoindex`, **correr la suite de Phase 1** (especialmente `test_pipeline_integration.py`, que construye el embedder real) **antes de aceptar el lock**. Si revienta: esperar fix de cocoindex o fijar un upper bound en `pyproject.toml`. Oráculo: el `FutureWarning` dejando de emitirse cuando cocoindex adopte `get_embedding_dimension`. **Estado Phase 1 (2026-10-23):** abierta y confirmada — la suite de Phase 1 emite exactamente **1 warning** (137 passed / 1 deselected / 1 warning), la esperada; el oráculo no se ha disparado y el gate de bump (suite Phase 1 antes de aceptar el lock) sigue vigente |
| **TD-10** | **`default_env_loop` es un símbolo interno de cocoindex**: `_update_blocking_with_stats()` en `app.py` importa `cocoindex._internal.environment.default_env_loop` y programa la consumición con `asyncio.run_coroutine_threadsafe(_consume(), default_env_loop())` — única vía en `cocoindex==1.0.25` de leer `handle.stats()` en el loop de fondo compartido (un `asyncio.run` por pasada cierra el loop y la segunda corrida falla con «Event loop is closed») | T8 (stats de refresh); pin `cocoindex==1.0.25` en `.tepochcalli/pyproject.toml` | Un bump de cocoindex que renombre o mueva el símbolo revienta **todo refresh con stats**, sin aviso: vive en `_internal` (fuera de cualquier garantía de estabilidad) y el changelog de features del bump no lo menciona — rotura silenciosa para quien solo mira la nota de release | Oráculo doble: **`uv.lock` pineado** + **suite delta de T8** (`tests/integration/test_delta.py`, que ejecuta `refresh_blocking()` completo) **corrida antes de aceptar cualquier bump**. Si revienta: buscar la API pública de stats en la versión nueva o fijar upper bound en `pyproject.toml`. Síntoma a vigilar: `ImportError`/`AttributeError` de `default_env_loop` |
| **TD-11** | **TOCTOU symlink re-target**: la frontera de symlinks se evalúa al clasificar pero NO se re-verifica con fd propio al leer el conector (localfs de cocoindex no expone `O_NOFOLLOW` fd-level); hardlinks fuera del recurso tampoco se detectan | ADR-002 (motor), revisión Phase 1 5-ejes | En vault multiusuario/hostil admitiría swap de objetivo entre check y lectura; en el modelo v1 (vault del propio usuario, material confiado) se acepta | Documentado en docs/SECURITY.md §Symlinks (limitaciones); si el conector expone fd/NOFOLLOW, re-chequear en `classify_file`; no requiere decisiones D1-D8 — remediación de mecanismo propio |

## Revisión Phase 1 (gate CP-D, 2026-10-23)

Re-review de TD-1…TD-10 con estado real tras T1-T11 (medido, no estimado):

| ID | Estado (2026-10-23) | Evidencia / próxima acción |
| --- | --- | --- |
| **TD-1** | Abierta; **primera cuota pagada en Phase 1** | El flow quedó con tests (137 passed) y pineos estrictos (`uv.lock`, `cocoindex==1.0.25`); la capa se mantuvo fina (hexagonal, `ports.py` sin engine). El glue MCP sigue para Phase 2. Oráculo intacto: contract tests + suite completa tras cada bump |
| **TD-2** | Abierta; **coste ya medido** | 49–51 s / 30 páginas en caliente (celda actualizada arriba); PDFs excluidos del presupuesto Δ por protocolo y reportados en WORKFLOW §Phase 1 (M5). Límite de tamaño / cache de parse → Phase 6 |
| **TD-3** | Abierta; **infraestructura de detección lista** | `model` se escribe por fila desde T6 ⇒ `E_MODEL_MISMATCH` tendrá dato real que leer. Mensaje + comando llegan con Phase 2-3 |
| **TD-4** | Abierta; **mitigación validada por medición** | Δ típico 58–178 ms (p95 5,4–6,0 s en bench de 50 archivos): refrescar al inicio de tarea es barato ⇒ regla MCP-first viable. Sin watcher (ADR-002 intacto); `auto_refresh` sigue siendo decisión de spec futura |
| **TD-5** | Sin cambios | No ejecutar; revisit date de ADR-001 (2027-04) con bench comparativo |
| **TD-6** | Sin cambios | Regla MCP-first vive en el AGENTS.md del vault; tracker Phase 6+ (fase de aceptación) |
| **TD-7** | Pendiente de diseño | Decisión de aseo/consolidación en Phase 4 (blueprint); ejecución en Phase 5 |
| **TD-8** | Pendiente | Alias `00-resources/` no tocado en Phase 1; decisión en Phase 4, remediación en Phase 5 |
| **TD-9** | Abierta; **oráculo activo** | 1 warning esperada en la suite (137/1/1); oráculo sin disparar. Gate: suite Phase 1 antes de aceptar cualquier bump de `sentence-transformers`/`cocoindex` |
| **TD-10** | **Nueva (abierta)** | `default_env_loop` interno de cocoindex, justificado solo por el pin exacto `==1.0.25`; oráculo: `uv.lock` + suite delta de T8 antes de cada bump |
| **TD-11** | **Nueva (2026-10-23, pase 5-ejes)** | Limitación TOCTOU de symlinks/hardlinks, documentada en SECURITY §Symlinks; pago atado al conector de cocoindex |

Ningún TD asciende a blocker de Phase 2; TD-1 y TD-3 quedan con la puerta de Phase 2 en su plan de pago.

## Deuda no aceptada (evitada por diseño)

* RAG desde cero (UH.md lo prohíbe explícitamente) → mitigado por ADR-001.
* Daemon/puerto del índice o del MCP → evitado por ADR-002/005, verificable en bench.
* Python en el host del usuario → evitado por ADR-004 (uv gestiona CPython).
* Versiones de deps sin pinear → pyproject + uv.lock (TRD §4).

## Revisión

* Cada gate de phase en WORKFLOW.md re-valida este registro (ningún TD-1..10 asciende a blocker
  sin nota aquí).
* **Revisión Phase 1 ejecutada:** 2026-10-23 (T12) — TD-1..TD-9 re-reviewadas arriba, TD-10
  añadida; ninguna subió a blocker. Pase de corrección 5-ejes (2026-10-23): TD-11 nueva
  (TOCTOU symlink, documentada en SECURITY); ninguna otra está abierta — la deuda nueva no
  queda registrada (offsets_ref aditivo, pins de revisión, exit codes, probe de permisos) 
  porque el remediador se aplicó en el mismo pase.
* Próxima revisión formal: cierre de Phase 6 (aceptación E2E).
