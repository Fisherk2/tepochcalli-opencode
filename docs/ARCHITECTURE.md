# Architecture — Tepochcalli

> Índice ejecutivo de las decisiones de arquitectura. Cada decisión significativa está
> registrada como ADR en [`specs/adr/`](../specs/adr/) siguiendo el formato MADR.
> Requisitos: [docs/UH.md](UH.md) · Especificación: [SPEC.md](../SPEC.md)

## Sistema en una frase

Un vault de Obsidian distribuible donde el harness **OpenCode V2** obtiene respuestas citadas
sobre el material de investigación del usuario (`00-resources/`) consultando —vía **MCP
stdio local**— un índice vectorial **incremental** construido por **CocoIndex + LanceDB** con
embeddings **locales** (MiniLM multilingüe), entregado por un **wizard Rust** sin requerir
Python ni Node en el host.

## Diagrama de contenedores (C4 nivel 2)

```mermaid
graph TB
    subgraph USUARIO["Capa de Usuario — Vault Obsidian"]
        OB["Obsidian<br/>nota/PDF authoring"]
        RES["N raíces del vault<br/>00-resources/ por defecto"]
        WORK["01-tasks · 02-drafts · 03-citations<br/>trabajo del usuario"]
        VAG["AGENTS.md del vault<br/>guía genérica harness-agnóstica"]
    end

    subgraph AGENTE["Capa de Agente"]
        OC["OpenCode V2<br/>harness, comandos /rubric../update,<br/>agentes Itzamná..Tlacuilo"]
        CFG["opencode.json<br/>mcp.servers"]
    end

    subgraph MCP["Capa de Comunicación"]
        RAG["MCP server tepochcalli-rag<br/>7 tools: search · index_refresh() · add_source · rag_status<br/>convert_document · convert_base64 · list_formats<br/>stdio local, sin puerto"]
    end

    subgraph ENGINE["Capa de Procesamiento"]
        FLOW["CocoIndex flow multi-raíz<br/>.tepochcalli/flow/ — memoizado, Δ-only<br/>markitdown (8 formatos) · RecursiveSplitter · MiniLM"]
        DB[("LanceDB embebido<br/>.tepochcalli/db/<br/>ANN + FTS")]
        MODELS[".tepochcalli/models/<br/>cache SBERT/HF"]
        VENV[".tepochcalli/venv/ + bin/uv<br/>deps pineadas (ADR-004)"]
    end

    OB --- RES
    OC -->|tool call| RAG
    RAG --> FLOW
    RAG -->|lectura| DB
    FLOW -->|escritura Δ| DB
    FLOW --> MODELS
    RAG -->|add_source y convert_* escriben Markdown| RES
    VAG -.->|system prompt| OC
    CFG -.->|spawn stdio| RAG
    VENV --- FLOW
    RES --- FLOW
```

Regla de dependencias: el flujo va SIEMPRE usuario→agente→MCP→engine→storage. El harness no
importa CocoIndex; el motor no conoce OpenCode. Único punto de contacto: los contratos de
herramienta de [specs/spec-mcp-server.md](../specs/spec-mcp-server.md) (ADR-005).

## Diagrama de secuencia — consulta citada

```mermaid
sequenceDiagram
    actor U as Investigador (Obsidian)
    participant A as Agente (OpenCode V2)
    participant S as tepochcalli-rag (MCP stdio)
    participant F as CocoIndex flow
    participant D as LanceDB (db/)

    U->>U: escribe nota / añade PDF en una raíz del vault
    U->>A: "estado del arte sobre X" (+/research)
    A->>S: index_refresh()
    S->>F: ciclo delta multi-raíz (memo/update)
    F->>D: upsert solo de archivos nuevos/modificados
    S-->>A: {scanned, indexed, skipped, elapsed_ms, locked, roots} (Δ texto p95 <30s)
    A->>S: search(query, top_k=5, path_filter?)
    S->>D: embed query + ANN/FTS híbrido (<500ms)
    D-->>S: chunks + {source_path, heading, char_start, char_end, score, offsets_ref}
    S-->>A: JSON ≤~1600 tokens, truncated flag
    A->>A: genera respuesta citando source_path+heading
    A-->>U: respuesta con citas precisas a las raíces indexadas
```

## Flujo de ingesta externa (URL → índice)

```mermaid
sequenceDiagram
    actor U as Usuario
    participant A as Agente (OpenCode V2)
    participant S as tepochcalli-rag
    participant M as markitdown (en proceso)
    participant F as flow → db
    U->>A: "convierte este documento a mis fuentes"
    A->>S: convert_document(path, output_path?)
    S->>M: convert(Path) — biblioteca, sin server
    M-->>S: markdown (nunca viaja al wire)
    S-->>A: resumen de 5 claves {written_to, source_uri, bytes, chars, preview}
    S->>S: (o add_source: escribe en 00-resources/ + frontmatter de trazabilidad)
    A->>S: index_refresh()
    S->>F: ciclo delta
    F-->>S: {scanned, indexed, skipped, elapsed_ms, roots}
    A-->>U: confirmación con ruta citable
```

## Component inventory

| Componente | Capa | Ubicación | Spec/ADR |
| --- | --- | --- | --- |
| Vault numerado (00-resources, 01-tasks…) + `10-templates/` | Usuario | `obsidian-workspace/` (payload) | spec-vault-structure, [ADR-012](../specs/adr/adr-012-formato-payload-revisado.md) |
| AGENTS.md del vault (guía genérica harness-agnóstica, EN) | Usuario/Agente | `<vault>/AGENTS.md` | spec-agent-workflow, [ADR-012](../specs/adr/adr-012-formato-payload-revisado.md) |
| OpenCode V2 + agentes/comandos/skills | Agente | `<vault>/.opencode/` | spec-agent-workflow |
| `opencode.json` (`mcp.servers`) | Agente | `<vault>/opencode.json` | spec-markitdown §config |
| `tepochcalli-rag` (**7 tools**: `search`/`index_refresh()`/`add_source`/`rag_status` + `convert_document`/`convert_base64`/`list_formats` — Phase 3.5) | Comunicación | `.tepochcalli/mcp/tepochcalli_mcp/` — 4 tools entregadas en Phase 2 (T1-T8); 3 del conversor en Phase 3.5 (ADR-009) | spec-mcp-server, ADR-005, ADR-009, ADR-010 |
| `markitdown` (librería) | Comunicación/Procesamiento | venv del vault — **en proceso** en `convert.py` y en `parsers.py`; el server standalone `markitdown-mcp` queda **retirado del payload** (D29, ADR-011) | spec-markitdown, ADR-011 |
| **Paquete `tepochcalli_mcp` (Phase 2 + 3.5):** `server.py` (MCPServer stdio, registro de las **7 tools**, `CallToolResult` explícito — nunca `ToolError`), `tools/{search,index_refresh,add_source,rag_status,convert_document,convert_base64,list_formats}.py` (handlers + validación de borde), `errors.py` (taxonomía `E_*` + `internal_guard`), `budget.py` (estimador `chars/4 + 25`, techo 1600), `paths.py` (B′: rutas y raíces dentro del vault — D16/D31/D64), `summary.py` (resumen de 5 claves, ≤1400 chars), `formats.py` (catálogo sin OCR), `writer.py` (escritura atómica idempotente — D66), `embedder.py` (fábrica `local`/`litellm`/`none` — D15/D59), `convert.py` (markitdown en proceso — D-b), `__main__.py` (entrypoint `python -m tepochcalli_mcp` — D17) | Comunicación | `obsidian-workspace/.tepochcalli/mcp/tepochcalli_mcp/` | spec-mcp-server, ADR-005, ADR-009 |
| **Contract tests + e2e golden (Phase 2):** `tests/e2e/test_mcp_contract.py` (shapes en el wire, 5 `E_*`, instalación degradada, globs de `path_filter`), `tests/e2e/test_mcp_journey.py` (pregunta → tool-call → JSON citado), fixture grabada `tests/fixtures/golden_vault/` (md+PDF) | Verificación | repo `tests/e2e/`, `tests/fixtures/` | CP-C, CP-D, spec-mcp-server §Testing |
| **Soporte de tests y bench (Phase 2):** `tests/support/mcp_server.py` (ayudantes de arranque/env compartidos — residuo R4 pagado en T8), `tests/benchmarks/bench_search.py` (p95 <500 ms con n y método publicados — M2) | Verificación | repo `tests/support/`, `tests/benchmarks/` | T7, T8 |
| **Flow `tepochcalli_flow` (Phase 1, T2–T8; multi-raíz en Phase 3.5):** `app.py` (entrada CocoIndex, lock de proceso + refresh con stats), `source.py` (walk de **N raíces** —`00-resources/` por defecto— con skips tipados y dedup), `parsers.py` (md/txt en UTF-8 + **markitdown** para pdf/docx/pptx/xlsx/xls + RecursiveSplitter 1536/192 bytes), `models.py` (cache de modelos), `model_store.py` (snapshot local exigido), `ports.py` (contrato de lectura), `adapters/lancedb_reader.py` (ANN+FTS+RRF) | Procesamiento | `.tepochcalli/flow/tepochcalli_flow/` | spec-rag-engine, ADR-001, ADR-010, ADR-011 |
| **Dominio puro (sin I/O):** `citation.py` (metadatos de cita por chunk — `heading` nullable, `doc_kind`, `offsets_ref_for`), `config.py` (`tepochcalli.toml` con fallbacks a defaults) | Procesamiento | `.tepochcalli/flow/tepochcalli_flow/` | spec-rag-engine §Target, D13 |
| **Puerto `ChunkReader` (T9):** 6 campos congelados + `offsets_ref` derivado del `doc_kind` al leer, engine-free — contrato de lectura para la capa MCP | Procesamiento | `.tepochcalli/flow/tepochcalli_flow/ports.py` | spec-mcp-server, ADR-005 |
| **Adaptador de lectura (T9):** `adapters/lancedb_reader.py` (ANN+FTS híbrido con fusión RRF) + `verify.py` (verificador CLI de solo lectura, M4) | Procesamiento | `.tepochcalli/flow/tepochcalli_flow/adapters/`, `verify.py` | ADR-002, ADR-005 |
| Estado del engine (LMDB) — D14 | Procesamiento | `.tepochcalli/db/cocoindex/` | D14, spec-vault-structure |
| LanceDB (ANN+FTS) | Procesamiento | `.tepochcalli/db/` | ADR-002 |
| Embeddings MiniLM multilingüe | Procesamiento | `.tepochcalli/models/` | ADR-006, spec-embeddings |
| venv + uv bootstrap | Runtime | `.tepochcalli/venv/`, `bin/` | ADR-004 |
| `tepochcalli.toml` | Config | `.tepochcalli/config/` (gitignored) | spec-embeddings |
| **Suite Phase 1 (T2–T11):** `tests/unit/` + `tests/integration/` — 137 tests en T11, **164 al cierre de Phase 1 (2026-10-23)**; `bench_delta.py` en `tests/benchmarks/` (M1, p95 sobre 20 ciclos) | Verificación | repo `tests/{unit,integration,benchmarks}/` | WORKFLOW §Phase 1, TRD §6.2 |
| **Suite Phase 3.5 (T1–T16):** **670 passed + 3 `slow`**, cobertura **97 %** (gate 95 %); contract tests e2e de las 7 tools, negativos de B′, multi-raíz y documentos; `bench_delta.py` re-medido (Δ texto p95 **4 299 ms**, n=20 nearest-rank) | Verificación | repo `tests/` | WORKFLOW §Phase 3.5 |
| **CI Phase 1:** `phase1.yml` (ruff → suite → smoke Δ) | Verificación | `.github/workflows/phase1.yml` — **solo verificación local; nunca corrió en GitHub Actions (M6)** | T11, WORKFLOW §Phase 1 |
| Wizard TUI Rust + cargo-dist | Distribución | repo `crates/` (Phase 3) + Releases | ADR-003, spec-installer-wizard |
| **Payload materializado (Phase 5, 2026-11-09; formato revisado 2026-11-11; canónico 2026-11-12):** 15 artefactos de texto (5 agentes con permisos inline + 9 comandos + `AGENTS.md` genérico del vault) + 40 skills (`database-lookup/` retirada `c815eb0`; `ls` 2026-11-12 = 40 dirs) + global 313 reglas + scaffold `00-resources/`/`10-templates/`; la capa MCP no cambia | Usuario/Agente | `obsidian-workspace/` (payload instalable) | spec-payload-vault, spec-payload-{skills,permissions,agents,commands}, WORKFLOW §Phase 5, [ADR-012](../specs/adr/adr-012-formato-payload-revisado.md) |

## Engine components (hexagonal view)

Vista hexagonal del motor tal como quedó tras Phase 3.5: dominio puro en el centro, `ports.py`
como contrato de lectura, adapters de infraestructura alrededor y **N raíces por pasada**.
**Las flechas indican dirección de dependencia** (`importa` / `implementa`) — nunca al revés:
el dominio no importa infraestructura y `ports.py` no importa ningún motor (test de
arquitectura, `tests/unit/test_architecture.py`).

```mermaid
graph TB
    subgraph DOMAIN["Dominio — puro, sin I/O"]
        CIT["citation.py<br/>metadatos de cita por chunk — heading, doc_kind, offsets_ref_for"]
        CFG["config.py<br/>tepochcalli.toml + defaults"]
    end

    subgraph PORT["Puerto — contrato de lectura sin motor (T9)"]
        PRT["ports.py — ChunkReader / CitedChunk<br/>6 campos congelados, heading nullable"]
    end

    subgraph ADAPTERS["Adapters — infraestructura"]
        SRC["source.py<br/>walk de N raíces del vault con skips tipados y dedup"]
        PAR["parsers.py<br/>md/txt + markitdown (8 formatos) + RecursiveSplitter 1536/192 bytes"]
        APP["app.py<br/>flow CocoIndex multi-raíz — lock, refresh con stats"]
        MDL["models.py + model_store.py<br/>ChunkRow, RefreshReport, snapshot local"]
        LDR["adapters/lancedb_reader.py<br/>ANN+FTS híbrido con fusión RRF"]
        VER["verify.py<br/>verificador CLI de solo lectura — M4"]
    end

    DB[("LanceDB<br/>.tepochcalli/db/")]
    MCP2["tepochcalli-rag — capa MCP (7 tools)"]

    CIT --> CFG
    PRT --> CFG
    SRC --> CIT
    PAR --> CIT
    APP --> SRC
    APP --> PAR
    APP --> CIT
    APP --> CFG
    APP --> MDL
    APP --> DB
    MDL -.->|esquema de filas| DB
    LDR -.->|implementa| PRT
    LDR --> DB
    VER -->|referencias del puerto| PRT
    VER -->|usa el adaptador| LDR
    MCP2 -.->|consume| PRT
```

* **Write path (indexación):** `app` orquesta `source` (walk de N raíces) → `parsers` (extracto con markitdown + chunking, cita derivada en `citation`) → embedder → LanceDB — sin pasar por el puerto.
* **Read path (búsqueda citada):** el puerto `ChunkReader` lo implementa `lancedb_reader` y lo consumen `tepochcalli-rag` (las 7 tools desde Phase 3.5) y `verify` (CLI de desarrollo) — el único contrato que cruza capas (ADR-005).

## MCP layer components (Phase 3.5)

Detalle de la capa de comunicación tal como quedó tras Phase 3.5: el harness solo ve
JSON-RPC por stdio; cada handler construye el `CallToolResult` explícito con
`content[0].text` = JSON canónico (nunca `ToolError`, que metería texto libre — omen H4).
**Flechas = dirección de dependencia** (`importa` / `consume`), con la misma regla que el
diagrama hexagonal: `tepochcalli_mcp` importa el puerto `ChunkReader` y el flow; nunca al
revés, y el server **no** importa `cocoindex` ni `lancedb` (test de arquitectura).

```mermaid
graph TB
    subgraph HARNESS["Harness OpenCode V2 — opencode.json del payload"]
        OC["OpenCode V2<br/>spawn stdio del server"]
    end

    subgraph MCPL["Capa MCP — .tepochcalli/mcp/tepochcalli_mcp/"]
        SRV["server.py<br/>MCPServer stdio · registro 7 tools"]
        TS["tools/search.py"]
        TR["tools/index_refresh.py"]
        TA["tools/rag_status.py"]
        TAD["tools/add_source.py"]
        TCD["tools/convert_document.py"]
        TCB["tools/convert_base64.py"]
        TLF["tools/list_formats.py"]
        ERR["errors.py<br/>taxonomía E_* · internal_guard"]
        BUD["budget.py<br/>chars/4 + 25 · techo 1600"]
        PATHS["paths.py<br/>B′: rutas y raíces dentro del vault"]
        SUM["summary.py + writer.py<br/>5 claves · escritura atómica idempotente"]
        FMT["formats.py<br/>catálogo curado, sin OCR"]
        EMB["embedder.py<br/>local · litellm · none"]
        CONV["convert.py<br/>markitdown en proceso"]
    end

    subgraph ENGC["Capa de procesamiento — Phase 1"]
        PRT["ports.py<br/>ChunkReader / CitedChunk"]
        APP["app.py<br/>refresh con lock y stats"]
        DB[("LanceDB<br/>.tepochcalli/db/")]
    end

    RES["00-resources/"]

    OC -->|"stdio JSON-RPC"| SRV
    SRV --> TS
    SRV --> TR
    SRV --> TA
    SRV --> TAD
    SRV --> TCD
    SRV --> TCB
    SRV --> TLF
    SRV -.-> ERR
    TS --> BUD
    TS --> EMB
    TS --> PRT
    TR --> PATHS
    TR --> APP
    TA --> EMB
    TAD --> PATHS
    TAD --> CONV
    TAD --> APP
    TCD --> PATHS
    TCD --> CONV
    TCD --> SUM
    TCB --> PATHS
    TCB --> CONV
    TCB --> SUM
    TLF --> FMT
    CONV --> RES
    SUM --> RES
    PRT --> DB
    APP --> DB
```

* **Write path (`index_refresh`/`add_source`):** `app` (Phase 1) orquesta walk → parsers →
  embedder → LanceDB — la capa MCP solo lo invoca y serializa su `RefreshReport` (`+roots`).
* **Read path (`search`):** query → `embedder` + puerto `ChunkReader` → `budget` (truncado a
  1600) → JSON canónico; sin red y sin LLM.
* **Conversor (`convert_document`/`convert_base64`/`list_formats`):** `paths` valida la
  frontera B′ (entrada y salida dentro del vault) **antes** de tocar el disco; `convert`
  produce el Markdown en proceso; `writer` lo escribe de forma atómica e idempotente (D66) y
  `summary` devuelve **solo** las 5 claves — el artefacto nunca viaja por el wire (ADR-009).
* **`file:` (D16):** `paths.py` es la única puerta que decide qué `file:` entra — fuera del
  vault ⇒ `VALIDATION_ERROR` antes de que markitdown toque el disco.
* `markitdown` es una **librería en proceso** compartida por `add_source` y las 3 tools del
  conversor; el server standalone `markitdown-mcp` ya no existe en el payload (ADR-011).

## Decision Index

| ADR | Título | Status | Date |
| --- | --- | --- | --- |
| [ADR-001](../specs/adr/adr-001-motor-rag-cocoindex.md) | Motor RAG: CocoIndex (vs LEANN/LightRAG/RAG-Anything/PageIndex) | Accepted | 2026-10-21 |
| [ADR-002](../specs/adr/adr-002-lancedb-embebido.md) | LanceDB embebido (vs pgvector/Qdrant/ChromaDB/SQLite) | Accepted | 2026-10-21 |
| [ADR-003](../specs/adr/adr-003-distribucion-cargo-dist.md) | Distribución cargo-dist + GitHub Releases (no bunx) | Accepted | 2026-10-21 |
| [ADR-004](../specs/adr/adr-004-uv-venv-aislado.md) | uv + venv local de proyecto (usuario sin Python) | Accepted | 2026-10-21 |
| [ADR-005](../specs/adr/adr-005-mcp-ports-adapters.md) | MCP `tepochcalli-rag` como capa ports/adapters | Accepted | 2026-10-21 |
| [ADR-006](../specs/adr/adr-006-minilm-multilingue-default.md) | MiniLM multilingüe como embedding default (elección del modelo default; el comportamiento del wizard en §4.1 queda reemplazado por ADR-007) | Accepted | 2026-10-21 |
| [ADR-007](../specs/adr/adr-007-seleccion-embedder-instalacion.md) | Selección de embedder en instalación (menú D7.1-D7.4) | Accepted | 2026-10-21 |
| [ADR-008](../specs/adr/adr-008-transparencia-hardware-cambio-modelo.md) | Transparencia de hardware y swap atómico de modelo (refina ADR-007 capa UX) | Accepted | 2026-10-21 |
| [ADR-009](../specs/adr/adr-009-conversor-resumen-sin-cuerpo.md) | Conversor summary-only: resumen de 5 claves, markitdown en proceso, frontera B′ | Accepted | 2026-11-03 |
| [ADR-010](../specs/adr/adr-010-indice-multi-raiz-cita-vault.md) | Índice multi-raíz declarado en `INDEXER_DIR` + `source_path` relativo al vault (rev. 2 2026-11-03) | Accepted | 2026-11-03 |
| [ADR-011](../specs/adr/adr-011-politica-dependencias-dos-librerias.md) | Dos librerías (cocoindex + markitdown) y ledger de no-reinvención | Accepted | 2026-11-03 |
| [ADR-012](../specs/adr/adr-012-formato-payload-revisado.md) | Formato revisado del payload: AGENTS.md genérico, permisos inline + global 313, minúsculas, 41 skills | Accepted | 2026-11-11 |
| [ADR-013](../specs/adr/adr-013-distribucion-cargo-binstall.md) | Canal de instalación: `cargo binstall` recomendado, `shell`/`powershell` como fallback (reemplaza el canal de ADR-003) | Accepted | 2026-11-13 |
| [ADR-014](../specs/adr/adr-014-distribucion-uvx-pypi.md) | Canal de distribución uvx + PyPI (maturin bindings=bin); sustituye el canal de ADR-013 y declara el retiro del backend de ADR-003 | Proposed | 2026-11-18 |
| [ADR-015](../specs/adr/adr-015-dispositivo-inferencia-wizard.md) | Elección explícita de device en wizard y re-entrada (`cpu`/`cuda`/`cuda:N`); refina ADR-007/008 sin reabrir el rechazo de autoselección | Proposed | 2026-11-18 |

## Key decisions summary

1. **CocoIndex** (ADR-001) — incrementalismo memoizado, live-watch y cero LLM por índice: los tres requisitos que ningún otro candidato cumplía a la vez.
2. **LanceDB sin daemon** (ADR-002) — el índice es archivos bajo `.tepochcalli/db/`; Obsidian y la nube del usuario solo ven una carpeta más.
3. **stdio MCP = frontera** (ADR-005) — contratos `search/index_refresh/add_source` congelados; motor y almacén intercambiables sin tocar el harness.
4. **Distribución Rust one-liner + segundo paso** (ADR-013/003/004) — el binario se instala con `cargo binstall tepochcalli` (fallback sin toolchain: `curl | sh` / `install.ps1`) y el vault se configura con `tepochcalli install`: binstall no reenvía flags. El wizard hace bootstrap de `uv`, que a su vez instala un CPython gestionado: el investigador no instala Python ni Node.
5. **MiniLM local default** (ADR-006) — ES+EN, CPU, 8GB, $0; upgrades bge-m3/LiteLLM por config.
6. **Destino del wizard (ADR-014/015, Proposed 2026-11-18)** — canal único `uvx tepochcalli`, TUI full-screen con botones y device explícito en wizard/re-entrada; **PENDIENTE de FTR** (Phase 6.5 GATED en `docs/WORKFLOW.md`). Mientras no sean Accepted, el estado operativo sigue siendo ADR-013/003 (`cargo binstall` + cargo-dist) con dialoguer.

## Engine-migration contingency

Si ADR-001 se revisita (triggers en su §8): el payload del motor vive íntegramente en
`.tepochcalli/flow/`; los contratos MCP (ADR-005) permanecen. Rutas documentadas:
(a) mismo flow, otro target (pgvector/Qdrant/ChromaDB/SQLite — soportados por CocoIndex);
(b) motor nuevo (p.ej. LEANN vía `leann_mcp`): re-implementaría flow + adaptador de lectura,
conservando db schema lógico `{source_path, heading, char_start, char_end, text, vector}`;
(c) el directorio `.tepochcalli/` es engine-neutral precisamente para sobrevivir ese cambio.
Coste conocido: re-index completo y re-validación de los benchmarks <30s/<500ms/<2000 tokens.

## References

* [C4 model](https://c4model.com/) · [MADR](https://adr.github.io/) · OpenCode V2 docs (<https://opencode.ai/v2/docs>)
* Specs: [../specs/](../specs/) · Requisitos: [UH.md](UH.md)
