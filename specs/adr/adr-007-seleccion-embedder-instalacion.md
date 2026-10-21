# ADR-007: Selección de embedder en la instalación (menú con default preseleccionado)

* **Status:** Accepted
* **Date:** 2026-10-21
* **Decision Makers:** Arquitecto (follow-up entrevista /spec), Product Owner (usuario — aprobó D7.1-D7.4)
* **Consulted:** Catálogo de SentenceTransformers/HuggingFace; contratos de specs/spec-mcp-server.md; requisitos de hardware UH.md
* **Informed:** Autor del wizard (Rust), mantenedores de specs/spec-embeddings.md y specs/spec-installer-wizard.md, usuarios del vault
* **Traceability:** docs/UH.md (deuda cognitiva Q6 — "¿dónde configure sus modelos locales… API key de embebidos externos?") + follow-up de entrevista /spec aprobado por el usuario el 2026-10-21; **reemplaza parcialmente ADR-006 §4.1** (la descarga obligatoria del modelo en el wizard); relacionado con ADR-004 (venv donde corre el embedder y viven los artefactos) y ADR-005 (la frontera MCP donde vive `rag_status`)

## 1. Context and Problem Statement

ADR-006 eligió el modelo default y, en su §4.1, convirtió esa elección en un comportamiento del
wizard: descarga obligatoria e incondicional de `paraphrase-multilingual-MiniLM-L12-v2` en la
fase de modelos. La deuda cognitiva Q6 de UH.md pregunta además dónde configura el usuario *sus*
modelos locales y cómo añadir una API key externa. El wizard actual no tiene respuesta para
ninguna de las dos; y un modelo HF mal elegido (no-embedding) puede cargarse en silencio por
`sentence-transformers`, degradando la búsqueda sin ningún síntoma. Hace falta libertad de elección
sin sacrificar el ready-to-use, un modo sin-modelo honesto y detección de fallo mudo.

## 2. Decision Drivers

* No restringir la UX de modelos: el usuario debe poder elegir preset local, ID libre de HuggingFace o API externa.
* Preservar el camino feliz cero-decisión: el default preseleccionado mantiene el "funciona sin configurar nada" de ADR-006.
* Reducir la carga de mantenimiento del default hardcodeado: el catálogo de modelos debe ser datos, no UI.
* Modo sin-modelo honesto: instalar sin embedder debe verse como estado `degraded` explícito, nunca como media configuración ni como éxito falso.
* Detección de fallo mudo: gate test-embed en el wizard + códigos de error estructurados + herramienta de diagnóstico en el MCP.

## 3. Considered Options

* **Option A:** Menú "Embedding provider" con default preseleccionado — cinco salidas (default, presets alternativos, ID HF libre con gate, API LiteLLM, configurar después).
* **Option B:** Elección obligatoria sin default — el wizard fuerza al usuario a elegir modelo antes de continuar.
* **Option C:** Estatus quo — descarga incondicional del MiniLM (comportamiento actual, ADR-006 §4.1).
* **Option D:** Catálogo remoto en vivo — el wizard consulta la API de HuggingFace en la instalación y lista modelos dinámicamente.

## 4. Decision Outcome

**Chosen option: Option A**, porque satisface a la vez los drivers: libertad de elección (Q6),
zero-decision happy path (pre-selección RECOMENDADA), mantenimiento del catálogo como datos
(`presets.toml`) y modo honesto `degraded` con observabilidad (`rag_status` + `E_*`). El resto del
documento codifica D7.1-D7.4 aprobadas por el usuario.

### 4.1 D7.1 — Wizard embedder UX = menú con default preseleccionado (no impuesto)

El wizard gana un paso **"Embedding provider"** con cinco salidas:

1. `paraphrase-multilingual-MiniLM-L12-v2` — RECOMENDADO, pre-seleccionado (preserva ready-to-use).
2. Presets locales alternativos: `BAAI/bge-m3` (GPU recomendada, ~2.3GB), `all-MiniLM-L6-v2` (~90MB, EN-only, calidad ES limitada) — con peso estimado y detección de GPU; advertencia, no bloqueo.
3. ID libre de HuggingFace → portero **test-embed**: el wizard descarga e incrusta una frase de prueba (`"tepochcalli embedding check"`), exige respuesta válida + dims + nombre, y escribe `model + dims` en los metadatos del índice; rechaza modelos que sentence-transformers cargaría en silencio como no-embeddings. Campo opcional `HF_TOKEN` para modelos gated.
4. API externa vía LiteLLM (OpenAI/Cohere/Voyage/Ollama-compatible) + API key en `.tepochcalli/config/tepochcalli.toml` (gitignored, nunca en logs) → sin descarga local.
5. "Configurar después" → el vault se instala COMPLETO (todas las demás fases del wizard corren), la indexación inicial se omite, RAG queda en estado `degraded`, y el wizard muestra el checklist final de re-entrada sin escribir half-config.

### 4.2 D7.2 — Presets como datos, no UI

`presets.toml` va embebido en el binario Rust del wizard (`include_str!`): tabla con campos
`{name, hf_id, dims, size_mb, gpu_recommended, recommended_flag}`. Actualizar modelos = editar
datos + release vía cargo-dist (ADR-003); la UI del wizard nunca se toca. Su revisión periódica
queda vinculada a los revisit-triggers ya existentes de ADR-006 §8.

### 4.3 D7.3 — Observabilidad del modo degraded

Cuarto tool MCP `rag_status()` en `tepochcalli-rag` (JSON mínimo, coste de tokens despreciable)
+ dialecto de errores estructurados en los tools existentes, con códigos:
`E_NO_EMBEDDER` (sin modelo ni API), `E_API_AUTH` (key inválida/expirada — detectada al primer
embed; proveedor nombrado, clave NUNCA loggeada), `E_MODEL_MISMATCH` (`config.model` ≠ modelo del
índice — `search` se niega a cruzar dims), `E_MODEL_INVALID` (custom HF falló el test-embed o no
es embedding model), `E_OFFLINE_NO_CACHE` (modo `--offline` sin `models/` cacheado). Regla del
vault (`AGENTS.md` del workspace, referenciada en spec-agent-workflow): ante cualquier `E_*`, el
agente llama `rag_status` y reporta al usuario la solución exacta, no el error crudo.

### 4.4 D7.4 — Comandos de re-entrada

`tepochcalli config embedder` (abre el menú D7.1 post-instalación) y `tepochcalli reindex --confirm`
(swap de modelo = re-index completo destructivo; requiere confirmación explícita; procedimiento
alineado con specs/spec-embeddings.md §Procedimiento de swap de modelo).

## 5. Pros and Cons of the Options

### Option A — Menú con default preseleccionado (elegida)

* ✅ **Pros:** libertad real de elección (Q6); happy path intacto por pre-selección; catálogo mantenible como datos (`presets.toml`); modo sin-modelo honesto con checklist de re-entrada; fallo mudo imposible (gate test-embed + `E_*` + `rag_status`).
* ⚠️ **Cons:** superficie de validación extra en el wizard (gate, claves, GPU); cinco códigos de error nuevos que testear; dos comandos CLI nuevos de re-entrada.
* ⚖️ **Neutral:** ADR-006 permanece Accepted como elección del modelo default; esta ADR solo reemplaza su §4.1.

### Option B — Elección obligatoria

* ✅ **Pros:** obliga a decisión consciente; cero riesgo de default inapropiado.
* ⚠️ **Cons:** rompe ready-to-use; re-crea exactamente la deuda cognitiva que UH.md pide eliminar; fricción inaceptable para el perfil "investigador sin DevOps".
* ⚖️ **Neutral:** —

### Option C — Estatus quo (descarga incondicional)

* ✅ **Pros:** cero cambios; camino feliz garantizado.
* ⚠️ **Cons:** impone modelo; sin respuesta a la pregunta de API key de Q6; modo `--skip-model` deja un `INDEX_EMPTY` engañoso en lugar de un estado degraded honesto.
* ⚖️ **Neutral:** —

### Option D — Catálogo remoto vía API de HuggingFace

* ✅ **Pros:** catálogo siempre fresco; acceso a cualquier modelo sin release del wizard.
* ⚠️ **Cons:** red obligatoria en un paso que hoy no la exige; supply-chain sin curar (el wizard instalaría cualquier ID publicado); sin control sobre pesos/requisitos mostrados.
* ⚖️ **Neutral:** —

## 6. Consequences

* ✅ **Positives:** libertad del usuario + zero-decision happy path (default preseleccionado) + presets como datos: actualizar el catálogo es editar `presets.toml` y publicar vía cargo-dist, sin tocar la UI del wizard.
* ⚠️ **Negatives / Risks:** superficie de validación extra en el wizard (gate test-embed, verificación de claves, detección de GPU); cinco códigos de error `E_*` nuevos que mantener y testear en contract tests; los comandos de re-entrada (`tepochcalli config embedder`, `tepochcalli reindex --confirm`) amplían la superficie CLI del wizard, que ahora debe versionarse como contrato.
* ⚖️ **Neutral:** ADR-006 queda intacto para la elección del modelo default (Option A lo conserva como salida 1 pre-seleccionada); el estado degraded es ahora un modo soportado, no un error de instalación.

## 7. Related Decisions

* ADR-006 — **parcialmente reemplazado**: su §4.1 (descarga obligatoria en el wizard) queda sin efecto; la elección del modelo default MiniLM sigue Accepted.
* ADR-004 — el venv del proyecto ejecuta sentence-transformers/LiteLLM y alberga `models/` donde aterrizan los presets.
* ADR-005 — `rag_status` y los códigos `E_*` viven detrás de la frontera MCP; el harness nunca consulta el motor directamente.
* ADR-003 — `presets.toml` viaja embebido en el binario publicado por cargo-dist.

## 8. Compliance and Review

* **Success metrics / confirmation (Phase 5, docs/WORKFLOW.md):**
  * instalación eligiendo la salida 5 ("Configurar después") → `search` responde `E_NO_EMBEDDER`, `rag_status` reporta `health.state = degraded` con `fix_hint` accionable, y el vault quedó instalado completo con checklist final (sin half-config).
  * instalación eligiendo la salida 3 (ID libre) con un modelo de basura (no-embedding) → rechazo en el gate test-embed del wizard; no se escribe config a medias.
  * contract tests: los cinco códigos `E_*` con su payload `{error:{code,message,fix_hint}}` y el shape de `rag_status` (<200 tokens por forma).
* **Next review date:** 2027-04-21 (junto con ADR-006).
* **Revisit triggers:** los de ADR-006 §8 aplican al contenido de `presets.toml` (MTEB muestra brecha para ES → promover `BAAI/bge-m3` con detección de GPU; LiteLLM abarata embeddings → recomendar API visible). Si `presets.toml` necesitara campos fuera de su schema, D7.2 se re-abre con ADR nuevo.

---
