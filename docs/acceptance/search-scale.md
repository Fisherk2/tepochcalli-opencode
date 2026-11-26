# Criterio 3 a escala (10k/1k) y deriva del índice FTS ES/EN (Phase 6 · T4)

> **Fecha:** 2026-11-12 · **Fase:** Phase 6 — E2E Acceptance · **Calpulli:** T4
> **Estado:** entregado; **sin commit** (lo integra el orquestador).
> **Fuente de verdad:** `docs/BACKLOG.md §1 / C3` (criterio vigente; antes `tasks/plan.md` §Task T4) · `docs/TRD.md` §6.1 (método) y §6.2 (umbrales,
> fijados en T0/CP-0) · `specs/spec-mcp-server.md` §Presupuesto de latencia.
> **Jerarquía de evidencia (D8):** todas las cifras de este documento son **`medido`** en el host
> de referencia (`/tmp/opencode`, btrfs/NVMe, CPython 3.12.14 del venv del payload) con el
> bench `tests/benchmarks/bench_search_scale.py`; cada tabla lleva su comando.
> **Evidencia archivada:** [search-scale.json](search-scale.json) (39 KB, incluye
> **las 100 consultas publicadas** con su `source_path`, la semilla y las muestras crudas).

## 1. Corpus, índice y método (una sola materialización, un solo índice)

| Hecho | Valor | Origen |
| --- | --- | --- |
| Corpus | **11 000 ficheros** (10 000 `.md` + 1 000 PDF), 10 586 197 B, `tree_sha256` `27a20c05…3ecd2` | manifiesto de T1 verificado (`reused: true`), copiado a `/tmp/opencode/t4-scale/vault` y **re-verificado** byte a byte en el vault del bench |
| Índice | **11 006 chunks** (6 notas partieron en 2), `scanned=11 000`, `indexed=11 000`, `skipped=0`, raíz `00-resources/` | fase `index` (`refresh_blocking`) |
| Coste de la indexación en frío | **543 645 ms** (9 m 03,6 s), `VmHWM` **3 963 392 KiB (3,78 GiB)** | fase `index` — cifra de referencia para T5, no criterio de T4 |
| Consultas | **n = 100** muestreadas del corpus (86 `.md` + 14 PDF), 12 palabras (7 en los PDF), `top_k=5`, semilla **20261112** | `_sample_queries`; las 100 van publicadas en el JSON |
| Percentil | **nearest-rank** `sorted[ceil(0.95·n)-1]`; con n=100 es el **95.º valor ordenado** | declarado en el JSON y en el bench |
| Host | i7-8750H (6C/12T), 15,5 GiB, btrfs `/dev/nvme0n1p3`, CPython 3.12.14 | `host` del JSON |

`p95_client_ms` es la puerta del gate (llamada completa del cliente por stdio, **incluye IPC**);
`p95_server_took_ms` es el punto de medición de la spec (dentro del handler). Las **dos** se
publican; la que decide el criterio es la primera.

## 2. Criterio 3 — resultado

**p95 `client` = 97 ms · p95 `server took_ms` = 94 ms · presupuesto 500 ms ⇒ PASS**
(muestras `client`: mín 70 · mediana 88 · máx 102 ms; n = 100, nearest-rank 95.º).

### 2.1 Tabla por etapa (método y margen declarados)

| Etapa | p95 | Presupuesto (spec) | Margen de la medición |
| --- | --- | --- | --- |
| **embed** | **27,0 ms** | 120 ms | **directa**: `perf_counter` alrededor del callable real texto→vector, dentro del worker thread; el salto de hilo queda fuera de la ventana (~µs) |
| **ANN+FTS** | **24,5 ms** | 200 ms | **diferencia** `chunks_ms − embed_ms` en la MISMA `reader.search()`: incluye apertura/cierre de la conexión embebida, la consulta híbrida, `to_list` y el mapeo a `CitedChunk`; no descompone la consulta interna de LanceDB (exigiría instrumentar `flow/`) |
| **ensamblado** | **4,6 ms** | 30 ms | **diferencia** `handler_ms − chunks_ms − index_models_ms` + `json_ms` medido directo sobre `tools.json_result`; incluye validación, `apply_budget` y el `asyncio.run` por iteración |
| **IPC** | **3,0 ms** | 150 ms | **diferencia** `client_ms − took_ms` por llamada stdio: despacho del SDK, framing JSON-RPC, tuberías, serialización server-side y ±0,5 ms de cuantización de `took_ms` |
| **index_state** *(fuera de la tabla de la spec)* | **36,5 ms** | — | **directa** sobre `_VaultSearchBackend.index_models`: el handler lee el estado del índice **en cada llamada**; no tiene fila en el presupuesto y por eso se publica aparte |

**Reconciliación:** 27,0 + 24,5 + 4,6 + 3,0 = **59,1 ms** de las cuatro etapas de la spec, más
36,5 ms de `index_state` = **95,6 ms**, contra 97 ms de `p95_client_ms`. La suma cuadra, así
que no hay coste oculto: la mitad del total es la lectura del estado del índice, no la búsqueda.
Las cuatro etapas de la spec quedan al 22 %, 12 %, 15 % y 2 % de su presupuesto respectivo.

## 3. Deriva del índice FTS ES/EN

### 3.1 Las dos piernas, mismo corpus y mismas 100 consultas

| Brazo | recall@5 | hits | MRR | Nota |
| --- | --- | --- | --- | --- |
| **híbrido ANN+FTS+RRF** (producción, por stdio) | **0,19** | 19/100 | 0,154 | coinciden las dos mediciones: por el server (stdio) y en proceso |
| **solo ANN** (misma tabla, mismo embedder, sin `nearest_to_text`) | **0,15** | 15/100 | 0,138 | consulta ANN construida **dentro del bench**: no se añade ningún keyword al adaptador ni se toca el puerto `ChunkReader` (ADR-005) |
| pierna **FTS sola** (BM25, profundidad 50) | — | 19 en top-5 · 25 en top-50 · **75 no aparecen** | — | rango medio 5,6 cuando aparece |

**Umbral T0/CP-0 aplicado sin tocarlo:** caída relativa = (0,15 − 0,19) / 0,15 = **−26,7 %**
(el híbrido recupera **más** que solo ANN) ⇒ **el umbral no se dispara**. Un umbral que no se
dispara también es un resultado: se publica y no se renegocia.

Los 19 aciertos del híbrido son **exactamente** los 19 ficheros que la pierna FTS mete en su
top-5 (`hybrid_also_fts_top5 = 19`): en este corpus la pierna FTS es la que aporta señal y la
ANN no gana ningún documento que el FTS no tuviera.

### 3.2 Por qué el recall absoluto es bajo (y por qué eso no invalida la comparación)

| Subconjunto | híbrido | solo ANN |
| --- | --- | --- |
| consultas de **PDF** (n=14) | **1,00** (14/14) | 0,93 |
| consultas de **nota `.md`** (n=86) | **0,058** (5/86) | 0,023 |

El corpus de escala genera notas como bolsas de ~50 palabras del mismo vocabulario: una frase de
12 palabras de una nota de ~100 palabras es **indistinguible** de otras 9 900 notas casi
idénticas, tanto para BM25 como para MiniLM. Los PDF usan otro vocabulario (20 palabras) y son
1 000 ficheros: ahí la consulta sí identifica su origen (recall 1,00). Es decir: **este corpus
mide el p95 del criterio 3 con honestidad y el SIGNO de la fusión, pero no es un instrumento de
calidad de recuperación** — eso lo mide T3 (recall@5 = 1,00 sobre un vault con conceptos
distintos). La comparación de brazos sigue siendo válida porque ambos ven exactamente las mismas
consultas sobre el mismo índice, sin reindexar entre brazos.

### 3.3 El mecanismo: sonda morfológica (inglés vs español, medido)

El corpus de escala tampoco puede demostrar la deriva del **stemming** (no tiene flexión). La
sonda `tests/support/fts_probe.py` la mide con 9 pares `(query, nota)` donde la consulta usa una
forma que la nota **no** contiene como token, sobre un vault de 61 filas (9 objetivos + 52
distractores) — recall@5 sobre 9 filas sería un techo y no mediría nada:

| Índice FTS (config real leída de `list_indices`) | pares ES con el fichero en top-50 del FTS | controles EN |
| --- | --- | --- |
| **`language="English"`** (el que declara el flow, `app.py`) | **4/7** — `presupuestos`, `evaluaciones`, `ciudades`, `mociones` (todos en el puesto 1) | **2/2** (puesto 1) |
| **`language="Spanish"`** (`create_fts_index(..., name="text", language="Spanish", replace=True)`) | **6/7** — falla `ciudades` | **0/2** — `budgets` y `run` ya no aparecen |

Con el índice inglés **no aparecen** (ni en top-50) `países`, `investigar` ni `aprobadas`: el
stemmer inglés no une `país/países`, `investigar/investigó` ni `aprobado/aprobadas`, que en
español sí comparten raíz. Con el índice español suben a 6/7 pero se pierden los controles
ingleses. En las dos configuraciones el **híbrido** devuelve el fichero correcto en 7/7 ES y 2/2
EN: en un vault de 61 filas la pierna ANN lo compensa, y por eso el número que demuestra el
mecanismo es el **rango en la pierna FTS**, no el recall del híbrido.

### 3.4 Decisión (escrita también en `docs/TRD.md` §6.2 y `docs/TECH_DEBT.md`)

* **Se mantiene `language="English"` en v1.** El umbral no se disparó: en el corpus de escala el
  híbrido **no pierde** recall medible frente a solo ANN (−26,7 % de caída, es decir gana).
* **El límite queda documentado con su cifra** (TD-35): con la config por defecto, 3 de 7 pares
  flexivos ES no llegan al FTS; con `Spanish`, 1 de 7 no llega y se pierden las 2/2 formas
  inglesas.
* **No hay configuración bilingüe en un solo índice.** Verificado contra el pin
  (`lancedb==0.40.0`): `Table.create_fts_index(..., language=...)` existe y
  `lancedb/index.py` mapea `"es" → "Spanish"`, pero **un índice gobierna la columna `text`**;
  dos índices sobre la MISMA columna son ambiguos al consultar (`fts_columns` no los
  distingue — comprobado: el segundo `create_fts_index` sin `name` crea `text_idx` y deja la
  columna con dos configuraciones). Un FTS bilingüe exigiría una **segunda columna de texto**
  (cambio de schema de `ChunkRow`, re-index completo) y, por tanto, **ADR nuevo**.
* **Candidato para esa decisión futura** (no medido aquí, no se recomienda sin medirlo):
  `stem=False`/`remove_stop_words=False` (tokenización neutra, sin stemming en ningún idioma) o
  una columna `text_es` con índice español. El coste de cada opción se mide con esta misma sonda
  antes de decidir.

## 4. Lo que este calpulli NO hace

* **No** toca el contrato MCP ni el puerto `ChunkReader` (6 campos congelados, ADR-005): la
  pierna ANN pura vive en el bench.
* **No** re-materializa el corpus de T1 (se verifica y se copia) ni reindexa entre brazos.
* **No** incluye la latencia del arranque en frío del server (25,8 s de la llamada de
  calentamiento, cargando MiniLM dentro del hijo): la spec excluye el cold start del proceso,
  igual que `bench_search.py` y `bench_delta.py`.
* **No** mide criterio 6 (Δ de indexación y ratio 10 % vs 100 %): es T5, que reutiliza **este**
  corpus e índice. La cifra de la indexación en frío (§1) queda como referencia suya.
* **No** commitea.

## 5. Reproducción (por fases, en primer plano)

```bash
just python-bench-search-scale --phase prepare   # verifica el corpus y copia su 00-resources/
just python-bench-search-scale --phase index     # UNA indexación en frío (~9 min)
just python-bench-search-scale --phase queries   # n=100 por stdio real (client + took)
just python-bench-search-scale --phase stages    # n=100 por etapa, en proceso
just python-bench-search-scale --phase legs      # híbrido vs solo ANN vs FTS sola
just python-bench-search-scale --phase probe     # sonda morfológica ES/EN
just python-bench-search-scale --phase report    # une todo → docs/acceptance/search-scale.json
# o las siete de golpe: just python-bench-search-scale --phase all   (30+ min)
```

Artefactos intermedios por fase en `/tmp/opencode/t4-scale/<fase>.json`; el vault del
bench (`.tepochcalli/db/` incluido) queda en `/tmp/opencode/t4-scale/vault` para que
T5 lo reutilice sin una segunda indexación en frío. El payload
(`obsidian-workspace/.tepochcalli/{db,models}`) no se creó: la fase `report` aborta si aparece.
