# TODO — Phase 4 (blueprint del payload del vault)

> **Fecha:** 2026-11-04 · **Orquestador:** Moctezuma · **Plan:** [tasks/plan.md](plan.md)
> **Verificación de esta fase:** SOLO linters (markdownlint + mermaid render + greps). **La suite de pruebas no se ejecuta.**
> **Prohibido escribir en `obsidian-workspace/**`** (Phase 4 es diseño puro).

## Baseline del gate de linters (T0)

Pendiente de T0: lo rellena el orquestador con el reporte del subagente.

| Métrica | Valor en HEAD (2026-11-04) | Nota |
| --- | --- | --- |
| Errores de `just md-lint` (`docs specs AGENTS.md SPEC.md`) | — | baseline D12: el gate **no** está verde; el criterio es **cero errores nuevos** |
| Bloques mermaid en `docs/` + `specs/` | — | render obligatorio de los nuevos |
| `wc -l specs/*.md` | — | `spec-payload-vault.md` = 528 (rojo: umbral <500) |
| `git status --short` | — | debe quedar vacío antes de empezar |

---

## Leyenda

- `[ ]` pendiente · `[~]` en curso · `[x]` hecho y verificado · `[!]` bloqueado (motivo en la línea)
- Cada calpulli se cierra con su checkpoint. **No se avanza al siguiente checkpoint en rojo.**

---

## Ola 1 — Fundamentos (paralelo: T1 ‖ T2)

### [ ] T0 — Baseline del gate de linters

- Subagente: `developer-tooling-engineer` · Skills: `bash-defensive-patterns`, `context-engineering` · Tools: shell, npx
- Salida: 4 números (md-lint, mermaid, `wc -l`, `git status`) reportados al orquestador
- [ ] `just md-lint` ejecutado y recuento reportado
- [ ] Bloques mermaid contados por fichero
- [ ] `wc -l specs/*.md` con los 4 objetivos marcados
- [ ] `git status --short` vacío
- Deps: — · Verificación: números reportados

### [ ] T1 — Reglas de formato OpenCode V2 (re-verificadas) + vocabulario de acciones

- Subagente: `developer-tooling-engineer` · Skills: `opencode`, `source-driven-development`, `find-docs`
- Tools: `context7`, `gitmcp`, `vercel-grep`
- Fichero: `specs/spec-payload-vault.md` (§Reglas de formato)
- [ ] Cada regla con URL oficial + versión `v2.1.2` + fecha 2026-11-04
- [ ] Tabla del vocabulario V2 de acciones, con `todowrite` marcado **inexistente**
- [ ] `permission:` singular marcado **V1 legacy / prohibido**
- [ ] Discrepancia `agents.mdx` vs `permissions.mdx` resuelta a favor de la **lista**, citada
- [ ] Checklist de no-regresión de frontmatter (7 campos legacy + `todowrite` + `subagent` en comandos)
- Deps: T0 · Verificación: grep de URLs + md-lint sin errores nuevos + revisión del orquestador

### [ ] T2 — Inventario real + matriz de conflictos 1:1

- Subagentes (secuencial): `codebase-archaeologist` → `knowledge-synthesizer`
- Skills: `codebase-memory`, `context-engineering`, `documentation-and-adrs` · Tools: `codebase-memory-mcp`, `vercel-grep`, shell
- Fichero: NUEVO `specs/spec-payload-skills.md`
- [ ] Recuento con comando + fecha: **209** skills · **170** agentes · **9** comandos
- [ ] 0 skills inventadas (grep 1:1 contra el `ls`) · 0 huérfanas
- [ ] 209/209 clasificadas (CONSERVAR / CONSOLIDAR+ganadora / RETIRAR / INSTALAR-GAP) o barridas por la fila 15
- [ ] Gaps (Jupyter, R, Graphviz/PlantUML, LaTeX manuscrito) declarados sin inventar nombres
- [ ] `tepochcalli-mcp` (fila 17) y TD-22/OfficeCLI coherentes con `docs/TECH_DEBT.md`
- [ ] Recuento **derivado** de skills del payload base vs objetivo **<60**
- [ ] Fichero <500 líneas (si supera 450 → avisar: contingencia O-2)
- Deps: T0 · Verificación: script de cobertura (faltantes 0, huérfanos 0) + `wc -l` + md-lint

### 🚦 Checkpoint CP-A — fin de T1+T2

- [ ] Reglas de formato citadas (URL + versión + fecha)
- [ ] Inventario 1:1 verificado (209/170/9)
- [ ] 0 skills inventadas
- [ ] Las 4 specs objetivo <500 líneas
- [ ] md-lint sin errores nuevos vs baseline

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
- [ ] 5 YAML con vocabulario V2 (sin `todowrite`, sin `permission:` singular, sin campos legacy)
- [ ] last-match-wins: reglas amplias primero, excepciones al final (ej. Nezahualcóyotl: `01-tasks/research/** deny` **último**)
- [ ] Superficies: Pochteca `01-tasks/research/**` · Nezahualcóyotl `01-tasks/` (sin research) · Chilam `03-citations/`+`04-review/` · Tlacuilo deny-list (`02-drafts/`, `05-outputs/`, 10+ a petición) · Itzamná sin edit/subagent/shell
- [ ] **D-P4-2 registrada**: el array global de 313 reglas se elimina en Phase 5 → permisos SOLO en los `.md`
- [ ] Frontmatter: `mode: primary`, `description` en español, sin `model`; `default_agent` → `itzamna`
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
- [ ] 5 cuerpos ≤60 líneas, en español
- [ ] 6/6 elementos por agente: persona UH · propósito + bandeja · MCP-first · no-contaminación · formato de cita · cláusula «el AGENTS.md del vault manda»
- [ ] Itzamná enruta y no ejecuta ni delega
- [ ] 0 skills inexistentes citadas
- [ ] Frontmatter conforme a T1 y coherente con los YAML de T4
- [ ] Fichero <500 líneas
- Deps: T4 · Verificación: `wc -l` + grep de los 6 elementos + grep de skills + md-lint

### [ ] T6 — Los 9 cuerpos de comando (verbatim)

- Subagente: `technical-writer` · Skills: `context-engineering`, `obsidian-markdown`, `opencode`, `documentation-and-adrs`
- Tools: `context7`, `codebase-memory-mcp`
- Fichero: NUEVO `specs/spec-payload-commands.md`
- [ ] 9 cuerpos ≤35 líneas, frontmatter `{description, agent}` (sin `model`, sin `subagent`)
- [ ] 7/7 elementos por comando: fase UH · `$ARGUMENTS`/`$1` · MCP-first 7 tools · protocolo `E_*`→`rag_status` · destino = su bandeja D9.2 · formato de cita · no-contaminación
- [ ] `/research`, `/validate`, `/cite` verbatim (cualquier cambio anotado como enmienda fechada)
- [ ] 0 ocurrencias de `!`cmd`` y de `@paths`
- [ ] `/transform`: solo skills existentes + gaps declarados sin inventar
- [ ] Fichero <500 líneas
- Deps: T3, T4 · Verificación: `wc -l` + greps + `agent:` válidos + md-lint

### 🚦 Checkpoint CP-C — fin de T5+T6

- [ ] 5 prompts ≤60 líneas con los 6 elementos
- [ ] 9 comandos ≤35 líneas con los 7 elementos
- [ ] 0 `!`cmd`` / `@paths`
- [ ] Cada destino de escritura = su bandeja (D9.2)
- [ ] md-lint sin errores nuevos vs baseline

---

## Ola 4 — Coherencia

### [ ] T7 — Coherencia del blueprint y cierre de preguntas abiertas

- Subagente: `docs-writer` · Skills: `documentation-and-adrs`, `agent-md-refactor`, `context-engineering`
- Tools: `codebase-memory-mcp`, `vercel-grep`
- Ficheros: `specs/spec-payload-vault.md`, `specs/spec-agent-workflow.md`
- [ ] `AGENTS.md` del vault ≤120 líneas, 7 secciones, coherente con T5/T6
- [ ] §Testing con criterios ejecutables por Phase 5 (greps incluidos)
- [ ] §Open Questions: array global **resuelto** (D-P4-2) y `default_agent` resuelto por evidencia
- [ ] Enlaces relativos entre specs: 0 rotos
- [ ] §Decisiones fechadas y §Trade-offs con el riesgo D-P4-3
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
- [ ] `CHANGELOG.md` con entrada de Phase 4
- [ ] `git diff --stat -- obsidian-workspace` **vacío**
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
| | | | |

## Notas de ejecución (rellenar al avanzar)

_Cada nota registra: qué se hizo, qué se encontró que no estaba en el plan, y la decisión que tomado._
