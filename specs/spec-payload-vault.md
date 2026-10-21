# Spec: Blueprint del payload del vault — agentes, comandos y AGENTS.md (OpenCode V2)

* **Status:** Proposed
* **Date:** 2026-10-21
* **Author:** Arquitecto (blueprint confirmado por el usuario 2026-10-21)
* **Reviewers:** Product Owner (usuario)
* **Traceability:** specs/spec-agent-workflow.md (mapa comandos→bandejas D9.2, desviación Pochteca D9.3, reglas del AGENTS del vault), specs/spec-vault-structure.md (zonas D9.1), specs/spec-mcp-server.md (4 tools + taxonomía `E_*`), docs/UH.md (tabla Agentes Primarios — inmutable), docs/WORKFLOW.md Phase 4; reglas de formato OpenCode V2 verificadas contra docs oficiales el 2026-10-21

## Summary

Esta spec es el **blueprint ejecutable** del payload distribuible: el contenido exacto de los 5
agentes primarios (`.opencode/agents/{itzamna,nezahualcoyotl,pochteca,chilam,tlacuilo}.md`), los 9
comandos de la metodología (`.opencode/commands/*.md`) y el `AGENTS.md` del vault, en formato
OpenCode V2. **No se escribe nada ahora**: por decisión explícita del usuario (2026-10-21),
`obsidian-workspace/` queda intacto bajo /spec; la ejecución del blueprint es labor de **Phase 4
vía /plan**, por agentes autorizados. Los permisos por agente viven SOLO en los `.md`; los modelos
viven SOLO en `opencode.json` (no duplicar en ambos lugares).

## Problem / Motivation

La metodología D9 (comandos→bandejas, MCP-first, no-contaminación) solo es real si los artefactos
del harness la reflejan: stubs sin cuerpo y permisos hereditarios de un template de desarrollo NO
aplican el diseño. Un despacho anterior autorizó reescribir el payload; el usuario lo corrigió
(2026-10-21): el diseño se DOCUMENTA aquí y se EJECUTA en Phase 4. Esta spec congela el blueprint.

> Como investigador, quiero que /rubric → /update enruten solos al agente correcto y que ningún
> agente pueda escribir fuera de su bandeja — sin configurar nada a mano.

## Goals and Non-Goals

### Goals

* Documentar verbatim-fiel el blueprint de permisos (5 YAML), comandos (9) y `AGENTS.md` del vault (7 secciones).
* Congelar las reglas de formato OpenCode V2 verificadas 2026-10-21 (frontmatter permitido, last-match-wins, prohibiciones).
* Definir los criterios de aceptación de la ejecución Phase 4, linkables desde docs/WORKFLOW.md.

### Non-Goals (fuera de scope — decisión usuario 2026-10-21)

* Instalación/saneamiento de skills (Anexo A; obra de /plan Phase 4). Esta spec NO referencia skills inexistentes.
* Borrado de subagents: los ~170 archivos de `.opencode/agents/` (5 primarios + ~165 del pack Códice) se CONSERVAN.
* Cambiar `obsidian-workspace/` desde /spec: **PROHIBIDO**. Ningún archivo del payload se modifica con esta ola.

## Proposed Solution

Phase 4 materializa 15 archivos de texto desde los bloques de esta spec (5 agents, 9 commands,
1 AGENTS.md) más la verificación de `opencode.json` (§Nota de fusión). El enrutamiento usa el
patrón nativo V2: el campo `agent:` de un comando cambia la sesión al primary indicado — Itzamná
"enruta sin ejecutar" sin necesidad de spawns.

## Detailed Design

### Reglas de formato OpenCode V2 (verificadas en docs oficiales 2026-10-21)

* **Agent** (`.opencode/agents/<name>.md`): frontmatter con campos {`description`, `mode`, `model`,
  `permissions`, `steps`, `hidden`, `color`}; el cuerpo Markdown ES el system prompt.
* `permissions` = lista ordenada de `{action, resource, effect}`; `action` ∈ {shell, edit, subagent,
  read, glob, grep, webfetch, websearch, skill, …} (wildcards válidos); `resource` para read/edit es
  un path glob (`01-tasks/research/**`, `~`/$HOME expanden); `effect` ∈ allow|ask|deny.
  **LAST MATCHING RULE WINS: reglas amplias primero, excepciones después.**
* **PROHIBIDO cualquier campo legacy** en el frontmatter: `temperature`, `top_p`, `prompt`,
  `permission` (singular), `tools`, `disable`, `maxSteps`.
* **Command** (`.opencode/commands/<name>.md`): frontmatter opcional {`description`, `agent`,
  `model`, `subagent`}; el cuerpo es la plantilla de prompt (NO existe clave `template`).
  Placeholders: `$ARGUMENTS` (string completo), `$1`/`$2` (posicionales).
  **Bloques shell !`cmd` PROHIBIDOS** (advertencia de args no confiables); `@paths` no expanden en
  plantillas almacenadas — no usar. `subagent: true` se deja OMITIDO: los comandos corren en la
  sesión sobre el primary seleccionado (patrón de ruteo V2).

### Blueprint de permisos por agente (YAML; cuerpo ≤60 líneas por archivo, español)

Los cinco archivos llevan `mode: primary`, `description` en español (1 línea) y SIN `model`
(vive en `opencode.json`). Cada cuerpo (system prompt, español, ≤60 líneas) incluye: persona UH
(1-2 líneas); propósito en el workflow con su bandeja exacta; MCP-first (`search` de
`tepochcalli-rag` antes de lectura cruda de `00-Resources/`, `index_refresh()` con dudas de
frescura, ante cualquier `E_*` → `rag_status()` + reportar el `fix_hint`, no el error crudo);
no-contaminación (WARN si hay archivos del usuario en bandejas 01-05); formato de cita
`source_path » heading (chars x–y)`; cláusula "el AGENTS.md del vault manda y es editable".

**Pochteca** (`/research`; desviación documentada del UH — D9.3):

```yaml
permissions:
  - {action: "edit", resource: "*", effect: "deny"}
  - {action: "subagent", resource: "*", effect: "deny"}
  - {action: "shell", resource: "*", effect: "deny"}
  - {action: "read", resource: "*", effect: "allow"}
  - {action: "glob", resource: "*", effect: "allow"}
  - {action: "grep", resource: "*", effect: "allow"}
  - {action: "skill", resource: "*", effect: "allow"}
  - {action: "webfetch", resource: "*", effect: "allow"}
  - {action: "websearch", resource: "*", effect: "allow"}
  - {action: "edit", resource: "01-tasks/research/**", effect: "allow"}
```

Único write surface del diseño: `01-tasks/research/**` — toda nota con frontmatter
{agent, timestamp, fuentes, método} obligatorio. El resto del vault: negado.

**Nezahualcóyotl** (`/rubric`, `/synthesize`):

```yaml
permissions:
  - {action: "edit", resource: "*", effect: "deny"}
  - {action: "subagent", resource: "*", effect: "deny"}
  - {action: "read", resource: "*", effect: "allow"}
  - {action: "glob", resource: "*", effect: "allow"}
  - {action: "grep", resource: "*", effect: "allow"}
  - {action: "skill", resource: "*", effect: "allow"}
  - {action: "webfetch", resource: "*", effect: "deny"}
  - {action: "websearch", resource: "*", effect: "deny"}
  - {action: "edit", resource: "01-tasks/**", effect: "allow"}
  - {action: "edit", resource: "01-tasks/research/**", effect: "deny"}
```

El deny de `research/**` va DESPUÉS del allow (last-match): su bandeja es el root de `01-tasks/`
(rúbricas, planes, outlines); la sub-bandeja de evidencia es exclusiva de Pochteca. Sin web (UH).

**Chilam** (`/validate`, `/cite`, `/review`):

```yaml
permissions:
  - {action: "edit", resource: "*", effect: "deny"}
  - {action: "subagent", resource: "*", effect: "deny"}
  - {action: "read", resource: "*", effect: "allow"}
  - {action: "glob", resource: "*", effect: "allow"}
  - {action: "grep", resource: "*", effect: "allow"}
  - {action: "skill", resource: "*", effect: "allow"}
  - {action: "webfetch", resource: "*", effect: "deny"}
  - {action: "websearch", resource: "*", effect: "deny"}
  - {action: "edit", resource: "03-citations/**", effect: "allow"}
  - {action: "edit", resource: "04-review/**", effect: "allow"}
```

Audita lo recolectado, no investiga fuente nueva (trazabilidad: web negada); informes en
`04-review/` con frontmatter {command, agent, target_doc, verdict}.

**Tlacuilo** (`/draft`, `/transform`, `/update`) — estilo deny-list (UH: "permisos exclusivos para
crear/sobrescribir los archivos finales"):

```yaml
permissions:
  - {action: "subagent", resource: "*", effect: "deny"}
  - {action: "shell", resource: "*", effect: "deny"}
  - {action: "webfetch", resource: "*", effect: "deny"}
  - {action: "websearch", resource: "*", effect: "deny"}
  - {action: "read", resource: "*", effect: "allow"}
  - {action: "glob", resource: "*", effect: "allow"}
  - {action: "grep", resource: "*", effect: "allow"}
  - {action: "skill", resource: "*", effect: "allow"}
  - {action: "edit", resource: "*", effect: "allow"}
  - {action: "edit", resource: ".obsidian/**", effect: "deny"}
  - {action: "edit", resource: ".opencode/**", effect: "deny"}
  - {action: "edit", resource: ".tepochcalli/**", effect: "deny"}
  - {action: "edit", resource: "00-Resources/**", effect: "deny"}
  - {action: "edit", resource: "01-tasks/**", effect: "deny"}
  - {action: "edit", resource: "03-citations/**", effect: "deny"}
  - {action: "edit", resource: "04-review/**", effect: "deny"}
```

Sus superficies efectivas: `02-drafts/`, `05-outputs/` y los finales que el usuario pida en sus
carpetas (10+). Sin navegación web (UH); shell deny (las exportaciones las hacen las skills).

**Itzamná** (default_agent; orquestador — verificar que el nombre coincide con
`default_agent: "itzamna"` en `opencode.json`, archivo `itzamna.md` sin acento):

```yaml
permissions:
  - {action: "edit", resource: "*", effect: "deny"}
  - {action: "subagent", resource: "*", effect: "deny"}
  - {action: "shell", resource: "*", effect: "deny"}
  - {action: "read", resource: "*", effect: "allow"}
  - {action: "glob", resource: "*", effect: "allow"}
  - {action: "grep", resource: "*", effect: "allow"}
  - {action: "skill", resource: "*", effect: "allow"}
```

Enrutamiento por comandos, no spawns: `subagent * deny` deja los ~165 subagents Códice catalogados
pero NO invocables (los archivos se CONSERVAN por decisión del usuario; pureza de la sesión de
investigación). Edit deny: su salida es análisis/enrutamiento/estado.

### Nota de fusión con `opencode.json` (verificación Phase 4, sin duplicar)

* `permissions` SOLO en los `.md` de agentes: verificar que el bloque `agents` de `opencode.json`
  no traiga arrays de permisos que colisionen con el spine anterior.
* `model` (y `steps`/`color`) pueden quedarse en el `agents` de `opencode.json`; en ese caso NO se
  duplican en el frontmatter del `.md`. Un solo lugar por campo.
* `default_agent` debe resolver a `itzamna` (nombre de archivo real).
* `mcp.servers` para `tepochcalli-rag` y `markitdown`: los añade el wizard (fase 8,
  spec-installer-wizard §Merge) — el payload NO los pre-carga.

### Blueprint de los 9 comandos (mapeo D9.2 — frontmatter: `description` no vacío + `agent`)

| Comando | `agent:` | Bandeja destino | Contract del cuerpo |
|---|---|---|---|
| `/rubric` | nezahualcoyotl | `01-tasks/` | matriz: pregunta central, objetivos, alcance, criterios inclusión/exclusión, metodología (UH Definición) |
| `/research` | pochteca | `01-tasks/research/` | evidencia con frontmatter {agent, timestamp, fuentes, método}; search + web según rúbrica |
| `/validate` | chilam | `04-review/` | informe con frontmatter {command, agent, target_doc, verdict}; contradicciones/sesgos/obsolescencia |
| `/synthesize` | nezahualcoyotl | `01-tasks/` | ejes temáticos + outline sobre evidencia validada |
| `/cite` | chilam | `03-citations/` | formato APA\|MLA\|Chicago vía `$1` (default APA); trazabilidad afirmación→fuente |
| `/draft` | tlacuilo | `02-drafts/` | redacción siguiendo outline + citas; conserva formato de cita |
| `/review` | chilam | `04-review/` | revisión por pares del `$1` en `02-drafts/`; veredicto, sin editar el borrador |
| `/transform` | tlacuilo | `05-outputs/` | CSV/Excel, presentación, mapa mental, figuras — solo skills existentes hoy |
| `/update` | tlacuilo | `02-drafts/` | localizar `$1` en `02-drafts/` e inyectar `$ARGUMENTS` sin reiniciar el flujo |

Skeleton obligatorio de cada cuerpo (≤35 líneas, español): uso explícito de `$ARGUMENTS` y/o `$1`;
fase metodológica UH nombrada; MCP-first con los 4 tools y protocolo `E_*`→`rag_status`; destino
de escritura = SU bandeja del mapa + frontmatter contract cuando aplique; cita
`source_path » heading (chars x–y)`; no-contaminación donde lee bandejas. Prohibido: `!`cmd`` y
`@paths`.

Regla de skills en `/transform`: citar SOLO skills presentes hoy en `.opencode/skills/` (Phase 4
hace ls de verificación): `xlsx`/`excel-analysis`/`data-transform` (CSV/Excel),
`scientific-slides`/`pptx-official` (presentaciones), `markdown-mermaid-writing` (mapa mental vía
`mindmap` de Mermaid), `matplotlib`/`plotly`/`seaborn`/`scientific-visualization` (figuras),
`markitdown` (conversión). Gaps Jupyter / R / Graphviz-PlantUML / LaTeX-manuscrito: declarados
como pendientes del Anexo A (su instalación NO es labor de esta spec); el comando los menciona como
"pendiente Phase 4" sin inventar nombres.

### Blueprint `AGENTS.md` del vault (≤120 líneas; system prompt distribuido)

Siete secciones obligatorias:

1. **Qué es este vault** — 1 párrafo (Obsidian + OpenCode V2 + RAG local; metodología 9/5).
2. **Zonas de propiedad (D9.1)** — matriz compacta: `00-Resources/` = entrada del usuario (única
   indexable); `01-…-05-…` = bandejas del agente (leer/extraer/borrar OK; NO depositar/editar;
   `01-tasks/research/` nombrada explícitamente); `10+` = biblioteca personal (no indexada v1);
   `.tepochcalli/`/`.opencode/` = no tocar. Regla **no-contaminación** con el WARN del agente.
3. **Regla MCP-first** — los 4 tools (`search`, `index_refresh`, `add_source`, `rag_status`),
   presupuesto `top_k` ≤ 8, protocolo `E_*` → `rag_status()` → reportar `fix_hint`.
4. **Mapa comando→agente→bandeja** — tabla de 9 filas, espejo D9.2.
5. **Reglas de cita y trazabilidad** — formato, fuentes web con URL+fecha, contenido externo no
   confiable (anti prompt-injection).
6. **Formato de notas** — Obsidian markdown + YAML frontmatter; los dos contratos
   {agent, timestamp, fuentes, método} y {command, agent, target_doc, verdict}.
7. **Cláusula de edición** — el archivo es del usuario, editable; el wizard no lo sobreescribe;
   manda sobre los prompts de `.opencode/agents/` (UH §wizard/AGENTS).

## Alternatives Considered

* **Ejecutar el rediseño del payload ahora (bajo /spec):** *rechazado:* el usuario corrigió el
  despacho — `obsidian-workspace/` intocable fuera de Phase 4; el contenido vive como blueprint.
* **Convertir el blueprint en un ADR:** *rechazado:* no es una decisión nueva — D9/ADR-005/007 ya
  están Accepted; esto es documentación de ejecución (spec).
* **Itzamná invocando subagents para "enrutar":** *rechazado:* viola la pureza de la sesión y el
  patrón V2 nativo (`agent:` en comandos cambia la sesión al primary).

## Trade-offs

* ✅ **Pros:** blueprint congelado y grepeable; Phase 4 se vuelve mecánica; permisos como datos por archivo; payload coherente con D9.
* ⚠️ **Cons / Risks:** dos fuentes (esta spec + stubs actuales) hasta Phase 4 — el drift se corta con los criterios de aceptación; el deny-list de Tlacuilo depende de mantener el orden last-match.
* ⚖️ **Neutral:** los ~165 subagents Códice quedan en disco, no invocables — catálogo inerte.

## Testing Strategy — criterios de aceptación de la ejecución Phase 4

Linkables desde docs/WORKFLOW.md Phase 4 ("Validación del agent workflow (D9)"):

* Los permission fixtures de spec-agent-workflow §Testing (D9.3) y la methodology e2e (D9.1/D9.2)
  pasan sobre el payload generado por ESTE blueprint: escritura de Pochteca solo bajo
  `01-tasks/research/**`, denegada en todo lo demás; Chilam solo `03-citations/**`+`04-review/**`;
  Tlacuilo/Nezahualcóyotl sin web; Itzamná sin edit.
* Greps de no-regresión: cero campos legacy (`temperature|top_p|prompt:|permission:|tools:|maxSteps`
  en frontmatter de `.md`), cero skills inventadas referenciadas (todo nombre citado existe en el
  ls de `.opencode/skills/`), `default_agent` resuelve a `itzamna`, ningún `.md` duplica `model`
  que ya define `opencode.json`.
* Cada archivo: agent ≤60 líneas, command ≤35 líneas, `AGENTS.md` del vault ≤120 líneas.

## Security Considerations

* Sin bloques `!`cmd`` en comandos (inyección vía args). Contenido web/externo = no confiable.
* Ningún agente lee `.tepochcalli/config/` (claves) ni escribe `.obsidian/`. Separación de poderes
  por permisos de archivo, no por prompt.

## Rollback / Monitoring

* El payload es texto versionado: rollback = `git checkout` del archivo. Tras la ejecución Phase 4,
  smoke: sesión nueva, `/rubric`, y verificar `opencode agents list` + routing real.
* Señal de deriva: cualquier diff de `.opencode/agents/*.md` que no cite esta spec en el commit.

## Open Questions

* ¿El array global `permissions` de `opencode.json` (higiene heredada del pack Códice) se elimina
  al ejecutar el blueprint para que los permisos queden SOLO en los `.md`? (verificación exigida
  por §Nota de fusión; decisión al ejecutar Phase 4)

## References

* OpenCode V2 docs (agents/commands/permissions) — verificación 2026-10-21
* specs/spec-agent-workflow.md (D9.2/D9.3, Anexo A), specs/spec-vault-structure.md (D9.1),
  specs/spec-mcp-server.md (contrato 4 tools + `E_*`), docs/UH.md (tabla Agentes Primarios),
  docs/WORKFLOW.md Phase 4
