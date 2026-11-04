# Spec: Skills del payload — inventario, matriz de conflictos y muestras

* **Status:** Proposed (gate: BLUEPRINT APPROVED por el usuario)
* **Fase:** Phase 4 (diseño) — resultado del split del blueprint en 4 specs (D-P4-4); Phase 5 ejecuta literal
* **Date:** 2026-11-04
* **Author:** Arquitecto (calpulli T2b, Phase 4)
* **Reviewers:** Product Owner (usuario)
* **Traceability:** [specs/spec-payload-vault.md](spec-payload-vault.md) (blueprint de agentes/comandos/AGENTS.md; la §Tabla de invocación 9×4 es T3), [specs/spec-agent-workflow.md](spec-agent-workflow.md) (Anexo A — auditoría de 208 skills, 2026-10-21), [specs/spec-vault-structure.md](spec-vault-structure.md) (zonas D9.1), [docs/TECH_DEBT.md](../docs/TECH_DEBT.md) TD-7 (skills infladas) y TD-22 (OfficeCLI 0.2.0), [docs/UH.md](../docs/UH.md) (áreas de investigación; la fuente no las numera), [docs/WORKFLOW.md](../docs/WORKFLOW.md) Phase 4 (diseño) y Phase 5 (payload + skills audit)

## Summary

Esta spec es dueña de tres cosas del payload: el **inventario real de skills** (209 dirs,
2026-11-04), la **matriz de conflictos/redundancias** (17 filas) con su **recuento derivado**, y el
**inventario de muestras** que produce el instalador (D-P4-7).

No es dueña de: la tabla de invocación comando→skills (T3, en [specs/spec-payload-vault.md](spec-payload-vault.md)
§Tabla de invocación 9×4), los cuerpos de comandos, agentes y `AGENTS.md` del vault (spec del
blueprint), ni la instalación de gaps (Anexo A de [specs/spec-agent-workflow.md](spec-agent-workflow.md),
decisión de Phase 5). **No se escribe nada en `obsidian-workspace/` en esta fase.**

## Inventario real (2026-11-04)

```bash
# fecha de la medición: 2026-11-04
ls obsidian-workspace/.opencode/skills | wc -l                    # 209
find obsidian-workspace/.opencode/agents -name '*.md' | wc -l    # 170
find obsidian-workspace/.opencode/commands -name '*.md' | wc -l  # 9
ls obsidian-workspace/00-Resources | wc -l                        # 0 (muestras de instalación: ver abajo)
wc -c obsidian-workspace/.opencode/skills/tepochcalli-mcp/SKILL.md # 13098 (cuerpo en inglés)
```

* **0 skills citadas e inexistentes**: toda referencia de comandos y agentes resuelve contra el `ls`.
* **112 dirs presentes y nunca citados**: los cubre el barrido de la fila 15 de la matriz.
* **209 nombres**, lectura directa (2026-11-04):

<!-- markdownlint-disable MD033 -->
<details>
<summary>Ver listado completo (209)</summary>

academic-literature-search · aeon · agent-browser · analytical-method-validation · anndata · arbor · arboreto · article-writing · arxiv-search · astropy · autoskill · benchling-integration · bgpt-paper-search · bids · biopython · biorxiv-database · biorxiv-search · brainstorming · bulk-rnaseq · cantera · cirq · citation-management · cobrapy · consciousness-council · dask · data-stats-analysis · data-transform · data-viz-plots · database-lookup · datalad · datamol · deep-research · deep-research-swarm · deepspot-m · deeptools · depmap · diffdock · doc-coauthoring · docx · docx-official · esm · etetoolkit · exa-search · excel-analysis · experimental-design · exploratory-data-analysis · fictiv · flowio · flowkit · fluidsim · folklore-variant-evidence · generate-image · geo-database · geomaster · geopandas · get-available-resources · gget · ginkgo-cloud-lab · gtars · gwas-database · histolab · hmdb-database · hugging-science · hypogenic · hypothesis-generation · idea-refine · imaging-data-commons · infographics · interview-me · iso-standards-readiness · lab-hardware-cad · labarchive-integration · lamindb · latex-posters · liteparse · literature · literature-review · literature-search · literature_to_hypothesis · mageck · markdown-mermaid-writing · market-research-reports · markitdown · matchms · matlab · matplotlib · medrxiv-search · modal · molecular-dynamics · molfeat · multi-search-engine · ncats-arax · networkx · neurokit2 · neuropixels-analysis · nextflow · nmrglue · nwb-conversion · obsidian-cli · obsidian-markdown · obsidian-vault · omero-integration · onekgpd · ontology-term-resolution · open-notebook · openalex-database · openpiv · opentrons-integration · optimize-for-gpu · pacsomatic · paper-2-web · paper-lookup · paperclip · paperzilla · parallel-web · patents-search · pathway-enrichment · pdb-database · pdf · pdf-anthropic · pdf-processing · pdf-processing-pro · peer-review · pennylane · perplexity-search · pi-agent · pkpd-modeling · plotly · polars · polars-bio · pptx · pptx-official · pptx-posters · primekg · primer-design · protocol-writing · protocolsio-integration · pubmed-database · pubmed-search · pufferlib · pybamm · pycalphad · pydeseq2 · pydicom · pyhealth · pylabrobot · pymatgen · pymc · pymoo · pyopenms · pysam · pytdc · pytorch-lightning · pyzotero · qiime2-amplicon · qiskit · qutip · relion · relsa-severity-assessment · research-grants · research-literature · research-lookup · review-writing · scanpy · scholar-evaluation · scientific-brainstorming · scientific-critical-thinking · scientific-manuscript · scientific-problem-selection · scientific-schematics · scientific-slides · scientific-visualization · scientific-writing · scikit-bio · scikit-learn · scikit-survival · scvelo · scvi-tools · seaborn · shap · simpy · stable-baselines3 · statistical-analysis · statistical-power · statsmodels · sympy · tamarind · tellurium · tepochcalli-mcp · tiledbvcf · timesfm-forecasting · tooluniverse-literature-deep-research · torch-geometric · torchdrug · transformers · treatment-plans · umap-learn · uncertainty-and-units · usfiscaldata · uspto-database · vaex · venue-templates · what-if-oracle · wikipedia-search · writing-plans · writing-skills · xlsx · xlsx-official · zarr-python

</details>
<!-- markdownlint-enable MD033 -->

### Veredictos (4 cubos, suman 209)

| Cubo | Dirs | Qué son |
| --- | --- | --- |
| CONSERVAR (explícito) | 34 | nombradas con veredicto de conservación (filas 6, 8, 11, 13, 17 y 14) |
| CONSOLIDAR — supervivientes | 21 | ganadoras nominadas en las filas 1, 2, 3, 4, 5, 7, 9, 10 y 11; las perdedoras pasan a RETIRAR |
| CONSERVAR por defecto | 5 | citadas por los comandos sin fila en la matriz: `markdown-mermaid-writing`, `multi-search-engine`, `parallel-web`, `peer-review`, `wikipedia-search` |
| RETIRAR (explícito) | 37 | 29 de las filas 1-13 + 8 nombradas como ejemplo en la fila 15 |
| INSTALAR-GAP | 0 | v1 no instala ninguna skill nueva; los 4 gaps del Anexo A quedan declarados como no instalados (fila 16) |
| Barrido sin nombrar | 112 | resto del inventario, cubierto por familias en la fila 15 |
| **Total** | **209** | 34 + 21 + 5 + 37 + 0 + 112 |

Nombrado explícitamente = 34 + 21 + 5 + 37 = **97** (58 dirs en las filas 1-13 + 14 en la fila 14 +
19 en la fila 15 + 1 en la fila 17 = 92 con veredicto, más las 5 citadas sin veredicto). Nombrado +
barrido = 97 + 112 = 209.

## Inventario de muestras del payload (D-P4-7)

`00-Resources/` está **vacío** en el repo (ver el `ls` de arriba): las muestras del golden-vault las
crea el instalador en tiempo de instalación. Todo lo de esta tabla vive en el crate `tepochcalli`,
no en el payload.

| Artefacto | Ruta / constante | Estado actual | Objetivo (inglés) | Acción Phase 5 |
| --- | --- | --- | --- | --- |
| Nombre de la nota | `crates/tepochcalli/src/application/installer.rs:46` `PLACEHOLDER_MD_NAME` | valor `ejemplo.md` | `example.md` | renombrar la constante y sus usos |
| Nombre del PDF | `installer.rs:47` `PLACEHOLDER_PDF_NAME` | valor `ejemplo.pdf` | `example.pdf` | renombrar la constante y sus usos |
| Cuerpo de la nota | `installer.rs:49-53` `PLACEHOLDER_MD_BODY` | español: empieza por `# Ejemplo` y explica que es un «marcador de posición creado por `tepochcalli install`» | cuerpo en inglés con el mismo mensaje (dónde escribir, cuándo indexa el RAG) | traducir el literal |
| Bytes del PDF | `installer.rs:58` `EJEMPLO_PDF` = `include_bytes!` de `crates/tepochcalli/assets/ejemplo.pdf` | PDF válido de **592 bytes**; su única línea de contenido es `Hola tepochcalli` | PDF mínimo con el texto en inglés (p. ej. `Hello tepochcalli`) | regenerar el asset, renombrar la constante a `EXAMPLE_PDF` y corregir la ruta |
| Generador del PDF | comentario de `EJEMPLO_PDF` (installer.rs:55-57) cita `gen_ejemplo_pdf.py` | **el script no existe en el repo** (búsqueda por nombre en todo el árbol: 0 resultados) | generador versionado, o comentario que no cite un artefacto inexistente | crear un generador mínimo y commitearlo, o reescribir el comentario |
| Carpeta de bandeja | `obsidian-workspace/01-Tasks/` | existe y está trackeada con 3 ficheros de 0 bytes (`outline.md`, `rubric.md`, `todo.md`); `01-tasks/` **no** existe | `01-tasks/` (convención D9.1 en minúsculas) | renombrar la carpeta en el payload; no crearla |

**Riesgo de caso (vecino de TD-8):** en sistemas de ficheros insensibles a mayúsculas (macOS,
Windows) un `create_dir_all` con `01-tasks` de Phase 5 **adopta silenciosamente** `01-Tasks/`; en
Linux conviven las dos. Phase 5 debe **renombrar**, no crear, y verificar el nombre con `ls` tras el
install. Se registra como remediación de Phase 5, no como cambio de esta fase.

## Matriz de conflictos/redundancias (inventario REAL, 209; 2026-11-04)

Contra `ls obsidian-workspace/.opencode/skills` = **209 dirs** (2026-11-04: los 208 del `ls` de
2026-10-21 más la skill `tepochcalli-mcp` de Phase 3.5). Veredictos: **CONSERVAR / CONSOLIDAR
(nominando ganadora) / RETIRAR (out-of-domain) / INSTALAR-GAP**. Criterio de dominio: investigación
general — las 14 áreas que pide [docs/UH.md](../docs/UH.md); la fuente **no las numera** (la
numeración por categorías es de Anexo A, no de UH.md). Phase 5 repite el `ls` antes de ejecutar y
cierra el recuento 1:1 por fila.

| Grupo | Skills miembros (inventario real) | Solape/conflicto | Veredicto | Acción Phase 5 |
| --- | --- | --- | --- | --- |
| 1. PDF ×5 | pdf, pdf-anthropic, pdf-processing, pdf-processing-pro, liteparse | cuatro wrappers de la misma conversión; liteparse duplica al conversor del motor (markitdown, spec-rag-engine) | CONSOLIDAR — gana `pdf` (general) + `pdf-processing-pro` (documentos largos) | retirar 3 (pdf-anthropic, liteparse, pdf-processing) |
| 2. Office ×6 | docx, docx-official, pptx, pptx-official, xlsx, xlsx-official | duplicado exacto por familia | CONSOLIDAR — ganan `docx-official`, `pptx-official`, `xlsx-official` | retirar 3 variantes libres. **Frontera TD-22:** esta matriz gobierna el payload **v1** (las 3 ganadoras se quedan); TD-22 gobierna **0.2.0** y elimina las 6 + la entrada `excel` del MCP cuando OfficeCLI entre (ver §Cobertura, nota TD-22) |
| 3. Excel/MCP | excel-analysis, data-transform + entrada `excel` MCP en `opencode.json` (disabled; `uvx` rompe `--offline`) | tres caminos para CSV/Excel | CONSOLIDAR — gana la vía skill (offline-safe) | retirar 1 (`data-transform`); la entrada MCP disabled la elimina TD-22 en 0.2.0 |
| 4. Literatura ×14 | literature, literature-search, literature-review, research-literature, academic-literature-search, paper-lookup, arxiv-search, biorxiv-search, medrxiv-search, pubmed-search, pubmed-database, openalex-database, bgpt-paper-search, paperzilla | buscadores redundantes; las bases bio/med específicas son out-of-domain para el payload genérico | CONSOLIDAR — ganan `paper-lookup` (buscador general, ya citado con la marca de ganadora en `/research`) + `arxiv-search` + `pubmed-search` | retirar **11**: literature, literature-search, literature-review, research-literature, academic-literature-search, biorxiv-search, medrxiv-search, pubmed-database, openalex-database, bgpt-paper-search, paperzilla ⇒ 14 − 11 = **3** supervivientes, que son las 3 nominadas. (`research-lookup` **no** es miembro de esta fila: pertenece a la fila 5) |
| 5. Deep research ×4 | deep-research, deep-research-swarm, tooluniverse-literature-deep-research, research-lookup | variantes de orquestación duplican búsqueda; swarm = coste de tokens contra criterio 4 | CONSOLIDAR — ganan `deep-research` + `research-lookup` | retirar 2 (deep-research-swarm, tooluniverse-literature-deep-research) |
| 6. markitdown skill × markitdown MCP | skill `markitdown` + MCP `markitdown` (retirado del payload en la review Phase 2 y **definitivamente** en Phase 3.5: la conversión es en proceso, D29/ADR-011) | mismo convertidor por dos canales | CONSERVAR la skill con nota: el flujo RAG usa `add_source`/`convert_*` de `tepochcalli-rag`; la skill queda para conversión ad-hoc multi-archivo sin tocar índice. **El MCP standalone ya no existe** | mantener la skill; nota en el `AGENTS.md` del vault |
| 7. Obsidian trío + instructions | obsidian-markdown, obsidian-vault, obsidian-cli | vault×cli se solapan en gestión de notas; el json del workspace lista además `markdown-mermaid-writing` | CONSOLIDAR — ganan `obsidian-markdown` (formato) + `obsidian-cli` (gestión); `obsidian-vault` se fusiona | retirar 1; actualizar `instructions` de `opencode.json` si se retira la skill |
| 8. Estadística ×4 | statistical-analysis, data-stats-analysis, statsmodels, statistical-power | data-stats-analysis duplica el rango de statistical-analysis | CONSOLIDAR — ganan `statistical-analysis` + `statsmodels`; `statistical-power` CONSERVAR (helper) | retirar 1 (data-stats-analysis) |
| 9. Visualización ×5 | matplotlib, seaborn, plotly, data-viz-plots, scientific-visualization | wrappers sobre los mismos backends | CONSOLIDAR — entry point `scientific-visualization` + backends `matplotlib`/`seaborn`/`plotly` | retirar 1 (`data-viz-plots`) |
| 10. Brainstorm/ideas ×6 | brainstorming, scientific-brainstorming, hypothesis-generation, hypogenic, idea-refine, what-if-oracle | ideación redundante | CONSOLIDAR — ganan `scientific-brainstorming` + `hypothesis-generation`; `idea-refine` queda para `/synthesize` | retirar 3 (brainstorming, hypogenic, what-if-oracle) |
| 11. Escritura ×5 | article-writing, scientific-writing, scientific-manuscript, doc-coauthoring, review-writing | scientific-manuscript solapa con scientific-writing (nota Anexo A); article-writing es divulgación/diseminación | CONSOLIDAR — gana `scientific-writing`; CONSERVAR `doc-coauthoring`, `review-writing`, `article-writing` (roles distintos) | retirar 1 (scientific-manuscript) |
| 12. RAG-chat paralelo | open-notebook | NotebookLM-like local: solape frontal con tepochcalli-rag (que ES el producto) | RETIRAR | retirar 1 |
| 13. Creativo/visual suelto | generate-image (+ `infographics`, que se conserva) | generación de imagen creativa, fuera de la metodología | RETIRAR | retirar 1 (`infographics` se CONSERVA: es salida de `/transform`) |
| 14. Núcleo metodológico sin conflicto (en dominio) | 14 nombradas: citation-management, experimental-design, writing-plans, scientific-problem-selection, scientific-critical-thinking, analytical-method-validation, uncertainty-and-units, venue-templates, scientific-slides, paper-2-web, exploratory-data-analysis, networkx, sympy, shap | sin solape material para el pipeline de 9 comandos y 5 agentes | CONSERVAR | mantener en el payload base |
| 15. Resto del inventario (barrido por familia) | **112 dirs no nombrados** en las filas 1-14 y 17 (listado completo en el bloque `<details>`); dentro de la fila se nombran **12 remnants en dominio** — `polars`, `dask`, `vaex`, `zarr-python`, `pyzotero`, `scientific-schematics`, `exa-search`, `perplexity-search`, `patents-search`, `database-lookup`, `wikipedia-search`, `multi-search-engine` — que ya cuentan como CONSERVAR en el cubo explícito, más **7 ejemplos out-of-domain** que cuentan como RETIRAR | **familias medidas en este payload: 0 dirs** para `gis-*`, `marketing-*`, `finance-*`, `sales-*`, `legal-*`, `healthcare-*`, `paid-media-*`, `product-*` y `design-*` (la v1 las citaba como si existieran). El resto barrido es out-of-domain **medido: 102 dirs** (wet-lab, omics, química, física, geo, clínico, RL y meta); con los 7 ejemplos nombrados, el total out-of-domain es **109**, no ≈120 | RETIRAR el barrido out-of-domain (skill pack opcional futuro) y CONSERVAR los 12 remnants en dominio, de los cuales **10 quedan a decisión del FTR (D-P4-10)** | retirar los 102 out-of-domain del barrido + los 7 ejemplos; los 12 remnants se conservan salvo que el FTR apruebe el corte de 10; `wikipedia-search` y `multi-search-engine` **se quedan siempre** (los cita `/research`); `PACK=1` en CI para no romper referencias |
| 16. Gaps UH (sin skill hoy) | jupyter (cuadernos), R (graficación estadística), Graphviz/PlantUML (diagramas), LaTeX de manuscrito (`latex-posters` no cubre manuscrito) | áreas de UH.md sin cubrir | INSTALAR-GAP — **0 instalaciones en v1** (declarado como no instalado) | Phase 5 solo instala si el Anexo A lo decide; mientras, `/transform` los menciona como pendiente de Phase 5 sin inventar nombres |
| 17. `tepochcalli-mcp` (nueva, Phase 3.5 — H4) | `tepochcalli-mcp/SKILL.md` (13 KB, cuerpo en inglés), ausente del `ls` de 2026-10-21 | catálogo único de decisión de las 7 tools de `tepochcalli-rag` + fallback `anydoc`; solapa con la skill `markitdown` en «convertir», pero esta decide **cuándo** usar cada tool | CONSERVAR (nueva; registrada por OM-6 para que la matriz cubra el 100 %) | contarla como entrada del inventario: **209 dirs** (208 + 1) |

* Recuento explícito por fila: las filas 1-13 nombran **58** dirs (21 ganadoras + 8 conservadas + 29
  retiradas); la fila 14 nombra **14** conservadas; la fila 15 nombra **19** a título explícito (7
  ejemplos retirados + 12 remnants en dominio conservados); la fila 17 añade **1** ⇒ **92 nombradas** +
  **5 citadas sin veredicto** = **97 explícitas**; el barrido cubre los **112** restantes (97 + 112 = 209).
  Los 12 remnants se cuentan en el cubo CONSERVAR (34), no en el barrido: por eso el corte de 10 baja
  la base estricta de 60 a 50.
* **Decisión explícita (2026-10-28, se mantiene): 0 skills nuevas para el protocolo de opendraft.**
  Los gates heredados (procedencia, check de claim, gate de compilación) son invariantes de
  workflow — deben correr SIEMPRE — y en OpenCode un cuerpo de comando se ejecuta siempre, mientras
  que una skill es oportunista (el harness decide si la carga): por eso los gates viven en los
  cuerpos de `/research`, `/validate` y `/cite`, jamás en una skill. `citation-management`
  (CONSERVAR, fila 14) cubre la mecánica DOI→BibTeX/dedupe/validación de metadata; el protocolo la
  complementa desde el comando, no la duplica. **Ruta de extracción nominada** (única): si el
  protocolo de procedencia de `/research` no cabe en el cuerpo de ≤35 líneas, extraer UNA skill
  `procedance-verification` (triggers: verificar existencia de una referencia académica; pasos:
  consultar ≥2 bases, clasificar en los 4 estados, serializar `procedencia`; salida: lista
  `{fuente, estado, url_o_doi, fecha_consulta}`) — solo entonces, y anotándola en esta matriz.
  (Origen del protocolo: análisis de federicodeponte/opendraft, 2026-10-28.)

## Cobertura y recuento derivado

Recuento del inventario: 34 + 21 + 5 + 37 + 0 + 112 = **209** (desglose en
§Veredictos). Cobertura explícita: **97** nombradas + **112** en el barrido = 209.

**Payload base según los veredictos de la matriz:**

| Escenario | Cálculo | Total | Objetivo <60 |
| --- | --- | --- | --- |
| A — estricto (solo veredictos) | 34 CONSERVAR + 21 CONSOLIDAR + 5 por defecto | **60** | ✗ falla por 0/1 (60 no es menor que 60) |
| B — A + 6 barridos claramente en dominio | 60 + 6 | 66 | ✗ |
| C — B + 4 borderline | 66 + 4 | 70 | ✗ |
| D — corte recomendado (no aplicado) | A − 10 remnants en dominio sin cita | **50** | ✓ |

El objetivo de menos de 60 skills del payload base (métrica heredada de [docs/WORKFLOW.md](../docs/WORKFLOW.md)
Phase 5 y de TD-7) **no se cumple sin un corte**: el payload derivado de los veredictos es 60 y el
barrido en dominio lo sube hasta 70. **No se borra nada por cuenta propia.**

**Corte recomendado — DECISIÓN DEL OWNER (D-P4-10, pendiente en el FTR):** retirar los 10 remnants
en dominio de la fila 15 que **ningún comando cita** — `polars`, `dask`, `vaex`, `zarr-python`,
`pyzotero`, `scientific-schematics`, `exa-search`, `perplexity-search`, `patents-search`,
`database-lookup`. Con la fila 4 ya corregida (11 retiradas, 3 supervivientes) la base estricta baja
a 50. Se **conservan** `wikipedia-search` y `multi-search-engine` porque la tabla 9×4 de `/research`
las cita.

**Nota TD-22 (OfficeCLI, 0.2.0) — sin contradicción:** esta matriz gobierna el payload **v1**: las 6
skills de ofimática permanecen y se consolidan en `docx-official`/`pptx-official`/`xlsx-official`
(las cita `/transform`). [docs/TECH_DEBT.md](../docs/TECH_DEBT.md) TD-22 gobierna la **feature 0.2.0**:
cuando OfficeCLI entre, esas 6 skills y la entrada `excel` del MCP desaparecen en la misma tarea.
Orden: v1 primero (esta matriz), 0.2.0 después (TD-22). El solape es temporal y deliberado: no se
retiran ahora tres ganadoras que la 0.2.0 volverá a retirar.

## Open Questions

* **D-P4-10 (owner/FTR):** ¿se aprueba retirar los 10 remnants en dominio de la fila 15 que ningún
  comando cita? Sin ese corte el payload base queda en 60 (escenario A) o 70 (C) y el objetivo no se
  cumple; con el corte, 50. No se aplica hasta aprobación explícita.
* **Escenario base del corte:** ¿la métrica se mide sobre A (60) o sobre C (70)? De ello depende que
  el corte deje 50 o 60; el FTR debe fijarlo antes de Phase 5 para que el recuento sea reproducible.
* **4 borderline del barrido:** ¿se aceptan como en dominio (suben el payload a 70) o se tratan como
  out-of-domain? T2a los separó de los 6 claros; la matriz no los reclama.
* **Generador del PDF de muestra:** `gen_ejemplo_pdf.py` no existe en el repo aunque el comentario de
  `EJEMPLO_PDF` lo cite. ¿Se versiona un generador mínimo o se reescribe el comentario sin él?

## References

* [specs/spec-payload-vault.md](spec-payload-vault.md) — blueprint de agentes/comandos/`AGENTS.md`; §Tabla de invocación 9×4 (T3) y puntero a esta matriz
* [specs/spec-agent-workflow.md](spec-agent-workflow.md) — Anexo A: auditoría de 208 skills (2026-10-21) y gaps accionables
* [docs/TECH_DEBT.md](../docs/TECH_DEBT.md) — TD-7 (skills infladas) y TD-22 (OfficeCLI 0.2.0: 6 skills + MCP `excel`)
* [docs/UH.md](../docs/UH.md) — áreas de investigación pedidas (sin numeración en la fuente)
* [docs/WORKFLOW.md](../docs/WORKFLOW.md) — Phase 4 (diseño) y Phase 5 (payload + skills audit)
* [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) — capas y contratos que el payload debe respetar
* `crates/tepochcalli/src/application/installer.rs` (muestras del instalador) y `crates/tepochcalli/assets/ejemplo.pdf`
* [AGENTS.md](../AGENTS.md) — R1/R2 (no reinventar, cero asunción) y umbrales de líneas por fichero
