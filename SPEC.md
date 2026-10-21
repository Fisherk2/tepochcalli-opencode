# SPEC — Tepochcalli

> Workspace distribuible de Obsidian potenciado con OpenCode V2 + motor RAG, para búsqueda
> semántica citada sobre notas y PDFs de investigación con coste mínimo de tokens LLM.
> Fuente de requisitos: [docs/UH.md](docs/UH.md) (no se modifica; se especifica).
> Este documento indexa las specs modulares (`specs/spec-*.md`) y los ADRs (`specs/adr/`).

## Objetivo

Investigadores y estudiantes obtienen, con un solo comando de instalación, un vault de
Obsidian donde OpenCode V2 responde preguntas con citas precisas a sus fuentes
(`00-Resources/`), gracias al motor RAG CocoIndex + LanceDB expuesto por el servidor MCP
local `tepochcalli-rag`. Cuatro capas: Vault (usuario) → RAG Engine (procesamiento) →
MCP Server (comunicación) → OpenCode V2 (agente). Ver [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Criterios de aceptación (textuales, docs/UH.md)

El sistema se considera correctamente implementado cuando:

1. "El vault de Obsidian funciona normalmente sin interferencias"
2. "Los archivos nuevos se indexan automáticamente en menos de 30 segundos cuando Opencode invoca la función del MCP correspondiente"
3. "Las búsquedas semánticas devuelven resultados relevantes en menos de 500ms"
4. "El consumo de tokens por consulta es inferior a 2000 tokens (incluyendo contexto)"
5. "Las respuestas del agente incluyen citas precisas a las fuentes originales"
6. "El sistema puede manejar vaults de hasta 10,000 notas y 1,000 PDFs sin degradación de rendimiento"
7. "Pueda procesar distintos formatos de texto, si no, utilizar el convertidor Markdown para que pueda manipularse adecuadamente."

Cobertura: criterios 1-2-3-4-5-6-7 → [spec-rag-engine](specs/spec-rag-engine.md),
[spec-mcp-server](specs/spec-mcp-server.md), [spec-vault-structure](specs/spec-vault-structure.md),
[spec-markitdown](specs/spec-markitdown.md); verificación por fases en
[docs/WORKFLOW.md](docs/WORKFLOW.md) Phase 6.

## Comandos del workspace (metodología)

| Comando | Fase | Agente dueño |
|---|---|---|
| `/rubric` | Definición | Nezahualcóyotl |
| `/research` | Recolección | Pochteca |
| `/validate` | Evaluación crítica | Chilam |
| `/synthesize` | Análisis | Nezahualcóyotl |
| `/cite` | Gestión bibliográfica | Chilam |
| `/draft` | Redacción | Tlacuilo |
| `/review` | Refinamiento | Chilam |
| `/transform` | Diseminación | Tlacuilo |
| `/update` | Mantenimiento | Tlacuilo |

Comandos y agentes reales del vault viven en `obsidian-workspace/.opencode/` (documentados,
no modificados, en [spec-agent-workflow](specs/spec-agent-workflow.md)).

## Estructura del proyecto

```text
repo                                # este repositorio (producto + plantilla)
├── AGENTS.md                       # reglas para asistentes de IA (línea guía ≤200)
├── SPEC.md                         # este índice central
├── specs/                          # especificación modular + ADRs
│   ├── spec-*.md                   #   7 specs (motor, MCP, vault, embeddings, wizard…)
│   └── adr/adr-NNN-*.md            #   7 ADRs aceptados 2026-10-21
├── docs/                           # UH.md (requisitos), ARCHITECTURE, PRD, TRD, APPFLOW…
└── obsidian-workspace/             # PAYLOAD instalable (vault plantillado) → template/
    ├── 00-Resources/ · 01-tasks/…05-outputs/ (bandejas del agente) · 10+ biblioteca personal
    ├── .opencode/{agents,commands,skills}/
    ├── .tepochcalli/               # runtime RAG (D2): flow/ mcp/ db/ models/ venv/ bin/ config/
    ├── AGENTS.md  opencode.json
    └── (wizard Rust lo materializa en el vault del usuario)
```

## Stack técnico (decisiones D1-D7, inmutables sin ADR nuevo)

| Componente | Decisión | ADR |
|---|---|---|
| Motor RAG | **CocoIndex** (`pip install cocoindex`; flow `@coco.fn(memo=True)`; runner-up LEANN) | [ADR-001](specs/adr/adr-001-motor-rag-cocoindex.md) |
| Runtime dir | **`.tepochcalli/`** engine-neutral (flow/mcp/db/models/venv/bin/config) | [ADR-002](specs/adr/adr-002-lancedb-embebido.md) (db) + layout D2 |
| Vector store | **LanceDB embebido** (file-based, sin daemon/puerto) | [ADR-002](specs/adr/adr-002-lancedb-embebido.md) |
| Embeddings | **paraphrase-multilingual-MiniLM-L12-v2** (384d, ~470MB, CPU); upgrade bge-m3/LiteLLM | [ADR-006](specs/adr/adr-006-minilm-multilingue-default.md) |
| Selección de embedder (wizard) | **menú "Embedding provider"** con default preseleccionado; `presets.toml` como datos; modo `degraded` + `rag_status` (D7) | [ADR-007](specs/adr/adr-007-seleccion-embedder-instalacion.md) |
| Instalador | **TUI Rust + cargo-dist + GitHub Releases** (`curl|sh`, `cargo binstall`); NO bunx | [ADR-003](specs/adr/adr-003-distribucion-cargo-dist.md) |
| Frontera agente↔motor | **MCP `tepochcalli-rag`**: `search`/`index_refresh`/`add_source`/`rag_status` | [ADR-005](specs/adr/adr-005-mcp-ports-adapters.md), [ADR-007](specs/adr/adr-007-seleccion-embedder-instalacion.md) |
| Conversor soporte | **markitdown-mcp** (oficial, stdio local, mismo venv) | specs/spec-markitdown.md |
| Deps Python | **uv + venv local** (`.tepochcalli/venv`; usuario sin Python en host) | [ADR-004](specs/adr/adr-004-uv-venv-aislado.md) |

Resumen de estilo de código: [docs/CODE_STYLE.md](docs/CODE_STYLE.md) (ruff+type hints Python,
rustfmt+clippy wizard, specs kebab, ADRs `adr-NNN-kebab`, prosa en español).

## Estrategia de testing

* **Unit por capa:** transformaciones del flow (puras, sin red); parsers de config; helpers de truncado/token-budget del MCP.
* **Contract tests MCP:** vault fixture → shape exacto de `search/index_refresh/add_source`, códigos de error, globs de `path_filter`.
* **Fixtures de performance (los 4 criterios numéricos):** delta <30s; `search` <500ms p95; payload ≤~1600 tokens/call (cota ≤2000 con overhead); stress sintético 10k notas + 1k PDFs (metodología en [docs/TRD.md](docs/TRD.md)).
* **Golden-vault e2e:** vault de muestra del wizard (1 md + 1 PDF en `00-Resources/`) → consulta real → respuesta citada correcta.
* **Idempotencia del wizard:** `install` dos veces → sin duplicados en payload ni `opencode.json`.

## Boundaries

| Siempre (Always) | Preguntar antes (Ask first) | Nunca (Never) |
|---|---|---|
| Respetar contratos D1-D7 o escribir ADR nuevo | Añadir dependencias al `pyproject.toml` pineado | Commitear claves, `config/`, `db/`, `models/`, `venv/` |
| Specs antes que código; commits atómicos Convención | Cambiar top_k por default o tamaño de chunk | Modificar `docs/UH.md`, `obsidian-workspace/.opencode/` (agents/commands/skills), `README.md`, `LICENSE` |
| Validar entradas en el borde MCP (`add_source` rutas) | Añadir un nuevo MCP server al payload | Exponer el RAG por red (stdio local únicamente) |
| Citas estructuradas en toda respuesta RAG | Re-index strategy distinta de "swap=full" | Hacer que el instalador toque `.obsidian/` |

## Índice de specs

| Spec | Status | Alcance |
|---|---|---|
| [specs/spec-rag-engine.md](specs/spec-rag-engine.md) | Proposed | Flujo CocoIndex: fuentes, chunking, PDF/Docling, Δ<30s, escala |
| [specs/spec-mcp-server.md](specs/spec-mcp-server.md) | Proposed | Contratos de tools, errores, latencia/token budget, config |
| [specs/spec-vault-structure.md](specs/spec-vault-structure.md) | Proposed | Carpetas numeradas, layout `.tepochcalli/`, gitignore, no-interferencia |
| [specs/spec-embeddings.md](specs/spec-embeddings.md) | Proposed | Modelo default, matriz local/externo, cache, swap+re-index |
| [specs/spec-installer-wizard.md](specs/spec-installer-wizard.md) | Proposed | TUI Rust, 8 fases atómicas, cargo-dist, flags, UX de fallo |
| [specs/spec-markitdown.md](specs/spec-markitdown.md) | Proposed | markitdown-mcp: config V2, `convert_to_markdown`, fallback, seguridad |
| [specs/spec-agent-workflow.md](specs/spec-agent-workflow.md) | Proposed | 9 comandos + 5 agentes, AGENTS.md del vault, anexo auditoría skills |
| [specs/spec-payload-vault.md](specs/spec-payload-vault.md) | Proposed | Blueprint Phase 4 (diseño del agent workflow) — ejecución literal en Phase 5; gate Approved usuario |

(Plantillas: [specs/spec-template.md](specs/spec-template.md), [specs/adr/adr-template.md](specs/adr/adr-template.md).)

## Log de decisiones

| ADR | Título | Status |
|---|---|---|
| [ADR-001](specs/adr/adr-001-motor-rag-cocoindex.md) | Motor RAG CocoIndex (comparativa 5 candidatos) | Accepted 2026-10-21 |
| [ADR-002](specs/adr/adr-002-lancedb-embebido.md) | LanceDB embebido como almacén vectorial | Accepted 2026-10-21 |
| [ADR-003](specs/adr/adr-003-distribucion-cargo-dist.md) | Distribución con cargo-dist + GitHub Releases | Accepted 2026-10-21 |
| [ADR-004](specs/adr/adr-004-uv-venv-aislado.md) | uv + venv local de proyecto | Accepted 2026-10-21 |
| [ADR-005](specs/adr/adr-005-mcp-ports-adapters.md) | MCP como capa ports/adapters (`tepochcalli-rag`) | Accepted 2026-10-21 |
| [ADR-006](specs/adr/adr-006-minilm-multilingue-default.md) | MiniLM multilingüe como modelo default | Accepted 2026-10-21 |
| [ADR-007](specs/adr/adr-007-seleccion-embedder-instalacion.md) | Selección de embedder en instalación (menú D7.1-D7.4; reemplaza solo ADR-006 §4.1) | Accepted 2026-10-21 |
| [ADR-008](specs/adr/adr-008-transparencia-hardware-cambio-modelo.md) | Transparencia de hardware y swap atómico sin reinstalar (refina ADR-007 D7.1/D7.4) | Accepted 2026-10-21 |

## Referencias

* [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/PRD.md](docs/PRD.md) · [docs/TRD.md](docs/TRD.md) · [docs/APPFLOW.md](docs/APPFLOW.md)
* [docs/WORKFLOW.md](docs/WORKFLOW.md) — plan de fases Phase 0-5
* [docs/CODE_STYLE.md](docs/CODE_STYLE.md) · [docs/SECURITY.md](docs/SECURITY.md) · [docs/TECH_DEBT.md](docs/TECH_DEBT.md)
