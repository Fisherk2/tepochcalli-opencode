# Spec: Estratégia de embeddings (modelo default, cache y proveedores)

* **Status:** Proposed
* **Date:** 2026-10-21
* **Author:** Arquitecto (entrevista /spec)
* **Reviewers:** Product Owner (usuario)
* **Traceability:** docs/UH.md (deuda cognitiva 6), ADR-006 (modelo default), ADR-007 (selección de provider en instalación, D7), specs/spec-rag-engine.md, specs/spec-installer-wizard.md, specs/spec-mcp-server.md (`rag_status`, códigos `E_*`)

## Summary

Define cómo Tepochcalli genera embeddings: default local con `paraphrase-multilingual-MiniLM-L12-v2` (384 dims, ~470MB, CPU), cache de modelos en `.tepochcalli/models/`, proveedor/modelo configurables vía `.tepochcalli/config/tepochcalli.toml` con soporte de embedders externos por LiteLLM (100+ proveedores), requisitos mínimos de hardware y el procedimiento (y su costo) para cambiar de modelo.

## Problem / Motivation

El usuario quiere embebidos locales "donde configure sus modelos" y, a la vez, la opción de claves de APIs externas — preguntas abiertas de UH.md. Además, cambiar de modelo no puede degradar silenciosamente la búsqueda: un índice con dos familias de vectores es peor que un índice viejo.

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
|---|---|
| Modelo | `paraphrase-multilingual-MiniLM-L12-v2` |
| Dimensiones | 384 |
| Peso | ~470MB |
| Inferencia | CPU (torch CPU wheel en venv) |
| Idiomas objetivo | ES + EN (50+ soportados) |
| Uso en sistema | chunks de `00-Resources/` + query de `search` |

### Matriz local vs externo

| Criterio | Local MiniLM (default) | Local bge-m3 (upgrade GPU) | Externo vía LiteLLM |
|---|---|---|---|
| Coste por consulta | $0 | $0 | $ (tokens embedder) |
| Privacidad | material no sale del host | no sale | sale al proveedor |
| RAM mín. | 8GB | 16GB + GPU recomendada | host liviano |
| Latencia query | decenas de ms (presupuestado en spec-mcp-server) | cientos de ms en CPU | red + proveedor |
| Setup | ninguno (wizard) | editar config + reindex | clave API + editar config + reindex |
| Calidad ES/EN | buena (piso) | muy alta | alta (según proveedor) |

### Upgrade path (config, no código)

* `BAAI/bge-m3` (1024 dims, GPU recomendada): cambiar `model` en `[embedding]` → ejecutar re-index completo → refresh. Documentado para usuarios con hardware.
* API externa (OpenAI/Voyage/Cohere/etc. vía LiteLLM): `provider = "litellm"`, `model = "openai/text-embedding-3-small"` (ejemplo), clave vía `api_key_env = "TEPOCHCALLI_EMBED_API_KEY"` referenciada por opencode.json con `{env:TEPOCHCALLI_EMBED_API_KEY}` o en `tepochcalli.toml` (gitignored). Coste: la indexación consume API tokens — advertencia visible en docs y en el wizard si se activa.

### Selección de provider en instalación (D7 — ADR-007)

El wizard incluye un paso **"Embedding provider"** (ubicación y rollback en specs/spec-installer-wizard.md §Fases) con cinco salidas. La elección alimenta `[embedding]` de `tepochcalli.toml`; ninguna salida escribe half-config.

| # | Salida del menú | provider/model en config | Descarga | Comportamiento |
|---|---|---|---|---|
| 1 | `paraphrase-multilingual-MiniLM-L12-v2` — RECOMENDADO, pre-seleccionado | `local` / `paraphrase-multilingual-MiniLM-L12-v2` | ~470MB | Preserva el ready-to-use (ADR-006); indexación inicial corre al terminar el paso |
| 2 | Preset local alternativo: `BAAI/bge-m3` o `all-MiniLM-L6-v2` | `local` / id del preset | ~2.3GB / ~90MB | Peso estimado + detección de GPU en la UI; advertencia (no bloqueo) si no hay GPU para `BAAI/bge-m3`; `all-MiniLM-L6-v2` avisa EN-only, calidad ES limitada |
| 3 | ID libre de HuggingFace | `local` / id escrito por el usuario | variable | Pasa el **gate test-embed** (§abajo); campo opcional `HF_TOKEN` para modelos gated |
| 4 | API externa vía LiteLLM (OpenAI/Cohere/Voyage/Ollama-compatible) | `litellm` / model del proveedor | ninguna | Clave en `.tepochcalli/config/tepochcalli.toml` (gitignored, nunca en logs); sin descarga local; coste por token advertido |
| 5 | "Configurar después" | ninguno — `mode: none` | ninguna | el vault se instala COMPLETO (todas las demás fases del wizard corren), la indexación inicial se omite, RAG queda en estado `degraded`, y el wizard muestra el checklist final de re-entrada sin escribir half-config |

#### Gate test-embed (salida 3)

1. El wizard descarga el ID de HuggingFace propuesto (con `HF_TOKEN` opcional si el modelo es gated).
2. Incrusta la frase de prueba `"tepochcalli embedding check"` con sentence-transformers.
3. Exige: respuesta vectorial válida (dims > 0, floats finitos) y lectura del nombre real del modelo desde su config.
4. Escribe `model + dims` en los metadatos del índice (`.tepochcalli/db/`); `search` los usará luego para rechazar cruces de dimensiones (`E_MODEL_MISMATCH`, spec-mcp-server).
5. Cualquier fallo → `E_MODEL_INVALID`: el candidato se rechaza —incluidos modelos que sentence-transformers cargaría en silencio como no-embeddings— y el wizard vuelve al menú sin escribir config.

#### `presets.toml` — el catálogo como datos (D7.2)

Embebido en el binario Rust del wizard vía `include_str!`. Actualizar modelos = editar datos + release por cargo-dist; la UI del wizard nunca se toca. Revisión periódica vinculada a los revisit-triggers de ADR-006 §8.

| Campo | Tipo | Descripción |
|---|---|---|
| `name` | string | Etiqueta mostrada en el menú |
| `hf_id` | string | ID en HuggingFace (p.ej. `BAAI/bge-m3`) |
| `dims` | integer | Dimensiones del vector (384, 1024…) |
| `size_mb` | integer | Peso estimado de la descarga |
| `gpu_recommended` | boolean | Muestra aviso de GPU recomendada (no bloquea) |
| `recommended_flag` | boolean | Marca RECOMENDADO / pre-seleccionado (exactamente un preset) |

```toml
# presets.toml (embebido en el binario)
[[preset]]
name = "MiniLM multilingüe (default)"
hf_id = "paraphrase-multilingual-MiniLM-L12-v2"
dims = 384
size_mb = 470
gpu_recommended = false
recommended_flag = true

[[preset]]
name = "BGE-M3 (GPU)"
hf_id = "BAAI/bge-m3"
dims = 1024
size_mb = 2300
gpu_recommended = true
recommended_flag = false
```

#### HF_TOKEN

Las salidas 2-3 aceptan `HF_TOKEN` opcional para modelos gated: se usa solo durante la corrida
del wizard (env del proceso de descarga) y **nunca** se loggea ni se persiste sin que el usuario
lo pida explícitamente. La API key de la salida 4 sí se persiste, solo en
`.tepochcalli/config/tepochcalli.toml` (gitignored).

#### Matriz de edge cases (D7)

| Caso | Comportamiento motor-MCP (código) | Comportamiento wizard (código/flag) | Recuperación (comando) |
|---|---|---|---|
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
provider = "local"            # local | litellm
model = "paraphrase-multilingual-MiniLM-L12-v2"
# provider = "litellm"
# model = "openai/text-embedding-3-small"
# api_key_env = "TEPOCHCALLI_EMBED_API_KEY"

[chunking]
max_chunk_size = 1024
overlap = 128

[search]
top_k_default = 5
```

### Cache de modelos (`models/`)

* `SENTENCE_TRANSFORMERS_HOME` y `HF_HOME` se exportan apuntando a `.tepochcalli/models/` (env del venv vía archivo `.env` interno del venv o wrapper del entrypoint — decisión Phase 1).
* El wizard valida la presencia del modelo post-descarga (peso esperado ≈470MB) y ofrece reintento; la salida 5 del menú D7.1 (o `--skip-model`) la omite: el vault se instala COMPLETO (todas las demás fases del wizard corren), la indexación inicial se omite, RAG queda en estado `degraded`, y el wizard muestra el checklist final de re-entrada sin escribir half-config — `search` responderá `E_NO_EMBEDDER` hasta `tepochcalli config embedder`.
* `models/` es eliminable en cualquier momento: se regenera (provenance HuggingFace documentada en docs/SECURITY.md).

### Requisitos mínimos (TRD §hardware, respuesta a UH.md 6)

* CPU 4 núcleos modernos; 8GB RAM; 3-4GB libres para `.tepochcalli/` completo (venv 1-2GB + modelo 470MB + LanceDB inicial); disco SSD recomendado.
* Sin GPU obligatoria para el default. Si RAM <8GB: el wizard aborta con mensaje y requisitos (no instala "mitad").

### Procedimiento de swap de modelo

1. Editar `[embedding]` en `tepochcalli.toml`.
2. El próximo `index_refresh` detecta mismatch (campo `model` de las filas vs config) → responde `INDEX_STALE_MODEL` (spec-mcp-server §errores; dialecto D7.3: `E_MODEL_MISMATCH`) y `search` se niega a cruzar dims.
3. Ejecutar re-index completo: vaciar tabla `chunks` en `.tepochcalli/db/` y regenerar (`cocoindex` setup+update). El wizard ofrece el comando destructivo con confirmación explícita `tepochcalli reindex --confirm` (D7.4, specs/spec-installer-wizard.md §Re-entrada; no se duplica el procedimiento aquí).
4. Consecuencia registrada: docs/TECH_DEBT.md TD-3 (re-index = tiempo de CPU proporcional al corpus; sin modelo externo, sin costo $).

## Alternatives Considered

* **Hardcodear un modelo sin config:** *rechazado:* responde NO a las preguntas de deuda cognitiva de UH.md (modelos locales configurables + API key externa).
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
* La descarga del default es de HuggingFace (org `sentence-transformers`): el pin de la revisión del modelo queda documentado en SECURITY §provenance.

## Rollback / Monitoring

* Volver al default = restaurar la clave `[embedding]` + re-index; `models/` viejo puede purgarse para liberar disco.
* Señal de monitoreo: tamaño de `models/` y dims del índice (`search` debug reporta modelo/actual).

## Open Questions

* ¿Exponer batch-size/threads de inferencia en config v1? (propuesto: no, heurística del engine)

## References

* ADR-006; CocoIndex embedders docs (SentenceTransformerEmbedder, LiteLLM); https://www.sbert.net/docs/pretrained_models.html; HF: `BAAI/bge-m3`
