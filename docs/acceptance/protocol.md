# Protocolo de aceptación — Phase 6

> **Fecha:** 2026-11-12 · **Fase:** Phase 6 — E2E Acceptance · **Estado:** borrador para CP-0
> (revisión del dueño; sin aprobación, ningún calpulli mide).
>
> **Fuente de verdad de los criterios:** `docs/BACKLOG.md §1 / C1–C7`.
> **Metodología de la corrida:** `docs/WORKFLOW.md` §Phase 6 (líneas 271-294).
> **Protocolos numéricos:** `docs/TRD.md` §6.1 (método, líneas 80-97) y §6.2 (umbrales, 99-117).
> **Jerarquía de evidencia (D8):** `medido > estimado > declarado`. Cada cifra de este
> documento lleva su comando (`nproc`, `df -T`, `wc -l`…) o su fuente con `ruta:línea`.
> **Este calpulli no ha medido nada:** el protocolo se escribe antes de medir (D-P6-8). Las
> cifras que aparecen son baselines **ya registrados** en el repo, citados con su origen.

## 1. Host y filesystem de referencia (D-P6-3)

| Hecho | Valor | Comando / fuente |
| --- | --- | --- |
| CPU | Intel Core i7-8750H @ 2.20 GHz, **6C/12T** | `lscpu` (`Model name`, `CPU(s)`) |
| vCPU visibles | **12** | `nproc` → `12` |
| RAM total | **15,5 GiB** | `awk '/MemTotal/{print $2/1048576}' /proc/meminfo` → `15.5 GiB`; `free -g` redondea a `15` |
| Interprete pineado | **CPython 3.12.14** | `obsidian-workspace/.tepochcalli/venv/bin/python -V` |
| Interprete del host | CPython 3.14.9 (system) | `python3 -V` — **no** es el que corre el motor; los benches usan el venv del payload |
| Swap | zram **7,9 GB** (7,7 GiB, prioridad 100) | `swapon --show` → `/dev/zram0 7.7G`; `cat /sys/block/zram0/disksize` → `8.3 GB` brutos |
| FS de referencia | **btrfs / NVMe** | `df -T /tmp/opencode` → `/dev/nvme0n1p3 btrfs` |
| FS de contraste | **fuseblk (NTFS-3G)** | `df -T /mnt/HDDFish` → `/dev/sda1 fuseblk` |

**Decisión de medición (D-P6-3, `tasks/plan.md:45`):**

* La cifra que **decide** el PASS/FAIL de los criterios 2, 3 y 6 es la medida en
  **btrfs/NVMe** (`/tmp/opencode`). Todo bench que escriba corpus pasa `--dir` apuntando ahí.
* **NTFS-3G es límite conocido, no objetivo de optimización en v1.** Se mide igual y se
  publica con su cifra y su causa en la columna de límites de la tabla §6.3; un FAIL en
  NTFS-3G **no** bloquea la release por sí solo, pero se declara.
* El repositorio vive en NTFS-3G: un bench lanzado sin `--dir` mide el filesystem equivocado
  (`tests/benchmarks/bench_delta.py:58-63`).
* **Desviación declarada vs `docs/TRD.md:82`:** TRD pide «VM limpia, 8GB, SSD»; este host es
  el de desarrollo (15,5 GiB, zram, btrfs/NVMe), no la VM de referencia. La desviación ya está
  registrada para Phase 1 en `docs/WORKFLOW.md:38` y se mantiene por ausencia de VM; el FTR
  debe verla escrita, no silenciada.

## 2. Los 7 criterios de BACKLOG.md, literales

Copiados **textualmente** de `docs/BACKLOG.md §1 / C1–C7` (sin parafrasear, sin corregir
mayúsculas ni tildes):

1. El vault de Obsidian funciona normalmente sin interferencias
2. Los archivos nuevos se indexan automáticamente en menos de 30 segundos cuando Opencode invoca la función del MCP correspondiente
3. Las búsquedas semánticas devuelven resultados relevantes en menos de 500ms
4. El consumo de tokens por consulta es inferior a 2000 tokens (incluyendo contexto)
5. Las respuestas del agente incluyen citas precisas a las fuentes originales
6. El sistema puede manejar vaults de hasta 10,000 notas y 1,000 PDFs sin degradación de rendimiento
7. Pueda procesar distintos formatos de texto, si no, utilizar el convertidor Markdown para que pueda manipularse adecuadamente.

| # | Cota exacta que se mide |
| --- | --- |
| 1 | Cualitativa: vault operativo, `.obsidian/` intacto, 0 puertos nuevos |
| 2 | Δ de indexación **< 30 s** (`index_refresh` invocado por el agente) |
| 3 | `search` **< 500 ms** |
| 4 | **< 2000 tokens** por consulta, contexto incluido |
| 5 | Citas con `source_path` + `heading` + offsets **reproducibles** |
| 6 | **10 000 notas + 1 000 PDFs** sin degradación de rendimiento |
| 7 | Formatos distintos procesables, con el conversor Markdown como fallback |

### Gate adicional D9 — **no es el criterio 8**

`docs/WORKFLOW.md:287` lo dice literalmente: *«Gate adicional (no criterio UH) — no forma parte
de la tabla de 7 criterios de BACKLOG.md (no se renumeran ni se añade un "criterio 8")»*.

* **Contenido:** methodology e2e de los 9 comandos (`/rubric → /update`) sobre corpus golden,
  con bandejas D9.2, permission fixtures D9.3 y frontmatters assertados (`docs/WORKFLOW.md:266`).
* **Estado de partida:** **no ejecutado**. La corrida se difirió en Phase 5 (D-P5-10, TD-31) y
  el runbook `tests/phase5-methodology-runbook.md` está escrito contra el formato **anterior** a
  la ola canónica del 2026-11-12 (`tasks/plan.md:76`).
* **Quién lo ejecuta:** el QA humano (D-P6-2, `tasks/plan.md:44`); no es automatizable. Phase 6
  entrega scaffolding y verificación mecánica (T14) y la corrida es de T15. Sin corrida se
  declara **NO EJECUTADO**, nunca verde.

## 3. Tabla de huecos

Rutas verificadas con `ls`/`grep` el 2026-11-12. `n` y método: nearest-rank sobre n=20
(`sorted[ceil(0.95·n)−1]`) es la convención del repo.

| Criterio | Bench/test que lo mide hoy | Cifra actual y método | Calpulli que lo cierra |
| --- | --- | --- | --- |
| 1. Sin interferencias | `no existe` como test ejecutable. Solo checklist en prosa: `specs/spec-vault-structure.md:147` (assert `.obsidian/` byte-idéntico, 0 puertos nuevos, 0 archivos `.`-prefijados en la API de Obsidian) | no medida | **T9** |
| 2. Δ < 30 s | `tests/benchmarks/bench_delta.py` (Δ de texto, corpus 50 md/txt, 20 ciclos; binarios medidos aparte vía `pdf_policy`, `bench_delta.py:417`) | **4 299 ms** p95 de texto, n=20 nearest-rank (`docs/WORKFLOW.md:115`, M11). PDF de 30 páginas con markitdown: **no medido** (TD-2) | **T2** (coste del PDF) + **T5** (escala) |
| 3. `search` < 500 ms | `tests/benchmarks/bench_search.py` (corpus 100 ficheros, n=20, por etapas) · a escala, `tests/benchmarks/bench_delta_scale.py` (solo walk, sin `search` a 10k/1k) | **52 ms** p95 cliente / **49 ms** `took_ms`, n=20, corpus 100 ficheros (`docs/WORKFLOW.md:57`, M2). **No medido sobre 10k/1k** | **T4** (con el corpus de **T1**) |
| 4. ≤ 2000 tokens | `tests/integration/test_mcp_budget_adversarial.py` (techo 1600 por `chars/4 + 25`) · medidor e2e del harness: `no existe` | **no medida** con tokenizador real: la cota 1600 se estima con `chars/4 + 25` (`docs/TRD.md:92`) | **T6** |
| 5. Citas precisas | `tests/e2e/test_mcp_journey.py` (golden **grabado**: `source_path` real, slice del md == `text`, `heading is None` en PDF, `offsets_ref` `source`/`extract`) · re-verificación contra el archivo vivo: `no existe` (TD-13) | e2e grabado verde; **sin re-verificación post-indexación** y **sin recall etiquetado** (TD-15) | **T7** (con el recall de **T3**) |
| 6. 10k notas + 1k PDFs | `tests/benchmarks/bench_delta_scale.py` (10 000 md + 1 000 PDF, 20 Δ + walk-only, `--dir`/`--keep`) | btrfs **26 967 ms** PASS (90 % del budget) · NTFS-3G **39 501 ms** FAIL · walk-only 7,2 s vs **17,6 s** (`docs/TECH_DEBT.md:200-201`, bench P-02). **Sin manifiesto de hash** del corpus | **T5** (con el corpus de **T1**) |
| 7. Multi-formato | Conversor probado por tool (`tests/integration/test_mcp_convert_document.py`, `tests/unit/test_formats.py`), catálogo de 8 formatos · **matriz** docx/xlsx/html/url → indexable: `no existe` | «8 formatos» declarado, **sin matriz ejecutable** | **T8** |
| Gate D9 (no criterio 8) | `tests/phase5-methodology-runbook.md` (runbook, formato pre-2026-11-12) · verificador mecánico: lo entrega T14 | **no ejecutado** (TD-31, D-P5-10) | **T14** (scaffolding) + **T15** (corrida QA) |

**Desviaciones del protocolo que el FTR debe ver escritas (drift detectado en T0):**

* **Corpus de PDFs:** `docs/TRD.md:84` pide 1 000 PDFs de **5-40 páginas**; el bench existente
  genera **1 página** (`tests/benchmarks/bench_delta_scale.py:7,106`). Con 1 página el coste de
  extracción por documento queda subestimado (TD-2). T1 (corpus con manifiesto) y T2 (PDF de 30
  páginas) existen para cerrar esto.
* **Corpus de `search`:** TRD §6 pide 100 queries sobre 10k/1k; hoy el bench usa 100 **ficheros**
  y 20 queries (`tests/benchmarks/bench_search.py:133,181`).
* **Punto de medición:** TRD fija «tool-call recibido → respuesta serializada»; `bench_search.py`
  publica **dos** cifras (cliente stdio y `took_ms`). La que **decide el criterio** es
  `p95_client_ms` —incluye IPC y es lo que vive el usuario—; `p95_server_took_ms` se publica
  como el punto de medición de la spec (`tasks/plan.md` §5 T4).

## 4. Tabla §6.3 con `Result` vacía y `origen de la cifra`

Copiada de `docs/WORKFLOW.md:277-285`, con columna nueva al final (convención de T16, D-P6-7).
`Result` queda **☐** hasta que el calpulli dueño la rellene con una cifra y su origen.

| Criterio BACKLOG.md | Test | Result | origen de la cifra |
| --- | --- | --- | --- |
| 1. Sin interferencias | checklist Vault-OK post-instalación (0 puertos, `.obsidian/` intacto, UI limpia) | ☐ | T9 → script de checklist + `ss -ltnp` + hash de `.obsidian/` |
| 2. Δ <30s | bench `index_refresh` 20 corridas típicas | ☐ | T2/T5 → `bench_delta.py` y `bench_delta_scale.py`, p95 n=20 nearest-rank, btrfs |
| 3. Búsqueda <500ms | bench `search` p95 sobre corpus 10k/1k | ☐ | T4 → `bench_search.py` a escala, `p95_client_ms` (n=100 nearest-rank) + `p95_server_took_ms` |
| 4. ≤2000 tokens/consulta | fixture adverso + medidor e2e del harness | ☐ | T6 → payload del server + tokenizador real del harness |
| 5. Citas precisas | golden answers: 100% con `source_path`+`heading`+offsets reproducibles | ☐ | T7 → `test_mcp_journey.py` ampliado + `verify.py --spot-check` |
| 6. 10k notas + 1k PDFs | stress corpus + regresión de latencia vs 10% | ☐ | T5 → `bench_delta_scale.py` (10 % vs 100 %), corpus con manifiesto de T1 |
| 7. Multi-formato | matriz conversión (docx/xlsx/html/url) → indexable | ☐ | T8 → matriz ejecutable + fixture por formato |

Gate adicional (`docs/WORKFLOW.md:289-291`):

| Gate | Test | Result | origen de la cifra |
| --- | --- | --- | --- |
| Methodology e2e (§Phase 5 Validación D9) completo en corpus golden | corrida `/rubric→/update` con bandeajes D9.2 + permission fixtures D9.3 + frontmatters assertados | ☐ | T14 → runbook actualizado + verificador; T15 → corrida del QA (o **NO EJECUTADO**) |

## 5. Deuda re-declarada (D-P6-4)

Fuente: `tasks/plan.md:46` y `docs/TECH_DEBT.md`. La deuda **en alcance** se paga en Phase 6;
la **fuera de alcance** se re-declara abierta, no se cierra por omisión.

| Deuda | Estado | Calpulli | Motivo / nota |
| --- | --- | --- | --- |
| TD-2 — coste de extracción de binarios; PDF de 30 páginas sin medir | En alcance | **T2** | Afecta al criterio 2; nunca hubo cifra con markitdown |
| TD-13 — la cita no se re-verifica contra el archivo vivo | En alcance | **T7** | Afecta al criterio 5 (cita válida en forma, falsa contra el vault vivo) |
| TD-15 — sin eval de relevancia (recall) | En alcance | **T3** | Afecta a los criterios 3 y 5; habilita el umbral de §6 |
| TD-27 — PDF sin jerarquía de headings (D54) | En alcance | **T10** | Se resuelve **midiendo** el impacto en el criterio 5 (D-P6-5) |
| TD-28 — `embedder_menu.rs` con 894 líneas | En alcance | **T11** | Tramo 701-1000 con advertencia; refactor a <500 |
| TD-29 — `require_local_model` solo mira que el directorio no esté vacío | En alcance | **T11** | Endurecer la comprobación del snapshot |
| TD-34 — refs del payload a skills sin verificar | En alcance | **T12** | Solo lectura del payload; `git diff --stat -- obsidian-workspace` vacío |
| D-b — Windows fuera de la matriz y sin probar | En alcance | **T13** | Se cierra como **declaración honesta** de soporte (D-P6-6), no como «probado» |
| **M6 — CI y release nunca ejecutados** | **Fuera** | — | Motivo textual: es una decisión de **producto/entrega** (publicar una release de prueba), no un criterio de aceptación del sistema instalado; se re-declara **abierta** en T16 |
| **TD-32 — advertencias de tamaño en el wizard y `RecordingProc` clonado** | **Fuera** | — | Motivo textual: **no seleccionada** en D-P6-4; T11 solo toca `embedder_menu.rs` y `embedder.py`, no `installer.rs` ni los ficheros de test; se re-declara **abierta** en T16 |

## 6. Umbrales propuestos (a fijar en CP-0, D-P6-8)

**Estado: APROBADOS en CP-0 (2026-11-12) por el dueño, sin cambios sobre la propuesta.** Están
vigentes y escritos en `docs/TRD.md` §6.2 desde antes de la primera medición.

1. **Recall@5 = 1.0** sobre el golden vault, con **n = 10 consultas etiquetadas** (mix ES/EN,
   `query → source_path` esperado), siguiendo el patrón de TD-15 (`docs/TECH_DEBT.md:26`).
   «Etiquetada» = el `source_path` correcto se fija **antes** de correr la consulta.
2. **Deriva FTS = caída de recall en español > 10 % relativo** al comparar FTS activa
   (`ANN + FTS` con fusión RRF) contra **solo ANN**, sobre las mismas consultas ES etiquetadas.
   Referencia del hallazgo: FTS declarada sin `language` ⇒ stemming/stopwords solo en inglés
   (`docs/TECH_DEBT.md:189-190`, `flow/tepochcalli_flow/app.py:341`).

**Reglas de uso (D-P6-8):**

* Se escriben en `docs/TRD.md` §6.2 **antes** de medir y **no se ajustan después de ver el
  resultado**; T3 y T4 los aplican tal cual.
* Si CP-0 cambia una cifra, se corrige **en este documento y en TRD §6.2 antes** de la primera
  medición, y el cambio se registra con fecha y motivo.
* Si el umbral no se cumple, el resultado es un **hallazgo** (deuda o decisión), no un umbral
  renegociado.

## 7. Conflicto de numeración en `docs/TRD.md` §6

Hecho verificado (`grep -n '^## ' docs/TRD.md`): **§6 no tiene subsecciones** — va de la línea 78
a la 95 y le sigue §7 en la 97. Sin embargo la casa ya cita «TRD §6.2» al menos dos veces:

* `docs/TECH_DEBT.md:26` (TD-15): *«publicar método/umbral en TRD §6.2»*.
* `docs/WORKFLOW.md:38` (M1): *«Protocolo TRD §6.2»*.

Existe, por tanto, una referencia a una sección **que no existe**. Se resuelve creando, en el
mismo T0 (calpulli siguiente), dos subsecciones dentro de §6:

* **§6.1 «Método»** — el contenido actual de §6 (host/corpus/instrumentación + tabla de
  protocolos), sin cambios de fondo.
* **§6.2 «Umbrales»** — los dos umbrales de §6 aprobados en CP-0.

Al crearlas, las citas existentes («TRD §6.2») pasan a ser correctas sin editarlas.

## 8. Lo que este protocolo NO hace

* **No mide.** Ni un bench, ni un test de rendimiento, ni una corrida de `search`/`index_refresh`.
* **No estima cifras nuevas.** Las que aparecen son baselines ya registrados, con su origen.
* **No ejecuta** ningún bench ni materializa corpus; T0 es lectura del repo.
* **No toca el payload** `obsidian-workspace/` (ni agentes, ni comandos, ni skills).
* **No modifica** `docs/BACKLOG.md`, `README.md`, `LICENSE` ni `docs/TRD.md` (el §6.1/§6.2 lo escribe
  el calpulli siguiente dentro del mismo T0).
* **No cierra deuda:** §5 re-declara; M6 y TD-32 quedan **abiertas**.
* **No aprueba nada:** este documento es el objeto de CP-0; sin aprobación, las cifras de §6 son
  propuestas.
