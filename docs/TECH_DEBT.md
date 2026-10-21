# Technical Debt Register — Tepochcalli v1
**Date:** 2026-10-21 | **Author:** Arquitecto (entrevista /spec) | **Status:** Active
**Cobertura:** n/a (pre-código); este registro abre en Phase 0 y se actualiza en cada gate de [WORKFLOW.md](WORKFLOW.md).

Deuda conocida y aceptada al diseñar el sistema. Cada entrada: descripción, por qué existe,
coste si se ignora, y acción/oráculo para pagarla.

| ID | Deuda | Origen | Impacto si se pospone | Plan de pago |
|---|---|---|---|---|
| **TD-1** | **Autoría del flow + glue MCP**: `cocoindex-code` (el proyecto hermano) solo cubre búsqueda sobre código; **no existe RAG de vault listo** en el ecosistema — la capa entre CocoIndex y `tepochcalli-rag` (flow declarativo + handlers + token budget) es código propio inevitable | ADR-001, ADR-005 | El glue sin tests se rompe en cada bump de cocoindex; shadow de mantenimiento permanente | Tests de contrato + golden vault desde Phase 1-2; pineos estrictos (`uv.lock`); mantener la capa lo más fina posible (adaptadores, no lógica) |
| **TD-2** | **Coste CPU de Docling por PDF grande** (30 páginas ≈ 5-30s, memoria de parse) | ADR-001 (elección de pipeline CPU) | Deltas con PDFs grandes incumplen percepción del criterio "30s"; usuarios con 1k PDFs en lote inicial sufren primera indexación | Excluir PDFs grandes del presupuesto Δ (definición en spec-rag-engine); progreso visible en `index_refresh`; evaluar límite de tamaño/cache de parse en Phase 5 |
| **TD-3** | **Cambio de modelo de embeddings = re-index completo** (vector space distinto; prohibido mezclar dims) | ADR-006, spec-embeddings | El usuario que cambie modelo sin re-indexar obtiene resultados degradados o `INDEX_STALE_MODEL` | Detección automática por campo `model` + mensaje accionable; comando de conveniencia `tepochcalli reindex`; documentar en APPFLOW. **Resuelto en parte (2026-10-21, ADR-007):** D7.2 mueve el catálogo de modelos a `presets.toml` (datos, no UI del wizard) y D7.4 fija el swap como `tepochcalli reindex --confirm` con detección `E_MODEL_MISMATCH` + `rag_status` |
| **TD-4** | **Obsolescencia del índice con editores externos**: cambios por apps distintas a Obsidian (editores, sync) solo se ven cuando `index_refresh()` corre (diseño sin watcher residente) | ADR-002/005 (no demonios) | Búsquedas "viejas" entre refreshes; confusión "¿no está indexado?" | Regla MCP-first: el agente refresca al inicio de tarea; documentar; evaluar `auto_refresh` opt-in en config (riesgo: viola cero-procesos → decisión de spec nueva) |
| **TD-5** | **Opción de migración LEANN sin ejecutar**: si el almacenamiento del índice domina el disco o `leann_mcp` madura, convendría migrar (97% menos storage) pero con riesgo de latencia >500ms en CPU y metadatos de cita delgados | ADR-001 revisit triggers | Payer el cambio sobre flujo probado es más caro cada versión; pero migrar a ciegas rompe criterio 3 | No ejecutar; revisar en revisit date ADR-001 (2027-04) con bench comparativo bajo el mismo contrato de ADR-005 |
| **TD-6** | **MCP-first vive en texto editable (`AGENTS.md` del vault)**: la instrucción es prompt, no código; el usuario puede debilitarla. Evolución prevista en UH.md: plugin/tool de OpenCode V2 que asegure el uso del MCP y deje el fichero como placeholder | docs/UH.md §wizard | Regla incumplida = tokens sin presupuesto y citas opcionales | Mantener contratos estables para que el futuro plugin sea adaptador fino; tracker en Phase 5+ (fuera de v1) |
| **TD-7** | **Skills del payload infladas (208)**: inventario actual incluye ~120 skills out-of-domain y familias duplicadas (pdf×5, office×3, literatura×8+) — coste de contexto y de descarga para el usuario | Anexo A de spec-agent-workflow | Sesiones más caras/lentas; confusión del harness al elegir skill redundante | Acciones de aseo/consolidación como entregable de Phase 4 (WORKFLOW): retirar del payload base lo out-of-domain (skill pack opcional futuro), consolidar duplicados, instalar gaps (Jupyter/R/Graphviz/PlantUML/LaTeX) |
| **TD-8** | **Alias de carpeta `00-resources/` (scaffold actual) vs `00-Resources/` (canónico en specs)** | specs/spec-vault-structure.md nota | Inconsistencia de rutas entre producto e instalación (SOs sensibles a case) | Decidir en /plan Phase 4: renombrar el scaffold del template o alias en wizard con validación |

## Deuda no aceptada (evitada por diseño)

* RAG desde cero (UH.md lo prohíbe explícitamente) → mitigado por ADR-001.
* Daemon/puerto del índice o del MCP → evitado por ADR-002/005, verificable en bench.
* Python en el host del usuario → evitado por ADR-004 (uv gestiona CPython).
* Versiones de deps sin pinear → pyproject + uv.lock (TRD §4).

## Revisión

* Cada gate de phase en WORKFLOW.md re-valida este registro (ningún TD-1..8 asciende a blocker
  sin nota aquí).
* Próxima revisión formal: cierre de Phase 5 (aceptación E2E).
