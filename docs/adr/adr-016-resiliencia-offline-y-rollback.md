# ADR-016: Resiliencia offline y rollback cancelable en la instalación del wizard

* **Status:** Accepted 2026-11-20
* **Date:** 2026-11-20
* **Age:** 2026-11-20 (decisión vigente desde la orden del dueño)
* **Decision Makers:** Fisherk2 (dueño del repo; fuente directa: «orden de Fisherk2, 2026-11-20»); Arquitecto (redacción)
* **Consulted:** [ADR-007](adr-007-seleccion-embedder-instalacion.md) (D7.1 menú "Embedding provider", D7.3 `--offline`, D7.4 re-entrada), [ADR-008](adr-008-transparencia-hardware-cambio-modelo.md) (D8.4 swap atómico con rollback), [ADR-014](adr-014-distribucion-uvx-pypi.md) (canal `uvx`, versión), [ADR-015](adr-015-dispositivo-inferencia-wizard.md) (`device` electivo); [spec-installer-wizard](../../specs/spec-installer-wizard.md) §Fases / §UX de fallo / §Casos de uso destino H6-H8; [spec-embeddings](../../specs/spec-embeddings.md) §Cache de modelos / §Matriz de edge cases / §Enmienda 2026-11-18
* **Informed:** autor del wizard (Rust, `crates/tepochcalli/`), mantenedores de `specs/spec-installer-wizard.md` y `specs/spec-embeddings.md`, usuarios del vault
* **Traceability:** docs/BACKLOG.md §2 / US-H6 (🔵 Install), US-H7 (🟢 Update), US-H9 (🟣 Change Embedder) + decisión §4 D-009 (registrada en el BACKLOG por orden de Fisherk2, 2026-11-20); [spec-installer-wizard](../../specs/spec-installer-wizard.md) §Enmienda 2026-11-20; [spec-embeddings](../../specs/spec-embeddings.md) §Enmienda 2026-11-20

> **Nota de alcance:** este ADR **REFINA** (no reemplaza, no borra, no re-edita) ADR-007,
> ADR-008, ADR-014 y ADR-015, y el comportamiento de **backup de H7/H8** descrito en
> `specs/spec-installer-wizard.md` §Casos de uso destino. Los cuatro ADRs citados quedan
> **byte-idénticos**; el precedente de redacción es el propio ADR-008 Traceability («refina,
> no reemplaza»), seguido por ADR-015. Añade una garantía de integridad acotada a la
> **instalación/cambio de embedder**, sin tocar el modo degradado de runtime ni el canal.
> Este ADR no modifica código: la evidencia es `declarado` hasta su implementación.

## 1. Context

Los casos de uso destino H6 (🔵 Install), H7 (🟢 Update) y H9 (🟣 Change Embedder) requieren red:
descarga de wheels de `uv` (`cocoindex`, `markitdown`), del payload y, para los modelos locales,
del snapshot de HuggingFace en `.tepochcalli/models/` (`paraphrase-multilingual-MiniLM-L12-v2`
por defecto, ~470MB; `BAAI/bge-m3`, ~2300MB). El contrato vigente en
`specs/spec-installer-wizard.md` §Fases (fila 6) y §Semántica de rollback del provider (D7.1)
establece que un fallo de descarga/validación **no aborta**: compensa `models/` y cae a la salida
5 ("Configurar después"), dejando el vault completo en estado `degraded`. Esa regla es correcta
para un modelo inválido (gate `test-embed` → `E_MODEL_INVALID`), pero resulta insuficiente para
dos situaciones que el dueño ordena cubrir el 2026-11-20:

1. **Sin red al instalar o cambiar el embedder:** el usuario espera que la operación se cancele
   y que su workspace quede **exactamente como estaba**, no un vault a medias ni un degraded
   silencioso. El preflight de red debe ocurrir **antes de escribir cualquier fichero** (antes
   incluso de la fase 3 de extracción del payload y del backup de H7).
2. **Descarga en progreso:** la barra de progreso de H6/H9 no ofrece hoy salida; interrumpir el
   proceso deja partials en `.tepochcalli/models/` y exige limpieza manual.

Además, H7/H8 ya definen **backup obligatorio + journal** antes de pisar/retirar ficheros
gestionados (`.opencode/`, `.tepochcalli/`, `.gitignore`, `opencode.json`, `AGENTS.md`). Ese
mecanismo es la base natural del rollback: no hace falta inventar otro sistema de restauración.

Finalmente existe un riesgo real de contradicción documental: US-H9 dice que «si la API no
responde, se muestra `sin dato` sin fallar la instalación» (refs de
`specs/spec-embeddings.md` §Extracción de requisitos vía API pública de HuggingFace y
§Enmienda 2026-11-18 / ADR-015 §4.2). Esa frase regula **solo la estimación previa de
requisitos** (RAM/disco/GPU), no la descarga real del modelo. La sección §2.4 fija la frontera.

## 2. Decision

Se adoptan los cuatro requisitos del enunciado canónico, tal cual fueron ordenados:

* **R-offline-1 (preflight):** antes de escribir cualquier fichero, el wizard comprueba la
  conectividad mínima que la operación necesita. Si no hay red, cancela la operación con
  rollback y deja el workspace del usuario exactamente como estaba; muestra error tipado con
  razón y acción correctiva. No hay modo degradado ni instalación parcial en tiempo de
  instalación.
* **R-offline-2 (cancelación en progreso):** durante la descarga del modelo (H6/H9; y H7 si la
  operación descarga algo), el usuario puede cancelar en cualquier momento desde el TUI y con
  Ctrl+C. La cancelación detiene la descarga, elimina los artefactos parciales y compensa todo
  cambio ya aplicado (rollback), cancelando la instalación completa. No queda modelo a medias en
  `.tepochcalli/models/`.
* **R-offline-3 (integridad):** el rollback restaura el estado previo de los ficheros gestionados
  usando el backup + journal ya existentes de H7/H8. Notas, PDFs, `.obsidian/` y configuración
  propia del usuario nunca se tocan. Tras el rollback se verifica que no quedan restos.
* **R-offline-4 (distinción crítica — evitar contradicción):** el modo degradado existente
  (ADR-007 / `rag_status`: embedder no disponible en **runtime**) NO se confunde con esto: en
  instalación/cambio de embedder, **sin red = cancelación, no degradación**. Además, el texto
  vigente de US-H9 «Si la API no responde, se muestra `sin dato` sin fallar la instalación»
  aplica **solo a la estimación previa de requisitos**, no a la descarga real: el ADR y las specs
  deben aclarar explícitamente esa frontera para que no parezca una contradicción.

### 2.1 Preflight antes de tocar disco (R-offline-1)

El chequeo de red se ejecuta como **fase 0**, anterior a la fase 1 de `spec-installer-wizard.md`,
y comprueba solo la conectividad que la operación necesita: reachability del registro de paquetes
y de HuggingFace (o del proveedor LiteLLM si la salida elegida es API externa). `--offline` (D7.3)
conserva su semántica: con caché válida no hay preflight de red; sin ella falla con
`E_OFFLINE_NO_CACHE` como hoy. Sin red y sin caché suficiente: cancelación con error tipado de la
banda 20-29 (red) de §UX de fallo, con razón visible y acción correctiva (reconectar o usar
`--offline` con caché). **No se crea `.tepochcalli/`, no se hace backup y no se escribe config.**

### 2.2 Cancelación en progreso (R-offline-2)

La TUI full-screen (`ratatui` + `crossterm`, ADR-014/015) ofrece un botón **Cancel** activo
durante la descarga y enlaza `Ctrl+C` al mismo manejador de cancelación cooperativa: se detiene
el stream, se descarta el fichero en escritura y se reproducen las compensaciones de las fases
ya ejecutadas en orden inverso (journal). El resultado es cancelación de la **instalación
completa**, con el mismo código de salida tipado que una cancelación en H2 (`E_CANCELLED`,
banda de red/cancelación), no un vault instalado a medias.

### 2.3 Integridad y verificación posterior (R-offline-3)

El rollback reutiliza el **backup + journal de H7/H8** sin ampliar su alcance: se restauran solo
los ficheros gestionados (`.opencode/`, `.tepochcalli/`, `.gitignore`, `opencode.json`,
`AGENTS.md`) y se borran los artefactos creados en la corrida. Quedan intactos notas, PDFs,
`.obsidian/` y cualquier configuración propia del usuario. Antes de reportar éxito del rollback
se verifica que no quedan restos: ni `.tepochcalli/models/<slug>@*` parcial, ni marker
`.install-intent`/`.install-state`, ni entrada `tepochcalli-rag` nueva en `opencode.json`. Si la
verificación falla, se informa con la ruta exacta pendiente en lugar de dar el rollback por bueno.

### 2.4 Frontera con el modo degradado y con `sin dato` (R-offline-4)

* El estado `degraded` de `rag_status()` (ADR-007, §Matriz de edge cases de
  `spec-embeddings.md`) describe un **embedder no disponible en runtime** (salida 5,
  `--skip-model`, `provider = "none"` → `E_NO_EMBEDDER`). **No cambia**: sigue siendo una
  respuesta honesta del motor ante una config sin embedder. La cancelación por ausencia de red
  **en tiempo de instalación** es otra cosa y no lo produce.
* La regla «API HF no responde → `sin dato` sin fallar» es **solo de la estimación previa** de
  disco/RAM/GPU que se muestra en el menú (D8.1). No autoriza a continuar cuando falla la
  **descarga real** del snapshot: ahí aplica R-offline-1/R-offline-2. Un `sin dato` en la fila no
  es una instalación degradada ni un permiso para instalar parcialmente.
* La salida 5 elegida **explícitamente** por el usuario y `--skip-model` siguen vigentes: son una
  decisión deliberada, no un fallback ante fallo de red. Lo que se refina es el fallback
  automático por fallo de descarga descrito en §Fases fila 6 y §Semántica de rollback del
  provider: **cuando la causa es ausencia de red en H6/H7/H9, se sustituye por cancelación con
  rollback**. El fallback por modelo inválido (`E_MODEL_INVALID`, gate `test-embed`) se mantiene.

## 3. Alternatives

* **Option A — preflight + cancelación cooperativa + rollback por journal (elegida).** Cumple los
  cuatro requisitos y reutiliza el backup de H7/H8. Refina ADR-007/008/014/015 sin re-editarlos.
* **Option B — mantener el fallback a salida 5 ("degraded") ante ausencia de red.** Rechazada:
  contradice R-offline-1 y deja un vault instalado sin embedder cuando el usuario pidió uno;
  además la cancelación en progreso seguiría sin resolver.
* **Option C — reintento automático hasta que vuelva la red.** Rechazada: bloquea la TUI sin
  salida visible, no ofrece cancelación al usuario y alarga una operación que ya se sabe inviable.
* **Option D — no hacer nada (estatus quo).** Rechazada: deja partials en `.tepochcalli/models/`
  y depende de limpieza manual, con riesgo de sobrescribir ficheros del usuario.

## 4. Trade-offs

* ✅ **Pros:** el workspace del usuario queda byte-a-byte igual ante sin-red o cancelación;
  error tipado con acción correctiva en vez de un degraded silencioso; se reutiliza el backup
  existente (cero mecanismo nuevo de persistencia); la frontera `sin dato` vs descarga real
  elimina la contradicción documental.
* ⚠️ **Cons / Risks:** un host con red intermitente ya no se "salva" instalando degraded — el
  usuario debe reintentar o elegir salida 5 explícitamente; la cancelación cooperativa exige que
  el gate `test-embed`/descarga (`python -m tepochcalli_flow embed-check`, spec-installer-wizard
  §Materialización del modelo) acepte señal de cancelación y limpie su directorio destino; el
  la verificación "sin restos" añade una pasada de comprobación tras la compensación.
* ⚖️ **Neutral:** no cambia canal (`uvx`, ADR-014), ni `device` electivo (ADR-015), ni el
  determinismo del índice (ADR-008), ni los códigos `E_*` del MCP `tepochcalli-rag`.

## 5. Consequences

* ✅ **Positives:** H6/H7/H9 ganan una garantía de integridad verificable; H7/H8 conservan su
  backup y lo comparten con el rollback sin ampliar su alcance; los ADRs *Accepted* permanecen
  intactos y la trazabilidad apunta a US-H6/H7/H9 + D-009.
* ⚠️ **Negatives / Risks:** hasta la implementación, el comportamiento real sigue siendo el de
  las secciones Accepted (fallback a salida 5) — la evidencia de este ADR es `declarado`, no
  `medido`; el riesgo de regresión está en confundir el degraded de runtime con la cancelación
  de instalación, acotado por §2.4 y por las dos enmiendas de spec.
* ⚖️ **Paradigm shifts / Dependencias:** ningún cambio de paradigma; dependencia documental de
  `specs/spec-installer-wizard.md` y `specs/spec-embeddings.md` (enmiendas 2026-11-20, hermanas
  de este ADR) y del registro de D-009 en `docs/BACKLOG.md` §4 (2026-11-20).

## 6. Implementation/Verification

**Evidencia: `declarado`** (orden del dueño 2026-11-20); pasa a `medido` cuando la implementación
autorizada ejecute los tests siguientes (detalle en cada spec, §Enmienda 2026-11-20):

* **Sin red → rollback:** fixture sin conectividad antes de la fase 3; assert de workspace
  byte-a-byte idéntico, cero `.tepochcalli/` nuevo, error tipado de red con razón y acción.
* **Cancelación a mitad de descarga:** interrumpir vía botón Cancel y vía `Ctrl+C`; assert de
  streaming detenido, cero partial en `.tepochcalli/models/`, compensaciones aplicadas en orden
  inverso y marker de instalación ausente.
* **Integridad de ficheros del usuario:** snapshot de notas, PDFs, `.obsidian/` y config propia
  antes/después del rollback; assert de byte-idénticos y de verificación "sin restos" ejecutada.
* **No regresión del degraded:** `rag_status()` con `provider = "none"` sigue reportando
  `degraded` + `fix_hint`; `search` → `E_NO_EMBEDDER`; `sin dato` sigue siendo solo estimación.

La spec de wizard fija fases/compensación, UX de fallo y testing; la spec de embeddings fija el
flujo de descarga del modelo local. Ninguna de las dos re-escribe su enmienda 2026-11-18.

## 7. References

* docs/BACKLOG.md §2 / US-H6, US-H7, US-H9 + §4 / D-009 (decisión registrada el 2026-11-20)
* [ADR-007](adr-007-seleccion-embedder-instalacion.md) D7.1/D7.3/D7.4 · [ADR-008](adr-008-transparencia-hardware-cambio-modelo.md) D8.4 · [ADR-014](adr-014-distribucion-uvx-pypi.md) · [ADR-015](adr-015-dispositivo-inferencia-wizard.md) §4.2 — **refinados, no reemplazados**
* [spec-installer-wizard](../../specs/spec-installer-wizard.md) §Enmienda 2026-11-20 — resiliencia offline y rollback cancelable (H6/H7/H9)
* [spec-embeddings](../../specs/spec-embeddings.md) §Enmienda 2026-11-20 — descarga de embedder cancelable y sin red (ADR-016, H9)
* Código citado (sin cambios en este ADR): `crates/tepochcalli/src/` (fases, backup/journal, TUI `ratatui`+`crossterm`) y `obsidian-workspace/.tepochcalli/flow/` (`embed-check`, `rag_status` del MCP `tepochcalli-rag`)

---
*Formato basado en [MADR v4.0](https://adr.github.io/madr/), igual que [adr-template.md](adr-template.md).*
