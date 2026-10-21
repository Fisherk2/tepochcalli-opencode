# ADR-001: Adoptar CocoIndex como motor RAG del vault

* **Status:** Accepted
* **Date:** 2026-10-21
* **Decision Makers:** Arquitecto (entrevista /spec), Product Owner (usuario)
* **Consulted:** Documentación oficial de CocoIndex (cocoindex.io/docs), repositorios de las alternativas evaluadas
* **Informed:** Futuros mantenedores del flujo de indexación, agente de instalación (wizard)
* **Traceability:** docs/UH.md (historias de usuario), docs/PRD.md, specs/spec-rag-engine.md, ADR-002 (almacén vectorial)

## 1. Context and Problem Statement

Tepochcalli necesita un motor RAG que monitoree `00-Resources/` de un vault de Obsidian, extraiga texto de Markdown y PDFs, genere embeddings locales y los almacene en una base vectorial embebida, cumpliendo: indexación incremental del delta en <30s, búsquedas <500ms, y **cero consumo de tokens LLM durante la indexación** (criterio de presupuesto de tokens del usuario). El requerimiento explícito de UH.md es incorporar un motor ya construido por la comunidad, fácil de instalar y bien documentado — no implementar un RAG desde cero.

## 2. Decision Drivers

* Indexación incremental real (solo delta), soporte para live-watch de archivos locales.
* Sin LLM obligatorio por chunk indexado ni por consulta (presupuesto de tokens).
* Sin daemon ni puerto expuesto (Obsidian-safe, criterio de no interferencia).
* Extracción de PDF en CPU y metadatos de cita ricos (path, heading, offsets de caracteres).
* Embeddings locales (SentenceTransformers) como default y APIs externas como opción.
* Instalación simple (`pip install`) y documentación accesible.
* Almacén embebido compatible (LanceDB — véase ADR-002).

## 3. Considered Options

* **CocoIndex** — Motor de flujos de datos incrementales: núcleo en Rust + SDK en Python (`pip install cocoindex`), Apache-2.0. Flujos declarativos con `@coco.fn(memo=True)`, fuente `localfs` con live-watch, transformaciones de chunks, `SentenceTransformerEmbedder` local o LiteLLM (100+ proveedores), targets a LanceDB/pgvector/Qdrant/ChromaDB/SQLite.
* **LEANN** (StarTrail-org) — Índice vectorial de bajo almacenamiento (~97% menos que IVF-PQ clásico), incluye `leann_mcp` listo para MCP.
* **LightRAG** (HKUDS) — RAG con grafo de conocimiento; extrae entidades/relaciones con LLM obligatorio por documento indexado; requiere binding de LLM externo y corre como servidor en puerto.
* **RAG-Anything** (HKUDS) — Complemento de LightRAG para documentos multimodales; hereda las mismas restricciones (LLM por chunk indexado, daemon externo).
* **PageIndex** (VectifyAI) — RAG "vectorless": navegación de índices de documento con una llamada LLM por consulta; diseñado para documentos largos individuales.

## 4. Decision Outcome

**Chosen option: CocoIndex**, porque es el único candidato que satisface simultáneamente todos los decision drivers: incremental por diseño (engine Rust con memoización), live-watch de `localfs`, cero LLM en indexación y consulta (los embeddings son locales y la búsqueda es ANN pura), sin daemon ni puerto, extracción con Docling y metadatos de cita completos, y soporte nativo de target LanceDB embebido (ADR-002).

### 4.1 Comparativa de candidatos

| Criterio | CocoIndex ✅ | LEANN | LightRAG | RAG-Anything | PageIndex |
|---|---|---|---|---|---|
| Licencia conocida | Apache-2.0 | OSI | OSI | OSI | OSI |
| Instalación | `pip install cocoindex` | pip | pip + servicio | pip (depende de LightRAG) | pip |
| Indexación incremental (delta) | Sí (engine Rust + memo) | Sí (upsert) | Parcial | Parcial | N/A (sin índice) |
| Live-watch de archivos locales | Sí (`localfs` watch) | No (bajo demanda) | No (batch/API) | No (batch/API) | No |
| LLM obligatorio por chunk indexado | **No** | No | **Sí** ❌ | **Sí** ❌ | No |
| LLM obligatorio por consulta | No | No | Parcial | Parcial | **Sí** ❌ |
| Latencia de búsqueda en CPU | Baja (ANN en LanceDB) | **Riesgo >500ms** (recompute) ⚠️ | Variable | Variable | Alta (LLM por query) ❌ |
| Metadatos de cita (path/heading/offsets) | Ricos (campo origen por chunk) | **Delgados** ⚠️ | Entidades de grafo | Entidades de grafo | Sección del índice |
| Sin daemon / sin puerto | Sí (embebido) | Sí | No (servidor) ❌ | No (hereda LightRAG) ❌ | Sí |
| Escala multi-documento (10k/1k) | Sí | Sí | Sí | Sí | **Falla >5 docs** ❌ |
| Embeddings locales gratuitos | Sí (SentenceTransformer) | Sí | Depende de LLM externo ❌ | Depende ❌ | N/A |
| MCP listo para reutilizar | No (se construye `tepochcalli-rag`) | Sí (`leann_mcp`) | No | No | No |
| Documentación del dominio (RAG sobre vault) | Buena (cocoindex.io/docs) | Media | Buena | Media | Media |

### 4.2 Confirmation

* El flujo `@coco.fn(memo=True)` sobre `localfs` + LanceDB se valida en Phase 1 de docs/WORKFLOW.md: delta de un vault de muestra indexado en <30s (`cocoindex update`).
* Bench de búsqueda <500ms sobre corpus sintético 10k notas + 1k PDFs (docs/TRD.md, metodología de performance).
* Ningún paso del flujo invoca un LLM (verificable en la definición del flow: solo embedder).

## 5. Pros and Cons of the Options

### CocoIndex (elegido)

* ✅ **Pros:** Incrementalismo de primera clase; memoización por función; live-watch; embebido sin puerto; targets intercambiables (escape hatch de migración); embeddings locales o LiteLLM; Apache-2.0; SDK Python declarativo y legible.
* ⚠️ **Cons:** Comunidad más joven que LightRAG; no trae servidor MCP propio (hay que escribir `tepochcalli-rag`, registrado en docs/TECH_DEBT.md); el parsing de PDF depende de Docling (costo CPU por PDF grande).
* ⚖️ **Neutral:** Adopta un modelo de "flujos declarativos" que el equipo debe aprender.

### LEANN

* ✅ **Pros:** ~97% menos almacenamiento; `leann_mcp` reutilizable.
* ⚠️ **Cons:** Latencia de recomputación en CPU con riesgo de exceder el criterio de 500ms; metadatos de cita delgados (comprometen el criterio 5); sin pipeline de ingesta/particionado equivalente (habría que escribir más glue).
* ⚖️ **Neutral:** Documentado como opción de migración futura (véase §8 Revisit triggers y docs/TECH_DEBT.md).

### LightRAG / RAG-Anything

* ✅ **Pros:** Grafo de conocimiento potente para preguntas multi-hop; ecosistema de investigación activo.
* ⚠️ **Cons:** LLM obligatorio por chunk indexado (viola el presupuesto de tokens, driver principal); requieren binding a un LLM externo; corren como daemon en puerto (violan Obsidian-safe).
* ⚖️ **Neutral:** —

### PageIndex

* ✅ **Pros:** Sin vector store; excelente en un documento largo único (tipo manual).
* ⚠️ **Cons:** LLM por consulta (costo y latencia); escala mal a corpus multi-documento (>5 docs), exactamente el caso de uso del vault.
* ⚖️ **Neutral:** —

## 6. Consequences

* ✅ **Positives:** El glue a escribir se limita al servidor MCP y la definición del flow; la política de tokens del usuario queda protegida por diseño; migrar de almacén vectorial queda barato (targets de CocoIndex).
* ⚠️ **Negatives / Risks:** Deuda: autoría del flow + servidor MCP (ver docs/TECH_DEBT.md); riesgo de API-breaking en versiones tempranas de CocoIndex → se pinea la versión en `.tepochcalli/pyproject.toml` (ADR-004).
* ⚖️ **Neutral:** La indexación queda expresada como código declarativo Python versionado en `.tepochcalli/flow/`.

## 7. Related Decisions

* ADR-002 — LanceDB embebido como target vectorial del flujo.
* ADR-004 — uv + venv del proyecto para instalar `cocoindex[lancedb]`.
* ADR-005 — MCP `tepochcalli-rag` como capa ports/adapters sobre este motor.
* ADR-006 — Modelo de embeddings default usado por el flow.

## 8. Compliance and Review

* **Success metrics:** Δ <30s, búsqueda <500ms, 0 tokens LLM por indexación en vaults de 10k notas + 1k PDFs.
* **Next review date:** 2027-04-21
* **Revisit triggers:** (a) CocoIndex abandona incremental/live-watch o cambia licencia; (b) latencia de búsqueda ingobernable en CPU; (c) el almacenamiento del índice domina el disco del usuario → evaluar migración a LEANN conservando el flow como productor.

---
