# ADR-011: Fijar la política de dependencias en dos librerías con un ledger de no-reinvención

* **Status:** Accepted (2026-11-03)
* **Date:** 2026-11-02
* **Decision Makers:** Product Owner (dueño del repo), Arquitecto
* **Consulted:** Backend instalado (`cocoindex==1.0.25`, `markitdown==0.1.9`), tasks/plan.md §2.1-§2.2 y §5.6
* **Informed:** Mantenedores del flow y del MCP `tepochcalli-rag`, autor del wizard (ADR-003/004)
* **Traceability:** docs/UH.md (criterios 1-7), tasks/plan.md D52-D56/D58-D63, specs/spec-rag-engine.md, specs/spec-mcp-server.md, specs/spec-embeddings.md, docs/TECH_DEBT.md TD-16

## 1. Context and Problem Statement

El venv del payload ocupa 2,3 GB y arrastra dos stacks completos que el producto no usa: `docling`
(con `opencv` y `rapidocr`) dejó de ser el extractor del motor, y `markitdown-mcp` solo se usaba por
su librería, con el extra `[all]` metiendo parsers de audio, vídeo y Azure que nunca se invocan.
¿Cómo se fija una regla que impida que cada revisión futura vuelva a engordar el venv, y que además
deje escrito por qué el código propio que rodea al backend no es «duplicación a eliminar»?

## 2. Decision Drivers

* Coste de instalación y de disco para el usuario (`docs/TRD.md` presupuesta 1-2 GB de venv).
* RSS pico del ciclo Δ, que compite con Obsidian en la misma máquina de 8 GB.
* Superficie de ataque: cada parser de formato es un decodificador de entrada no confiable.
* Una sola librería por responsabilidad: un motor RAG y un extractor documento→markdown.
* R1 de AGENTS.md: no reinventar lo que el backend ya da; y a la inversa, no borrar lo que el
  backend no da.
* El índice debe invalidarse cuando cambia **nuestra** lógica de parseo o troceo, no solo el fichero.
* El binario que indexa y el que incrusta la query deben ser el mismo (criterio 5: citas correctas).
* Sin daemons ni watchers (ADR-002).

## 3. Considered Options

* **Option A:** Dos librerías funcionales (`cocoindex[lancedb,sentence-transformers]` +
  `markitdown[...]`), más lo que arrastran, con un **ledger explícito** de lo que se delega y lo que
  se conserva con su razón.
* **Option B:** Mantener `markitdown[all]` por comodidad, aceptando todos los extractores.
* **Option C:** Mantener `docling` como extractor de PDF de calidad (jerarquía de headings).
* **Option D:** Escribir un extractor propio sobre `pypdf`/`python-docx` para no depender de
  `markitdown`.

## 4. Decision Outcome

**Chosen option:** A. Delega todo lo que el backend hace bien (parseo, chunking, memoización,
escritura del índice) y conserva —documentado— solo lo que el backend no ofrece; cualquier
dependencia nueva exige un ADR nuevo.

### 4.1 Confirmation

* `uv tree` (desde `.tepochcalli/`) **no muestra** `docling`, `docling-ibm-models`, `torchvision` ni
  `markitdown-mcp`; el comando falla el gate si aparecen.
* `uv run python -c "import markitdown, importlib.metadata as m; print(m.version('markitdown'))"`
  imprime `0.1.9` con el lock nuevo, sin red.
* `du -sh venv/` ≤ **1,95 GB** y `uv lock --check` + `uv sync --frozen` en verde.
* `grep -rn "litellm\." mcp/ flow/` no devuelve nada; `pyproject.toml` declara `litellm` **solo** en
  `[tool.uv] constraint-dependencies`.
* Test de change detection: editar `parsers.extract_text`, reejecutar el refresh y comprobar que el
  fichero se re-indexa (hoy no lo hace: el memo queda obsoleto en silencio).
* Test del embedder único: `write` y `read` resuelven **el mismo path** de modelo (`Path.resolve()`).
* Revisión de PR: toda dependencia nueva sin ADR-011 rectificado ⇒ cambio rechazado.

### 4.2 La regla de oro (D52)

Dos librerías **funcionales** y nada más por cuenta propia:

| Librería | Rol | Lo que arrastra |
| --- | --- | --- |
| `cocoindex[lancedb,sentence-transformers]==1.0.25` | El motor: walk, memo, chunking, escritura del índice | `torch` (CPU pineado), `lancedb`, `pyarrow`, `sentence-transformers` |
| `markitdown[docx,pptx,xlsx,xls,pdf]==0.1.9` | El extractor documento→markdown | `mammoth`+`lxml`, `python-pptx`, `openpyxl`, `xlrd`, `pdfminer.six`+`pdfplumber`, `pandas`+`numpy` (los dos últimos, vía los extras `xlsx`/`xls`; verificado en el `METADATA` instalado) |

Más las dos que son contrato o plataforma, no funcionalidad de producto: `mcp==2.3.0` (el wire) y
`torch==2.14.1` (pin del índice CPU; sin declaración directa uv arrastra el stack CUDA de ~5 GB).
Cualquier otra dependencia exige **ADR nuevo** que la justifique; la regla no se relaja «porque es
pequeña».

### 4.3 Extractor y formatos (D53, D54, D55)

* **D53 — `docling` fuera:** el motor ya parsea con `markitdown` (D48). Ahorro **≈225 MB**
  (`opencv` 153, `docling_parse` 33, `rapidocr` 32) y **≈2,0 GB de RSS pico** en el ciclo Δ.
  `torchvision` sale con él (solo lo traía `docling-ibm-models`, −7 MB).
* **D55 — `markitdown-mcp` fuera:** solo usábamos la **librería**; el server aportaba ~2 MB más
  `starlette`/`uvicorn` y un segundo proceso MCP que el payload ya no registra. Extras
  **granulares** `[docx,pptx,xlsx,xls,pdf]` en vez de `[all]`: **−125 MB** (Azure 63,
  `speech_recognition` 43, YouTube 3, `pydub`/`olefile`).
* **D54 — el PDF pierde la jerarquía de headings:** `markitdown` extrae texto plano, así que
  `heading` queda **nulo** en las citas de PDF. Es un coste **afirmado y medido en el FTR**, no un
  efecto colateral: el criterio 5 se apoya en `source_path`, `doc_kind` y los offsets de carácter
  (`offsets_ref="extract"`), no en el heading. Recuperar la jerarquía (docling u otro extractor)
  exige revertir este ADR con uno nuevo que pague los 225 MB y los 2,0 GB de RSS.

### 4.4 Change detection sobre nuestra propia lógica (D58, D60)

* **D58:** `extract_text`, `chunk_document` y los helpers de cita se decoran con `@coco.fn` (sin
  `memo=True`). Sin el decorador, un helper es **invisible** al fingerprint: cambiar el parser **no
  invalida** el memo del fichero y el índice queda obsoleto en silencio — un bug real, no una
  precaución estética. Con el decorador, la lógica entra en la identidad del memo.
* **D60:** `@coco.fn.as_async` en lugar de saltos a hilo manuales, y **batching** de embeddings según
  la op. El event loop del server no se bloquea durante el refresh, y el batching es del backend, no
  código nuestro.

### 4.5 Un solo embedder (D59, D61)

* **D59:** write y read usan **la misma** implementación,
  `cocoindex.ops.sentence_transformers.SentenceTransformerEmbedder`, y el modelo se referencia por
  **ruta local materializada** `<models>/<slug>@<sha>/`. El bug que cierra: hoy write usa la op sin
  `revision` (⇒ «main») y read usa `SentenceTransformer(revision=MODEL_REVISION)`; si el upstream
  mueve `main`, el binario que indexa y el que incrusta la query **no son el mismo fichero** y el
  espacio vectorial se desalinea sin error visible. La op acepta «name **or path**» ⇒ la ruta local
  es el pin, sin inventar API. Snapshot ausente ⇒ `E_MODEL_INVALID` con guía; **nunca** descarga
  silenciosa de otro modelo.
* **D61:** **sin** memo de embeddings por chunk. El coste está cuantificado: ~6 KB/vector ⇒ ~600 MB
  por 100k chunks para cubrir reruns raros, cuando el memo por fichero ya cubre el caso estable. Se
  re-embebe el chunk cuando cambia el fichero; es más barato que mantener una caché coherente.

### 4.6 LiteLLM como feature, no como dependencia directa (D56)

`litellm` sale de `dependencies`; la op `cocoindex.ops.litellm.LiteLLMEmbedder` lo aporta vía
`cocoindex[litellm]` y nuestro código deja de llamarlo. El extra de cocoindex declara
`litellm>=1.81.0` **sin techo**, así que quitar la declaración a secas dejaría a uv resolver la
serie comprometida: el pin de seguridad se expresa como restricción de resolución, no como
dependencia —`[tool.uv] constraint-dependencies = ["litellm>=1.106.2,<1.107.0"]`
(GHSA-92x9-889m-jgmw)— que alcanza a **toda** la gráfica. Los ~129 MB siguen (el paquete lo necesita
la op); lo que desaparece es nuestra declaración y nuestro código. La op aporta además reintentos con
backoff (1 s, ×2, tope 30 s) dentro de una ventana de `timeout` de 10 min ⇒ **cierra TD-16**.

### 4.7 Ledger de no-reinvención (D63)

Ninguna revisión futura puede «optimizar» una de estas piezas hacia el backend sin leer esta tabla:

| Conservamos | Por qué NO se delega |
| --- | --- |
| El lector ANN + FTS + fusión RRF (`adapters/lancedb_reader.py`) | El conector de cocoindex es **solo de escritura**: no hay API de búsqueda. Sin lector propio no existe `search`. |
| `heading_before` y los metadatos de cita (`citation.py`) | CocoIndex no produce `heading`: entrega texto y offsets del chunk, no la estructura del documento. |
| Los skips tipados (`SkippedSource`, `source.py`) | El conector se traga rotos e ilegibles **en silencio**; sin motivo tipado el usuario no sabe qué quedó fuera. |
| `paths.py` (frontera D16/B′) | Es la única puerta de `file:` y de las raíces; el conector no valida containment, tipo ni extensión. |
| `write_atomic` (escritura idempotente del conversor) | `declare_file` es *target state* del índice, no una escritura atómica con idempotencia en disco. |
| El estimador de tokens (`budget.py`, `chars/4 + 25`, techo 1600) | No hay equivalente en el backend: el presupuesto es contrato de wire (criterio 4). |
| La ausencia de watchers | ADR-002 los prohíbe: el live-watch de `localfs` abriría un proceso residente. |

**Método:** cada fila se verificó leyendo el backend **instalado** (`cocoindex==1.0.25`,
`markitdown==0.1.9`), no de memoria ni de la documentación de PyPI. Si una versión futura gana la
capacidad (p. ej. API de búsqueda en el conector), se abre ADR que la adopte y **borre** nuestra
pieza; hasta entonces, la fila es la razón de ser del código.

## 5. Pros and Cons of the Options

### Option A — Dos librerías + ledger (elegida)

* ✅ **Pros:** venv 2,3 GB → **≈1,95 GB** (−350 MB, 624 → ~560 paquetes) y −2,0 GB de RSS pico;
  una sola librería por responsabilidad; la superficie de ataque se reduce a los formatos que el
  producto ofrece; el ledger impide que el código propio se borre por error y que se añada de más.
* ⚠️ **Cons:** el ledger hay que mantenerlo; la política es estrecha y a veces habrá que decir «no»
  a una librería cómoda; el ahorro (350 MB) es real pero modesto frente a los 1,95 GB que quedan.
* ⚖️ **Neutral:** el extractor pasa a ser una dependencia de terceros con salida versionada.

### Option B — `markitdown[all]`

* ✅ **Pros:** cero decisiones: cualquier formato entra sin tocar el pyproject.
* ⚠️ **Cons:** **−125 MB** de extractores que nunca se invocan (Azure 63, `speech_recognition` 43,
  YouTube 3, `pydub`/`olefile`), y cada uno es un decodificador de entrada no confiable sin uso:
  superficie de ataque pura. Además contradice la regla de que el catálogo de formatos es dato
  curado.
* ⚖️ **Neutral:** añadir un formato nuevo sería gratis, pero también invisible en revisión.

### Option C — Mantener `docling`

* ✅ **Pros:** jerarquía de headings en PDF y mejor extracción de tablas.
* ⚠️ **Cons:** **≈225 MB** (opencv 153, docling_parse 33, rapidocr 32) y **≈2,0 GB de RSS pico** en
  el Δ para una jerarquía que el criterio 5 **no exige**; dos caminos de parseo que producen texto
  distinto para el mismo fichero (el índice y el `.md` del conversor dejarían de coincidir).
* ⚖️ **Neutral:** el coste se mide y se acepta (D54); revertir exige ADR.

### Option D — Extractor propio (`pypdf`/`python-docx`)

* ✅ **Pros:** superficie mínima y control total del texto extraído.
* ⚠️ **Cons:** reinventar la rueda (R1): perderíamos los cinco formatos que `markitdown` ya cubre y
  el mantenimiento de cada parser sería nuestro, para siempre, en cada versión de cada formato.
* ⚖️ **Neutral:** ninguna ventaja que A no tenga ya.

## 6. Consequences

* ✅ **Positives:** instalación más ligera y rápida; menos RSS compitiendo con Obsidian; un solo
  camino de parseo ⇒ el texto indexado y el `.md` convertido coinciden; TD-16 cerrado; el bug de
  desalineación de embeddings desaparece por construcción.
* ⚠️ **Negatives / Risks:** **el PDF pierde los headings** (`heading` nulo; coste afirmado en el
  FTR); **un formato nuevo exige un ADR** (no hay «añado el extra y ya»); el extractor es de
  terceros y **puede cambiar su salida entre versiones menores** (OM-3: `MarkItDown().convert` y
  `result.markdown` se anclan contra la fuente instalada, nunca contra memoria); sin OCR (fuera de
  alcance v1) y sin audio/vídeo, que ahora ni siquiera están instalados.
* ⚖️ **Neutral:** el catálogo de formatos pasa a ser un dato curado (`list_formats`), no la lista de
  extras del lock.

## 7. Related Decisions

* **ADR-001** — el motor es cocoindex; este ADR fija qué se le delega y qué no (D63).
* **ADR-002** — sin daemon: de ahí la fila de watchers del ledger.
* **ADR-004** — uv + venv + lockfile: el vehículo donde se aplica la dieta y el `constraint-dependencies`.
* **ADR-006 / ADR-007 / ADR-008** — el modelo de embeddings y su selección; D59 los materializa como
  ruta local estable, y la provenance (`<slug>@<sha>`) es la que ya declaraba la config.
* **ADR-009** (conversor markitdown en proceso) y **ADR-010** (índice multi-raíz y cita
  vault-relativa) — redactados en el mismo hito; comparten con este ADR la regla de una sola librería
  de extracción y el contrato de cita.

## 8. Compliance and Review

* **Success metrics:** venv ≤ 1,95 GB medido; 0 dependencias fuera de la regla sin ADR; Δ p95 < 30 s
  con el RSS pico nuevo publicado; 0 incidentes de desalineación de embeddings; TD-16 cerrada.
* **Next review date:** 2027-05-02
* **Revisit triggers:** (a) el criterio 5 pasa a exigir headings en PDF; (b) un formato que el
  producto necesite no está cubierto por los extras granulares; (c) `cocoindex` gana API de búsqueda
  o de extracción que vacíe una fila del ledger; (d) el ahorro real medido en T13 se aleja del
  presupuesto de 1,95 GB.

---
*Basado en [MADR v4.0](https://adr.github.io/madr/) y el formato de Nygard.*
