# ADR-008: Transparencia de hardware y cambio de modelo sin reinstalar

* **Status:** Accepted
* **Date:** 2026-10-21
* **Decision Makers:** Arquitecto (follow-up entrevista /spec), Product Owner (usuario — aprobó las cuatro opciones "Recommended" del layer D8 vía question tool, 2026-10-21)
* **Consulted:** API pública de HuggingFace (verificado en vivo 2026-10-21 contra `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`); crate `sysinfo`; ADR-006 §6 (consecuencia de re-index)
* **Informed:** Autor del wizard (Rust), mantenedores de specs/spec-embeddings.md y specs/spec-installer-wizard.md, usuarios del vault
* **Traceability:** solicitud del usuario 2026-10-21 (NFR "cero-sorpresas" de hardware + UX de "cambié de opinión / elegí mal"); **refina (no reemplaza) ADR-007** D7.1 (menú "Embedding provider") y D7.4 (comandos de re-entrada `tepochcalli config embedder` / `tepochcalli reindex --confirm`); se apoya en ADR-006 §6 (LanceDB no puede mezclar dims → re-index completo) y ADR-004 (venv donde corre el embedder); docs/UH.md (requisitos, inmutable)

## 1. Context and Problem Statement

ADR-007 dio libertad de elegir embedder, pero el menú no responde la pregunta que más caro sale
errar: **¿cabrá este modelo en MI máquina?** (disco, RAM, GPU). Hoy el usuario solo lo descubre
tras la descarga o ante un índice lento/fallante. Además, la corrección de una elección errónea no
tiene camino de ida y vuelta atómico: `tepochcalli config embedder` avisa del `E_MODEL_MISMATCH`
pero el swap práctico implicaba reinstall o un re-index destructivo "a ciegas" (el índice viejo se
vacía antes de saber si el nuevo funciona). Nace la capa D8: requisitos visibles ANTES de elegir
y swap atómico sin reinstalar el workspace.

## 2. Decision Drivers

* NFR cero-sorpresas: los requisitos de hardware (💾 disk · 🧠 RAM · 🎮 GPU) deben verse antes de la selección, para presets y para IDs libres de HuggingFace.
* Detección honesta sin promesas: todo número mostrado lleva su procedencia (`medido`/`estimado`/`declarado`); una estimación nunca se presenta como garantía.
* No reinstalar ante elección errónea: "cambié de opinión / elegí mal" debe resolverse con un swap de modelo atómico, con rollback y sin tocar el resto del vault.
* Mantenimiento de defaults acotado: los datos de hardware curados viven en `presets.toml` (capa declarada), no en la UI — regla de ADR-007 D7.2 intacta.
* Superficie MCP estable: la capa D8 toca solo la instalación (wizard + spec-embeddings); el contrato MCP (`rag_status`, códigos `E_*`) no cambia en esta ola.

## 3. Considered Options

Ejes de decisión (cada uno con su opción elegida):

* **Eje 1 — badge incómodo:** **Option A: bloquear-duro** (el wizard impide elegir un modelo que no cabe) vs **Option B: advertir** (badge `no recomendado`, selección libre). *Elegida: B.*
* **Eje 2 — origen de requisitos:** **Option A: declarar-requisitos-sin-detección** (solo `presets.toml`, host ignorado) vs **Option B: autodetección+badges** (capas declarado → estimado → medido con perfilado del host). *Elegida: B, en las dos capas (declarado siempre; autodetección opt-in scope confirmado).*
* **Eje 3 — camino del swap:** **Option A: re-download-sin-rollback** (vaciar índice, regenerar, rezar) vs **Option B: flujo atómico** (índice viejo servable durante el re-index; old model solo se borra tras éxito; cualquier fallo = rollback cero). *Elegida: B.*

## 4. Decision Outcome

**Chosen option: las tres B**, porque convierten la incertidumbre de hardware en información
accionable pre-elección sin quitar libertad al usuario (coherente con ADR-007 D7.1: advertir, no
imponer) y hacen del swap de modelo una operación reversible hasta el conmutador atómico final.
La capa codificada es D8.1-D8.4, aprobada por el usuario el 2026-10-21.

### 4.1 D8.1 — Requisitos de hardware visibles ANTES de seleccionar

Cada fila del menú muestra, pre-elección: `💾 disk (MB) · 🧠 RAM requirement · 🎮 GPU status`,
tanto para presets como para IDs libres de HuggingFace. Tres fuentes de verdad en orden
decreciente de certidumbre, cada número etiquetado con su procedencia:

1. **Medido** (ground truth): el gate test-embed de ADR-007 D7.1 se extiende a muestrear el pico de RSS durante la prueba de embedding para TODOS los caminos locales (presets y HF custom por igual); el wizard muestra la huella medida una vez ejercitado el modelo.
2. **Estimado (API HF)**: para cualquier id de HF, el wizard consulta la API pública ANTES de descargar: `safetensors.parameters.total` (conteo de parámetros), tamaños de blobs de model.safetensors (disco exacto), campo `gated` (→ requisito de `HF_TOKEN` visible temprano) y `pipeline_tag` + tags (`sentence-similarity`/`feature-extraction`/`sentence-transformers`) como pre-filtro barato del gate (un modelo sin ninguno de los tres se rechaza como "not an embedding model" con semántica `E_MODEL_INVALID`). Fórmula de RAM, canónica: `params × 4 bytes × 1.3 overhead factor` (fp32, CPU resident). VRAM para modo GPU: el mismo tamaño de pesos + margen de activaciones.
3. **Declarado (presets.toml v2)**: campos de hardware curados en la schema ya existente: `disk_mb` (int), `min_ram_gb` (float), `rec_ram_gb` (float, holgado), `gpu_recommended` (bool, ya existía — se conserva). `presets.toml` sigue embebido vía `include_str!` en el binario Rust; la UI nunca hardcodea datos de modelos.

Regla NFR: todo número mostrado se etiqueta con su procedencia (`medido`/`estimado`/`declarado`)
— nunca presentar una estimación como promesa.

### 4.2 D8.2 — Autodetección del host + badges (alcance opt-in CONFIRMADO)

En el paso "Embedding provider" el wizard sondea: RAM total y disco libre vía crate `sysinfo`;
presencia de GPU vía probe opcional de `nvidia-smi`/`rocm-smi` en PATH (ausencia silenciosa = no
hay GPU, no es error). Badge por opción calculado por ratio (`rec_ram_gb` / RAM disponible):
`recommended` (cabe con ≥50% de margen), `viable` (cabe, margen bajo), `no recomendado` (el
requisimiento estimado excede la RAM disponible, o `gpu_recommended` && sin GPU detectada). Si el
sondeo falla (`/proc` ilegible, plataforma exótica): fallback a valores declarados, SIN badge de
veredicto, y la instalación continúa normal — nunca un crash. Ejemplo (host de 4 GB de RAM): fila
MiniLM badge `recommended` (≈0.5 GB disk, ~0.9 GB est. RAM); fila `BAAI/bge-m3` badge
`no recomendado` (≈2.3 GB disk, ~2.9 GB est. RAM).

### 4.3 D8.3 — Advertir, nunca bloquear (locked)

Un badge `no recomendado` es advertencia; la selección sigue siendo posible (cuantización,
"sé lo que hago", la máquina más grande de mañana). Coherente con la fila ya existente de la
matriz de edge cases en specs/spec-embeddings.md ("GPU insuficiente para `BAAI/bge-m3` →
advertencia, no bloqueo") — se referencia, no se re-regula.

### 4.4 D8.4 — Swap de modelo atómico sin reinstalar el workspace

Extiende `tepochcalli config embedder` (D7.4) a un flujo completo de swap — la respuesta
user-facing a "cambié de opinión / elegí mal":

1. Muestra el estado actual: model, dims, filas del índice, tamaño de db (lectura local con forma `rag_status`).
2. El usuario elige el nuevo embedder (mismo menú D7.1 + transparencia D8.1 + badges D8.2).
3. Advertencia explícita de re-index: re-index completo requerido (LanceDB no puede mezclar dimensiones — consecuencia ADR-006 §6), tiempo estimado desde el tamaño del índice actual; requiere `--confirm` (evoca el contrato de comando D7.4: `tepochcalli reindex --confirm`).
4. Descarga del modelo nuevo → gate test-embed (RSS medido registrado) → re-index con el nuevo embedder. EL ÍNDICE VIEJO PERMANECE INTACTO Y SERVABLE DURANTE TODO EL PROCESO (el target gestionado de CocoIndex construye filas nuevas; la tabla vieja no se elimina hasta el éxito).
5. Éxito → conmutación atómica de `config.model` + metadatos; ENTONCES se borra el cache del modelo viejo de `models/` (auto-GC). El flag `--keep-previous` desactiva el borrado.
6. Fallo en CUALQUIER paso → rollback: config, índice viejo y modelo viejo intactos; el vault nunca queda en half-state. Durante todo el flujo la disponibilidad de `search` solo degrada para la indexación de archivos nuevos, nunca para lecturas del índice existente.

Superficie opcional de higiene (nice-to-have, marcado P2): `tepochcalli models list` /
`tepochcalli models prune`.

## 5. Pros and Cons of the Options

### Option B — advertir (Eje 1, elegida)

* ✅ **Pros:** libertad intacta (misma filosofía D7.1); el usuario con cuantización o hardware atípico no queda excluido; cero código de bloqueo.
* ⚠️ **Cons:** alguien elegirá el modelo grande y sufrirá — mitigado por badge + advertencia + swap D8.4 barato.
* ⚖️ **Neutral:** consistente con la regla existente "advertencia, no bloqueo" de la matriz D7.

### Option A — autodetección+badges (Eje 2, elegida en dos capas)

* ✅ **Pros:** requisito verificado contra el host real (no genérico); `medido` da ground truth sin prometer de más; `estimado` cubre IDs libres sin tocar disco.
* ⚠️ **Cons:** superficie de detección nueva (sondeos de SO que pueden fallar → fallback obligatorio); dependencia de la API de HF para ids custom en hosts sin red (degrada a `declarado`).
* ⚖️ **Neutral:** la capa declarada (`presets.toml` v2) sigue siendo la fuente curada; los nuevos campos son aditivos.

### Option B — flujo atómico (Eje 3, elegida)

* ✅ **Pros:** el swap deja de requerir reinstall ni fe; invariantes claras (índice viejo servable durante el re-index; modelo viejo borrado solo post-éxito); fallo = cero cambio de estado.
* ⚠️ **Cons:** el flujo debe mantener dos cuerpos de filas (viejas/nuevas) simultáneamente — más disco transitorio; la conmutación atómica y el auto-GC son lógica nueva del wizard; borrar el modelo viejo es irreversible (mitigado por `--keep-previous`).
* ⚖️ **Neutral:** aprovecha el target gestionado de CocoIndex (ya re-escribe filas por hash); el contrato MCP no cambia — `E_MODEL_MISMATCH` sigue siendo la señal de mismatch mientras el swap está pendiente.

### Options rechazadas (A de Eje 1, A de Eje 2, A de Eje 3)

* ❌ Bloquear-duro: viola la filosofía de libertad de ADR-007 y castiga hardware atípico.
* ❌ Solo-declarado: ignora el host real; "8GB RAM" en el doc no responde "¿en MI laptop de 4GB?".
* ❌ Re-download-sin-rollback: convierte "elegí mal" en pérdida de servicio de búsqueda durante todo el re-index — inaceptable como respuesta al driver cero-sorpresas.

## 6. Consequences

* ✅ **Positives:** transparencia pre-elección con procedencia honesta del número; "elegí mal" se resuelve sin reinstalar con invariante de cero half-state; los defaults curados siguen siendo datos (`presets.toml` v2) — la UI del wizard nunca se toca (ADR-007 D7.2 intacto); el contrato MCP queda estable en esta ola.
* ⚠️ **Negatives / Risks:** la medición de RSS añade segundos a la instalación (se paga una vez por modelo); la dependencia de la API de HF para validar ids custom falla en offline → fallback a `declarado` (nunca crash); el borrado del modelo viejo post-éxito es irreversible → mitigado por `--keep-previous`; dos cuerpos de filas durante el re-index suben el pico transitorio de disco; los umbrales de badge son heurística (rec_ram_gb / RAM) que puede etiquetar mal en hardware exótico → fallback sin veredicto lo acota.
* ⚖️ **Neutral:** la superficie CLI del wizard crece (flags del swap + P2 opcional `tepochcalli models list` / `tepochcalli models prune`); el swap D8.4 sustituye en la práctica al procedimiento manual de spec-embeddings como camino recomendado, sin deprimirlo.

## 7. Related Decisions

* ADR-007 — **refinado, no reemplazado**: ADR-007 permanece Accepted; D8 añade la capa de transparencia (D8.1-D8.3) sobre su menú D7.1 y la semántica atómica sobre sus comandos D7.4 (`tepochcalli config embedder`, `tepochcalli reindex --confirm`, `presets.toml`, códigos `E_*` intocados).
* ADR-006 §6 — la consecuencia "dimensión fija del store → re-index completo al cambiar modelo" es el motivo del paso 3 (advertencia) y del re-index del swap.
* ADR-004 — el RSS se mide dentro del venv gestionado por uv; la cache de modelos que GC-kea el swap vive en `.tepochcalli/models/`.
* ADR-005 — durante el swap el índice viejo sigue servido por los mismos contratos MCP; `E_MODEL_MISMATCH` marca el estado pre-conmutación.

## 8. Compliance and Review

* **Success metrics / confirmation (Phase 5, docs/WORKFLOW.md):**
  * host fixture de 4 GB de RAM → la fila de `BAAI/bge-m3` muestra badge `no recomendado` y aun así es seleccionable; la fila MiniLM muestra `recommended`; cada número lleva etiqueta de procedencia (`medido`/`estimado`/`declarado`).
  * swap en vault fixture: durante el re-index el índice viejo queda **consultable** (una `search` de prueba resuelve contra filas viejas) y tras el éxito el modelo viejo **no está** en `models/` (auto-GC); con `--keep-previous` sí está.
  * descarga interrumpida a mitad del swap → cambio de estado CERO: config, índice viejo y modelo viejo idénticos byte-a-byte al pre-swap.
  * gate test-embed: para presets Y custom HF, el RSS pico se mide y se muestra como `medido`; un id sin `pipeline_tag`/tags de embedding es rechazado pre-descarga con semántica `E_MODEL_INVALID`.
* **Next review date:** 2027-04-21 (junto con ADR-006/ADR-007).
* **Revisit triggers:** si la divergencia medido-vs-estimado supera ~2× sistemáticamente en presets → recalibrar el factor 1.3 de la fórmula; si la API de HF cambia campos (`safetensors.parameters.total`/`gated`) → re-validar la extracción D8.1 y bump de release del wizard; si `presets.toml` necesitara campos fuera de la schema → D7.2 se re-abre (trigger heredado de ADR-007 §8); si los badges generaran soporte excesivo ("me dijiste viable y se cayó") → revisar umbrales con datos de telemetry-free logs locales.

---
