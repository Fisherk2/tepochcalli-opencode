# Spec: Blueprint del payload del vault — agentes, comandos y AGENTS.md (OpenCode V2)

* **Status:** Proposed
* **Fase:** Phase 4 (diseño) — lienzo vivo de esta spec; gate: BLUEPRINT APPROVED por el usuario; Phase 5 ejecuta literal (sin reinterpretación)
* **Date:** 2026-10-21
* **Author:** Arquitecto (blueprint confirmado por el usuario 2026-10-21)
* **Reviewers:** Product Owner (usuario)
* **Traceability:** specs/spec-agent-workflow.md (mapa comandos→bandejas D9.2, desviación Pochteca D9.3, reglas del AGENTS del vault), specs/spec-vault-structure.md (zonas D9.1), specs/spec-mcp-server.md (4 tools + taxonomía `E_*`), docs/UH.md (tabla Agentes Primarios — inmutable), docs/WORKFLOW.md Phases 4 (diseño) y 5 (ejecución); reglas de formato OpenCode V2 verificadas contra docs oficiales el 2026-10-21

## Summary

Esta spec es el **blueprint ejecutable** del payload distribuible: el contenido exacto de los 5
agentes primarios (`.opencode/agents/{itzamna,nezahualcoyotl,pochteca,chilam,tlacuilo}.md`), los 9
comandos de la metodología (`.opencode/commands/*.md`) y el `AGENTS.md` del vault, en formato
OpenCode V2. **No se escribe nada ahora**: por decisión explícita del usuario (2026-10-21),
`obsidian-workspace/` queda intacto bajo /spec; la ejecución del blueprint es labor de **Phase 5
vía /plan**, por agentes autorizados, de forma LITERAL desde esta spec Approved. Los permisos por agente viven SOLO en los `.md`; los modelos
viven SOLO en `opencode.json` (no duplicar en ambos lugares).

## Problem / Motivation

La metodología D9 (comandos→bandejas, MCP-first, no-contaminación) solo es real si los artefactos
del harness la reflejan: stubs sin cuerpo y permisos hereditarios de un template de desarrollo NO
aplican el diseño. Un despacho anterior autorizó reescribir el payload; el usuario lo corrigió
(2026-10-21): el diseño se DOCUMENTA aquí (Phase 4) y se EJECUTA en Phase 5. Esta spec congela el blueprint.

> Como investigador, quiero que /rubric → /update enruten solos al agente correcto y que ningún
> agente pueda escribir fuera de su bandeja — sin configurar nada a mano.

## Goals and Non-Goals

### Goals

* Documentar verbatim-fiel el blueprint de permisos (5 YAML), comandos (9) y `AGENTS.md` del vault (7 secciones).
* Congelar las reglas de formato OpenCode V2 verificadas 2026-10-21 (frontmatter permitido, last-match-wins, prohibiciones).
* Definir los criterios de aceptación de la ejecución (Phase 5), linkables desde docs/WORKFLOW.md.

### Non-Goals (fuera de scope — decisión usuario 2026-10-21)

* Instalación/saneamiento de skills (Anexo A; decisión en la matriz de esta spec, obra de /plan Phase 5). Esta spec NO referencia skills inexistentes.
* Borrado de subagents: los ~170 archivos de `.opencode/agents/` (5 primarios + ~165 del pack Códice) se CONSERVAN.
* Cambiar `obsidian-workspace/` desde /spec: **PROHIBIDO**. Ningún archivo del payload se modifica con esta ola.

## Proposed Solution

Phase 5 materializa 15 archivos de texto desde los bloques de esta spec (5 agents, 9 commands,
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

### Nota de fusión con `opencode.json` (verificación en Phase 5, sin duplicar)

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

Regla de skills en `/transform`: citar SOLO skills presentes hoy en `.opencode/skills/` (la matriz
§Matriz de conflictos se construyó contra el `ls` del 2026-10-21; Phase 5 repite el `ls` antes de
generar): `xlsx`/`excel-analysis`/`data-transform` (CSV/Excel),
`scientific-slides`/`pptx-official` (presentaciones), `markdown-mermaid-writing` (mapa mental vía
`mindmap` de Mermaid), `matplotlib`/`plotly`/`seaborn`/`scientific-visualization` (figuras),
`markitdown` (conversión). Gaps Jupyter / R / Graphviz-PlantUML / LaTeX-manuscrito: declarados
como pendientes del Anexo A (su instalación NO es labor de esta spec); el comando los menciona como
"pendiente de Phase 5 (Anexo A)" sin inventar nombres.

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

### Tabla de invocación por comando (9×4 — lienzo Phase 4)

Referencia cruzada de cada comando contra el inventario REAL. Las columnas de skills citan nombres que EXISTEN hoy en `.opencode/skills/` (ls 2026-10-21, 208 dirs); donde la matriz de conflictos CONSOLIDA una familia, Phase 5 deja de citar a la perdedora y conserva la ganadora (marcadas ⟵G). Política de subagentes: los 5 primarios llevan `subagent * deny` — SI un comando necesitara un helper, se DOCUMENTA aquí como enmienda pendiente al blueprint; no se inventa.

| Comando | Skills concretas (inventario real) | Herramientas nativas | MCPs a ejecutar | Subagentes permitidos |
|---|---|---|---|---|
| `/rubric` | scientific-problem-selection, experimental-design, writing-plans | read · glob · grep · question · todowrite | `tepochcalli-rag`: search (dimensionar corpus), rag_status ante `E_*` | ninguno |
| `/research` | deep-research⟵G, research-lookup⟵G, paper-lookup⟵G, arxiv-search⟵G, pubmed-search⟵G, wikipedia-search, multi-search-engine, parallel-web | webfetch · websearch · read · edit `01-tasks/research/**` | search · index_refresh · add_source (ingesta externa vía markitdown MCP) · rag_status | ninguno |
| `/validate` | scholar-evaluation⟵G, scientific-critical-thinking, analytical-method-validation, uncertainty-and-units | read · glob · grep · edit `04-review/**` | search (cruce con corpus) · rag_status | ninguno |
| `/synthesize` | idea-refine⟵G, markdown-mermaid-writing | read · glob · grep · edit `01-tasks/**` | search · rag_status | ninguno |
| `/cite` | citation-management, venue-templates | read · glob · grep · edit `03-citations/**` | search (verificar procedencia) · rag_status | ninguno |
| `/draft` | scientific-writing⟵G, doc-coauthoring, obsidian-markdown⟵G, markdown-mermaid-writing | read · edit `02-drafts/**` | search · rag_status | ninguno |
| `/review` | peer-review, review-writing⟵G, scholar-evaluation⟵G | read · glob · grep · edit `04-review/**` | search · rag_status | ninguno |
| `/transform` | xlsx-official⟵G, excel-analysis⟵G, data-transform⟵G, scientific-slides, pptx-official⟵G, markdown-mermaid-writing (mindmap), matplotlib⟵G, scientific-visualization⟵G, infographics | read · edit `02-drafts/**` (fuente) y `05-outputs/**` (salida) | search · rag_status; `excel` MCP: disabled y break `--offline` → manda la skill (grupo 3); `jupyter` MCP: disabled, sin skill → GAP | ninguno; Jupyter/Graphviz/R = GAP Anexo A, se declaran sin inventar |
| `/update` | obsidian-markdown⟵G, scientific-writing⟵G | read · glob · grep · edit `02-drafts/**` | search · index_refresh (si hay ingesta nueva) · add_source solo si el usuario lo pide · rag_status | ninguno |

### Matriz de conflictos/redundancias de skills (inventario REAL, 2026-10-21)

Contra `ls obsidian-workspace/.opencode/skills/` = **208 dirs** (recuento de esta ola). Veredictos: **CONSERVAR / CONSOLIDAR (nominando ganadora) / RETIRAR (out-of-domain) / INSTALAR-GAP**. Cobertura: filas 1-13 nombran 58 dirs en conflicto explícito; fila 14 suma 14 ganadoras del núcleo en dominio; fila 15 barre el resto por familia (~120 out-of-domain según Anexo A; el remanente en dominio no listado se falla CONSERVAR por el criterio de la fila 14); fila 16 gaps = 0 dirs hoy. Phase 5 repite el `ls` y cierra el recuento 1:1 por fila (métrica WORKFLOW: 100% del inventario).

| Grupo | Skills miembros (inventario real) | Solape/conflicto | Veredicto | Acción Phase 5 |
|---|---|---|---|---|
| 1. PDF ×5 | pdf, pdf-anthropic, pdf-processing, pdf-processing-pro, liteparse | cuatro wrappers de la misma conversión; liteparse duplica al motor (Docling, spec-rag-engine) | CONSOLIDAR — gana `pdf` (general) + `pdf-processing-pro` (documentos largos) | retirar 3 (pdf-anthropic, liteparse, uno de processing) |
| 2. Office ×6 | docx, docx-official, pptx, pptx-official, xlsx, xlsx-official | duplicado exacto por familia | CONSOLIDAR — ganan `docx-official`, `pptx-official`, `xlsx-official` | retirar 3 variantes libres |
| 3. Excel/MCP | excel-analysis, data-transform + entrada `excel` MCP en opencode.json (disabled; `uvx` → rompe `--offline`) | tres caminos para CSV/Excel | CONSOLIDAR — gana la vía skill (offline-safe) | retirar 1 (`data-transform` si `excel-analysis` cubre); dejar/eliminar la entrada MCP disabled |
| 4. Literatura ×14 | literature, literature-search, literature-review, research-literature, academic-literature-search, paper-lookup, arxiv-search, biorxiv-search, medrxiv-search, pubmed-search, pubmed-database, openalex-database, bgpt-paper-search, paperzilla | buscadores redundantes; las bases bio/med específicas son out-of-domain para el payload genérico | CONSOLIDAR — ganan `research-lookup` (general) + `arxiv-search` + `pubmed-search` | retirar 11 |
| 5. Deep research ×4 | deep-research, deep-research-swarm, tooluniverse-literature-deep-research, research-lookup | variantes de orquestación duplican búsqueda; swarm = coste de tokens contra criterio 4 | CONSOLIDAR — ganan `deep-research` + `research-lookup` | retirar 2 (swarm, tooluniverse) |
| 6. markitdown skill × markitdown MCP | skill `markitdown` + MCP `markitdown` (lo añade el wizard, fase 8) | mismo convertidor por dos canales | CONSERVAR con nota: **el MCP manda en el flujo RAG** (`add_source`); la skill queda para conversión ad-hoc multi-archivo sin tocar índice | mantener ambos; nota en AGENTS.md del vault |
| 7. Obsidian trío + instructions | obsidian-markdown, obsidian-vault, obsidian-cli | vault×cli se solapan en gestión de notas; el json del workspace lista además `markdown-mermaid-writing` | CONSOLIDAR — ganan `obsidian-markdown` (formato) + `obsidian-cli` (gestión); `obsidian-vault` se fusiona | retirar 1; actualizar `instructions` de `opencode.json` si se retira la skill |
| 8. Estadística ×4 | statistical-analysis, data-stats-analysis, statsmodels, statistical-power | data-stats-analysis duplica el rango de statistical-analysis | CONSOLIDAR — ganan `statistical-analysis` + `statsmodels` (statistical-power como helper CONSERVAR) | retirar 1 |
| 9. Visualización ×5 | matplotlib, seaborn, plotly, data-viz-plots, scientific-visualization | wrappers sobre los mismos backends | CONSOLIDAR — entry point `scientific-visualization` + backends `matplotlib`/`seaborn`/`plotly` | retirar 1 (`data-viz-plots`) |
| 10. Brainstorm/ideas ×6 | brainstorming, scientific-brainstorming, hypothesis-generation, hypogenic, idea-refine, what-if-oracle | ideación redundante | CONSOLIDAR — ganan `scientific-brainstorming` + `hypothesis-generation`; `idea-refine` queda para /synthesize | retirar 3 (brainstorming, hypogenic, what-if-oracle) |
| 11. Escritura ×5 | article-writing, scientific-writing, scientific-manuscript, doc-coauthoring, review-writing | scientific-manuscript solapa con scientific-writing (nota Anexo A); article-writing es divulgación/diseminación | CONSOLIDAR — gana `scientific-writing`; CONSERVAR `doc-coauthoring`, `review-writing`, `article-writing` (roles distintos) | retirar 1 (scientific-manuscript) |
| 12. RAG-chat paralelo | open-notebook | NotebookLM-like local: solape frontal con tepochcalli-rag (que ES el producto) | RETIRAR | retirar 1 |
| 13. Creativo/visual suelto | generate-image | generación de imagen creativa, fuera de la metodología | RETIRAR (infographics se CONSERVA: salida de `/transform`) | retirar 1 |
| 14. Núcleo metodológico sin conflicto (restantes en dominio) | p. ej. citation-management, experimental-design, writing-plans, scientific-problem-selection, scientific-critical-thinking, analytical-method-validation, uncertainty-and-units, venue-templates, scientific-slides, paper-2-web, exploratory-data-analysis, networkx, sympy, shap | sin solape material para el pipeline 9/5 | CONSERVAR | mantener en payload base |
| 15. Out-of-domain para payload genérico (grosso del remanente) | scanpy, pydeseq2, qiime2-amplicon, neuropixels-analysis, diffdock, qiskit, matlab, geopandas y `gis-*` (×14), `marketing-*` (×37), `finance-*`/`sales-*`/`legal-*`/`healthcare-*`/`paid-media-*`/`product-*`/`design-*`, y el resto del inventario no nombrado arriba | no corresponden a las 14 categorías UH de investigación general | RETIRAR → "skill pack" opcional futuro | retirar del payload base (Anexo A; PACK=1 en CI para no romper referencias); el remanente en dominio (p. ej. polars, dask, vaex, zarr-python, pyzotero, scientific-schematics, exa-search, perplexity-search, patents-search, database-lookup, wikipedia-search, multi-search-engine) se falla CONSERVAR por el criterio de la fila 14 |
| 16. Gaps UH (sin skill hoy) | jupyter (cuadernos), R (graficación estadística), Graphviz/PlantUML (diagramas), LaTeX de manuscrito (`latex-posters` no cubre manuscrito) | categorías #10/#11/#14 de UH sin cubrir | INSTALAR-GAP | Phase 5 instala según Anexo A o declara won't (gate WORKFLOW) |

* Cierre de cobertura: filas 1-14 nombran explícitamente 72 de los 208 dirs del `ls`; fila 15 barre el resto por familia con criterio decidido (RETIRAR out-of-domain ≈120 / CONSERVAR remanente en dominio); fila 16 declara los gaps. **Objetivo del payload final: <60 skills en el payload base** (métrica heredada de WORKFLOW Phase 5).

## Alternatives Considered

* **Ejecutar el rediseño del payload ahora (bajo /spec):** *rechazado:* el usuario corrigió el
  despacho — `obsidian-workspace/` intocable hasta Phase 5 (ejecución); el contenido vive como blueprint de Phase 4.
* **Convertir el blueprint en un ADR:** *rechazado:* no es una decisión nueva — D9/ADR-005/007 ya
  están Accepted; esto es documentación de ejecución (spec).
* **Itzamná invocando subagents para "enrutar":** *rechazado:* viola la pureza de la sesión y el
  patrón V2 nativo (`agent:` en comandos cambia la sesión al primary).

## Trade-offs

* ✅ **Pros:** blueprint congelado y grepeable; Phase 5 se vuelve mecánica; permisos como datos por archivo; payload coherente con D9.
* ⚠️ **Cons / Risks:** dos fuentes (esta spec + stubs actuales) hasta Phase 5 — el drift se corta con los criterios de aceptación; el deny-list de Tlacuilo depende de mantener el orden last-match.
* ⚖️ **Neutral:** los ~165 subagents Códice quedan en disco, no invocables — catálogo inerte.

## Testing Strategy — criterios de aceptación de la ejecución (Phase 5)

Linkables desde docs/WORKFLOW.md Phase 5 ("Validación del agent workflow (D9)"):

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

* El payload es texto versionado: rollback = `git checkout` del archivo. Tras la ejecución Phase 5,
  smoke: sesión nueva, `/rubric`, y verificar `opencode agents list` + routing real.
* Señal de deriva: cualquier diff de `.opencode/agents/*.md` que no cite esta spec en el commit.

## Open Questions

* ¿El array global `permissions` de `opencode.json` (higiene heredada del pack Códice) se elimina
  al ejecutar el blueprint para que los permisos queden SOLO en los `.md`? (verificación exigida
  por §Nota de fusión; decisión al ejecutar Phase 5)

## References

* OpenCode V2 docs (agents/commands/permissions) — verificación 2026-10-21
* specs/spec-agent-workflow.md (D9.2/D9.3, Anexo A), specs/spec-vault-structure.md (D9.1),
  specs/spec-mcp-server.md (contrato 4 tools + `E_*`), docs/UH.md (tabla Agentes Primarios),
  docs/WORKFLOW.md Phases 4 (diseño) y 5 (ejecución)
