# ADR-018: Refresco de las restricciones de dependencias del payload (pillow 13, litellm 1.110.4, filelock 4.2.1, soupsieve 4, opentelemetry-api 1.45.2)

* **Status:** Accepted 2026-11-24
* **Date:** 2026-11-24
* **Decision Makers:** Fisherk2 (dueño del repo; orden de preparación de `0.1.0-beta.2`); docs-writer (redacción)
* **Consulted:** [ADR-011](adr-011-politica-dependencias-dos-librerias.md) §4.6 (D56), `GHSA-92x9-889m-jgmw`, OSV.dev (verificación 2026-11-24), `.tepochcalli/pyproject.toml` `[tool.uv] constraint-dependencies`
* **Informed:** mantenedores de `.tepochcalli/pyproject.toml` y `uv.lock`, autores de las suites de conversor/engine, usuarios del payload
* **Traceability:** [docs/BACKLOG.md](../BACKLOG.md) §8 (fila 2026-11-24); [CHANGELOG.md](../../CHANGELOG.md) `[0.1.0-beta.2]`; `.tepochcalli/pyproject.toml` (`[tool.uv]`)

> **Nota de alcance:** este ADR **REFINA** la política de pins de [ADR-011](adr-011-politica-dependencias-dos-librerias.md)
> —su §4.6/D56 y el mecanismo de `constraint-dependencies`—, **no la reemplaza**. La dieta de dos
> librerías (`cocoindex` + `markitdown`) y el resto de D1-D67 siguen intactos. ADR-011 queda
> **byte-idéntico**: no se reeditan ADRs *Accepted*.

## 1. Context and Problem Statement

La preparación de `0.1.0-beta.2` arrastra advisories en el árbol transitivo del payload. El pin de
seguridad de `litellm` fijado en Phase 3.5 (`>=1.106.2,<1.107.0`, D56) protegía del malware de la
serie `1.107.0` (`GHSA-92x9-889m-jgmw`), pero deja la gráfica anclada a una serie antigua y su techo
de `filelock` bloquea versiones ya publicadas (`3.32.7` acumula 13 advisories). En paralelo, `pillow 12.3.0` (vía
`markitdown[pdf,pptx]`) acumula **5 CVEs CRITICAL** corregidos en `13.0.0` —desbordamientos de
heap en FPX/JPEG/TIFF e inyección de argumentos hacia Ghostscript—, y `soupsieve 3.0.3` y
`opentelemetry-api 1.45.1` suman un advisory cada uno.

Pregunta: ¿cómo cerrar esos hallazgos sin añadir dependencias directas ni romper la política de
pins de ADR-011?

## 2. Decision Drivers

* **Cerrar advisories CRITICAL:** 5 en `pillow` y 1 en cada uno de `soupsieve` y `opentelemetry-api`.
* **Salir del rango comprometido de `litellm`:** por encima de `GHSA-92x9-889m-jgmw`.
* **Mantener el mecanismo de ADR-011 D56:** restricción de resolución (`constraint-dependencies`),
  nunca dependencia directa; el extra `cocoindex[litellm]` sigue aportando la op.
* **Cero librería nueva:** los cinco paquetes ya están en el árbol transitivo.
* **Forzar `filelock>=4.2.1`:** `3.32.7` acumula 13 advisories y el suelo ya publicado (`4.2.1+`) está limpio.
* **Trazabilidad reproducible:** `uv.lock` sigue siendo el registro exacto de la resolución.

## 3. Considered Options

* **Option A — Refrescar los suelos de `constraint-dependencies` (elegida):** cinco restricciones de
  resolución (`litellm>=1.110.4,<1.111`, `filelock>=4.2.1`, `pillow>=13.0.0`, `soupsieve>=4.0.0`,
  `opentelemetry-api>=1.45.2`) sin tocar `dependencies`.
* **Option B — Declarar los cinco como dependencias directas:** rechazada — contradice la dieta de
  dos librerías (ADR-011 D52) y mete paquetes que nuestro código no importa.
* **Option C — Conservar los pins antiguos y aceptar los advisories:** rechazada — 5 CRITICAL sin
  mitigación no es un riesgo aceptable en un release.
* **Option D — Pinear versiones exactas (`==`):** rechazada — sobrerrestricción innecesaria; el pin
  exacto ya vive en `uv.lock` y los suelos permiten parches futuros sin reabrir el ADR.

## 4. Decision Outcome

**Chosen option: Option A**, porque cierra los advisories conservando el mecanismo de ADR-011 D56
(restricción de resolución sobre toda la gráfica) y sin añadir dependencias directas. El bloque
queda:

```toml
[tool.uv]
constraint-dependencies = ["litellm>=1.110.4,<1.111", "filelock>=4.2.1", "pillow>=13.0.0", "soupsieve>=4.0.0", "opentelemetry-api>=1.45.2"]
```

Versiones objetivo y motivo:

| Paquete | Restricción | Resuelto en `uv.lock` (2026-11-24) | Motivo |
| --- | --- | --- | --- |
| `litellm` | `>=1.110.4,<1.111` | `1.110.4` | Por encima del rango de `GHSA-92x9-889m-jgmw`; declara `filelock<5`, compatible con el suelo `>=4.2.1` |
| `filelock` | `>=4.2.1` | `4.3.1` | `3.32.7` acumula 13 advisories y `4.2.1+` está limpio; ahora **forzado** por restricción explícita, no solo desbloqueado |
| `pillow` | `>=13.0.0` | `13.0.0` | 5 CVEs CRITICAL corregidos en `13.0.0` (FPX/JPEG/TIFF heap overflow, inyección de argumentos a Ghostscript) |
| `soupsieve` | `>=4.0.0` | `4.1.3` | 1 advisory corregido |
| `opentelemetry-api` | `>=1.45.2` | `1.45.2` | 1 advisory corregido |

El techo `<1.111` de `litellm` se conserva a propósito: acota la serie verificada y evita repetir el
incidente de `1.107.0`; subirlo exige una nueva verificación OSV y, si cambia el rango, un ADR nuevo.

### 4.1 Confirmation

* **OSV.dev, verificación 2026-11-24:** los cinco paquetes en las versiones objetivo no aparecen en
  el rango afectado de sus advisories (incluido `GHSA-92x9-889m-jgmw` para `litellm`).
* **`uv.lock`:** resuelve las cinco versiones de la tabla; `filelock` resuelve `4.3.1` por la
  restricción explícita `>=4.2.1`.
* **Suites:** `test-converter` (markitdown + `pillow` 13) y `test-engine` deben quedar verdes; el
  estado se archiva en la ship review de `0.1.0-beta.2`.
* **Sin imports directos:** `grep` en `flow/`/`mcp/` no referencia `pillow`, `soupsieve`,
  `opentelemetry-api` ni `litellm` (siguen siendo transitivos).

## 5. Pros and Cons of the Options

### Option A — Refrescar los suelos (elegida)

* ✅ **Pros:** cierra los advisories de los cinco paquetes (5 CVEs CRITICAL en `pillow` y 13 en
  `filelock`); `filelock` sube de `3.32.7` a `4.3.1`; mantiene el mecanismo D56 y la dieta de dos
  librerías; cero dependencias nuevas; el pin exacto sigue en `uv.lock`.
* ⚠️ **Cons:** mueve la serie de `litellm` (`1.107` → `1.110`) y obliga a relock; `pillow` sube de
  major (`12` → `13`) y `filelock` de `3` a `4`, con la extracción de PDF/PPTX a revalidar.
* ⚖️ **Neutral:** —.

### Option B — Dependencias directas

* ✅ **Pros:** visibilidad explícita de las versiones.
* ⚠️ **Cons:** rompe ADR-011 D52/D56; declara paquetes que el código no usa.
* ⚖️ **Neutral:** —.

### Option C — Conservar los pins

* ✅ **Pros:** cero cambios y cero relock.
* ⚠️ **Cons:** deja 5 CRITICAL abiertos en un artefacto distribuible.
* ⚖️ **Neutral:** —.

### Option D — Versiones exactas

* ✅ **Pros:** resolución totalmente determinista.
* ⚠️ **Cons:** bloquea parches de seguridad menores; duplica el pin que ya hace `uv.lock`.
* ⚖️ **Neutral:** —.

## 6. Consequences

* ✅ **Positives:** el payload de `0.1.0-beta.2` sale sin los advisories conocidos; `filelock` sube a
  `4.3.1`; la política de pins de ADR-011 se mantiene legible en un único bloque.
* ⚠️ **Negatives / Risks:** el rango de `litellm` se movió y el árbol transitivo cambia con el
  relock; `pillow 13` es un salto de major y puede alterar la extracción de PDF/PPTX de `markitdown`
  (cubierto por `test-converter`).
* ⚖️ **Neutral:** sin dependencias nuevas, sin cambio de contrato MCP, sin cambio del canal `uvx`
  (ADR-014) ni de la topología de cuatro capas.

## 7. Related Decisions

* [ADR-011](adr-011-politica-dependencias-dos-librerias.md) §4.6/D56 — **refinado** (nuevos suelos,
  mismo mecanismo), no reemplazado.
* [ADR-001](adr-001-motor-rag-cocoindex.md) — `cocoindex[litellm]` sigue aportando la op.
* [ADR-009](adr-009-conversor-resumen-sin-cuerpo.md) — `markitdown` sigue siendo el extractor; de él
  llegan `pillow` y `soupsieve`.
* [ADR-014](adr-014-distribucion-uvx-pypi.md) — canal de release; el relock viaja en la rueda.
* [ADR-016](adr-016-resiliencia-offline-y-rollback.md) — instalación offline; el lock se materializa
  en el payload, sin descargas extra en runtime.

## 8. Compliance and Review

* **Success metrics:** OSV sin hallazgos para las cinco versiones; `uv.lock` resuelve
  `litellm 1.110.4`, `filelock 4.3.1`, `pillow 13.0.0`, `soupsieve 4.x`, `opentelemetry-api 1.45.2`;
  suites de conversor y engine verdes en la ship review.
* **Next review date:** 2027-05-24.
* **Revisit triggers:** nuevo advisory dentro del rango, publicación estable de `litellm 1.111+`,
  `pillow 14` o `filelock 5`.

---
*Formato basado en [MADR v4.0](https://adr.github.io/madr/), igual que [adr-template.md](adr-template.md).*
