# Spec: Skills del payload — inventario definitivo y tabla de invocación

* **Status:** Approved (BLUEPRINT APPROVED 2026-11-09 — gate concedido por congelamiento del dueño: 40 skills definitivas, `cf17f31`/`2e62e60`) · **Enmendada 2026-11-11** ([ADR-012](../specs/adr/adr-012-formato-payload-revisado.md): 41 skills con `math-typesetting-guide`; D-P5-1 SUPERSEDED)
* **Fase:** Phase 4 (diseño) — Phase 5 verifica, no ejecuta cortes
* **Date:** 2026-11-09 (congela inventario; rev. 2026-11-04 SUPERSEDED, ver §Histórico)
* **Author:** Arquitecto (calpulli T2b, Phase 4)
* **Reviewers:** Product Owner (usuario)
* **Traceability:** [specs/spec-payload-vault.md](spec-payload-vault.md) (blueprint; la §Tabla de invocación 9×4 es T3), [specs/spec-agent-workflow.md](spec-agent-workflow.md) (Anexo A — auditoría de 208 skills, 2026-10-21), [specs/spec-vault-structure.md](spec-vault-structure.md) (zonas D9.1), [docs/TECH_DEBT.md](../docs/TECH_DEBT.md) TD-7 y TD-22, [docs/UH.md](../docs/UH.md) (áreas de investigación; la fuente no las numera), [docs/WORKFLOW.md](../docs/WORKFLOW.md) Phase 4 y Phase 5

## Summary

Esta spec es dueña de tres cosas del payload: el **inventario definitivo de skills**
(40 dirs, 2026-11-09), la **tabla de invocación comando→herramientas (9×4)** — movida aquí
desde [specs/spec-payload-vault.md](spec-payload-vault.md) en T3 (D-P4-4) — y el
**inventario de muestras** que produce el instalador (D-P4-7).

**Congelado 2026-11-09 (decisión del dueño):** `obsidian-workspace/.opencode/skills/` queda
**definitivo con 40 dirs**. Veredictos: **CONSERVAR 40/40, RETIRAR 0, CONSOLIDAR 0,
INSTALAR-GAP 0**. Phase 5 **verifica presencia (40 presentes, 0 retiros)** y no ejecuta
ninguna matriz de recorte. La matriz de 17 filas de la rev. 2026-11-04 queda **SUPERSEDED**
y se conserva solo como histórico colapsado (§Histórico) — **no ejecutar**.

**Enmienda 2026-11-11 ([ADR-012](../specs/adr/adr-012-formato-payload-revisado.md)):** el
dueño autorizó la skill 41 (`math-typesetting-guide`, commit `1c4a90b`, invocada desde §3
del `AGENTS.md` del payload). D-P5-1 (freeze 40) queda **SUPERSEDED**; el inventario pasa
a **41 dirs**, objetivo <60 sigue cumplido (41 < 60).

No es dueña de: los cuerpos de comandos, agentes y `AGENTS.md` del vault (spec del
blueprint). **No se escribe nada en `obsidian-workspace/` en esta fase.**

## Inventario definitivo (2026-11-09)

```bash
# fecha de la medición: 2026-11-09 (40); enmienda 2026-11-11: 41 con math-typesetting-guide
ls obsidian-workspace/.opencode/skills | wc -l                    # 41
find obsidian-workspace/.opencode/agents -name '*.md' | wc -l    # 170
find obsidian-workspace/.opencode/commands -name '*.md' | wc -l  # 9
ls obsidian-workspace/00-Resources | wc -l                        # 0 (muestras de instalación: ver abajo)
wc -c obsidian-workspace/.opencode/skills/tepochcalli-mcp/SKILL.md # 13098 (cuerpo en inglés)
```

* **0 skills citadas e inexistentes**: toda referencia de comandos y agentes resuelve contra el `ls`.
* **Cobertura 40/40** (2026-11-09): las 40 están citadas o disponibles para la tabla 9×4; ninguna cae en barrido.
* **41 nombres** (2026-11-11: los 40 + `math-typesetting-guide`), orden alfabético:

article-writing · brainstorming · citation-management · consciousness-council ·
data-analysis · data-plotting · database-lookup · doc-coauthoring · experimental-design ·
hypothesis-generation · idea-refine · image-prompt-generator · interview-me ·
literature-review · literature-search-engine · markdown-mermaid-writing ·
math-typesetting-guide · obsidian-cli ·
obsidian-markdown · obsidian-vault · osint-skills · paper-2-web · pdf · peer-review ·
planning-and-task-breakdown · posters-generator · research-grants ·
research-search-protocol · scholar-evaluation · scientific-brainstorming ·
scientific-critical-thinking · scientific-problem-selection · scientific-writing ·
spreadsheet-analysis · statistical-analysis · statistical-power · tepochcalli-mcp ·
toon · websearch-engine · what-if-oracle · writing-skills

### Veredictos (un cubo: 40)

| Cubo | Dirs | Qué son |
| --- | --- | --- |
| CONSERVAR (definitivo) | 40 (+1 enmienda 2026-11-11: `math-typesetting-guide` ⇒ 41) | las del inventario; sin recorte, sin fusión, sin instalación |
| RETIRAR | 0 | congelado: ningún retiro en Phase 5 |
| CONSOLIDAR | 0 | congelado: ninguna fusión en Phase 5 |
| INSTALAR-GAP | 0 | v1 no instala ninguna skill nueva |

## Tabla de invocación por comando (9×4)

`9×4` = **9 filas** (una por comando) × **4 columnas de contenido** (skills concretas,
herramientas nativas, MCPs a ejecutar y subagentes permitidos); la primera columna solo
etiqueta el comando con su `agent:` de stub. Toda skill citada existe en el `ls` de 40;
donde la rev. anterior citaba una skill que ya no existe, se sustituye por el equivalente
de los 40 o se declara **GAP**. Los 7 nombres de tool se copian verbatim de
`obsidian-workspace/.tepochcalli/mcp/tepochcalli_mcp/server.py` (`@server.tool()`):
`search`, `index_refresh`, `add_source`, `convert_document`, `convert_base64`,
`list_formats`, `rag_status`. Los nombres nativos son el vocabulario V2 de
[specs/spec-payload-vault.md](spec-payload-vault.md) §Vocabulario de acciones V2.

| Comando | Skills concretas (inventario 40) | Herramientas nativas | MCPs a ejecutar | Subagentes permitidos |
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
  manuscrito no tienen skill en el inventario de 40: `/transform` los declara como pendientes
  de Phase 5 sin inventar nombres.
* **`venue-templates` = GAP declarado:** sin skill de plantillas de venue en los 40; `/cite`
  usa `citation-management` + `paper-2-web`.
* **`officecli` no se cita** como skill ni como MCP: es binario del wizard (TD-22, feature 0.2.0).
* **Permisos MCP:** el mapeo `<server>_<tool>` por agente es de T4
  ([specs/spec-payload-vault.md](spec-payload-vault.md) §permisos); esta tabla solo declara
  qué tool ejecuta cada comando.
* **Subagentes:** **ninguno** en las 9 filas — los 5 primarios llevan `subagent * deny`; si un
  comando necesitara un helper, se documenta antes como enmienda al blueprint.

## Cobertura y objetivo <60

Cobertura del inventario: **40/40** (2026-11-09; toda skill del `ls` está conservada;
0 huérfanas fuera de tabla porque el congelado no exige cita exhaustiva).

El objetivo de menos de 60 skills del payload base (métrica heredada de
[docs/WORKFLOW.md](../docs/WORKFLOW.md) Phase 5 y de TD-7) queda **CUMPLIDO: 41 < 60**
(40 al congelado 2026-11-09 + `math-typesetting-guide` por enmienda 2026-11-11,
[ADR-012](../specs/adr/adr-012-formato-payload-revisado.md)).
**No se ejecuta ningún corte ni consolidación en Phase 5** — el inventario ya está por
debajo del umbral por decisión del dueño (2026-11-09).

**Nota TD-22 (OfficeCLI, 0.2.0) — sin contradicción:** TD-22 gobierna la **feature 0.2.0**;
si OfficeCLI entrara, su tarea retiraría entonces las skills de ofimática que toque. En v1
las 40 se quedan.

**Decisión explícita (se mantiene): 0 skills nuevas para el protocolo de opendraft.** Los
gates heredados (procedencia, check de claim, gate de compilación) son invariantes de
workflow y viven en los cuerpos de `/research`, `/validate` y `/cite`, jamás en una skill
(una skill es oportunista; un cuerpo de comando se ejecuta siempre). `citation-management`
(cubo CONSERVAR) cubre la mecánica DOI→BibTeX/dedupe/validación de metadata; el protocolo
la complementa desde el comando, no la duplica. (Origen: análisis de
federicodeponte/opendraft, 2026-10-28.)

## Inventario de muestras del payload

`00-Resources/` está **vacío** en el repo: las muestras del golden-vault las crea el
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

* Ninguna abierta. El congelado de 40 y las muestras (sin cambio) quedan como están por
  decisión del dueño (2026-11-09); la matriz histórica queda SUPERSEDED. Enmienda
  2026-11-11: inventario en 41 (`math-typesetting-guide`, [ADR-012](../specs/adr/adr-012-formato-payload-revisado.md)).

## References

* [specs/spec-payload-vault.md](spec-payload-vault.md) — blueprint de agentes, permisos y `AGENTS.md`; puntero a esta spec para la tabla 9×4 (D-P4-4)
* [specs/spec-agent-workflow.md](spec-agent-workflow.md) — Anexo A: auditoría de 208 skills (2026-10-21) y gaps accionables
* [docs/TECH_DEBT.md](../docs/TECH_DEBT.md) — TD-7 (skills infladas) y TD-22 (OfficeCLI 0.2.0)
* [docs/UH.md](../docs/UH.md) — áreas de investigación pedidas (sin numeración en la fuente)
* [docs/WORKFLOW.md](../docs/WORKFLOW.md) — Phase 4 (diseño) y Phase 5 (payload + verificación 40)
* [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) — capas y contratos que el payload debe respetar
* `crates/tepochcalli/src/application/installer.rs` (muestras del instalador) y `crates/tepochcalli/assets/ejemplo.pdf`
* [AGENTS.md](../AGENTS.md) — R1/R2 (no reinventar, cero asunción) y umbrales de líneas por fichero
