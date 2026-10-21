# Spec: Servidor MCP `tepochcalli-rag` (capa de comunicación)

* **Status:** Proposed
* **Date:** 2026-10-21
* **Author:** Arquitecto (entrevista /spec)
* **Reviewers:** Product Owner (usuario)
* **Traceability:** docs/UH.md (capa MCP Server), ADR-005 (ports/adapters), specs/spec-rag-engine.md, specs/spec-markitdown.md, docs/WORKFLOW.md Phase 2

## Summary

`tepochcalli-rag` es un servidor MCP en Python (`.tepochcalli/mcp/`) que corre como proceso stdio local dentro del venv del proyecto y expone al harness OpenCode V2 tres herramientas con contrato fijo: `search`, `index_refresh` y `add_source`. Es el puerto (hexagonal) detrás del cual vive el motor CocoIndex/LanceDB; garantiza respuestas con citas estructuradas y presupuesto de tokens ≤2000 por consulta.

## Problem / Motivation

Sin una frontera tipada, el agente leería archivos crudos del vault (tokens por los cielos, sin citas confiables) o dependería de la API interna del motor (acople que rompe prompts al migrar motor). El harness necesita herramientas estables cuyos schemas hagan imposible una consulta no citada ni fuera de presupuesto.

> Como agente de investigación, quiero una herramienta `search` que me devuelva fragmentos con su archivo, encabezado y offsets, para citar la fuente original exacta en cada afirmación.

## Goals and Non-Goals

### Goals

* Contratos D6 exactos con ejemplos JSON y errores tipados (formato único de error).
* `search` end-to-end (tool-call→respuesta) **<500ms** p95 en CPU (criterio 3); punto de medición definido.
* Presupuesto de tokens por respuesta: diseño determinista ≤~1600 tokens de payload (criterio 4, con margen).
* `index_refresh` delta-only con reporte `{scanned, indexed, skipped, elapsed}` (criterio 2).
* `add_source` = conversión markitdown + escritura en `00-Resources/<subdir>/` + refresh (criterio 7).

### Non-Goals

* Endpoints de red (HTTP/socket) — stdio local exclusivamente (docs/SECURITY.md).
* Generación de respuestas con LLM dentro del server (esa es la capa del agente).
* Chat de múltiples turnos, historial, o stateful sessions: las tools son stateless salvo el índice.

## Proposed Solution

Un paquete `tepochcalli_mcp` instalado en `.tepochcalli/venv/` (ADR-004), lanzado por OpenCode vía `mcp.servers.tepochcalli-rag` (stdio). Usa el SDK oficial de MCP para Python; las handlers implementan la lógica fina de selección de contexto sobre la API de lectura de LanceDB del flow (spec-rag-engine).

## Detailed Design

### API / Interface Design — tool `search`

Contrato: `search(query: str, top_k: int = 5, path_filter: str | None = None)`

```jsonc
// request (arguments del tool call)
{ "query": "¿qué métricas usa el modelo X en pacientes pediátricos?",
  "top_k": 5, "path_filter": "00-Resources/lit-pediatría/**/*.pdf" }

// response (content[0].text = JSON canónico)
{ "query": "…", "took_ms": 142, "truncated": false,
  "results": [
    { "text": "…fragmento…",
      "source_path": "00-Resources/lit-pediatría/ruiz2024.pdf",
      "heading": "2.3 Medidas de resultado",
      "char_start": 4120, "char_end": 5088, "score": 0.87 } ] }
```

* `path_filter`: glob relativo a la raíz del vault; se aplica como pre-filtro en la query LanceDB (`WHERE source_path LIKE …` traducido de `*`→`%`).
* `score`: similitud normalizada [0,1] del híbrido ANN+FTS; orden descendente garantizado.
* Campos congelados por contrato (Hyrum, ADR-005): extensiones futuras solo aditivas/opcionales.

### Tool `index_refresh`

Contrato: `index_refresh()` — sin argumentos. Ejecuta un ciclo de actualización delta del flow (con lock de un solo proceso).

```jsonc
{ "scanned": 214, "indexed": 3, "skipped": 210,
  "elapsed_ms": 8200, "locked": false }
```

* `scanned`: archivos visitados en la pasada; `indexed`: (re)escritos al índice; `skipped`: memoizados/inalterados/excluidos; `elapsed_ms`: duración de la pasada.
* Delta grande (>~200 archivos o PDFs pesados) puede exceder 30s: el server responde al completar; el timeout del harness debe cubrir 120s (documentado en TRD) y el criterio 2 aplica a deltas típicos.

### Tool `add_source`

Contrato: `add_source(uri: str, subdir: str | None = None)` — convierte URL/archivo a Markdown (capacidad markitdown, spec-markitdown), escribe bajo `00-Resources/<subdir|_inbox>/`, luego invoca el ciclo de `index_refresh` internamente.

```jsonc
{ "ok": true, "written_to": "00-Resources/_inbox/paper-2026-03.md",
  "indexed": { "scanned": 215, "indexed": 1, "skipped": 214, "elapsed_ms": 2600 } }
```

* Validación en el borde: `subdir` normalizado, sin `..`, queda dentro de `00-Resources/`; `uri` acepta `http(s):`, `file:` (ver advertencia de seguridad).

### Manejo de errores (formato único)

Toda falla → tool result con `isError` y payload JSON canónico (nunca texto libre):

```jsonc
{ "error": { "code": "INDEX_EMPTY",
             "message": "El índice no existe; ejecute index_refresh().",
             "details": null } }
```

| Code | Significado | Acción sugerida del agente |
|---|---|---|
| `VALIDATION_ERROR` | argumentos inválidos (top_k>20, glob malformado, subdir fuera de 00-Resources) | reintentar corrigiendo args |
| `INDEX_EMPTY` | tabla `chunks` inexistente | invocar `index_refresh()` |
| `INDEX_STALE_MODEL` | dims/modelo del índice ≠ config actual | avisar usuario: requiere re-index (spec-embeddings) |
| `ENGINE_LOCKED` | refresh concurrente en curso | reintentar en segundos |
| `SOURCE_UNREACHABLE` | add_source no pudo fetch/convertir | sugerir descarga manual + `index_refresh()` |
| `INTERNAL` | inesperado (detalles al log, no al cliente) | reportar issue |

### Presupuesto de latencia (<500ms, criterio 3)

Punto de medición: desde que el server recibe `tools/call(search)` (marca en handler) hasta que serializa la respuesta completa — excluye arranque del proceso MCP (cold start del harness, amortizado por sesión) e incluye embed de la query.

| Etapa | Presupuesto p95 |
|---|---|
| Embed de query (MiniLM CPU, 1 frase) | ≤120ms |
| Búsqueda ANN+FTS (≤100k chunks) | ≤200ms |
| Ensamblado/truncado/JSON | ≤30ms |
| Margen IPC/stdio | ≤150ms |
| **Total** | **≤500ms** |

### Presupuesto de tokens (≤2000, criterio 4)

Diseño determinista en el server (no depende del modelo):

* Payload máximo devuelto por `search`: `top_k` efectivo = min(solicitado, 5 por default; tope duro 8) × chunk ≤1024 chars ≈ 5×~260 tokens ≈ **1300 tokens**.
* Overhead de citación por resultado ≈25 tokens (path+heading+offsets compactos) → +125 tokens.
* Techo duro: si la suma estimada (tokenizador aprox chars/4 para ES/EN) excede 1600, se descartan resultados de menor `score` y se marca `truncated: true` — deja ≥400 tokens de margen para la pregunta del usuario y la respuesta generada dentro de los 2000 totales.
* Fixtures de test assertan la cota con queries adversas (unicode, listas, PDFs con tablas).

### Carga de configuración

* El server lee `.tepochcalli/config/tepochcalli.toml` al arrancar: `[embedding] provider/model`, `[chunking] sizes`, `[search] top_k_default, max_chunk_chars`. Claves de API externas solo vía `{env:VAR}` o ese archivo (gitignored).
* Rutas derivadas de una única `TEPOCHCALLI_ROOT` (cwd del vault inyectado por `opencode.json` → `cwd`): `db/`, `flow/`, `models/`.

### Empaquetado en el venv

* Entrypoint console: `tepochcalli-mcp` (definido en el paquete `.tepochcalli/mcp/`, instalado editable/`uv sync`). `opencode.json` lo invoca como `["<root>/.tepochcalli/venv/bin/tepochcalli-mcp"]` con `cwd` = raíz del vault (spec-installer-wizard §merge de config).

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
* Fixtures de presupuesto: asserts de tokens ≤1600 payload y de `took_ms` <500 en CI con HW de referencia (metodología TRD).
* Golden answers: queries ES/EN sobre la muestra de `00-Resources/` (md+PDF) verificando que cada resultado cite `source_path` real y offsets reproducibles.

## Security Considerations

* Solo stdio local; sin binding de red (docs/SECURITY.md).
* `path_filter`/`subdir`: validación de ruta (path traversal → `VALIDATION_ERROR`); el server jamás escribe fuera de `00-Resources/` ni lee fuera del vault salvo `file:` explícito en `add_source` (riesgo documentado del canal markitdown).
* Errores `INTERNAL` nunca exponen stack traces al harness.

## Rollback / Monitoring

* El server es stateless: revertir = checkout de la versión anterior + `uv sync`. El índice sobrevive independientes de versiones.
* Métricas mínimas por tool-call (log local rotativo en flujo stderr del proceso, no persistente): `took_ms`, `results_n`, `truncated`, error codes.

## Open Questions

* ¿`add_source` debería deduplicar por hash de `uri` para no re-descargar lo mismo? (propuesta Phase 2: hash en `_inbox/.sources.json`)

## References

* MCP Python SDK — https://github.com/modelcontextprotocol/python-sdk
* OpenCode V2 MCP servers — https://opencode.ai/v2/docs/mcp-servers/
* ADR-005; specs/spec-rag-engine.md; specs/spec-markitdown.md
