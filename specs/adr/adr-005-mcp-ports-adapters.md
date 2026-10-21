# ADR-005: Exponer el RAG al agente vía MCP con contratos ports/adapters (`tepochcalli-rag`)

* **Status:** Accepted
* **Date:** 2026-10-21
* **Decision Makers:** Arquitecto (entrevista /spec), Product Owner (usuario)
* **Consulted:** Documentación OpenCode V2 de MCP servers; patrón hexagonal ports/adapters
* **Informed:** Autores de agentes/comandos del vault, usuarios del harness
* **Traceability:** docs/UH.md (capa "MCP Server"), specs/spec-mcp-server.md, specs/spec-agent-workflow.md, ADR-001/002

## 1. Context and Problem Statement

OpenCode V2 (capa de agente) necesita consultar el índice vectorial construido por CocoIndex (capa de procesamiento). Si el agente importara directamente la API de CocoIndex/LanceDB, cada cambio de motor o de almacén rompería prompts, agentes y flujo. Se requiere una frontera explícita y estable que además garantice los criterios de salida: citas precisas (criterio 5) y presupuesto de ≤2000 tokens por consulta (criterio 4).

## 2. Decision Drivers

* Contrato estable entre agente y motor: el motor (ADR-001) debe ser intercambiable sin tocar el harness.
* OpenCode V2 soporta MCP servers locales (stdio) configurados en `opencode.json` bajo `mcp.servers`.
* Los contratos de herramienta deben fijar presupuesto de tokens y forma de citas (no dejarlo al azar del modelo).
* Sin red expuesta: transporte stdio local, coherente con ADR-002 (sin puertos).
* Regla "MCP-first" en el AGENTS.md del vault: el agente debe preferir estas herramientas antes que leer archivos crudo.

## 3. Considered Options

* **MCP server dedicado `tepochcalli-rag`** (capa adapter): tres herramientas con contrato fijo — `search(query, top_k=5, path_filter?)`, `index_refresh()`, `add_source(uri, subdir?)` — sobre transporte stdio local.
* **Plugin de OpenCode V2** que inyecte contexto RAG automáticamente: acopla el ciclo de vida del harness al motor; la documentación de UH.md lo prevé solo como evolución futura (el AGENTS.md quedaría como placeholder entonces).
* **Herramienta CLI invocada por el agente vía bash** (ej. `tepochcalli search --json`): funciona, pero sin schema de herramientas el modelo reinventa flags y parsea texto; peor garantías de presupuesto/citas.
* **Servidor HTTP local con REST**: expone un puerto y un daemon — contradice Obsidian-safe (ADR-002) y añade ciclo de vida de servicio.

## 4. Decision Outcome

**Chosen option: MCP server `tepochcalli-rag` con contratos ports/adapters.** Las tres herramientas de D6 son los *puertos* del sistema; CocoIndex+LanceDB son el *adaptador* interno. El contrato de `search` devuelve siempre chunks con `{text, source_path, heading, char_start, char_end, score}` — la cita precisa es estructural, no opcional — y el server es el responsable de recortar `top_k`/tamaño para no exceder ~1600 tokens de contexto por respuesta (margen sobre el límite de 2000). Stdio local cumple cero-puerto. El plugin se documenta como migración futura natural del mismo contrato.

### 4.1 Confirmation

* Phase 2 de docs/WORKFLOW.md: OpenCode conecta el server, `search` devuelve chunks citables <500ms y fixtures assertan el presupuesto de tokens.
* Cambiar el target vectorial (ADR-002) o el motor (ADR-001) no exige modificar schemas de herramienta ni `opencode.json` más allá de `command`.

## 5. Pros and Cons of the Options

### MCP `tepochcalli-rag` (elegido)

* ✅ **Pros:** Schemas tipados que el harness valida; presupuesto de tokens y citas garantizados en el servidor (un solo lugar); portable entre harnesses que hablen MCP; stdio sin puertos; contrato versionable junto al vault.
* ⚠️ **Cons:** Hay que construir y mantener el server (deuda registrada en TECH_DEBT: cocoindex-code solo cubre búsqueda de código, no RAG de vault); overhead de proceso por sesión.
* ⚖️ **Neutral:** El conocimiento del dominio RAG vive en `.tepochcalli/mcp/`, fuera de prompts.

### Plugin de OpenCode

* ✅ **Pros:** Integración más profunda (auto-injection de contexto, menos instrucciones en AGENTS.md).
* ⚠️ **Cons:** Acopla el producto a un harness específico en fase temprana; API de plugins V2 aún moviéndose.
* ⚖️ **Neutral:** Decidido como evolución post-v1 (UH.md lo anticipa).

### CLI por bash

* ✅ **Pros:** Cero infraestructura MCP.
* ⚠️ **Cons:** Sin contrato de schema; el modelo puede omitir citas o truncar mal; latencia por proceso por invocación.
* ⚖️ **Neutral:** —

### HTTP REST local

* ✅ **Pros:** Reutilizable desde cualquier cliente.
* ⚠️ **Cons:** Daemon + puerto + CORS/seguridad local; viola no-interferencia y Obsidian-safe.
* ⚖️ **Neutral:** —

## 6. Consequences

* ✅ **Positives:** El motor y el almacén se pueden migrar (LEANN, pgvector) sin reescribir prompts ni configuración del agente; los tests de contrato corren contra un vault fixture sin LLM.
* ⚠️ **Negatives / Risks:** El server es un punto único de fallos de la capa de comunicación → errores tipados y fallback degrado (responder con `error.code`, nunca con texto libre malformado); Hyrum's law: los campos devueltos se congelan como contrato — extensiones solo aditivas.
* ⚖️ **Neutral:** La regla "MCP-first" del AGENTS.md del vault es la garantía de uso; un futuro plugin la reemplazará (TECH_DEBT).

## 7. Related Decisions

* ADR-001 — motor detrás del adaptador.
* ADR-002 — almacén que lee el puerto `search`.
* ADR-004 — el server se empaqueta en el venv del proyecto.
* ADR-006 — la config de embeddings que el server reporta en modo debug.

## 8. Compliance and Review

* **Success metrics:** 100% de respuestas de `search` con citas estructuradas; 0 consultas que excedan 2000 tokens en fixtures; latencia tool-call→respuesta <500ms p95.
* **Next review date:** 2027-04-21
* **Revisit triggers:** OpenCode madura plugins estables → migrar MCP-first a plugin conservando contratos; necesidad de múltiples motores → añadir puerto `search` agregador.

---
