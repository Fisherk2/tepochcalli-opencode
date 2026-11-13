# TD-27 — el impacto real de la cita de PDF sin `heading` (D54) · Phase 6 · T10

> **Fecha:** 2026-11-13 · **Fase:** Phase 6 — E2E Acceptance · **Calpulli:** T10
> **Estado:** **medido** y **firmado por el dueño (2026-11-13): se reafirma D54**.
> **Fuente de verdad:** [ADR-011](../specs/adr/adr-011-politica-dependencias-dos-librerias.md) §4.3
> (D54) · [spec-rag-engine](../specs/spec-rag-engine.md) §Ruta de documentos ·
> [TECH_DEBT](../TECH_DEBT.md) TD-27 · [plan](../tasks/plan.md) §Task T10 (D-P6-5).
> **Jerarquía de evidencia (D8):** `medido > estimado > declarado`. Lo medido lleva su comando;
> lo que no se pudo medir se escribe como no medido.
> **Evidencia archivada:** [pdf-heading.json](pdf-heading.json) (11 registros: 9 documentos,
> 1 muestra del corpus, 1 consulta).

## 1. Resultado en una línea

Sobre **8 PDF reales** (1 a 1 313 páginas, **6 303 chunks**) el **100 % de las citas de PDF va sin
`heading`** (0/6 303) — y si la política de D54 no lo forzara, **7 de esos 8 PDF seguirían sin
él**: markitdown no emite ni una línea ATX en ellos. En el de 1 313 páginas hay **2 líneas con
forma de heading y las dos son basura** (`"   !#` y `"`); aceptarlas daría heading falso al
**79,0 %** del documento. **El `heading` nulo del PDF no lo causa D54: lo causa el extractor.**

## 2. Qué se puede medir aquí, y por qué son dos capas

D54 mezcla dos cosas en una frase («markitdown extrae texto plano, así que `heading` queda nulo»).
Se miden por separado porque solo la primera está en nuestras manos:

| Capa | Dónde vive | Qué se mide | Resultado |
| --- | --- | --- | --- |
| **Política** (código nuestro) | `parsers._to_document_chunk`: `heading_before(...) if kind in SOURCE_OFFSETS_DOC_KINDS else None` | `chunks_with_heading` | **0/6 303** en PDF (**0/6 307** contando el `.docx` de §6) — es `1,0` **por construcción**, no por el corpus |
| **Extracción** (markitdown 0.1.9) | `MarkItDown().convert(path).markdown` | `headings_in_extract` (con `citation.HeadingScanner`, el escáner del pipeline) y `chunks_with_heading_if_policy_allowed` | **3 373/6 303 chunks de PDF sin una sola línea ATX**; los 2 930 restantes (CLRS), 2 artefactos |

La cifra que **discrimina** es la segunda: dice cuánto se recuperaría si la política dejara pasar
lo que el extractor entrega. La primera, sola, sería un 100 % tautológico.

## 3. El corpus de T1 no permite medir esto (y ese es el hallazgo)

Los 1 000 PDF del corpus de [T1](corpus.md) son **stubs de 1 página**: 707 B, **54 caracteres**,
7 líneas, 1 chunk. Muestra de **n = 20** (los primeros por orden lexicográfico):

| Medición | Valor |
| --- | --- |
| PDFs / chunks | 20 / 20 (1 chunk por PDF) |
| `chars` por PDF | **54** (7 líneas de texto suelto: «Informe PDF 00000 / Oficina / Rincon…») |
| Líneas ATX en el extracto | **0** |
| Citas de PDF sin `heading` | **20/20 = 100 %** — **por diseño del fixture**, no por D54 |

Un PDF de una página de 54 caracteres no tiene secciones que perder: publicar ese 100 % como
«impacto» sería exactamente el rework que el plan prohíbe. **Se mide sobre los PDF reales** que el
repo ya tiene (`tests/fixtures/pdf/`, los 5 libros de T2 + 3 fixtures), que sí tienen estructura.

## 4. Medición sobre PDFs reales (n = 8 documentos, 6 303 chunks)

| PDF (págs) | Caracteres | Chunks | Líneas ATX en el extracto | `heading` hoy | `heading` si la política lo permitiera |
| --- | --- | --- | --- | --- | --- |
| `16-pages.pdf` (Brooks, *No Silver Bullet*) | 53 568 | 42 | 0 | 0 | **0** |
| `335-pages.pdf` (SWEBOK v3) | 1 000 523 | 852 | 0 | 0 | **0** |
| `444-pages.pdf` (libro EPUB) | 527 068 | 421 | 0 | 0 | **0** |
| `952-pages.pdf` (Code Complete) | 2 278 941 | 2 053 | 0 | 0 | **0** |
| `1313-pages.pdf` (CLRS) | 3 344 734 | 2 930 | **2 (artefactos)** | 0 | **2 315 (79,0 %), todos con el mismo valor basura** |
| `articulo_t7.pdf` · `articulo_dorado.pdf` | 1 718 c/u | 2 c/u | 0 | 0 | **0** |
| `tablas_t7.pdf` | 991 | 1 | 0 | 0 | **0** |
| **Total** | — | **6 303** | **2** | **0 / 6 303** | **2 315 / 6 303 (36,7 %), 0 aprovechables** |

Los `chars` coinciden con los publicados en [documents.md](documents.md) §3 para los mismos libros
(53 568 · 1 000 523 · 527 068 · 2 278 941 · 3 344 734): es **la misma extracción**, no una
imitación.

**Lectura del caso 1 313 páginas.** Las dos líneas que el escáner reconoce nacen en `char_start`
693 939 (`"   !#`) y 1 350 314 (`"`); el escáner devuelve el último heading previo, así que el
artefacto se propaga a **2 315 chunks** (79 % del documento) y luego cambia de basura a otra.
No es una jerarquía perdida: es **ruido de extracción** que D54 evita. Un heading inventado es una
cita falsa (ADR-011 §4.3).

**Lo que sobrevive en esos PDF, y sí es usable:** los títulos de sección están **en el texto
plano** aunque no sean campo. SWEBOK: 1 269 líneas con forma de sección numerada
(«1.1. Definition of a Software Requirement 1-1»); Code Complete: 1 583; CLRS: 2 367. El agente
puede citarlas **citando el texto**, no por un campo estructurado.

**Contraste de la explicación alternativa (el escáner solo entiende ATX).** `HeadingScanner`
reconoce ATX (`#`) y **no** setext (`===`/`---` bajo una línea), limitación documentada en
`citation.py`. Para que la ausencia de headings no sea sesgo del escáner, se cuenta también el
setext: **0 subrayados setext en los 8 PDF** (y 0 en el `.docx`). markitdown no entrega jerarquía
en PDF **en ninguna de las dos sintaxis**.

## 5. Query cuyo único material es un PDF: los campos que le quedan al agente

Vault temporal con **un solo fichero** (`16-pages.pdf`, 42 chunks), índice real, `search(top_k=5)`
por el camino del server (`LanceDBChunkReader`, híbrido ANN+FTS+RRF):

> `¿cuál es la diferencia entre la esencia y el accidente de la ingeniería del software?`
> — refresh `scanned 1, indexed 1`; **5/5 citas del mismo `source_path`, 0 con `heading`,
> 5/5 con identidad F1 verificada**.

| Score | `heading` | `offsets_ref` | `char_start`–`char_end` | Texto citado (inicio) |
| --- | --- | --- | --- | --- |
| 0,969 | `null` | `extract` | 0–1 446 | «No Silver Bullet —Essence and Accident in Software Engineering…» |
| 0,500 | `null` | `extract` | 5 055–6 303 | «Second, to see what rate of progress we can expect…» |
| 0,492 | `null` | `extract` | 45 178–46 670 | «F. Brooks: No Silver Bullet—Essence and accident…» |
| 0,492 | `null` | `extract` | 14 020–15 376 | «**Past Breakthroughs Solved Accidental Difficulties** If we exam…» |
| 0,484 | `null` | `extract` | 23 706–25 089 | «3 Booch, G., “Object-oriented design,”…» |

**¿Puede citar con precisión?** Sí para el criterio 5 (**el texto exacto se reproduce**, F1 5/5,
y `text` se persiste en la fila) — **no** para localizar la sección en el visor del PDF. Los campos
reales del wire (`CitedChunk`, ADR-005) son:

`text` · `source_path` · `heading` (**`null`**) · `char_start` · `char_end` · `score` ·
`offsets_ref` (**`"extract"`**). **`doc_kind` no viaja** (la extensión de `source_path` lo delata;
`offsets_ref` es el campo aditivo que sí cruza).

Lo que **falta** en ese caso, y ninguna política de `heading` arregla: **número de página**. Los
offsets son del *texto extraído*, no del binario; `source_path` + offsets no son navegables en un
lector de PDF. Lo único que ancla la cita a una sección es **el propio texto citado** — en la 4ª
fila, el título de sección «Past Breakthroughs Solved Accidental Difficulties» viaja *dentro* del
chunk. Con 5 citas del mismo fichero, el agente las distingue por `char_start` y por el texto, no
por sección. (En **2 de los 8** documentos el extracto **sí** conserva separadores de página —
`\x0c`: 15 en `16-pages`, 442 en `444-pages` —, así que derivar página sería posible sin cambiar
de extractor; no está en el esquema ni en el contrato, y no se mide ni se propone aquí.)

## 6. Hallazgo colateral (no estaba en el encargo, no firmado): `.docx` sí trae headings

La política de D54 no es exclusiva del PDF: `else None` cubre **todos** los `doc_kind` extraídos.
Y ahí el extractor **sí** entrega jerarquía:

| Documento | Chunks | Líneas ATX en el extracto | `heading` hoy | `heading` si la política lo permitiera |
| --- | --- | --- | --- | --- |
| `.docx` con `Heading1`/`Heading2` (`informe-heading.docx`, generado con OOXML a mano) | 4 | **2** («Informe Trimestral», «Resultados») | **0** | **3/4 (75 %)** |

Es decir: para `.docx` (y presumiblemente `.pptx`) D54 **sí** descarta estructura real, y
recuperarla **no cuesta Docling**: sería quitar el gate para los `doc_kind` cuyo extracto *es*
markdown. **No se propone aquí como opción firmable** por dos motivos medidos: (a) cambiaría una
decisión `Accepted` ⇒ ADR nuevo igualmente; (b) el caso CLRS demuestra que aplicar el escáner sin
gate puede envenenar un documento entero, así que el cambio exige su propia medición por formato.
Se deja como **hallazgo para decisión separada** del dueño.

## 7. Las dos opciones, con su coste

### (a) Reafirmar D54 — `heading` nulo en documentos extraídos

* **Qué se apoya en el dato:** en PDF, quitar la política **no recupera nada** (0 de 6 303 chunks;
  2 315 serían citas falsas en un solo libro) y el criterio 5 se cumple con `source_path` +
  `offsets_ref="extract"` + offsets + `text` persistido (F1 5/5, [citations.md](citations.md) 6/6).
* **Coste de revertir (documentado, no pagado):** reintroducir Docling = **≈225 MB** de
  dependencias (`opencv` 153, `docling_parse` 33, `rapidocr` 32) y **≈2,0 GB de RSS pico** en el
  ciclo Δ — cifras de [ADR-011](../specs/adr/adr-011-politica-dependencias-dos-librerias.md) §4.3,
  **no medidas en T10** — más un re-index completo (índice en frío del corpus 11k: **543 645 ms**
  en btrfs / **944 019 ms** en NTFS, [search-scale.md](search-scale.md) y
  [scale-ratio.md](scale-ratio.md)) y la re-validación de los benchmarks de la fase.
* **Qué queda escrito:** nota de cierre de TD-27 con la cifra + la limitación en
  `spec-mcp-server` §citas. Sin cambios de código.

### (b) Revertir ADR-011 — recuperar la jerarquía de headings en PDF

* **Qué exige:** **ADR-013** que reemplace §4.3 de ADR-011 + re-sincronizar
  `spec-mcp-server`, `spec-rag-engine`, `spec-markitdown` y `spec-vault-structure` + volver a
  abrir la regla de dos librerías (ADR-011 §4.2) + medir el coste de Docling en **este** host
  (no está instalado: no se puede medir aquí).
* **Qué compraría, según este dato:** nada demostrado. Lo medido es que **markitdown** no entrega
  la jerarquía; que Docling la entregue bien en estos 5 libros **no se ha medido** y no se afirma.

### Recomendación (firmada 2026-11-13)

**(a) reafirmar D54**, por una razón que el dato sostiene y no una opinión: la pérdida de `heading`
en PDF es **del extractor, no de la política** — quitarla no gana ni un heading y sí puede meter
citas falsas. Pago de 225 MB y 2,0 GB de RSS por una jerarquía que el criterio 5 no exige, sin
medición previa de que Docling la produzca mejor en estos libros, es un coste sin contrapartida
medida. Y por separado, decidir el caso **`.docx`/`.pptx`** (§6), donde el extractor sí entrega
estructura y no hace falta Docling.

**Firmado por el dueño (2026-11-13): se reafirma D54.** Este documento **no** toca el payload
(D-P6-1), **no** toca el contrato MCP y **no** escribe ADR-013: prepara la decisión, y el cierre
de TD-27 queda registrado en [TECH_DEBT](../TECH_DEBT.md).

## 8. Cómo reproducirlo

Herramienta: `tests/benchmarks/bench_pdf_heading.py` (nueva receta `just python-bench-pdf-heading`).
Cada fase es una llamada en primer plano y archiva su JSON en `/tmp/opencode/phase6-t10`:

```bash
# 1) los 5 libros y los 3 PDF de fixture (uno o dos por llamada: el de 1 313 págs ~130 s)
just python-bench-pdf-heading --phase extract \
  --pdf "$PWD/tests/fixtures/pdf/16-pages.pdf" --pdf "$PWD/tests/fixtures/pdf/335-pages.pdf"
# 2) el corpus de T1 (por qué no sirve: stubs de 54 caracteres)
just python-bench-pdf-heading --phase corpus-sample --n 20
# 3) query cuyo único material es un PDF (indexa un vault de 1 fichero y busca top_k=5)
just python-bench-pdf-heading --phase query --pdf "$PWD/tests/fixtures/pdf/16-pages.pdf" \
  --query '"¿cuál es la diferencia entre la esencia y el accidente de la ingeniería del software?"'
# 4) el hallazgo del .docx (genera el fixture con OOXML a mano, sin dependencias)
just python-bench-pdf-heading --phase extract --docx
# 5) unir todo → JSON archivado
just python-bench-pdf-heading --phase report
```

Método publicado en cada registro: extractor `markitdown==0.1.9` (`MarkItDown().convert`),
chunker `parsers.chunk_document` (1536/192 bytes, D11), escáner `citation.HeadingScanner` (el del
pipeline, no una regex propia), percentiles no aplican (conteos exactos). Host: 12 vCPU, CPython
3.12.14, lecturas desde `/mnt/HDDFish` (fuseblk/NTFS-3G). **Los conteos son deterministas**; los
`extract_ms` de este JSON **no** son la cifra de T2 (esa se mide en btrfs con n=3, ver
[documents.md](documents.md)) y no se usan aquí como rendimiento.

## 9. Lo que este calpulli NO hace

* **No firma** por sí mismo la decisión (cambia una decisión `Accepted`: es del dueño); la firma
  (2026-11-13) y el cierre de TD-27 viven en `docs/TECH_DEBT.md`.
* **No** escribe ADR-013 ni toca `specs/adr/`; **no** toca `specs/` (la re-sincronización de las 4
  specs es de la vía (b), y solo si se firma).
* **No** mide Docling (no está instalado) ni afirma que Docling produzca buenos headings.
* **No** reescribe el payload (D-P6-1) ni el contrato MCP (ADR-005).
* **No** propone código: la vía (a) no cambia una línea; el caso `.docx` queda como hallazgo
  separado con su propio gate de medición.
