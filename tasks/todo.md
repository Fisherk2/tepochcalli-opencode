# TODO — Phase 4 (blueprint del payload del vault)

> **Fecha:** 2026-11-04 · **Orquestador:** Moctezuma · **Plan:** [tasks/plan.md](plan.md)
> **Verificación de esta fase:** SOLO linters (markdownlint + mermaid render + greps). **La suite de pruebas no se ejecuta.**
> **Prohibido escribir en `obsidian-workspace/**`** (Phase 4 es diseño puro).

## Baseline del gate de linters (T0)

Medido en HEAD `d04e5ac` (2026-11-04) por el orquestador.

| Métrica | Valor en HEAD (2026-11-04) | Nota |
| --- | --- | --- |
| Errores de `just md-lint` (`docs specs AGENTS.md SPEC.md`) | **1** — `docs/WORKFLOW.md:166` (MD005) | baseline D12: el gate **no** está verde; el criterio es **cero errores nuevos** |
| Bloques mermaid en `docs/` + `specs/` | **13** — ARCHITECTURE 5 · UH 2 · APPFLOW 2 · spec-rag-engine 1 · spec-markitdown 1 · spec-installer-wizard 1 · spec-agent-workflow 1 | render obligatorio de los nuevos |
| `wc -l specs/*.md` | `spec-payload-vault.md` = **528** (rojo: umbral <500); resto <500 | dividir en 4 specs (D-P4-4) → T2/T5/T6 |
| `git status --short` | solo `?? agent_example.md` · `?? command_example.md` | los dos ejemplos de la guía (D-P4-8) quedan untracked |

---

## Leyenda

- `[ ]` pendiente · `[~]` en curso · `[x]` hecho y verificado · `[!]` bloqueado (motivo en la línea)
- Cada calpulli se cierra con su checkpoint. **No se avanza al siguiente checkpoint en rojo.**

---

## Ola 1 — Fundamentos (paralelo: T1 ‖ T2)

### [x] T0 — Baseline del gate de linters

- Subagente: `developer-tooling-engineer` · Skills: `bash-defensive-patterns`, `context-engineering` · Tools: shell, npx
- Salida: 4 números (md-lint, mermaid, `wc -l`, `git status`) reportados al orquestador
- [x] `just md-lint` ejecutado y recuento reportado
- [x] Bloques mermaid contados por fichero
- [x] `wc -l specs/*.md` con los 4 objetivos marcados
- [x] `git status --short` vacío (salvo los dos ejemplos untracked de D-P4-8)
- Deps: — · Verificación: números reportados

### [x] T1 — Reglas de formato OpenCode V2 (re-verificadas) + vocabulario de acciones

- Subagente: `developer-tooling-engineer` · Skills: `opencode`, `source-driven-development`, `find-docs`
- Tools: `context7`, `gitmcp`, `vercel-grep`
- Fichero: `specs/spec-payload-vault.md` (§Reglas de formato)
- [x] Cada regla con URL oficial + versión `v2.1.2` + fecha 2026-11-04
- [x] Tabla del vocabulario de acciones V2; las acciones de casa (`todowrite`, `lsp`, `question`) **se conservan** (las docs admiten acciones de plugin); lo prohibido es `permission:` singular + los 7 campos legacy
- [x] Discrepancia `agents.mdx` vs `permissions.mdx` resuelta a favor de la **lista**, citada
- [x] Checklist de no-regresión de frontmatter (7 campos legacy + `permission:` singular + `subagent` en comandos)
- [x] **Guía de formato del repo citada como canónica** (D-P4-8): `agent_example.md` y `command_example.md` (raíz, **sin commitear**) — solo por ruta, sin copiar su contenido
- [x] **Regla de idioma (D-P4-6)**: payload (`agents/*.md`, `commands/*.md`, `AGENTS.md` del vault) en **inglés**; repo en español — con la lista de marcadores del español para el chequeo y la excepción de los nombres propios
- Hallazgo: `doom_loop` **no** es acción oficial en v2.1.2 («`doom_loop` and `lsp` are not current V2 Core permission actions»); se marca `casa`/`no` en la tabla, sin falso citation
- Deps: T0 · Verificación: grep de URLs + md-lint sin errores nuevos + revisión del orquestador

### [x] T2 — Inventario real + matriz de conflictos 1:1

- Subagentes (secuencial): `codebase-archaeologist` → `knowledge-synthesizer`
- Skills: `codebase-memory`, `context-engineering`, `documentation-and-adrs` · Tools: `codebase-memory-mcp`, `vercel-grep`, shell
- Fichero: NUEVO `specs/spec-payload-skills.md`
- [x] Recuento con comando + fecha: **209** skills · **170** agentes · **9** comandos
- [x] 0 skills inventadas (grep 1:1 contra el `ls`) · 0 huérfanas (112 presentes sin citar, cubiertas por la fila 15)
- [x] 209/209 clasificadas (34+21+5 CONSERVAR/CONSOLIDAR · 37 RETIRAR · 0 INSTALAR-GAP · 112 barrido)
- [x] Gaps (Jupyter, R, Graphviz/PlantUML, LaTeX manuscrito) declarados sin inventar nombres
- [x] `tepochcalli-mcp` (fila 17) y TD-22/OfficeCLI coherentes con `docs/TECH_DEBT.md` (frontera v1 vs 0.2.0)
- [x] **Muestras inventariadas (D-P4-7)**: son artefactos de instalación (`installer.rs:46-58`), `00-Resources/` está vacío; objetivo `example.md`/`example.pdf`; cuerpo y PDF en español a regenerar; caja `01-Tasks/` vs `01-tasks/` anotada
- [x] Recuento **derivado**: base estricta **60** (falla `<60` por 0/1); corte de 10 remnants → 50, flagged como D-P4-10 (owner/FTR), no aplicado
- [x] Fichero <500 líneas (**182**)

### 🚦 Checkpoint CP-A — fin de T1+T2

- [x] Reglas de formato citadas (URL + versión + fecha)
- [x] Inventario 1:1 verificado (209/170/9)
- [x] 0 skills inventadas
- [~] Las 4 specs objetivo <500 líneas → `spec-payload-skills.md` 182 ✔; `spec-payload-vault.md` **585** (baja a <500 cuando T6 mueva los cuerpos de comando; ver nota D-P4-9)
- [x] md-lint sin errores nuevos vs baseline

---

## Ola 2 — Tabla y permisos (paralelo: T3 ‖ T4)

### [ ] T3 — Tabla de invocación por comando (9×4)

- Subagente: `workflow-architect` · Skills: `api-and-interface-design`, `opencode`, `context-engineering`
- Tools: `context7`, `codebase-memory-mcp`, `gitmcp`
- Fichero: `specs/spec-payload-skills.md`
- [ ] 9 filas × 4 columnas
- [ ] Cada skill citada existe (0 huérfanas); `⟵G` solo donde la matriz consolidó
- [ ] Herramientas nativas con vocabulario V2
- [ ] MCPs: solo las 7 de `tepochcalli-rag`; las 3 del conversor asignadas; `anydoc` = fallback **disabled**
- [ ] `excel`/`jupyter` disabled → GAP declarado (no tools usables)
- [ ] Subagentes permitidos = **ninguno** en las 9 filas
- [ ] `officecli` no citado como skill ni MCP
- Deps: T2 · Verificación: 7 tools de `server.py` contrastados (0 diferencias) + grep de skills + md-lint

### [ ] T4 — Permisos de los 5 agentes + decisión del array global

- Subagente: `security-architect` · Skills: `security-and-hardening`, `design-patterns`, `opencode`
- Tools: `context7`, `gitmcp`
- Fichero: `specs/spec-payload-vault.md` (§Blueprint de permisos + §Nota de fusión)
- [ ] 5 YAML en la **forma de la guía**: `permissions` como lista con `action:`/`resource:`/`effect:` en líneas propias (no el mapa en línea del blueprint actual), con `todowrite`/`lsp`/`question` conservadas, sin `permission:` singular y sin campos legacy
- [ ] last-match-wins: reglas amplias primero, excepciones al final (ej. Nezahualcóyotl: `01-tasks/research/** deny` **último**)
- [ ] Superficies: Pochteca `01-tasks/research/**` · Nezahualcóyotl `01-tasks/` (sin research) · Chilam `03-citations/`+`04-review/` · Tlacuilo deny-list (`02-drafts/`, `05-outputs/`, 10+ a petición) · Itzamná sin edit/subagent/shell
- [ ] **D-P4-2 registrada**: el array global de 313 reglas se elimina en Phase 5 → permisos SOLO en los `.md`
- [ ] Frontmatter: `description` **entrecomillado** con patrón «Name - Role» (`"Pochteca - The Explorer"`), `mode: primary`, sin `model`; `default_agent` → `itzamna`
- [ ] Divergencia con la guía documentada: la guía usa `subagent * allow` + deny por nombre; el blueprint mantiene `subagent * deny` para los 5 (catálogo inerte, D9)
- [ ] Riesgo D-P4-3 (tools MCP sin regla por agente) anotado para §Trade-offs
- Deps: T1, T3 · Verificación: YAML parseable + simulación last-match-wins (≥3 reglas/agente) + grep legacy = 0 + md-lint

### 🚦 Checkpoint CP-B — fin de T3+T4

- [ ] 7 tools del servidor MCP == columna MCP de la tabla
- [ ] Toda skill citada existe
- [ ] 0 campos legacy, 0 `todowrite`
- [ ] YAMLs parsean y la simulación de última-coincidencia coincide con lo esperado
- [ ] md-lint sin errores nuevos vs baseline

---

## Ola 3 — Contenido congelado (paralelo: T5 ‖ T6)

### [ ] T5 — Los 5 system prompts (verbatim)

- Subagente: `prompt-engineer` · Skills: `context-engineering`, `obsidian-markdown`, `opencode`
- Tools: `context7`, `codebase-memory-mcp`
- Fichero: NUEVO `specs/spec-payload-agents.md`
- [ ] 5 cuerpos ≤60 líneas, **in English** (D-P4-6); la spec que los surrounds sigue en español
- [ ] **Esqueleto de casa** (guía): `# NAME — ROLE` · `## ROLE & DIRECTIVE` · `### PERSONALITY` (Tone/Opening/Closing/Ritual/Taboo/E.g.) · `### CAPABILITIES` · `### RULES` · `## SOURCES OF TRUTH` · `## COMPOSITION`
- [ ] `### DELEGATION PROTOCOL` sustituido por cláusula explícita de **no-delegación** (D9), declarada en el `.md` y en la spec
- [ ] 6/6 elementos por agente mapeados a las secciones de casa: persona UH · propósito + bandeja · MCP-first · no-contaminación · formato de cita · cláusula «the vault's AGENTS.md governs and is editable»
- [ ] ≤60 líneas: el ejemplo de la guía tiene ~123 → comprimir y **declarar qué secciones se recortan**
- [ ] Persona de cada agente = traducción fiel de su fila en `docs/UH.md` (mismo rol, mismo alcance; sin reinterpretar la metodología)
- [ ] Itzamná enruta y no ejecuta ni delega
- [ ] 0 skills inexistentes citadas
- [ ] Frontmatter conforme a T1 y coherente con los YAML de T4
- [ ] Fichero <500 líneas
- Deps: T4 · Verificación: `wc -l` + grep de los 6 elementos + grep de skills + **chequeo de idioma (0 marcadores del español)** + md-lint

### [ ] T6 — Los 9 cuerpos de comando (verbatim)

- Subagente: `technical-writer` · Skills: `context-engineering`, `obsidian-markdown`, `opencode`, `documentation-and-adrs`
- Tools: `context7`, `codebase-memory-mcp`
- Fichero: NUEVO `specs/spec-payload-commands.md`
- [ ] 9 cuerpos ≤35 líneas, **in English** (D-P4-6), frontmatter `{description (1 line, English), agent}` (sin `model`, sin `subagent`)
- [ ] **Esqueleto de casa** (guía) adaptado: `## Pre-Flight` (frescura del índice + `search` antes de leer crudo) · `## Phase …` (fase metodológica) · `## Escalation` (`E_*` → `rag_status()` + `fix_hint`; dudas → `question`) · `## Suggested Next Step` con cita de bloque `> …` (siguiente comando de la cadena)
- [ ] ≤35 líneas: el ejemplo de la guía tiene ~99 → comprimir y **declarar qué secciones se recortan**
- [ ] 7/7 elementos por comando: fase UH · `$ARGUMENTS`/`$1` · MCP-first 7 tools · protocolo `E_*`→`rag_status` · destino = su bandeja D9.2 · formato de cita · no-contaminación
- [ ] `/research`, `/validate`, `/cite`: el español original queda en la spec como contrato de referencia; el bloque inglés es el congelado — traducción fiel (mismos estados de `procedencia`, mismo gate, mismas clasificaciones); divergencia semántica = enmienda fechada
- [ ] 0 ocurrencias de `!`cmd`` y de `@paths`
- [ ] `/transform`: solo skills existentes + gaps declarados sin inventar
- [ ] Fichero <500 líneas
- Deps: T3, T4 · Verificación: `wc -l` + greps + `agent:` válidos + **chequeo de idioma (0 marcadores del español)** + md-lint

### 🚦 Checkpoint CP-C — fin de T5+T6

- [ ] 5 prompts ≤60 líneas con los 6 elementos
- [ ] 9 comandos ≤35 líneas con los 7 elementos
- [ ] 0 `!`cmd`` / `@paths`
- [ ] Cada destino de escritura = su bandeja (D9.2)
- [ ] **0 marcadores del español en los 14 bloques del payload** (D-P4-6)
- [ ] Esqueleto de casa presente en los 14 ficheros (secciones de la guía, con las sustituidas declaradas)
- [ ] md-lint sin errores nuevos vs baseline

---

## Ola 4 — Coherencia

### [ ] T7 — Coherencia del blueprint y cierre de preguntas abiertas

- Subagente: `docs-writer` · Skills: `documentation-and-adrs`, `agent-md-refactor`, `context-engineering`
- Tools: `codebase-memory-mcp`, `vercel-grep`
- Ficheros: `specs/spec-payload-vault.md`, `specs/spec-agent-workflow.md`
- [ ] `AGENTS.md` del vault **reescrito en inglés** (D-P4-6) ≤120 líneas, 7 secciones, coherente con T5/T6
- [ ] §Testing con criterios ejecutables por Phase 5 (greps incluidos, incluido el de idioma)
- [ ] §Open Questions: array global **resuelto** (D-P4-2) y `default_agent` resuelto por evidencia
- [ ] Enlaces relativos entre specs: 0 rotos
- [ ] §Decisiones fechadas y §Trade-offs con los riesgos D-P4-3 y O-10 (fidelidad de la traducción)
- Deps: T5, T6 · Verificación: script de enlaces + `wc -l` de las 4 specs + md-lint

### 🚦 Checkpoint CP-D — fin de T7

- [ ] `AGENTS.md` del vault ≤120 líneas y coherente
- [ ] 0 enlaces rotos · 0 preguntas abiertas
- [ ] md-lint sin errores nuevos vs baseline

---

## Ola 5 — Cierre y FTR

### [ ] T8 — Cierre documental + FTR Phase 4→5

- Subagentes (secuencial): `code-reviewer` → `git-workflow-manager`
- Skills: `code-review-and-quality`, `git-workflow-and-versioning`, `changelog-generate`
- Tools: `codebase-memory-mcp`, `gitmcp`
- Ficheros: `SPEC.md`, `AGENTS.md`, `docs/WORKFLOW.md`, `docs/TECH_DEBT.md`, `CHANGELOG.md`
- [ ] 4 specs en el índice de `SPEC.md`; `spec-payload-vault.md` → `Approved` tras el FTR
- [ ] Índice de `AGENTS.md` (repo) con las 3 specs nuevas, ≤200 líneas
- [ ] `docs/WORKFLOW.md` §Phase 4 COMPLETADA con métricas reales + entrada FTR en §4
- [ ] `docs/WORKFLOW.md` §Phase 3.5: la referencia a `tasks/plan.md` apunta al commit (D-P4-5)
- [ ] `docs/TECH_DEBT.md`: TD-7, TD-8, TD-14a/TD-14b, TD-22, TD-6 actualizados
- [ ] Impacto de D-P4-6/D-P4-7 registrado para Phase 5 (constantes del wizard + asset `ejemplo.pdf` + re-verificación de que el PDF sigue parseable, F3)
- [ ] `CHANGELOG.md` con entrada de Phase 4
- [ ] `git diff --stat -- obsidian-workspace` **vacío**
- [ ] `agent_example.md` y `command_example.md` siguen **untracked** (`??` en `git status --short`) y **no entran en ningún commit** (D-P4-8)
- [ ] Commits atómicos Conventional Commits ≤72 columnas + trailer `Co-Authored-By: Moctezuma <dev@fisherk2.com>`
- Deps: T7 · Verificación: md-lint + render mermaid + `wc -l` + enlaces + **FTR con el usuario**

### 🚦 Checkpoint CP-E — gate de fase

- [ ] **BLUEPRINT APPROVED por el usuario** (FTR Phase 4→5) → status `Approved` en `SPEC.md`
- [ ] md-lint sin errores nuevos vs baseline
- [ ] mermaid render: 0 fallos
- [ ] 0 escrituras en `obsidian-workspace/**`
- [ ] `git status --short` con solo los ficheros del blueprint + docs

---

## Registro de decisiones durante la fase

| # | Decisión | Quién | Fecha |
| --- | --- | --- | --- |
| D-P4-1 | Congelar los 9 comandos verbatim en Phase 4 | dueño | 2026-11-04 |
| D-P4-2 | Eliminar el array global `permissions` (313 reglas) en Phase 5 | dueño | 2026-11-04 |
| D-P4-3 | Solo corregir el vocabulario V2; sin reglas MCP por agente | dueño | 2026-11-04 |
| D-P4-4 | Dividir el blueprint en 4 specs (<500 líneas) | dueño | 2026-11-04 |
| D-P4-5 | Sobrescribir `tasks/plan.md` y `tasks/todo.md` | dueño | 2026-11-04 |
| D-P4-6 | **Los artefactos del payload van en INGLÉS** (5 agents, 9 commands, `AGENTS.md` del vault, `description`); la prosa del repo sigue en español | dueño | 2026-11-04 |
| D-P4-7 | **Las muestras del payload van en inglés** (nombre y contenido): `ejemplo.md`/`ejemplo.pdf` → `example.md`/`example.pdf`; el renombrado del wizard es de Phase 5 | dueño | 2026-11-04 |
| D-P4-8 | **La guía de formato son `agent_example.md` y `command_example.md`** (raíz, **sin commitear**): fijan el header y el esqueleto de cuerpo; el plan solo referencia las rutas | dueño | 2026-11-04 |
| D-P4-9 | **CP-A se lee sobre las specs que existen en ese momento**: `spec-payload-skills.md` 182 ✔; `spec-payload-vault.md` 585 baja a <500 cuando T6 mueva los cuerpos de comando (el fichero ya partía de 528, rojo antes de Phase 4) | orquestador | 2026-11-04 |
| D-P4-10 | **Corte de 10 remnants en dominio** (`polars`, `dask`, `vaex`, `zarr-python`, `pyzotero`, `scientific-schematics`, `exa-search`, `perplexity-search`, `patents-search`, `database-lookup`) para que la base baje de 60 a 50 y cumpla `<60` — **pendiente de aprobación del dueño en el FTR**, no aplicado | dueño (pendiente) | 2026-11-04 |
| | | | |

## Notas de ejecución (rellenar al avanzar)

_Cada nota registra: qué se hizo, qué se encontró que no estaba en el plan, y la decisión que tomado._

- **T0 (2026-11-04):** baseline medido — 1 error MD005 pre-existente (`docs/WORKFLOW.md:166`), 13 bloques mermaid, `spec-payload-vault.md` 528 → 620 tras T1. Nada escrito.
- **T1 (2026-11-04):** §Reglas de formato reescrita (107 líneas) con URLs v2.1.2. Hallazgo: `doom_loop` y `lsp` **no** son acciones del catálogo oficial V2 («not current V2 Core permission actions»); se marcan como `casa`/`no` y se conservan solo por la vía de acciones ampliables por plugin. Se corrigieron tres contradicciones de D-P4-6 (fecha 2026-10-21 en cabecera y Goals; `description` y cuerpo «en español»).
- **T2 (2026-11-04):** inventario verificado 209/170/9, MISSING=0, 112 sin citar. La fila 15 citaba familias inexistentes (`gis-*`, `marketing-*`, … = 0 dirs) y «≈120» era falso: medido **109** out-of-domain. Fila 4 mal sumada (14−11=3 pero solo 2 ganadoras nombradas) → se nombró `paper-lookup`. Las muestras **no** están en el payload: las crea el instalador (`installer.rs`), con cuerpo y PDF en español → Phase 5 renombra constantes, traduce cuerpo y regenera el asset. `01-Tasks/` (mayúscula) existe y `01-tasks/` no: riesgo de caso en macOS/Windows. Matriz movida a `spec-payload-skills.md` (182 líneas).
- **CP-A (2026-11-04):** verde salvo el umbral de `spec-payload-vault.md` (585), que solo baja a <500 cuando T6 mueva los cuerpos de comando — el fichero ya estaba en 528 antes de Phase 4 (D-P4-9). Se avanza con el umbral como deuda declarada, no como verde.
