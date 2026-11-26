# Criterio 6 a escala: brazos 10 % vs 100 % y contraste de filesystem (Phase 6 · T5)

> **Fecha:** 2026-11-13 · **Fase:** Phase 6 — E2E Acceptance · **Calpulli:** T5
> **Estado:** entregado; **sin commit** (lo integra el orquestador).
> **Fuente de verdad:** `docs/BACKLOG.md §1 / C6` (criterio vigente; antes `tasks/plan.md` §Task T5) · `docs/TRD.md` §6 (criterio 6: «sin regresión
> >2× entre tamaños») y §6.2 (umbral fijado en T0/CP-0, **no se toca**) · protocolo de host y FS
> en [protocol.md](protocol.md) §1 y §6.
> **Jerarquía de evidencia (D8):** todo lo de aquí es **`medido`** en el host de referencia con el
> bench `tests/benchmarks/bench_scale_ratio.py`; cada tabla lleva su comando.
> **Evidencia archivada:** [scale-ratio.json](scale-ratio.json) (JSON único con **los dos FS y los
> tres brazos**: muestras crudas de Δ, las 100 consultas por brazo, walk-only y cold index).

## 1. Resultado en una línea

**Δ de indexación: FAIL (6,17× entre 10 % y 100 %, cota 2×) · `search`: PASS (1,71×) ·
fuseblk/NTFS-3G: FAIL declarado como límite conocido (52 996 ms, 1,77× el presupuesto).**

El criterio 6 se decide con **btrfs** (D-P6-3). La parte que el usuario siente en cada consulta
(`search`) cumple; la que se paga en cada refresco **no puede cumplir con el diseño actual**,
porque el walk es lineal en el número de entradas — y eso es exactamente lo que se mide abajo.

## 2. Método: qué se compara y qué se deja fijo

| Hecho | Valor |
| --- | --- |
| Corpus | T1: **11 000 ficheros** (10 000 md + 1 000 PDF), `tree_sha256 27a20c05…3ecd2` |
| Brazo **100 %** | vault de T4 (`/tmp/opencode/t4-scale/vault`), **11 006 chunks**, sin reindexar |
| Brazo **10 %** | **1 100 entradas** (1 000 md + 100 PDF) derivadas **del manifiesto de T1**: uno de cada 10 en orden canónico de ruta, por tipo; cada copia verificada contra su `sha256`; manifiesto propio `tree_sha256 66a194d5…701d65a`; índice **propio en frío** (1 101 chunks) |
| Δ por ciclo | reescribir **10 `.md`** + `index_refresh()`; 20 ciclos; p95 **nearest-rank** `sorted[ceil(0.95·20)-1]` = 19.º valor |
| Consultas | las **100 de T4** (semilla `20261112`), mismo texto, `top_k=5`, por stdio real |
| Host | i7-8750H (6C/12T), 15,5 GiB, btrfs `/dev/nvme0n1p3`, CPython 3.12.14 del venv del payload |
| Orden | `prepare → index10 → search` (índices intactos) `→ delta b100 → delta b10 → walk → ntfs → report` |

**Por qué 10 ficheros en AMBOS brazos (y no 10 vs 100).** El trabajo de parse+embed queda
constante, así que el ratio aísla el **walk/engine a escala**, que es la pregunta del criterio. Es
la opción *favorable* al brazo del 100 %: con reescritura proporcional (100 ficheros) el ratio
subiría, no bajaría.

**Los brazos no comparten índice, y se declara.** El 100 % usa el índice de T4; el 10 % tiene el
suyo, construido en frío en este host con el mismo método. Comparar un índice contra sí mismo no
mediría nada. Los dos brazos son el **mismo corpus** (uno es subconjunto estricto del otro, byte a
byte) y se miden en el mismo host, mismo día y mismo bench.

## 3. Δ de indexación — brazos btrfs

| Brazo | Entradas | p95 | mín / mediana / máx | Presupuesto |
| --- | --- | --- | --- | --- |
| **100 %** | 11 000 | **15 695 ms** | 11 787 / 13 627 / 16 051 | 30 000 ms |
| **10 %** | 1 100 | **2 543 ms** | 1 863 / 2 155 / 2 680 | 30 000 ms |

**Ratio = 15 695 / 2 543 = 6,17× ⇒ FAIL contra la cota de 2× de TRD §6** (fijada antes de medir,
D-P6-8; no se renegocia aquí). El brazo del 100 % **sí** cabe en el presupuesto absoluto (52 % de
30 000 ms); lo que no cumple es la comparación entre tamaños.

### 3.1 Baseline P-02 (declarada, no renegociada)

| Cifra | Valor | Diferencia |
| --- | --- | --- |
| P-02 (Phase 3.5, bench `bench_delta_scale.py`, corpus **sin** manifiesto) | **26 967 ms** | — |
| Este calpulli (T5, corpus de T1 con manifiesto, índice de T4) | **15 695 ms** | **−11 272 ms (−41,8 %)** |

La diferencia es **medida, no estimada**: mismo host y misma rotación de 10 ficheros por ciclo.
Las condiciones no son idénticas y se declaran: P-02 materializaba el corpus dentro del mismo
proceso y construía el índice en esa corrida; aquí el vault está caliente y el índice ya existía
(T4). No se usa para decidir nada: la baseline era una referencia, no un umbral.

### 3.2 El mecanismo: el walk es lineal y se come el ratio

| Componente | 11 000 entradas | 1 100 entradas | Ratio |
| --- | --- | --- | --- |
| **walk-only** (`source.scan_items`, n=5, mediana) | **6 114,7 ms** | **555,1 ms** | **11,0×** |
| resto del ciclo (memo/stat del engine + parse+embed de 10 docs) | ~9 580 ms | ~1 988 ms | ~4,8× |
| **Δ completo (p95)** | **15 695 ms** | **2 543 ms** | **6,17×** |

El walk —que en btrfs **no** es el coste dominante del ciclo, pero sí su parte proporcional al
tamaño— escala con el número de entradas porque el diseño **no tiene watcher residente** (ADR-002:
cero demonios) y cada `index_refresh()` recorre las raíces declaradas. Con 10× corpus, cualquier
presupuesto expresado como «≤2× de latencia» es inalcanzable para el refresco: la cota solo podría
cumplirse si el walk dejase de ser lineal (snapshot de `mtime`/integración con el update del
engine), que es el follow-up que P-02 ya dejó abierto y que exige decisión de diseño, no un ajuste
de bench. Queda como **TD-36** con la cifra.

## 4. Latencia de `search` — brazos btrfs (n = 100, mismas consultas)

| Brazo | Chunks | p95 cliente | p95 `server took_ms` | Presupuesto |
| --- | --- | --- | --- | --- |
| **100 %** | 11 006 | **87 ms** | 84 ms | 500 ms |
| **10 %** | 1 101 | **51 ms** | 49 ms | 500 ms |

**Ratio = 87 / 51 = 1,71× ⇒ PASS** (cota 2×). Los dos brazos están muy por debajo del presupuesto
del criterio 3 (17 % y 10 %). El p95 del 100 % (87 ms) reproduce el de T4 (97 ms) con las mismas
100 consultas: la diferencia es ruido de host, no un cambio de índice.

## 5. Walk-only, publicado aparte (sin embed y sin Δ)

| Brazo | Entradas | Muestras (n=5) | Mediana |
| --- | --- | --- | --- |
| btrfs 100 % | 11 000 | 6 487,5 · 6 114,7 · 5 839,6 · 5 974,3 · 6 916,1 ms | **6 114,7 ms** |
| btrfs 10 % | 1 100 | 562,8 · 552,0 · 590,6 · 555,1 · 554,5 ms | **555,1 ms** |
| fuseblk 100 % | 11 000 | 21 964,6 · 22 705,9 · 23 978,8 · 24 217,5 · 22 945,3 ms | **22 945,3 ms** |

Es la cifra que explica el FS lento y la que hace lineal el Δ. `scan_items` puro: no toca el
embedder ni el ciclo de update.

## 6. fuseblk/NTFS-3G — límite conocido (D-P6-3), sin maquillar

| Cifra | Valor | Veredicto |
| --- | --- | --- |
| Δ p95 (n=20) | **52 996 ms** | **FAIL** (1,77× el presupuesto de 30 000 ms) |
| mín / mediana / máx | 38 491 / 46 894 / 53 533 ms | — |
| walk-only (n=5, mediana) | **22 945 ms** | 76 % del presupuesto **él solo** |
| indexación en frío de las 11 000 entradas | **944 019 ms** (15 m 44 s) | vs 543 645 ms en btrfs (T4) ⇒ **1,74×** |

**Causa.** El walk de 11 000 entradas sobre NTFS-3G cuesta **22,9 s** (17,6 s en P-02): el ciclo de
update lo dominan el walk y el `stat`/memo del árbol sobre FUSE, no el embed de los 10 documentos.
Con ese suelo, ningún refresco cabe en 30 s en este FS.

**Recomendación al usuario.** El presupuesto de 30 s es de un **FS local rápido** (btrfs/ext4/APFS).
Un vault en NTFS-3G (ni siquiera por red) ya lo roza, y una unidad de red o una carpeta sincronizada
(OneDrive/Dropbox, que añaden su propio I/O y bloqueos) lo empeoran: **el vault va en el disco local
del sistema**, nunca en el montaje NTFS ni en una carpeta de sincronización.

**Intento descartado, con su cifra (para no repetirlo).** Copiar el índice ya construido de btrfs al
montaje fuseblk **no funciona**: el memo del engine no cruza el cambio de ruta, así que **cada**
refresh re-extrae y re-embebe las 11 000 entradas (96-204 s por ciclo con `indexed=0`, es decir un
re-embed completo disfrazado de Δ). Se descartó y el brazo se midió con **índice construido en frío
en el propio FS**, que es lo único comparable con P-02.

## 7. Documentos (D51) — aparte, no se mezclan

El Δ de arriba es de **texto**. Los PDF de 30+ páginas siguen midiéndose y publicándose aparte
(T2: PDF de 30 páginas = **3 144 ms p50 / 4 172 ms p95**, n=3 — [documents.md](documents.md)). Este
calpulli **no** los mezcla con el Δ de 10 notas, y por eso el corpus de PDF del brazo de escala es
de 1 página (ver la desviación declarada en [protocol.md](protocol.md) §6).

## 8. Integridad de la medición: dos artefactos encontrados y corregidos

1. **Primer ciclo de cada tramo inflado (~+15 s).** Cada llamada abre un proceso nuevo y el primer
   `refresh` pagaba la inicialización del engine: los ciclos 0, 5 y 10 salían a ~30 s frente a
   ~13-16 s del resto. Se corrigió con un **ciclo Δ de calentamiento descartado** sobre los mismos
   ficheros del primer ciclo medido (el medido reescribe con otra marca ⇒ sigue siendo un cambio
   real). Sin esa corrección el p95 lo fijaba el troceado, no el sistema.
2. **Tramos Δ perdidos por nombre de fichero.** La primera pasada del brazo del 100 % escribió sus
   cuatro tramos con el mismo nombre y se pisaron. Se corrigió (`delta-<arm>-<start>.json`) y la
   pasada publicada es la segunda, con `rewrite_pass = 2` en los tramos del brazo
   (`delta-b100-<start>.json`, en el directorio de trabajo del bench): el contenido reescrito lleva
   una marca de pasada para que una repetición vuelva a ser un cambio real (`--pass N`). El tiempo
   no depende del texto; el warmup de cada tramo exige `indexed = 10`, así que un tramo que no
   cambiara nada **falla**, no promedia basura.

Además, ambos vaults btrfs se midieron con el índice **consistente con el disco** al empezar (el
warmup lo verifica) y el payload (`obsidian-workspace/.tepochcalli/{db,models}`) se comprueba
ausente al final de cada fase.

## 9. Lo que este calpulli NO hace

* **No** toca el contrato MCP, el puerto `ChunkReader`, `lang` ni los pesos de la fusión
  (ADR-005/ADR-010): esto es medición; el bench mide por el camino real (`stdio`) y, cuando mide
  por etapa, en proceso.
* **No** re-materializa el corpus de T1 ni reindexa el vault de T4 entre brazos.
* **No** mueve la cota de 2× ni la reinterpreta a posteriori: el FAIL del Δ se publica como tal.
* **No** mezcla brazos con índices distintos sin declararlo (§2) ni publica el FAIL de NTFS como si
  fuera PASS.
* **No** corre en CI ni en `just ci` (no es `test_*`); sigue siendo herramienta one-shot.
* **No** commitea.

## 10. Reproducción (por tramos, en primer plano)

```bash
just python-bench-scale-ratio --phase prepare     # deriva y verifica el 10 % (1 100 entradas)
just python-bench-scale-ratio --phase index10     # indexación en frío del 10 % (~61 s)
just python-bench-scale-ratio --phase search      # n=100 en AMBOS brazos (~1 min)
for s in 0 5 10 15; do                            # Δ del 100 % (~2 min por tramo)
  just python-bench-scale-ratio --phase delta --arm b100 --start $s --cycles 5
  just python-bench-scale-ratio --phase delta --arm b10  --start $s --cycles 5
done
just python-bench-scale-ratio --phase walk --arm b100
just python-bench-scale-ratio --phase walk --arm b10
just python-bench-scale-ratio --phase ntfs        # corpus + índice en frío en fuseblk (~17 min)
just python-bench-scale-ratio --phase walk --arm ntfs
for s in 0 5 10 15; do                            # Δ en fuseblk (~8 min por tramo)
  just python-bench-scale-ratio --phase delta --arm ntfs --start $s --cycles 5
done
just python-bench-scale-ratio --phase report       # ratio + veredictos → docs/acceptance/scale-ratio.json
```

Artefactos intermedios por tramo en `/tmp/opencode/phase6-scale-ratio/*.json`; los vaults btrfs
quedan ahí para reutilizarse. El vault de fuseblk vive en `benchmarks/t5-ntfs/` (datos de trabajo
gitignored, borrables: `benchmarks/README.md`) y se borra al correr `--phase report` salvo `--keep`.
