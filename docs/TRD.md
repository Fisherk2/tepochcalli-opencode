# Technical Requirements Document — Tepochcalli v1 (MVP)

**Date:** 2026-10-21 | **Author:** Arquitecto (entrevista /spec) | **Status:** Approved (alineado a docs/UH.md + ADRs)

## 1. Reference Architecture

Arquitectura hexagonal por capas con frontera única MCP (ADR-005). Detalle y diagramas:
[docs/ARCHITECTURE.md](ARCHITECTURE.md). Resumen de dependencias:

* `obsidian-workspace` (payload de datos/prompt) → sin dependencias de código.
* OpenCode V2 (harness) → solo `mcp.servers` en `opencode.json`.
* `tepochcalli-rag` (adapter de lectura/refresh/ingesta) → CocoIndex flow (adapter de
  escritura) → LanceDB (persistencia). Ninguna flecha inversa.
* Wizard Rust (distribución) → orquesta uv/venv/model/flow/config; no es runtime.

## 2. Matriz de plataformas soportadas

| SO | Arquis | Notas |
| --- | --- | --- |
| Linux | x86_64, aarch64 | primary (distro-agnostic: binarios estáticos de uv/wizard; torch CPU wheel) |
| macOS | arm64 (Apple Silicon), x86_64 | rutas estándar Obsidian; quarantine por Gatekeeper → documentado en wizard UX |
| Windows | x86_64 | `install.ps1`; venv layout `Scripts\` — el merge de opencode.json usa rutas por plataforma |

Requisitos por plataforma: Obsidian instalado; OpenCode V2 en PATH (fase 1 del wizard solo
detecta e instruye, no instala).

## 3. Pisos de recursos (hardware mínimo)

| Recurso | Mínimo | Recomendado |
| --- | --- | --- |
| RAM | 8 GB | 16 GB (bge-m3/local grande) |
| CPU | 4 núcleos (AVX2 deseable para MiniLM) | 8+ |
| Disco para `.tepochcalli/` | 3-4 GB libres | +0.5 GB por cada 1k PDFs (~150MB por 100k chunks + margen LanceDB) |
| Red | Internet en primer arranque (wheels uv + modelo 470MB + payload release) | — (luego `--offline` posible) |

Desglose v1 **medido** (Phase 3.5, host de desarrollo — no la VM de TRD §6): venv canónico
**1,921 GiB** (`du -sb` 2 063 018 440 B; `du -sh` 2.1G) con **135 paquetes**; modelo ~470MB;
LanceDB inicial ~50MB muestra. La cifra manda sobre el rango 1-2GB de la estimación original.

## 4. Versiones pineadas (plan de pin; valores concretos en Phase 1)

| Componente | Plan | Fijado en |
| --- | --- | --- |
| CPython | 3.12.x gestionado por uv (`uv python pin 3.12`) | `.tepochcalli/` (marker uv) |
| uv | latest estable al construir release (binario en `.tepochcalli/bin/`) | wizard lock de release |
| cocoindex | `cocoindex[lancedb,sentence-transformers,litellm]` (extras granulares; no `[all]`) — pin exacto al cerrar Phase 1, bump solo con suite verde | `.tepochcalli/pyproject.toml` + `uv.lock` |
| sentence-transformers | `>=3,<4` con modelo `paraphrase-multilingual-MiniLM-L12-v2` (revisión pin en HF) | pyproject + `models/` |
| markitdown | `markitdown[docx,pptx,xlsx,xls,pdf]==0.1.9` — **librería en proceso** (motor + conversor); sin `markitdown-mcp` | pyproject + `uv.lock` |
| lancedb | vía extra `[lancedb]` de cocoindex (no pinear aparte → evitar divergencia de versiones) | uv.lock |
| OpenCode V2 | `>=` la versión mínima que soporta `mcp.servers` forma usada (ver §5) | detección wizard fase 1 |
| tepochcalli (wizard) | semver propio; release por tag `v*` cargo-dist | GitHub Releases |

Regla: ningún bump entra sin los benches §6 verdes (gate de docs/WORKFLOW.md).

## 5. Notas de schema de config MCP (OpenCode V2)

Estructura usada por el wizard (fuente: <https://opencode.ai/v2/docs/mcp-servers/>):

```jsonc
{ "mcp": { "servers": {
    "<nombre>": {
      "type": "local",                 // stdio local — único soportado por diseño (sin remote)
      "command": ["<argv...>"],        // array; p.ej. [".tepochcalli/venv/bin/tepochcalli-mcp"]
      "cwd": ".",                      // relativo a la raíz del vault = cwd de opencode
      "environment": { "VAR": "{env:VAR}" }, // sustitución de secretos sin commitearlos
      "disabled": false                // permite apagar RAG sin borrar la entrada
    } } } }
```

* El wizard **fusiona** estas entradas conservando servers previos del usuario (fase 8,
  spec-installer-wizard) y hace backup `.bak` atómico.
* `tepochcalli-rag` corre bajo el venv del vault (ADR-004): el mismo `uv sync` lo instala;
  sin `uvx` en el default (razón offline en spec-markitdown). `markitdown` es una **librería
  en proceso** de ese venv, no un server: no hay entrada `mcp.servers.markitdown` (ADR-011).
* Regla de la dieta: dos librerías principales (`cocoindex` + `markitdown`) y sus extras
  granulares; `docling`, `torchvision` y `markitdown-mcp` quedan fuera del venv (ADR-011).

## 6. Metodología de performance (criterios numéricos de UH.md)

### 6.1 Método

Referencia de medición: **VM limpia por plataforma**, CPU-only, 8GB, SSD; corpus = golden vault
(muestra) para humo + **corpus sintético** 10k notas `.md` (1-8KB, ES/EN mix) + 1k PDFs
(5-40 páginas, generado plantilla→PDF) para stress. Instrumentación: timestamps `monotonic_ms`
dentro de las handlers del server MCP (punto de medición = tool-call recibido→respuesta
serializada; definición en spec-mcp-server §latencia).

| Criterio | Protocolo de test | Pass |
| --- | --- | --- |
| 2. Δ indexación <30s | Corridas ×20: tocar/crear 1-50 archivos md en las raíces indexadas (`INDEXER_DIR`), luego `index_refresh()`; registrar `elapsed_ms` | p95 < 30000ms; documentos binarios (`pdf/docx/pptx/xlsx/xls`) medidos y publicados **aparte** (D51) |
| 3. Búsqueda <500ms | 100 queries muestreadas del corpus 10k/1k, `search(top_k=5)`, tras índice estable | p95 < 500ms en HW mínimo |
| 4. ≤2000 tokens/consulta | Fixture adversa (unicode, tablas, listas largas): estimador chars/4 sobre payload `search` + overhead cita + query del usuario; validar contra tokenizador real del harness en e2e | payload ≤1600 tokens garantizado por server + e2e total <2000 |
| 6. Escala 10k/1k sin degradación | Bench delta tras stress: latencia búsqueda y refresh en corpus lleno vs 10% | sin regresión >2× entre tamaños; índices ANN/FTS rebuild < presupuesto |

Relevancia de criterios no numéricos: 1 (no-interferencia) → checklist e2e de
spec-vault-structure §Testing; 5 (citas) → golden answers con asserts de `source_path`/
`heading`/offsets reproducibles; 7 (formatos) → matriz de conversión markitdown fixtures.

**Documentos binarios (D51, medidos aparte del Δ de texto).** Extracción markitdown en proceso,
btrfs/NVMe, CPython 3.12.14: PDF de **30 páginas** = **3 144 ms p50 / 4 172 ms p95** (n=3,
`VmHWM` 191,6 MiB); libro real de **1 313 páginas** = **128 015 ms p50** (n=3); coste por página
**no constante** (97,5-221 ms/página según composición del documento ⇒ no se extrapola). Comando:
`just python-bench-documents --doc-pages 30 --n 3 --json …`; detalle, n por fila y JSON en
[docs/acceptance/documents.md](acceptance/documents.md).

### 6.2 Umbrales

> **Vigencia:** fijados en T0 (2026-11-12) **antes de medir** (D-P6-8) y **aprobados en CP-0 el
> 2026-11-12** por el dueño, sin cambios sobre la propuesta. No se ajustan después de ver el
> resultado; si se cambiaran, la corrección sería aquí y en
> `docs/acceptance/protocol.md` §6 **antes** de la primera medición. El protocolo que estos
> umbrales interpretan es §6.1.

| Umbral | Valor | Método | Calpulli que lo aplica | Fuente |
| --- | --- | --- | --- | --- |
| **Recall@5** | **1.0** | n = **10** consultas etiquetadas ES/EN (`query → source_path` esperado) sobre el golden vault; `search(top_k=5)` en subproceso, afirmando que el `source_path` esperado aparece en el top-5 | **T3** | TD-15 (`docs/TECH_DEBT.md:26`) |
| **Deriva FTS** | **caída de recall ES > 10 % relativo** | Comparar `ANN + FTS` (fusión RRF) contra **solo ANN**, con las mismas consultas ES etiquetadas y el mismo corpus | **T4** | Hallazgo del review 5-ejes: FTS declarada sin `language` ⇒ stemming/stopwords solo en inglés (`docs/TECH_DEBT.md:189-190`, `obsidian-workspace/.tepochcalli/flow/tepochcalli_flow/app.py:341`) |

**Consecuencia de incumplir.** Incumplir un umbral **no** renegocia el umbral: produce un
**hallazgo** que se documenta con su cifra en `docs/TECH_DEBT.md` y, si toca un contrato
`Accepted`, exige **ADR nuevo**.

**Medición de la deriva FTS (T4, 2026-11-12).** Sobre el corpus de T1 (10 000 md + 1 000 PDF,
`tree_sha256 27a20c05…3ecd2`), las **mismas 100 consultas** muestreadas (semilla `20261112`) y
el **mismo índice** (11 006 chunks, sin reindexar entre brazos): recall@5 híbrido (ANN+FTS+RRF)
**0,19** (19/100) vs **solo ANN** **0,15** (15/100) ⇒ variación relativa **−26,7 %** (el híbrido
recupera más): **el umbral no se dispara**. La pierna FTS sola sitúa el fichero de origen en el
top-5 en 19/100 consultas y no lo alcanza (top-50) en 75/100 — con un corpus de vocabulario fijo
(~50 palabras, sin flexión) el corpus de escala mide el **signo** de la fusión, no la deriva
morfológica. La sonda dirigida (9 pares flexivos + 2 controles EN, `tests/support/fts_probe.py`)
sí la mide: con el índice **`language="English"`** que declara `app.py`, 4/7 pares ES llegan al
top-50 del FTS (`países`, `investigar`, `aprobadas` **no** aparecen) y los 2 controles EN rankean
1; con **`language="Spanish"`** suben a 6/7 ES y caen a **0/2** EN. Un solo índice FTS gobierna la
columna `text` (`lancedb==0.40.0`; dos índices en la misma columna son ambiguos: `fts_columns` no
los distingue), así que la configuración bilingüe exigiría una segunda columna de texto +
re-index + ADR nuevo. **Decisión: v1 mantiene `language="English"`** (el híbrido no pierde
recall medible) y el límite queda registrado como **TD-35**. Cifras, tablas, método y JSON:
[docs/acceptance/search-scale.md](acceptance/search-scale.md).

**Medición del criterio 6 a escala (T5, 2026-11-13).** Sobre el corpus de T1, con el brazo del
100 % en el índice de T4 (11 006 chunks) y el del 10 % en un subconjunto derivado del manifiesto
(1 100 entradas, índice propio en frío), mismo host y mismas 100 consultas: **Δ p95 = 15 695 ms
(100 %) vs 2 543 ms (10 %) ⇒ ratio 6,17× = FAIL** de la cota de 2× (el 100 % sí cabe en el
presupuesto absoluto: 52 % de 30 s); **`search` p95 = 87 ms vs 51 ms ⇒ ratio 1,71× = PASS**; y
**walk-only 6 115 ms vs 555 ms (11,0×)** como mecanismo: el walk es lineal y no hay watcher
(ADR-002), así que la cota entre tamaños no es alcanzable en el refresco sin cambiar el diseño del
walk (ADR nuevo; **TD-36**). La cota **no se renegocia**: el resultado se publica como FAIL medido.
En fuseblk/NTFS-3G el Δ es **52 996 ms (FAIL, 1,77× el presupuesto)** con walk de 22 945 ms: va a
límites, no decide (D-P6-3: un vault en NTFS/red/sync degrada el Δ; mantenerlo en disco local).
Cifras, método, muestras y comandos: [docs/acceptance/scale-ratio.md](acceptance/scale-ratio.md).

**Regla de origen de cifra (D-P6-7).** Cada cifra publicada en la tabla §6.3 de
`docs/WORKFLOW.md` lleva **bench + n + método + filesystem**; la jerarquía de evidencia es
`medido > estimado > declarado` (D8) y un número sin comando no entra en `docs/`.

## 7. Requisitos no funcionales adicionales

* **Privacidad:** sin egress en runtime default (embeddings locales; solo el agente usa su LLM).
* **Portabilidad:** borrar `.tepochcalli/{venv,db,models,bin}` = desinstalar sin dejar rastros;
  los fuentes del vault intactos (spec-vault-structure).
* **Observabilidad local:** logs de instalación fuera del vault (XDG/LOCALAPPDATA); métricas por
  tool-call en stderr del proceso MCP (spec-mcp-server §rollback/monitoring).
* **Seguridad:** íntegramente en [docs/SECURITY.md](SECURITY.md) (stdio-only, markitdown
  file-read, claves por env).

## 8. Dependencias de construcción (dev)

* Rust: toolchain estable + cargo-dist para release; clippy/rustfmt (docs/CODE_STYLE.md).
* Python 3.12 + uv para desarrollo del flow/MCP (tests con venv de CI, fixture vault en repo de tests).
* CI de release por tag `v*` (ADR-003); CI de PR: unit+contract+benches de humo (sin stress completo).
