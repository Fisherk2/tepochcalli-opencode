# Coste real de extraer documentos con markitdown (Phase 6 · T2 · TD-2)

> **Fecha:** 2026-11-12 · **Fase:** Phase 6 — E2E Acceptance · **Calpulli:** T2
> **Estado:** entregado; **sin commit** (lo integra el orquestador).
> **Fuente de verdad:** `tasks/plan.md` §5 T2 · `tasks/todo.md` T2 · `docs/TECH_DEBT.md` TD-2 ·
> `docs/TRD.md` §6.1 · `docs/acceptance/protocol.md` §1 (host).
> **Jerarquía de evidencia (D8):** toda cifra de este documento es **`medido`** en el host de
> referencia (btrfs/NVMe, `/tmp/opencode`) con el intérprete pineado del venv; cada fila lleva
> su JSON y su comando. Las dos únicas cifras **derivadas** (no medidas) van marcadas.

## 1. Qué se mide y con qué método

TD-2 pedía el coste de **markitdown** sobre un PDF de 30 páginas y sobre PDFs grandes: la cifra
histórica de 49-51 s pertenecía a **Docling**, que ADR-011 retiró, y no se extrapola (ADR-011 §4.3).

| Decisión de método | Valor |
| --- | --- |
| Extracción | `MarkItDown().convert(path).markdown` en un **proceso hijo limpio por muestra** (markitdown en proceso, como el motor) |
| Reloj | `time.monotonic()` **dentro del hijo**; `construct_ms` y `convert_ms` se publican por separado |
| RSS | **`VmHWM`** de `/proc/self/status` leído por el propio hijo antes de salir: pico real del proceso que extrae (no muestreo del padre que puede perder el máximo) |
| Indexación | `RefreshReport.elapsed_ms` de `flow_app.refresh_blocking()` en un vault temporal; un **warm-up** con carga del modelo **fuera** de las muestras (`cold_ms`) |
| Percentiles | **nearest-rank** `sorted[ceil(p·n)-1]`, n declarado por fila |
| Filesystem | **btrfs / NVMe** (`df -T /tmp/opencode` → `/dev/nvme0n1p3 btrfs`, D-P6-3); los libros se **copian** a `/tmp/opencode/phase6-docs/` antes de medir |
| Host | Intel i7-8750H, 12 vCPU, 15,8 GiB, CPython **3.12.14** (venv del payload), Linux 7.3.1 |
| Bench | `tests/benchmarks/bench_documents.py` · `just python-bench-documents …` |
| Ejecución | un documento por llamada, **primer plano** (AGENTS.md §Commands) |

## 2. Extracción — tabla completa (n=3 por fila, `medido`)

| Documento | Págs | Bytes | p50 | p95 | ms/página (p50) | chars | chars/página | RSS pico (MiB) | JSON |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `generated-30-pages.pdf` (generado) | **30** | 85 924 | **3 144 ms** | **4 172 ms** | **104,8** | 51 761 | 1 725,4 | 191,6 | `t2-30p.json` |
| `16-pages.pdf` | 16 | 266 288 | 3 535 ms | 3 759 ms | 221,0 | 53 568 | 3 348,0 | 194,3 | `t2-16.json` |
| `335-pages.pdf` | 335 | 6 903 167 | 50 557 ms | 50 704 ms | 150,9 | 1 000 523 | 2 986,6 | 221,7 | `t2-335.json` |
| `444-pages.pdf` | 444 | 8 414 896 | 95 068 ms | 100 446 ms | 214,1 | 527 068 | 1 187,1 | 244,0 | `t2-444.json` |
| `952-pages.pdf` | 952 | 6 580 624 | 121 483 ms | 125 724 ms | 127,6 | 2 278 941 | 2 393,8 | 254,8 | `t2-952.json` |
| `1313-pages.pdf` | 1 313 | 5 076 764 | 128 015 ms | 133 730 ms | 97,5 | 3 344 734 | 2 547,4 | 248,2 | `t2-1313.json` |

Muestras crudas (ms), para que el lector las juzgue:

| Documento | `extract_samples_ms` (n=3) |
| --- | --- |
| 30 págs | 2 847,4 · 3 143,9 · 4 172,3 |
| 16 págs | 3 759,0 · 3 409,7 · 3 535,3 |
| 335 págs | 50 557,0 · 47 600,7 · 50 704,3 |
| 444 págs | 90 956,2 · 95 067,5 · 100 446,0 |
| 952 págs | 125 723,7 · 121 483,2 · 111 676,0 |
| 1 313 págs | 133 729,6 · 128 015,2 · 118 296,1 |

n real: **3 en todas las filas**. En los libros grandes no se subió de 3: el de 1 313 páginas
cuesta ~2,1 min por muestra y la varianza entre muestras es pequeña (118-134 s), así que más n
compra precisión que no cambia la conclusión. El coste del intérprete + `MarkItDown()` es
constante y pequeño (`construct_ms` p50 = **45-57 ms**); no explica las diferencias.

### Contraste: corpus de 1 página de T1 (muestra, n=3 por PDF, `medido`)

Los 1 000 PDF de 1 página de T1 (`/tmp/opencode/phase6-corpus/00-Resources/pdfs/`) son
**minimalistas** (51-58 chars extraídos): su extracción está dominada por el coste fijo del
proceso, no por el contenido.

| PDF | Bytes | p50 | p95 | chars | RSS pico (MiB) |
| --- | --- | --- | --- | --- | --- |
| `informe-00000.pdf` | 707 | 67,0 ms | 67,6 ms | 54 | 189,0 |
| `informe-00001.pdf` | 704 | 65,5 ms | 88,4 ms | 51 | 189,1 |
| `informe-00002.pdf` | 711 | 75,7 ms | 79,1 ms | 58 | 190,9 |

En **8 llamadas independientes** (cada JSON repite la muestra) el p50 por fichero cae siempre en
**59-110 ms**; ninguna muestra bajó de 59 ms aunque el `convert()` puro de estos PDF sea ~15-19 ms:
el resto es arranque del intérprete + imports de markitdown. Json: `t2-30p.json`, `t2-16.json`,
`t2-335.json`, `t2-444.json`, `t2-952.json`, `t2-1313.json`, `t2-index-16.json`, `t2-index-335.json`.

## 3. Indexación separada de la extracción (n=3, `medido`)

Mismo protocolo, vault temporal, un hijo que carga el modelo **una vez** (el `cold_ms` incluye
la carga y queda **fuera** de las muestras). Cada muestra escribe una copia con un comentario PDF
único para que el memo por contenido no pueda saltarse parse+embed.

| Documento | Págs | `extract_ms` p50 | `index_ms` p50 | `index_ms` p95 | Delta (embed+upsert) | RSS pico (MiB) | JSON |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `16-pages.pdf` | 16 | 3 535 | **6 413** | **7 381** | ≈ 2 878 ms | 1 522,1 | `t2-index-16.json` |
| `335-pages.pdf` | 335 | 50 557 | **108 478** | **118 219** | ≈ 57 921 ms | 1 789,2 | `t2-index-335.json` |

* muestras de indexación: 16 págs `[7 381, 6 266, 6 413]`; 335 págs `[108 478, 102 390, 118 219]`.
* `cold_ms` (excluido del muestreo): **43 293 ms** y **52 272 ms** — carga del modelo + creación
  del índice. `VmHWM` del hijo en frío: **1 338-1 342 MiB**, que es el suelo del RSS de indexación.
* El RSS de indexación incluye el modelo (≈1,3 GiB); el de extracción es solo markitdown
  (**190-255 MiB**). No son comparables entre sí y no se mezclan.

## 4. Lectura de los datos

1. **El coste por página NO es una constante del formato.** 221 ms/página (16 págs) → 97,5
   ms/página (1 313 págs): factor **2,3×**, pero **no monótono** — 444 págs (214,1) es más caro
   por página que 335 págs (150,9). Lo que manda es la **composición** del documento (objetos,
   imágenes, densidad de texto: `chars/página` va de 1 187 a 3 348), no el número de páginas.
   **Corolario: extrapolar ms/página de un documento a otro es inválido**; la cifra buena es la
   medida, y así se publica el PDF de 30 páginas (medido, no derivado).
2. **La cifra de Docling no se extrapolaba y además sobra:** markitdown saca 30 páginas en
   **3,14 s p50**, frente a los 49-51 s de Docling — un orden de magnitud. El pico de RSS es
   **191,6 MiB** frente a los 2 048-2 189 MiB históricos.
3. **Los PDF de 1 página no son 1/30 de un PDF de 30 páginas:** 65-76 ms contra 3 144 ms no
   escala (30 × 70 ms = 2,1 s ≠ 3,1 s). La parte fija (arranque + imports) es la mitad de la
   cifra pequeña y desaparece en la grande.

## 5. Derivaciones (declaradas como derivación, **no** medidas)

| Derivación | Cálculo | Resultado |
| --- | --- | --- |
| Extracción de 30 págs desde los libros | rango 97,5-214,1 ms/página × 30 | **2,9-6,4 s** — el medido (3,14 s) cae dentro |
| Extracción del corpus de 1 000 PDF de 1 página de T1 | 1 000 × (59-110 ms) muestreados | **59-110 s** de extracción **una vez** (índice inicial), no un Δ |
| Indexación de 30 págs (embed+upsert) | Delta del 16-págs (2 878 ms / 16 págs) × 30 | **≈ 5,4 s**; total extracción+indexación ≈ **8,5 s** |

## 6. Condición de TD-2, resuelta con el dato

**Pregunta de TD-2:** ¿cuánto cuesta un PDF de 30 páginas con markitdown, y rompe la percepción
del Δ de 30 s (criterio 2)?

* **30 páginas ⇒ NO lo rompe.** Medido: **3,14 s p50 / 4,17 s p95** de extracción; con la
  indexación derivada (~5,4 s) el refresco de ese documento queda en **≈ 8,5 s**, por debajo de
  30 s con margen 3,5×.
* **Un libro de 335+ páginas SÍ supera los 30 s**: 50,6 s de extracción y 108,5 s de
  extracción+indexación (335 págs); 121-128 s de extracción (952/1 313 págs). D51 ya declara los
  documentos **fuera** del presupuesto del Δ de texto, pero el usuario **percibe** ese refresco:
  es la diferencia entre «el presupuesto no lo cubre» y «la operación tarda dos minutos».

**Cierre de TD-2:** la deuda era la **ausencia de cifra**. Con la cifra medida arriba, TD-2 se
**cierra** en su parte de medición: el PDF de 30 páginas está holgadamente dentro de 30 s y el
coste del formato queda publicado (`docs/TRD.md` §6.1). Lo que queda abierto no es TD-2 sino una
**decisión de producto** sobre los libros grandes, que se propone a continuación — redactada para
la firma del dueño, **sin implementar y sin ADR**.

### Propuesta para el dueño (elegir una; no implementada)

| Opción | Qué implica | Coste estimado | Riesgo |
| --- | --- | --- | --- |
| **A. Mantener D51 tal cual** (recomendada para v1) | Documentos binarios siguen fuera del presupuesto de 30 s; se publica la cifra y el aviso al usuario de que el primer refresco de un libro tarda minutos | **0 código**; 1 nota en TRD (hecha) + 1 frase en la spec del MCP | El usuario ve un `index_refresh` de 2 min sin progreso; no es un fallo, es UX |
| **B. Aviso de progreso en `index_refresh`** | Mantener D51 y añadir trazas a stderr por documento (el contrato devuelve el resumen al final, sin cambiar el JSON) | **~0,5 día**: log por fichero + test de contrato que no cambia el shape | Ninguno sobre el contrato (ADR-005 intacto) |
| **C. Límite de tamaño configurable** | `max_document_pages` (p. ej. 200) en `tepochcalli.toml`: los PDF que lo superan se cuentan como `skipped` con motivo tipado | **~1-2 días**: config + taxonomía de skip + tests + spec | Un vault con libros grandes deja de indexarlos: degrada criterios 6/7 y hay que documentarlo |
| **D. Caché de parseo en disco** | Cachear el markdown por sha256 del binario para no re-parsear tras borrar el índice | **~2-3 días**; **no arregla el primer ingesto** (que es el caso medido) y CocoIndex ya memoiza dentro del índice | Bajo valor para el problema medido |

**Recomendación:** **A + B**. La cifra ya está; el problema restante es de expectativa, no de
rendimiento, y B lo resuelve sin tocar el contrato MCP (ADR-005) ni el payload (D-P6-1). C y D
solo si el dueño decide que los libros grandes deben caber en 30 s, cosa que hoy D51 no promete.

## 7. Evidencia y garantías

| Artefacto | Ruta |
| --- | --- |
| Bench | `tests/benchmarks/bench_documents.py` (`--pdf`/`--index`/`--n`/`--json`/`--doc-pages`/`--matrix`) |
| Generador multi-página | `tests/fixtures/pdf/gen_fixture_pdf.py` (`--pages N`; el de 1 página queda byte a byte idéntico — `sha256` verificado contra `articulo_t7.pdf`) |
| Test del generador | `tests/unit/test_gen_fixture_pdf.py` (xref real, `/Count 30`, texto presente; <1 s) |
| JSON archivo | `/tmp/opencode/t2-{16,335,444,952,1313,30p,index-16,index-335}.json` |
| Copia de los libros en btrfs | `/tmp/opencode/phase6-docs/` |

* **Sin procesos en segundo plano:** cada fila se midió en una llamada en primer plano y terminó
  dentro de ella.
* **Cero cambios en `obsidian-workspace/`** (`git status --short` solo lista `tests/` y `docs/`;
  el `Justfile` ya tenía la receta `python-bench-documents`).
* El PDF de 30 páginas **no entra en CI**: se genera on-demand en `/tmp/opencode` y el bench no es
  `test_*`.
* `VmHWM` es el pico del **hijo**; en las filas de indexación incluye el modelo de embeddings
  (≈1,3 GiB), por eso 1 522-1 789 MiB y no los 190-255 MiB de la extracción pura.
