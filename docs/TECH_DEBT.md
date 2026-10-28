# Technical Debt Register — Tepochcalli v1

**Date:** 2026-10-21 | **Author:** Arquitecto (entrevista /spec) | **Status:** Active
**Revisión de gate:** Phase 1 (2026-10-23) y Phase 2 (2026-10-27) — ver §Revisión Phase 1 y §Revisión Phase 2 más abajo.
**Cobertura:** abre en Phase 0 y se actualiza en cada gate de [WORKFLOW.md](WORKFLOW.md).

Deuda conocida y aceptada al diseñar el sistema. Cada entrada: descripción, por qué existe,
coste si se ignora, y acción/oráculo para pagarla.

| ID | Deuda | Origen | Impacto si se pospone | Plan de pago |
| --- | --- | --- | --- | --- |
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
| **TD-12** | **Peso de `markitdown[all]` en el venv del vault**: **+142 MB y +49 paquetes** (medido 2026-10-26 con `uv pip install --dry-run` contra PyPI, CPython 3.12) — entre los extras hay soporte que v1 no usa (PDF, audio, YouTube, Azure AI) | D18 (plan §2/§3); el layout congelado (spec-vault-structure §Layout) y `--offline` (spec-markitdown) exigen el paquete oficial completo | venv más pesado en disco y en la descarga inicial del wizard; candidato a reclasificar cuando markitdown publique un extra mínimo | Aceptado en v1: el venv ya ronda los ~2 GB con torch/Docling (margen relativo ~7 %) y el PDF lo cubre Docling. Revisar en Phase 6 si aparece un extra mínimo o si el wizard debe mostrar el peso real al usuario |

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

## Revisión Phase 2 (gate CP-D, 2026-10-27)

Re-review de TD-1…TD-11 con el estado real tras T1-T10 (medido, no estimado). Cierre de fase:
`just ci` verde en local con **404 tests** (2 deselected `slow`) y **1 warning** — exactamente
la esperada de TD-9; GitHub Actions **sigue sin correr** (M6 de Phase 1, sin cambio): no se
declara CI verde.

| ID | Estado (2026-10-27) | Evidencia / próxima acción |
| --- | --- | --- |
| **TD-1** | **Pagada en Phase 2** | El glue MCP existe y está probado: contract tests D7.3 (`tests/e2e/test_mcp_contract.py`), e2e golden (`test_mcp_journey.py` + fixture `tests/fixtures/golden_vault/`) y la capa se mantuvo fina — `tepochcalli_mcp` habla con el motor solo por el puerto `ChunkReader`, sin importar `cocoindex`/`lancedb` (test de arquitectura extendido a `mcp/`). Pineos intactos. Oráculo vigente: `just ci` tras cada bump |
| **TD-2** | Sin cambios (coste ya medido en Phase 1) | Límite de tamaño / cache de parse → Phase 6 |
| **TD-3** | **Pagada en Phase 2** (detección y mensaje) | `E_MODEL_MISMATCH`, `rag_status.model_matches_config` y su `fix_hint` son **reales y verificados en el wire** (contract tests): el usuario ya no puede quedarse en silencio con un modelo distinto. El comando `tepochcalli reindex --confirm` (D7.4/ADR-008) es entrega del wizard en **Phase 3**, no deuda pendiente |
| **TD-4** | Sin cambios (mitigación validada en Phase 1) | Refresco típico barato + regla MCP-first; sin watcher (ADR-002 intacto); `auto_refresh` sigue siendo decisión de spec futura |
| **TD-5** | Sin cambios | No ejecutar; revisit date de ADR-001 (2027-04) con bench comparativo |
| **TD-6** | Sin cambios | MCP-first sigue en texto editable (`AGENTS.md` del vault); tracker Phase 6+ |
| **TD-7** | Pendiente de diseño | Aseo/consolidación en Phase 4 (blueprint); ejecución en Phase 5 |
| **TD-8** | Pendiente | Alias `00-resources/` → decisión Phase 4, remediación Phase 5 |
| **TD-9** | Abierta; **oráculo activo** | La suite completa de Phase 2 (**404 passed**) emite **exactamente 1 warning**, la esperada `FutureWarning` de `get_sentence_embedding_dimension`. Oráculo sin disparar; gate de bump (suite antes de aceptar el lock) intacto |
| **TD-10** | Abierta; oráculo intacto | `default_env_loop` sigue tras el pin `cocoindex==1.0.25`; `tests/integration/test_delta.py` corre dentro de las 404 |
| **TD-11** | Sin cambios | Limitación TOCTOU de symlinks documentada en SECURITY §Symlinks; pago atado al conector de cocoindex. Relacionada con **R5** (TOCTOU de slug) más abajo |

Ningún TD asciende a blocker de Phase 3; **TD-1 y TD-3 quedan pagadas** en esta fase.

### Deuda nueva en Phase 2 (abierta al cierre de T10)

Procede de los registros de `tasks/todo.md` (residuos CP-B, deuda declarada por T6, hallazgos
de T7/T8/T9): nada aquí es deuda inventada en T10.

| ID | Deuda | Origen | Impacto si se pospone | Plan de pago |
| --- | --- | --- | --- | --- |
| **R5** | **TOCTOU en la colisión de slug** de `add_source`: `available_name` + `os.replace` entre sesiones — dos procesos concurrentes podrían elegir el mismo sufijo y pisarse | Residuo CP-B (T5) | Pérdida de una fuente recién convertida en el caso de dos `add_source` simultáneos en el mismo `subdir` | Aceptada: tool local single-user (mismo modelo que TD-11); re-chequeo post-rename (`O_EXCL`/reintento) si el uso multi-proceso llega a ser real — evaluar en Phase 6 |
| **R6** | `pyproject.toml` `packages` omite `tepochcalli_mcp.tools` — con el editable instalado es irrelevante (MetaPathFinder, H2), pero un **wheel construido perdería el subpaquete `tools/`** | Residuo CP-B (T9/T10) | `uv build` produciría un paquete incompleto | Añadir el subpaquete (o `find`) al preparar la primera distribución del flow/server — antes de construir ningún wheel |
| **D6-1** | **`just md-lint` no está en verde**: cae sobre el baseline pre-existente **D12** (MD060 en tablas antiguas, MD034 en specs) | T6 (verificado con `git stash`: ya fallaba en HEAD) | El AC «sin errores nuevos» es manual de por sí; el ruido dificulta ver regresiones | Recuento del cierre de T10: **422 errores en HEAD / 422 tras T10** (cero errores nuevos; `just md-lint` en ambas revisiones). Limpieza del baseline → tarea de aseo de docs sin gate (D12 permite vivir con ello) |
| **D6-2** | `spec-embeddings.md` §Proposed Solution (línea 37) sigue diciendo `provider = "local" (default) o "litellm"` — incompleto tras **D15** (`none` es el 3.er valor); §`tepochcalli.toml` sí está al día | T6 (fuera de la sección autorizada) | Un lector de la §Proposed Solution cree que `none` no existe | Enmienda en la siguiente pasada autorizada sobre `specs/` (reportada en el cierre de T10; `specs/` vedado en T6/T10) |
| **D6-3** | `verify.py` (CLI de desarrollo, vedado en T6) construye su lector con `citation.model_id(config)` **ignorando el provider**: en un vault `none`/`litellm` sigue embebiendo en local | T6 | La CLI minte sobre el embedder real del vault; no afecta al server | Reusar la fábrica `tepochcalli_mcp.embedder` (o `adapters`) desde `verify.py` — fix de flow, sin contrato; evaluar con Phase 6 |
| **D6-4** | Los **fallos de API reales dentro del update de escritura** (401/rate-limit ocurridos *dentro* de cocoindex) salen como `INTERNAL`; solo la **clave ausente** se traduce a `E_API_AUTH` (chequeo local en la fábrica) | T6, documentado en `server._refresh_once` | El agente ve `INTERNAL` donde podría ver un `fix_hint` de credenciales | Traducirlos exigiría engancharse a los retries/batch de cocoindex — evaluar en Phase 6 si el criterio de aceptación lo exige |
| **D6-6** | La **primera indexación con litellm** hace **una llamada extra de descubrimiento de dims** (`_get_dim` de cocoindex, heredada del update) — dato que el plan no decía, inherente a cocoindex | T6, documentado en `app.py::_build_embedder` | Una llamada de API imprevista en el primer refresh (coste y fallo posible sin red) | Evaluado en T7: sola llamada, dentro de presupuesto con margen; queda registrado — vigilar si cocoindex la añade a cada pasada |
| **F-T7-4** | **Discrepancia spec↔regla:** `spec-mcp-server` §Testing pide «asserts de `took_ms` <500 **en CI**»; la regla anti-flake de la casa (aprendida con el fallo real de T3) prohíbe aserciones de latencia en la suite. **No se implementó a propósito** — el p95 vive solo en `just bench-search` (medición local) y el `--smoke` va con umbral generoso sin percentil | Hallazgo T7 | Una spec pide algo que la casa rechaza: próxima lectura genera duda o un flake | Enmendar `spec-mcp-server` §Testing (quitar «en CI» o explicitar «bench local») en la siguiente pasada autorizada — reportada al FTR; `specs/` vedado en T10 |
| **`FIX_OFFLINE_NO_CACHE`** | El literal de ese `fix_hint` **no tiene ancla en ninguna spec**: unit y wire se comparan auto-referenciados, así que una derivación silenciosa del texto pasaría inadvertida | Duda declarada en T8 | El contrato del `fix_hint` puede derivar sin que nada falle | Fijar el literal en `spec-mcp-server` §errores (enmienda futura) o fijar el esperado en un test con fuente externa al código |
| **`opencode_payload_before_t9.json`** | Fixture con la copia del `opencode.json` pre-T9: sostiene el test de *merge conservador* y **irá obsoleta si el payload cambia legítimamente en Phase 4-5** | T9 | El test de merge fallaría por un cambio legítimo del payload y tentaría a «arreglar» el test a ciegas | **Regenerarla en Phase 4-5** cuando el payload cambie; no combatirla. Cualquier cambio de `mcp.servers.*` por tarea autorizada la invalida a propósito |

**R6 cerrada (2026-10-28, T9):** `pyproject.toml` declara `tepochcalli_mcp.tools`; `import tepochcalli_mcp.tools.search` verificado en `crates/tepochcalli/tests/phases_f4f5.rs` (check del venv en F5).

### Pasada de calidad sobre Phase 2 (rito `/test`, 2026-10-27)

Auditoría de cobertura del código de la fase (**1.760 LOC** del paquete `tepochcalli_mcp`) más
medición real con `just coverage` (404 tests).

**Hallazgo estructural, cerrado aquí:** el gate de cobertura medía **solo `tepochcalli_flow`**. Los
1.760 LOC del server —los 4 handlers, `errors`, `paths`, `embedder`, `budget`, `server`— quedaban
fuera de todo umbral: `just coverage` podía seguir verde con el server entero sin ejercitar.
Corregido: `source = ["tepochcalli_flow", "tepochcalli_mcp"]`, y `just ci` ejecuta `coverage` **en
lugar de** `test` (misma suite, solo instrumentada ⇒ mismo coste). Un gate que nadie ejecuta no es
un gate. Medición final: **414 tests, TOTAL 99 %** (1376 stmts, 238 ramas) y `mcp/tepochcalli_mcp`
al **100 % en 13 de 14 ficheros** (`__main__.py` 91 %, rama `24->exit`).

**Bug de contrato corregido en esta pasada** (historia, no deuda): `add_source` no emitía
`E_NO_EMBEDDER` en instalación degradada, aunque `spec-mcp-server.md:151` lo exige para las tres
tools; respondía `INTERNAL` **después** de escribir el `.md` en `00-Resources/`, dejando un
huérfano sin `fix_hint`. Test que lo demuestra:
`tests/e2e/test_mcp_contract.py::test_degraded_install_add_source_returns_e_no_embedder_and_writes_nothing`.
Siete ramas más que estaban sin ejecutar (lectura `litellm` con éxito, limpieza del temporal en
`_write_atomic`, `_is_auth_error` por nombre de clase, `_select` sobre tabla ilegible,
`resolve_file_uri` con host/relativa, `index_models` con `ValueError`, `build_embedder` en `none`)
quedaron cubiertas con tests de caracterización.

| ID | Deuda | Origen | Impacto si se pospone | Plan de pago |
| --- | --- | --- | --- | --- |
| **Q-1** | `.github/workflows/phase1.yml` **no ejecuta el gate de cobertura** que `just ci` sí exige | Rito `/test` (2026-10-27) | Local y CI divergen: una regresión de cobertura no la vería GitHub. Se suma a M6 (Actions nunca ha corrido) | Añadir el paso `coverage` al job `mcp` cuando se toque CI; hoy invisible porque Actions nunca corrió |
| **Q-2** | El 95 % global tiene **4 puntos de margen** y todo lo que queda sin cubrir es de **Phase 1**: `flow/refresh_lock.py` **83 %** (30-32, 42-45, 70), `verify.py` **94 %** (111-116, 134→exit), `source.py` **96 %** (339, 352-353, 417), `app.py:383`, y `mcp/__main__.py` **91 %** (rama `24->exit`) | Medición 2026-10-27 (414 tests) | Cualquier línea nueva sin test en `mcp/` o `flow/` tumba el gate recién atado a `just ci` | Cubrir las ramas del lock (concurrencia real) y de `verify.py` (ligado a D6-3) en Phase 6 |
| **Q-3** | El caso «`uri` inválida **y** `provider=none` a la vez» no tiene test explícito: la precedencia `VALIDATION_ERROR > E_NO_EMBEDDER` es estructural (orden de código), no afirmada | Fase verde del rito | Un reordenamiento futuro del handler podría invertir la precedencia sin que nada falle | Test de precedencia por pares cuando se toque `add_source` de nuevo (el patrón ya existe en `test_mcp_e_dialect.py`) |

## Review /code-review Phase 2 (2026-10-27)

Aplicados y verificados en rama `feat/workspace-obsidian` (commits 913a53b…b21e6af + e5fc8b4,
docs): agregados O(1) del estado del índice y tabla rota ⇒ `INTERNAL` (ya no finge vacío);
denylist SSRF en `validate_source_uri`; pin exclusivo `litellm<1.107.0` (GHSA-92x9-889m-jgmw);
redacción de credenciales del URI; guard TOCTOU en `_write_atomic`; vault root resuelto;
retirada la entrada `mcp.servers.markitdown` del payload; estimador de tokens con peso CJK.

Lo que queda DEFERIDO de esa review (o no llegó a preguntarse), con razonamiento:

| ID | Deuda | Origen | Impacto si se pospone | Plan de pago |
| --- | --- | --- | --- | --- |
| **CR-1** | `_scrub` solo elimina la cadena EXACTA del secreto (`embedder.py:205-207`): sin encodings (URL-encode, escapes JSON de la librería en el mensaje de error) | Review Phase 2 | Un mensaje de litellm que encoda la clave (`sk%2Dx`) escapearía al log | Normalizar/codificar oscilaciones al avanzar el wrapper (`replace` por cada encoding conocido) — Phase 6 con la matriz de proveedores |
| **CR-2** | `INDEXED_FIELDS` en `tools/add_source.py:60` es una tupla global sin `Final` | Review Phase 2 | Reasignación accidental en un refactor; mypy no avisa | `Final` al toucher de nuevo `add_source` (cambio de 1 token, no merece su propio pase) |
| **CR-3** | Rename `_meta_seam` → `_index_meta` (`server.py:347`, docstring de `rag_status` consume ese nombre literal) | Review Phase 2 | Cosmético: nombre menos descriptivo de lo posible | Con la siguiente tarea que toque el wiring de `rag_status` |
| **CR-4** | Shadowing `effective_top_k` (función `budget.effective_top_k` vs variable local `tools/search.py:102`) | Review Phase 2 | Confusión en lectura; sin bug real | Renombrar la variable en la próxima pasada sobre `search` |
| **CR-5** | `.gitignore` PROPIO del directorio `obsidian-workspace/` (artefactos del payload): hoy el repo raíz cubre `venv/db/models/bin/config` desde arriba | Review Phase 2 (secops) | Si el payload se copia/mueve fuera del repo (wizard), el ignore deja de viajar con él | Crearlo al tocarse el layout del payload en Phase 4-5 (depende del wizard) |
| **CR-6** | El SDK de MCP responde TIPOS inválidos de args con **texto libre** propio del transporte antes de llegar al handler (server.py:339 y los 4 `@server.tool`): violación del §Manejo de errores «nunca texto libre» imputable al SDK, no a nuestros payloads | Review Phase 2 | Un agente que manda `top_k: "fuerte"` ve texto del SDK en vez de `VALIDATION_ERROR` canónico | Documentado como LÍMITE del SDK (`mcp==2.3.0`); si la v2 publica validación de args canónica o un hook pre-handler, adoptarla — abierta ante upstream |
| **CR-7** | `O_EXCL`/fd atómico ante escritura multiusuario (`_write_atomic` tiene guard TOCTOU single-user y depaso del rename) | Review Phase 2; cerrada la pierna single-user en el mismo pase (eje 5, commit 00e29bf) | El guard cubre la carrera como-error (jamás `ok:true` borrando); un sistema multiusuario real quisiera retry-transparente | Solo si llega el caso multi-usuario (misma puerta que TD-11/R5) |
| **CR-8** | `index_meta` sigue pagando el walk recursivo `rglob` de `db/` para `db_size_bytes` (O(archivos) en disco, O(1) en filas ya logrado) | Review Phase 2 (eje 1) — los AGREGADOS del índice SÍ quedaron O(1) (`count_rows()`); el `rglob` puede porque la spec §rag_status pide `db/` ENTERO, no `stats` de LanceDB | `db_size_bytes` menor coste con 1k PDFs ya indexados (miles de ficheros de fragments en `db/`) | Proyectar el tamaño del `.tepochcalli/db` con `os.scandir` de 1 nivel o cachearlo por sesión cuando el AC de escala lo pida (Phase 6) |

Ninguna asciende a blocker: CR-1..CR-5 son nominativas de una pasada futura sobre cada
fichero; CR-6 es límite externo documentado; CR-7/CR-8 solo activan con escala real.

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
* **Nota T9 (2026-10-27):** `.github/workflows/phase1.yml` conserva el nombre
  histórico de Phase 1; con el job `mcp` (Phase 2 T9 — gate `mypy flow+mcp` del
  server `tepochcalli_mcp`) el fichero cubre ya dos fases. Renombrarlo
  (p. ej. `quality.yml`) es deuda menor sin impacto funcional — los gates
  dentro están documentados en su propia cabecera; decisión para T10.
* **Decisión T10 (2026-10-27):** el fichero **no se renombra** — `.github/` está vedado en T10
  y el nombre histórico no rompe nada (los gates están documentados en su cabecera). Queda como
  deuda menor: renombrar en la siguiente tarea que toque CI.
* **Deuda nueva de Phase 2 registrada:** ver §Deuda nueva en Phase 2 (R5, R6, D6-1…D6-6,
  F-T7-4, `FIX_OFFLINE_NO_CACHE`, fixture pre-T9) — TD-12 añadida a la tabla principal.
* Próxima revisión formal: cierre de Phase 6 (aceptación E2E).
