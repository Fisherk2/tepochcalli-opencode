# Spec: Estratégia de embeddings (modelo default, cache y proveedores)

* **Status:** Proposed
* **Date:** 2026-10-21
* **Author:** Arquitecto (entrevista /spec)
* **Reviewers:** Product Owner (usuario)
* **Traceability:** docs/UH.md (deuda cognitiva 6), ADR-006 (modelo default), specs/spec-rag-engine.md, specs/spec-installer-wizard.md

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
* El wizard valida la presencia del modelo post-descarga (peso esperado ≈470MB) y ofrece reintento; `--skip-model` la omite (búsqueda devolverá `INDEX_EMPTY` hasta proveer modelo).
* `models/` es eliminable en cualquier momento: se regenera (provenance HuggingFace documentada en docs/SECURITY.md).

### Requisitos mínimos (TRD §hardware, respuesta a UH.md 6)

* CPU 4 núcleos modernos; 8GB RAM; 3-4GB libres para `.tepochcalli/` completo (venv 1-2GB + modelo 470MB + LanceDB inicial); disco SSD recomendado.
* Sin GPU obligatoria para el default. Si RAM <8GB: el wizard aborta con mensaje y requisitos (no instala "mitad").

### Procedimiento de swap de modelo

1. Editar `[embedding]` en `tepochcalli.toml`.
2. El próximo `index_refresh` detecta mismatch (campo `model` de las filas vs config) → responde `INDEX_STALE_MODEL` (spec-mcp-server §errores).
3. Ejecutar re-index completo: vaciar tabla `chunks` en `.tepochcalli/db/` y regenerar (`cocoindex` setup+update; wizard ofrece `tepochcalli reindex` como comodidad).
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
