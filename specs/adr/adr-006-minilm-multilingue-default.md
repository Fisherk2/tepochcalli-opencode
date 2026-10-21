# ADR-006: Paraphrase-multilingual-MiniLM-L12-v2 como modelo de embeddings default

* **Status:** Accepted
* **Date:** 2026-10-21
* **Decision Makers:** Arquitecto (entrevista /spec), Product Owner (usuario)
* **Consulted:** Catálogo de SentenceTransformers (org HuggingFace `sentence-transformers`); requisitos de hardware UH.md
* **Informed:** Usuario final, autor del wizard (descarga del modelo), mantenedores de spec-embeddings
* **Traceability:** docs/UH.md (deuda cognitiva 6), specs/spec-embeddings.md, specs/spec-installer-wizard.md, ADR-001/004

## 1. Context and Problem Statement

El pipeline de indexación necesita un modelo de embeddings que corra **localmente, en CPU, con 8GB de RAM**, sobre contenido mayormente bilingüe español-inglés (notas de investigación hispanohablantes + literatura académica en inglés), con descarga única en el wizard y coste $0 por consulta. La pregunta abierta de UH.md: ¿dónde configuran los usuarios sus modelos locales y cuáles son los requisitos mínimos?

## 2. Decision Drivers

* Multilingüe real (ES+EN como piso) — el vault se usa en español.
* Latencia de embedding de query pequeña en CPU (contribuye al presupuesto de <500ms de ADR-005).
* Huella: peso del modelo descargable una vez y cacheable en `.tepochcalli/models/`.
* Sin coste por uso ni filtración de datos a proveedores externos por defecto.
* Camino de upgrade declarado sin re-arquitectura (cambiar nombre del modelo en config).

## 3. Considered Options

* **paraphrase-multilingual-MiniLM-L12-v2** — 384 dims, ~470MB, familia MiniLM destilada, 50+ idiomas vía sentencepiece, estándar de facto para bilingüe ES/EN en CPU.
* **all-MiniLM-L6-v2** — 384 dims, ~90MB, rapidísimo, pero entrenado casi exclusivamente en inglés.
* **BAAI/bge-m3** — 1024 dims, denso+esparseo+máscara multi-vector, ~2.3GB, líder multilingüe en MTEB; pensado para GPU o CPU tolerante a latencia.
* **API externa de embeddings (vía LiteLLM: OpenAI, Voyage, etc.)** — calidad alta, cero carga de hardware, pero coste por token, clave API y datos salen de la máquina.
* **multilingual-e5-small/base** — alternativas multilingües competitivas con prefijos de instrucción "query:/passage:" que añaden fricción de uso correcto.

## 4. Decision Outcome

**Chosen option: paraphrase-multilingual-MiniLM-L12-v2**, porque es el único candidato que cumple a la vez: multilingüe ES+EN verificable, ~470MB descargables una vez por el wizard, inferencia de query en decenas de ms en CPU (compatible con el presupuesto de 500ms) y coste cero. El upgrade path queda documentado, no improvisado: `BAAI/bge-m3` para usuarios con GPU (mayor recall/dims 1024) o API vía LiteLLM con clave en `.tepochcalli/config/tepochcalli.toml` / variable de entorno. La consecuencia conocida — cambiar de modelo implica re-indexación completa — se registra en docs/TECH_DEBT.md y en el procedimiento de specs/spec-embeddings.md.

### 4.1 Confirmation

* El wizard descarga el modelo a `.tepochcalli/models/` vía `SENTENCE_TRANSFORMERS_HOME`/`HF_HOME` y la indexación inicial corre sin red después (flag `--offline` en re-instalaciones).
* Benchmark Phase 5: embedding de query + búsqueda ANN <500ms p95 sobre corpus 10k/1k en CPU de 8GB.

## 5. Pros and Cons of the Options

### paraphrase-multilingual-MiniLM-L12-v2 (elegido)

* ✅ **Pros:** Multilingüe ES/EN sólido; 384 dims ≈ 150MB de vectores por 100k chunks (presupuesto LanceDB); rápido en CPU; soportado de primera clase por `SentenceTransformerEmbedder` de CocoIndex; un solo artefacto de 470MB.
* ⚠️ **Cons:** Recall inferior a gigantes modernos en literatura densa; la tokenización sentencepiece es más lenta que WordPiece pura; no soporta sparse/hybrid nativo (el FTS lo pone LanceDB).
* ⚖️ **Neutral:** Dimensión fija del store → re-index completo al cambiar modelo.

### all-MiniLM-L6-v2

* ✅ **Pros:** Mínimo peso y máxima velocidad.
* ⚠️ **Cons:** Rendimiento pobre en español — el vault es bilingüe por diseño; falsearía el criterio de calidad de recuperación.
* ⚖️ **Neutral:** —

### BAAI/bge-m3

* ✅ **Pros:** Mejor recuperación multilingüe; híbrido denso+esparseo.
* ⚠️ **Cons:** ~2.3GB y latencia de varios segundos por lote en CPU sin optimización; excede el piso de hardware declarado.
* ⚖️ **Neutral:** Documentado como upgrade oficial (GPU recomendada) en spec-embeddings.

### API externa (LiteLLM)

* ✅ **Pros:** Mejor calidad con modelos de frontier; cero hardware.
* ⚠️ **Cons:** Coste por token continuo, gestión de claves, privacidad (material de investigación sale del host), dependencia de red en la indexación.
* ⚖️ **Neutral:** Soportado como opción de configuración, no default (UH.md: minimizar consumo de tokens).

### multilingual-e5-*

* ✅ **Pros:** fuerte en MTEB multilingüe.
* ⚠️ **Cons:** exige prefijos de instrucción consistentes en índice y query; error de uso silencioso y difícil de auditar desde CocoIndex.
* ⚖️ **Neutral:** —

## 6. Consequences

* ✅ **Positives:** Experiencia determinista "funciona sin configurar nada"; coste marginal de hardware conocido; la cache en `.tepochcalli/models/` hace offline las reinstalaciones.
* ⚠️ **Negatives / Risks:** Si el usuario cambia modelo sin re-indexar, resultados se degradan silenciosamente → el flow debe versionar el nombre de modelo en los metadatos del índice y `search` debe negarse a mezclar dimensiones; 470MB extra en la descarga del wizard (primera vez requiere internet).
* ⚖️ **Neutral:** Se documenta la matriz local vs externa y el procedimiento de swap en specs/spec-embeddings.md.

## 7. Related Decisions

* ADR-001 — CocoIndex consume el modelo vía `SentenceTransformerEmbedder` o LiteLLM.
* ADR-002 — LanceDB almacena vectores de 384 dims con este modelo.
* ADR-004 — el wheel de sentence-transformers vive pineado en el venv.

## 8. Compliance and Review

* **Success metrics:** p50 de calidad de búsqueda aceptable (nDCG subjetivo verificado en fixtures dorados ES/EN); 0 quejas de "necesité GPU para el default".
* **Next review date:** 2027-04-21
* **Revisit triggers:** MTEB multilingüe muestra brecha práctica grande para ES → promover bge-m3 a default con detección de GPU; LiteLLM abarata embeddings → ofrecer API como default de facto solo si el usuario lo elige.

---
