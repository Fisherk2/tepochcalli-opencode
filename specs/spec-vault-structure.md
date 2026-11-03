# Spec: Estructura del vault y aislamiento del runtime

* **Status:** Approved; Amended 2026-11-02 (Phase 3.5; ADR-010 Accepted 2026-11-03) — `00-Resources/` pasa de «única raíz indexable» a **valor por omisión del índice**.
* **Date:** 2026-10-21
* **Author:** Arquitecto (entrevista /spec)
* **Reviewers:** Product Owner (usuario)
* **Traceability:** docs/UH.md (convención de carpetas, flujo de datos), ADR-002 (db embebida), ADR-004 (venv local), ADR-010 (índice multi-raíz y cita vault-relativa), specs/spec-rag-engine.md, specs/spec-installer-wizard.md, specs/spec-agent-workflow.md (mapa comandos→bandejas D9.2); capa **D9** (zonas de propiedad) confirmada por el usuario vía question tool el 2026-10-21 — sin ADR nuevo, por decisión explícita del usuario (spec-only)

## Summary

Define la organización canónica del vault distribuible: carpetas numeradas de primer nivel visibles para Obsidian, directorios ocultos con prefijo punto (`.opencode/` para el harness, `.tepochcalli/` como runtime engine-neutral del RAG), y las reglas de no-interferencia que mantienen a Obsidian "sin percibir" al sistema. `00-Resources/` es la **carpeta de entrada del usuario** y el **valor por omisión de `INDEXER_DIR`** (las raíces que el harness declara), con anidamiento libre; cualquier otro directorio del vault puede indexarse pidiéndolo en la llamada o declarándolo en esa env (ADR-010).

## Problem / Motivation

Un vault de Obsidian es una carpeta que el usuario edita visualmente, sincroniza por git/nube y abre con plugins. Si los artefactos del motor (índices, entorno Python, servidor MCP) aparecen en la vista de archivos o bloquean escrituras, el producto destruye la herramienta que pretende mejorar.

> Como investigador, quiero instalar capacidad RAG en mi vault sin que Obsidian muestre basura del sistema, sin plugins invasivos y sin romper mi sincronización por git.

## Goals and Non-Goals

### Goals

* Convención de carpetas numeradas clara y soportada por el scaffold existente (`obsidian-workspace/`).
* Layout completo de `.tepochcalli/` (D2) documentado y con estrategia gitignore.
* Reglas de no-interferencia observables (criterio 1) y testeables.
* `00-Resources/` con subdirección libre, recursiva y **default de `INDEXER_DIR`** (raíz por
  omisión del índice); cualquier directorio del vault indexable cuando la llamada lo pide o la env
  lo declara (ADR-010).

### Non-Goals

* Gestionar el contenido de `.obsidian/` (propiedad del usuario; nunca se toca).
* Indexar **por omisión** las bandejas del agente (`01-tasks/`…`05-outputs/`) o la biblioteca personal:
  no es el caso normal; sí son indexables si el usuario pasa la raíz explícitamente (ADR-010 §7, D9.1).
* Redefinir los agentes/comandos del harness (spec-agent-workflow los documenta; no se modifican).

## Proposed Solution

Tres zonas de propiedad + una zona administrativa (D9.1, decisión confirmada del usuario 2026-10-21; alcance del índice replanteado por ADR-010):

* **Entrada del usuario** — `00-Resources/`: la carpeta donde el usuario deposita material nuevo y el **destino por omisión de `add_source`**; es también la **raíz por omisión del índice**. El agente escribe ahí solo vía `add_source` bajo petición explícita del usuario (regla existente, intacta).
* **Bandejas del agente** (`01-…-05-…`): espacio de trabajo del agent workflow — bandejas de salida de los 9 comandos (mapa en specs/spec-agent-workflow.md §Mapa de comandos→bandejas). Semántica de caché: el usuario puede LEER, EXTRAER (copiar/mover hacia sus propias carpetas) y BORRAR (seguro: es regenerable); NO debe depositar archivos nuevos ni editar en sitio (no-contaminación: archivos sueltos rompen las convenciones del agent workflow).
* **Biblioteca personal** (`10+`/`20+`/`30+`, carpetas creadas por el usuario): organización personal de los resultados extraídos; no indexada por omisión. Si el usuario quiere consultarla, pasa su ruta como raíz (ADR-010) — ya no hace falta copiar el material a `00-Resources/`.
* **Zona de runtime** (prefijo punto: `.tepochcalli/`, `.opencode/`, `.obsidian/`): la administran el wizard y el propio sistema; ignorada por Obsidian por convención de carpetas ocultas y excluida de git por artefactos regenerables. **Nunca se indexa**: la exclusión `**/.*` poda el subárbol entero (ver §Raíces del índice).

## Detailed Design

### Árbol canónico del vault distribuible

```text
<mivault>/                          # raíz del vault (usuario)
├── 00-Resources/                   # ENTRADA del usuario: raíz POR OMISIÓN del índice (anidamiento libre)
│   └── ...                         #   p.ej. lit-pediatría/, datasets/, papers/*.pdf
├── 01-tasks/                       # bandeja del agente — Nezahualcóyotl (/rubric, /synthesize) — no indexada por omisión
│   └── research/                   #   sub-bandeja de Pochteca (única escritura suya permitida, D9.3)
├── 02-drafts/                      # bandeja del agente — Tlacuilo (/draft, /update) — no indexada por omisión
├── 03-citations/                   # bandeja del agente — Chilam (/cite) — no indexada por omisión
├── 04-review/                      # bandeja del agente — Chilam (/validate, /review) — NUEVA (D9.2)
├── 05-outputs/                     # bandeja del agente — Tlacuilo (/transform) — NUEVA (D9.2)
├── 10-*/ 20-*/ 30-*/               # biblioteca personal (carpetas del usuario; no indexadas por omisión)
├── .obsidian/                      # configuración Obsidian — intocable; NUNCA indexada (poda `**/.*`)
├── .opencode/                      # harness: agents/, commands/, skills/ (existente); nunca indexado
├── .tepochcalli/                   # runtime RAG (D2); nunca indexado — ver siguiente sección
├── AGENTS.md                       # system prompt del vault (regla MCP-first)
└── opencode.json                   # configuración OpenCode V2 (mcp.servers)
```

Nota de convención: el nombre canónico de la carpeta de entrada —y raíz por omisión del índice— es `00-Resources/` (este set de specs lo usa en todo momento). El scaffold actual del repo aparece como `00-resources/` (minúsculas); **Action Item para /plan**: alinear el scaffold del template al nombre canónico o declarar el alias en el wizard, para evitar dos ortografías entre especificación y payload (Obsidian enlaza rutas sensible a mayúsculas según SO). Además, el scaffold TAMPOCO contiene `04-review/` ni `05-outputs/` (bandejas nuevas de D9.2): **Action Item para /plan (Phase 5, ejecución)** — crear ambas carpetas en el template con sus dueños de la tabla §Mapa de propiedad.

### Mapa de propiedad y acciones permitidas (D9.1)

| Carpeta | Dueño | Usuario puede | Agente puede |
| --- | --- | --- | --- |
| `00-Resources/` | usuario (entrada; raíz por omisión del índice) | leer · extraer · borrar · **depositar** · editar (anidamiento libre) | leer (vía `search` preferente); escribir SOLO por `add_source` o por las tools del conversor, con petición explícita |
| `01-tasks/` · `02-drafts/` · `03-citations/` · `04-review/` · `05-outputs/` (bandejas del agente) | agente por comando (mapa D9.2 en specs/spec-agent-workflow.md) | leer · extraer · **borrar** (semántica de caché: regenerable) — NO depositar ni editar en sitio | escribir únicamente en su bandeja asignada; advertir ante archivos ajenos (no-contaminación) |
| `10+`/`20+`/`30+` (biblioteca personal) | usuario | todo: leer · extraer · borrar · depositar · editar | solo lectura si el usuario lo pide; NUNCA escribe ahí (indexable solo si el usuario la pide) |
| `.obsidian/` · `.opencode/` · `.tepochcalli/` (zona de runtime) | Obsidian / harness / wizard | no tocar (fuera del flujo diario) | `.tepochcalli/` solo el wizard; los agentes jamás (regla 4 de spec-agent-workflow) |

### Layout de `.tepochcalli/` (D2)

```text
<vault>/.tepochcalli/         # runtime RAG — nombre engine-neutral, sobrevive a migraciones de motor
├── flow/                      # definición del pipeline CocoIndex + config del engine — código fuente (el estado derivado vive en db/cocoindex/, D14)
├── mcp/                       # fuente del servidor tepochcalli-rag (paquete tepochcalli_mcp)
├── db/                        # LanceDB embebido (tepochcalli.lance, tabla chunks) — ADR-002
├── models/                    # cache de modelos de embeddings (SENTENCE_TRANSFORMERS_HOME/HF_HOME)
├── venv/                      # entorno Python aislado creado por uv — ADR-004
├── bin/                       # binario uv bootstrappeado por el wizard — ADR-003/004
├── config/                    # tepochcalli.toml (proveedor/modelo embeddings, chunk sizes,
│                              #   claves de embedders externos) — NUNCA se commit-ear
└── pyproject.toml             # deps pineadas: cocoindex[lancedb,sentence-transformers],
                               #   markitdown[docx,pptx,xlsx,xls,pdf] (+ uv.lock) — ADR-011
```

### Estrategia gitignore

| Ruta | ¿Commit? | Razón |
| --- | --- | --- |
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
5. **Escrituras atómicas dentro de `.tepochcalli/`**: el motor nunca escribe en el vault indexado (solo `add_source` y las tools del conversor escriben en `00-Resources/`, explícitamente por petición del usuario y dentro de la convención).
6. **Compatibilidad de sync**: los artefactos ignorados por git no generan diffs de sincronización ruidosos.
7. **Bandejas = espacio de trabajo del agente (no-contaminación)**: que el usuario deposite archivos dentro de las bandejas 01-05 NO es una configuración soportada (D9.1) — el agente asume las bandejas como suyas y debe ADVERTIR si encuentra archivos ajenos (podrían consumirse por error en el pipeline; regla replicada en spec-agent-workflow §AGENTS del vault). El usuario interactúa con las bandejas solo leyendo, extrayendo o borrando.

### `00-Resources/`: anidamiento libre + autodetección

* El usuario crea cualquier subárbol (`papers/2026/`, `datasets/raw/*.csv`); el source `localfs` del flow recurre y aplica la whitelist de 8 extensiones (spec-rag-engine §Fuentes) — no existe una lista de "rutas conocidas" que haya que mantener.
* El wizard deja placeholders de muestra (1 Markdown + 1 PDF) para el golden-vault test (SPEC.md §Testing).
* Subcarpetas punto (`00-Resources/.privado/`) quedan excluidas — regla consistente con no-interferencia.
* Es la raíz **por omisión**, no la única: ver la sección siguiente.

### Raíces del índice: el conjunto declarado en `INDEXER_DIR` (D32, ADR-010)

* **(a) Convención + default.** `00-Resources/` es donde el usuario deja material nuevo y donde `add_source` escribe por defecto. Es también el **valor por omisión de `INDEXER_DIR`** — la variable de entorno del harness (`opencode.json` → `environment`) que declara el conjunto de raíces de `index_refresh()` (`roots == ["00-Resources"]` cuando no se declara otra cosa): compatibilidad con los agentes y prompts ya escritos. El usuario puede declarar otras raíces (`"00-Resources,03-citations"`, multi-valor por comas) sin editar el toml ni re-ejecutar el wizard (ADR-010 §4.1, enmendado 2026-11-03).
* **(b) Cualquier directorio indexable, solo por configuración.** El conjunto lo declara el usuario en `INDEXER_DIR`: el MCP **no puede añadir ni quitar raíces** — el argumento `directories` se retiró el 2026-11-03 y **no tiene efecto**: el SDK valida por firma y descarta las claves desconocidas, así que la tool indexa el conjunto configurado (no es un error, es la garantía de que el wire no cambia el conjunto), porque una pasada declara el estado completo del índice y un subconjunto purgaría las demás raíces (ADR-010 §4.1 rev. 2). Tampoco hay `index.roots` en `tepochcalli.toml` ni paso por el wizard. Cada raíz la valida el borde MCP (dentro del vault, existe, directorio o fichero soportado) y la cita resultante es **vault-relativa** (`materiales/a.pdf`, `00-Resources/nota.md`) para que dos raíces homónimas no colisionen (D41).
* **(c) Los directorios con prefijo punto nunca se indexan.** No es una lista nueva: la exclusión `**/.*` (más `**/.git/**`) hace que el conector **pode el subárbol** antes de descender (`is_dir_included` antes de encolar) ⇒ indexar la raíz del vault no recorre `.tepochcalli/venv/`, `.obsidian/` ni `.trash/` (ADR-010 §4.9).
* **(d) Anidamiento libre y recursivo.** Dentro de una raíz no hay límite de profundidad ni de niveles; una raíz puede ser además un **fichero suelto**.
* **(e) Fail-fast atómico.** El conjunto completo se valida **antes** de caminar ninguna raíz: si una falla, no se indexa ninguna y el error nombra la raíz mala; un índice parcial que nadie pidió es peor que un reintento (ADR-010 §4.1).
* **Relación con D9.1 (sin contradicción).** D9.1 decía «solo `00-Resources/` es indexable»; esa convención se **replantea**: la responsabilidad pasa del nivel de la carpeta al **conjunto declarado en `INDEXER_DIR`**. `00-Resources/` sigue siendo el default y el destino de `add_source` (que exige tenerla declarada); las bandejas `01-…05-…` siguen siendo bandejas del agente (indexables si el usuario lo declara, no es el caso normal), y la biblioteca personal deja de exigir copiar el material a `00-Resources/` para consultarlo.

## Alternatives Considered

* **Runtime en `~/Library/Application Support/` (fuera del vault):** *rechazado:* rompe portabilidad "vault = todo" y el aislamiento multi-vault; además D2 decidió `.tepochcalli/`.
* **Carpeta visible `_tepochcalli/`:** *rechazado:* ensucia la vista de Obsidian y contradice el criterio 1.
* **Nombre del directorio por motor (`.cocoindex/`):** *rechazado en D2:* engine-neutral `.tepochcalli/` permite migrar motor (ADR-001 revisit) sin reestructurar el vault.

## Trade-offs

* ✅ **Pros:** Un solo lugar para todo el runtime; borrable sin daño; invisible para Obsidian.
* ⚠️ **Cons:** El vault pesa GB extra (venv+modelos — presupuestado en TRD); usuarios que copian el vault entre SO distintos deben re-ejecutar el wizard (venv no portable, ADR-004). El índice puede mezclar carpetas de distinta naturaleza: la responsabilidad de elegir bien las raíces pasa al agente (ADR-010 §6).
* ⚖️ **Neutral:** Aparece una distinción conceptual "zona de usuario / zona de runtime" que documentarse en el AGENTS.md del vault.

## Testing Strategy

* Test de criterio 1: abrir vault con `00-Resources` populado + motor corriendo refresh; assert: `.obsidian/` byte-idéntico, 0 procesos escuchando puertos nuevos, 0 archivos `.`-prefijados listados en la API de workspace de Obsidian.
* Test de anidamiento: fixture con 3 niveles arbitrarios de subcarpetas → todos los elegibles indexados, todos los excluidos ausentes.
* Test multi-raíz: con `INDEXER_DIR="materiales,documentos"`, `index_refresh()` indexa ambos con
  `source_path` vault-relativo; una raíz que es el vault **no** produce filas bajo
  `.tepochcalli/`, `.obsidian/` ni `.trash/` (la exclusión poda el subárbol); pasar `directories`
  ⇒ se indexa el conjunto configurado, **sin error** (el SDK descarta la clave desconocida).
* Test de idempotencia de instalación (wizard): dos corridas → sin duplicados ni diffs de gitignore.

## Security Considerations

* `config/` gitignored: única justificación técnica de por qué las claves pueden vivir en el vault local; documentado también en docs/SECURITY.md.
* No se commit-ea `db/`: evitar filtración de contenido indexado al compartir el vault.

## Rollback / Monitoring

* Desinstalación = borrar `.tepochcalli/` completo (el vault queda en estado pre-instalación; ver spec-installer-wizard §rollback del wizard).
* Integridad: `index_refresh` reporta `skipped` por archivos ilegibles (>100MB, corruptos) — señal temprana de desorden en el material indexado.

## Open Questions

* Decisión de alias `00-resources`/`00-Resources` pendiente en /plan (ver Nota de convención).

## References

* docs/UH.md — sección organización del vault
* ADR-002 (db), ADR-004 (venv), ADR-010 (multi-raíz y cita vault-relativa), specs/spec-rag-engine.md (source rules), specs/spec-installer-wizard.md (payload)
