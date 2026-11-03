# ADR-010: Indexar múltiples raíces del vault y citar rutas relativas al vault

* **Status:** Accepted (enmendado 2026-11-03)
* **Date:** 2026-11-02
* **Decision Makers:** Dueño del repo (Product Owner), Arquitecto
* **Consulted:** Fuente instalada de `cocoindex==1.0.25` (conector `localfs`), `docs/TRD.md` §presupuestos
* **Informed:** Autor de T2/T3/T8, autores de agentes/comandos del vault
* **Traceability:** docs/UH.md (criterios 2, 5, 6, 7), specs/spec-rag-engine.md, specs/spec-mcp-server.md, tasks/plan.md D32-D67

## 1. Context and Problem Statement

El motor indexa hoy una sola raíz fija —`00-Resources/`— y solo cuatro extensiones
(`.md/.markdown/.txt/.pdf`); `citation.normalize_source_path` **prefija** `00-Resources/` a toda
cita. El dueño decidió que el RAG indexe **cualquier** directorio del vault, recursivamente, con
las raíces elegidas **en la llamada**, y que indexe los documentos **en su forma original** sin
convertirlos antes a Markdown.

El cambio toca dos contratos congelados a la vez: la firma de `index_refresh` y la semántica de
`source_path`. ¿Cómo se indexan N raíces arbitrarias sin introducir estado oculto y sin que dos
raíces distintas produzcan citas ambiguas?

## 2. Decision Drivers

* **Sin estado (D32/D42):** la raíz es un argumento, no configuración; ni `tepochcalli.toml` ni el wizard cambian.
* **Cita inequívoca con N raíces (D41):** el `source_path` debe localizar el fichero sin ambigüedad posible.
* **Documento original (D43/D49):** el RAG lee `.docx/.pptx/.xlsx/.xls/.pdf` directamente; el conversor sigue siendo el camino del artefacto `.md`.
* **Contabilidad honesta:** `scanned == indexed + skipped` sigue siendo la identidad del reporte.
* **Frontera de confianza B′ (D16/D31/D47):** lo que entra al índice no puede salir del vault.
* **Δ<30 s defendible (D51):** se promete solo lo medible; los binarios se miden aparte.
* **Cero reinvención (R1):** nada que el conector `localfs` ya resuelva se reimplementa.
* **Wizard intacto:** cambiar de carpeta no exige reinstalar.

## 3. Considered Options

* **A — Raíces por llamada, sin estado, `source_path` relativo al vault.** `index_refresh(directories=[...])`; cada llamada valida y camina sus raíces; la cita se normaliza contra la raíz del vault.
* **B — Config persistente.** `index.roots` en `tepochcalli.toml`, escrita por el wizard; el MCP lee la lista al arrancar.
* **C — `source_path` relativo a la raíz.** Se mantiene la forma actual y cada raíz aporta su propio prefijo lógico.
* **D — Un índice por raíz.** Una tabla LanceDB (`chunks_<slug>`) por raíz; búsqueda federada entre tablas.

## 4. Decision Outcome

**Chosen option: A**, porque es la única que satisface a la vez «sin estado» y «cita inequívoca»:
las raíces viajan en la llamada (nada que reconfigurar) y la cita se ancla al vault, que es el
único marco común a todas las raíces.

### 4.1 Contrato `index_refresh(directories=[...])`

* `index_refresh(directories: list[str] | None = None)`. Sin argumento ⇒ las raíces declaradas
  en **`INDEXER_DIR`** (variable de entorno del harness, `opencode.json` → `environment`;
  multi-valor separado por comas, `strip`, vacíos descartados), con `00-Resources` como
  **fallback** cuando está ausente o vacía: compatibilidad byte-a-byte con el contrato anterior y
  con los agentes ya escritos (D32).
* **Enmienda 2026-11-03 — el default lo declara el harness, no lo persiste el motor.** El literal
  `00-Resources` deja de ser el default del contrato y pasa a ser el fallback de `INDEXER_DIR`.
  Esa lista **no** se escribe en `tepochcalli.toml`, no la toca el wizard y el server la relee en
  cada llamada. Razón: el dueño quiere cambiar las raíces por defecto sin editar el toml ni
  re-ejecutar el wizard, y sin devolverle estado al motor (la opción B sigue descartada: el toml
  puede contener secretos y no es registro de una operación). El argumento `directories` sigue
  siendo el **override** de la llamada y el multi-raíz/dedup de §4.4 no cambia.
* Las raíces viven **solo** en la invocación o en el entorno del proceso: no se escriben en
  `tepochcalli.toml`, no tocan el wizard y no sobreviven al proceso. Cambiar de carpeta es un
  argumento (o una env), no un reinstall.
* El reporte gana `roots` **aditivo** (`{scanned, indexed, skipped, elapsed_ms, locked, roots}`):
  un campo nuevo no rompe consumidores; quitarlo o renombrarlo, sí (ADR-005, Hyrum).
* Cada pasada **declara el conjunto completo** de raíces; el índice refleja esa pasada (el target
  de CocoIndex reconcilia el estado declarado). Por eso `rag_status` publica
  `index.last_refresh_roots` —de la sesión, D42— además de `index.available_roots` (D67): el
  agente que quiere ampliar el alcance pregunta qué hay y qué está indexado en vez de adivinar.
* **Fail-fast atómico (D65):** se validan las N raíces **antes** de caminar ninguna. Si una falla,
  no se indexa ninguna y el error nombra la raíz mala, las que sí existen y las sugerencias. Un
  índice parcial que nadie pidió es peor que un error: el usuario corrige y reintenta una vez, y
  `scanned == indexed + skipped` describe siempre una operación completa.

### 4.2 `source_path` relativo al VAULT (D41)

`normalize_source_path` deja de prefijar `00-Resources/`: devuelve la ruta POSIX relativa a la
raíz del vault (`materiales/a.pdf`, `documentos/a.pdf`, `00-Resources/nota.md`).

* **Razón decisiva:** con N raíces, dos raíces distintas pueden contener el **mismo relativo**.
  `materiales/a.pdf` y `documentos/a.pdf` solo no colisionan si la cita guarda el relativo al
  vault; el relativo a la raíz colapsaría ambas filas en `a.pdf` y la cita dejaría de localizar
  nada.
* Es isomorfo al modelo `FilePath = base_dir + relativo` de CocoIndex: el `base_dir` del walk es
  la raíz pedida, y la cita es ese mismo relativo re-anclado al vault. La diferencia es de
  **anclaje**, no de forma.
* Cambia el contrato de `search`: los `source_path` dejan de empezar por `00-Resources/` salvo
  para el material que de verdad vive ahí. Es un cambio **breaking** del campo, asumido por el
  dueño; `path_filter` pasa a interpretarse contra el vault, no contra el recurso.

### 4.3 Fuentes: whitelist ampliada y parseo nativo (D43/D48/D50/D54)

* Whitelist: `md`, `markdown`, `txt`, `pdf`, `docx`, `pptx`, `xlsx`, `xls` — un solo lugar para
  ampliarla (`WHITELIST_PATTERNS`), y `DocKind` espeja el mismo conjunto cerrado.
* `md/markdown/txt` se leen en UTF-8 estricto ⇒ `offsets_ref = "source"` (el slice del original
  reproduce `text`). El resto se extrae con markitdown ⇒ `offsets_ref = "extract"` (el binario no
  es espacio de cita). `offsets_ref_for` queda: `{md,markdown,txt} → "source"`, resto →
  `"extract"` (D50).
* **Coste explícito (D54):** markitdown extrae texto plano, así que un PDF pierde la jerarquía de
  headings ⇒ `heading` **nulo** en sus citas. D13 ya admite nulo; el criterio 5 se apoya en
  `source_path` + offsets. No se disimula con el título del fichero: un heading inventado es una
  cita falsa.
* `doc_kind` gana los tipos nuevos como columna de texto (aditiva), sin migración de esquema.

### 4.4 Recursión, raíz-fichero y dedup (D46)

* La recursión ya existe en el conector (`walk_dir(recursive=True)` + `**/*`); la multi-raíz la
  preserva a cualquier profundidad. No se añade límite de profundidad.
* Una raíz puede ser un **fichero suelto**: se emite como una entrada sin pasar por `walk_dir`
  (que lanza `ValueError` si no es directorio). El borde ya validó que existe y que su extensión
  está en la whitelist.
* Raíces solapadas (una dentro de otra, o la misma dos veces) se **deduplican** antes de caminar:
  sin dedup, el mismo fichero contaría dos veces y `scanned == indexed + skipped` mentiría.

### 4.5 La frontera de los symlinks es el VAULT (D47)

`classify_file` rechaza el symlink cuyo target resuelto sale del **vault**, no de la raíz pedida.
Con una sola raíz ambos límites coincidían; con N raíces, un link de `documentos/` a
`materiales/x.pdf` es legítimo (ambos dentro del vault y ambos indexables). El límite de confianza
del sistema siempre fue el vault (D16/B′); la raíz es una conveniencia de recorrido.

### 4.6 Presupuestos (D51)

Los documentos binarios quedan **fuera** del Δ<30 s y se miden aparte: markitdown parsea a
segundos por documento y un `.docx` de 200 páginas no cabe en el presupuesto de 50 md/txt. Se
publican dos medidas —Δ de texto y Δ de documentos— en vez de una promesa que se rompe sola.

### 4.7 Identidad de memo por raíz (D62)

Cada raíz se materializa como `ContextKey[Path]` (una clave **estable** por raíz), y todos los
`FilePath` de esa raíz se construyen con `base_dir=` esa clave — **nunca** con un `Path` pelado:
verificado en el pin `1.0.25`, `to_file_path` resuelve un `Path` contra el **CWD del proceso**
(`connectors/localfs/_common.py:69-75`), de modo que la clave de memo dependería de dónde se lanzó
el server. Con la clave explícita, mover el árbol no invalida el índice.

### 4.8 Existencia y tipo en el borde MCP (D64)

La validación de raíces (existe, es directorio o fichero con extensión soportada, dentro del
vault, sin `..`) vive en `paths.py`, **puro**, antes de tocar el disco. Motivo verificado:
`localfs.walk_dir` lanza `ValueError("Path is not a directory: …")`
(`connectors/localfs/_source.py:109-110`); si el motor lo dejara pasar, el `internal_guard` lo
convertiría en `INTERNAL` y el usuario que escribió mal una carpeta leería «fallo interno». En el
borde es `VALIDATION_ERROR` con `details.suggestions` — la taxonomía no crece (D39).

### 4.9 Ledger: lo que el conector YA resuelve (R1)

Verificado contra el `cocoindex==1.0.25` instalado en el payload. **No se reimplementa.**

| Hecho verificado | Fuente | Por qué NO lo escribimos |
| --- | --- | --- |
| Los directorios excluidos se **podan**: no se baja a ellos | `_source.py:136-138` (`is_dir_included` antes de encolar) + docstring de `PatternFilePathMatcher` | `**/.*` excluye el **subárbol** ⇒ indexar la raíz del vault no recorre `.tepochcalli/venv/` (2,4 GB), `.obsidian/` ni `.trash/`. No hacen falta patrones nuevos |
| Los bucles de symlink se cortan con la cadena de ancestros `(dev, ino)` | `_source.py:113-145` | Un visited-set nuestro sería un duplicado peor: no conoce los inodos y no corta el ciclo antes de abrir el directorio |
| `PermissionError` se traga en silencio (`continue`) | `_source.py:121-123` | Ya se contabiliza como `unreadable_dir` en `source.unvisited_skips`; lo que falta es **contar**, no recorrer |

Lo que sí es nuestro y se conserva con su razón: whitelist y exclusiones (política de producto),
umbral de 100 MB y `SkipReason` (el conector no ofrece ni tamaño ni hook de errores), la frontera
de symlink del vault, y la normalización de cita.

### 4.10 Confirmation

* **Golden-vault, `offsets_ref="source"`:** indexar `materiales/` produce filas con
  `source_path == "materiales/<fichero>"` y, leyendo ese fichero del vault,
  `text[char_start:char_end] == chunk.text` (identidad F1).
* **Golden-vault, documento:** un `.docx` bajo `documentos/` produce filas con
  `doc_kind == "docx"`, `offsets_ref == "extract"` y `heading is None`; el slice del **extracto**
  reproduce `text`.
* **Colisión imposible:** `materiales/a.md` y `documentos/a.md` en la misma pasada ⇒ dos filas,
  dos `source_path` distintos; ninguna se pierde.
* **Compatibilidad:** `index_refresh()` sin argumentos y sin `INDEXER_DIR` declarada ⇒
  `roots == ["00-Resources"]` y el mismo `scanned` que la versión anterior sobre el mismo vault.
* **Atomicidad (D65):** `index_refresh(directories=["materiales", "no-existe"])` ⇒
  `VALIDATION_ERROR` y el recuento de filas del índice **no cambia**.
* **Nunca `INTERNAL`:** una raíz inexistente, un fichero con extensión no soportada y un
  directorio donde se esperaba un fichero devuelven `VALIDATION_ERROR` con
  `details.suggestions` no vacías.
* **Clave de memo estable:** dos pasadas desde `chdir` distintos sobre el mismo vault ⇒ la
  segunda devuelve `indexed == 0` y `scanned == skipped`.
* **Poda:** indexar la raíz del vault no produce filas ni skips bajo `.tepochcalli/venv/`,
  `.obsidian/` ni `.trash/`, y el tiempo no escala con su tamaño.
* **Symlink:** un directorio con un link a sí mismo termina el walk (sin visited-set propio).
* **Dedup:** `directories=["00-Resources", "00-Resources/sub"]` ⇒ `scanned == indexed + skipped`
  y ninguna entrada duplicada.
* **`rag_status`:** expone `index.available_roots` con los directorios de primer nivel visibles y
  cabe en <200 tokens.

## 5. Pros and Cons of the Options

### Opción A — Raíces por llamada, cita relativa al vault (elegida)

* ✅ **Pros:** Cero estado oculto; cambiar de carpeta es un argumento; la cita localiza el fichero aunque haya N raíces con el mismo relativo; el wizard no se toca; el reporte declara qué se indexó.
* ⚠️ **Cons:** El agente debe **recordar** pasar las raíces en cada llamada (no hay memoria entre sesiones); `source_path` es un cambio breaking para `search` y `path_filter`; más casos de validación (N raíces, dedup).
* ⚖️ **Neutral:** La raíz deja de ser constante del producto y pasa a ser dato de la operación.

### Opción B — Config persistente (`index.roots` en el toml)

* ✅ **Pros:** El agente no repite argumentos; una preferencia por vault.
* ⚠️ **Cons:** Estado oculto: cambiar de carpeta obliga a editar el toml o a re-ejecutar el wizard (justo lo que D32 elimina); el índice y la config pueden divergir sin que nadie lo vea; `tepochcalli.toml` puede contener secretos y no debe ser el registro de una operación.
* ⚖️ **Neutral:** Habría que versionar el fichero en el wizard y migrarlo.

### Opción C — `source_path` relativo a la raíz

* ✅ **Pros:** No cambia el contrato actual de `search`; las citas son más cortas.
* ⚠️ **Cons:** Colisiona con N raíces (`materiales/a.pdf` y `documentos/a.pdf` se vuelven el mismo `a.pdf`); la cita deja de localizar el fichero y el criterio 5 se apoya en un identificador ambiguo.
* ⚖️ **Neutral:** Obligaría a un campo extra `root` en cada fila para desambiguar — un par donde hoy basta uno.

### Opción D — Una tabla LanceDB por raíz

* ✅ **Pros:** Aislamiento: borrar una raíz es borrar su tabla; reindexar una no toca las demás.
* ⚠️ **Cons:** Multiplica el coste de búsqueda (N ANN + N FTS + fusión entre tablas) y rompe el ranking único ANN+FTS que sostiene <500 ms; `top_k` global exige mezclar resultados de esquemas idénticos; la lista de tablas es estado que hay que mantener.
* ⚖️ **Neutral:** Coherente si algún día una raíz fuese de otro usuario o de otra política de embeddings; hoy no lo es.

## 6. Consequences

* ✅ **Positives:** El usuario investiga sobre su estructura real (no solo `00-Resources/`); los ofimáticos entran sin paso de conversión; el agente descubre carpetas con `rag_status`; la cita sigue siendo un único string localizable; el índice incremental no se invalida al mover el vault.
* ⚠️ **Negatives / Risks:** El PDF pierde la jerarquía de headings (D54) — el criterio 5 depende de `source_path` + offsets, no del heading. Los documentos binarios no entran en el Δ de 30 s (D51) y un vault lleno de `.docx` tendrá refreshes lentos y visibles. El agente **debe** pasar raíces explícitas: sin argumento solo indexa las de `INDEXER_DIR` (fallback `00-Resources/`), y un agente que asuma memoria entre sesiones indexará de menos. El target declarativo de CocoIndex reconcilia por pasada: una llamada que no declara una raíz puede purgar sus filas — T2 lo fija con el test de tres pasadas y `last_refresh_roots` lo hace observable. `source_path` breaking: los `path_filter` y prompts que asumían el prefijo `00-Resources/` hay que revisarlos.
* ⚖️ **Neutral:** La raíz pasa de constante a argumento; el ledger de §4.9 se convierte en la referencia obligatoria antes de «optimizar» el walk; la whitelist y `DocKind` crecen juntos o no crecen.

## 7. Related Decisions

* **ADR-001** — mismo motor (CocoIndex): el incrementalismo memoizado es lo que hace barato re-anclar N raíces.
* **ADR-002** — LanceDB sin daemon: una sola tabla `chunks` sigue siendo válida con N raíces (opción D descartada); nada que arrancar.
* **ADR-005** — el puerto `ChunkReader`/`search` consume estas citas: `source_path` vault-relativo es el campo que cruza la frontera y por eso el cambio se congela aquí.
* **ADR-009** — conversor documento→Markdown: sigue siendo el camino del **artefacto**; este ADR es el camino del **índice** (no se indexa el `.md` convertido, se indexa el original).
* **ADR-011** — política de dependencias y embedder único: la ampliación de formatos no añade librerías (markitdown ya está); el ledger de §4.9 complementa su ledger de no-reinvención.
* **D9.1** — convención de carpetas: con multi-raíz, `00-Resources/` deja de ser la única indexable pero sigue siendo el fallback de `INDEXER_DIR` (§4.1) y el destino de `add_source`.

## 8. Compliance and Review

* **Success metrics:** 0 respuestas con `source_path` ambiguo sobre un vault con dos raíces homónimas; 0 `INTERNAL` por raíz mal escrita; Δ de texto p95 <30 s tras el cambio; `scanned == indexed + skipped` en el 100 % de los refreshes de la suite.
* **Next review date:** 2027-05-02
* **Revisit triggers:** El agente falla repetidamente por no repetir raíces entre llamadas ⇒ reevaluar B con estado explícito y visible; el ranking se degrada al crecer el número de raíces ⇒ reevaluar D; aparece un formato que markitdown no extrae con fidelidad ⇒ reevaluar la whitelist, no el contrato.

---
*Template based on [MADR v4.0](https://adr.github.io/madr/) and [Nygard's ADR format](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).*
