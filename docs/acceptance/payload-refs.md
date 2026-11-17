# Refs del payload a skills y subagentes (Phase 6 · T12 · TD-34)

> **Fecha:** 2026-11-12 · **Fase:** Phase 6 — E2E Acceptance · **Calpulli:** T12
> **Estado:** entregado; **sin commit** (lo integra el orquestador). El payload no se tocó (D-P6-1).
> **Fuente de verdad de la deuda:** `docs/TECH_DEBT.md:45` (TD-34) · alcance en `tasks/plan.md:448` y `tasks/plan.md:43` (D-P6-1) y `tasks/todo.md:220`.
> **Jerarquía de evidencia:** toda cifra de este documento es **`medido`** en el repo con el comando que se cita.

## Veredicto

**0 huérfanos.** Las 111 referencias de skill/subagente/agente de los **9 comandos** y los **5 agentes primarios**
resuelven contra el inventario real (40 skills, 170 agentes). Ningún nombre se queda en el aire:
hoy la ola canónica del 2026-11-12 no tiene una referencia rota que falle en runtime del harness.

Lo que **sí** está desalineado es la **documentación**, no el payload (§2): la spec del inventario sigue afirmando
41 skills y sigue publicando una tabla 9×4 que no describe los cuerpos de comando actuales.

## 1. Inventario real medido

| Hecho | Comando | Valor medido |
| --- | --- | --- |
| Skills presentes | `ls obsidian-workspace/.opencode/skills \| wc -l` | **40** |
| Skills con `SKILL.md` | `for d in */; do [ -f "$d/SKILL.md" ] \|\| echo MISSING: $d; done` | **40/40** (0 huecos) |
| Agentes presentes | `ls obsidian-workspace/.opencode/agents \| wc -l` | **170** |
| Agentes `mode: primary` | `grep -h '^mode:' agents/*.md \| sort \| uniq -c` | **5** |
| Agentes `mode: subagent` | idem | **165** |
| Comandos | `ls obsidian-workspace/.opencode/commands \| wc -l` | **9** |
| Referencias extraídas | `python3 tests/e2e/verify_payload_refs.py` | **111** (71 skill · 15 subagente · 25 agente) |

Los 5 primarios son `itzamna`, `nezahualcoyotl`, `pochteca`, `chilam` y `tlacuilo` (los únicos con `mode: primary`).

### Discrepancia de conteo (declarada, no corregida)

| Fuente | Dice | Realidad |
| --- | --- | --- |
| `specs/spec-payload-skills.md:26` | **41 dirs** (enmienda 2026-11-11 con `math-typesetting-guide`) | **40** |
| `specs/spec-payload-skills.md:47` | lista de inventario que aún incluye `database-lookup` | `database-lookup/` no existe (`ls`) |
| `SPEC.md:114` | **40 desde 2026-11-12** (retiro de `database-lookup/`) | **40** ✓ |

La spec no tiene enmienda que baje 41 a 40 ni que saque `database-lookup` del inventario; `SPEC.md` ya lo corrige.
Cero referencias a `database-lookup` en los cuerpos (`grep -rn database-lookup obsidian-workspace/` = 0 líneas), así que
el payload está sano: es deuda documental.

## 2. Discrepancias con la documentación (payload intacto)

### D1 — La tabla 9×4 asigna skills que los cuerpos no cargan (Moderada, doc/code mismatch)

| Fila de la spec | Skill que la spec asigna | Qué hace el cuerpo |
| --- | --- | --- |
| `specs/spec-payload-skills.md:82` (`/research`) | `database-lookup` | no existe en `skills/` y ningún comando la cita |
| `specs/spec-payload-skills.md:82` (`/research`) | `literature-review`, `paper-2-web` | `/research` no las cita (`commands/research.md:6-59`); `paper-2-web` solo en `commands/transform.md:41` |
| `specs/spec-payload-skills.md:83` (`/validate`) | `statistical-analysis`, `statistical-power` | ninguna de las dos se cita en `commands/validate.md` |
| `specs/spec-payload-skills.md:86` (`/draft`) | `writing-skills` | no se cita en `commands/draft.md` (ni en ningún otro cuerpo) |
| `specs/spec-payload-skills.md:89` (`/update`) | `obsidian-cli` | no se cita en `commands/update.md` (sí en `obsidian-workspace/AGENTS.md`) |

En el sentido contrario también falla: los cuerpos cargan skills que la tabla no les reconoce
(p. ej. `commands/research.md:6` carga `research-grants`; `commands/review.md:36` carga `article-writing`).
**La tabla es un artefacto de Phase 4 (2026-11-09); los cuerpos son la ola canónica 2026-11-12 y no se re-sincronizaron.**

### D2 — "Subagentes: ninguno" y "los 5 primarios llevan `subagent * deny`" es falso (Moderada)

`specs/spec-payload-skills.md:106` afirma dos cosas; el payload dice lo contrario en la segunda:

| Agente | Bloque real | Efecto |
| --- | --- | --- |
| `itzamna` | `agents/itzamna.md:20-22` | `subagent *` **allow** |
| `nezahualcoyotl` | `agents/nezahualcoyotl.md:38-40` | `subagent *` **deny** |
| `pochteca` | `agents/pochteca.md:26-40` | allow + 4 denies nominales (`nezahualcoyotl`, `itzamna`, `chilam`, `tlacuilo`) |
| `chilam` | `agents/chilam.md:20-34` | allow + 4 denies nominales |
| `tlacuilo` | `agents/tlacuilo.md:20-34` | allow + 4 denies nominales |

Y hay **15 delegaciones reales** a 5 subagentes (§3.2), no "ninguno". Coherente con los cuerpos: cada delegación
resuelve contra un agente `mode: subagent` y contra un primario que no lo tiene en su lista de denies.

### D3 — `specs/spec-payload-skills.md:71` ("toda skill citada existe en el `ls` de 40")

Hoy es **cierto** (71/71 citas de skill resuelven), pero era una afirmación sin mécanismo que la
comprobara: nada en `just ci` la miraba, que es exactamente TD-34. El verificador de §5 la convierte en gate reproducible.

**Corrección propuesta (no aplicada, D-P6-1):** enmienda fechada 2026-11-12 en `specs/spec-payload-skills.md` con
(a) inventario **40** tras el retiro de `database-lookup/`, sin la fila de `database-lookup`; (b) tabla 9×4 regenerada
desde los cuerpos (o degradada a "histórico, no normativo"); (c) §Subagentes con las 15 delegaciones reales y el
reparto de permisos de la tabla D2. No se toca ni un byte de `obsidian-workspace/`.

## 3. Referencias por nombre

### 3.1 Skills citadas (29 nombres: 61 citas en comandos + 10 en los primarios)

| Nombre | Fichero:línea | Citas | Presente |
| --- | --- | --- | --- |
| `article-writing` | review.md:36 | 1 | sí |
| `brainstorming` | rubric.md:9 | 1 | sí |
| `citation-management` | cite.md:17, review.md:18 | 2 | sí |
| `data-plotting` | transform.md:53 | 1 | sí |
| `doc-coauthoring` | synthesize.md:16 | 1 | sí |
| `idea-refine` | rubric.md:14 | 1 | sí |
| `interview-me` | rubric.md:8 | 1 | sí |
| `literature-search-engine` | research.md:49, update.md:26 | 2 | sí |
| `markdown-mermaid-writing` | draft.md:21, rubric.md:31 | 2 | sí |
| `math-typesetting-guide` | draft.md:21 | 1 | sí |
| `obsidian-markdown` | cite.md:28, draft.md:20, research.md:59, review.md:31, rubric.md:31, synthesize.md:26, transform.md:24, update.md:35, validate.md:49 | 9 | sí |
| `obsidian-vault` | cite.md:28, draft.md:20, research.md:59, review.md:31, rubric.md:31, synthesize.md:26, transform.md:24, update.md:35, validate.md:49 | 9 | sí |
| `osint-skills` | research.md:42, update.md:19 | 2 | sí |
| `paper-2-web` | transform.md:41 | 1 | sí |
| `pdf` | transform.md:47 | 1 | sí |
| `peer-review` | review.md:14, validate.md:34 | 2 | sí |
| `planning-and-task-breakdown` | rubric.md:27 | 1 | sí |
| `posters-generator` | transform.md:35 | 1 | sí |
| `research-grants` | research.md:6 | 1 | sí |
| `research-search-protocol` | research.md:6 | 1 | sí |
| `scholar-evaluation` | review.md:14, validate.md:6 | 2 | sí |
| `scientific-brainstorming` | rubric.md:9 | 1 | sí |
| `scientific-critical-thinking` | review.md:17 | 1 | sí |
| `scientific-problem-selection` | rubric.md:14 | 1 | sí |
| `scientific-writing` | draft.md:19, review.md:36 | 2 | sí |
| `spreadsheet-analysis` | transform.md:29 | 1 | sí |
| `tepochcalli-mcp` | cite.md:6, draft.md:9, research.md:38, review.md:9, synthesize.md:18, transform.md:59, update.md:10, update.md:15, validate.md:21, @itzamna.md:147, @itzamna.md:166, @nezahualcoyotl.md:143, @nezahualcoyotl.md:163, @pochteca.md:155, @pochteca.md:175, @chilam.md:147, @chilam.md:166, @tlacuilo.md:115, @tlacuilo.md:136 | 19 | sí |
| `websearch-engine` | research.md:50, update.md:27 | 2 | sí |
| `what-if-oracle` | rubric.md:38 | 1 | sí |

Convenio de la columna: sin prefijo = `obsidian-workspace/.opencode/commands/`; con `@` = `.opencode/agents/`
(`@itzamna.md:147` es `agents/itzamna.md:147`). `tepochcalli-mcp` es la única skill que los 5 primarios cargan
(2 citas por agente: `agents/itzamna.md:147` y `:166`, y el equivalente en los otros cuatro).

### 3.2 Subagentes delegados (5 nombres, 15 citas)

| Nombre | Fichero:línea | Citas | Presente |
| --- | --- | --- | --- |
| `knowledge-synthesizer` | review.md:33 | 1 | sí |
| `obsidian-vault-writer` | cite.md:28, draft.md:20, research.md:59, review.md:31, transform.md:24, update.md:35, validate.md:49 | 7 | sí |
| `research-analyst` | research.md:27, review.md:18, validate.md:10 | 3 | sí |
| `scientific-literature-researcher` | research.md:49, update.md:26 | 2 | sí |
| `search-specialist` | research.md:38, update.md:15 | 2 | sí |

Los 5 resuelven a `mode: subagent` (`grep -m1 '^mode:'` sobre cada uno). Cero delegaciones a un primario.

### 3.3 Agentes nombrados (`agent:` de comando y `resource:` de permisos, 25 citas)

| Nombre | Fichero:línea | Citas | Presente |
| --- | --- | --- | --- |
| `chilam` | cite.md:3, review.md:3, validate.md:3, @itzamna.md:30, @pochteca.md:36, @tlacuilo.md:30 | 6 | sí |
| `itzamna` | @pochteca.md:33, @chilam.md:30, @tlacuilo.md:33 | 3 | sí |
| `nezahualcoyotl` | rubric.md:3, synthesize.md:3, @itzamna.md:24, @pochteca.md:30, @chilam.md:24, @tlacuilo.md:24 | 6 | sí |
| `pochteca` | research.md:3, @itzamna.md:27, @chilam.md:27, @tlacuilo.md:27 | 4 | sí |
| `tlacuilo` | draft.md:3, transform.md:3, update.md:3, @itzamna.md:33, @pochteca.md:39, @chilam.md:33 | 6 | sí |

Los 9 `agent:` de comando resuelven a un primario (§4). Las 16 citas con prefijo `@` son `resource:` de bloques
`action: subagent` en los frontmatter: nombran primarios que el agente **no** puede invocar, y los 5 existen.

### 3.4 Skills presentes y nunca citadas por los 9 comandos ni los 5 primarios (11)

`consciousness-council`, `data-analysis`, `experimental-design`, `hypothesis-generation`, `image-prompt-generator`, `literature-review`, `obsidian-cli`, `statistical-analysis`, `statistical-power`, `toon`, `writing-skills`

No es un defecto: son capacidades disponibles a demanda. Dos matices:
`obsidian-cli` sí se cita en `obsidian-workspace/AGENTS.md` §6 (fuera del alcance de este barrido), y
`literature-review` · `data-analysis` · `statistical-analysis` · `statistical-power` · `writing-skills` · `experimental-design`
· `hypothesis-generation` · `image-prompt-generator` son precisamente las que la tabla 9×4 (D1) asigna a comandos que no las cargan.

## 4. Carga por comando

Cada `agent:` resuelve a un primario existente con `mode: primary`, y cada skill se carga **en el comando que la cita**
(verbo `Load`/`Delegate` en la misma línea de la cita — comprobado en §3.1).

| Comando | `agent:` | Skills que carga | Subagentes que delega |
| --- | --- | --- | --- |
| `/cite` | `chilam` | `tepochcalli-mcp`, `citation-management`, `obsidian-vault`, `obsidian-markdown` | `obsidian-vault-writer` |
| `/draft` | `tlacuilo` | `tepochcalli-mcp`, `scientific-writing`, `obsidian-vault`, `obsidian-markdown`, `math-typesetting-guide`, `markdown-mermaid-writing` | `obsidian-vault-writer` |
| `/research` | `pochteca` | `research-grants`, `research-search-protocol`, `tepochcalli-mcp`, `osint-skills`, `literature-search-engine`, `websearch-engine`, `obsidian-vault`, `obsidian-markdown` | `research-analyst`, `search-specialist`, `scientific-literature-researcher`, `obsidian-vault-writer` |
| `/review` | `chilam` | `tepochcalli-mcp`, `scholar-evaluation`, `peer-review`, `scientific-critical-thinking`, `citation-management`, `obsidian-vault`, `obsidian-markdown`, `article-writing`, `scientific-writing` | `research-analyst`, `obsidian-vault-writer`, `knowledge-synthesizer` |
| `/rubric` | `nezahualcoyotl` | `interview-me`, `scientific-brainstorming`, `brainstorming`, `scientific-problem-selection`, `idea-refine`, `planning-and-task-breakdown`, `markdown-mermaid-writing`, `obsidian-vault`, `obsidian-markdown`, `what-if-oracle` | — |
| `/synthesize` | `nezahualcoyotl` | `doc-coauthoring`, `tepochcalli-mcp`, `obsidian-vault`, `obsidian-markdown` | — |
| `/transform` | `tlacuilo` | `obsidian-vault`, `obsidian-markdown`, `spreadsheet-analysis`, `posters-generator`, `paper-2-web`, `pdf`, `data-plotting`, `tepochcalli-mcp` | `obsidian-vault-writer` |
| `/update` | `tlacuilo` | `tepochcalli-mcp`, `tepochcalli-mcp`, `osint-skills`, `literature-search-engine`, `websearch-engine`, `obsidian-vault`, `obsidian-markdown` | `search-specialist`, `scientific-literature-researcher`, `obsidian-vault-writer` |
| `/validate` | `chilam` | `scholar-evaluation`, `tepochcalli-mcp`, `peer-review`, `obsidian-vault`, `obsidian-markdown` | `research-analyst`, `obsidian-vault-writer` |

Observaciones de coherencia (sin hallazgo):

* `/rubric` corre como `nezahualcoyotl`, el único primario con `subagent * deny`; por eso **planifica** el reparto de
  subagentes (`commands/rubric.md:32`) sin invocarlos, y no delega ninguno. Coherente con `agents/nezahualcoyotl.md:160`.
* `/research`, `/review`, `/validate`, `/cite`, `/draft`, `/transform`, `/update` delegan en `obsidian-vault-writer`
  (`mode: subagent`), y su primario lo permite por el `subagent *` allow.
* `commands/update.md:10` y `:15` cargan `tepochcalli-mcp` dos veces en la misma fase: redundante, inocuo (idempotente),
  no se toca.

## 5. Verificador reutilizable

`tests/e2e/verify_payload_refs.py` (188 líneas, stdlib) — no es un `test_*`, así que las suites de módulo (`just test-mcp` / `test-engine` / `test-converter`) no lo recolectan;
es un verificador CLI con el mismo patrón que `tests/e2e/verify_payload_install.py`.

```text
python3 tests/e2e/verify_payload_refs.py            # payload del repo
python3 tests/e2e/verify_payload_refs.py PATH       # vault instalado (lo que corre T15)
```

Reglas de extracción (estrechas a propósito, sin dependencias):

1. `agent:` del frontmatter de un comando y cada par `action: subagent` + `resource:` de un agente.
2. Span en backticks tipado por lo que le sigue hasta el siguiente span: "`a` + `b` skills" tipa **las dos**;
   "`x` MCP" o "`search` tool" no tipan nada. Fenced blocks se ignoran.
3. Una skill se busca como directorio en `.opencode/skills/` (y exige `SKILL.md`); un subagente como `.md` en
   `.opencode/agents/` con `mode: subagent`; un `agent:` de comando exige `mode: primary`.

### Salida sobre el payload del repo (ejecutada)

```text
$ python3 tests/e2e/verify_payload_refs.py
0 failure(s); 111 reference(s) checked against 40 skill(s) and 170 agent(s) in /mnt/HDDFish/Documents/Programacion/PROYECTOS/14-tepochcalli-opencode/obsidian-workspace
$ echo "exit=$?"
exit=0
```

### Control negativo (copia mutada en `/tmp/opencode/negctl`, el payload intacto)

Se copió `.opencode/` a `/tmp`, se escribió `citation-managment` (typo) en `cite.md:17` y se cambió
`knowledge-synthesizer` por `chilam` (primario) en `review.md:33`:

```text
$ python3 tests/e2e/verify_payload_refs.py /tmp/opencode/negctl
FAIL: commands/cite.md:17 loads skill `citation-managment` - not in .opencode/skills/
FAIL: commands/review.md:33 delegates to `chilam` - mode primary, not subagent
2 failure(s); 111 reference(s) checked against 40 skill(s) and 170 agent(s) in /tmp/opencode/negctl
$ echo "exit=$?"
exit=1
```

Es decir: huérfano de skill **y** delegación a un no-subagente ponen el verificador rojo. Un root sin `.opencode/` sale 2.

### Test unitario del parser

`tests/unit/test_payload_refs_parser.py` (57 líneas, 4 casos: cadena de skills, nombre de tool que no es skill,
frontmatter/permisos, fenced block):

```text
$ cd obsidian-workspace/.tepochcalli && venv/bin/python -m pytest ../../tests/unit/test_payload_refs_parser.py -q
....                                                                     [100%]
4 passed in 0.30s
```

## 6. Evidencia de solo lectura (D-P6-1)

```text
$ git diff --stat -- obsidian-workspace | wc -l
0
$ git status --short -- obsidian-workspace | wc -l
0
```

Antes y después del calpulli, `git diff --stat -- obsidian-workspace` está **vacío** (0 líneas, arriba): ninguna escritura en
`obsidian-workspace/.opencode/`, `AGENTS.md` ni `opencode.json`. Los artefactos nuevos de T12 viven fuera del payload:
`tests/e2e/verify_payload_refs.py`, `tests/unit/test_payload_refs_parser.py` y este informe.

## 7. Qué desbloquea

* **T14/T15:** el script corre también contra el vault instalado, así que el QA de la corrida D9 puede verificar
  el payload **materializado** (no solo el del repo) antes de gastar la corrida: `verify_payload_refs.py $VAULT`.
* **TD-34:** cerrada en su parte verificable — el criterio "0 refs a nombres inexistentes" ya es un exit code
  reproducible en vez de un `grep` manual.
* **Pendiente declarado:** D1/D2 son deuda **documental** y esta tarea no las corrige (D-P6-1). Requieren enmienda
  fechada en `specs/spec-payload-skills.md`; hasta entonces, la tabla 9×4 no debe usarse como fuente de verdad de
  qué carga cada comando — los cuerpos lo son.
