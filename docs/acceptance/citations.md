# Criterio 5: citas precisas y re-verificación contra el archivo vivo (Phase 6 · T7)

> **Fecha:** 2026-11-13 · **Fase:** Phase 6 — E2E Acceptance · **Calpulli:** T7
> **Estado:** entregado; **sin commit** (lo integra el orquestador).
> **Fuente de verdad:** `docs/BACKLOG.md §1 / C5` — «las respuestas del agente incluyen
> citas precisas a las fuentes originales» (antes `tasks/plan.md` §Task T7) · `docs/TECH_DEBT.md` TD-13.
> **Jerarquía de evidencia (D8):** todo lo de aquí es **`medido`** sobre el golden vault grabado;
> cada cifra lleva su comando.
> **Evidencia archivada:** [citations.json](citations.json) (cifras por corrida).

## 1. Resultado en una línea

**PASS: 6/6 citas reproducibles (100 %) en el golden (md + txt + pdf); 0 citas rotas.**
La re-verificación **detecta** una edición externa: el mismo spot-check pasa de `exit 0` (100 %)
a `exit 1` (3/6, 50 %) cuando se edita un archivo después de indexarlo.

## 2. Qué se mide y qué no

La identidad F1 del contrato —`text[char_start:char_end] == chunk.text`— se afirma al indexar
(`parsers.chunk_document`) y en el e2e grabado. TD-13 abría el hueco restante: **nadie la
re-comprobaba contra el archivo VIVO**. `verify.py --spot-check N` lo cierra:

| Pieza | Cómo se obtiene |
| --- | --- |
| Muestreo | `LanceDBChunkReader.sample_rows(N)` → `table.head(N)`: primeras N filas en orden de almacenamiento (determinista, sin vectorizar consulta) |
| `offsets_ref == "source"` | se relee el **archivo original** (md/markdown/txt) y se corta `[char_start, char_end)` |
| `offsets_ref == "extract"` | se **re-extrae** el binario con markitdown (`parsers.extract_text`) y se corta el texto extraído — el binario nunca es espacio de cita (D50/D54) |
| Veredicto | `verify_slice_identity` (la MISMA función del write path, reutilizada, no duplicada) |
| Severidad | `OK` · `BROKEN` (el slice no reproduce `text` o el extractor falla) · `MISSING` (archivo ausente) |
| Salida | `exit 0` si todas reproducen; `exit 1` si alguna no (el índice existe y se leyó) |

**No se mide aquí** (declarado): la fidelidad de la respuesta final del agente a los chunks
devueltos (TD-14 — vive en los prompts del payload, no en código), ni la relevancia de la
recuperación (TD-15/T3), ni la escala 10k/1k (el spot-check es una verificación de identidad, no
un bench). El golden tiene **n = 6 filas**; el muestreo se declara como tal, no se extrapola.

## 3. Medición sobre el golden vault

Vault copiado de `tests/fixtures/golden_vault/` e indexado en subproceso (`index_vault`, patrón
T8/T9). `--spot-check 100` (pide más filas que las existentes ⇒ cubre el índice entero):

| Corrida | Filas (`source`/`extract`) | Tasa | Rotas | Exit |
| --- | --- | --- | --- | --- |
| Golden limpio | 6 (4 / 2) | **6/6 (100.0 %)** | 0 | **0** |
| Tras editar `00-Resources/nota_dorada.md` después de indexar | 6 (4 / 2) | 3/6 (50.0 %) | **3** | **1** |
| Tras borrar `00-Resources/transcripcion_dorada.txt` | 6 | — | ≥1 (`MISSING`) | **1** |

* **Tasa de citas rotas publicada: 0/6 = 0 %** sobre el golden limpio. No se maquilla: el caso
  que debe fallar falla (3 filas md rotas ⇒ `exit 1`), así que el 0 % no es un «siempre verde».
* Los dos espacios de coordenadas se afirman en la MISMA corrida: md (3 chunks, `source`), txt
  (1 chunk, `source`) y pdf (2 chunks, `extract`).
* **Solo lectura:** el test snapshot-ea `(mtime_ns, size)` de `<vault>/.tepochcalli/db/` antes y
  después de cada corrida ⇒ **0 cambios**, también cuando detecta roturas.

## 4. Golden ampliado (md + txt + pdf)

`tests/e2e/test_mcp_journey.py` afirma sobre el wire los tres formatos:

| Fuente | `source_path` real | `heading` | Offsets | Identidad |
| --- | --- | --- | --- | --- |
| `nota_dorada.md` | sí | ATX en algún chunk (D13: nullable, no anulado) | `source` | slice del original == `text` |
| `transcripcion_dorada.txt` | sí | **`None`** (prosa sin ATX; campo presente, D13) | `source` | slice del original == `text` |
| `articulo_dorado.pdf` | sí | **`None` afirmado** (D54: markitdown no conserva headings) | `extract` | offsets citan el texto extraído |

El refresh del golden pasa a `(scanned, indexed, skipped) = (3, 0, 3)` (md + txt + pdf memoizados).

## 5. Cómo reproducirlo

```bash
TEPOCHCALLI_CITATIONS_EVIDENCE="/mnt/HDDFish/Documents/Programacion/PROYECTOS/14-tepochcalli-opencode/docs/acceptance/citations.json" \
  just python-test-file spot_check
```

Los 3 tests del par (limpio ⇒ 0, edición ⇒ 1, ausente ⇒ `MISSING`) corren en `just test-engine`.
La cifra de cobertura de este código nuevo se reconcilia en **T16** con `just coverage` (no se
corre aquí: ~1 h y calienta el host).

## 6. Límites y deuda relacionada

* **TD-4** (raíz compartida): el índice no se refresca solo (sin watcher, ADR-002). El spot-check
  **detecta** la obsolescencia pero no la corrige: remediación = `index_refresh()` (barato,
  Δ típico 58–178 ms) o re-index del documento editado. Si la tasa de una corrida real fuera > 0,
  se abre esa remediación en TD-4 con la cifra.
* El spot-check muestrea por orden de almacenamiento, no aleatoriamente: con N menor que las
  filas del índice el informe es estable entre corridas, pero no es un muestreo estadístico.
