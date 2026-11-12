# Spec: Permisos de los 5 agentes del payload (OpenCode V2)

* **Status:** Approved (BLUEPRINT APPROVED 2026-11-09 — gate concedido por congelamiento del dueño: 40 skills definitivas, `cf17f31`/`2e62e60`) · **Enmendada 2026-11-11** ([ADR-012](adr-012-formato-payload-revisado.md): bloques inline + global 313 reglas; D-P4-2 SUPERSEDED — ver §Enmienda 2026-11-11 al final) · **Enmendada 2026-11-12** (alineación con el bloque global — ver §Enmienda 2026-11-12)
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
  - action: edit
    resource: ".git/**"
    effect: deny
  - action: edit
    resource: "AGENTS.md"
    effect: deny
  - action: edit
    resource: "opencode.json"
    effect: deny
  - action: edit
    resource: "tepochcalli.toml"
    effect: deny
```

Sus superficies efectivas: `02-drafts/`, `05-outputs/` y los finales que el usuario pida en sus
carpetas (10+). Sin navegación web (UH); shell deny (las exportaciones las hacen las skills). La
lista de deny va ENTERA detrás de `edit * allow`: mover una línea cambia la política. Los cuatro
últimos denies protegen la gobernanza del vault (`.git/`, `AGENTS.md`, `opencode.json`,
`tepochcalli.toml`): sin ellos, `edit * allow` dejaría a Tlacuilo reescribir el fichero que dice
mandar sobre su prompt o la config del harness.

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

## Verificación (simulación last-match-wins)

Simulación ejecutada el 2026-11-04 con el intérprete del §Semántica de `permissions` (glob `*`
cruza `/`, `?` = un carácter, sin coincidencia ⇒ `ask`). 42 probes, 42/42 esperado == real:

| Agente | Probes | Casos clave (esperado → real) |
| --- | --- | --- |
| Pochteca | 9 | `edit 01-tasks/research/x.md` allow → allow · `edit 02-drafts/x.md` deny → deny |
| Nezahualcóyotl | 6 | `edit 01-tasks/research/x.md` deny → deny · `edit 01-tasks/plan.md` allow → allow |
| Chilam | 6 | `edit 03-citations/x.md` allow → allow · `edit 02-drafts/x.md` deny → deny |
| Tlacuilo | 15 | `edit 05-outputs/x.csv` allow → allow · `edit 00-Resources/x.md` deny → deny · `edit AGENTS.md` deny → deny · `edit opencode.json` deny → deny · `edit .git/config` deny → deny |
| Itzamná | 6 | `edit` cualquiera deny → deny |

Lectura de secretos en los 5: `.env`, `sub/.env`, `.env.local`, `config/.env`, `secrets.env` →
`deny`; `.tepochcalli/config/tepochcalli.toml` → `deny`. Sin reglas muertas.

## Enmienda 2026-11-11 — formato revisado ([ADR-012](adr-012-formato-payload-revisado.md))

Los bloques de arriba quedan como **diseño histórico Phase 4**: el payload real
(`b4cc8ff`..`1ce44ca`) lleva **permisos inline verificados por agente** (edit acotado por
bandeja, web/subagent/shell según rol — ver mensajes de commit) y **array global de 313
reglas** anti-destructivo en `opencode.json`. **D-P4-2 SUPERSEDED**: la política efectiva
vuelve a ser `global ++ bloque` (last-match-wins); los bloques inline se verificaron
contra ese global. La §Nota de fusión se lee invertida: sin array no hay política
completa; si el global cambia, re-verificar los 5 bloques. D-P4-3 intacta (sin reglas
`<server>_<tool>` por agente).

## Enmienda 2026-11-12 — la política de secretos vive en el bloque global

**Decisión del dueño (2026-11-12).** Phase 6 alinea spec y tests al **payload actual**: la política de secretos vive en el array `permissions` de `obsidian-workspace/opencode.json` (313 reglas); **el payload no se toca** (D-P6-1).

**Hecho medido.** `grep '"action": "read"'` sobre los 5 `.opencode/agents/*.md` = **0** reglas `read`; el global tiene **41** (índices 272–312).

**Semántica efectiva: `global ++ agente`.** Las reglas globales se cargan primero y las del
agente se **añaden al final** (no lo reemplazan); gana la última que casa. Un `deny` global
**no se reabre** porque los 5 bloques no declaran ninguna regla `read`: el único `read` que
casa con cualquier ruta es el global `* allow` (1506) o un `deny` posterior más específico.

**Reglas `read` del global (literal, `opencode.json:línea`).**

```text
1506 `*` allow · 1512 `*.env` deny · 1517 `*.env.*` deny
1522 `*.env.example` allow · 1527 `.npmrc` deny · 1532 `*.pem` deny
1537 `*.key` deny · 1542 `*.p12` deny · 1547 `*.pfx` deny
1552 `credentials.json` deny · 1557 `*x-session-cookies*` deny · 1562 `.cargo/credentials` deny
1567 `service-account*.json` deny · 1572 `.ssh/id_*` deny · 1577 `.ssh/config` deny
1582 `.aws/credentials` deny · 1587 `.kube/config` deny · 1592 `.netrc` deny
1597 `.pgpass` deny · 1602 `.git-credentials` deny · 1607 `.s3cfg` deny
1612 `.config/gh/hosts.yml` deny · 1617 `.docker/config.json` deny · 1622 `*.gpg` deny
1627 `*.ovpn` deny · 1632 `*.mobileprovision` deny · 1637 `*id_rsa*` deny
1642 `*id_ed25519*` deny · 1647 `*id_ecdsa*` deny · 1652 `*.envrc*` deny
1657 `**/.npmrc` deny · 1662 `credentials.json*` deny · 1667 `**/credentials.json` deny
1672 `**/service-account*.json` deny · 1677 `**/.aws/credentials` deny · 1682 `**/.kube/config` deny
1687 `**/.netrc` deny · 1692 `**/.pgpass` deny · 1697 `**/.git-credentials` deny
1702 `**/.cargo/credentials` deny · 1707 `*docker/config.json*` deny
```

**Cobertura real de secretos.** Con `read * allow` (1506) siempre casando, el efecto `read`
**nunca** cae en el default `ask`: o un `deny` posterior lo cubre, o queda `allow`.

| Ruta | Efecto | Regla que decide |
| --- | --- | --- |
| `.env`, `.env.local`, `sub/.env`, `config/.env`, `secrets.env` | deny | `*.env` / `*.env.*` (1512/1517) |
| `.env.example` | allow | excepción última `*.env.example` (1522) |
| `*.pem`, `*.key`, `*.p12`, `*.pfx`, `*.gpg`, `*.ovpn`, `*.mobileprovision`, `*.envrc*`, `credentials.json*`, `service-account*.json`, `*x-session-cookies*`, `id_rsa`/`id_ed25519`/`id_ecdsa` | deny | listado (1527–1662) |
| `.ssh/*`, `.aws/credentials`, `.kube/config`, `.netrc`, `.pgpass`, `.git-credentials`, `.s3cfg`, `.cargo/credentials`, `.docker/config.json`, `.config/gh/hosts.yml` | deny | listado (1562–1712) |
| **`.tepochcalli/config/**`** (p. ej. `tepochcalli.toml`) | **allow — GAP** | sin regla específica ⇒ `* allow` (1506) |

**SUPERSEDED.** Las reglas inline `read *.env deny`, `read *.env.* deny` y `read .tepochcalli/config/** deny` de los §Blueprint y los probes de §Verificación que las usaban quedan **SUPERSEDED** por esta enmienda. El diseño Phase 4 se conserva como historia; la política vigente es la de arriba (mismo patrón que [ADR-012](adr-012-formato-payload-revisado.md)).

**GAP declarado: `.tepochcalli/config/**` ⇒ `allow`.** El global no incluye esa ruta y el último `read` que casa es `* allow` (1506) — **no** `ask`, como se creía antes de medir. Consecuencia: un agente puede leer `tepochcalli.toml` (claves del embedder) sin confirmación. Cerrarlo exige **una regla global nueva** (`{action: read, resource: ".tepochcalli/config/**", effect: deny}`) después de `read * allow` y antes de `*.env.example`: cambio de payload, no autorizado en Phase 6. El test lo declara como GAP (`test_tepochcalli_config_is_a_declared_gap`), no como fallo.
