# ADR-009: El conversor escribe a disco y devuelve solo un resumen (sin cuerpo en el wire)

* **Status:** Proposed
* **Date:** 2026-11-02
* **Decision Makers:** Dueño del repo, Arquitecto
* **Consulted:** `docs/diagnosis/fix01-conversor-satura-contexto-llm.md` (defecto reproducido), `markitdown==0.1.9` instalado y `obsidian-workspace/.tepochcalli/mcp/tepochcalli_mcp/convert.py` (API real: `MarkItDown().convert(source).markdown`), `tasks/plan.md` §2.1/§2.2 (D28-D67) y §5.5-§5.9
* **Informed:** Autor de la skill `tepochcalli-mcp` (H4), mantenedores de `spec-markitdown.md` y `spec-mcp-server.md`, usuarios del vault
* **Traceability:** `tasks/plan.md` D28 · D31 · D36 · D37 · D38 · D39 · D49 · D64 · D66 · D35; `docs/UH.md` H1-H2 (anexo 2026-10-30); diagnosis `fix01`; `specs/spec-markitdown.md` (contrato que este ADR amplía); `docs/SECURITY.md`

## 1. Context and Problem Statement

La tool `convert_to_markdown` del MCP standalone `markitdown` devuelve el markdown **completo**
como `content[0].text`: con un documento grande el artefacto entero entra en la ventana de
contexto, la sesión degenera y se viola el criterio 4 de `docs/UH.md` (≤2000 tokens por consulta).
El defecto es de presupuesto, no de excepción: no hay error, solo un agente que intenta
re-escribir por partes un documento que ya viajó por el wire dos veces
(`docs/diagnosis/fix01-conversor-satura-contexto-llm.md` §Root Cause).

El mismo repo ya tiene la disciplina correcta en `add_source` (conversión en proceso, escribe a
disco, `{written_to, indexed}` en el wire) y en `search` (techo 1600 tokens, `truncated`). Lo que
falta es **un conversor de propósito general con ese mismo contrato**, separado del camino de
indexación (D49): el motor indexa los documentos **originales** con la misma librería, y el
conversor produce el artefacto `.md` que el usuario pide.

## 2. Decision Drivers

* El wire no transporta artefactos: el coste en tokens de una tool call es constante respecto al
  tamaño del documento (criterio 4, `spec-mcp-server` §presupuesto).
* Un solo MCP y un solo proceso: el venv ya pinea `markitdown` y `convert.py` ya la usa en
  proceso; un server extra es un proceso más que arrancar, versionar y depurar.
* Frontera de confianza = el vault (D16/D47): ni lectura ni **escritura** fuera de él.
* Taxonomía de errores cerrada (D39): el agente debe poder decidir con tres códigos, no con una
  lista que crece por cada caso de borde.
* Nunca sobrescribir material del usuario: reintentar debe ser seguro sin parámetro `overwrite`.
* Una responsabilidad por tool (D35): convertir ≠ indexar; el motor es dueño del Δ.
* Cero dependencias nuevas (R1/ADR-011): la librería ya está instalada y ya se usa.

## 3. Considered Options

* **Option A:** tres tools (`convert_document`, `convert_base64`, `list_formats`) dentro del
  server `tepochcalli-rag` existente, markitdown **en proceso**, y un resumen de 5 claves como
  única respuesta posible.
* **Option B:** mantener el MCP `markitdown` standalone como camino del agente (el defecto
  actual; D29 lo retira del payload).
* **Option C:** devolver el markdown completo y confiar en que el agente lo trunque o lo escriba
  (el defecto diagnosticado en `fix01`).
* **Option D:** un conversor que además indexa el resultado (fusiona conversión y motor).

## 4. Decision Outcome

**Chosen option: Option A**, porque es la única que satisface a la vez el presupuesto de tokens
(el cuerpo nunca cruza el wire), el mínimo de procesos (markitdown en proceso en el server que ya
existe) y la frontera de confianza única (entrada y salida validadas en `paths.py`). B reproduce
el defecto por construcción, C lo deja a la disciplina del modelo (no verificable) y D rompe la
separación conversión/indexación que D49 fija.

### D28 — Las 3 tools viven en `tepochcalli-rag`, con markitdown en proceso

`convert_document(path, output_path?, format?)`, `convert_base64(data, output_path?, format?,
filename?)` y `list_formats()` se registran en el paquete `tepochcalli_mcp` del server ya
existente, junto a `search`/`index_refresh`/`add_source`/`rag_status`. La conversión corre **en
proceso** con `MarkItDown().convert(...).markdown` — la misma llamada que `convert.py` ya hace
hoy para `add_source`. Razón: un proceso más es un proceso más que arrancar, versionar y depurar,
y el venv ya tiene la librería; además el standalone es la fuente del defecto
(`markitdown_mcp/__main__.py` devuelve el cuerpo, plan OM-1). D29 retira su entrada del payload:
el conversor tiene un solo camino.

### D31 — Frontera B′: entrada **y** salida dentro del vault

Todo `path` de entrada y todo `output_path` deben resolver dentro del vault; `..`, ruta absoluta
externa o symlink que escape ⇒ `VALIDATION_ERROR`. Esto **extiende** D16 —que solo cubría el
`file:` de entrada vía `paths.resolve_file_uri`— al destino de escritura, con
`paths.ensure_within` como defensa en profundidad. Razón: escribir fuera del vault es
*arbitrary file write* (plan OM-2); la frontera del sistema es el vault (D47), no la carpeta
pedida. La comprobación va **antes** de convertir: no se gasta una conversión de 100 páginas para
descubrir al escribir que el destino era ilegal.

### D36 — El resumen tiene 5 claves en orden fijo, y el cuerpo nunca viaja

La respuesta de éxito es exactamente `written_to`, `source_uri`, `bytes`, `chars`, `preview`
(≤500 caracteres) y, solo cuando aplica, `truncated`. No hay clave `ok`: el resumen **es** la
confirmación, y el fracaso es un `CallToolResult` de error con `{error:{code,message,details?}}`
(convención ya congelada en Phase 2: nunca `ToolError`). Objetivo ~200 tokens, techo 1600 con el
mismo estimador y la misma disciplina que `budget.py`. El resumen se construye **desde el fichero
escrito** (tamaño real, `preview` leído del disco), no desde el markdown en memoria: así el test
nuclear —«el cuerpo no aparece en `content[0].text`»— prueba también que el disco es la fuente de
verdad (mitigación de OM-1).

El cuerpo escrito es el markdown de markitdown, **sin** el frontmatter de trazabilidad que añade
`add_source`: aquel artefacto es una fuente indexada y este es un documento del usuario. Además,
un `converted_at` con timestamp haría que dos conversiones idénticas difirieran siempre y D66
(idempotencia) sería inalcanzable.

### D37 / D38 — Defaults del destino y de `source_uri`

`output_path` omitido ⇒ el destino se deriva del nombre del documento dentro del vault
(`00-Resources/<slug>.md`, reutilizando `paths.slugify_uri`). El destino canónico **no** se
renombra solo ante colisión: `paths.available_name` se reutiliza para *proponer* el nombre
alternativo que acompaña al error de D66, porque auto-renombrar (`x-1.md`) rompería la
idempotencia y llenaría `00-Resources/` de duplicados. Razón: H3 fija `00-Resources/` como
convenio default y el agente no debe inventar rutas.

`source_uri` refleja la entrada **tal como llegó**: en `convert_document`, la ruta recibida; en
`convert_base64`, el `filename` si vino. `convert_base64` exige `format` **o** `filename` —sin
pista de tipo markitdown no puede elegir extractor, y adivinarlo convertiría bytes opacos en
markdown plausible pero falso—; sin ninguno de los dos es `VALIDATION_ERROR`. En
`convert_document`, `format` es solo una pista opcional (`StreamInfo(extension=…)`) para nombres
sin extensión, no un selector de convertidor.

### D39 — La taxonomía de errores no crece

Tres códigos, una respuesta distinta cada uno:

| Código | Cuándo | Qué hace el agente |
| --- | --- | --- |
| `VALIDATION_ERROR` | ruta fuera del vault o con `..`, formato no soportado, base64 sin pista de tipo, ruta inexistente, tipo equivocado, destino ocupado con contenido distinto | corrige la llamada y reintenta (los `details.suggestions` le bastan) |
| `SOURCE_UNREACHABLE` | el documento existe y es del tipo pedido pero no se puede convertir: escaneado sin capa de texto, corrupto, cifrado | informa al usuario y ofrece OCR manual o guardar el `.md` a mano |
| `INTERNAL` | bug nuestro | reporta; el detalle vive en el log, nunca en el payload |

Razón: el agente necesita tres reacciones, no veinte; un código por caso de borde obligaría a
re-entrenar prompts y a ampliar `errors.py` en cada iteración. `SYMLINK_ESCAPE` sigue siendo un
skip tipado **del motor** (D47): en el conversor un symlink que escapa es `VALIDATION_ERROR`.

### D64 — Existencia y tipo se deciden en el borde MCP, antes de tocar el disco

`path` inexistente o que es un directorio ⇒ `VALIDATION_ERROR` con `details.suggestions`
(propuestas por similitud, sin distinguir mayúsculas), decidido en `paths.py` —módulo puro y
testeable— **antes** de invocar markitdown. Motivo verificado: `localfs.walk_dir` del `cocoindex`
pineado lanza `ValueError("Path is not a directory: …")` y el `internal_guard` lo convertiría en
`INTERNAL`, es decir, «fallo interno» por haber escrito mal una ruta. El mismo chequeo cubre el
padre del `output_path` (debe existir como directorio dentro del vault) por la misma razón: el
error tiene que ser corregible en un reintento, no un callejón.

### D66 — Destino existente: idempotencia, nunca sobrescritura

Si el destino existe con **contenido idéntico** (mismos bytes) ⇒ éxito: se devuelve el resumen con
`written_to` y reintentar la misma conversión no falla. Si el contenido **difiere** ⇒
`VALIDATION_ERROR` con «el destino existe, elige otro `output_path`» y el nombre alternativo
propuesto. Nunca se sobrescribe material del usuario. Razón: es la única semántica que hace seguro
reintentar sin añadir un parámetro `overwrite` (YAGNI) y sin que una segunda conversión destruya
una edición manual del `.md`. El `ok:true` de D66 se expresa como ausencia de error: D36 no tiene
clave `ok`.

### D49 — El conversor **no** es el camino de indexación

El motor indexa los documentos **originales** con markitdown directamente (`parsers.extract_text`,
D48); el conversor produce el `.md` que el usuario pide. Misma librería, propósitos distintos.
Razón: convertir-y-luego-indexar crearía un segundo artefacto que hay que mantener sincronizado
con el original y movería la cita del documento real (D41) a un derivado; además el motor es el
dueño del Δ y de sus presupuestos (D35, D51), y una tool que indexa dejaría de ser una
responsabilidad.

### 4.1 Confirmation

* Test nuclear (contract test): documento sintético de ≥100 000 caracteres con una marca única
  (`TEPOCHCALLI_BODY_SENTINEL`) ⇒ el markdown escrito en `output_path` **contiene** la marca y
  `content[0].text` **no** la contiene, y su longitud es ≤ ~4× el techo (1600 tokens estimados).
* Shape del wire: el JSON de éxito tiene exactamente las claves `written_to`, `source_uri`,
  `bytes`, `chars`, `preview` (y `truncated` cuando el preview se recorta), en ese orden, y
  `len(preview) <= 500`; ningún test puede pasar con una sexta clave.
* `bytes`/`chars` coinciden con `stat()` y `len()` del fichero escrito, no con el buffer en
  memoria (prueba de que el resumen se construyó desde el disco).
* Frontera B′: `output_path` con `..`, absoluto externo o symlink que escapa ⇒
  `VALIDATION_ERROR`, y el fichero externo **no** se crea (aserción sobre el filesystem, no solo
  sobre el código de error).
* D64: `path` inexistente y `path` que es un directorio ⇒ `VALIDATION_ERROR` con
  `details.suggestions`, sin invocar markitdown (espía sobre la costura de conversión).
* D66: dos llamadas idénticas ⇒ la segunda devuelve el mismo `written_to` y no cambia el mtime del
  fichero; contenido distinto sobre el mismo destino ⇒ `VALIDATION_ERROR` y el fichero original
  intacto byte a byte.
* D39: escaneado sin texto ⇒ `SOURCE_UNREACHABLE`; formato no soportado ⇒ `VALIDATION_ERROR` con
  la lista de `list_formats`; ningún caso nuevo introduce un código fuera de los tres.
* D28: `opencode.json` del payload no registra ningún server `markitdown` (test `MANAGED_KEYS`), y
  el test de arquitectura sigue prohibiendo que `tools/*` importen `markitdown`.

## 5. Pros and Cons of the Options

### Option A — 3 tools en `tepochcalli-rag` con resumen de 5 claves (elegida)

* ✅ **Pros:** coste en tokens constante respecto al tamaño del documento; un solo proceso y un
  solo venv; reutiliza `paths`, `errors`, `budget` y los contract tests existentes; la frontera
  B′ queda en un módulo puro; cero dependencias nuevas.
* ⚠️ **Cons:** tres tools y un contrato más que mantener; el agente pierde el acceso directo al
  contenido y necesita un `read` para materializarlo; `list_formats` es catálogo curado que puede
  desincronizarse de markitdown (OM-4).
* ⚖️ **Neutral:** `spec-markitdown.md` deja de describir la conversión como capacidad exclusiva de
  `add_source`; se enmienda en T1, no se re-edita un ADR Accepted.

### Option B — MCP `markitdown` standalone

* ✅ **Pros:** cero código nuevo; el paquete upstream ya existe.
* ⚠️ **Cons:** es exactamente el defecto (`fix01`): devuelve el cuerpo por el wire y escala
  O(tamaño del documento) en tokens; segundo proceso que arrancar y versionar; superficie sin
  presupuesto ni frontera de salida (el agente escribe el `.md` a mano, con riesgo de truncado o
  alucinación); su entrada del payload ya contradice `spec-markitdown.md` §Summary (párrafo del
  standalone retirado).
* ⚖️ **Neutral:** D29 lo retira del payload; el paquete queda solo como librería en el venv.

### Option C — Devolver el markdown completo y que el agente lo trunque

* ✅ **Pros:** una tool, contrato trivial, nada que validar en el servidor.
* ⚠️ **Cons:** el presupuesto depende del criterio del modelo en cada sesión —no es verificable
  ni auditable—; el daño es silencioso (no hay error, solo degradación); el contenido cruza el
  wire dos veces; viola el criterio 4 y la disciplina de `search`/`add_source` ya congelada.
* ⚖️ **Neutral:** es el comportamiento actual del standalone; se documenta aquí para que no se
  re-litigue como «arreglo rápido».

### Option D — Conversor que además indexa

* ✅ **Pros:** una sola llamada resuelve «convierte y úsalo»; menos pasos para el usuario.
* ⚠️ **Cons:** fusiona dos responsabilidades (D35) y contradice D49: el motor indexaría un
  derivado en vez del original, con citas sobre un artefacto intermedio; duplica el control del Δ
  y de los presupuestos del motor; `convert_base64` indexaría material no confiado sin pasar por
  `add_source`.
* ⚖️ **Neutral:** quien quiera las dos cosas encadena `convert_document` + `index_refresh`
  (o usa `add_source`, que ya hace ambas).

## 6. Consequences

* ✅ **Positives:** convertir un documento de cualquier tamaño cuesta ~200 tokens; la escritura
  del `.md` deja de depender del modelo (se acaba el truncado/alucinación silenciosa); una sola
  frontera de validación para lectura y escritura; los errores son corregibles por el agente sin
  preguntar al usuario.
* ⚠️ **Negatives / Risks:** **el agente ya no puede leer el markdown desde la respuesta de la
  tool**: para usar el contenido necesita un `read` del fichero (o `search` si está indexado), es
  decir, un paso más y un coste que puede volver a saturar el contexto si el fichero es enorme —
  la skill H4 debe decir «cita la ruta, no reproduzcas el cuerpo». Sin OCR: un escaneado sin capa
  de texto es `SOURCE_UNREACHABLE` con guía, no una conversión vacía. `list_formats` es dato
  curado sin API upstream que lo respalde (OM-4). El resumen obliga a que `preview` y `truncated`
  se calculen sobre el fichero escrito: un bug ahí miente sobre el resultado.
* ⚖️ **Neutral:** `add_source` sigue siendo el camino de ingesta (convierte, escribe con
  frontmatter e indexa); el conversor es el camino del artefacto. Dos tools, dos intenciones, una
  sola librería.

## 7. Related Decisions

* **ADR-005** — la frontera MCP no cambia: el harness sigue viendo solo JSON-RPC por stdio y este
  ADR **extiende** el conjunto de tools del mismo server; no hay server nuevo ni puerto nuevo.
* **ADR-002** — sin daemon ni puerto: la conversión es una llamada en proceso dentro del server
  que ya se lanza por stdio.
* **ADR-004** — `markitdown==0.1.9` y sus extras viven en el venv del vault; el conversor no
  instala nada en runtime.
* **ADR-009 ↔ ADR-010 ↔ ADR-011** — los tres son el mismo contrato de Phase 3.5 visto por capas:
  este ADR fija el wire del conversor; ADR-010 fija el índice multi-raíz y la cita
  vault-relativa (que el conversor no toca: no indexa, D49); ADR-011 fija la política de
  dependencias que hace que markitdown sea la única librería documento→markdown (D48/D52/D55).
  Comparten la frontera B′ (D31) y la taxonomía cerrada (D39/D64).
* **`spec-markitdown.md`** — su contrato de conversión (hoy exclusivo de `add_source`) se enmienda
  en T1 para incluir las tres tools y el resumen; su §Summary (standalone retirado) queda confirmado
  por D29. Este ADR no edita la spec.

## 8. Compliance and Review

* **Success metrics:** 0 respuestas de conversión con cuerpo en `content[0].text` (test nuclear
  permanente); 100% de escrituras dentro del vault; 0 sobrescrituras de ficheros existentes con
  contenido distinto; coste mediano por conversión ≤ ~250 tokens con independencia del tamaño del
  documento; `SOURCE_UNREACHABLE` solo por causas reales de conversión (no por rutas mal escritas).
* **Next review date:** 2027-05-02
* **Revisit triggers:** (1) markitdown publica una API de formatos soportados ⇒ `list_formats`
  deja de ser catálogo curado; (2) aparece la necesidad real de conversión en lote (N documentos
  por llamada) o de streaming ⇒ nuevo contrato, nuevo ADR; (3) se necesita un segundo conversor
  en proceso (p. ej. anydoc como librería) ⇒ ADR de dependencias (ADR-011), no parche aquí;
  (4) el motor necesita los `.md` convertidos para citar ⇒ reabre D49; (5) el harness ofrece un
  canal de artefactos fuera del contexto del modelo ⇒ revisar si el resumen sigue siendo la única
  forma correcta.

---
*Template based on [MADR v4.0](https://adr.github.io/madr/) and [Nygard's ADR format](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).*
