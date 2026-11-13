# ADR-012: Formato revisado del payload (post-Phase 5)

* **Status:** Accepted
* **Date:** 2026-11-11
* **Decision Makers:** Dueño del repo (decisión de producto en los 9 commits)
* **Consulted:** Arquitecto (calpulli docs, Phase 5)
* **Informed:** Equipo / agentes del vault
* **Traceability:** commits `baf2993`..`1c4a90b` (9 revisiones, 2026-11-10); [SPEC.md](../../SPEC.md); specs `spec-payload-{vault,skills,permissions,agents}.md`; [ADR-005](adr-005-mcp-ports-adapters.md), [ADR-007](adr-007-seleccion-embedder-instalacion.md), [ADR-010](adr-010-indice-multi-raiz-cita-vault.md)

## 1. Context and Problem Statement

Phase 5 cerró 2026-11-09 con el payload materializado según el blueprint: permisos como
fuente única en `spec-payload-permissions.md` (D-P4-2: sin array global de 313 reglas en
`opencode.json`), `AGENTS.md` del vault metodológico en inglés (7 secciones, 74 líneas,
regla MCP-first incluida), freeze de 40 skills (D-P5-1) y scaffold con `00-Resources/`.
El dueño revisó el payload instalado y ordenó 9 revisiones atómicas (`baf2993`,
`b4cc8ff`, `e58102f`, `3dd3901`, `2e59d4a`, `38f0248`, `1ce44ca`, `1dc350d`, `1c4a90b`),
ya commiteadas, que cambian el formato canónico ongoing sin reabrir el motor (D1-D6
intactos). Este ADR las consolida para que specs y docs vuelvan a describir el payload
real. Sin fuente externa: las decisiones provienen de los mensajes de commit del dueño
(máxima autoridad de producto); donde no hay fuente se marca explícito.

## 2. Decision Drivers

* Permisos **probados anti-comandos destructivos** priman sobre la pureza single-source.
* El `AGENTS.md` del vault debe regir **cualquier vault Obsidian**, independiente del harness.
* Nomenclatura en **minúsculas** en todo el vault (`AGENTS.md` §2 del payload).
* La skill 41 (`math-typesetting-guide`) es ampliación autorizada fuera del freeze D-P5-1.

## 3. Considered Options

* **Option A:** Adoptar el formato revisado como canónico ongoing (enmendar specs, superseder lo que choque).
* **Option B:** Mantener el blueprint Phase 5 y revertir las 9 revisiones.
* **Option C:** Convivencia sin documentar (payload y specs divergen en silencio).

## 4. Decision Outcome

**Chosen option:** Option A, porque las 9 revisiones son decisión explícita del dueño ya
sellada en commits atómicos; revertirlas (B) desobedecería producto y no documentarlas
(C) rompería la regla "specs antes que código".

### Revisión (a) — `AGENTS.md` del vault: guía genérica harness-agnóstica

`baf2993` sustituye el `AGENTS.md` metodológico (MCP-first/RAG, 7 secciones) por una guía
genérica en inglés (§1-9 + referencias): principios del vault, nomenclatura en minúsculas,
frontmatter, templates en `10-templates/`, reglas de operación y workflow de notas.
Referencia las skills `obsidian-markdown`, `obsidian-vault`, `math-typesetting-guide`,
`markdown-mermaid-writing` y delega CLI al subagente `obsidian-vault-writer` con la skill
`obsidian-cli`. La regla MCP-first **deja de vivir en el `AGENTS.md`** y queda solo en los
system prompts de los 5 agentes (consecuencia para TD-6/TD-14, ver §6).

### Revisión (b) — permisos inline por agente + global amplio anti-destructivo

Los 5 commits `b4cc8ff`..`38f0248` inscriben permisos inline verificados en cada
`.opencode/agents/*.md` y retiran el comentario single-source a
`spec-payload-permissions.md`: nezahualcóyotl (edit acotado a `01-tasks`, web deny,
subagent deny, shell anti-redirección); pochteca (edit solo `01-tasks/research`, subagent
allow con denies nominales, web allow); chilam (edit `03-citations` + `04-review`, web
allow); tlacuilo (edit allow global, web allow); itzamná (edit ask global, web allow).
`1ce44ca` añade el bloque `permissions` global de **313 reglas** anti-comandos
destructivos (subagent ask, `external_directory` deny con allows a caches/toolchains/tmp,
shell ask con granularidad por comando). **Revierte D-P4-2/D-P5-4** (eliminar el array
global): con array global + bloques inline, la política efectiva vuelve a ser la
concatenación `global ++ bloque` (last-match-wins); los bloques inline se verificaron
contra ese global, no contra el vacío.

### Revisión (c) — minúsculas `00-resources/` + scaffold `10-templates/`

`1dc350d` renombra `00-Resources/` → `00-resources/` y agrega `10-templates/.gitkeep`;
`1ce44ca` cambia `INDEXER_DIR` a `00-resources`. El fallback del contrato (`["00-Resources"]`
cuando la variable está ausente, ADR-010 §4.1) **no cambia en esta ola**: es default de código, no del
payload. En Linux ambas rutas son directorios distintos (sensible a case); el instalador
debe materializar el case exacto de `INDEXER_DIR` (vecino de TD-8).

**Actualización 2026-11-13:** el fallback de código también pasa a `00-resources` (minúsculas) —
ver [spec-vault-structure](../spec-vault-structure.md) §Enmienda 2026-11-13. Este apartado se
conserva como registro de la revisión de 2026-11-11.

### Revisión (d) — skill 41 `math-typesetting-guide`

`1c4a90b` agrega la skill `math-typesetting-guide` (referencia LaTeX, invocada desde §3
del `AGENTS.md` del payload). **Reemplaza el freeze D-P5-1**: el inventario pasa de 40 a
**41 dirs**; el objetivo <60 sigue cumplido (41 < 60).

### 4.1 Confirmation

* `ls obsidian-workspace/.opencode/skills | wc -l` ⇒ 41; `ls obsidian-workspace/00-resources` y `10-templates/` existen.
* `python3 -c` sobre `obsidian-workspace/opencode.json` ⇒ `len(permissions) == 313`, `INDEXER_DIR == "00-resources"`.
* Grep: cero `single source; never duplicated here` en `.opencode/agents/`; cero `00-Resources` en `obsidian-workspace/` (tracked).

## 5. Pros and Cons of the Options

### Option A — Formato revisado (elegida)

* ✅ **Pros:** payload y specs coherentes; permisos verificados contra el global real; vault reutilizable sin harness.
* ⚠️ **Cons:** dos fuentes de permiso por agente (global ++ inline) — auditar exige simular la fusión; deriva single-source asumida.
* ⚖️ **Neutral:** el blueprint Phase 4/5 queda como histórico, no como vigente.

### Option B — Revertir las 9 revisiones

* ✅ **Pros:** blueprint intacto, fuente única.
* ⚠️ **Cons:** desobedece decisión explícita del dueño; pierde permisos probados.
* Rejected: el dueño ya selló el formato.

### Option C — No documentar

* ✅ **Pros:** cero trabajo.
* ⚠️ **Cons:** specs describen un payload que no existe; gates futuros (TD-31) verificarían contra ficción.
* Rejected: viola "specs antes que código".

## 6. Consequences

* ✅ **Positives:** formato canónico claro y grepeable; 41 < 60 cumplido; `INDEXER_DIR` en minúsculas coherente con la guía del vault.
* ⚠️ **Negatives / Risks:** la fusión `global ++ inline` reintroduce el riesgo D-P4-2 (un `allow` global ensancha en silencio) — mitigado porque los bloques inline se verificaron contra ese global; si el global cambia, re-verificar. TD-6/TD-14: su evidencia "MCP-first en el `AGENTS.md`" queda **desactualizada** — la regla vive ahora en los prompts (ver TECH_DEBT). TD-7: freeze 40 roto, pasa a 41. TD-8: se extiende a case de `00-resources` vs fallback `00-Resources`.
* ⚖️ **Neutral / Paradigm Shifts:** D-P4-2, D-P5-1 (freeze 40) y D-P5-4 quedan **SUPERSEDED** por este ADR; ADR-005/007/010 y D1-D6 **no se reabren** (motor intacto).

## 7. Related Decisions

* [ADR-005](adr-005-mcp-ports-adapters.md) — frontera MCP intacta; sin reglas `<server>_<tool>` por agente (D-P4-3 sigue).
* [ADR-007](adr-007-seleccion-embedder-instalacion.md) — menú embedder intacto.
* [ADR-010](adr-010-indice-multi-raiz-cita-vault.md) — fallback `00-Resources` de código intacto; el payload declara `00-resources`.
* Supersede: D-P4-2, D-P5-1, D-P5-4 (decisiones de blueprint Phase 4/5).

## 8. Compliance and Review

* **Success metrics:** specs enmendadas describen el payload real (grep §4.1 verde); TD-31 corre contra el formato revisado.
* **Next review date:** 2027-05-11
* **Revisit triggers:** cambio del array global sin re-verificación inline; nuevo rename de raíces; skill 42+.

---
*Template based on [MADR v4.0](https://adr.github.io/madr/) and [Nygard's ADR format](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).*
