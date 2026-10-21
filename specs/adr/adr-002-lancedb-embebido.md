# ADR-002: Usar LanceDB embebido como almacén vectorial

* **Status:** Accepted
* **Date:** 2026-10-21
* **Decision Makers:** Arquitecto (entrevista /spec), Product Owner (usuario)
* **Consulted:** Soporte oficial de targets de CocoIndex
* **Informed:** Usuario final (investigador), autor del wizard de instalación
* **Traceability:** docs/UH.md, specs/spec-rag-engine.md, specs/spec-vault-structure.md, ADR-001

## 1. Context and Problem Statement

El flujo RAG necesita persistir ~100k vectores de 384 dimensiones con búsqueda ANN + FTS dentro de un vault de Obsidian que el usuario abre, mueve y sincroniza (git/Dropbox/OneDrive). Cualquier base con servidor, puerto o demonio choca con la regla de no interferencia (criterio 1 de UH.md) y con la premisa de que el workspace sea una carpeta autocontenida.

## 2. Decision Drivers

* **Embebido, file-based:** sin daemon, sin puerto, sin credenciales; el índice es solo un directorio más (`.tepochcalli/db/`).
* Compatibilidad nativa como target de CocoIndex (ADR-001).
* Soporte de índice vectorial (ANN) + índice full-text en el mismo almacén.
* Rendimiento suficiente para 10k notas + 1k PDFs con búsqueda <500ms en CPU.
* Portabilidad: la carpeta del vault debe poder copiarse/borrarse sin desinstalar nada.
* Bajo consumo de RAM (piso de 8GB, D4/TECH_DEBT del entorno CPU).

## 3. Considered Options

* **LanceDB** — librería embebida (Python/Rust) sobre formato de columnas Lance; file-based; ANN (IVF_PQ/HNSW-ish) + FTS; soportado por CocoIndex.
* **pgvector** — extensión de PostgreSQL; excelente, pero exige servidor PostgreSQL local con puerto y gestión de servicio.
* **Qdrant** — servidor de vectores dedicado (proceso/contenedor en puerto).
* **ChromaDB** — modo embebido disponible; soportado por CocoIndex; menos maduro en FTS híbrida y compactación.
* **SQLite (sqlite-vec)** — embebido y omnipresente; capacidad ANN/FTS híbrida más limitada para el volumen objetivo.

## 4. Decision Outcome

**Chosen option: LanceDB embebido**, porque es el único que combina cero infraestructura (archivos bajo `.tepochcalli/db/`), soporte oficial como target de CocoIndex, índices vectoriales + FTS híbridos, y manejo holgado del volumen objetivo (10k notas + 1k PDFs ≈ ~150MB de vectores a 384 dims) sin proceso residente que pueda interferir con Obsidian.

### 4.1 Confirmation

* Tras `cocoindex setup`, `.tepochcalli/db/` contiene solo archivos Lance (verificable con `ls`); ningún proceso escucha puertos nuevos (`ss -ltn` vacío de cambios).
* Búsqueda ANN+FTS sobre el corpus sintético 10k/1k en <500ms p95 (bench de Phase 5, docs/WORKFLOW.md).

## 5. Pros and Cons of the Options

### LanceDB (elegido)

* ✅ **Pros:** Sin servidor ni puerto; file-based portable; ANN + FTS híbrido; target soportado por CocoIndex; Python-first; good enough para decenas de miles de vectores en laptop.
* ⚠️ **Cons:** Ecosistema más joven que PostgreSQL; menos apto si mañana se quisiera búsqueda multi-usuario centralizada (fuera de scope); binarios dependientes de plataforma → justifica el venv aislado (ADR-004).
* ⚖️ **Neutral:** El índice viaja con el vault; se ignora en git (specs/spec-vault-structure.md).

### pgvector

* ✅ **Pros:** Estándar, robusto, SQL completo.
* ⚠️ **Cons:** Requiere servidor PostgreSQL instalado y corriendo → viola "sin daemon/sin puerto" y agrava la fricción de instalación.
* ⚖️ **Neutral:** Queda documentado como opción de migración (CocoIndex lo soporta).

### Qdrant

* ✅ **Pros:** Rendimiento alto, filtros potentes.
* ⚠️ **Cons:** Proceso servidor dedicado; mismo conflicto de interferencia que pgvector.
* ⚖️ **Neutral:** Opción de migración soportada por CocoIndex.

### ChromaDB

* ✅ **Pros:** Embebible, API simple.
* ⚠️ **Cons:** Híbrido ANN+FTS menos capaz; concurrencia/compactación débiles para el volumen objetivo.
* ⚖️ **Neutral:** Opción de migración soportada por CocoIndex.

### SQLite + sqlite-vec

* ✅ **Pros:** Cero dependencias externas, portátil.
* ⚠️ **Cons:** Sin FTS híbrida con re-ranking comparable al caso vector+texto de LanceDB; rendimiento ANN degradado en >50k filas.
* ⚖️ **Neutral:** Migración menor si algún día se pide "un solo archivo".

## 6. Consequences

* ✅ **Positives:** El vault sigue siendo una carpeta; el wizard solo crea `.tepochcalli/db/`; borrar el índice es `rm -rf` sin efectos secundarios.
* ⚠️ **Negatives / Risks:** Crecimiento de disco con el corpus (se presupuesta en docs/TRD.md); dos instancias de Obsidian/OpenCode sobre el mismo vault concurrentemente podrían escribir el índice a la vez → mitigación: el delta solo lo dispara `index_refresh()` (única ventana de escritura, ADR-005).
* ⚖️ **Neutral:** Estrategia de gitignore para `db/` definida en specs/spec-vault-structure.md.

## 7. Related Decisions

* ADR-001 — CocoIndex escribe en este target.
* ADR-004 — venv aislado que fija el wheel de lancedb.
* ADR-005 — `tepochcalli-rag` lee el índice vía la API pública del flow.

## 8. Compliance and Review

* **Success metrics:** 0 puertos escuchados atribuibles al vault; índice <2GB en corpus 10k/1k; búsqueda <500ms.
* **Next review date:** 2027-04-21
* **Revisit triggers:** Necesidad de compartición multi-usuario → reevaluar pgvector/Qdrant; dolores de concurrencia de escritura reales → serializar refresh o migrar target.

---
