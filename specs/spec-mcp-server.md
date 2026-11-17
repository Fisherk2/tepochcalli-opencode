# Spec: Servidor MCP `tepochcalli-rag` (capa de comunicación)

* **Status:** Approved 2026-10-27 (FTR Phase 2→3, docs/WORKFLOW.md §4) · Amended 2026-11-02 (Phase 3.5; ADR-009/010/011 Accepted 2026-11-03) · Amended 2026-11-03 (rev. 2: `index_refresh` sin argumentos, orden del dueño) · Amended 2026-11-12 (T2-bis: traza de progreso en `index_refresh` por `stderr`; contrato JSON intacto)
* **Date:** 2026-10-21
* **Author:** Arquitecto (entrevista /spec)
* **Reviewers:** Product Owner (usuario)
* **Traceability:** docs/UH.md (capa MCP Server; H1-H2 anexo 2026-10-30), ADR-005 (ports/adapters), ADR-007 (tool `rag_status` + dialecto `E_*`, D7.3), ADR-009 (conversor resumen-only), ADR-010 (índice multi-raíz), ADR-011 (dieta de dependencias), specs/spec-rag-engine.md, specs/spec-markitdown.md, specs/spec-embeddings.md, docs/WORKFLOW.md Phase 2

## Summary

`tepochcalli-rag` es un servidor MCP en Python (`.tepochcalli/mcp/`) que corre como proceso stdio local dentro del venv del proyecto y expone al harness OpenCode V2 **siete** herramientas con contrato fijo: las cuatro preexistentes `search`, `index_refresh`, `add_source` y `rag_status` (observabilidad D7.3/ADR-007), y las tres del conversor `convert_document`, `convert_base64` y `list_formats` (D28/ADR-009). Es el puerto (hexagonal) detrás del cual vive el motor CocoIndex/LanceDB; garantiza respuestas con citas estructuradas y presupuesto de tokens ≤2000 por consulta. Las cuatro preexistentes conservan su forma salvo los campos **aditivos** documentados aquí (`roots` en `index_refresh`; `last_refresh_roots` y `available_roots` en `rag_status`).

## Problem / Motivation

Sin una frontera tipada, el agente leería archivos crudos del vault (tokens por los cielos, sin citas confiables) o dependería de la API interna del motor (acople que rompe prompts al migrar motor). El harness necesita herramientas estables cuyos schemas hagan imposible una consulta no citada ni fuera de presupuesto.

> Como agente de investigación, quiero una herramienta `search` que me devuelva fragmentos con su archivo, encabezado y offsets, para citar la fuente original exacta en cada afirmación.

## Goals and Non-Goals

### Goals

* Contratos D6 exactos con ejemplos JSON y errores tipados (formato único de error).
* `search` end-to-end (tool-call→respuesta) **<500ms** p95 en CPU (criterio 3); punto de medición definido.
* Presupuesto de tokens por respuesta: diseño determinista ≤~1600 tokens de payload (criterio 4, con margen).
* `index_refresh` delta-only sobre el conjunto de raíces declarado en **`INDEXER_DIR`**, con reporte `{scanned, indexed, skipped, elapsed_ms, locked, roots}` y validación atómica `fail-fast` (criterio 2; ADR-010).
* `add_source` = conversión markitdown + escritura en `00-resources/<subdir>/` + refresh (criterio 7).
* `rag_status` = diagnóstico del provider/embedder e índice (estado `ok`/`degraded`, motivos `E_*` con `fix_hint` accionable, raíces disponibles e indexadas), coste <200 tokens por forma (D7.3/ADR-007, D67).
* Las 3 tools del conversor devuelven **solo** el resumen de 5 claves; el cuerpo nunca cruza el wire (H1/H2, D36).

### Non-Goals

* Endpoints de red (HTTP/socket) — stdio local exclusivamente (docs/SECURITY.md).
* Generación de respuestas con LLM dentro del server (esa es la capa del agente).
* Chat de múltiples turnos, historial, o stateful sessions: las tools son stateless salvo el índice y las raíces de la última pasada.
* Convertir ≠ indexar: el conversor no indexa (D35/D49); la ingesta sigue siendo `add_source`.
* OCR de documentos escaneados: fuera de v1 (⇒ `SOURCE_UNREACHABLE` con guía).

## Proposed Solution

Un paquete `tepochcalli_mcp` instalado en `.tepochcalli/venv/` (ADR-004), lanzado por OpenCode vía `mcp.servers.tepochcalli-rag` (stdio). Usa el SDK oficial de MCP para Python; las handlers implementan la lógica fina de selección de contexto sobre la API de lectura de LanceDB del flow (spec-rag-engine).

## Detailed Design

### API / Interface Design — tool `search`

Contrato: `search(query: str, top_k: int = TEPOCHCALLI_TOP_K (5), path_filter: str | None = None)`

```jsonc
// request (arguments del tool call)
{ "query": "¿qué métricas usa el modelo X en pacientes pediátricos?",
  "top_k": 5, "path_filter": "00-resources/lit-pediatría/**/*.pdf" }

// response (content[0].text = JSON canónico)
{ "query": "…", "took_ms": 142, "truncated": false,
  "results": [
    { "text": "…fragmento…",
      "source_path": "00-resources/lit-pediatría/ruiz2024.pdf",
      "heading": "2.3 Medidas de resultado",
      "char_start": 4120, "char_end": 5088, "score": 0.87 } ] }
```

* `path_filter`: glob relativo a la raíz del vault; se aplica como pre-filtro en la query LanceDB (`WHERE source_path LIKE …` traducido de `*`→`%`).
* `top_k`: por omisión el valor de **`TEPOCHCALLI_TOP_K`** (5) — es el `default` del schema, fijado **al arrancar** el proceso MCP. El agente puede sobreescribirlo por llamada; `budget.effective_top_k` acepta 1–20 y recorta el efectivo a **8** (fuera de rango ⇒ `VALIDATION_ERROR`). Un `TEPOCHCALLI_TOP_K` no entero o fuera de `[1,20]` cae a 5.
* `source_path`: ruta POSIX **relativa al vault** (D41/ADR-010 §4.2). Con N raíces, `materiales/a.pdf` y `documentos/a.pdf` son citas distintas; el prefijo `00-resources/` solo aparece cuando el material vive ahí. Es un cambio *breaking* del campo, asumido por el dueño.
* `score`: similitud normalizada [0,1] del híbrido ANN+FTS; orden descendente garantizado.
* Campo aditivo (T7, 2026-10-23): `offsets_ref: "source" | "extract"` — `source` si el slice del archivo original reproduce `text` (`md/markdown/txt`), `extract` si los offsets citan el markdown extraído por **markitdown** (`pdf/docx/pptx/xlsx/xls`; el binario jamás es el espacio de cita). No hay Docling (ADR-011/D53).
* Campos congelados por contrato (Hyrum, ADR-005): extensiones futuras solo aditivas/opcionales.

### Tool `index_refresh`

Contrato: `index_refresh()` — **sin argumentos**. Ejecuta un ciclo de actualización delta del flow (con lock de un solo proceso) sobre el conjunto de raíces que declara el usuario en **`INDEXER_DIR`** (`opencode.json` → `mcp.servers.tepochcalli-rag.environment`; multi-valor por **comas**, `strip`, vacíos descartados; ausente o vacía ⇒ `["00-resources"]`, D32/D42). El MCP **no puede añadir ni quitar raíces**: el conjunto vive solo en esa variable —no en la llamada y no en `tepochcalli.toml`—, y cambiarlo es editar la variable y reiniciar el MCP, nunca un argumento. El resto del contrato multi-raíz (recursión, raíz-fichero, dedup de solapadas) se aplica a ese conjunto.

> **El argumento `directories` se retiró el 2026-11-03 (orden del dueño).** El argumento retirado **no tiene efecto**: el SDK valida por firma y descarta las claves desconocidas, así que la tool se ejecuta con el conjunto de `INDEXER_DIR`. No es un error — es la garantía de que el wire no puede cambiar el conjunto. Razón: con el target de CocoIndex una pasada **declara el estado completo del índice**, así que aceptar un subconjunto («indexa solo `documentos/`») **purgaría** las filas de las demás raíces — permitirlo contradecía la regla de que solo el usuario cambia el conjunto. El delta ya es memoizado, así que re-escanear el conjunto completo cuesta solo lo que cambió: no se pierde rendimiento.

```jsonc
{ "scanned": 214, "indexed": 3, "skipped": 211, "elapsed_ms": 8200, "locked": false,
  "roots": ["00-resources", "03-Citations"] }
```

* `scanned`: archivos visitados en la pasada; `indexed`: (re)escritos al índice; `skipped`: memoizados/inalterados/excluidos; `elapsed_ms`: duración de la pasada. La identidad `scanned == indexed + skipped` se mantiene en toda pasada (incluido `locked` y directorio vacío).
* `roots`: campo **aditivo** (ADR-005/Hyrum) con el conjunto completo que declara `INDEXER_DIR` para esa pasada. Añadirlo no rompe consumidores; quitarlo o renombrarlo, sí.
* **Validación en el borde, antes de la costura** (`paths.validate_roots`, puro): raíz inexistente, tipo equivocado (un documento donde se espera un directorio o viceversa), fuera del vault o con `..` ⇒ `VALIDATION_ERROR` con `details: {requested, exists, suggestions[], vault_dirs[]}`. Las `suggestions` son por similitud sin distinguir mayúsculas (`Documentos` → `documentos`). El server lee la variable de su propio entorno en cada llamada; editar `opencode.json` exige reiniciar el MCP para que el proceso reciba el valor nuevo.
* **Fail-fast atómico (D65):** se valida el conjunto **completo** antes de caminar ninguna raíz. Una raíz mala ⇒ no se indexa ninguna y el recuento del índice no cambia. Un índice parcial que nadie pidió es peor que un error corregible.
* **Directorio vacío no es error:** `{scanned: 0, indexed: 0, skipped: 0, …}` — el agente no debe leerlo como fallo.
* Raíces solapadas o repetidas del conjunto se **deduplican**; una raíz puede ser un fichero suelto (ADR-010 §4.4). La recursión y la poda de directorios de punto (`.tepochcalli/`, `.obsidian/`, `.trash/`) ya las resuelve el conector `localfs`.
* Los documentos binarios (`.pdf/.docx/.pptx/.xlsx/.xls`) quedan **fuera** del presupuesto Δ<30 s y se miden aparte (D51): el criterio 2 aplica a deltas de texto. Un delta grande puede exceder 30 s: el server responde al completar y el timeout del harness cubre 120 s (TRD).
* **Traza de progreso (T2-bis, 2026-11-12):** el JSON de esta tool **no cambia** (siguen siendo esas 6 claves y nada más). Lo que se añade es que el proceso escribe a **`stderr`** —vía `logging`, que `python -m tepochcalli_mcp` fija a `sys.stderr`— una línea al abrir el ciclo con las raíces, una línea `extrayendo` / `extraído en N ms` por **documento binario** (los únicos con coste de segundos; los `.md`/`.txt` no se trazan uno a uno: 10 000 notas serían 10 000 líneas de ruido), la traza honesta `candado retenido` cuando otro proceso tiene el lock, y las cuentas finales. Razón: un PDF de 335 páginas tarda 50,6 s solo en extraerse ([documents](../docs/acceptance/documents.md) §2) y quien llamaba veía silencio. `stdout` queda **exclusivamente** para el JSON-RPC: una línea de log ahí corrompe el protocolo, y hay test que lo afirma.

### Tool `add_source`

Contrato: `add_source(uri: str, subdir: str | None = None)` — convierte URL/archivo a Markdown (capacidad markitdown, spec-markitdown), escribe bajo `00-resources/<subdir|_inbox>/`, luego invoca el ciclo de `index_refresh` internamente.

```jsonc
{ "ok": true, "written_to": "00-resources/_inbox/paper-2026-03.md",
  "indexed": { "scanned": 215, "indexed": 1, "skipped": 214, "elapsed_ms": 2600 } }
```

* **`00-resources` debe estar declarada en `INDEXER_DIR`:** si no lo está, `add_source` rechaza con `VALIDATION_ERROR` **antes de escribir**, con `details: {requested, allowed, hint}` — `requested` = `00-resources`, `allowed` = el conjunto declarado, `hint` = añadirla a la variable o usar `convert_document` con un `output_path` dentro de una raíz indexada. Escribir un fichero que el índice no va a ver es una promesa falsa; antes la tool lo añadía a la unión del refresh de esa llamada, y con el conjunto fijado en la variable eso ya no es posible sin que el MCP modifique raíces.
* Validación en el borde: `subdir` normalizado, sin `..`, queda dentro de `00-resources/`; `uri` acepta `http(s):`, `file:` (ver advertencia de seguridad). Un `file:` **inexistente** ⇒ `VALIDATION_ERROR`: la ruta mal escrita es un argumento corregible, no un documento ilegible que merezca `SOURCE_UNREACHABLE` (D64). El shape de respuesta **no cambia**.

### Tool `rag_status` (D7.3/ADR-007)

Contrato: `rag_status()` — sin argumentos. Devuelve el diagnóstico mínimo del provider de embeddings, el índice y la config; es barato por diseño (<200 tokens, ver §Presupuesto de tokens) para que el agente lo llame ante cualquier `E_*` sin penalizar la conversación.

```jsonc
// request (arguments del tool call)
{ }

// response — instalación sana (salida 1 del menú del wizard)
{ "embedder": { "mode": "local",
                "model": "paraphrase-multilingual-MiniLM-L12-v2",
                "dims": 384, "provider": null },
  "index":    { "rows": 1240, "model_matches_config": true,
                "last_refresh": "2026-10-21T14:32:10Z", "db_size_bytes": 18400000,
                "last_refresh_roots": ["00-resources"],
                "available_roots": ["00-resources", "documentos", "materiales"] },
  "config":   { "path": ".tepochcalli/config/tepochcalli.toml", "valid": true,
                "problems": [], "unknown_env": [] },
  "health":   { "state": "ok", "reason": null, "fix_hint": null } }

// response — instalación con "Configurar después" (salida 5 del menú embedder)
{ "embedder": { "mode": "none", "model": null, "dims": null, "provider": null },
  "index":    { "rows": 0, "model_matches_config": true,
                "last_refresh": null, "db_size_bytes": 0,
                "last_refresh_roots": [], "available_roots": ["00-resources"] },
  "config":   { "path": ".tepochcalli/config/tepochcalli.toml", "valid": true,
                "problems": [], "unknown_env": [] },
  "health":   { "state": "degraded", "reason": "E_NO_EMBEDDER",
                "fix_hint": "Ejecuta `tepochcalli config embedder` y luego `index_refresh()`" } }
```

* `index.last_refresh_roots`: raíces de la última indexación **de la sesión** (D42/ADR-010 §4.1); `[]` si aún no hubo refresh. Hace observable qué dejó indexado la pasada anterior.
* `index.available_roots`: directorios de **primer nivel** del vault que son indexables; los de punto (`.tepochcalli/`, `.obsidian/`, `.trash/`) quedan fuera (D67). El agente **pregunta** qué hay en vez de adivinar qué carpeta indexar.
* Salida 5 ("Configurar después"): el vault se instala COMPLETO (todas las demás fases del wizard corren), la indexación inicial se omite, RAG queda en estado `degraded`, y el wizard muestra el checklist final de re-entrada sin escribir half-config.

* `embedder.mode`: `local` (peso en `.tepochcalli/models/`), `api` (LiteLLM: `provider` nombra el proveedor, `model` su id) o `none` (sin provider — salida 5).
* `index.model_matches_config`: `false` cuando el campo `model` de los metadatos del índice ≠ `[embedding].model` de config (gate anti-cruce de dims; el índice registra `model + dims` en la instalación, D7.1).
* `health.reason` usa exclusivamente los códigos de §Códigos de error estructurados; `fix_hint` es la solución exacta para el usuario (la regla del vault en specs/spec-agent-workflow.md obliga al agente a reportarla, no el error crudo).
* `config.valid` = el toml parsea **y** `config.problems` está vacío. Mide coherencia de la configuración, no existencia del fichero: ausente ⇒ `true` (los defaults son canónicos).
* `config.problems`: mensajes cortos (≤80 chars, tope 3 + `"… y N más"`) de lo que el usuario escribió mal en el `environment` — `TEPOCHCALLI_ROOT` inexistente o que no es directorio, **cada** raíz de `INDEXER_DIR` que falle (con la sugerencia cuando la hay) y `TEPOCHCALLI_TOP_K` no entero o fuera de `[1,20]`. Es diagnóstico completo: `index_refresh` sigue siendo fail-fast y nombra solo la primera raíz mala (D65).
* `config.unknown_env`: nombres que **parecen** nuestras variables y no lo son (`INDEXER_DRI`, `TEPOCHALLI_ROOT`…), tope 3. Es el único error de configuración que ningún validador de valor puede cazar: una clave mal escrita se ignoraría en silencio.
* Ni `problems` ni `unknown_env` degradan `health`: un `INDEXER_DIR` malo no rompe `search` (el índice ya construido sigue sirviendo) y un estado `degraded` exigiría un `E_*` nuevo, que D39 prohíbe.

### Tools del conversor (D28/ADR-009)

`convert_document(path, output_path?, format?)` y `convert_base64(data, output_path?, format?, filename?)` convierten un documento a Markdown **en proceso** y devuelven solo el resumen; `list_formats()` publica el catálogo. El cuerpo nunca viaja en `content[0].text` (H1/H2, D36). Catálogo, cadena de fallback y detalle del conversor: [spec-markitdown](spec-markitdown.md).

```jsonc
// convert_document(path, output_path?, format?)  → y convert_base64(data, output_path?, format?, filename?)
{ "written_to": "00-resources/informe-anual.md",
  "source_uri": "00-resources/fuentes/informe-anual.docx",
  "bytes": 48213, "chars": 47120,
  "preview": "# Informe anual 2026\n\n…", "truncated": true }

// list_formats()
{ "formats": [".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".html", ".htm", ".csv",
              ".txt", ".md", ".markdown", ".json", ".jsonl"],
  "count": 13, "notes": "…sin OCR: un PDF escaneado no tiene capa de texto…" }
```

* **Sin clave `ok`**: el éxito es la ausencia de error; `truncated` solo aparece cuando `preview` (≤500 caracteres) se recortó. `bytes`/`chars`/`preview` se leen del fichero escrito, no del buffer en memoria.
* **B′ (D31):** entrada y `output_path` deben resolver dentro del vault; `..`, ruta absoluta externa o symlink que escapa ⇒ `VALIDATION_ERROR`. La validación corre **antes** de convertir.
* **Existencia y tipo en el borde (D64):** `path` inexistente o que es un directorio ⇒ `VALIDATION_ERROR` con `details.suggestions`, sin invocar markitdown. El padre del `output_path` debe existir como directorio dentro del vault.
* **Idempotencia (D66):** destino con los mismos bytes ⇒ misma respuesta de éxito; con bytes distintos ⇒ `VALIDATION_ERROR` («elige otro `output_path`») y nombre alternativo propuesto. Nunca se sobrescribe.
* `convert_base64` exige `format` **o** `filename`; sin pista de tipo ⇒ `VALIDATION_ERROR`. `output_path` omitido ⇒ `00-resources/<slug>.md` (`paths.slugify_uri`).
* El `.md` escrito **no** lleva frontmatter ni `converted_at`: un timestamp rompería la idempotencia (D66).

### Manejo de errores (formato único)

Toda falla → tool result con `isError` y payload JSON canónico (nunca texto libre): los códigos heredados llevan `details`; los códigos `E_*` de D7.3 llevan `fix_hint` (ver §Códigos de error estructurados).

```jsonc
{ "error": { "code": "INDEX_EMPTY",
             "message": "El índice no existe; ejecute index_refresh().",
             "details": null } }
```

| Code | Significado | Acción sugerida del agente |
| --- | --- | --- |
| `VALIDATION_ERROR` | argumentos inválidos: `top_k` fuera de rango, glob malformado, `subdir` fuera de `00-resources`, **ruta inexistente, tipo equivocado, raíz fuera del vault o con `..`, formato no soportado, base64 sin pista de tipo**, destino ocupado con contenido distinto | reintentar corrigiendo args (los `details.suggestions` bastan) |
| `INDEX_EMPTY` | tabla `chunks` inexistente **con embedder configurado** (sin embedder el estado es `E_NO_EMBEDDER`, que tiene precedencia) | invocar `index_refresh()`; si devuelve `E_NO_EMBEDDER` → `rag_status()` y reportar fix_hint |
| `INDEX_STALE_MODEL` | dims/modelo del índice ≠ config actual | avisar usuario: requiere `tepochcalli reindex --confirm` (spec-embeddings; alias D7.3: `E_MODEL_MISMATCH`) |
| `ENGINE_LOCKED` | `add_source`: su refresh interno quedó bloqueado por otro proceso (`index_refresh` **no** emite este error: devuelve `{scanned:0, indexed:0, skipped:0, locked:true}`) | reintentar en segundos |
| `SOURCE_UNREACHABLE` | **solo** el documento existe y es del tipo pedido pero no se puede leer/convertir (escaneado sin capa de texto, corrupto, cifrado); en `add_source`, fallo de fetch/convert | informar y ofrecer OCR manual o guardar el `.md` a mano |
| `INTERNAL` | **solo** bug nuestro (detalles al log, nunca al cliente) | reportar issue |

Forma de `details` cuando el error es corregible (rutas, raíces, formato):

```jsonc
{ "error": { "code": "VALIDATION_ERROR",
             "message": "La raíz no existe: 'Documentos'",
             "details": { "requested": "Documentos", "exists": false,
                          "suggestions": ["documentos"],
                          "vault_dirs": ["00-resources", "documentos", "materiales"] } } }
```

* Las `suggestions` se calculan por similitud **sin distinguir mayúsculas** (`Documentos` → `documentos`); `vault_dirs` lista lo que sí existe para que el agente corrija en un reintento.
* **La taxonomía NO crece (D39):** ningún caso nuevo introduce un código fuera de los tres de D39 —`VALIDATION_ERROR`, `SOURCE_UNREACHABLE`, `INTERNAL`— más los heredados (`INDEX_EMPTY`, `INDEX_STALE_MODEL`, `ENGINE_LOCKED`) y los `E_*` de D7.3. Un formato no soportado, una raíz mal escrita o un `file:` inexistente son `VALIDATION_ERROR`; `SOURCE_UNREACHABLE` no culpa a la ruta.
* `SYMLINK_ESCAPE` sigue siendo un skip tipado **del motor**, no un código de wire.

### Códigos de error estructurados (D7.3/ADR-007)

Además de los códigos heredados de la tabla anterior, los tools emitidos desde la frontera de provider usan el dialecto `E_*` con payload `{error:{code,message,fix_hint}}:

```jsonc
{ "error": { "code": "E_API_AUTH",
             "message": "La clave de OpenAI (LiteLLM) fue rechazada al incrustar la query.",
             "fix_hint": "Ejecuta `tepochcalli config embedder` y re-ingresa la clave; la clave nunca se registra en logs" } }
```

| Código | Significado | Tools que pueden emitirlo |
| --- | --- | --- |
| `E_NO_EMBEDDER` | sin modelo local ni API configurada (modo `none`) | `search`, `index_refresh`, `add_source` (diagnóstico en `rag_status`) |
| `E_API_AUTH` | clave de API inválida/expirada — detectada al primer embed; se nombra el proveedor, la clave NUNCA se loggea | `search`, `index_refresh`, `add_source` |
| `E_MODEL_MISMATCH` | `config.model` ≠ modelo registrado en los metadatos del índice; `search` se niega a cruzar dims | `search`, `index_refresh` |
| `E_MODEL_INVALID` | modelo custom de HuggingFace que fallaría el test-embed o no es embedding model (p.ej. `models/` corrompido post-instalación) | `search`, `index_refresh`, `add_source` |
| `E_OFFLINE_NO_CACHE` | modo `--offline` sin `models/` cacheado ni config API presente | `search`, `index_refresh`, `add_source` |

* Nota de compatibilidad: `E_MODEL_MISMATCH` es el término D7.3 de la condición que el código heredado `INDEX_STALE_MODEL` ya describía; mientras los contract tests de v1 lo fijan, ambos viajan en el payload (`code` = `E_MODEL_MISMATCH`, `details.legacy_code` = `INDEX_STALE_MODEL`). Los demás `E_*` son nuevos y no tienen alias.
* Regla del vault (`AGENTS.md` del workspace, specs/spec-agent-workflow.md): ante cualquier `E_*`, el agente llama `rag_status()` y reporta al usuario la solución exacta del `fix_hint`, no el error crudo.

### Presupuesto de latencia (<500ms, criterio 3)

Punto de medición: desde que el server recibe `tools/call(search)` (marca en handler) hasta que serializa la respuesta completa — excluye arranque del proceso MCP (cold start del harness, amortizado por sesión) e incluye embed de la query.

| Etapa | Presupuesto p95 |
| --- | --- |
| Embed de query (MiniLM CPU, 1 frase) | ≤120ms |
| Búsqueda ANN+FTS (≤100k chunks) | ≤200ms |
| Ensamblado/truncado/JSON | ≤30ms |
| Margen IPC/stdio | ≤150ms |
| **Total** | **≤500ms** |

### Presupuesto de tokens (≤2000, criterio 4)

Diseño determinista en el server (no depende del modelo):

* Payload máximo devuelto por `search`: `top_k` efectivo = min(solicitado, `TEPOCHCALLI_TOP_K` —5 por default—; tope duro 8) × chunk ≤1024 chars ≈ 5×~260 tokens ≈ **1300 tokens**.
* Overhead de citación por resultado ≈25 tokens (path+heading+offsets compactos) → +125 tokens.
* Techo duro: si la suma estimada (peso por carácter: CJK/emoji ⇒ 1 token/car, ES/EN ⇒ 4 chars/token — revisión Phase 2, 2026-10-27) excede 1600, se descartan resultados de menor `score` y se marca `truncated: true` — deja ≥400 tokens de margen para la pregunta del usuario y la respuesta generada dentro de los 2000 totales (criterio 4 REAL también en chino/japonés).
* Fixtures de test assertan la cota con queries adversas (unicode, listas, PDFs con tablas).
* `rag_status`: su shape fijo de cuatro bloques (`embedder/index/config/health`) lo mantiene **<200 tokens** por construcción — el coste de llamarlo ante cualquier `E_*` es despreciable (D7.3/ADR-007). Las dos listas nuevas (`last_refresh_roots`, `available_roots`) son nombres de directorios de primer nivel: no rompen el presupuesto.
* Conversor: ~200 tokens típicos (resumen de 5 claves, `preview` ≤500) y techo 1600 con el **mismo estimador** de `budget.py`. El coste es constante respecto al tamaño del documento porque el cuerpo no cruza el wire (D36).

### Carga de configuración

* El server lee `.tepochcalli/config/tepochcalli.toml` en **cada llamada** (sin caché; así un swap de modelo se recoge sin reiniciar el server): `[embedding] provider/model/revision/device`, `[chunking] sizes`. Claves de API externas solo vía `{env:VAR}` o ese archivo (gitignored). La sección `[search]` está **jubilada**: si un toml viejo la trae, el loader avisa de sección desconocida y **no lanza** — el valor se ignora.
* Rutas derivadas de una única `TEPOCHCALLI_ROOT` (cwd del vault inyectado por `opencode.json` → `cwd`): `db/`, `flow/`, `models/`.
* Variables de entorno del harness (`opencode.json` → `mcp.servers.tepochcalli-rag.environment`):

  | Variable | Obligatoria | Default | Validación y efecto |
  | --- | --- | --- | --- |
  | `TEPOCHCALLI_ROOT` | sí | — | raíz del vault; toda ruta del contrato se valida contra ella (B′) |
  | `INDEXER_DIR` | no | `00-resources` | split por **comas** + `strip`, vacíos descartados (nunca `os.pathsep`: `:` colisiona con `C:\`); cada raíz relativa al vault —una absoluta solo si resuelve **dentro**—, existente, sin `..`; si no, `VALIDATION_ERROR` en el borde. Ausente o vacía ⇒ `00-resources`. Es el **único** conjunto de raíces del índice: `index_refresh()` no lo recibe y el MCP no lo modifica; el proceso lo recibe al arrancar, así que editarlo exige reiniciar el MCP |
  | `TEPOCHCALLI_TOP_K` | no | `5` | entero en [1,20]; no entero o fuera de rango ⇒ `5` + `problems`. Se lee **al arrancar** el proceso: es el `default` del schema de `search` (rango efectivo 1–8) y cambiarla exige reiniciar el MCP |

* Una variable **mal escrita** no se ignora en silencio: su nombre aparece en `rag_status().config.unknown_env` (el filtro es estrecho — `TEPOCH*` o cualquier nombre con `INDEXER`—, así que no escupe el entorno del harness). Un **valor** inválido aparece en `config.problems` y deja `config.valid: false`. Ambas señales llegan en la primera llamada, sin indexar nada.

### Empaquetado en el venv

* Entrypoint: el server se invoca como `python -m tepochcalli_mcp` (D17 — el bit de ejecución se pierde en NTFS/fuseblk, lección (f) de Phase 1). `opencode.json` lo lanza como `[".tepochcalli/venv/bin/python", "-m", "tepochcalli_mcp"]` con `cwd` = raíz del vault (spec-installer-wizard §merge de config); el console script `tepochcalli-mcp` sigue definido en el paquete pero **no se usa**.

## Alternatives Considered

* **Alternative A:** Plugin OpenCode inyectando contexto — rechazado por ADR-005 (acople temprano al harness; previsto como evolución).
* **Alternative B:** CLI JSON vía bash — sin schema tipada; el modelo puede romper citas/presupuesto (ADR-005).
* **Alternative C:** Delegar la selección de top-k/token budget al prompt del agente — transfiere una garantía medible al no-determinismo del LLM; rechazado.

## Trade-offs

* ✅ **Pros:** Contratos estables y testeables sin LLM; garantías de criterios 2-5 centralizadas; motor intercambiable.
* ⚠️ **Cons:** Proceso extra por sesión; el truncado determinista puede cortar contexto que un humano editaría; doble mantenimiento de esquema (flow + server) hasta estabilizar.
* ⚖️ **Neutral:** El equipo del vault aprende el patrón tool-contract de MCP.

## Testing Strategy

* Contract tests contra vault fixture: shape exacto de request/response, codes de error, globs de `path_filter`.
* Contract tests multi-raíz: `INDEXER_DIR` con dos raíces, dedup de solapadas, raíz-fichero; `roots` en el reporte y `scanned == indexed + skipped` en todos los casos. `index_refresh` llamado con el retirado `directories` ⇒ se indexa el conjunto de `INDEXER_DIR`, **sin error**: el SDK descarta la clave desconocida.
* Contract tests de entorno: `INDEXER_DIR` multi-valor (coma, `strip`, vacíos), fallback `00-resources` con la env vacía, y `TEPOCHCALLI_TOP_K` inválido (no entero, ≤0 o >20) ⇒ `5` con el `default` del schema de `search` igual al valor de arranque.
* Raíz inexistente en `INDEXER_DIR` ⇒ `VALIDATION_ERROR` con `details.suggestions` no vacías y **nunca** `INTERNAL`; atomicidad: el recuento de filas del índice no cambia (D65).
* `add_source` con `00-resources` fuera de `INDEXER_DIR` ⇒ `VALIDATION_ERROR` con `details: {requested, allowed, hint}` y **ningún fichero escrito** (se comprueba el árbol antes/después).
* Directorio vacío ⇒ tres ceros, **no** error. `rag_status` expone `available_roots`/`last_refresh_roots` y cabe en <200 tokens; `file:` inexistente ⇒ `VALIDATION_ERROR`.
* Contract tests de las 3 tools del conversor (mismo shape que spec-markitdown): 5 claves y orden, `preview` ≤500, cuerpo ausente de `content[0].text` con un documento ≥100 000 caracteres, idempotencia y frontera B′.
* Contract tests D7.3: `rag_status` con shape exacto de los 4 bloques y <200 tokens; los cinco códigos `E_*` (`E_NO_EMBEDDER`, `E_API_AUTH`, `E_MODEL_MISMATCH`, `E_MODEL_INVALID`, `E_OFFLINE_NO_CACHE`) con payload `{error:{code,message,fix_hint}}`; instalación degraded (salida 5) → `search` = `E_NO_EMBEDDER` + `rag_status` = `degraded` con `fix_hint`.
* Fixtures de presupuesto: asserts de tokens por la fórmula de §Presupuesto de tokens (Σ sobre resultados ≤1600, con cota de la envoltura aparte) y de `rag_status` <200, en `just quality` (tests unitarios). La latencia se **mide** en `tests/benchmarks/bench_search.py`: p95 <500 ms **en local**, publicando n y método de percentil (metodología TRD) — **sin aserciones de latencia en CI**, que son la regla anti-flake de la casa: un rojo que depende de la máquina no es un rojo.
* Golden answers: queries ES/EN sobre la muestra de `00-resources/` (md+PDF) verificando que cada resultado cite `source_path` real y offsets reproducibles.

## Security Considerations

* Solo stdio local; sin binding de red (docs/SECURITY.md).
* `path_filter`/`subdir`: validación de ruta (path traversal → `VALIDATION_ERROR`); el server jamás escribe fuera del **vault** (`00-resources/` es el destino por omisión de `add_source`, no el único: el conversor escribe el `output_path` que se le pide, siempre dentro del vault — B′). **`file:` en `add_source` se RECHAZA si queda fuera del vault** (D16, ratificado 2026-10-26): markitdown con `file:` leería cualquier archivo accesible al proceso (riesgo documentado del canal markitdown, docs/SECURITY.md), y la validación corre **antes** de que el conversor toque el disco (`tepochcalli_mcp.paths.validate_source_uri` / `resolve_file_uri`).
* **B′ (D31/ADR-009):** el conversor valida también el **destino**: `output_path` dentro del vault, sin `..` ni symlink que escape, evitando *arbitrary file write*. `paths.ensure_within` es la defensa en profundidad antes de `os.replace`.
* La validación de existencia y tipo (raíces, `path`, padre de `output_path`) es **pura** (`paths.py`) y corre **antes** de tocar el disco; si el motor recibiera una ruta mal escrita, el `internal_guard` la convertiría en `INTERNAL`. Por eso el borde decide `VALIDATION_ERROR` (D64).
* Errores `INTERNAL` nunca exponen stack traces al harness.
* Las claves API nunca aparecen en logs ni en payloads de error: `E_API_AUTH` nombra solo el proveedor (D7.3/ADR-007); la clave vive únicamente en `.tepochcalli/config/tepochcalli.toml` (gitignored) o `{env:VAR}`.

## Rollback / Monitoring

* El server es stateless: revertir = checkout de la versión anterior + `uv sync`. El índice sobrevive independientes de versiones.
* Métricas mínimas por tool-call (log local rotativo en flujo stderr del proceso, no persistente): `took_ms`, `results_n`, `truncated`, error codes.

## Open Questions

* ¿`add_source` debería deduplicar por hash de `uri` para no re-descargar lo mismo? (propuesta Phase 2: hash en `_inbox/.sources.json`)

## References

* MCP Python SDK — <https://github.com/modelcontextprotocol/python-sdk>
* OpenCode V2 MCP servers — <https://opencode.ai/v2/docs/mcp-servers/>
* ADR-005; ADR-007 (`rag_status` + dialecto `E_*`, D7.3); ADR-009 (conversor resumen-only); ADR-010 (índice multi-raíz y cita vault-relativa); ADR-011 (dieta de dependencias); specs/spec-rag-engine.md; specs/spec-markitdown.md; specs/spec-embeddings.md
