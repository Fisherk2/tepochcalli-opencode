# SPEC — Tepochcalli

> Workspace distribuible de Obsidian potenciado con OpenCode V2 + motor RAG, para búsqueda
> semántica citada sobre notas y PDFs de investigación con coste mínimo de tokens LLM.
> Fuente de requisitos: [docs/BACKLOG.md](docs/BACKLOG.md) (fuente de verdad; todo cambio se registra en §8 y, si es decisión, exige ADR/enmienda).
> Este documento indexa las specs modulares (`specs/spec-*.md`) y los ADRs (`docs/adr/`).

## Objetivo

Investigadores y estudiantes obtienen, con un solo comando de instalación, un vault de
Obsidian donde OpenCode V2 responde preguntas con citas precisas a sus fuentes
(`00-resources/`), gracias al motor RAG CocoIndex + LanceDB expuesto por el servidor MCP
local `tepochcalli-rag`. Cuatro capas: Vault (usuario) → RAG Engine (procesamiento) →
MCP Server (comunicación) → OpenCode V2 (agente). Ver [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Criterios de aceptación (textuales, docs/BACKLOG.md)

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
| --- | --- | --- |
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
├── specs/                          # especificación modular
│   └── spec-*.md                   #   12 specs (motor, MCP, vault, embeddings, wizard… + 5 del payload)
├── docs/                           # BACKLOG.md (requisitos), ARCHITECTURE, PRD, TRD, APPFLOW…
│   └── adr/adr-NNN-*.md            #   8 ADRs Accepted 2026-10-21 + 3 Accepted 2026-11-03 + ADR-012 (2026-11-11) + ADR-013 (2026-11-13) + ADR-014/015 (Accepted 2026-11-19)
└── obsidian-workspace/             # PAYLOAD instalable (vault plantillado) → template/
    ├── 00-resources/ · 01-tasks/…05-outputs/ (bandejas del agente) · 10-templates/ · 10+ biblioteca personal
    ├── .opencode/{agents,commands,skills}/
    ├── .tepochcalli/               # runtime RAG (D2): flow/ mcp/ db/ models/ venv/ bin/ config/
    ├── AGENTS.md  opencode.json
    └── (wizard Rust lo materializa en el vault del usuario)
```

## Stack técnico (decisiones D1-D7, inmutables sin ADR nuevo)

| Componente | Decisión | ADR |
| --- | --- | --- |
| Motor RAG | **CocoIndex** (`pip install cocoindex`; flow `@coco.fn(memo=True)`; runner-up LEANN) | [ADR-001](docs/adr/adr-001-motor-rag-cocoindex.md) |
| Runtime dir | **`.tepochcalli/`** engine-neutral (flow/mcp/db/models/venv/bin/config) | [ADR-002](docs/adr/adr-002-lancedb-embebido.md) (db) + layout D2 |
| Vector store | **LanceDB embebido** (file-based, sin daemon/puerto) | [ADR-002](docs/adr/adr-002-lancedb-embebido.md) |
| Embeddings | **paraphrase-multilingual-MiniLM-L12-v2** (384d, ~470MB, CPU); upgrade bge-m3/LiteLLM; device explícito en wizard: [ADR-015](docs/adr/adr-015-dispositivo-inferencia-wizard.md) (Accepted 2026-11-19) | [ADR-006](docs/adr/adr-006-minilm-multilingue-default.md) |
| Selección de embedder (wizard) | **menú "Embedding provider"** con default preseleccionado; `presets.toml` como datos; modo `degraded` + `rag_status` (D7) | [ADR-007](docs/adr/adr-007-seleccion-embedder-instalacion.md) |
| Instalador | **TUI Rust**; canal **aprobado** `uvx tepochcalli` (rueda PyPI vía maturin `bindings = "bin"`): [ADR-014](docs/adr/adr-014-distribucion-uvx-pypi.md) (Accepted 2026-11-19) sustituye el canal de [ADR-013](docs/adr/adr-013-distribucion-cargo-binstall.md) y declara el retiro del backend de [ADR-003](docs/adr/adr-003-distribucion-cargo-dist.md) (no materializado, TD-51) | ADR-014 (canal) · ADR-003 (backend, en retiro) · ADR-013 (canal heredado) |
| Frontera agente↔motor | **MCP `tepochcalli-rag`**: `search`/`index_refresh`/`add_source`/`rag_status` + `convert_document`/`convert_base64`/`list_formats` (Phase 3.5); el conjunto de raíces del índice es solo `INDEXER_DIR` | [ADR-005](docs/adr/adr-005-mcp-ports-adapters.md), [ADR-007](docs/adr/adr-007-seleccion-embedder-instalacion.md), [ADR-009](docs/adr/adr-009-conversor-resumen-sin-cuerpo.md), [ADR-010](docs/adr/adr-010-indice-multi-raiz-cita-vault.md) |
| Conversor soporte | **markitdown** como librería **en proceso** en el venv (el server standalone `markitdown-mcp` se retira del payload) | specs/spec-markitdown.md, [ADR-011](docs/adr/adr-011-politica-dependencias-dos-librerias.md) |
| Deps Python | **uv + venv local** (`.tepochcalli/venv`; usuario sin Python en host) | [ADR-004](docs/adr/adr-004-uv-venv-aislado.md) |

Resumen de estilo de código: [docs/CODE_STYLE.md](docs/CODE_STYLE.md) (ruff+type hints Python,
rustfmt+clippy wizard, specs kebab, ADRs `adr-NNN-kebab`, prosa en español).

## Estrategia de testing

* **Unit por capa:** transformaciones del flow (puras, sin red); parsers de config; helpers de truncado/token-budget del MCP.
* **Contract tests MCP:** vault fixture → shape exacto de `search/index_refresh/add_source`, códigos de error, globs de `path_filter`.
* **Fixtures de performance (los 4 criterios numéricos):** delta <30s; `search` <500ms p95; payload ≤~1600 tokens/call (cota ≤2000 con overhead); stress sintético 10k notas + 1k PDFs (metodología en [docs/TRD.md](docs/TRD.md)).
* **Golden-vault e2e:** vault de muestra del wizard (1 md + 1 PDF en `00-resources/`) → consulta real → respuesta citada correcta.
* **Idempotencia del wizard:** `install` dos veces → sin duplicados en payload ni `opencode.json`.

## Boundaries

| Siempre (Always) | Preguntar antes (Ask first) | Nunca (Never) |
| --- | --- | --- |
| Respetar contratos D1-D7 o escribir ADR nuevo | Añadir dependencias al `pyproject.toml` pineado — **`maturin`/PyPI (toolchain de release) y `ratatui`/`crossterm` (TUI) ya fueron aprobadas por el dueño el 2026-11-19** ([ADR-014](docs/adr/adr-014-distribucion-uvx-pypi.md) §4.3); cualquier otra sigue exigiendo visto bueno | Commitear claves, `config/`, `db/`, `models/`, `venv/` |
| Specs antes que código; commits atómicos Convención | Cambiar top_k por default o tamaño de chunk | Modificar `docs/BACKLOG.md` sin registrar el cambio en §8 (y ADR/enmienda si es decisión), `obsidian-workspace/.opencode/` (agents/commands/skills), `README.md`, `LICENSE` |
| Validar entradas en el borde MCP (`add_source` rutas) | Añadir un nuevo MCP server al payload | Exponer el RAG por red (stdio local únicamente) |
| Citas estructuradas en toda respuesta RAG | Re-index strategy distinta de "swap=full" | Hacer que el instalador toque `.obsidian/` |

## Índice de specs

| Spec | Status | Alcance |
| --- | --- | --- |
| [specs/spec-rag-engine.md](specs/spec-rag-engine.md) | Approved; Amended 2026-11-02 (Phase 3.5; ADR-009/010/011 Accepted 2026-11-03) | Flujo CocoIndex: N raíces declaradas en `INDEXER_DIR`, extracción markitdown (8 formatos, sin Docling), Δ<30s de texto y documentos aparte, escala |
| [specs/spec-mcp-server.md](specs/spec-mcp-server.md) | Approved; Amended 2026-11-02 (Phase 3.5; ADR-009/010/011 Accepted 2026-11-03) | 7 contratos de tools, errores `E_*`, frontera B′, latencia/token budget, config |
| [specs/spec-vault-structure.md](specs/spec-vault-structure.md) | Approved; Amended 2026-11-02 (Phase 3.5; ADR-010 Accepted 2026-11-03) | Carpetas numeradas, layout `.tepochcalli/`, gitignore, no-interferencia, raíces indexables |
| [specs/spec-embeddings.md](specs/spec-embeddings.md) | Approved · **Enmienda 2026-11-18 (Accepted 2026-11-19) — flujo destino** | Modelo default, matriz local/externo, cache, swap+re-index |
| [specs/spec-installer-wizard.md](specs/spec-installer-wizard.md) | Approved (FTR Phase 3→4, 2026-10-28) · **Enmienda 2026-11-18 (Accepted 2026-11-19) — flujo destino** | TUI Rust, 8 fases atómicas, cargo-dist, flags, UX de fallo |
| [specs/spec-markitdown.md](specs/spec-markitdown.md) | Approved; Amended 2026-11-02 (Phase 3.5; ADR-009/010/011 Accepted 2026-11-03) | markitdown en proceso: 3 tools del conversor summary-only, frontera B′, fallback `anydoc`, seguridad |
| [specs/spec-agent-workflow.md](specs/spec-agent-workflow.md) | Proposed | 9 comandos + 5 agentes, AGENTS.md del vault, anexo auditoría skills |
| [specs/spec-payload-vault.md](specs/spec-payload-vault.md) | Approved (BLUEPRINT APPROVED 2026-11-09, freeze 40; materializado en Phase 5, amended 2026-11-09 — D-P5-2/T2/T8) · **Enmendada 2026-11-11 ([ADR-012](docs/adr/adr-012-formato-payload-revisado.md))** | spec padre: reglas de formato V2, blueprint del AGENTS.md del vault, testing ejecutable y decisiones Phase 4 |
| [specs/spec-payload-skills.md](specs/spec-payload-skills.md) | Approved (BLUEPRINT APPROVED 2026-11-09, freeze 40; materializado en Phase 5, amended 2026-11-09 — D-P5-2/T2/T8) · **Enmendada 2026-11-11 (41 skills, D-P5-1 SUPERSEDED)** · **Enmendada 2026-11-12 (39 reales tras los retiros `c815eb0` y `e785072`; tabla 9×4 y delegaciones regeneradas desde los cuerpos)** | Inventario 39 (`database-lookup/` y `writing-skills/` retiradas 2026-11-12) + tabla 9×4 vigente (§Enmienda E2) + muestras del instalador; tabla 9×4 Phase 4 y matriz 17 filas SUPERSEDED |
| [specs/spec-payload-permissions.md](specs/spec-payload-permissions.md) | Approved (BLUEPRINT APPROVED 2026-11-09, freeze 40; materializado en Phase 5, amended 2026-11-09 — D-P5-2/T2/T8) · **Enmendada 2026-11-11 (D-P4-2 SUPERSEDED)** | Bloques `permissions` V2 como diseño histórico + formato revisado (inline + global 313 reglas) |
| [specs/spec-payload-agents.md](specs/spec-payload-agents.md) | Approved (BLUEPRINT APPROVED 2026-11-09, freeze 40; materializado en Phase 5, amended 2026-11-09 — D-P5-2/T2/T8) · **Enmendada 2026-11-11 (permisos inline)** | 5 system prompts en inglés con el esqueleto de casa (≤60 líneas) |
| [specs/spec-payload-commands.md](specs/spec-payload-commands.md) | Approved (BLUEPRINT APPROVED 2026-11-09, freeze 40; materializado en Phase 5, amended 2026-11-09 — D-P5-2/T2/T8) | 9 cuerpos en inglés (≤35 líneas) + contrato de referencia español |

(Plantillas: [specs/spec-template.md](specs/spec-template.md), [docs/adr/adr-template.md](docs/adr/adr-template.md).)

> **Phase 3.5 cerrada (FTR 2026-11-03):** los ADR-009/010/011 pasan a *Accepted* y las cuatro
> specs enmendadas quedan **definitivas** (`spec-vault-structure` promovida a *Approved*). Phase 4
> (blueprint) quedó desbloqueada (hoy completada a nivel de checklist, ver abajo).
>
> **Phase 4 COMPLETADA (2026-11-09) — BLUEPRINT APPROVED concedido por congelamiento del dueño:**
> blueprint definitivo en 5 specs **Approved** (freeze 40 skills definitivas, `cf17f31`/`2e62e60`;
> matriz de 17 filas SUPERSEDED, objetivo <60 cumplido).
>
> **Phase 5 COMPLETADA (2026-11-09) — payload materializado, con la salvedad D-P5-10:** los 15
> artefactos de texto, las 40 skills (hash del árbol idéntico al baseline) y el `opencode.json` sin
> el array global de 313 reglas quedaron instalados y verificados por el gate estático y el install
> e2e. **La corrida D9 (methodology e2e de los 9 comandos) se difiere al QA de cierre de proyecto**
> — se entrega el runbook `tests/phase5-methodology-runbook.md` y la deuda queda como TD-31. Phase 6
> (aceptación E2E) queda habilitada.
>
> **Revisiones post-Phase 5 (2026-11-10/11, [ADR-012](docs/adr/adr-012-formato-payload-revisado.md)):**
> 9 commits (`baf2993`..`1c4a90b`) fijan el formato canónico ongoing — `AGENTS.md` del
> vault como guía genérica harness-agnóstica, permisos inline por agente + global 313
> reglas (D-P4-2/D-P5-4 SUPERSEDED), `00-resources/` + `10-templates/`, 41 skills
> (D-P5-1 SUPERSEDED). Las 4 specs del payload llevan enmienda 2026-11-11.
>
> **Formato canónico ongoing (2026-11-12, 12 commits `2072121..c815eb0`):** 9 comandos
> endurecidos (rubric fases 0-2; research Pre-Flight+multi-fuente; validate 4 fases;
> synthesize Pre-Flight+outline; cite Rn+gate EN; draft 3 insumos; review revA→B;
> transform A-G EN; update quirúrgico), `chilam.md` sin bandejas propias,
> `tepochcalli-mcp` con `INDEXER_DIR` genérico (retira `anydoc`), `database-lookup/`
> borrada (83 ficheros, cero refs; 40 skills). **PHASE 5 COMPLETADA 2026-11-12** con la
> salvedad D-P5-10 intacta (TD-31 diferida); **PHASE 6 (aceptación E2E) LISTA para
> planificarse** (runbook `tests/phase5-methodology-runbook.md`).
>
> **Evolución 2026-11-18 (/evolve sobre `docs/BACKLOG.md §2 «Wizard de instalación: flujo destino (2026-11-18)»`) — histórico:** ADR-014/015 nacieron **Proposed** (canal
> `uvx` único + device explícito en wizard), con enmiendas "Enmienda 2026-11-18 — flujo destino
> (entonces Proposed)" en `spec-installer-wizard.md` y `spec-embeddings.md`, y Phase 6.5 declarada
> no ejecutable en `docs/WORKFLOW.md` (ola D68). **FTR del dueño 2026-11-19:** ADR-014/015 **Accepted**, las dos
> enmiendas **Accepted**, versión alineada a `0.1.0` y Phase 6.5 **desbloqueada y después
> COMPLETADA** el mismo día (métricas y salvedades en WORKFLOW §Phase 6.5); el canal queda
> decidido, sin publicar nada.

## Log de decisiones

| ADR | Título | Status |
| --- | --- | --- |
| [ADR-001](docs/adr/adr-001-motor-rag-cocoindex.md) | Motor RAG CocoIndex (comparativa 5 candidatos) | Accepted 2026-10-21 |
| [ADR-002](docs/adr/adr-002-lancedb-embebido.md) | LanceDB embebido como almacén vectorial | Accepted 2026-10-21 |
| [ADR-003](docs/adr/adr-003-distribucion-cargo-dist.md) | Distribución con cargo-dist + GitHub Releases | Accepted 2026-10-21 |
| [ADR-004](docs/adr/adr-004-uv-venv-aislado.md) | uv + venv local de proyecto | Accepted 2026-10-21 |
| [ADR-005](docs/adr/adr-005-mcp-ports-adapters.md) | MCP como capa ports/adapters (`tepochcalli-rag`) | Accepted 2026-10-21 |
| [ADR-006](docs/adr/adr-006-minilm-multilingue-default.md) | MiniLM multilingüe como modelo default | Accepted 2026-10-21 |
| [ADR-007](docs/adr/adr-007-seleccion-embedder-instalacion.md) | Selección de embedder en instalación (menú D7.1-D7.4; reemplaza solo ADR-006 §4.1) | Accepted 2026-10-21 |
| [ADR-008](docs/adr/adr-008-transparencia-hardware-cambio-modelo.md) | Transparencia de hardware y swap atómico sin reinstalar (refina ADR-007 D7.1/D7.4) | Accepted 2026-10-21 |
| [ADR-009](docs/adr/adr-009-conversor-resumen-sin-cuerpo.md) | Conversor summary-only: 3 tools en `tepochcalli-rag`, markitdown en proceso, resumen de 5 claves (D28/D31/D36/D39/D66) | Accepted 2026-11-03 |
| [ADR-010](docs/adr/adr-010-indice-multi-raiz-cita-vault.md) | Índice multi-raíz declarado en `INDEXER_DIR` con `source_path` relativo al vault (D32/D41/D64/D65; rev. 2 2026-11-03) | Accepted 2026-11-03 |
| [ADR-011](docs/adr/adr-011-politica-dependencias-dos-librerias.md) | Política de dependencias: dos librerías (cocoindex + markitdown) y ledger de no-reinvención (D52/D63) | Accepted 2026-11-03 |
| [ADR-012](docs/adr/adr-012-formato-payload-revisado.md) | Formato revisado del payload: AGENTS.md genérico, permisos inline + global 313, minúsculas, 41 skills (supersede D-P4-2/D-P5-1/D-P5-4) | Accepted 2026-11-11 |
| [ADR-013](docs/adr/adr-013-distribucion-cargo-binstall.md) | Canal de instalación: `cargo binstall` recomendado, `shell`/`powershell` como fallback (reemplaza el canal de ADR-003, no su backend cargo-dist) | Accepted 2026-11-13 |
| [ADR-014](docs/adr/adr-014-distribucion-uvx-pypi.md) | Canal de distribución uvx + PyPI (maturin bindings=bin); sustituye el canal de ADR-013 y declara el retiro del backend de ADR-003; ADR-004 intacto | Accepted 2026-11-19 |
| [ADR-015](docs/adr/adr-015-dispositivo-inferencia-wizard.md) | Elección explícita de device en wizard y re-entrada; refina ADR-007/008 sin reabrir el rechazo de autoselección | Accepted 2026-11-19 |

## Referencias

* [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/PRD.md](docs/PRD.md) · [docs/TRD.md](docs/TRD.md) · [docs/APPFLOW.md](docs/APPFLOW.md)
* [docs/WORKFLOW.md](docs/WORKFLOW.md) — plan de fases Phase 0-6
* [docs/CODE_STYLE.md](docs/CODE_STYLE.md) · [docs/SECURITY.md](docs/SECURITY.md) · [docs/TECH_DEBT.md](docs/TECH_DEBT.md)
