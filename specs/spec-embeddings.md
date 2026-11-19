# Spec: Estratégia de embeddings (modelo default, cache y proveedores)

* **Status:** Approved 2026-10-23 (FTR Phase 0→1, docs/WORKFLOW.md §4) · **Enmienda 2026-11-18 — flujo destino (Proposed)** (§Enmienda 2026-11-18; el código vigente no cambia)
* **Date:** 2026-10-23 (original: 2026-10-21)
* **Author:** Arquitecto (entrevista /spec)
* **Reviewers:** Product Owner (usuario)
* **Traceability:** docs/BACKLOG.md (deuda cognitiva 6), ADR-006 (modelo default), ADR-007 (selección de provider en instalación, D7), ADR-008 (transparencia de hardware y swap atómico, D8), specs/spec-rag-engine.md, specs/spec-installer-wizard.md, specs/spec-mcp-server.md (`rag_status`, códigos `E_*`)

## Summary

Define cómo Tepochcalli genera embeddings: default local con `paraphrase-multilingual-MiniLM-L12-v2` (384 dims, ~470MB, CPU), cache de modelos en `.tepochcalli/models/`, proveedor/modelo configurables vía `.tepochcalli/config/tepochcalli.toml` con soporte de embedders externos por LiteLLM (100+ proveedores), requisitos mínimos de hardware y el procedimiento (y su costo) para cambiar de modelo.

## Problem / Motivation

El usuario quiere embebidos locales "donde configure sus modelos" y, a la vez, la opción de claves de APIs externas — preguntas abiertas de BACKLOG.md. Además, cambiar de modelo no puede degradar silenciosamente la búsqueda: un índice con dos familias de vectores es peor que un índice viejo.

> Como investigador con laptop sin GPU, quiero búsquedas semánticas decentes en español e inglés sin pagar APIs ni enviar mis PDFs a terceros.

## Goals and Non-Goals

### Goals

* Default cero-configuración: el wizard descarga e instala el modelo y nada más.
* Matriz documentada local vs externo (coste, privacidad, latencia, requisitos).
* Cache determinista en `.tepochcalli/models/` vía `SENTENCE_TRANSFORMERS_HOME`/`HF_HOME`.
* Piso de hardware explícito (8GB RAM, CPU 4-core) y señal clara si no se cumple.
* Procedimiento de swap de modelo con re-indexación completa explícita (consecuencia registrada en TECH_DEBT).

### Non-Goals

* Fine-tuning o entrenamiento de modelos propios.
* Comparación continua contra leaderboards (revisión semestral, no en runtime).
* Multi-modelo simultáneo (varios embedders indexando el mismo vault): soportado **no** — un índice, un modelo.

## Proposed Solution

El flow lee `[embedding]` de `tepochcalli.toml`: `provider = "local"` (default) o `provider = "litellm"` con `model` y `api_key_env`. Para `local`, CocoIndex usa `SentenceTransformerEmbedder("paraphrase-multilingual-MiniLM-L12-v2")` y el entorno del venv/vault apunta `SENTENCE_TRANSFORMERS_HOME=$VAULT/.tepochcalli/models` — la descarga ocurre una vez (wizard, fase de modelos) y nunca más viaja por red. Para externo, LiteLLM resuelve el resto.

## Detailed Design

### Modelo default (D4/ADR-006)

| Propiedad | Valor |
| --- | --- |
| Modelo | `paraphrase-multilingual-MiniLM-L12-v2` |
| Dimensiones | 384 |
| Peso | ~470MB |
| Inferencia | CPU (torch CPU wheel en venv) |
| Idiomas objetivo | ES + EN (50+ soportados) |
| Uso en sistema | chunks de `00-resources/` + query de `search` |

### Matriz local vs externo

| Criterio | Local MiniLM (default) | Local bge-m3 (upgrade GPU) | Externo vía LiteLLM |
| --- | --- | --- | --- |
| Coste por consulta | $0 | $0 | $ (tokens embedder) |
| Privacidad | material no sale del host | no sale | sale al proveedor |
| RAM mín. | 8GB | 16GB + GPU recomendada | host liviano |
| Latencia query | decenas de ms (presupuestado en spec-mcp-server) | cientos de ms en CPU | red + proveedor |
| Setup | ninguno (wizard) | editar config + reindex | clave API + editar config + reindex |
| Calidad ES/EN | buena (piso) | muy alta | alta (según proveedor) |

### Upgrade path (config, no código)

* `BAAI/bge-m3` (1024 dims, GPU recomendada): cambiar `model` en `[embedding]` → ejecutar re-index completo → refresh. Documentado para usuarios con hardware.
* API externa (OpenAI/Voyage/Cohere/etc. vía LiteLLM): `provider = "litellm"`, `model = "openai/text-embedding-3-small"` (ejemplo). La clave tiene dos fuentes, resueltas en un solo sitio (`EmbeddingConfig.resolve_api_key()`, flow y MCP comparten la regla): la variable de entorno nombrada por `api_key_env = "TEPOCHCALLI_EMBED_API_KEY"` — referenciable desde opencode.json con `{env:TEPOCHCALLI_EMBED_API_KEY}` — o la clave literal `api_key = "sk-…"` que el wizard escribe en `tepochcalli.toml` (gitignored). **Precedencia: la env var gana**; el fichero es el fallback. Coste: la indexación consume API tokens — advertencia visible en docs y en el wizard si se activa.

### Selección de provider en instalación (D7 — ADR-007)

El wizard incluye un paso **"Embedding provider"** (ubicación y rollback en specs/spec-installer-wizard.md §Fases) con cinco salidas. La elección alimenta `[embedding]` de `tepochcalli.toml`; ninguna salida escribe half-config.

| # | Salida del menú | provider/model en config | Descarga | Comportamiento |
| --- | --- | --- | --- | --- |
| 1 | `paraphrase-multilingual-MiniLM-L12-v2` — RECOMENDADO, pre-seleccionado | `local` / `paraphrase-multilingual-MiniLM-L12-v2` | ~470MB | Preserva el ready-to-use (ADR-006); indexación inicial corre al terminar el paso |
| 2 | Preset local alternativo: `BAAI/bge-m3` o `all-MiniLM-L6-v2` | `local` / id del preset | ~2.3GB / ~90MB | Peso estimado + detección de GPU en la UI; advertencia (no bloqueo) si no hay GPU para `BAAI/bge-m3`; `all-MiniLM-L6-v2` avisa EN-only, calidad ES limitada |
| 3 | ID libre de HuggingFace | `local` / id escrito por el usuario | variable | Pasa el **gate test-embed** (§abajo); campo opcional `HF_TOKEN` para modelos gated |
| 4 | API externa vía LiteLLM (OpenAI/Cohere/Voyage/Ollama-compatible) | `litellm` / model del proveedor | ninguna | Clave en `.tepochcalli/config/tepochcalli.toml` (gitignored, nunca en logs); sin descarga local; coste por token advertido |
| 5 | "Configurar después" | ninguno — `mode: none` | ninguna | el vault se instala COMPLETO (todas las demás fases del wizard corren), la indexación inicial se omite, RAG queda en estado `degraded`, y el wizard muestra el checklist final de re-entrada sin escribir half-config |

#### Gate test-embed y prueba de footprint (salidas locales — D7.1 + D8.1)

1. Para las salidas 1-3 (todo camino local, presets y HF custom por igual) el wizard descarga el modelo y corre la prueba de embedding: incrusta la frase de prueba `"tepochcalli embedding check"` con sentence-transformers **mientras muestrea el RSS pico del proceso** — la huella medida (`medido`) se muestra en la fila del menú; para la salida 3 la prueba actúa además como portero de validez.
2. El wizard descarga el ID de HuggingFace propuesto (con `HF_TOKEN` opcional si el modelo es gated — el campo `gated` de la API de HF lo anuncia antes de la descarga, D8.1).
3. Exige: respuesta vectorial válida (dims > 0, floats finitos) y lectura del nombre real del modelo desde su config.
4. Escribe `model + dims` en los metadatos del índice (`.tepochcalli/db/`); `search` los usará luego para rechazar cruces de dimensiones (`E_MODEL_MISMATCH`, spec-mcp-server).
5. Cualquier fallo → `E_MODEL_INVALID`: el candidato se rechaza —incluidos modelos que sentence-transformers cargaría en silencio como no-embeddings— y el wizard vuelve al menú sin escribir config.

#### `presets.toml` — el catálogo como datos (D7.2)

Embebido en el binario Rust del wizard vía `include_str!`. Actualizar modelos = editar datos + release por cargo-dist; la UI del wizard nunca se toca. Revisión periódica vinculada a los revisit-triggers de ADR-006 §8.

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `name` | string | Etiqueta mostrada en el menú |
| `hf_id` | string | ID en HuggingFace (p.ej. `BAAI/bge-m3`) |
| `revision` | string | (T6/D59) SHA del commit HF que se materializa; es lo que se escribe en `[embedding].revision` y lo que fija el path `<slug>@<sha>` |
| `dims` | integer | Dimensiones del vector (384, 1024…) |
| `size_mb` | integer | Peso estimado de la descarga (blob HF) |
| `gpu_recommended` | boolean | Muestra aviso de GPU recomendada (no bloquea) |
| `recommended_flag` | boolean | Marca RECOMENDADO / pre-seleccionado (exactamente un preset) |
| `disk_mb` | integer | (D8.1, presets.toml v2) Disco a ocupar en `models/` tras la descarga |
| `min_ram_gb` | float | (D8.1) RAM mínima para que el modelo funcione en CPU |
| `rec_ram_gb` | float | (D8.1) RAM cómoda (holgada) — denominador del ratio de badge D8.2 |

```toml
# presets.toml (embebido en el binario) — v2 con campos de hardware (D8.1/ADR-008)
[[preset]]
name = "MiniLM multilingüe (default)"
hf_id = "paraphrase-multilingual-MiniLM-L12-v2"
revision = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"   # T6/D59
dims = 384
size_mb = 470
disk_mb = 500
min_ram_gb = 0.7
rec_ram_gb = 1.0
gpu_recommended = false
recommended_flag = true

[[preset]]
name = "BGE-M3 (GPU)"
hf_id = "BAAI/bge-m3"
dims = 1024
size_mb = 2300
disk_mb = 2300
min_ram_gb = 2.4
rec_ram_gb = 2.9
gpu_recommended = true
recommended_flag = false
```

#### Tres fuentes de verdad de los requisitos (D8.1/ADR-008)

Cada fila del menú muestra `💾 disk (MB) · 🧠 RAM requirement · 🎮 GPU status` ANTES de la
selección, para presets y para IDs libres de HuggingFace. Fuentes en orden decreciente de
certidumbre; **todo número mostrado se etiqueta con su procedencia** (`medido`/`estimado`/`declarado`)
— nunca presentar una estimación como promesa (NFR cero-sorpresas).

| Fuente | Certidumbre | Cómo se obtiene | Cuándo aplica |
| --- | --- | --- | --- |
| **Medido** | ground truth | muestreo del RSS pico durante la prueba de embedding del gate test-embed (salidas 1-3, presets y HF custom por igual) | tras ejercitar el modelo en el host real |
| **Estimado (API HF)** | fórmula sobre metadatos | consulta a la API pública de HF antes de la descarga (tabla §abajo) | cualquier id de HF, pre-elección |
| **Declarado (presets.toml v2)** | curado por mantenedores | campos `disk_mb`, `min_ram_gb`, `rec_ram_gb`, `gpu_recommended` | presets; fallback cuando no hay red ni sondeo |

#### Extracción de requisitos vía API pública de HuggingFace (D8.1)

Para CUALQUIER id de HF (preset o libre), el wizard consulta la API pública ANTES de descargar:

| Campo de la API HF | Uso en el menú |
| --- | --- |
| `safetensors.parameters.total` | conteo de parámetros → RAM estimada con la fórmula canónica `params × 4 bytes × 1.3 overhead factor` (fp32, CPU resident); VRAM para modo GPU: el mismo tamaño de pesos + margen de activaciones |
| tamaños de blobs de `model.safetensors` | requisito de disco exacto (`disk_mb` estimado) |
| `gated` | si es `true` → el requisito de `HF_TOKEN` se surfaced temprano, antes de intentar la descarga |
| `pipeline_tag` + tags | pre-filtro barato antes del gate: tags válidos = `sentence-similarity` / `feature-extraction` / `sentence-transformers`; un modelo sin ninguno de los tres se rechaza como "not an embedding model" con semántica `E_MODEL_INVALID` (sin tocar disco) |

* Verificación en vivo (2026-10-21): `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` reporta `safetensors.parameters.total` = 117.6M → RAM estimada ≈ 117.6M × 4 B × 1.3 ≈ 0.61 GB, consistente con la fila de ejemplo de badges (host 4 GB: `recommended`).
* Host sin red o API inalcanzable: el número estimado degrada a `declarado` (presets) o a "sin dato" (id libre); la instalación nunca falla por esto (misma regla de fallback que D8.2 en specs/spec-installer-wizard.md).

#### HF_TOKEN

Las salidas 2-3 aceptan `HF_TOKEN` opcional para modelos gated: se usa solo durante la corrida
del wizard (env del proceso de descarga) y **nunca** se loggea ni se persiste sin que el usuario
lo pida explícitamente. La API key de la salida 4 sí se persiste, solo en
`.tepochcalli/config/tepochcalli.toml` (gitignored) bajo `[embedding].api_key`, y el motor la
resuelve con precedencia env-var > fichero (§Upgrade path); el flow y el MCP comparten esa regla.

#### Matriz de edge cases (D7)

| Caso | Comportamiento motor-MCP (código) | Comportamiento wizard (código/flag) | Recuperación (comando) |
| --- | --- | --- | --- |
| Sin modelo + sin key (salida 5 o config vacía) | `search`/`index_refresh` → `E_NO_EMBEDDER`; `rag_status` → `health.state = degraded` con `fix_hint` | instala el vault COMPLETO, omite indexación inicial, muestra checklist final de re-entrada | `tepochcalli config embedder` |
| API key inválida/expirada (salida 4) | detectada al primer embed → `E_API_AUTH` (proveedor nombrado, clave NUNCA loggeada) | valida la clave con un test-embed en el paso; reintento sin continuar | `tepochcalli config embedder` (re-ingresar clave) |
| Modelo HF no-válido (no es embedding model, salida 3) | no alcanza al motor si el gate funciona; índice corrupto → `E_MODEL_INVALID` | rechazo en el gate test-embed; no escribe config (flag implícita: volver al menú) | `tepochcalli config embedder` |
| Modelo gated sin `HF_TOKEN` (salida 3) | n/a (la descarga ocurre en el wizard, no en el motor) | descarga 401 → pide `HF_TOKEN` opcional; no bloquea otras salidas | `tepochcalli config embedder` con `HF_TOKEN` |
| Mismatch config vs índice (`config.model` ≠ modelo del índice) | `search` se niega a cruzar dims → `E_MODEL_MISMATCH` | advierte en re-instalación/re-entrada; nunca re-indexa solo | `tepochcalli reindex --confirm` |
| GPU insuficiente para `BAAI/bge-m3` (salida 2) | sin código: funciona pero excede presupuestos de latencia (lento) | detección de GPU → advertencia, no bloqueo (peso ~2.3GB mostrado) | `tepochcalli config embedder` (elegir default/preset CPU) |
| `--offline` sin `models/` cacheado | modo offline sin cache → `E_OFFLINE_NO_CACHE` | `--offline` solo válido si hay `models/` o config API presente; si no, fallo limpio | quitar `--offline` o `tepochcalli config embedder` |

La observabilidad de todos estos estados vive en el tool `rag_status()` y el dialecto `E_*` de
specs/spec-mcp-server.md §Códigos de error estructurados (ADR-007 §4.3).

### Estructura de `tepochcalli.toml` (config/)

```toml
# .tepochcalli/config/tepochcalli.toml — NUNCA se commitea
[embedding]
provider = "local"            # local | litellm | none (D15: none aceptado desde T6)
model = "paraphrase-multilingual-MiniLM-L12-v2"
revision = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"   # SHA HF del modelo (T6/D59); el path estable se deriva de model+revision
device = "cpu"                # device explícito para SentenceTransformerEmbedder(..., device=...); sobre-escribible por el usuario (ADR-008)
# provider = "litellm"
# model = "openai/text-embedding-3-small"
# api_key_env = "TEPOCHCALLI_EMBED_API_KEY"
# api_key = "sk-..."          # alternativa LITERAL a api_key_env (gitignored); la env var gana si existe
# provider = "none"           # D15: sin embedder — RAG en modo degraded (E_NO_EMBEDDER) hasta `tepochcalli config embedder`

[chunking]
max_chunk_size = 1536         # unidad: BYTES, no chars (el splitter mide bytes) — ver F4, spec-rag-engine.md §Chunking
overlap = 192                 # 12,5% de max_chunk_size (mismo ratio que el 128/1024 original en chars)
```

`top_k` e `INDEXER_DIR` **no** son claves del toml: son variables de entorno del harness
(`opencode.json` → `mcp.servers.tepochcalli-rag.environment`; contrato y validación en
[spec-mcp-server](spec-mcp-server.md) §Carga de configuración). La sección `[search]` está
**jubilada**: un toml viejo que la traiga solo recibe el aviso de sección desconocida y el valor
se ignora (el loader nunca lanza).

### Cache de modelos (`models/`)

* **Un solo snapshot, dos caminos (T6/D59).** El modelo se materializa en `<models>/<slug>@<revision>/` (`slug` = id con `/`→`__`) y **ambos** caminos cargan ese directorio con `cocoindex.ops.sentence_transformers.SentenceTransformerEmbedder`: el write path lo materializa (descarga pineada + `save` + rename atómico) y el read path **lo exige** sin descargar — si falta, `E_MODEL_INVALID` con guía `tepochcalli config embedder`. Consecuencia: ya no hay «índice con main y query con SHA»; `[embedding].revision` es el pin único y `embedding.model` sigue siendo el id que se muestra en `rag_status`.
* `SENTENCE_TRANSFORMERS_HOME` y `HF_HOME` se exportan apuntando a `.tepochcalli/models/` (env del venv vía archivo `.env` interno del venv o wrapper del entrypoint — decisión Phase 1). Esa caché es **temporal de descarga**; el directorio estable `<slug>@<revision>/` es el que se carga.
* El wizard valida la presencia del modelo post-descarga (peso esperado ≈470MB) y ofrece reintento; la salida 5 del menú D7.1 (o `--skip-model`) la omite: el vault se instala COMPLETO (todas las demás fases del wizard corren), la indexación inicial se omite, RAG queda en estado `degraded`, y el wizard muestra el checklist final de re-entrada sin escribir half-config — `search` responderá `E_NO_EMBEDDER` hasta `tepochcalli config embedder`.
* `models/` es eliminable en cualquier momento: se regenera (provenance HuggingFace documentada en docs/SECURITY.md).

### Requisitos mínimos (TRD §hardware, respuesta a BACKLOG.md §3 / Q-006)

* CPU 4 núcleos modernos; 8GB RAM; 3-4GB libres para `.tepochcalli/` completo (venv 1-2GB + modelo 470MB + LanceDB inicial); disco SSD recomendado.
* Sin GPU obligatoria para el default. Si RAM <8GB: el wizard aborta con mensaje y requisitos (no instala "mitad").

### Procedimiento de swap de modelo

Camino recomendado (D8.4/ADR-008): `tepochcalli config embedder` ejecuta el swap atómico sin reinstalar — el índice viejo permanece servable durante el re-index y el modelo viejo solo se borra tras el éxito (`--keep-previous` desactiva el GC). La secuencia de estados e invariantes viven en specs/spec-installer-wizard.md §Swap atómico; no se duplican aquí. El procedimiento manual equivalente:

1. Editar `[embedding]` en `tepochcalli.toml`.
2. El próximo `index_refresh` detecta mismatch (campo `model` de las filas vs config) → responde `INDEX_STALE_MODEL` (spec-mcp-server §errores; dialecto D7.3: `E_MODEL_MISMATCH`) y `search` se niega a cruzar dims.
3. Ejecutar re-index completo: vaciar tabla `chunks` en `.tepochcalli/db/` y regenerar (`cocoindex update` — la CLI de v1 no tiene paso `setup`, D11). El wizard ofrece el comando destructivo con confirmación explícita `tepochcalli reindex --confirm` (D7.4, specs/spec-installer-wizard.md §Re-entrada; no se duplica el procedimiento aquí).
4. Consecuencia registrada: docs/TECH_DEBT.md TD-3 (re-index = tiempo de CPU proporcional al corpus; sin modelo externo, sin costo $).

## Alternatives Considered

* **Hardcodear un modelo sin config:** *rechazado:* responde NO a las preguntas de deuda cognitiva de BACKLOG.md (modelos locales configurables + API key externa).
* **Detección automática de GPU y selección de modelo en runtime:** *rechazado:* no-determinismo de índices (un mismo vault cambiaría de espacio vectorial según hardware) → viola el principio "un índice, un modelo".
* **Compartir cache de modelos global (`~/.cache/huggingface`):** *rechazado:* el vault debe ser autocontenido (criterio portabilidad) y `models/` bajo `.tepochcalli/` es parte de D2.

## Trade-offs

* ✅ **Pros:** offline-after-first-run; coste $0; privacidad; camino de mejora sin fork del motor.
* ⚠️ **Cons / Risks:** 470MB + re-index al cambiar modelo; MiniLM pierde ante embedders frontier en prosa muy técnica.
* ⚖️ **Neutral:** aparece una superficie de config (`tepochcalli.toml`) que el wizard debe validar/mergear sin pisar al usuario.

## Testing Strategy

* Unit: parser de `tepochcalli.toml` (fallbacks a default si faltan claves).
* Integración: fixture que cambia modelo y asserta `INDEX_STALE_MODEL` y éxito tras re-index.
* Perf: latencia de query-embed en CPU de referencia alimenta el presupuesto de spec-mcp-server (≤120ms).

## Security Considerations

* API keys: solo `tepochcalli.toml` (gitignored) o variable de entorno; nunca en opencode.json commiteado — substitution `{env:VAR}` (docs/SECURITY.md).
* La descarga del default es de HuggingFace (org `sentence-transformers`): el pin de la revisión del modelo queda documentado en SECURITY §provenance — concreta: `tepochcalli_flow.config.MODEL_REVISION` = `e8f8c211226b894fcb81acc59f3b34ba3efd5f42` (2026-10-23), **default de `[embedding].revision`** y aplicado por igual a la ruta de escritura y a la de lectura desde T6/D59 (ambas cargan el mismo directorio `<models>/<slug>@<sha>/`).

## Rollback / Monitoring

* Volver al default = restaurar la clave `[embedding]` + re-index; `models/` viejo puede purgarse para liberar disco.
* Señal de monitoreo: tamaño de `models/` y dims del índice (`search` debug reporta modelo/actual).

## Open Questions

* ¿Exponer batch-size/threads de inferencia en config v1? (propuesto: no, heurística del engine)

## Enmienda 2026-11-18 — flujo destino (Proposed)

**Status: Proposed** — describe el destino del paso embedder del wizard según docs/BACKLOG.md
§"Wizard de instalación: flujo destino (2026-11-18)" (H9): **no se aprueba ni se implementa
aquí** (BACKLOG.md §2 «Wizard de instalación: flujo destino (2026-11-18)»); las secciones Accepted de arriba siguen describiendo el comportamiento
vigente. Depende de **ADR-015** (hermano, creado en este lote con Status **Proposed**) y de la enmienda coetánea en
specs/spec-installer-wizard.md.

### `device` en el contrato del wizard (ref ADR-015)

* El catálogo `Preset` (`crates/tepochcalli/src/config/presets.rs:10-33`) hoy **no** tiene
  campo `device`: el contrato destino lo añade, y el wizard escribe la elección explícita del
  usuario en `[embedding].device` de `tepochcalli.toml` — valores aceptados `cpu`
  (preseleccionado) | `cuda` | `cuda:N` (BACKLOG.md §2 / US-H9; la clave ya existe en §Estructura; `mps`/otros
  → futuro, trigger ADR-015 §8). La
  elección aplica por igual a indexación y búsquedas: comparten el mismo embedder.
* La re-entrada `tepochcalli config embedder` **preserva el valor `device` existente** como
  preselección, para no sobrescribir una elección manual.
* Drift conocido (a corregir en la implementación FUTURA, no en esta enmienda):
  `local_config()` hardcodea `device = "cpu"` (`application/embedder_config.rs:42`) y
  `picked_config_body()` del swap (`application/swap.rs:422`) la reutiliza — hoy la re-entrada
  pisa el valor del usuario con `cpu`.
* **Reafirma el rechazo a la autoselección en runtime** (§Alternatives Considered,
  "Detección automática de GPU y selección de modelo en runtime" — no-determinismo del índice):
  NO se reabre. La opción GPU se presenta como **botón deshabilitado con la razón "GPU no
  detectada"** cuando la sonda no la encuentra; si el usuario la fuerza sobre un dispositivo no
  disponible, se advierte con la cifra de procedencia `medido` y **nunca se bloquea** — el fallo
  efectivo ocurriría al cargar el modelo, no al configurar (UH §H9).

### Catálogo local ACTIVO (aclaración de `all-MiniLM-L6-v2`)

* Contradicción documentada y resuelta: docs/BACKLOG.md §H9 lista MiniLM (recomendado) y `BAAI/bge-m3`
  (GPU), mientras la tabla D7.1 de arriba (salida 2, `:75`) menciona históricamente también
  `all-MiniLM-L6-v2`. El **catálogo ACTIVO real es `presets.toml`**: exactamente dos presets —
  `paraphrase-multilingual-MiniLM-L12-v2` (recomendado/preseleccionado, ~470MB) y `BAAI/bge-m3`
  (GPU recomendada, ~2300MB) — como refleja `crates/tepochcalli/src/config/presets.toml`.
  `all-MiniLM-L6-v2` queda **solo como ejemplo de la guarda `test-embed`**, no como preset
  instalado.
* La opción de **ID libre de HuggingFace** sigue vigente como salida del menú: descarga a
  `.tepochcalli/models/`, portero **test-embed** (§Gate test-embed: frase de prueba, dims,
  nombre real, rechazo de no-embeddings) y campo opcional `HF_TOKEN` para modelos gated.
* Procedencia de las cifras (`declarado` catálogo / `estimado` fórmula `params × 4 bytes × 1.3`
  / `medido` RSS del gate) y badges del host: véase §Tres fuentes de verdad y
  spec-installer-wizard.md §D8.2 — no se duplican aquí.

### Sin campo `endpoint` + guarda anti-exfiltración (LAG de documentación, comportamiento YA implementado)

* `[embedding]` **NO tiene campo `endpoint`**: LiteLLM deriva proveedor y endpoint por defecto
  del prefijo de `model` (p. ej. `openai/` → `https://api.openai.com/v1`). La API key de la
  salida externa corresponde al endpoint **preestablecido** del proveedor; ni el wizard lo pide
  ni el TOML lo escribe.
* `api_key_env` es el **NOMBRE** de la variable de entorno y gana sobre `api_key` literal
  (§Upgrade path: precedencia env-var > fichero, ya documentada).
* El loader del flow **rechaza `://`, `http` o `@` dentro de `model`** con `provider =
  "litellm"` (avisa y cae al default): un `model` con componente de endpoint haría que LiteLLM
  enviara el texto del usuario a ESA URL — exfiltración por config. Está **ya implementado** en
  `obsidian-workspace/.tepochcalli/flow/tepochcalli_flow/config.py:357-369`; esta enmienda lo
  eleva a contrato documentado, sin cambiar el código.
* Endpoint custom (Ollama/vLLM/proxy): se declara como **variable de entorno de LiteLLM**
  (`OPENAI_BASE_URL`, `OLLAMA_API_BASE`) en `opencode.json` — fuera del TOML y del wizard, y no
  es contrato de Tepochcalli sino de LiteLLM.

## References

* ADR-006; CocoIndex embedders docs (SentenceTransformerEmbedder, LiteLLM); <https://www.sbert.net/docs/pretrained_models.html>; HF: `BAAI/bge-m3`
