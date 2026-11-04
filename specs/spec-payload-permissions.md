# Spec: Permisos de los 5 agentes del payload (OpenCode V2)

* **Status:** Proposed (gate: BLUEPRINT APPROVED por el usuario)
* **Fase:** Phase 4 (diseño) — especificación hermana de [specs/spec-payload-vault.md](spec-payload-vault.md) (D-P4-4/D-P4-11); Phase 5 ejecuta literal
* **Date:** 2026-11-04
* **Author:** Arquitecto (calpulli T4, Phase 4)
* **Reviewers:** Product Owner (usuario)
* **Traceability:** [specs/spec-payload-vault.md](spec-payload-vault.md) (§Reglas de formato y §Semántica de `permissions`, verificadas v2.1.2 el 2026-11-04), [specs/spec-payload-skills.md](spec-payload-skills.md) (§Tabla de invocación 9×4 — fija qué edita cada comando), [specs/spec-agent-workflow.md](spec-agent-workflow.md) (D9.2 bandejas, D9.3 desviación de Pochteca), [docs/UH.md](../docs/UH.md) (tabla Agentes Primarios — inmutable), [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)

## Summary

Esta spec es dueña de la **frontera de seguridad** del payload: el frontmatter y el bloque
`permissions` de los 5 agentes primarios (`.opencode/agents/{itzamna,nezahualcoyotl,pochteca,chilam,tlacuilo}.md`).
Los cuerpos (system prompts) viven en [specs/spec-payload-agents.md](spec-payload-agents.md) (T5); aquí
solo se fija el header y la superficie de escritura. **No se escribe nada en `obsidian-workspace/` en
esta fase.**

## Detailed Design

## Blueprint de permisos por agente (YAML; cuerpo ≤60 líneas por archivo, inglés — D-P4-6)

Los cinco archivos comparten el mismo contrato de frontmatter: `description` entrecomillado en
inglés con patrón «Name - Role» (D-P4-8), `mode: primary` explícito y **sin `model`** (vive en
`opencode.json`, §Nota de fusión). El nombre de archivo es el ID del agente; `default_agent` de
`opencode.json` debe resolver a `itzamna` (visible, sin `hidden`) — nombres sin acento:

| Archivo | `description` literal |
| --- | --- |
| `itzamna.md` | `"Itzamna - Supreme Orchestrator"` |
| `nezahualcoyotl.md` | `"Nezahualcoyotl - The Architect"` |
| `pochteca.md` | `"Pochteca - The Explorer"` |
| `chilam.md` | `"Chilam - The Auditor"` |
| `tlacuilo.md` | `"Tlacuilo - The Engineer"` |

Cada cuerpo (system prompt, inglés, ≤60 líneas) incluye: persona UH (1-2 líneas); propósito en el
workflow con su bandeja exacta; MCP-first (`search` de `tepochcalli-rag` antes de lectura cruda de
`00-Resources/`, `index_refresh()` con dudas de frescura, ante cualquier `E_*` → `rag_status()` +
reportar el `fix_hint`, no el error crudo); no-contaminación (WARN si hay archivos del usuario en
bandejas 01-05); formato de cita `source_path » heading (chars x–y)`; cláusula "el AGENTS.md del
vault manda y es editable".

**Orden = política.** Las reglas se resuelven por last-match-wins ([§Semántica de `permissions`](spec-payload-vault.md#semántica-de-permissions) en el blueprint):
regla amplia primero, excepción específica AL FINAL. Un `deny` amplio delante de un `allow`
estrecho no basta — el `allow` tiene que ser la última regla que case con el recurso. Cada bloque
reintroduce la higiene que hoy vive en el array global de 313 reglas (§Nota de fusión, D-P4-2) para
que borrarlo no reabra nada: `external_directory` deny (frontera del vault, se evalúa antes de
`read`/`edit`) y las denegaciones de lectura de secretos — `*.env` y `*.env.*` ya estaban en el
array; `.tepochcalli/config/**` no, y se añade aquí porque es donde viven las claves del motor.
Son necesarias porque `read * allow` va después del `ask` de la política base para `.env`.

**Pochteca** (`/research`; desviación documentada del UH — D9.3) — `"Pochteca - The Explorer"`:

```yaml
permissions:
  - action: external_directory
    resource: "*"
    effect: deny
  - action: edit
    resource: "*"
    effect: deny
  - action: subagent
    resource: "*"
    effect: deny
  - action: shell
    resource: "*"
    effect: deny
  - action: read
    resource: "*"
    effect: allow
  - action: glob
    resource: "*"
    effect: allow
  - action: grep
    resource: "*"
    effect: allow
  - action: skill
    resource: "*"
    effect: allow
  - action: question
    resource: "*"
    effect: allow
  - action: todowrite
    resource: "*"
    effect: allow
  - action: lsp
    resource: "*"
    effect: allow
  - action: webfetch
    resource: "*"
    effect: allow
  - action: websearch
    resource: "*"
    effect: allow
  - action: read
    resource: "*.env"
    effect: deny
  - action: read
    resource: "*.env.*"
    effect: deny
  - action: read
    resource: ".tepochcalli/config/**"
    effect: deny
  - action: edit
    resource: "01-tasks/research/**"
    effect: allow
```

Único write surface del diseño: `01-tasks/research/**` — toda nota con frontmatter
{agent, timestamp, fuentes, método} obligatorio. El resto del vault: negado porque `edit *`
deny va antes y la excepción va última.

**Nezahualcóyotl** (`/rubric`, `/synthesize`) — `"Nezahualcoyotl - The Architect"`:

```yaml
permissions:
  - action: external_directory
    resource: "*"
    effect: deny
  - action: edit
    resource: "*"
    effect: deny
  - action: subagent
    resource: "*"
    effect: deny
  - action: shell
    resource: "*"
    effect: deny
  - action: webfetch
    resource: "*"
    effect: deny
  - action: websearch
    resource: "*"
    effect: deny
  - action: read
    resource: "*"
    effect: allow
  - action: glob
    resource: "*"
    effect: allow
  - action: grep
    resource: "*"
    effect: allow
  - action: skill
    resource: "*"
    effect: allow
  - action: question
    resource: "*"
    effect: allow
  - action: todowrite
    resource: "*"
    effect: allow
  - action: lsp
    resource: "*"
    effect: allow
  - action: read
    resource: "*.env"
    effect: deny
  - action: read
    resource: "*.env.*"
    effect: deny
  - action: read
    resource: ".tepochcalli/config/**"
    effect: deny
  - action: edit
    resource: "01-tasks/**"
    effect: allow
  - action: edit
    resource: "01-tasks/research/**"
    effect: deny
```

El deny de `research/**` va DESPUÉS del allow (last-match): su bandeja es el root de `01-tasks/`
(rúbricas, planes, outlines); la sub-bandeja de evidencia es exclusiva de Pochteca. Sin web (UH).

**Chilam** (`/validate`, `/cite`, `/review`) — `"Chilam - The Auditor"`:

```yaml
permissions:
  - action: external_directory
    resource: "*"
    effect: deny
  - action: edit
    resource: "*"
    effect: deny
  - action: subagent
    resource: "*"
    effect: deny
  - action: shell
    resource: "*"
    effect: deny
  - action: webfetch
    resource: "*"
    effect: deny
  - action: websearch
    resource: "*"
    effect: deny
  - action: read
    resource: "*"
    effect: allow
  - action: glob
    resource: "*"
    effect: allow
  - action: grep
    resource: "*"
    effect: allow
  - action: skill
    resource: "*"
    effect: allow
  - action: question
    resource: "*"
    effect: allow
  - action: todowrite
    resource: "*"
    effect: allow
  - action: lsp
    resource: "*"
    effect: allow
  - action: read
    resource: "*.env"
    effect: deny
  - action: read
    resource: "*.env.*"
    effect: deny
  - action: read
    resource: ".tepochcalli/config/**"
    effect: deny
  - action: edit
    resource: "03-citations/**"
    effect: allow
  - action: edit
    resource: "04-review/**"
    effect: allow
```

Audita lo recolectado, no investiga fuente nueva (trazabilidad: web negada); informes en
`04-review/` con frontmatter {command, agent, target_doc, verdict}.

**Tlacuilo** (`/draft`, `/transform`, `/update`) — deny-list (UH: "permisos exclusivos para
crear/sobrescribir los archivos finales") — `"Tlacuilo - The Engineer"`:

```yaml
permissions:
  - action: external_directory
    resource: "*"
    effect: deny
  - action: subagent
    resource: "*"
    effect: deny
  - action: shell
    resource: "*"
    effect: deny
  - action: webfetch
    resource: "*"
    effect: deny
  - action: websearch
    resource: "*"
    effect: deny
  - action: read
    resource: "*"
    effect: allow
  - action: glob
    resource: "*"
    effect: allow
  - action: grep
    resource: "*"
    effect: allow
  - action: skill
    resource: "*"
    effect: allow
  - action: question
    resource: "*"
    effect: allow
  - action: todowrite
    resource: "*"
    effect: allow
  - action: lsp
    resource: "*"
    effect: allow
  - action: read
    resource: "*.env"
    effect: deny
  - action: read
    resource: "*.env.*"
    effect: deny
  - action: read
    resource: ".tepochcalli/config/**"
    effect: deny
  - action: edit
    resource: "*"
    effect: allow
  - action: edit
    resource: ".obsidian/**"
    effect: deny
  - action: edit
    resource: ".opencode/**"
    effect: deny
  - action: edit
    resource: ".tepochcalli/**"
    effect: deny
  - action: edit
    resource: "00-Resources/**"
    effect: deny
  - action: edit
    resource: "01-tasks/**"
    effect: deny
  - action: edit
    resource: "03-citations/**"
    effect: deny
  - action: edit
    resource: "04-review/**"
    effect: deny
```

Sus superficies efectivas: `02-drafts/`, `05-outputs/` y los finales que el usuario pida en sus
carpetas (10+). Sin navegación web (UH); shell deny (las exportaciones las hacen las skills). La
lista de deny va ENTERA detrás de `edit * allow`: mover una línea cambia la política.

**Itzamná** (default_agent; orquestador — verificar que el nombre coincide con
`default_agent: "itzamna"` en `opencode.json`, archivo `itzamna.md` sin acento) —
`"Itzamna - Supreme Orchestrator"`:

```yaml
permissions:
  - action: external_directory
    resource: "*"
    effect: deny
  - action: edit
    resource: "*"
    effect: deny
  - action: subagent
    resource: "*"
    effect: deny
  - action: shell
    resource: "*"
    effect: deny
  - action: webfetch
    resource: "*"
    effect: deny
  - action: websearch
    resource: "*"
    effect: deny
  - action: read
    resource: "*"
    effect: allow
  - action: glob
    resource: "*"
    effect: allow
  - action: grep
    resource: "*"
    effect: allow
  - action: skill
    resource: "*"
    effect: allow
  - action: question
    resource: "*"
    effect: allow
  - action: todowrite
    resource: "*"
    effect: allow
  - action: lsp
    resource: "*"
    effect: allow
  - action: read
    resource: "*.env"
    effect: deny
  - action: read
    resource: "*.env.*"
    effect: deny
  - action: read
    resource: ".tepochcalli/config/**"
    effect: deny
```

Enrutamiento por comandos, no spawns: `subagent * deny` deja los ~165 subagents Códice catalogados
pero NO invocables (los archivos se CONSERVAN por decisión del usuario; pureza de la sesión de
investigación). Edit deny: su salida es análisis/enrutamiento/estado. Sin web: no investiga.

## Nota de fusión con `opencode.json` (verificación en Phase 5, sin duplicar)

* **D-P4-2 — Phase 5 elimina el array global `permissions` de 313 reglas** de
  `obsidian-workspace/opencode.json`. Razón (orden de fusión): «Lower-priority configuration is
  loaded first, global rules are appended next, and **agent rules are appended last**» y «Agent
  rules are appended after global rules; **they do not replace the global array**»
  ([permissions.mdx](https://github.com/anomalyco/opencode/blob/v2.1.2/services/www/src/docs/content/permissions.mdx)).
  La política efectiva de cada agente es la concatenación `313 globales ++ bloque del agente`, no
  el bloque: cualquier `allow` global que el bloque no vuelva a declarar sigue siendo el efecto
  efectivo y ensancha la superficie del agente en silencio. Por eso el array se borra y los dos
  grupos que aportaba y que el bloque necesita —`external_directory` deny y las denegaciones de
  lectura de secretos— se declaran DENTRO de cada bloque (§Blueprint de permisos). Con array hay
  dos fuentes y decide el orden; sin array, el bloque es la política completa y auditable.
* `permissions` SOLO en los `.md` de agentes: el bloque `agents` de `opencode.json` no lleva
  arrays de permisos (hoy: `model`, `color`, `request`, `steps`).
* `model` (y `steps`/`color`) se quedan SOLO en el `agents` de `opencode.json`; no se duplican en
  el frontmatter del `.md`. Un solo lugar por campo.
* `default_agent` debe resolver a `itzamna`: archivo real `itzamna.md` (sin acento), agente
  visible (sin `hidden`) y `mode: primary`.
* `mcp.servers` para `tepochcalli-rag`: los añade el wizard (fase 8, spec-installer-wizard
  §Merge) — el payload NO los pre-carga.
* **Divergencia deliberada con `agent_example.md` (D-P4-8):** la guía usa `subagent * allow` y
  luego deniega por nombre; los 5 primarios usan `subagent * deny` sin excepción. Motivo: la guía
  es una plantilla de desarrollo general que delega en un catálogo de especialistas, mientras este
  payload es una metodología cerrada de 5 roles en la que ningún comando necesita subagente
  ([spec-payload-skills](spec-payload-skills.md) §Tabla de invocación: «ninguno» en las 9 filas).
  Los ~165 subagents del pack Códice quedan catalogados pero inertes (D9). De la guía se copia la
  FORMA (bloque `action`/`resource`/`effect`, house actions, `description` «Name - Role»), no la
  política.
* **Sin reglas `<server>_<tool>` por agente (D-P4-3):** qué tool MCP usa cada rol lo fija el
  system prompt, no `permissions`. Riesgo aceptado, con su blast radius, en §Trade-offs.
