# Criterio 7: matriz de conversión multi-formato (Phase 6 · T8)

> **Fecha:** 2026-11-13 · **Fase:** Phase 6 — E2E Acceptance · **Calpulli:** T8
> **Estado:** entregado; **sin commit** (lo integra el orquestador).
> **Fuente de verdad:** `docs/UH.md` línea 61 (inmutable) — «Pueda procesar distintos formatos de
> texto, si no, utilizar el convertidor Markdown para que pueda manipularse adecuadamente» ·
> `tasks/plan.md` §Task T8 · `specs/spec-rag-engine.md` §Fuentes · `specs/spec-markitdown.md`
> §Catálogo y §Cadena de fallback · ADR-009 (D28/D36) y ADR-010 (D41/D49).
> **Jerarquía de evidencia (D8):** lo de §3 es **`medido`** (wire real por stdio + índice real);
> las celdas GAP de §4 son `medido` = el mensaje que el wire devuelve; la celda `url` de §5 es
> **`declarado`** (no ejecutada) y se dice así.
> **Evidencia archivada:** [format-matrix.json](format-matrix.json) (celdas, GAP, refresh y las dos
> tablas tal como las imprime el test).

## 1. Resultado en una línea

**8 de las 9 celdas PASS ejecutadas, 1 celda `url` declarada GAP por método (sin egress en la
suite) y 3 formatos no soportados declarados GAP con su mensaje real** — ningún PASS simulado.

## 2. Método

Un test **parametrizado** (`tests/e2e/test_format_matrix.py`, 16 tests) construye un vault temporal
y lo mide en un solo servidor `tepochcalli-rag` por stdio:

| Paso | Qué hace | Qué prueba |
| --- | --- | --- |
| Índice | `00-resources/` con `nota.md`, `prosa.txt`, `articulo.pdf`, `informe.docx`, `diapositivas.pptx`, `hoja.xlsx`, `legado.xls` + `escaneado.pdf` (1 pasada de indexación en subproceso) | las 7 celdas de índice: `doc_kind` de la fila y `source_path`/`offsets_ref`/`heading` del wire |
| Conversión | `convert_document` sobre el `.docx` indexado y sobre `staging/pagina.html` | el resumen de 5 claves (ADR-009): el cuerpo no viaja |
| D49 | `search` tras convertir, **antes** de refrescar | el `.md` recién escrito no es cita: la cita del `.docx` sigue siendo el original |
| Refresh | `index_refresh()` por el wire (10 escaneados → 2 indexados, 8 memoizados) | el artefacto `.md` de `html` pasa a ser citable |
| GAP | `convert_document` sobre `.doc`, `.ppt` y `escaneado.pdf`; `add_source` con `http://127.0.0.1` | el mensaje accionable real, no uno inventado |

Los fixtures se generan en el test con **cero dependencias nuevas** (R1): `.docx` con `zipfile` de la
stdlib, `.xlsx` con `openpyxl` y `.pptx` con `python-pptx` (extras YA instalados de markitdown), el
PDF copiado del fixture de T3 y el `.xls` como **BIFF2 mínimo escrito con `struct`** — no hay
generador de `.xls` en la stdlib ni `xlwt` instalado, así que la celda `.xls` se ejecuta de verdad
en vez de declararse best-effort (lo que hacía `test_mcp_list_formats`).

**Sin latencia** (regla anti-flake): el test afirma formato y cita, nunca tiempo.

## 3. La matriz (salida literal del test)

| formato | entrada | resultado | doc_kind | offsets_ref | indexable | source_path | nota |
| --- | --- | --- | --- | --- | --- | --- | --- |
| md | índice | PASS | md | source | sí | 00-resources/nota.md | — |
| txt | índice | PASS | txt | source | sí | 00-resources/prosa.txt | — |
| pdf | índice | PASS | pdf | extract | sí | 00-resources/articulo.pdf | heading nulo (D54) |
| docx | índice | PASS | docx | extract | sí | 00-resources/informe.docx | heading nulo pese al `#` del original (D54) |
| pptx | índice | PASS | pptx | extract | sí | 00-resources/diapositivas.pptx | heading nulo (D54) |
| xlsx | índice | PASS | xlsx | extract | sí | 00-resources/hoja.xlsx | heading nulo (D54) |
| xls | índice | PASS | xls | extract | sí | 00-resources/legado.xls | BIFF2 mínimo generado con `struct` (sin `xlwt`) |
| html | conversor | PASS | md | source | sí, tras index_refresh | 00-resources/pagina.md | el `.html` original no está en la whitelist: nunca es citable |
| url | conversor | GAP | — | — | no verificado | — | sin egress (`nonet`) y el guard SSRF rechaza loopback; exige host con red o allowlist (ADR) |

**Lectura de las columnas.** `entrada` = borde por el que el formato llega: la whitelist del índice
(8 extensiones, `spec-rag-engine` §Fuentes) o las 3 tools del conversor. `doc_kind` y `offsets_ref`
salen de `citation.DocKind`/`offsets_ref_for` al leer la fila y el wire — no de memoria.
`source_path` es **la ruta citable** que devuelve `search`, no `written_to`.

## 4. `html` y `url`: `written_to` no es una cita

La confusión que este calpulli cierra: el conversor **escribe un `.md`** y devuelve `written_to`,
pero **no lo indexa** (D49, `spec-markitdown` §Non-Goals). Lo citable es lo que `search` devuelve:

| Caso | `written_to` | `source_path` citable | Cuándo |
| --- | --- | --- | --- |
| `docx` (formato del índice) | `00-resources/informe.md` | **`00-resources/informe.docx`** (`offsets_ref="extract"`) | siempre: se indexan los originales |
| `html` (fuera de la whitelist) | `00-resources/pagina.md` | **`00-resources/pagina.md`** (`offsets_ref="source"`) | **solo tras `index_refresh`** |
| `url` (GAP) | — | — (no ejecutado) | exige red: ver §5 |

Ejecutado y afirmado en el test: antes del refresh el artefacto **no aparece** en el top-5 de su
propia marca (`test_html_is_citable_only_after_refresh_and_never_as_html`) y la marca del `.docx`
devuelve el **original** con `offsets_ref="extract"`
(`test_the_original_is_the_citation_and_the_converted_md_is_not`). Ninguna ruta `.html` aparece
jamás como `source_path`, porque la whitelist no la admite.

## 5. La celda `url`: GAP con método declarado, no PASS

El camino `http(s)` existe (`add_source`, con fetch propio y SSRF por hop — W-02), pero **no es
ejecutable en esta suite**:

* el host de tests corre con el canario `nonet` (`tests/support/nonet`): cualquier `connect AF_INET`
  lanza `OSError` en el hijo del server — cero egress;
* `paths._deny_internal_host` rechaza `localhost`, `127.0.0.0/8`, `10/8`, `172.16/12`, `192.168/16`
  y link-local **por diseño** (SSRF), así que un servidor HTTP local **no** sirve el caso feliz: el
  test positivo con loopback se retiró en Phase 2 (`test_mcp_add_source.py`).

Lo ejecutado, y único afirmado: `add_source("http://127.0.0.1:9/pag.html")` ⇒ `VALIDATION_ERROR`
(«red interna») **antes** de conectar y sin escribir nada. Para convertir la celda en PASS hace
falta un host con red real o un allowlist de loopback — eso sería un cambio de política de
seguridad (ADR), no un ajuste de test. El camino equivalente sin red (`file:`, mismo markitdown en
proceso) queda cubierto por la celda `html`.

## 6. GAP declarados (no soportados) — mensajes literales del wire

| formato | resultado | mensaje ejecutado | Acción para el usuario |
| --- | --- | --- | --- |
| `.doc` | GAP | `VALIDATION_ERROR` — «formato no soportado: '.doc'» + catálogo en `details.formats` | guardar como `.docx` (o pegar el texto en un `.md`) |
| `.ppt` | GAP | `VALIDATION_ERROR` — «formato no soportado: '.ppt'» + catálogo en `details.formats` | guardar como `.pptx` (o pegar el texto en un `.md`) |
| pdf escaneado | GAP | `SOURCE_UNREACHABLE` — «Sin OCR: el documento no tiene capa de texto; guárdalo como `.md` a mano o pásalo por un OCR y reintenta la conversión» | OCR manual y reintentar |

Los tres se **ejecutan**: `.doc`/`.ppt` no llegan a markitdown (el catálogo los corta en el borde) y
el escaneado se cierra con `GUIDE_OCR` **sin escribir un parcial**. Al indexar, el escaneado queda
`skipped` y **nunca** produce una fila vacía (OM-11) — afirmado en el mismo test. El detector de
«escaneado» es el propio extractor: markitdown devuelve markdown vacío ⇒ `ExtractionError` «sin capa
de texto» al indexar y `SOURCE_UNREACHABLE` al convertir; `list_formats` lo declara de antemano
(`notes`: «Sin OCR…»).

## 7. RED archivado

Primera corrida del test completo **antes** de publicar §6.3 en `docs/TRD.md`:

```text
test_format_matrix.py ...............F                                   [100%]
FAILED test_format_matrix.py::test_published_matrix_matches_docs_trd
E       AssertionError: docs/TRD.md §6.3 no coincide con la salida del test; pega esta tabla:
=================== 1 failed, 15 passed, 882 deselected in 118.68s ===================
```

Las 15 celdas/GAP ya medían verde; lo que faltaba era **la publicación**, y la guarda la exige. Con
§6.3 pegada desde la salida del test: **16 passed**. La tabla no se escribió a mano en ningún
momento: `test_published_matrix_matches_docs_trd` compara el documento con lo medido.

## 8. Límites de esta medición (declarados)

* **n = 1 corrida** por forma de cada fixture (matriz funcional, no estadística).
* El vault de la matriz tiene 9 ficheros: demuestra el borde y la cita, **no** escala (eso es T5).
* El `.xls` es un BIFF2 mínimo: prueba el camino `XlsConverter`→`pandas`/`xlrd`, no la variedad de
  libros legacy reales (BIFF5/8 con OLE2); un `.xls` corrupto o cifrado cae en
  `EXTRACTION_FAILED`, ya cubierto por `test_documents.py`.
* La celda `url` **no está verificada** (§5): no se extrapola a «`http(s)` funciona».
* Sin latencia: el criterio 2/3 no se miden aquí.

## 9. Comando

```bash
TEPOCHCALLI_FORMAT_MATRIX_EVIDENCE="$PWD/docs/acceptance/format-matrix.json" \
  just python-test-file format_matrix        # ~2 min; sin la env var no escribe nada
```

El test corre en la suite de módulo **mcp** (`just test-mcp`), sin marcadores `slow`/`heavy` y sin red.
