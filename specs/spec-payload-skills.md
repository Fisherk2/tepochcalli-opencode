# Spec: Skills del payload — inventario definitivo y tabla de invocación

* **Status:** Approved (BLUEPRINT APPROVED 2026-11-09 — gate concedido por congelamiento del dueño: 40 skills definitivas, `cf17f31`/`2e62e60`) · **Enmendada 2026-11-11** ([ADR-012](../docs/adr/adr-012-formato-payload-revisado.md): 41 skills con `math-typesetting-guide`; D-P5-1 SUPERSEDED) · **Enmendada 2026-11-12** (inventario real **39** tras retirar `database-lookup/` en `c815eb0` y `writing-skills/` en `e785072`; tabla 9×4 y frase de subagentes **SUPERSEDED** por la §Enmienda 2026-11-12, generada desde los cuerpos)
* **Fase:** Phase 4 (diseño) — Phase 5 verifica, no ejecuta cortes
* **Date:** 2026-11-09 (congela inventario; rev. 2026-11-04 SUPERSEDED, ver §Histórico)
* **Author:** Arquitecto (calpulli T2b, Phase 4)
* **Reviewers:** Product Owner (usuario)
* **Traceability:** [specs/spec-payload-vault.md](spec-payload-vault.md) (blueprint; la §Tabla de invocación 9×4 es T3), [specs/spec-agent-workflow.md](spec-agent-workflow.md) (Anexo A — auditoría de 208 skills, 2026-10-21), [specs/spec-vault-structure.md](spec-vault-structure.md) (zonas D9.1), [docs/TECH_DEBT.md](../docs/TECH_DEBT.md) TD-7 y TD-22, [docs/BACKLOG.md](../docs/BACKLOG.md) (áreas de investigación; la fuente no las numera), [docs/WORKFLOW.md](../docs/WORKFLOW.md) Phase 4 y Phase 5

## Summary

Esta spec es dueña de tres cosas del payload: el **inventario definitivo de skills**
(**39 dirs al 2026-11-12**; 40 en el congelado del 2026-11-09), la **tabla de invocación
comando→herramientas (9×4)** — movida aquí
desde [specs/spec-payload-vault.md](spec-payload-vault.md) en T3 (D-P4-4) — y el
**inventario de muestras** que produce el instalador (D-P4-7).

**Congelado 2026-11-09 (decisión del dueño):** `obsidian-workspace/.opencode/skills/` quedó
**definitivo con 40 dirs**. Veredictos: **CONSERVAR 40/40, RETIRAR 0, CONSOLIDAR 0,
INSTALAR-GAP 0**. Phase 5 **verificó presencia (40 presentes, 0 retiros)** y no ejecutó
ninguna matriz de recorte. La matriz de 17 filas de la rev. 2026-11-04 queda **SUPERSEDED**
y se conserva solo como histórico colapsado (§Histórico) — **no ejecutar**.

**Enmienda 2026-11-11 ([ADR-012](../docs/adr/adr-012-formato-payload-revisado.md)):** el
dueño autorizó la skill 41 (`math-typesetting-guide`, commit `1c4a90b`, invocada desde §3
del `AGENTS.md` del payload). D-P5-1 (freeze 40) queda **SUPERSEDED**; el inventario pasó
a **41 dirs**, objetivo <60 seguía cumplido (41 < 60).

**Enmienda 2026-11-12 — SUPERSEDED de los dos párrafos anteriores:** se retiraron
`database-lookup/` (`c815eb0`) y `writing-skills/` (`e785072`), y el inventario queda en
**39 dirs reales** (`ls | wc -l`). El objetivo <60 se cumple igual (39 < 60). Ver
§Enmienda 2026-11-12 y E1, que es el inventario **vigente**.

No es dueña de: los cuerpos de comandos, agentes y `AGENTS.md` del vault (spec del
blueprint). **No se escribe nada en `obsidian-workspace/` en esta fase.**

## Inventario definitivo (2026-11-09)

```bash
# fecha de la medición: 2026-11-09 (40); enmienda 2026-11-11: 41 con math-typesetting-guide
# vigente 2026-11-12: 39 (retiros database-lookup/ y writing-skills/ — §Enmienda E1)
ls obsidian-workspace/.opencode/skills | wc -l                    # 39
find obsidian-workspace/.opencode/agents -name '*.md' | wc -l    # 170
find obsidian-workspace/.opencode/commands -name '*.md' | wc -l  # 9
ls obsidian-workspace/00-resources | wc -l                        # 0 (muestras de instalación: ver abajo)
wc -c obsidian-workspace/.opencode/skills/tepochcalli-mcp/SKILL.md # 13098 (cuerpo en inglés)
```

* **0 skills citadas e inexistentes**: toda referencia de comandos y agentes resuelve contra el `ls`.
* **Cobertura 39/39** (2026-11-12): las 39 están citadas o disponibles para la tabla 9×4; ninguna cae en barrido.
* **39 nombres vigentes**, orden alfabético — la lista de abajo es el inventario histórico de 40/41
  con los dos retiros tachados (§Enmienda E1 es la lista buena):

article-writing · brainstorming · citation-management · consciousness-council ·
data-analysis · data-plotting · ~~database-lookup~~ (retirado en `c815eb0`) ·
doc-coauthoring · experimental-design ·
hypothesis-generation · idea-refine · image-prompt-generator · interview-me ·
literature-review · literature-search-engine · markdown-mermaid-writing ·
math-typesetting-guide · obsidian-cli ·
obsidian-markdown · obsidian-vault · osint-skills · paper-2-web · pdf · peer-review ·
planning-and-task-breakdown · posters-generator · research-grants ·
research-search-protocol · scholar-evaluation · scientific-brainstorming ·
scientific-critical-thinking · scientific-problem-selection · scientific-writing ·
spreadsheet-analysis · statistical-analysis · statistical-power · tepochcalli-mcp ·
toon · websearch-engine · what-if-oracle · ~~writing-skills~~ (retirada en `e785072`)

### Veredictos (un cubo: 39)

| Cubo | Dirs | Qué son |
| --- | --- | --- |
| CONSERVAR (definitivo) | **39** — ver §Enmienda E1; el «+1 ⇒ 41» de la enmienda 2026-11-11 y el 40 del congelado quedan **SUPERSEDED** | las del inventario E1; sin recorte, sin fusión, sin instalación |
| RETIRAR | 0 | congelado: ningún retiro en Phase 5 |
| CONSOLIDAR | 0 | congelado: ninguna fusión en Phase 5 |
| INSTALAR-GAP | 0 | v1 no instala ninguna skill nueva |

## Tabla de invocación por comando (9×4)

`9×4` = **9 filas** (una por comando) × **4 columnas de contenido** (skills concretas,
herramientas nativas, MCPs a ejecutar y subagentes permitidos); la primera columna solo
etiqueta el comando con su `agent:` de stub. Toda skill citada existe en el `ls` de 39;
donde la rev. anterior citaba una skill que ya no existe, se sustituye por el equivalente
de los 39 o se declara **GAP**. Los 7 nombres de tool se copian verbatim de
`obsidian-workspace/.tepochcalli/mcp/tepochcalli_mcp/server.py` (`@server.tool()`):
`search`, `index_refresh`, `add_source`, `convert_document`, `convert_base64`,
`list_formats`, `rag_status`. Los nombres nativos son el vocabulario V2 de
[specs/spec-payload-vault.md](spec-payload-vault.md) §Vocabulario de acciones V2.

> **SUPERSEDED 2026-11-12.** La tabla siguiente es el **diseño Phase 4 (2026-11-09)** y no
> describe los cuerpos vigentes: asigna skills que ningún comando carga y omite las que sí
> (ver §Enmienda E2, que la reemplaza). Se conserva como historia. **No usar como fuente de
> verdad de qué carga cada comando: los cuerpos lo son.**

| Comando | Skills concretas (inventario vigente 39) | Herramientas nativas | MCPs a ejecutar | Subagentes permitidos |
| --- | --- | --- | --- | --- |
| `/rubric` (agent: `nezahualcoyotl`) | scientific-problem-selection, experimental-design, planning-and-task-breakdown | read · glob · grep · question · todowrite (el rubric es una lista de tareas) | `tepochcalli-rag`: search (dimensionar el corpus) · index_refresh (si la frescura es dudosa) · rag_status ante `E_*` | ninguno |
| `/research` (agent: `pochteca`) | literature-search-engine, research-search-protocol, literature-review, paper-2-web, websearch-engine, osint-skills, database-lookup, tepochcalli-mcp | webfetch · websearch · read · edit `01-tasks/research/**` | `tepochcalli-rag`: search · index_refresh · add_source (ingesta externa; markitdown **en proceso**) · rag_status | ninguno |
| `/validate` (agent: `chilam`) | scholar-evaluation, scientific-critical-thinking, statistical-analysis, statistical-power | read · glob · grep · edit `04-review/**` | `tepochcalli-rag`: search (cruce con el corpus) · index_refresh (si la frescura es dudosa) · rag_status | ninguno |
| `/synthesize` (agent: `nezahualcoyotl`) | idea-refine, scientific-brainstorming, hypothesis-generation, markdown-mermaid-writing | read · glob · grep · edit `01-tasks/**` | `tepochcalli-rag`: search · index_refresh (si la frescura es dudosa) · rag_status | ninguno |
| `/cite` (agent: `chilam`) | citation-management, paper-2-web | read · glob · grep · edit `03-citations/**` | `tepochcalli-rag`: rag_status; search SOLO si el usuario pide re-trazabilidad (el gate de procedencia opera sobre la evidencia de `/research`, sin red) | ninguno |
| `/draft` (agent: `tlacuilo`) | scientific-writing, article-writing, writing-skills, doc-coauthoring, obsidian-markdown, markdown-mermaid-writing | read · edit `02-drafts/**` | `tepochcalli-rag`: search · index_refresh (si la frescura es dudosa) · rag_status | ninguno |
| `/review` (agent: `chilam`) | peer-review, writing-skills, scholar-evaluation | read · glob · grep · edit `04-review/**` | `tepochcalli-rag`: search · index_refresh (si la frescura es dudosa) · rag_status | ninguno |
| `/transform` (agent: `tlacuilo`) | spreadsheet-analysis, data-analysis, data-plotting, posters-generator, pdf, image-prompt-generator, markdown-mermaid-writing (mindmap), tepochcalli-mcp | read `02-drafts/**` · edit `05-outputs/**` | `tepochcalli-rag`: search · rag_status · convert_document · convert_base64 · list_formats; `anydoc`: fallback disabled — solo si el conversor falla con formato fuera de catálogo y con permiso del usuario | ninguno |
| `/update` (agent: `tlacuilo`) | obsidian-markdown, obsidian-cli, obsidian-vault, scientific-writing, tepochcalli-mcp | read · glob · grep · edit `02-drafts/**` | `tepochcalli-rag`: search · index_refresh (si hay ingesta nueva) · add_source solo si el usuario lo pide · rag_status | ninguno |

* **Las 3 tools del conversor son de `/transform` (y solo de ahí):** un documento del vault
  se indexa **tal cual** con `index_refresh`; `convert_document`/`convert_base64` producen un
  `.md` legible en disco y `/transform` es el único comando que entrega artefactos a
  `05-outputs/`; `list_formats` es el catálogo previo a prometer un formato. `/research` no
  los necesita: ingiere con `add_source`, que convierte en la misma llamada.
* **`excel` y `jupyter` = GAP, no tools usables:** siguen `disabled: true` en `opencode.json`;
  la vía Excel es la skill `spreadsheet-analysis`. Jupyter, R, Graphviz, PlantUML y LaTeX de
  manuscrito no tienen skill en el inventario vigente: `/transform` los declara como pendientes
  de Phase 5 sin inventar nombres.
* **`venue-templates` = GAP declarado:** sin skill de plantillas de venue en las 39; `/cite`
  usa `citation-management` + `paper-2-web`.
* **`officecli` no se cita** como skill ni como MCP: es binario del wizard (TD-22, feature 0.2.0).
* **Permisos MCP:** el mapeo `<server>_<tool>` por agente es de T4
  ([specs/spec-payload-vault.md](spec-payload-vault.md) §permisos); esta tabla solo declara
  qué tool ejecuta cada comando.
* **Subagentes:** **ninguno** en las 9 filas — los 5 primarios llevan `subagent * deny`; si un
  comando necesitara un helper, se documenta antes como enmienda al blueprint.
  **SUPERSEDED 2026-11-12:** es falso en los dos extremos — solo `nezahualcoyotl` deniega
  `subagent *` y hay **15 delegaciones reales**; ver §Enmienda E3.

## Cobertura y objetivo <60

Cobertura del inventario: **39/39** (2026-11-12; toda skill del `ls` está conservada;
0 huérfanas fuera de tabla porque el congelado no exige cita exhaustiva).

El objetivo de menos de 60 skills del payload base (métrica heredada de
[docs/WORKFLOW.md](../docs/WORKFLOW.md) Phase 5 y de TD-7) queda **CUMPLIDO: 39 < 60**
(40 al congelado 2026-11-09 + `math-typesetting-guide` 2026-11-11 − `database-lookup/`
retirada 2026-11-12 − `writing-skills/` retirada 2026-11-12, [ADR-012](../docs/adr/adr-012-formato-payload-revisado.md),
`c815eb0` y `e785072`).
**No se ejecuta ningún corte ni consolidación en Phase 5** — el inventario ya está por
debajo del umbral por decisión del dueño (2026-11-09).

**Nota TD-22 (OfficeCLI, 0.2.0) — sin contradicción:** TD-22 gobierna la **feature 0.2.0**;
si OfficeCLI entrara, su tarea retiraría entonces las skills de ofimática que toque. En v1
las 39 se quedan.

**Decisión explícita (se mantiene): 0 skills nuevas para el protocolo de opendraft.** Los
gates heredados (procedencia, check de claim, gate de compilación) son invariantes de
workflow y viven en los cuerpos de `/research`, `/validate` y `/cite`, jamás en una skill
(una skill es oportunista; un cuerpo de comando se ejecuta siempre). `citation-management`
(cubo CONSERVAR) cubre la mecánica DOI→BibTeX/dedupe/validación de metadata; el protocolo
la complementa desde el comando, no la duplica. (Origen: análisis de
federicodeponte/opendraft, 2026-10-28.)

## Inventario de muestras del payload

`00-resources/` está **vacío** en el repo: las muestras del golden-vault las crea el
instalador en tiempo de instalación. Todo lo de esta tabla vive en el crate `tepochcalli`,
no en el payload.

| Artefacto | Ruta / constante | Estado actual | Objetivo | Acción Phase 5 |
| --- | --- | --- | --- | --- |
| Nombre de la nota | `crates/tepochcalli/src/application/installer.rs:46` `PLACEHOLDER_MD_NAME` | valor `ejemplo.md` | **sin cambio** (decisión del dueño 2026-11-04) | ninguna |
| Nombre del PDF | `installer.rs:47` `PLACEHOLDER_PDF_NAME` | valor `ejemplo.pdf` | **sin cambio** (decisión del dueño 2026-11-04) | ninguna |
| Cuerpo de la nota | `installer.rs:49-53` `PLACEHOLDER_MD_BODY` | español: empieza por `# Ejemplo` | **sin cambio** (decisión del dueño 2026-11-04) | ninguna |
| Bytes del PDF | `installer.rs:58` `EJEMPLO_PDF` = `include_bytes!` de `crates/tepochcalli/assets/ejemplo.pdf` | PDF válido de **592 bytes**; su única línea es `Hola tepochcalli` | **sin cambio** (decisión del dueño 2026-11-04) | ninguna |
| Generador del PDF | comentario de `EJEMPLO_PDF` (installer.rs:55-57) cita `gen_ejemplo_pdf.py` | **el script no existe en el repo** (0 resultados) | **sin cambio** (decisión del dueño 2026-11-04) | ninguna; el comentario queda como está |
| Carpeta de bandeja | `obsidian-workspace/01-Tasks/` | existe con 3 ficheros de 0 bytes; `01-tasks/` **no** existe | `01-tasks/` (convención D9.1 en minúsculas) | renombrar la carpeta en el payload; no crearla |

**Riesgo de caso (vecino de TD-8):** en sistemas insensibles a mayúsculas (macOS, Windows)
un `create_dir_all` con `01-tasks` **adopta silenciosamente** `01-Tasks/`; en Linux conviven
las dos. Phase 5 debe **renombrar**, no crear, y verificar con `ls` tras el install.

## Open Questions

* Ninguna abierta. El congelado y las muestras (sin cambio) quedan como están por
  decisión del dueño (2026-11-09); la matriz histórica queda SUPERSEDED. Las enmiendas
  2026-11-11 (inventario en 41) y el 40 del congelado quedan **SUPERSEDED** por la enmienda
  2026-11-12: **39 dirs reales** tras los retiros de `database-lookup/` (`c815eb0`) y
  `writing-skills/` (`e785072`) (§Enmienda E1).

## References

* [specs/spec-payload-vault.md](spec-payload-vault.md) — blueprint de agentes, permisos y `AGENTS.md`; puntero a esta spec para la tabla 9×4 (D-P4-4)
* [specs/spec-agent-workflow.md](spec-agent-workflow.md) — Anexo A: auditoría de 208 skills (2026-10-21) y gaps accionables
* [docs/TECH_DEBT.md](../docs/TECH_DEBT.md) — TD-7 (skills infladas) y TD-22 (OfficeCLI 0.2.0)
* [docs/BACKLOG.md](../docs/BACKLOG.md) — áreas de investigación pedidas (sin numeración en la fuente)
* [docs/WORKFLOW.md](../docs/WORKFLOW.md) — Phase 4 (diseño) y Phase 5 (payload + verificación 40, hoy 39)
* [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) — capas y contratos que el payload debe respetar
* `crates/tepochcalli/src/application/installer.rs` (muestras del instalador) y `crates/tepochcalli/assets/ejemplo.pdf`
* [AGENTS.md](../AGENTS.md) — R1/R2 (no reinventar, cero asunción) y umbrales de líneas por fichero

## Enmienda 2026-11-12 — inventario real 39 y delegaciones reales

**Origen.** Auditoría `T12` ([docs/acceptance/payload-refs.md](../docs/acceptance/payload-refs.md),
commit `bdb2da8`): **0 referencias huérfanas** en el payload y **3 defectos documentales**
en esta spec. Orden del dueño (2026-11-12): **la spec se alinea al payload**, no al revés.
**El payload no se toca** (D-P6-1, `obsidian-workspace/` congelado).

**Jerarquía de evidencia.** Toda cifra y toda línea de esta enmienda es **`medido`** el
2026-11-12 sobre `obsidian-workspace/.opencode/`; los **cuerpos** de comando son la fuente
de verdad de qué carga cada comando. Convenio de rutas: `commands/<x>.md:línea` =
`obsidian-workspace/.opencode/commands/`, `agents/<x>.md:línea` =
`obsidian-workspace/.opencode/agents/`.

### E1 — Inventario real: **39** (`database-lookup/` y `writing-skills/` retiradas)

| Hecho | Valor medido | Cómo se midió |
| --- | --- | --- |
| Dirs de skill presentes | **39** | `ls obsidian-workspace/.opencode/skills \| wc -l` |
| Con `SKILL.md` | 39/39 (0 huecos) | `for d in skills/*/; do [ -f "$d/SKILL.md" ] \|\| echo MISSING: $d; done` → sin salida |
| Dirs retirados | `database-lookup/` y `writing-skills/` (ninguno existe) | `ls …/skills/database-lookup …/skills/writing-skills` → *No such file or directory* |
| Commits y fecha de los retiros | `c815eb0` (2026-11-12, `chore(skill-database-lookup): retira skill superada por cadena EN`) y `e785072` (2026-11-12, `chore(skills): retira writing-skills del payload`, orden del dueño) | `git log --oneline -1 <sha>` |
| Referencias a los nombres retirados en el payload | **0** | `grep -rn 'database-lookup\|writing-skills' obsidian-workspace/.opencode` y `python3 tests/e2e/verify_payload_refs.py` → `0 failure(s); 111 reference(s) checked against 39 skill(s)` |
| Objetivo <60 | cumplido: **39 < 60** | — |

Inventario vigente (los bloques se leen **en columna**: 1–10, 11–20, 21–30, 31–39; el cuarto
bloque queda con 9):

| # | Skill | # | Skill | # | Skill | # | Skill |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `article-writing` | 11 | `image-prompt-generator` | 21 | `paper-2-web` | 31 | `scientific-problem-selection` |
| 2 | `brainstorming` | 12 | `interview-me` | 22 | `pdf` | 32 | `scientific-writing` |
| 3 | `citation-management` | 13 | `literature-review` | 23 | `peer-review` | 33 | `spreadsheet-analysis` |
| 4 | `consciousness-council` | 14 | `literature-search-engine` | 24 | `planning-and-task-breakdown` | 34 | `statistical-analysis` |
| 5 | `data-analysis` | 15 | `markdown-mermaid-writing` | 25 | `posters-generator` | 35 | `statistical-power` |
| 6 | `data-plotting` | 16 | `math-typesetting-guide` | 26 | `research-grants` | 36 | `tepochcalli-mcp` |
| 7 | `doc-coauthoring` | 17 | `obsidian-cli` | 27 | `research-search-protocol` | 37 | `toon` |
| 8 | `experimental-design` | 18 | `obsidian-markdown` | 28 | `scholar-evaluation` | 38 | `websearch-engine` |
| 9 | `hypothesis-generation` | 19 | `obsidian-vault` | 29 | `scientific-brainstorming` | 39 | `what-if-oracle` |
| 10 | `idea-refine` | 20 | `osint-skills` | 30 | `scientific-critical-thinking` | — | — |

**SUPERSEDED por E1:** el párrafo de la enmienda 2026-11-11 y el cierre de §Summary, el
`# 41` del bloque de medición, la lista de 41 nombres (con `database-lookup`), la fila
CONSERVAR de §Veredictos, la cobertura `41 < 60` de §Cobertura y la Open Question. El
diseño histórico se conserva; solo cambia qué cifra es vigente.

### E2 — Tabla de invocación regenerada desde los cuerpos

**Se regenera, no se degrada:** cabe en el presupuesto (9 filas medidas) y es la única
forma de que la tabla deje de mentir; degradarla a histórico dejaría al lector sin tabla
vigente.

Las skills y los subagentes son **cita literal del cuerpo**. La cuarta columna histórica
("herramientas nativas") **no se re-deriva**: los cuerpos no la declaran —solo citan
`question`— y proviene de los `permissions` de cada agente (`agents/*.md`); su fuente
vigente es [specs/spec-payload-permissions.md](spec-payload-permissions.md). Los **7 nombres
de tool** del MCP son los del contrato (`search`, `index_refresh`, `add_source`,
`convert_document`, `convert_base64`, `list_formats`, `rag_status`); la tabla anota la
**primera** cita de cada tool que el cuerpo **nombra** (y la segunda cuando cambia de fase).

| Comando (`agent:`) | Skills cargadas — `commands/<x>.md:línea` | MCP `tepochcalli-rag` nombrado | Subagentes delegados |
| --- | --- | --- | --- |
| `/rubric` (`nezahualcoyotl`) | `interview-me` :8 · `brainstorming` + `scientific-brainstorming` :9 · `idea-refine` + `scientific-problem-selection` :14 · `planning-and-task-breakdown` :27 · `obsidian-markdown` + `obsidian-vault` + `markdown-mermaid-writing` :31 · `what-if-oracle` :38 — **10** | `search` :47 · `rag_status` :48 | **ninguno** (0 `Delegate` en el cuerpo) |
| `/research` (`pochteca`) | `research-search-protocol` + `research-grants` :6 · `tepochcalli-mcp` :38 · `osint-skills` :42 · `literature-search-engine` :49 · `websearch-engine` :50 · `obsidian-markdown` + `obsidian-vault` + `citation-management` :59 — **9** | `search` :38 · `websearch`/`webfetch` + «ingest sources with `tepochcalli-rag`» :40 · `index_refresh` :69 · `rag_status` :70 | `research-analyst` :27 · `search-specialist` :38 · `scientific-literature-researcher` :49 · `obsidian-vault-writer` :59 — **4** |
| `/validate` (`chilam`) | `scholar-evaluation` :6 · `tepochcalli-mcp` :21 · `peer-review` :34 · `obsidian-markdown` + `obsidian-vault` :49 — **5** | `search` :25, :64 · `rag_status` :63 · `index_refresh` :64 | `research-analyst` :10 · `obsidian-vault-writer` :49 — **2** |
| `/synthesize` (`nezahualcoyotl`) | `doc-coauthoring` :16 · `tepochcalli-mcp` :18 · `obsidian-markdown` + `obsidian-vault` :26 — **4** | `search` :10 · `index_refresh` :10 · `rag_status` :36 | **ninguno** (0 `Delegate`) |
| `/cite` (`chilam`) | `tepochcalli-mcp` :6 · `citation-management` :17 · `obsidian-markdown` + `obsidian-vault` :28 — **4** | `rag_status` :37 | `obsidian-vault-writer` :28 — **1** |
| `/draft` (`tlacuilo`) | `tepochcalli-mcp` :9 · `scientific-writing` :19 · `obsidian-markdown` + `obsidian-vault` :20 · `markdown-mermaid-writing` + `math-typesetting-guide` :21 — **6** | `search` :9, :31 · `index_refresh` :9, :31 · `rag_status` :9, :30 | `obsidian-vault-writer` :20 — **1** |
| `/review` (`chilam`) | `tepochcalli-mcp` :9 · `peer-review` + `scholar-evaluation` :14 · `scientific-critical-thinking` :17 · `citation-management` :18 · `obsidian-markdown` + `obsidian-vault` :31 · `scientific-writing` + `article-writing` :36 — **9** | `search` :9, :46 · `index_refresh` :9, :46 · `rag_status` :47 | `research-analyst` :18 · `obsidian-vault-writer` :31 · `knowledge-synthesizer` :33 — **3** |
| `/transform` (`tlacuilo`) | `obsidian-markdown` + `obsidian-vault` :24 · `spreadsheet-analysis` :29 · `posters-generator` :35 · `paper-2-web` :41 · `pdf` :47 · `data-plotting` :53 · `tepochcalli-mcp` :59 — **8** | `list_formats` :59 · `convert_document` + `convert_base64` :61 · `search` :73 | `obsidian-vault-writer` :24 — **1** |
| `/update` (`tlacuilo`) | `tepochcalli-mcp` :10 (repetida en :15, inocuo) · `osint-skills` :19 · `literature-search-engine` :26 · `websearch-engine` :27 · `obsidian-markdown` + `obsidian-vault` :35 — **6** | `index_refresh` :10 · `add_source` :10 · `search` :15 · `websearch`/`webfetch` :17 · `rag_status` :48 | `search-specialist` :15 · `scientific-literature-researcher` :26 · `obsidian-vault-writer` :35 — **3** |

**Control de cuadre:** 10 + 9 + 5 + 4 + 4 + 6 + 9 + 8 + 6 = **61** cargas de skill en los 9
cuerpos, y los **39** nombres de E1 resuelven (el verificador de T12 da 0 huérfanos sobre
111 referencias). La spec deja de asignar
`database-lookup`, `literature-review`, `paper-2-web` (en `/research`), `statistical-analysis`
y `statistical-power` (en `/validate`), `writing-skills` (en `/draft`) y `obsidian-cli`
(en `/update`), y deja de omitir `research-grants` (`commands/research.md:6`) y
`article-writing` (`commands/review.md:36`).

### E3 — Delegaciones reales y reparto de `subagent`

`grep -c 'Delegate'` sobre los 9 cuerpos = **17** ocurrencias del verbo: **15 nombran un
subagente** (tabla siguiente) y **2** delegan de forma genérica en «appropriate/appropriated
specialist subagents» (`commands/research.md:36`, `commands/update.md:14`). Los 5 nombres
destino resuelven a `mode: subagent` (`grep -m1 '^mode:' agents/<x>.md`).

| # | Comando | Subagente | `ruta:línea` |
| --- | --- | --- | --- |
| 1 | `/cite` | `obsidian-vault-writer` | `commands/cite.md:28` |
| 2 | `/draft` | `obsidian-vault-writer` | `commands/draft.md:20` |
| 3 | `/research` | `research-analyst` | `commands/research.md:27` |
| 4 | `/research` | `search-specialist` | `commands/research.md:38` |
| 5 | `/research` | `scientific-literature-researcher` | `commands/research.md:49` |
| 6 | `/research` | `obsidian-vault-writer` | `commands/research.md:59` |
| 7 | `/review` | `research-analyst` | `commands/review.md:18` |
| 8 | `/review` | `obsidian-vault-writer` | `commands/review.md:31` |
| 9 | `/review` | `knowledge-synthesizer` | `commands/review.md:33` |
| 10 | `/transform` | `obsidian-vault-writer` | `commands/transform.md:24` |
| 11 | `/update` | `search-specialist` | `commands/update.md:15` |
| 12 | `/update` | `scientific-literature-researcher` | `commands/update.md:26` |
| 13 | `/update` | `obsidian-vault-writer` | `commands/update.md:35` |
| 14 | `/validate` | `research-analyst` | `commands/validate.md:10` |
| 15 | `/validate` | `obsidian-vault-writer` | `commands/validate.md:49` |

Reparto real de `subagent` en los 5 primarios (bloque `permissions` del frontmatter):

| Agente | Bloque | `subagent *` | Denies nominales |
| --- | --- | --- | --- |
| `itzamna` | `agents/itzamna.md:20-34` | **allow** | `nezahualcoyotl`, `pochteca`, `chilam`, `tlacuilo` |
| `nezahualcoyotl` | `agents/nezahualcoyotl.md:38-40` | **deny** | — |
| `pochteca` | `agents/pochteca.md:26-40` | **allow** | `nezahualcoyotl`, `itzamna`, `chilam`, `tlacuilo` |
| `chilam` | `agents/chilam.md:20-34` | **allow** | `nezahualcoyotl`, `pochteca`, `itzamna`, `tlacuilo` |
| `tlacuilo` | `agents/tlacuilo.md:20-34` | **allow** | `nezahualcoyotl`, `pochteca`, `chilam`, `itzamna` |

**Riesgo declarado: 4 de 5 primarios pueden delegar en cualquier subagente.** Los denies
nominales solo bloquean a **los otros 4 primarios**: no acotan el catálogo de **165**
agentes `mode: subagent` (`grep -h '^mode:' agents/*.md | sort | uniq -c` → 5 primary /
165 subagent; `ls agents | wc -l` = 170). Es decir, `itzamna`,
`pochteca`, `chilam` y `tlacuilo` pueden invocar cualquiera de los 165 sin restricción de
nombre, aunque los cuerpos solo nombren 5. `nezahualcoyotl` es el único hermético, y es
coherente con los cuerpos: `/rubric` y `/synthesize` no delegan y `agents/nezahualcoyotl.md:160`
lo dice en prosa («NEVER delegate to subagents»).

### E4 — Qué **no** se toca

* **El payload sigue congelado** (D-P6-1): ni un byte de `obsidian-workspace/`. Esta
  enmienda es documental; el payload ya era coherente (0 huérfanos, 15 delegaciones
  resueltas).
* **Cerrar el `subagent * allow`** de los 4 primarios exige **cambio de payload** (editar
  los 4 bloques `permissions`) o un **ADR nuevo** que reemplace la política — no esta
  enmienda, que solo declara el hecho medido.
* **La cuarta columna «herramientas nativas»** sigue viviendo en
  [specs/spec-payload-permissions.md](spec-payload-permissions.md); aquí no se duplica ni se
  re-deriva.
* **El verificador** `tests/e2e/verify_payload_refs.py` (T12) es el gate reproducible de
  esto: pone rojo un huérfano de skill y una delegación a un no-subagente. No sustituye a
  esta spec; la comprueba.
