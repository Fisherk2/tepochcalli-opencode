# TODO — Phase 5 (ejecución del blueprint del payload)

> **Fecha:** 2026-11-09 · **Orquestador:** Moctezuma · **Plan:** [tasks/plan.md](plan.md)
> **Fase:** Phase 5 — Payload + Skills audit (ejecución) · **Gate:** FTR Phase 5→6
> **Decisiones del dueño (2026-11-09):** D-P5-1..D-P5-9 — ver `tasks/plan.md` §2.
> **Precedente (D-P4-5):** este fichero **sobrescribe** el TODO de Phase 4; el de Phase 4 queda en git (`337c012`).

## Reglas de la fase

- **Se escribe en `obsidian-workspace/`** (a diferencia de Phase 4): es la fase de ejecución.
- **`.opencode/skills/` NO se toca**: las 40 skills son definitivas (D-P5-1). Ningún alta, baja ni edición.
- **Divergencia = vuelta a Phase 4**: si al ejecutar aparece una divergencia entre el blueprint y la realidad, se **enmienda la spec con fecha** (no parche en el payload).
- **Sin asunción**: cada afirmación del informe de cierre lleva su comando y su salida.
- **Commits atómicos**: uno por calpulli, Conventional Commits ≤ 72 cols, trailer `Co-Authored-By`.

## Leyenda

- `[ ]` pendiente · `[~]` en curso · `[x]` hecho y verificado · `[!]` bloqueado (motivo en la línea)
- **No se avanza al siguiente checkpoint en rojo.**

---

## Ola 0 — Fundamentos

### [x] T0 — Baseline del payload y auditoría de divergencias

- Subagente: `codebase-archaeologist` · Skills: `codebase-memory`, `context-engineering` · Tools: `codebase-memory-mcp`, `vercel-grep`
- [ ] Tabla de 4 divergencias con el comando que las evidencia
- [ ] Baseline: `wc -l` de los 15 artefactos · `ls .opencode/skills | wc -l` = 40 · `len(permissions)` = 313 · `just md-lint` = 0
- [ ] Hash del árbol de skills guardado (para M1)
- [ ] `git status --short` y `git diff --stat -- obsidian-workspace` vacíos
- Deps: — · Verificación: informe con números crudos

### [x] T1 — Enmienda fechada del blueprint (skills inexistentes)

- Subagente: `technical-writer` → `prompt-engineer` (secuencial) · Skills: `documentation-and-adrs`, `prompt-engineering`, `source-driven-development` · Tools: `gitmcp`, `context7`
- [ ] `spec-payload-commands.md` §`/transform`: 8 skills inexistentes → reales del `ls` de 40; GAP literales intactos
- [ ] `spec-payload-agents.md` §Tlacuilo: `xlsx-official`/`excel-analysis` → reales
- [ ] Marca de enmienda fechada 2026-11-09 en ambas; `Status: Approved` conservado
- [ ] Tabla 9×4 de `spec-payload-skills.md` coherente
- [ ] Invariante: **0** nombres de skill inexistentes en las 5 specs
- [ ] Reglas V2 re-verificadas contra el tag vigente (fecha + URL)
- [ ] `git diff --stat -- obsidian-workspace/.opencode/skills` **vacío**
- Deps: T0 · Verificación: barrido de skills 0 huérfanos · `just md-lint` 0

### [x] Checkpoint CP-0 — Enmienda aprobada por el dueño

- [ ] Enmienda aprobada explícitamente (T4 y T7 quedan desbloqueados)
- [ ] `.opencode/skills/` sin cambios

---

## Ola 1 — Los 5 agentes

### [x] T2 — `itzamna` (piloto vertical)

- Subagente: `security-architect` → `prompt-engineer` (secuencial) · Skills: `prompt-engineering`, `security-and-hardening`, `design-patterns`, `clean-code` · Tools: `gitmcp`
- [ ] `obsidian-workspace/.opencode/agents/itzamna.md`: frontmatter (16 reglas) + cuerpo de 56 líneas
- [ ] `wc -l` ≤ 60 · 0 campos legacy · 6 elementos del contrato T5
- [ ] 0 marcadores del español
- [ ] Probes: `edit *` deny · `read 00-Resources/x.md` allow · `read .env` deny · `read .tepochcalli/config/*` deny
- Deps: T0 · Verificación: simulador last-match-wins + markdownlint del payload

### [x] T3 — `nezahualcoyotl`, `pochteca`, `chilam`

- Subagente: `security-architect` → `prompt-engineer` (secuencial, por agente) · Skills: idem T2 · Tools: `gitmcp`
- [ ] 3 ficheros (54/58/58 líneas), todos ≤ 60
- [ ] Probes D9.3 de los 3 verdes (bandeja propia allow, resto deny)
- [ ] Sin web en Nezahualcóyotl y Chilam; con web en Pochteca
- [ ] `subagent * deny` en los 3
- Deps: T2 · Verificación: simulador + diff contra la spec

### [x] T4 — `tlacuilo` (depende de T1)

- Subagente: `security-architect` → `prompt-engineer` (secuencial) · Skills: idem T2 · Tools: `gitmcp`
- [ ] `tlacuilo.md` 56 líneas con deny-list completa (12 denies tras `edit * allow`)
- [ ] Probes: `edit 05-outputs/x.csv` allow · `edit 00-Resources/x.md` deny · `edit AGENTS.md` deny · `edit opencode.json` deny · `edit .git/config` deny
- [ ] CAPABILITIES con skills reales (enmienda de T1 aplicada)
- Deps: T1 + T3 · Verificación: simulador + barrido de skills

### [x] Checkpoint CP-1 — Los 5 agentes materializados

- [ ] 5 `.md` completos, ≤ 60 líneas
- [ ] Simulador verde en los 5
- [ ] `git diff --stat -- obsidian-workspace` = solo los 5 ficheros de agente

---

## Ola 2 — Los 9 comandos

### [x] T5 — `/rubric`, `/synthesize`, `/draft`, `/update`

- Subagente: `technical-writer` · Skills: `prompt-engineering`, `documentation-and-adrs` · Tools: `gitmcp`
- [ ] 4 ficheros, 24 líneas cada uno, ≤ 35
- [ ] Frontmatter `{description, agent}`; esqueleto de casa completo
- [ ] 0 `model` · 0 `subtask` · 0 `subagent:` · 0 `` !`cmd` `` · 0 `@paths`
- [ ] Bandeja y frontmatter de salida exactos por comando
- [ ] `E_*` → `rag_status()` + `fix_hint` en los 4
- Deps: T0 · Verificación: barrido de los 4 + diff contra la spec

### [x] T6 — `/research`, `/validate`, `/cite`, `/review`

- Subagente: `technical-writer` → `prompt-engineer` (secuencial) · Skills: `prompt-engineering`, `documentation-and-adrs` · Tools: `gitmcp`
- [ ] 4 ficheros (30/26/24/24 líneas), ≤ 35
- [ ] `/research`: `procedencia` siempre serializada, 4 estados, `web_search_unconfirmed` nunca como `verificada`
- [ ] `/validate`: 4 clases de claim; ambigüedad nunca `respaldada`; `ok` imposible con `sin_ancla`/`sin_cita`
- [ ] `/cite`: gate determinista sin red; sin `procedencia` ⇒ falla nombrando el culpable; 0 supervivientes ⇒ fallo
- [ ] `/review`: no edita el borrador; hallazgos con ubicación
- [ ] Nombres de campo en español intactos (`fuentes`, `método`, `procedencia`, `estado`, `fuente`, `url_o_doi`, `fecha_consulta`)
- Deps: T0 · Verificación: barrido + tokens de enum intactos

### [x] T7 — `/transform` (depende de T1)

- Subagente: `technical-writer` · Skills: `prompt-engineering`, `documentation-and-adrs` · Tools: `gitmcp`, `context7`
- [ ] `transform.md` 25 líneas, ≤ 35
- [ ] Skills solo reales del congelado; GAP (Jupyter, R, Graphviz/PlantUML, LaTeX) declarados
- [ ] `list_formats` antes de prometer formato; el `.md` convertido no es fuente citable
- [ ] Bandeja `05-outputs/` + manifiesto `{command, agent, source_draft, formats, date}`
- Deps: T1 · Verificación: barrido + 0 skills huérfanas

### [x] Checkpoint CP-2 — Los 9 comandos materializados

- [ ] 9 `.md` completos, ≤ 35 líneas
- [ ] 0 inline shell · 0 `@paths` · 0 `subtask`/`subagent:`
- [ ] Los 9 `agent:` coinciden con la spec y con el mapa D9.2
- [ ] 0 marcadores del español

---

## Ola 3 — Vault, config y scaffold (paralelo entre sí)

### [x] T8 — `AGENTS.md` del vault

- Subagente: `prompt-engineer` · Skills: `prompt-engineering`, `obsidian-markdown` · Tools: `gitmcp`
- [ ] Bloque congelado de `spec-payload-vault.md` literal; 7 secciones
- [ ] `wc -l` ≤ 120 (objetivo 67)
- [ ] Cita, 4 estados y 4 clases coinciden token a token con las otras specs (script)
- [ ] Mapa comando→agente→bandeja = D9.2 y los 9 `agent:`
- [ ] 0 marcadores del español · 0 placeholders `[...]` residuales
- Deps: T0 · Verificación: script de coincidencia literal + markdownlint

### [x] T9 — `opencode.json` del payload + fixture sintético

- Subagente: `python-pro` · Skills: `test-driven-development`, `incremental-implementation`, `api-and-interface-design` · Tools: —
- [ ] Array global de 313 `permissions` **eliminado**
- [ ] `instructions` → rutas relativas al vault (4 entradas) y resolubles
- [ ] `agents` con los 5 primarios (sin arrays de permisos) · `default_agent` = `itzamna` · `mcp.servers` intacto · `references` conservado
- [ ] Fixture **sintético** sustituye al congelado (cierra TD-30)
- [ ] Test del merge: resto byte-idéntico + solo `tepochcalli-rag` con la forma del contrato + `markitdown` no registrada
- [ ] Test del payload real: parseable, sin array global, `default_agent` correcto
- [ ] RED demostrado antes de implementar
- Deps: T0 · Verificación: `just python-test` + lint + fmt verdes

### [x] T10 — Scaffold canónico + `.gitignore` del vault

- Subagente: `minimal-change-engineer` · Skills: `git-workflow-and-versioning`, `bash-defensive-patterns` · Tools: `vercel-grep`
- [ ] `git mv 01-Tasks → 01-tasks` (renombrar, nunca crear)
- [ ] 3 ficheros de 0 bytes eliminados
- [ ] `01-tasks/research/`, `02-drafts/`, `03-citations/`, `04-review/`, `05-outputs/` con `.gitkeep`
- [ ] `00-Resources/.gitkeep`
- [ ] `obsidian-workspace/.gitignore` con las 5 rutas de spec-vault-structure
- [ ] `git ls-files` sin `01-Tasks` y con las 6 bandejas
- Deps: T0 · Verificación: `git ls-files` + `ls -la` + `git status --short`

### [x] Checkpoint CP-3 — Vault y config coherentes

- [ ] `AGENTS.md` con 7 secciones, ≤ 120 líneas, vocabulario compartido verificado
- [ ] `opencode.json` sin array global; `instructions` resolubles
- [ ] 6 bandejas con capitalización canónica + `.gitignore` con 5 rutas

---

## Ola 4 — El gate D9 ejecutable

### [x] T11 — Fixtures de permisos D9.3 + contrato estático del payload

- Subagente: `test-engineer` → `python-pro` (secuencial) · Skills: `test-driven-development`, `design-patterns`, `clean-code`, `doubt-driven-development` · Tools: —
- [ ] `tests/unit/test_payload_permissions.py`: intérprete last-match-wins + **42/42** probes
- [ ] 5 agentes con `subagent * deny`; secretos denegados en los 5; 0 reglas muertas
- [ ] `tests/unit/test_payload_contract.py`: skills **exactamente** las 40, con hash idéntico al de T0
- [ ] 0 nombres de skill inexistentes en los 15 artefactos
- [ ] Presupuestos: agentes ≤ 60, comandos ≤ 35, `AGENTS.md` ≤ 120
- [ ] 0 legacy · 0 `subtask`/`subagent:` · 0 `` !`cmd` `` · 0 `@paths` · 0 marcadores del español
- [ ] `default_agent` → `itzamna` con `mode: primary`; `model` no repetido en los `.md`
- [ ] RED demostrado antes de implementar
- Deps: T2-T10 · Verificación: `just ci` verde + cobertura ≥ 95 %

### [x] Checkpoint CP-4 — Contrato estático verde

- [ ] `just ci` verde
- [ ] 42/42 probes · 40/40 skills con hash idéntico · 0 huérfanos
- [ ] `just md-lint` 0

---

## Ola 5 — Los gates de la fase

### [x] T12 — Install e2e del wizard sobre el payload final

- Subagente: `rust-engineer` · Skills: `bash-defensive-patterns`, `test-driven-development`, `doubt-driven-development` · Tools: —
- [ ] Payload empaquetado con la misma lista de exclusiones de `release.yml` (raíz del tar = contenido del vault)
- [ ] `install --non-interactive --skip-model --payload <tmp>` → 0 errores
- [ ] Árbol instalado = canónico, con capitalización correcta
- [ ] 5 agentes + 9 comandos + `AGENTS.md` instalados con su contenido
- [ ] `opencode.json` instalado sin array global y con `tepochcalli-rag` inyectado por F8
- [ ] 2 muestras del wizard en `00-Resources/`
- [ ] `.gitignore` instalado con las 5 rutas
- [ ] Idempotencia: 2ª corrida sin duplicados ni diffs
- [ ] `just rust-ci` y `just rust-smoke` verdes
- Deps: T11 · Verificación: script de aserción sobre el vault efímero

### [ ] T13 — Methodology e2e (D9) — corrida manual con evidencia

- Subagente: `testing-evidence-collector` → `testing-reality-checker` (secuencial) · Skills: `doubt-driven-development`, `document-verification` · Tools: MCP `tepochcalli-rag` del payload
- [x] Protocolo escrito y versionado (`tasks/phase5-methodology-e2e.md`)
- [x] Runbook de QA con prompts por comando (`tests/phase5-methodology-runbook.md`, corpus de fotosíntesis)
- [ ] Corrida de los 9 comandos en orden sobre el vault de T12 (la ejecuta QA con el runbook)
- [ ] Checklist por comando: bandeja única · frontmatter exacto · cero contaminación cruzada · MCP-first observado · no-contaminación
- [ ] Evidencia: transcript de tool-calls + árbol final del vault
- [ ] Lo no verificado escrito como no verificado
- Deps: T12 · Verificación: checklist firmado; si no se ejecuta, la fase queda ABIERTA

### Checkpoint CP-5 — Gates de la fase verdes

- [ ] Install e2e verde (árbol, capitalización, F8, muestras, idempotencia)
- [ ] Methodology e2e 9/9 con evidencia
- [ ] Lo no verificado declarado

---

## Ola 6 — Cierre

### [ ] T14 — Cierre documental + FTR Phase 5→6

- Subagente: `docs-writer` → `code-reviewer` (secuencial) · Skills: `documentation-and-adrs`, `changelog-generate`, `git-workflow-and-versioning`, `code-review-and-quality` · Tools: `vercel-grep`
- [ ] `docs/WORKFLOW.md` §Phase 5: COMPLETADA + métricas medidas + lo no verificado
- [ ] `docs/TECH_DEBT.md`: TD-6, TD-7, TD-8, TD-14, TD-30 con evidencia de cierre
- [ ] `SPEC.md`: 5 specs del payload `Approved` con la marca de enmienda
- [ ] `CHANGELOG.md`: entrada de Phase 5
- [ ] `docs/ARCHITECTURE.md`: sin diagrama nuevo (Phase 5 no cambia las capas)
- [ ] FTR Phase 5→6 con el checklist de `docs/WORKFLOW.md` §4
- [ ] Revisión cruzada blueprint ↔ artefactos por un segundo par de ojos
- [ ] `just ci` verde + `just md-lint` 0
- Deps: T11 + T13 · Verificación: FTR con checklist firmado por el dueño

### Checkpoint CP-6 — FTR Phase 5→6

- [ ] Checklist de la fila Phase 5→6 de `docs/WORKFLOW.md` §4 verde
- [ ] Cifras medidas en todos los documentos
- [ ] Phase 6 (E2E Acceptance) liberada
