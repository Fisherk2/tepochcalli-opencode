# Spec: Estructura del vault y aislamiento del runtime

* **Status:** Proposed
* **Date:** 2026-10-21
* **Author:** Arquitecto (entrevista /spec)
* **Reviewers:** Product Owner (usuario)
* **Traceability:** docs/UH.md (convención de carpetas, flujo de datos), ADR-002 (db embebida), ADR-004 (venv local), specs/spec-rag-engine.md, specs/spec-installer-wizard.md, specs/spec-agent-workflow.md (mapa comandos→bandejas D9.2); capa **D9** (zonas de propiedad) confirmada por el usuario vía question tool el 2026-10-21 — sin ADR nuevo, por decisión explícita del usuario (spec-only)

## Summary

Define la organización canónica del vault distribuible: carpetas numeradas de primer nivel visibles para Obsidian, directorios ocultos con prefijo punto (`.opencode/` para el harness, `.tepochcalli/` como runtime engine-neutral del RAG), y las reglas de no-interferencia que mantienen a Obsidian "sin percibir" al sistema. `00-Resources/` es el único árbol indexable, con anidamiento libre por parte del usuario.

## Problem / Motivation

Un vault de Obsidian es una carpeta que el usuario edita visualmente, sincroniza por git/nube y abre con plugins. Si los artefactos del motor (índices, entorno Python, servidor MCP) aparecen en la vista de archivos o bloquean escrituras, el producto destruye la herramienta que pretende mejorar.

> Como investigador, quiero instalar capacidad RAG en mi vault sin que Obsidian muestre basura del sistema, sin plugins invasivos y sin romper mi sincronización por git.

## Goals and Non-Goals

### Goals

* Convención de carpetas numeradas clara y soportada por el scaffold existente (`obsidian-workspace/`).
* Layout completo de `.tepochcalli/` (D2) documentado y con estrategia gitignore.
* Reglas de no-interferencia observables (criterio 1) y testeables.
* `00-Resources/` con subdirección libre y autodetección recursiva por el motor.

### Non-Goals

* Gestionar el contenido de `.obsidian/` (propiedad del usuario; nunca se toca).
* Indexar las bandejas del agente (`01-tasks/`…`05-outputs/`) o la biblioteca personal del usuario en v1 (puede evaluarse en /plan futuro).
* Redefinir los agentes/comandos del harness (spec-agent-workflow los documenta; no se modifican).

## Proposed Solution

Tres zonas de propiedad + una zona administrativa (D9.1, decisión confirmada del usuario 2026-10-21):

* **Entrada del usuario** — `00-Resources/`: la ÚNICA carpeta donde el usuario deposita material; única fuente de indexación; el agente escribe ahí solo vía `add_source` bajo petición explícita del usuario (regla existente, intacta).
* **Bandejas del agente** (`01-…-05-…`) — espacio de trabajo del agent workflow: bandejas de salida de los 9 comandos (mapa en specs/spec-agent-workflow.md §Mapa de comandos→bandejas). Semántica de caché: el usuario puede LEER, EXTRAER (copiar/mover hacia sus propias carpetas) y BORRAR (seguro: es regenerable); NO debe depositar archivos nuevos ni editar en sitio (no-contaminación: archivos sueltos rompen las convenciones del agent workflow).
* **Biblioteca personal** (`10+`/`20+`/`30+`, carpetas creadas por el usuario) — organización personal de los resultados extraídos; NO indexada en v1 (si un artefacto final debe ser consultable, el usuario lo copia a `00-Resources/`).
* **Zona de runtime** (prefijo punto: `.tepochcalli/`, `.opencode/`, `.obsidian/`) — la administran el wizard y el propio sistema; ignorada por Obsidian por convención de carpetas ocultas y excluida de git por artefactos regenerables.

## Detailed Design

### Árbol canónico del vault distribuible

```text
<mivault>/                          # raíz del vault (usuario)
├── 00-Resources/                   # ENTRADA del usuario: ÚNICA fuente de indexación (anidamiento libre)
│   └── ...                         #   p.ej. lit-pediatría/, datasets/, papers/*.pdf
├── 01-tasks/                       # bandeja del agente — Nezahualcóyotl (/rubric, /synthesize) — no indexada v1
│   └── research/                   #   sub-bandeja de Pochteca (única escritura suya permitida, D9.3)
├── 02-drafts/                      # bandeja del agente — Tlacuilo (/draft, /update) — no indexados v1
├── 03-citations/                   # bandeja del agente — Chilam (/cite) — no indexados v1
├── 04-review/                      # bandeja del agente — Chilam (/validate, /review) — NUEVA (D9.2)
├── 05-outputs/                     # bandeja del agente — Tlacuilo (/transform) — NUEVA (D9.2)
├── 10-*/ 20-*/ 30-*/               # biblioteca personal (carpetas del usuario; NO indexadas v1)
├── .obsidian/                      # configuración Obsidian — intocable
├── .opencode/                      # harness: agents/, commands/, skills/ (existente)
├── .tepochcalli/                   # runtime RAG (D2) — ver siguiente sección
├── AGENTS.md                       # system prompt del vault (regla MCP-first)
└── opencode.json                   # configuración OpenCode V2 (mcp.servers)
```

Nota de convención: el nombre canónico de la fuente indexable es `00-Resources/` (este set de specs lo usa en todo momento). El scaffold actual del repo aparece como `00-resources/` (minúsculas); **Action Item para /plan**: alinear el scaffold del template al nombre canónico o declarar el alias en el wizard, para evitar dos ortografías entre especificación y payload (Obsidian enlaza rutas sensible a mayúsculas según SO). Además, el scaffold TAMPOCO contiene `04-review/` ni `05-outputs/` (bandejas nuevas de D9.2): **Action Item para /plan (Phase 5, ejecución)** — crear ambas carpetas en el template con sus dueños de la tabla §Mapa de propiedad.

### Mapa de propiedad y acciones permitidas (D9.1)

| Carpeta | Dueño | Usuario puede | Agente puede |
|---|---|---|---|
| `00-Resources/` | usuario (entrada única indexable) | leer · extraer · borrar · **depositar** · editar (anidamiento libre) | leer (vía `search` preferente); escribir SOLO por `add_source` con petición explícita |
| `01-tasks/` · `02-drafts/` · `03-citations/` · `04-review/` · `05-outputs/` (bandejas del agente) | agente por comando (mapa D9.2 en specs/spec-agent-workflow.md) | leer · extraer · **borrar** (semántica de caché: regenerable) — NO depositar ni editar en sitio | escribir únicamente en su bandeja asignada; advertir ante archivos ajenos (no-contaminación) |
| `10+`/`20+`/`30+` (biblioteca personal) | usuario | todo: leer · extraer · borrar · depositar · editar | solo lectura si el usuario lo pide; NUNCA escribe ahí (no indexada v1) |
| `.obsidian/` · `.opencode/` · `.tepochcalli/` (zona de runtime) | Obsidian / harness / wizard | no tocar (fuera del flujo diario) | `.tepochcalli/` solo el wizard; los agentes jamás (regla 4 de spec-agent-workflow) |

### Layout de `.tepochcalli/` (D2)

```text
<vault>/.tepochcalli/         # runtime RAG — nombre engine-neutral, sobrevive a migraciones de motor
├── flow/                      # definición del pipeline CocoIndex + estado del engine
├── mcp/                       # fuente del servidor tepochcalli-rag (paquete tepochcalli_mcp)
├── db/                        # LanceDB embebido (tepochcalli.lance, tabla chunks) — ADR-002
├── models/                    # cache de modelos de embeddings (SENTENCE_TRANSFORMERS_HOME/HF_HOME)
├── venv/                      # entorno Python aislado creado por uv — ADR-004
├── bin/                       # binario uv bootstrappeado por el wizard — ADR-003/004
├── config/                    # tepochcalli.toml (proveedor/modelo embeddings, chunk sizes,
│                              #   claves de embedders externos) — NUNCA se commit-ear
└── pyproject.toml             # deps pineadas: cocoindex[lancedb], sentence-transformers,
                               #   docling, markitdown-mcp (+ uv.lock)
```

### Estrategia gitignore

| Ruta | ¿Commit? | Razón |
|---|---|---|
| `.tepochcalli/venv/`, `bin/`, `db/`, `models/` | ❌ | Artefactos regenerables, pesados, platform-dependent |
| `.tepochcalli/config/` | ❌ | Puede contener claves API — nunca al repo ni al vault privado compartido (docs/SECURITY.md) |
| `.tepochcalli/flow/`, `mcp/`, `pyproject.toml`, `uv.lock` | ✅ | Son **código fuente** versionado: el vault distribuido los instala; auditable |
| `00-Resources/` | ✅ (usuario decide) | Contenido del investigador; el .gitignore template no lo fuerza |
| `.obsidian/` | ⚠️ | Costumbre del usuario; el wizard no opina |

El template de `.gitignore` del vault distribuido marca: `.tepochcalli/venv/`, `.tepochcalli/bin/`, `.tepochcalli/db/`, `.tepochcalli/models/`, `.tepochcalli/config/`.

### Reglas de no-interferencia con Obsidian (criterio 1)

1. **Todo el runtime bajo punto-prefijo**: Obsidian no lista carpetas `.*` en su explorador.
2. **Sin plugins ni JS en `.obsidian/`**: cero escritura en la config de Obsidian.
3. **Sin procesos residentes**: ni daemon, ni cron, ni watch de filesystem persistente; la detección de delta ocurre cuando OpenCode invoca `index_refresh()`/`add_source` (modelado en spec-rag-engine).
4. **Sin puertos escuchados** (ADR-002/005): verificable en tests con `ss -ltn` antes/después.
5. **Escrituras atómicas dentro de `.tepochcalli/`**: el motor nunca toca archivos bajo `00-Resources/` (solo `add_source` escribe ahí, explícitamente por petición del usuario y dentro de la convención).
6. **Compatibilidad de sync**: los artefactos ignorados por git no generan diffs de sincronización ruidosos.
7. **Bandejas = espacio de trabajo del agente (no-contaminación)**: que el usuario deposite archivos dentro de las bandejas 01-05 NO es una configuración soportada (D9.1) — el agente asume las bandejas como suyas y debe ADVERTIR si encuentra archivos ajenos (podrían consumirse por error en el pipeline; regla replicada en spec-agent-workflow §AGENTS del vault). El usuario interactúa con las bandejas solo leyendo, extrayendo o borrando.

### `00-Resources/`: anidamiento libre + autodetección

* El usuario crea cualquier subárbol (`papers/2026/`, `datasets/raw/*.csv`); el source `localfs` del flow recurre y aplica whitelist de extensiones (spec-rag-engine §Fuentes) — no existe una lista de "rutas conocidas" que haya que mantener.
* El wizard deja placeholders de muestra (1 Markdown + 1 PDF) para el golden-vault test (SPEC.md §Testing).
* Subcarpetas punto (`00-Resources/.privado/`) quedan excluidas — regla consistente con no-interferencia.

## Alternatives Considered

* **Runtime en `~/Library/Application Support/` (fuera del vault):** *rechazado:* rompe portabilidad "vault = todo" y el aislamiento multi-vault; además D2 decidió `.tepochcalli/`.
* **Carpeta visible `_tepochcalli/`:** *rechazado:* ensucia la vista de Obsidian y contradice el criterio 1.
* **Nombre del directorio por motor (`.cocoindex/`):** *rechazado en D2:* engine-neutral `.tepochcalli/` permite migrar motor (ADR-001 revisit) sin reestructurar el vault.

## Trade-offs

* ✅ **Pros:** Un solo lugar para todo el runtime; borrable sin daño; invisible para Obsidian.
* ⚠️ **Cons:** El vault pesa GB extra (venv+modelos — presupuestado en TRD); usuarios que copian el vault entre SO distintos deben re-ejecutar el wizard (venv no portable, ADR-004).
* ⚖️ **Neutral:** Aparece una distinción conceptual "zona de usuario / zona de runtime" que documentarse en el AGENTS.md del vault.

## Testing Strategy

* Test de criterio 1: abrir vault con `00-Resources` populado + motor corriendo refresh; assert: `.obsidian/` byte-idéntico, 0 procesos escuchando puertos nuevos, 0 archivos `.`-prefijados listados en la API de workspace de Obsidian.
* Test de anidamiento: fixture con 3 niveles arbitrarios de subcarpetas → todos los elegibles indexados, todos los excluidos ausentes.
* Test de idempotencia de instalación (wizard): dos corridas → sin duplicados ni diffs de gitignore.

## Security Considerations

* `config/` gitignored: única justificación técnica de por qué las claves pueden vivir en el vault local; documentado también en docs/SECURITY.md.
* No se commit-ea `db/`: evitar filtración de contenido indexado al compartir el vault.

## Rollback / Monitoring

* Desinstalación = borrar `.tepochcalli/` completo (el vault queda en estado pre-instalación; ver spec-installer-wizard §rollback del wizard).
* Integridad: `index_refresh` reporta `skipped` por archivos ilegibles (>100MB, corruptos) — señal temprana de desorden en `00-Resources/`.

## Open Questions

* ¿`01-tasks/…` debería volverse indexable opcional vía config en v2? (fuera de scope v1)
* Decisión de alias `00-resources`/`00-Resources` pendiente en /plan (ver Nota de convención).

## References

* docs/UH.md — sección organización del vault
* ADR-002 (db), ADR-004 (venv), specs/spec-rag-engine.md (source rules), specs/spec-installer-wizard.md (payload)
