# Phase 5 — Baseline del payload y auditoría de divergencias (T0)

> **Fecha:** 2026-11-09 · **Ejecutor:** T0 (read-only) · **Fase:** Phase 5 — Payload + Skills audit
> **Alcance:** medir `obsidian-workspace/` contra el blueprint Approved de Phase 4
> (`specs/spec-payload-{vault,skills,permissions,agents,commands}.md`) y contra `tasks/plan.md` §2
> (D-P5-1..D-P5-9). **Cero escrituras** dentro de `obsidian-workspace/`: el único fichero de esta
> tarea es este informe. Toda cifra lleva su comando; cuando un comando falló se transcribe el error
> tal cual (no hubo ninguno).

## Números base

| Hecho | Valor medido | Comando |
| --- | --- | --- |
| Skills del payload | **40 dirs** | `ls obsidian-workspace/.opencode/skills \| wc -l` |
| Agentes del payload | **170 `.md`** (5 primarios + 165 del pack Códice) | `find obsidian-workspace/.opencode/agents -name '*.md' \| wc -l` |
| Comandos del payload | **9 `.md`**, 4 líneas cada uno (36 en total) | `wc -l obsidian-workspace/.opencode/commands/*.md` |
| Agentes primarios | **5**: itzamna 135 · nezahualcoyotl 104 · pochteca 114 · chilam 84 · tlacuilo 83 (520 total) | `grep -l "mode: primary" … \| xargs wc -l` |
| `AGENTS.md` del vault | **79 líneas** (template genérico con placeholders) | `wc -l obsidian-workspace/AGENTS.md` |
| `permissions` global en `opencode.json` | **313 reglas** (shell 265 · read 41 · external_directory 6 · subagent 1; deny 204 · allow 93 · ask 16) | `python3 -c "json.load(...)['permissions']"` |
| Baseline de linters | **0 issues** en 39 ficheros | `just md-lint` |

Cifras de apoyo de la misma pasada: `default_agent = itzamna` (correcto); `instructions` = **4 rutas
relativas al repo** (divergencia D-4); `agents` de `opencode.json` = `build, chilam, explore,
general, itzamna, nezahualcoyotl, plan, pochteca, tlacuilo`; `00-Resources/` = **0 ficheros**;
`01-Tasks/` = 3 ficheros de **0 bytes**; **no existe `.gitignore`** en el payload.

**No-divergencia verificada (para no inflarla):** el techo de *cuerpo* ≤60 líneas (spec-payload-vault,
D-P4-6) **se cumple** en los 5 agentes (58/27/37/37/36 líneas de cuerpo sin frontmatter). Los ficheros
superan 60 líneas por el bloque YAML de permisos, que la spec cuenta aparte. `description` coincide con
el literal congelado en los 5 y ninguno declara `model` en frontmatter. El contrato de *forma* está
sano; lo divergente es la *política*.

## Divergencias blueprint ↔ payload

| id | Divergencia | Evidencia / comando | Decisión que la cubre |
| --- | --- | --- | --- |
| **D-1** | **8 skills citadas por el blueprint no existen** en el `ls` de 40: `xlsx-official`, `excel-analysis`, `scientific-slides`, `pptx-official`, `matplotlib`, `scientific-visualization`, `infographics`, `markitdown`. `spec-payload-commands.md:270` dice *"Use only skills that exist today"* enumerando 7 de ellas. Afecta a `/transform` y a Tlacuilo. | `test -d` por nombre → 8 × `MISSING`; `grep -n` en `spec-payload-commands.md:270` y `spec-payload-agents.md:322,414` | **D-P5-2** (enmienda fechada en T1; `.opencode/skills/` intacto) |
| **D-2** | **Los 5 bloques `permissions` no son el blueprint**: falta `external_directory * deny`; faltan en los bloques los denies de lectura de secretos (`*.env`, `*.env.*`, `.tepochcalli/config/**`), que hoy suple el array global (D-3); `subagent * allow` + denies por nombre en 4 de 5 (blueprint: `subagent * deny`); escritura invertida (`edit * allow` en Chilam/Tlacuilo; Pochteca sin `01-tasks/research/**`); `shell` por patrón en vez de `shell * deny`; web permitida a los 5 (solo Pochteca la tiene por D9.3). | diff regla a regla (§Diff de permisos) | **D-P4-3 / D-P4-11** ejecutados en T2-T4 |
| **D-3** | **Array global `permissions` de 313 reglas**. La fusión concatena globales **antes** del bloque y gana la última regla que case, así que el bloque solo manda donde casa: los `allow` globales que ningún bloque redeclara siguen vigentes — `external_directory` `~/.bun/*`, `~/.cargo/*`, `~/go/*`, `~/.cache/*`, `/tmp/opencode/*` (allow) frente al `external_directory * deny` del blueprint; y `read *.env.example` (índice 275) reabre lo que el deny de 274 cierra. Los denies de secretos de los que hoy depende Itzamná (sin `read` en su bloque) viven **solo** en el array: borrarlo sin reintroducirlos en el bloque los elimina. | `len(...['permissions']) == 313` + volcado de las 6 `external_directory` y del `subagent` | **D-P5-4** (borrar el array; T9) + **D-P4-2** |
| **D-4** | **`instructions` con rutas relativas al repo**, no al vault: `obsidian-workspace/.opencode/skills/<skill>/SKILL.md`. Instalado el payload apuntan a `<vault>/obsidian-workspace/...`, que no existe: las 4 skills de contexto no se cargan. | `json.load` → `instructions` | **D-P5-4** (corregir a `.opencode/skills/<skill>/SKILL.md`; T9) |
| **D-5** | **Scaffold incompleto y no canónico**: existe `01-Tasks/` (mayúscula) con 3 ficheros de 0 bytes; **faltan** `01-tasks/`, `01-tasks/research/`, `02-drafts/`, `03-citations/`, `04-review/`, `05-outputs/`; **no hay `.gitignore`**. Sin bandejas, la política por bandeja de D9.2 no tiene destino. | `ls -la obsidian-workspace/` + `ls -la 01-Tasks` | **D-P5-5** (renombrar, nunca crear) + **D-P5-6**; T10 |
| **D-6** | **`AGENTS.md` del vault es template vacío** (`# AGENTS.md — [Project Name]`, `[Rule 1 — describe…]`): sin MCP-first ni no-contaminación. | `grep -n "Describe\|\[.*\]" obsidian-workspace/AGENTS.md` | **D-P4-1 / D-P4-6** + §Blueprint de spec-payload-vault (T8) |
| **D-7** | **Los 9 comandos son stubs** (`description:` vacío + `agent:`), sin cuerpo: el enrutamiento es correcto, la metodología no existe. | `cat obsidian-workspace/.opencode/commands/draft.md` | **D-P4-1** (cuerpos congelados en spec-payload-commands; T5-T7) |

Severidad: **D-2, D-3 y D-4 altas** — cambian la política efectiva de seguridad sin error visible y
sin test que las cubra. **D-1, D-5 y D-6 medias** — el payload instala pero no ejecuta la metodología.
**D-7 baja por sí sola** (stub inerte), alta por consecuencia (sin cuerpo no hay workflow). Ninguna
está corregida: esta es la foto previa a T1-T11.

**Drift interno del blueprint (no del payload), declarado para que no se redescubra:** el inventario
congelado afirma *"0 skills citadas e inexistentes"*, pero las propias specs del payload citan las 8
de D-1. Las dos afirmaciones son incompatibles; D-P5-2 resuelve a favor del `ls` real.

### Diff de permisos (spec vs payload, regla a regla)

Entradas `action/resource/effect` únicas: spec **Pochteca 17 · Nezahualcóyotl 18 · Chilam 18 ·
Tlacuilo 27 · Itzamná 16** frente a payload **24 · 24 · 24 · 14 · 14**.

| Agente | Faltan | Sobran | Ejemplo concreto |
| --- | --- | --- | --- |
| itzamna | 10 | 18 | `edit *` es **ask** (blueprint: `deny`); `subagent * allow` + 4 denies (blueprint: `subagent * deny`) |
| nezahualcoyotl | 10 | 16 | `subagent * deny` **sí** coincide; faltan `external_directory`, denies de secretos y el deny final de `01-tasks/research/**` |
| pochteca | 8 | 15 | falta `edit 01-tasks/research/** allow`: hoy es **read-only total**, no puede depositar evidencia |
| chilam | 12 | 8 | `edit *` es **allow** (blueprint: `deny` + `03-citations/**` + `04-review/**`) |
| tlacuilo | 20 | 7 | con `edit * allow` vigente faltan los 11 denies de gobernanza (`.git/**`, `.obsidian/**`, `.opencode/**`, `.tepochcalli/**`, `00-Resources/**`, `01-tasks/**`, `03-citations/**`, `04-review/**`, `AGENTS.md`, `opencode.json`, `tepochcalli.toml`) |

## Hash del árbol de skills

Referencia para T11 (D-P5-1: 0 modificadas, 0 añadidas, 0 eliminadas):

```text
sha256 del árbol  : 169fe2c99fd58c71566342b076afd9098ae19dd13222ced96634963d617fc398
ficheros hasheados: 687

find obsidian-workspace/.opencode/skills -type f | sort | xargs sha256sum | sha256sum
```

Re-verificado al cierre: mismo hash y mismo recuento. El hash depende de las rutas y del orden, así
que T11 debe usar **este comando desde la raíz del repo**, no una variante con rutas absolutas.

## Salidas crudas

```text
$ ls obsidian-workspace/.opencode/skills | wc -l
40

article-writing  brainstorming  citation-management  consciousness-council  data-analysis
data-plotting  database-lookup  doc-coauthoring  experimental-design  hypothesis-generation
idea-refine  image-prompt-generator  interview-me  literature-review  literature-search-engine
markdown-mermaid-writing  obsidian-cli  obsidian-markdown  obsidian-vault  osint-skills
paper-2-web  pdf  peer-review  planning-and-task-breakdown  posters-generator  research-grants
research-search-protocol  scholar-evaluation  scientific-brainstorming  scientific-critical-thinking
scientific-problem-selection  scientific-writing  spreadsheet-analysis  statistical-analysis
statistical-power  tepochcalli-mcp  toon  websearch-engine  what-if-oracle  writing-skills

$ find obsidian-workspace/.opencode/agents -name '*.md' | wc -l
170

$ wc -l obsidian-workspace/.opencode/commands/*.md
  4 cite.md   4 draft.md   4 research.md   4 review.md   4 rubric.md
  4 synthesize.md   4 transform.md   4 update.md   4 validate.md
 36 total

$ grep -l "mode: primary" obsidian-workspace/.opencode/agents/*.md | xargs wc -l
   84 chilam.md   135 itzamna.md   104 nezahualcoyotl.md   114 pochteca.md   83 tlacuilo.md   520 total

$ wc -l obsidian-workspace/AGENTS.md
79 obsidian-workspace/AGENTS.md
```

```text
$ python3 -c "import json; d=json.load(open('obsidian-workspace/opencode.json')); ..."
keys: ['$schema', 'agents', 'compaction', 'default_agent', 'formatter', 'instructions', 'mcp', 'model', 'permissions', 'plugins', 'references']
permissions_len: 313
default_agent: itzamna
instructions: ['obsidian-workspace/.opencode/skills/obsidian-markdown/SKILL.md', 'obsidian-workspace/.opencode/skills/obsidian-cli/SKILL.md', 'obsidian-workspace/.opencode/skills/obsidian-vault/SKILL.md', 'obsidian-workspace/.opencode/skills/markdown-mermaid-writing/SKILL.md']
agents: ['build', 'chilam', 'explore', 'general', 'itzamna', 'nezahualcoyotl', 'plan', 'pochteca', 'tlacuilo']

Counter({'shell': 265, 'read': 41, 'external_directory': 6, 'subagent': 1})
Counter({'deny': 204, 'allow': 93, 'ask': 16})
external_directory: * deny · ~/.bun/* allow · ~/.cargo/* allow · ~/go/* allow · ~/.cache/* allow · /tmp/opencode/* allow
subagent: [{'action': 'subagent', 'resource': '*', 'effect': 'ask'}]
```

```text
$ for s in xlsx-official excel-analysis scientific-slides pptx-official matplotlib \
           scientific-visualization infographics markitdown; do
    test -d "obsidian-workspace/.opencode/skills/$s" && echo "EXISTS $s" || echo "MISSING $s"; done
MISSING xlsx-official
MISSING excel-analysis
MISSING scientific-slides
MISSING pptx-official
MISSING matplotlib
MISSING scientific-visualization
MISSING infographics
MISSING markitdown

$ grep -n "xlsx-official" specs/spec-payload-commands.md
270:2. Use only skills that exist today: `xlsx-official`/`excel-analysis` (CSV/Excel), `scientific-slides`/`pptx-official` (presentations), `markdown-mermaid-writing` (mind map via Mermaid `mindmap`), `matplotlib`/`scientific-visualization` (figures), `infographics`, `markitdown` (ad-hoc conversion).
```

```text
$ ls -la obsidian-workspace/
drwxr-xr-x .opencode        drwxr-xr-x .tepochcalli       drwxr-xr-x 00-Resources (0 ficheros)
drwxr-xr-x 01-Tasks (3 ficheros de 0 bytes)
-rw-r--r-- AGENTS.md (2652 B)   -rw-r--r-- LICENSE   -rw-r--r-- opencode.json (33367 B)
# no existe .gitignore en el payload

$ find obsidian-workspace/01-Tasks -type f -exec wc -c {} +
0 obsidian-workspace/01-Tasks/outline.md
0 obsidian-workspace/01-Tasks/rubric.md
0 obsidian-workspace/01-Tasks/todo.md
0 total

$ cat obsidian-workspace/.opencode/commands/draft.md
---
description: 
agent: tlacuilo
---
```

```text
$ just md-lint
npx --yes markdownlint-cli2 docs specs AGENTS.md SPEC.md
markdownlint-cli2 v0.24.0 (markdownlint v0.42.0)
Linting: 39 files
Summary: 0 issues in 0 files
EXIT=0
```

## Estado git al cierre

```text
$ git status --short
(sin salida)

$ git diff --stat -- obsidian-workspace
(sin salida)
```

`obsidian-workspace/` queda byte a byte como estaba; este informe es el único fichero escrito
(`tasks/phase5-baseline.md`). Cualquier desviación del hash o del `md-lint` posterior es imputable a
la ola que la produzca, no a T0.
