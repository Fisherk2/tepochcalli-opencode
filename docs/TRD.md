# Technical Requirements Document — Tepochcalli v1 (MVP)
**Date:** 2026-10-21 | **Author:** Arquitecto (entrevista /spec) | **Status:** Approved (alineado a docs/UH.md + ADRs)

## 1. Reference Architecture

Arquitectura hexagonal por capas con frontera única MCP (ADR-005). Detalle y diagramas:
[docs/ARCHITECTURE.md](ARCHITECTURE.md). Resumen de dependencias:

* `obsidian-workspace` (payload de datos/prompt) → sin dependencias de código.
* OpenCode V2 (harness) → solo `mcp.servers` en `opencode.json`.
* `tepochcalli-rag` (adapter de lectura/refresh/ingesta) → CocoIndex flow (adapter de
  escritura) → LanceDB (persistencia). Ninguna flecha inversa.
* Wizard Rust (distribución) → orquesta uv/venv/model/flow/config; no es runtime.

## 2. Matriz de plataformas soportadas

| SO | Arquis | Notas |
|---|---|---|
| Linux | x86_64, aarch64 | primary (distro-agnostic: binarios estáticos de uv/wizard; torch CPU wheel) |
| macOS | arm64 (Apple Silicon), x86_64 | rutas estándar Obsidian; quarantine por Gatekeeper → documentado en wizard UX |
| Windows | x86_64 | `install.ps1`; venv layout `Scripts\` — el merge de opencode.json usa rutas por plataforma |

Requisitos por plataforma: Obsidian instalado; OpenCode V2 en PATH (fase 1 del wizard solo
detecta e instruye, no instala).

## 3. Pisos de recursos (hardware mínimo)

| Recurso | Mínimo | Recomendado |
|---|---|---|
| RAM | 8 GB | 16 GB (bge-m3/local grande) |
| CPU | 4 núcleos (AVX2 deseable para MiniLM) | 8+ |
| Disco para `.tepochcalli/` | 3-4 GB libres | +0.5 GB por cada 1k PDFs (~150MB por 100k chunks + margen LanceDB) |
| Red | Internet en primer arranque (wheels uv + modelo 470MB + payload release) | — (luego `--offline` posible) |

Desglose v1: venv 1-2GB (torch CPU), modelo ~470MB, LanceDB inicial ~50MB muestra.

## 4. Versiones pineadas (plan de pin; valores concretos en Phase 1)

| Componente | Plan | Fijado en |
|---|---|---|
| CPython | 3.12.x gestionado por uv (`uv python pin 3.12`) | `.tepochcalli/` (marker uv) |
| uv | latest estable al construir release (binario en `.tepochcalli/bin/`) | wizard lock de release |
| cocoindex | `cocoindex[lancedb] ~= 0.x` — pin exacto al cerrar Phase 1, bump solo con suite verde | `.tepochcalli/pyproject.toml` + `uv.lock` |
| sentence-transformers | `>=3,<4` con modelo `paraphrase-multilingual-MiniLM-L12-v2` (revisión pin en HF) | pyproject + `models/` |
| docling | serie 2.x CPU, sin extra GPU | pyproject |
| markitdown-mcp | oficial pypi, mismo venv | pyproject |
| lancedb | vía extra `[lancedb]` de cocoindex (no pinear aparte → evitar divergencia de versiones) | uv.lock |
| OpenCode V2 | `>=` la versión mínima que soporta `mcp.servers` forma usada (ver §5) | detección wizard fase 1 |
| tepochcalli (wizard) | semver propio; release por tag `v*` cargo-dist | GitHub Releases |

Regla: ningún bump entra sin los benches §6 verdes (gate de docs/WORKFLOW.md).

## 5. Notas de schema de config MCP (OpenCode V2)

Estructura usada por el wizard (fuente: https://opencode.ai/v2/docs/mcp-servers/):

```jsonc
{ "mcp": { "servers": {
    "<nombre>": {
      "type": "local",                 // stdio local — único soportado por diseño (sin remote)
      "command": ["<argv...>"],        // array; p.ej. [".tepochcalli/venv/bin/tepochcalli-mcp"]
      "cwd": ".",                      // relativo a la raíz del vault = cwd de opencode
      "environment": { "VAR": "{env:VAR}" }, // sustitución de secretos sin commitearlos
      "disabled": false                // permite apagar RAG sin borrar la entrada
    } } } }
```

* El wizard **fusiona** estas entradas conservando servers previos del usuario (fase 8,
  spec-installer-wizard) y hace backup `.bak` atómico.
* `tepochcalli-rag` y `markitdown` corren ambos bajo el venv del vault (ADR-004): el mismo
  `uv sync` los instala; sin `uvx` en el default (razón offline en spec-markitdown).

## 6. Metodología de performance (criterios numéricos de UH.md)

Referencia de medición: **VM limpia por plataforma**, CPU-only, 8GB, SSD; corpus = golden vault
(muestra) para humo + **corpus sintético** 10k notas `.md` (1-8KB, ES/EN mix) + 1k PDFs
(5-40 páginas, generado plantilla→PDF) para stress. Instrumentación: timestamps `monotonic_ms`
dentro de las handlers del server MCP (punto de medición = tool-call recibido→respuesta
serializada; definición en spec-mcp-server §latencia).

| Criterio | Protocolo de test | Pass |
|---|---|---|
| 2. Δ indexación <30s | Corridas ×20: tocar/crear 1-50 archivos md en `00-Resources/`, luego `index_refresh()`; registrar `elapsed_ms` | p95 < 30000ms; PDFs grandes excluidos y reportados aparte |
| 3. Búsqueda <500ms | 100 queries muestreadas del corpus 10k/1k, `search(top_k=5)`, tras índice estable | p95 < 500ms en HW mínimo |
| 4. ≤2000 tokens/consulta | Fixture adversa (unicode, tablas, listas largas): estimador chars/4 sobre payload `search` + overhead cita + query del usuario; validar contra tokenizador real del harness en e2e | payload ≤1600 tokens garantizado por server + e2e total <2000 |
| 6. Escala 10k/1k sin degradación | Bench delta tras stress: latencia búsqueda y refresh en corpus lleno vs 10% | sin regresión >2× entre tamaños; índices ANN/FTS rebuild < presupuesto |

Relevancia de criterios no numéricos: 1 (no-interferencia) → checklist e2e de
spec-vault-structure §Testing; 5 (citas) → golden answers con asserts de `source_path`/
`heading`/offsets reproducibles; 7 (formatos) → matriz de conversión markitdown fixtures.

## 7. Requisitos no funcionales adicionales

* **Privacidad:** sin egress en runtime default (embeddings locales; solo el agente usa su LLM).
* **Portabilidad:** borrar `.tepochcalli/{venv,db,models,bin}` = desinstalar sin dejar rastros;
  los fuentes del vault intactos (spec-vault-structure).
* **Observabilidad local:** logs de instalación fuera del vault (XDG/LOCALAPPDATA); métricas por
  tool-call en stderr del proceso MCP (spec-mcp-server §rollback/monitoring).
* **Seguridad:** íntegramente en [docs/SECURITY.md](SECURITY.md) (stdio-only, markitdown
  file-read, claves por env).

## 8. Dependencias de construcción (dev)

* Rust: toolchain estable + cargo-dist para release; clippy/rustfmt (docs/CODE_STYLE.md).
* Python 3.12 + uv para desarrollo del flow/MCP (tests con venv de CI, fixture vault en repo de tests).
* CI de release por tag `v*` (ADR-003); CI de PR: unit+contract+benches de humo (sin stress completo).
