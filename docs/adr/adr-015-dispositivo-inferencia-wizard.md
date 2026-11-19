# ADR-015: Elección explícita de dispositivo de inferencia y catálogo de embedder en el wizard

* **Status:** Accepted 2026-11-19
* **Date:** 2026-11-18
* **Decision Makers:** Fisherk2 (dueño del repo; aprobación del FTR 2026-11-19, requisito H9 del flujo destino, docs/BACKLOG.md §2 / US-H9); Arquitecto (redacción)
* **Consulted:** [ADR-007](adr-007-seleccion-embedder-instalacion.md) (D7.1/D7.4), [ADR-008](adr-008-transparencia-hardware-cambio-modelo.md) (D8.1-D8.3), [spec-embeddings](../../specs/spec-embeddings.md):231 (autoselección rechazada); código vigente del wizard y del flow (`presets.rs`, `embedder_config.rs`, `swap.rs`, `config.py`)
* **Informed:** Autor del wizard (Rust), mantenedores de specs/spec-embeddings.md y specs/spec-installer-wizard.md, usuarios del vault
* **Traceability:** docs/BACKLOG.md §2 / US-H9 — «Change Embedder»; docs/BACKLOG.md §2 «Wizard de instalación: flujo destino (2026-11-18)» («no se implementan ni se aprueban aquí»); [spec-embeddings](../../specs/spec-embeddings.md); [spec-installer-wizard](../../specs/spec-installer-wizard.md)

> **Nota de alcance:** este ADR **nació Proposed** el 2026-11-18 y pasa a **Accepted** con el FTR
> del dueño del **2026-11-19** (docs/BACKLOG.md §2 «Wizard de instalación: flujo destino
> (2026-11-18)»), tras recorrer lo que exige AGENTS.md §Delegation Patterns `:204-205` — «Decisiones
> D1-D6: NO se re-litigan en código — requieren ADR nuevo aprobado por el usuario», aplicable a
> D1-D8. **REFINE** ADR-007 y ADR-008 — no los sustituye en su conjunto, no los borra, no los
> re-edita (son *Accepted*; precedente de esta redacción: el propio ADR-008 Traceability `:8`,
> «refina (no reemplaza) ADR-007»). Los drifts de código detectados (§1) se materializan en la
> Phase 6.5: este ADR no toca ningún `.rs`/`.py`.

## 1. Context and Problem Statement

El requisito H9 del flujo destino (docs/BACKLOG.md §2 / US-H9) ordena que el wizard pregunte
**explícitamente** el dispositivo de inferencia a los modelos locales — `cpu` preseleccionado;
`cuda`/`cuda:N` solo cuando la sonda detecta GPU (docs/BACKLOG.md §2 / US-H9) —, ofrezca el catálogo local
(MiniLM recomendado y preseleccionado, `BAAI/bge-m3` con GPU recomendada, más ID libre de
HuggingFace con gate `test-embed` y `HF_TOKEN` opcional — docs/BACKLOG.md §2 / US-H9) y aclare la rama
de API externa (LiteLLM deriva el endpoint del prefijo de `model`; **no existe campo de
endpoint** — docs/BACKLOG.md §2 / US-H9). El contrato actual del wizard no lo cubre: el catálogo `Preset`
no tiene campo `device` (`crates/tepochcalli/src/config/presets.rs:10-33`), la config generada
hardcodea `device = "cpu"` (`crates/tepochcalli/src/application/embedder_config.rs:42`) y la
re-entrada `config embedder` lo reescribe vía `picked_config_body()`
(`crates/tepochcalli/src/application/swap.rs:422`), pisoteando la elección manual del usuario.

## 2. Decision Drivers

* **Determinismo del índice:** «un índice, un modelo» — la autoselección de dispositivo en
  runtime está RECHAZADA en [spec-embeddings](../../specs/spec-embeddings.md):231 (un mismo vault
  cambiaría de espacio vectorial según hardware).
* **NFR cero-sorpresas (D8.1-D8.3):** cada cifra con su procedencia y cada badge como
  ADVERTENCIA, nunca bloqueo (ADR-008 §4.1-4.3, docs/BACKLOG.md §2 / US-H9).
* **No-destructividad de la re-entrada:** `tepochcalli config embedder` debe preservar la
  elección existente como preselección (docs/BACKLOG.md §2 / US-H9), hoy la sobreescribe a `cpu`.
* **Catálogo como datos, no UI (D7.2, ADR-007 §4.2 `:52-57`):** lo que se añada al contrato
  viaja en `presets.toml`, no hardcodeado en la UI.
* **Libertad con verdad:** el usuario puede forzar GPU sin detección, pero debe verlo apagado
  con la razón antes de decidir (docs/BACKLOG.md §2 / US-H9).

## 3. Considered Options

* **Option A:** elección EXPLÍCITA del dispositivo en el wizard + campo `device` en el catálogo
  y en `tepochcalli.toml`, preservada en la re-entrada. Elegida (refina ADR-007/008).
* **Option B:** autoselección del dispositivo en runtime según hardware detectado — RECHAZADA
  (ya lo está en spec-embeddings.md:231 y ADR-008; este ADR la reafirma, no la reabre).
* **Option C:** estatus quo — `cpu` fijo, sin pregunta y sin campo en `Preset`: no cumple H9 y
  deja a los usuarios de `BAAI/bge-m3`-GPU sin camino documentado.

## 4. Decision Outcome

**Chosen option: Option A.** Se AÑADE al contrato de instalación (refinando ADR-007 D7.1/D7.4
y ADR-008 D8.x, sin sustituirlos en su conjunto):

* **(a) Campo `device` en el catálogo `Preset` del wizard.** Hoy `Preset`
  (`crates/tepochcalli/src/config/presets.rs:10-33`) carece de él —los campos son `name`,
  `hf_id`, `revision`, `dims`, `size_mb`, `disk_mb`, `min_ram_gb`, `rec_ram_gb`,
  `gpu_recommended`, `recommended_flag`— y `embedder_config.rs:42` hardcodea
  `device = "cpu"`. El catálogo (`presets.toml`, D7.2) gana el campo como dato.
* **(b) `device` se escribe en `[embedding].device` de `tepochcalli.toml`** y aplica **tanto a
  la indexación como a las búsquedas**, que comparten el mismo embedder (docs/BACKLOG.md §2 / US-H9). El
  flow ya consume la clave: `config.py:121` (`device: str = DEFAULT_EMBEDDING_DEVICE`, E1/D11)
  — el hueco está solo en el lado del wizard.
* **(c) La re-entrada `tepochcalli config embedder` PRESERVA el valor existente como
  preselección** (docs/BACKLOG.md §2 / US-H9) para no sobrescribir una elección manual. Hoy
  `swap.rs:422` `picked_config_body()` reconstruye el cuerpo completo y pisa `device` a `cpu`;
  es **drift a corregir en implementación futura, NO en este ADR**.

### 4.1 Reafirmado (NO reabierto)

* La **autoselección de dispositivo en runtime sigue RECHAZADA** por no-determinismo del
  índice ([spec-embeddings](../../specs/spec-embeddings.md):231; ADR-008 §2-4, capas declarado→estimado→
  medido). GPU **NO se autoelige**: sin detección por la sonda (`nvidia-smi`/`rocm-smi`,
  ADR-008 §4.2 `:58-60`), la opción GPU se muestra como **botón deshabilitado con la razón
  `GPU no detectada`** (docs/BACKLOG.md §2 / US-H9).
* Si el usuario **fuerza** el dispositivo y no está disponible, se **advierte con procedencia
  `medido`, nunca se bloquea** (docs/BACKLOG.md §2 / US-H9; coherente con D8.3 «Advertir, nunca
  bloquear (locked)», ADR-008 §4.3 `:68-70`); el fallo efectivo se produciría al cargar el
  modelo, no al configurar.

### 4.2 Procedencia de las cifras (hereda D8.1, ADR-008 §4.1 `:43-54`)

Cada número mostrado lleva su etiqueta: **`declarado`** (campos curados de `presets.toml`) ·
**`estimado`** (API pública de HuggingFace para IDs libres: RAM residente = parámetros × 4
bytes × 1,3, fp32 — docs/BACKLOG.md §2 / US-H9; si la API no responde, `sin dato` sin fallar) · **`medido`**
(pico de RAM muestreado por el portero `test-embed` al ejercitar el modelo — docs/BACKLOG.md §2 / US-H9).
Los badges `recomendado` / `viable` / `no recomendado` (docs/BACKLOG.md §2 / US-H9) son **ADVERTENCIA, no
bloqueo** (D8.1-D8.3). MiniLM `paraphrase-multilingual-MiniLM-L12-v2` (~470MB) se mantiene
recomendado y preseleccionado; `BAAI/bge-m3` (~2300MB) figura con GPU recomendada
(docs/BACKLOG.md §2 / US-H9); el ID libre de HuggingFace pasa por el gate `test-embed` con `HF_TOKEN`
opcional para modelos gated (ADR-007 D7.1 salida 3, `:48`; docs/BACKLOG.md §2 / US-H9).

### 4.3 Endpoint de API externa — documentación de conducta VIGENTE (referencia, no nuevo diseño)

**NO existe campo `endpoint` en `[embedding]`**: LiteLLM deriva proveedor y endpoint por defecto
del **prefijo de `model`** (p. ej. `openai/` → `https://api.openai.com/v1`) (docs/BACKLOG.md §2 / US-H9 y
`:281`). `api_key_env` es el **NOMBRE** de la variable de entorno y gana sobre `api_key`
literal. El loader del flow **BLOQUEA URLs dentro de `model`** (`://`, `http` o `@` con
provider `litellm` → se cae al modelo default con warning), porque un `model` con componente de
endpoint haría que LiteLLM embebiera el texto del usuario hacia ESA URL — **exfiltración por
config**. Este comportamiento **YA está implementado** y este ADR solo lo documenta (lag de
documentación, no diseño nuevo):
`obsidian-workspace/.tepochcalli/flow/tepochcalli_flow/config.py:357-369` (guarda) con el
comentario de rationale en `:360-362`. Un endpoint custom (Ollama/vLLM/proxy) se declara como
variable de entorno de LiteLLM en `opencode.json`, fuera del TOML y del wizard (docs/BACKLOG.md §2 / US-H9).

### 4.4 Confirmation

* Con sonda sin GPU, el menú muestra `cuda` deshabilitado con la razón visible; elegirla es
  imposible salvo fuerza explícita con advertencia `medido`.
* `install` con `cuda:0` elegido (GPU detectada) deja `device = "cuda:0"` en
  `[embedding].device` de `tepochcalli.toml`; una re-entrada `config embedder` posterior
  preseleciona ese valor y no lo pisa.
* Prueba del loader: `model = "https://evil.example/x"` con provider `litellm` → fallback al
  default con warning (guarda implementada en `config.py:357-369`; **sin test específico en la
  suite — TD-50**).
* **Estado de la evidencia: `declarado`** para (a)/(b)/(c) — el campo `device` en `Preset` y la
  preservación en re-entrada no existen en el código todavía (§1); la Phase 6.5 los materializa
  (T4) y entonces pasarán a `medido`. *Medible* hoy solo la guarda del loader.

## 5. Pros and Cons of the Options

### Option A — elección explícita + campo `device` + preservación (elegida)

* ✅ **Pros:** cumple H9 literalmente; determinismo intacto (el dispositivo es parte de la
  config del índice, no una sorpresa de runtime); D7.2 respetado (el catálogo sigue siendo
  dato); la re-entrada deja de ser destructiva con la elección manual.
* ⚠️ **Cons:** amplía el contrato `Preset`/`presets.toml` y el cuerpo de config que escriben
  `local_config()` y `picked_config_body()` — deriva en tareas de implementación Rust + tests
  (fuera de este ADR); `device` incorrecto elegido a mano pospone el fallo a la carga del
  modelo (mitigado: advertencia `medido`, docs/BACKLOG.md §2 / US-H9).
* ⚖️ **Neutral:** exige enmienda de [spec-embeddings](../../specs/spec-embeddings.md) (el propio H9 lo
  declara, docs/BACKLOG.md §2 / US-H9) — tarea documental hermana.

### Option B — autoselección en runtime

* ✅ **Pros:** cero pregunta al usuario; «simplemente funciona» en host con GPU.
* ⚠️ **Cons:** índice no-determinista (mismo vault, distinto espacio vectorial según hardware)
  — RECHAZADA en spec-embeddings.md:231 y no reabierta aquí; silenciosa ante el usuario.

### Option C — estatus quo (`cpu` fijo)

* ✅ **Pros:** cero trabajo; camino MiniLM-CPU actual sin cambios.
* ⚠️ **Cons:** no cumple H9; `BAAI/bge-m3`-GPU queda sin ruta; la re-entrada sigue pisoteando
  cualquier `device` escrito a mano en el TOML (violación del NFR de no sobrescribir al
  usuario, spec-embeddings §Trade-offs).

## 6. Consequences

* ✅ **Positives:** el contrato del wizard queda alineado con H9 sin reabrir D7/D8: los ADRs
  *Accepted* conservan su texto y este ADR añade las tres letras (a)-(c) como refinamiento
  acotado; la documentación del endpoint cierra un lag real (la guarda ya vive en
  `config.py:357-369` sin reflejo en spec).
* ⚠️ **Negatives / Risks:** se registran como **deuda de implementación** los tres drifts del
  código vigente (`Preset` sin campo, `embedder_config.rs:42` hardcodeado, `swap.rs:422`
  pisoteando); hasta que se materialicen, el wizard sigue escribiendo `cpu` — este ADR no lo
  cambia. Riesgo de lectura: confundir el flujo destino con el vigente; acotado por la fecha de
  aprobación (2026-11-19) y la nota de alcance, que separa lo aprobado de lo implementado.
* ⚖️ **Paradigm shifts / Dependencias:** la UX de botones deshabilitados con razón exige la
  **TUI full-screen** que reemplaza al `dialoguer` line-based actual (D23; docs/BACKLOG.md §4 / D-006,
  «p. ej. `ratatui`») — **fijada como `ratatui` + `crossterm` por aprobación del dueño el
  2026-11-19** (R1 / [SPEC.md](../../SPEC.md):97 cumplido); **su especificación de UX vive en
  [spec-installer-wizard](../../specs/spec-installer-wizard.md)** (enmienda hermana Accepted) y no
  se fija aquí.

## 7. Related Decisions

* [ADR-007](adr-007-seleccion-embedder-instalacion.md) — **refinado** (D7.1 menú "Embedding
  provider" gana la pregunta por `device`; D7.4 re-entrada preserva). No sustituido.
* [ADR-008](adr-008-transparencia-hardware-cambio-modelo.md) — **refinado** (D8.1-D8.3 aplican
  a la fila `device`: badge por GPU detectada, advertencia nunca bloqueo). No sustituido; su
  precedente de redacción «refina (no reemplaza)» (`:8`) es el que copia este ADR.
* [spec-embeddings](../../specs/spec-embeddings.md):231 — la autoselección rechazada queda reafirmada;
  enmienda exigida por docs/BACKLOG.md §2 / US-H9 para formalizar `[embedding].device` electivo.
* [ADR-014](adr-014-distribucion-uvx-pypi.md) — hermano del mismo lote (flujo destino
  2026-11-18); independiente en su decisión (canal vs dispositivo).

## 8. Compliance and Review

* **Success metrics:** tras la implementación autorizada, un usuario con GPU puede elegir
  `cuda:0` en `install`, verlo persistido en `tepochcalli.toml`, y recuperarlo preseleccionado
  en `config embedder`; un usuario sin GPU nunca ve `cuda` habilitado sin advertencia.
* **Next review date:** 2027-05-18
* **Revisit triggers:** backends de torch distintos de `cpu`/`cuda` relevantes para el perfil
  del investigador (ROCm/MPS/exp CUDA) → ampliar el menú con el mismo contrato; cambio de la
  fórmula de estimación en la API de HuggingFace → revalidar `params × 4 × 1.3`; TD abierta por
  los drifts de §1 cerrada → actualizar §4.4 de `declarado` a `medido`.

## References

* docs/BACKLOG.md §2 / US-H9 — H9 «🟣 Change Embedder» (fuente del requisito)
* docs/BACKLOG.md §4 / D-006 — dependencia TUI full-screen (`ratatui` p. ej.) sobre `dialoguer` (D23)
* [spec-embeddings](../../specs/spec-embeddings.md):231 — «Detección automática de GPU y selección de modelo en runtime: rechazado»
* [ADR-007](adr-007-seleccion-embedder-instalacion.md) D7.1/D7.2/D7.4 · [ADR-008](adr-008-transparencia-hardware-cambio-modelo.md) D8.1-D8.4
* Código vigente citado: `crates/tepochcalli/src/config/presets.rs:10-33` · `crates/tepochcalli/src/application/embedder_config.rs:34-44` · `crates/tepochcalli/src/application/swap.rs:164,422` · `obsidian-workspace/.tepochcalli/flow/tepochcalli_flow/config.py:105-121,357-369`

---
*Formato basado en [MADR v4.0](https://adr.github.io/madr/), igual que [adr-template.md](adr-template.md).*
