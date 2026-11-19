# Implementation Plan — Tepochcalli v1

**Date:** 2026-10-21 (rev. 12 — Phase 5 **COMPLETADA 2026-11-09** con la salvedad **D-P5-10**: payload materializado y gates estático + install e2e verdes en local; la corrida **D9** (methodology e2e de los 9 comandos) se **difiere al QA de cierre de proyecto** y se entrega el runbook `tests/phase5-methodology-runbook.md` — nada se declara verde sin método. rev. 11 — Phase 4 **COMPLETADA** 2026-11-09: blueprint definitivo en 5 specs **Approved** (freeze 40 del dueño, `cf17f31`/`2e62e60`); gate BLUEPRINT APPROVED concedido por el congelamiento. rev. 10 — Phase 4 **COMPLETADA** 2026-11-04 a nivel de checklist: blueprint del payload en 5 specs <500 líneas (209 skills · 170 agentes · 9 comandos verificados), 0 links rotos, md-lint 0 errores (pagado el único MD005 del baseline) y `git diff --stat -- obsidian-workspace` vacío; **FTR pendiente de aprobación del usuario** — Phase 5 no arranca sin BLUEPRINT APPROVED. rev. 9 — Phase 3.5 **COMPLETADA** 2026-11-04: review 5-ejes post-FTR (6 commits `e191a45`..`6e00aa9`) + plugins del payload a @latest (`ad7575c`, revierte R-04 por orden del dueño); gate final 703 passed+3 slow, coverage 97 %, bench-smoke PASS, rust-ci ok; baseline escala NTFS-3G FAIL / btrfs PASS → Phase 6; Phase 4 lista para planificar. rev. 8 — Phase 3.5 **cerrada con FTR aprobado** 2026-11-03: 7 tools, índice multi-raíz, dieta y skill; ADR-009/010/011 **Accepted**. rev. 7 — Phase 3.5 planificada 2026-11-02: 3 ADR (009/010/011) + 4 specs enmendadas + D28-D67; rev. 6 estado de fases: Phase 1 completada 2026-10-23, Phase 2 completada 2026-10-28, Phase 3 completada 2026-10-28 y cerrada con revisión formal 5-ejes 2026-10-29; Phase 4 listo para planificar; rev. 3 renumeró Payload→5, E2E→6) | **Author:** Arquitecto (entrevista /spec) | **Methodology:** Especificación-driven, fases con gates (doc para `/plan`)

> Cada fase tiene: objetivo, entregables, dependencias, métricas de cierre y **gate** — la fase
> siguiente NO arranca sin gate verde. Los contratos (specs) se congelan en Phase 0; cambiar
> un contrato en vuelo requiere ADR, no solo código.

## 1. Phase Overview

| Phase | Nombre | Objetivo | Gate (criterio de salida, medible) |
| --- | --- | --- | --- |
| 0 | Foundations | Specs/ADRs aprobadas y congeladas | APROBACIÓN: usuario confirma este set de docs; D1-D9 sin cambios; ADR-001..008 Accepted |
| 1 | Engine + Flow | Flujo CocoIndex indexa un vault real incrementalmente | `cocoindex update` sobre vault muestra: Δ <30s; filas en LanceDB queryables con `{source_path,heading,char_start,char_end}`; bench PDF-exclusión documentado |
| 2 | MCP Server | `tepochcalli-rag` conecta a OpenCode con contratos D6 — 4 tools: `search`, `index_refresh`, `add_source`, `rag_status` *(histórico: hoy son 7 — ver Phase 3.5)* | opencode listá tools; `search` devuelve chunks citados <500ms en fixture; asserts de token-budget (≤1600 payload) en tests; taxonomía `E_*` + precedencia `INDEX_EMPTY` cubiertas (contract tests D7.3) |
| 3 | Wizard | Instalador Rust atomico end-to-end | VM limpia (Linux/macOS/Windows, sin Python/Node) → `cargo binstall` (fallback `curl \| sh`) + `tepochcalli install` → vault instalado + índice inicial + `mcp.servers` validados; prueba de idempotencia (2 corridas); instalación con menú de embedder (D7.1) en sus 5 salidas |
| 4 | Diseño del agent workflow (blueprint) | Completar specs/spec-payload-vault.md hasta Approved: system prompts definitivos de los 5 agentes, permisos YAML (last-match-wins), templates de los 9 comandos, tabla de invocación 9×4 y matriz de conflictos contra el inventario REAL de skills — documentación pura, cero escritura de payload | BLUEPRINT APPROVED por el usuario (status → Approved en SPEC.md index); matriz cubre el 100% del inventario (recuento ls vs filas); cero skills/subagents inventados; permisos sin campos legacy V2 |
| 5 | Payload + Skills audit (ejecución) | Ejecución LITERAL del blueprint Approved sobre `obsidian-workspace/` | `obsidian-workspace/` = payload versión-release generado del blueprint; muestras md+PDF; acciones Anexo A ejecutadas (duplicados consolidados, gaps Jupyter/R/Graphviz-PlantUML/LaTeX instalados o declarados won't); alias 00-Resources resuelto: canónico `00-resources/` (TD-8; 2026-11-13); Validación del agent workflow (D9) verde: permission fixtures + methodology e2e *(2026-11-09: fixtures verdes; methodology e2e diferida a QA de cierre — D-P5-10, runbook entregado)* |
| 6 | E2E Acceptance | Validar los 7 criterios de BACKLOG.md sobre sistema completo | Aceptación: tabla §6.3 toda verde en HW mínimo (8GB CPU-only) y corpus 10k/1k; docs de producto alineados |
| 6.5 | Wizard flujo destino (H5-H11) | Materializar el estado objetivo del instalador: canal uvx, TUI full-screen con botones por estado, versión desde pyproject, Update/Desinstall ampliados, selección de device/embedder | GATED (no ejecutable): requiere ADR-014/015 Accepted + deps (maturin/PyPI, TUI) aprobadas + one-version alineada (Cargo↔pyproject) + enmiendas 2026-11-18 Accepted; luego VM limpia sin Python/Node → `uvx tepochcalli` abre el wizard; menú con botones según los 4 escenarios de versión de H5; update/desinstall e2e con backup verificado; smoke TTY en las 3 SO |

> **Estado (2026-11-09):** Phase 1 **completada** (§Phase 1); Phase 2 (server MCP) **completada** — FTR Phase 2→3 verde y aprobado 2026-10-27, rito de calidad posterior y gate final `just ci` verde 2026-10-28 (§Phase 2, §4); **Phase 3 (wizard) completada** — FTR Phase 3→4 verde y aprobado 2026-10-28 (§4), cierre posterior con revisión formal de 5 ejes 2026-10-29 (suite local 311 passed / 0 failed / 2 ignored, 31 commits, deuda nueva TD-23..TD-25); **Phase 3.5 (conversor + multi-raíz + dieta + skill) COMPLETADA 2026-11-04** — FTR aprobado 2026-11-03 (7 tools, ADR-009/010/011 **Accepted**, 4 specs enmendadas definitivas) + review 5-ejes post-FTR (6 commits `e191a45`..`6e00aa9`) + plugins del payload a @latest (`ad7575c`, revierte R-04 por orden del dueño); gate final `just ci` verde local: **703 passed + 3 `slow`**, cobertura **97 %** (gate 95 %), bench-smoke **PASS**, rust-ci **ok** (§Phase 3.5); **Phase 4 (blueprint) COMPLETADA 2026-11-09** — blueprint definitivo en 5 specs **Approved** (freeze 40 del dueño, `cf17f31`/`2e62e60`); gate BLUEPRINT APPROVED concedido por el congelamiento (§4); **Phase 5 (payload) COMPLETADA 2026-11-09** — payload materializado (15 artefactos de texto + 40 skills intactas con hash idéntico al baseline), `opencode.json` sin el array global de 313 reglas, scaffold canónico, gate estático 42/42 probes e install e2e idempotente; **salvedad D-P5-10: la corrida D9 (methodology e2e) queda diferida al QA de cierre de proyecto** con runbook entregado (§Phase 5). GitHub Actions nunca ha corrido (M6 de Phase 1, extendida a Phase 3 en `docs/TECH_DEBT.md`) — **no se declara CI verde**. **Nota (2026-11-18):** Phase 6 (aceptación E2E) queda **LISTA para planificarse**; **Phase 6.5 (wizard flujo destino, H5-H11) AÑADIDA 2026-11-18 y queda GATED / no ejecutable** hasta que ADR-014/015 pasen a Accepted y las deps (maturin/PyPI, librería TUI) estén aprobadas — los ADR-014/015 y las enmiendas de spec están hoy en Proposed.

## 2. Phase Breakdown

### Phase 0 — Foundations (esta entrega)

* Entregables: SPEC.md + 8 specs modulares + 8 ADRs + docs núcleo (ARCHITECTURE/PRD/TRD/APPFLOW/CODE_STYLE/SECURITY/TECH_DEBT/WORKFLOW) + AGENTS.md. (8 specs desde la ola del blueprint specs/spec-payload-vault.md.)
* Dependencias: docs/BACKLOG.md (fuente de verdad; cambios en §8 + ADR/enmienda si es decisión). Métricas: checklist de quality-bar del set. Gate: revisión y aprobación humana del usuario (status → Approved en SPEC.md index).
* Nota (rev. 2): las olas D7 (ADR-007), D8 (ADR-008) y D9 (trays/propiedad — sin ADR, por decisión explícita del usuario) conformaron estas specs post-Phase-0; decisiones tomadas 2026-10-21 y registradas en §8 Change Control.

### Phase 1 — Engine + Flow

* **Estado (2026-10-23): COMPLETADA.** Gate de cierre verde: `just ci` (**164 passed**; smoke Δ **991 ms** < 10 000 ms), `just coverage` **98 %** (`fail_under=95`), mypy strict y ruff dentro del pipeline; revisión multi-eje (5 ejes) cerrada con **24 hallazgos aplicados en 16 commits**. Estas cifras de cierre **sustituyen** a las intermedias T10/T11 de las métricas de abajo (137 passed, smoke Δ 1 757 ms), que se conservan como registro histórico. Pendiente del usuario (**NO hecho**): **push de la rama** — ~29 commits sin publicar; el workflow de GitHub Actions sigue sin haber corrido (M6).
* Objetivo: `.tepochcalli/flow/` funcional (source localfs `00-resources/**` → Docling/md → RecursiveSplitter(1536/192 bytes) → MiniLM → LanceDB ANN+FTS).
* Tareas clave: pipeline declarativo con `@coco.fn(memo=True)`; exclusión de rutas-punto y >100MB; campo `model` en filas; lockfile pineado; benches de Δ.
* Dependencias: Phase 0; decisión abierta de spec-embeddings (env SBERT_HOME) se resuelve aquí.
* Métricas de cierre — **medidas** (T10/T11, 2026-10-22/23; ninguna estimación aquí):
  * **M1 — Δ p95 < 30 s: PASS con margen 5×.** p95 = **5 385 / 5 466 / 5 952 ms** en 3 corridas (gate 30 000 ms; variación ≤10 %). Percentil **nearest-rank** sobre n=20 (el 19.º valor ordenado). Protocolo TRD §6.2: corpus determinista de 50 md/txt (seed 20261022) en un vault temporal, 20 ciclos sobre una rampa 1→50, cronómetro `RefreshReport.elapsed_ms` (monótono; incluye lock + update). Host observado: Intel i7-8750H 6C/12T, 15,8 GiB RAM, zram swap de 7 913 MB **sin presión** durante las corridas (muestreo cada 250 ms), vault en btrfs/NVMe, CPython 3.12.14. **Desviación declarada:** es el host de desarrollo de Phase 1, no la VM de referencia de TRD §6. **Salvedad honesta:** la indexación *inicial fría* varió mucho más — 34 227 / 33 358 / **70 694 ms** —; queda fuera del presupuesto por el protocolo, pero se reporta.
  * **M2 — metadatos de cita al 100 %.** Todas las filas llevan `source_path`, `char_start`, `char_end` y `doc_kind` no nulos, y `heading` presente; `heading` es **nullable (D13)** — `null` cuando el documento no tiene heading padre. Verificado fila por fila re-sliceando desde disco (5/5).
  * **M3 — cero llamadas a LLM durante la indexación**, probado dos vías: (a) ningún `litellm`/`openai`/`anthropic` presente en `sys.modules`; (b) `update_blocking()` completado con el `socket.connect` saliente bloqueado (AF_INET/AF_INET6) y **cero intentos de egress** registrados por un canario.
  * Métricas de apoyo: **M4** — filas queryables con `{source_path, heading, char_start, char_end}` vía el verificador CLI, cuyo carácter de solo lectura está probado por snapshot de `(mtime_ns, size)`. **M5** — coste de PDF **medido**: 30 páginas = **49–51 s** en caliente (≈1,6–1,7 s/pág), RSS pico **2 048–2 189 MiB**; en frío la carga de modelos de Docling domina (**29–37 s**) — por encima de la estimación de spec-rag-engine (TD-2 actualizado). **M6** — CI con **solo verificación local**: `.github/workflows/phase1.yml` existe, actionlint v1.7.9 + shellcheck con 0 errores, y los 7 pasos ejecutados localmente en el mismo orden y directorios; suite **137 passed**, smoke Δ 1 757 ms < 60 000 ms. **El workflow nunca ha corrido en GitHub Actions** — decisión del usuario 2026-10-23 de no publicar los 27 commits en un repo público; no se declara CI verde.
  * Contexto operativo: Δ de refresh típico **58–178 ms**; suite completa **~180–250 s** (137 passed, 1 deselected, 1 warning esperada = TD-9).
* Gate: fixtures de spec-rag-engine §Testing verdes **en verificación local** (M6 sin correr en Actions — salvedad arriba) + FTR Phase 0→1 (§4) ejecutado en T12. **M7** (sign-off del usuario para arrancar Phase 2): **concedido el 2026-10-23** — Phase 1 queda cerrada (estado arriba) y Phase 2 habilitada para planeación.
* **Nota de vigencia (2026-11-03, Phase 3.5):** el motor de esta fase **cambió** — Docling salió del venv y la extracción de documentos pasó a **markitdown** (ADR-011). Las cifras M1/M5 de arriba quedan como **registro histórico** de Phase 1; las re-medidas con el motor actual están en §Phase 3.5 (M11): **Δ texto p95 4 299 ms**, índice en frío 34 061 ms, RSS `VmHWM` 1 486 MiB (texto) / 1 601 MiB (documentos), 2 486 ms los 15 documentos. El coste de un PDF de 30 páginas con markitdown sigue **sin medir** (TD-2).

### Phase 2 — MCP Server

* **Estado (2026-10-28): COMPLETADA.** T1-T10 ejecutados; CP-A (5/5), CP-B (5/5) y CP-C (5/5) aprobados, CP-D (6/6) cerrado con el FTR; **FTR Phase 2→3 verde y aprobado 2026-10-27** (§4). Rito de calidad posterior: `/code-simplification` (veredicto «nada que simplificar») + `/code-review` multieje (5 ejes) → **9 fixes atómicos** (`d68f978`..`b21e6af`) y deuda CR-1..CR-8 en [TECH_DEBT.md](TECH_DEBT.md). Gate final **`just ci` verde 2026-10-28** con cobertura **98 %** (§M8). Al cierre de T10 el gate local ya era verde con **404 tests** (cifra histórica; la del cierre definitivo está en M8). Aviso de homonimia heredado: esta «Phase 2» es la del plan por fases del **producto**; no confundirla con la «fase 2: TDD» interna de los comandos `/test`, trabajo ya entregado dentro de Phase 1 (pirámide unit/integration/e2e).
* Objetivo: `.tepochcalli/mcp/` con las 4 tools `search/index_refresh/add_source/rag_status` según spec-mcp-server (shapes JSON, taxonomía `E_*`, presupuestos) — **cumplido**: paquete `tepochcalli_mcp` (server stdio + `tools/`), sin importar `cocoindex`/`lancedb` (lee por el puerto `ChunkReader` de Phase 1). *(Histórico de Phase 2: hoy el server registra **7 tools** — ver §Phase 3.5.)*
* Tareas clave: handlers + validación de borde; token-budget determinista; medición `took_ms`; `add_source` integrado con markitdown-venv (biblioteca **en proceso**); entrypoint **`python -m tepochcalli_mcp`** (D17, no console script); contract tests D7.3: `rag_status` con shape exacto de los 4 bloques y <200 tokens; los cinco códigos `E_*` con payload `{error:{code,message,fix_hint}}`.
* Dependencias: Phase 1 (tabla de datos estable).
* Métricas de cierre — **medidas** (T7-T9, 2026-10-26/27; ninguna estimación). Percentil **nearest-rank** en todos los casos: `sorted[ceil(p·n) − 1]` — con n=20, el p95 es el **19.º valor ordenado**:

  | Métrica | Valor medido | Cota | Cómo se midió |
  | --- | --- | --- | --- |
  | **M1** — harness lista las tools | `opencode mcp list` ⇒ `tepochcalli-rag` **connected** + `markitdown` **connected**; log del harness ⇒ `tools=4`; **control** desde la raíz del repo ⇒ no listado (las entradas viven solo en el payload) *(histórico: hoy son 7 tools y `markitdown` ya no es server)* | las 4 tools visibles | Verificado en T9 (tres frentes) y re-verificado por el orquestador |
  | **M2** — `search` latencia | **p95 = 52 ms** (cliente stdio) / **49 ms** (`took_ms`, punto de medición de la spec) | <500 ms | n=20, nearest-rank → 19.º valor; **20 muestras crudas publicadas** en el JSON del bench; host de desarrollo declarado |
  | **M3** — payload tokens | fórmula de la spec ⇒ **1590** (≤1600 ✅); JSON literal **≈1740** (+150 de envoltura que la fórmula no contabiliza) | ≤1600 (fórmula) | Fixtures adversas (CJK/emoji, 10 000+ chars, chunk 1536 bytes, PDF con tablas, multibyte). **Decisión del usuario 2026-10-26: manda la fórmula** (F-T7-1); cota de **envoltura ≤200 con test**; BACKLOG.md (<2000 con contexto) se cumple ≈1840 |
  | **M4** — taxonomía `E_*` | **5 códigos** + precedencia `E_NO_EMBEDDER` > `INDEX_EMPTY` > `E_MODEL_MISMATCH` > `E_API_AUTH` | contract D7.3 | `tests/e2e/test_mcp_contract.py` (en el wire) + tests unit |
  | **M5** — `rag_status` | 4 bloques exactos, **<200 tokens** | <200 tokens | contract test |
  | **M6** — instalación degradada | `search` = `E_NO_EMBEDDER`; `rag_status` = `degraded` + `fix_hint` | salida 5 de D7.1 | `test_mcp_contract.py::…degradada` |
  | **M7** — e2e grabado | `tests/fixtures/golden_vault/` (md+PDF), offsets reproducibles; `offsets_ref == "extract"` en PDF | fixture en repo | `tests/e2e/test_mcp_journey.py` |
  | **M8** — gate | **436 tests recogidos** (de 438; `-m "not slow" --collect-only` — la suite completa no cerró en el tiempo asignado a esta revisión), `just ci` verde **local** medido 2026-10-28, cobertura **98 %** ≥ gate 95, bench-smoke **Δ 976 ms < 10 000 ms PASS**; GitHub Actions **NUNCA ha corrido** (M6 de Phase 1, sin cambio) — **no se declara CI verde** | gate local | gate final del cierre de Phase 2 (2026-10-28) |

  * Presupuesto por etapa **medido** (T7, en las costuras del server): embed **24.7 ms** (medición directa) · ANN+FTS **14.6 ms** (por diferencia) · ensamblado **1.9 ms** · IPC **4.0 ms** — todos bajo sus cotas (120/200/30/150 ms). El desglose interno de LanceDB **no se mide** porque exigiría instrumentar `flow/` (documentado en F-T7-3): no se presenta aproximación como medición directa.
* Gate: e2e "pregunta → tool-call → JSON citado" **grabado como fixture y verde** (M7 ✅) + contract tests D7.3 (M4-M6 ✅) + **FTR Phase 2→3** (§4) — **ejecutado 2026-10-27 con checklist verde y aprobación de usuario concedida (§4): gate de fase EJECUTADO Y EN VERDE**, Phase 3 liberada.

### Phase 3 — Wizard

* **Estado (2026-10-28): COMPLETADA.** T1-T20 ejecutados; CP-A (6/6), CP-B (6/6), CP-C (6/6) y CP-D (6/6) cerrados con el FTR; **FTR Phase 3→4 verde y aprobado 2026-10-28** (§4). T19 entrega el asset del payload + regla one-version; T20 cierra la documentación (APPFLOW journeys d/e/f, TECH_DEBT, CHANGELOG, spec → Approved). Cierre posterior: revisión formal de 5 ejes sobre el crate entero 2026-10-29 (§4, punto 4) — 311 passed / 0 failed / 2 ignored.
* Entregado: crate Rust `tepochcalli` + cargo-dist (ADR-003) ejecutando las 8 fases atómicas con rollback/`--resume`/`--offline`/`--skip-model` — el menú embedder es la fase 6 (no añade una 9ª fase; spec-installer-wizard §Fases). Semántica `--skip-model` = salida-5 degraded (ADR-007 D7.1-5), NO `INDEX_EMPTY`.
* Objetivo: crate Rust `tepochcalli` + cargo-dist (ADR-003) ejecutando las 8 fases atómicas con rollback/`--resume`/`--offline`/`--skip-model` — el menú embedder es la fase 6 (no añade una 9ª fase; spec-installer-wizard §Fases). Semántica `--skip-model` = salida-5 degraded (ADR-007 D7.1-5), NO `INDEX_EMPTY`.
* Tareas clave: fases con execute/compensate; merge conservador de `opencode.json` con `.bak`; UX TUI; matriz CI multi-OS; release `v*` de prueba; paso Embedding provider D7.1 (5 salidas, default `paraphrase-multilingual-MiniLM-L12-v2` preseleccionado); `presets.toml` embebido vía `include_str!` (D7.2); portero test-embed con RSS medido para todo camino local (D8.1); detección de host `sysinfo` + probe `nvidia-smi`/`rocm-smi` con badges `recommended`/`viable`/`no recomendado` (D8.2; fixture: host 4GB → fila `BAAI/bge-m3` badge `no recomendado` PERO seleccionable — warn-never-block D8.3); flujo degraded salida-5 (instalación COMPLETA sin fase 7 + checklist de re-entrada); swap atómico D8.4 (`tepochcalli config embedder` / `tepochcalli reindex --confirm` / `--keep-previous` / auto-GC del modelo viejo; fracaso inducido → cero cambio de estado). **Nota:** el merge conservador de `opencode.json` **NO debe copiar la entrada `markitdown` standalone** (retirada del payload en `ee26073`; la conversión es en proceso vía `add_source`, [spec-markitdown](../specs/spec-markitdown.md) §Config) — política reforzada por `tests/unit/test_opencode_payload_registration.py`.
* Dependencias: Phase 1+2 estables (el wizard los invoca); payload base de Phase 5 puede solaparse; el blueprint de Phase 4 (diseño) corre en paralelo sin depender del wizard.
* Métricas: VM limpia → instalado en 1 comando; fallo inducido en cada fase → compensación correcta; 2 corridas → sin duplicados; VM limpia con salida-5 → vault completo + RAG degraded + checklist re-entrada; swap fixture: índice viejo servable durante reindex; modelo viejo purgado solo tras éxito.
* Gate: FTR Phase 3→4 **ejecutado 2026-10-28 con checklist verde y aprobación de usuario concedida (§4): gate de fase EJECUTADO Y EN VERDE**, Phase 4 liberada. Salvedad honesta: la release tag de test con assets y el `install.sh` en las 3 plataformas **no se ejecutaron** (M6/D-b/F-T20 en `docs/TECH_DEBT.md`) — el gate aprueba lo implementado y testeado en local, no lo desplegado.

### Phase 3.5 — Conversor summary-only + skill `tepochcalli-mcp` (H1-H4)

* **Estado (2026-11-03): CERRADA — FTR aprobado.** T1-T16 ejecutados; CP-A, CP-B, CP-C, CP-D,
  CP-E y CP-F cerrados; plan y detalle en el commit `5064a26` (D-P4-5: `tasks/plan.md` y
  `tasks/todo.md` fueron sobrescritos por `391216d`, así que el contenido previo vive solo en git —
  las referencias «tasks/plan.md §2» de §8 y de `docs/TECH_DEBT.md`
  apuntan a ese contenido histórico, no al fichero actual). Contratos en **ADR-009** (conversor summary-only),
  **ADR-010** (índice multi-raíz + cita vault-relativa) y **ADR-011** (dos librerías + ledger de
  no-reinvención), **Accepted 2026-11-03**; `spec-markitdown`, `spec-mcp-server`, `spec-rag-engine`
  y `spec-vault-structure` enmendadas y definitivas.
  Nace del diagnóstico `docs/diagnosis/fix01-conversor-satura-contexto-llm.md` (saturación de la
  ventana de contexto: el MCP standalone `markitdown` devolvía el documento íntegro al LLM; una
  herramienta jamás devuelve el artefacto convertido, solo el resumen de su operación). Se ubica
  ENTRE Phase 3 y Phase 4 sin renumerar fases.
* Entregado: **7 tools** en `tepochcalli-rag` (las 4 del contrato + `convert_document`,
  `convert_base64`, `list_formats`); **índice multi-raíz** declarado en `INDEXER_DIR`
  (`index_refresh()` sin argumentos, `source_path` relativo al vault); **RAG de documentos** nativo
  (pdf/docx/pptx/xlsx/xls vía markitdown, sin Docling); **dieta** de dependencias (dos librerías,
  extras granulares); y la skill **`tepochcalli-mcp`** en el payload (catálogo único de decisión,
  7 tools + fallback `anydoc`).
* Métricas de cierre — **medidas** (T12/T13/T16, 2026-11-02/03; ninguna estimación). Host:
  Intel i7-8750H 6C/12T, 15,5 GiB RAM, btrfs/NVMe, CPython 3.12.14 — **host de desarrollo, no la
  VM de referencia de TRD §6**. Percentil **nearest-rank** (`sorted[ceil(p·n)−1]`; con n=20 el p95
  es el 19.º valor ordenado).

  | Métrica | Valor medido | Cómo se midió (n/método) |
  | --- | --- | --- |
  | **M1** — 3 tools del conversor registradas y operativas | **7 tools en el wire**; `opencode mcp list` ⇒ 7 (T11) | cliente stdio real + contract tests e2e (`tests/e2e/test_mcp_contract.py`) |
  | **M2** — ninguna tool devuelve el artefacto | cuerpos fuera del wire; test nuclear con documento ≥100 000 chars y marca única | test transversal sobre las 7 tools (falla si alguien devuelve el Markdown; comprobado rompiéndolo y revirtiendo) |
  | **M3** — presupuesto del resumen | `preview` ≤500 chars; respuesta ≤1 400 chars (≈200 tokens ES/EN); bulk: **665 chars** en el wire | estimador de `budget` + fixtures ES/EN/CJK |
  | **M4** — frontera B′ | entrada **y** salida dentro del vault; fuera ⇒ `VALIDATION_ERROR` | negativos de `paths`/`validate_roots` en unit, integración y e2e |
  | **M5** — índice multi-raíz | recursión a cualquier profundidad; raíz-fichero; dedup de solapadas; `source_path` vault-relativo; conjunto declarado en `INDEXER_DIR` (fallback `00-resources/`) | integración sobre `tempfile` + e2e |
  | **M6** — RAG de documentos | `.pdf/.docx/.pptx/.xlsx/.xls` indexados en su forma original, `doc_kind` propio, `offsets_ref="extract"` | integración con fixtures reales; PDF **sin** `heading` (afirmado, D54) |
  | **M7** — un solo embedder | write y read resuelven **el mismo path** resuelto del snapshot | test de `Path.resolve()` (D59) |
  | **M8** — change detection real | editar parser o troceo **invalida** el índice | test rojo si se quita un `@coco.fn` (D58) |
  | **M9** — dieta | venv **1,921 GiB** (`du -sb` 2 063 018 440 B; `du -sh` 2.1G) · **135 paquetes** (antes 184) · lock **193 → 140** entradas; `uv sync --frozen` verde; `docling`/`torchvision`/`markitdown-mcp` fuera | `du -sb`/`du -sh` sobre el venv canónico (`venv/`, no el `.venv/` paralelo) + `grep -c "name = " uv.lock` |
  | **M10** — e2e bulk | 1 000 páginas · 1 293 373 B de entrada · conversión **218 ms** · **665 chars** en el wire · cuerpo de **1,26 MB** en disco | fixture sintético + 21 conversiones, test `slow` (sin aserción de latencia) |
  | **M11** — motor re-medido | **Δ texto p95 = 4 299 ms** (n=20, nearest-rank 19.º; corpus 50 md/txt; raíces múltiples) — Phase 1: 5 385/5 466/5 952 ms · índice en frío **34 061 ms** (Phase 1: 34 227/33 358/70 694) · documentos **2 486 ms los 15 docs** (≈166 ms/doc; Δ de un `.docx` = **824 ms**) · RSS `VmHWM` texto **1 486 MiB** / documentos **1 601 MiB** (Phase 1 con Docling: 2 048–2 189 MiB) | `bench_delta.py`, 20 ciclos sobre rampa 1→50; `RefreshReport.elapsed_ms` (monótono, incluye lock + update); documentos medidos **aparte** (D51) |
  | **M12** — payload | sin `mcp.servers.markitdown`; `anydoc` sigue `disabled: true`; test de merge verde | `tests/unit/test_opencode_payload_registration.py` — **caveat TD-30**: el fixture está rebasado y compara el payload consigo mismo |
  | **M13** — skill | `SKILL.md` con las 7 tools, tabla de decisión, defaults, errores y fallback `anydoc` | frontmatter válido + catálogo contrastado contra `server.py` |
  | **M14** — contratos y gate | ADR-009/010/011 + 4 specs enmendadas; `just ci` local: **703 passed + 3 `slow`** al cierre definitivo **2026-11-04** (619 en T16, 650 tras los añadidos post-plan, 670 tras la auditoría de cobertura, 703 tras el review 5-ejes post-FTR), cobertura **97 %** (gate 95 %), bench-smoke **PASS**, rust-ci **ok** | suite + `just coverage`; GitHub Actions **nunca** ejecutada (M6) |
  | **M15** — FTR | **cumplido 2026-11-03**: ADR-009/010/011 *Accepted* y las 4 specs enmendadas definitivas (`spec-vault-structure` → Approved) | esta sección + registro de lo no verificado |

* **Lo NO verificado** (registro explícito):
  1. **CI**: `.github/workflows/*` nunca ha corrido en GitHub Actions (M6, heredado de Phase 1);
     no se declara CI verde. `just ci` es verde **local**.
  2. **Suite `slow`**: los 3 tests `slow` (incluye el bulk de 1 000 páginas) no están en los 670;
     se corren con `just python-test-slow`.
  3. **Coste de un PDF de 30 páginas con markitdown**: **no medido**. La cifra de Docling
     (49–51 s/30 págs, 2 048–2 189 MiB) queda como histórico y no se extrapola (TD-2).
  4. **Windows**: sin probar (D-b de Phase 3 sigue abierto).
  5. **Release**: no hay release publicada ni installers generados (M6 heredado).
  6. **Instalación completa en VM limpia con el lock nuevo**: no re-ejecutada en esta fase; solo
     `uv sync --frozen` + import-check dentro del venv.
  7. **Fixture de merge**: rebasado; el test no demuestra un merge sintético (TD-30).
  8. **FTR**: **cerrado 2026-11-03** — ADR-009/010/011 *Accepted* y las 4 specs definitivas; el
     resto de esta lista sigue abierto.

* **Añadidos post-plan (2026-11-03)** — hechos fuera de los 16 calpullis, antes del FTR:
  1. **`INDEXER_DIR` multi-valor por comas y `TEPOCHCALLI_TOP_K`** declarados en
     `opencode.json` → `environment`: el default de raíces de `index_refresh()` pasa a ser la env
     (`00-resources` queda como fallback) — ADR-010 §4.1 enmendado antes del FTR.
  2. La sección **`[search]` del `tepochcalli.toml` queda jubilada**: `top_k` se declara en
     `environment`; un toml viejo solo recibe el aviso de sección desconocida.
  3. **F8 del wizard conserva las claves de `environment` que no gestiona** (antes las borraba al
     reinstalar): impone solo `TEPOCHCALLI_ROOT`.
  4. **`rag_status.config` gana `problems` y `unknown_env`**, y `valid` pasa a medir coherencia de
     la configuración, no solo que el toml parsee.
  5. **`index_refresh` pierde `directories`** (orden del dueño, 2026-11-03): el conjunto de raíces
     es exclusivamente `INDEXER_DIR` y el MCP no puede añadir ni quitar raíces — una pasada declara
     el estado completo del índice, así que aceptar un subconjunto purgaría las filas de las demás.
     `add_source` rechaza con `VALIDATION_ERROR` (`details: {requested, allowed, hint}`) si
     `00-resources` no está declarada, **antes de escribir**. **ADR-010 se editó en sitio** (rev. 2)
     por decisión explícita del dueño, sin crear ADR-012.
  6. **Auditoría de cobertura de Phase 3.5 (2026-11-03)**: 6 huecos clasificados y cerrados —
     guard estático de seams del probe F8 + salto ruidoso del loopback; gate de `add_source`
     **en wire**; catálogo de la skill `tepochcalli-mcp` == 7 tools; `TEPOCHCALLI_TOP_K` fuera
     de `[1,20]` ⇒ 5 + `problems` (bug real: rompía toda `search` por defecto); `unknown_env`
     positivo en wire; límites de `suggestions.py`. `just ci` verde (97 %), suite **670 + 3
     `slow`**. Commits `95082be`/`92efc16`/`f4a399c`.
  7. **Review 5-ejes post-FTR (2026-11-03, orden del dueño)**: W-01…W-13 aplicados
     (validación de raíces en `add_source` antes de escribir —W-01—, guard SSRF por hop del
     prefetch del conversor con cap de bytes y timeout —W-02—, null byte en `paths` ⇒
     `VALIDATION_ERROR` —W-03—, redacción de credenciales completa —W-04/W-05—, `format` =
     sufijo del destino + pista de conversión `extension_hint` —W-06, rev. en ADR-009 §D38 y
     spec-markitdown—, hangul/dingbats/banderas en el estimador —W-07—, topes de `data` y
     `path_filter` —W-08—, heading con tope 200 y en el budget —W-09—, `serialize_budget`
     solo en éxito —W-10—, alternativo usable en `writer` —W-11—, `backend_factory` fuera del
     event loop —W-12— y `convert`/`mcp.*` en el test de arquitectura —W-13—). Tres
     hallazgos quedan FUERA de alcance y en `docs/TECH_DEBT.md` §Review 5-ejes Phase 3.5.
  8. **Cierre 2026-11-04 (orden del dueño):** el review 5-ejes post-FTR aterriza en 6 commits
   (`e191a45`, `876a215`, `a149fc7`, `a5ce99e`, `f904458`, `6e00aa9`) y `ad7575c` lleva los
   plugins del payload a **@latest** para seguir al harness — **revierte los pins de R-04**.
   Gate final verde en local: **703 passed + 3 `slow`**, cobertura **97 %** (gate 95 %),
   bench-smoke **PASS**, rust-ci **ok**. Baseline de escala registrado en
   `docs/TECH_DEBT.md` §Review 5-ejes Phase 3.5 (P-02: btrfs PASS 26 967 ms, NTFS-3G FAIL
   39 501 ms) — queda para Phase 6.

### Phase 4 — Diseño del agent workflow (blueprint)

* **Estado (2026-11-09): COMPLETADA — BLUEPRINT APPROVED concedido por congelamiento del dueño (40 definitivas, `cf17f31`/`2e62e60`).** Diseño
  puro: `obsidian-workspace/` intacto (`git diff --stat -- obsidian-workspace` **vacío**; sin commits
  de payload). El blueprint quedó en **5 specs** — `spec-payload-vault` (366 líneas, spec padre),
  `spec-payload-skills` (226), `spec-payload-permissions` (408), `spec-payload-agents` (443),
  `spec-payload-commands` (476) — todas <500 y hoy **Approved**; `spec-agent-workflow` (231)
  sigue en Proposed. Verificado sobre el inventario real: **209 skills · 170 agentes · 9 comandos** (2026-11-04; SUPERSEDED 2026-11-09 por el congelado de 40),
  **0 skills/subagentes inventados**; cuerpos de los 5 agentes 56/54/58/58/56 líneas, 9 comandos
  24-30 líneas, `AGENTS.md` del vault (blueprint) 67 líneas — todo en inglés (D-P4-6) y
  dentro de los techos de la spec. **92 links relativos** entre las 6 specs: **0 rotos**; markdownlint
  **0 errores** (se pagó el único MD005 del baseline); ningún bloque mermaid añadido en la fase. **Congelado 2026-11-09: 40 skills definitivas** — el
  objetivo <60 CUMPLIDO (40<60, congelado del dueño 2026-11-09); la matriz de 17 filas queda SUPERSEDED y Phase 5 solo verifica presencia. Por decisión del dueño (2026-11-04) **no se ejecuta ningún corte**:
  revisará manualmente cada skill del payload (D-P4-10 retirada). **D-P4-9**: CP-A se leyó sobre las specs existentes en ese momento;
  **D-P4-11**: los permisos se extrajeron a la 5.ª spec para respetar <500.
  **Gate concedido 2026-11-09 por congelamiento del dueño (§4); Phase 5 queda READY TO PLAN (plan vía `/plan`), sin ejecución en esta ola.**
* Objetivo (contenido entregado en las 5 specs; *Approved* es el gate, no el entregable): completar el blueprint hasta estado **Approved**: system
  prompts definitivos de los 5 agentes, bloques YAML de permisos (last-match-wins), templates
  determinísticos de los 9 comandos. AGENDA: (i) §Tabla de invocación por comando — 9 filas × 4 columnas {skills concretas del inventario real, herramientas nativas, MCPs a ejecutar (`tepochcalli-rag` tools por comando, incluidas las 3 del conversor; `anydoc` solo como fallback disabled), subagentes permitidos}; (ii) §Matriz de conflictos/redundancias de skills contra el inventario REAL de `obsidian-workspace/.opencode/skills/` (lectura only) — entregada con **17 filas** que cubren el 100 % del inventario.
* Naturaleza: **documentación pura — cero escritura de payload**. `obsidian-workspace/` sigue vedado; la prohibición es un deliverable verbal de esta fase, no código.
* Dependencias: Phase 0 (contratos D9); puede correr en paralelo a Phases 1-3 (no los necesita — los contratos MCP ya están Accepted).
* Métricas (medidas en el FTR del 2026-11-04; SUPERSEDED 2026-11-09 por el congelado de 40): la matriz cubría el 100% del inventario entonces (recuento `ls` vs filas ⇒ **17 filas / 209 skills**); cada skill referenciada en la tabla existe o está marcada GAP; cero skills/subagents inventados; permisos YAML sin campos legacy V2.
* **Gate: BLUEPRINT APPROVED — CONCEDIDO 2026-11-09 por congelamiento del dueño** (status de las 5 specs del payload → Approved en el
  índice de SPEC.md y en sus cabeceras). Checklist verde 2026-11-04 + freeze 40 (`cf17f31`/`2e62e60`) (§4).
  Phase 5 queda READY TO PLAN (plan vía `/plan`); su ejecución requiere su propio plan.

### Phase 5 — Payload + Skills audit (ejecución)

* **Estado (2026-11-09): COMPLETADA — con salvedad D-P5-10.** Ejecución literal del blueprint Approved
  en las olas T0-T13 (commits `f3a0a7c` plan y `06925ca`..`eeb62b6`): payload materializado y gates de
  la fase corridos en local. **La corrida D9 (methodology e2e de los 9 comandos) NO se ejecutó** —
  decisión del dueño (**D-P5-10**) de diferirla al **QA de cierre de proyecto**; se entrega el runbook
  `tests/phase5-methodology-runbook.md` como mitigación y el FTR Phase 5→6 la registra como **no
  ejecutada**, nunca como verde. Deuda de QA: TD-31.
* **Métricas medidas (2026-11-09, ninguna estimación):**
  * **Skills:** **40 dirs / 687 ficheros**, hash del árbol
    `169fe2c99fd58c71566342b076afd9098ae19dd13222ced96634963d617fc398` **idéntico al baseline T0** —
    0 altas, 0 bajas, 0 ediciones.
  * **5 agentes:** reglas `permissions` **16/18/17/18/27**
    (itzamna/nezahualcoyotl/pochteca/chilam/tlacuilo); cuerpos **55/53/57/57/55** líneas (≤60);
    0 campos legacy, 0 `model`, markdownlint 0.
  * **9 comandos:** **24/30/26/24/24/24/24/25/24** líneas (≤35), byte-idénticos a
    `spec-payload-commands.md`; 0 `subtask`/`subagent:`/`` !`cmd` ``/`@paths`.
  * **`AGENTS.md` del vault:** **74 líneas**, 7 secciones; vocabulario (cita, 4 estados, 4 clases)
    verificado token a token.
  * **`opencode.json`:** array global de **313 reglas eliminado**; `instructions` = 4 rutas
    vault-relative resolubles; `default_agent: itzamna`; 5 agentes sin arrays de permisos;
    `mcp.servers` y `references` intactos.
  * **Scaffold:** `01-Tasks/` renombrada a `01-tasks/` (TD-8), 3 ficheros de 0 bytes eliminados,
    6 bandejas con `.gitkeep`, `.gitignore` del vault con 5 rutas.
  * **Gate estático (T11):** **42/42 probes**, 30 denies de secretos (5 agentes × 6 rutas),
    5 `subagent * deny`, 0 reglas muertas; contrato de 40 skills con hash; `just ci` verde,
    cobertura **97 %** (gate 95 %), `md-lint` 0.
  * **Install e2e (T12):** payload empaquetado con las exclusiones de `release.yml`;
    `install --non-interactive --skip-model` ×2 → exit 0; 5 agentes + 9 comandos + `AGENTS.md`
    instalados; F8 inyecta `tepochcalli-rag` (forma `python -m`); 2 muestras en `00-resources/`;
    `.gitignore` con 5 rutas; **idempotencia**: digest
    `ffa4db0e29ad6c20fdbb52db9e7ef4f959c7fe1dda5756d4df625b713eac0151` (**875 ficheros**)
    antes/después, 0 duplicados, 0 `.bak`. **Bug real corregido:** la 2.ª instalación fallaba en F5
    (`uv venv` sobre un venv existente y la compensación lo borraba) → `uv venv --clear` (venv
    derivado) + test RED→GREEN en `int_install_f4_f5.rs`.
* **Lo NO verificado (declarado, no verde):** corrida D9 de los 9 comandos (**D-P5-10**, diferida al
  QA de cierre con runbook entregado); GitHub Actions **nunca ha corrido** (M6); Windows/PowerShell;
  release/cargo-dist; suite `slow`.
* **Revisiones post-Phase 5 (2026-11-10/11, [ADR-012](adr/adr-012-formato-payload-revisado.md)):**
  9 commits del dueño fijan el formato canónico ongoing (`AGENTS.md` genérico, permisos inline +
  global 313 reglas, `00-resources/` + `10-templates/`, 41 skills). No reabren Phase 5: la corrida
  TD-31 corre contra el formato revisado.
* **Formato canónico ongoing (2026-11-12, 12 commits `2072121..c815eb0`):** el dueño endureció
  los 9 comandos — rubric (fases 0-2 entrevista+plan), research (Pre-Flight+cadena multi-fuente),
  validate (4 fases+tabla de severidad), synthesize (Pre-Flight de veredictos+outline diseñado),
  cite (inventario Rn+gate EN), draft (3 insumos+compilar), review (target+revA→B), transform
  (dispatcher A-G→`05-outputs` EN), update (quirúrgico+rev); `chilam.md` audita-y-corrige sin
  bandejas propias; `tepochcalli-mcp` generaliza `INDEXER_DIR` y retira `anydoc`;
  `database-lookup/` borrada (83 ficheros, cero refs en el payload, reemplazada por
  `osint-skills`+`literature-search-engine`+`websearch-engine`). Salvedad D-P5-10 intacta.
* **PHASE 5 COMPLETADA 2026-11-12; PHASE 6 (aceptación E2E) LISTA para planificarse**
  (runbook `tests/phase5-methodology-runbook.md`; TD-31 diferida al QA de cierre).
* Ejecución LITERAL del blueprint Approved de Phase 4: los archivos del payload se generan del spec-payload-vault Approved, **sin reinterpretación**; divergencia descubierta en vuelo = volver a Phase 4 (enmienda al blueprint), no parche ad-hoc.
* Objetivo: `obsidian-workspace/` listo como asset de release (mirror del modelo `template/` de codice-opencode): muestras en `00-resources/` (md+PDF, opcionalmente docx para TD de markitdown), `.gitignore` del vault, AGENTS.md del vault con reglas MCP-first, ejecución del saneamiento del Anexo A (spec-agent-workflow), scaffold alineado a la convención de carpetas con `04-review/` y `05-outputs/` creadas (Action Item spec-vault-structure), y validación explícita del agent workflow (D9, bloque abajo). Ejecución según blueprint [specs/spec-payload-vault.md](../specs/spec-payload-vault.md).
* Dependencias: Phase 2 (contratos) + Phase 3 (payload se instala con wizard) + Phase 4 (blueprint Approved).

#### Validación del agent workflow (D9 — gate explícito de Phase 5)

* **(a) Permission fixtures** (spec-agent-workflow §Testing D9.3, config `tools`/`permission` por agente verificada en fixtures OpenCode):
  * Pochteca: escritura permitida **solo** bajo `01-tasks/research/` y **denegada en todo lo demás** (root `01-tasks/`, `02-drafts/`, `03-citations/`, `04-review/`, `05-outputs/`, `00-resources/` y carpetas personales: denegadas); navegación web permitida — desviación documentada del UH, decisión usuario 2026-10-21.
  * Tlacuilo: sin web; escritura en sus bandejas `02-drafts/` y `05-outputs/` (mapa D9.2).
  * Chilam: lectura total; escritura limitada a registros de auditoría, bases de citas y notas de revisión — bandejas `03-citations/` y `04-review/` (mapa D9.2).
  * Itzamná: lectura/escritura de contexto (enruta, NO ejecuta el pipeline).
  * Nezahualcóyotl: escritura solo de planificación (rúbricas, esquemas) en `01-tasks/`; sin web ni redacción final.
* **(b) Methodology e2e (golden vault)**: corrida completa `/rubric → /research → /validate → /synthesize → /cite → /draft → /review → /transform → /update` assertando: cada artefacto aterriza en SU bandeja única (mapa D9.2); frontmatter `{agent, timestamp, fuentes, método}` en las notas de `01-tasks/research/` y `{command, agent, target_doc, verdict}` en los informes de `04-review/`; cero contaminación cruzada entre bandejas; regla MCP-first observada (`search` antes de lectura cruda de `00-resources/`); regla no-contaminación observada (el agente WARN si encuentra archivos depositados por el usuario dentro de las bandejas 01-05).

* Métricas: inventario final = **40 skills congeladas** (decisión del dueño 2026-11-09; objetivo <60 **cumplido**); Phase 5 verifica presencia (40 presentes, 0 retiros), no ejecuta cortes; acciones de gaps documentadas; alias `00-Resources` resuelto **2026-11-13**: canónico `00-resources/` en las tres capas (renombrar scaffold, nunca crear el alias; el wizard materializa el case de `INDEXER_DIR`); permission fixtures (a) verdes y methodology e2e (b) **diferida (D-P5-10)**.
* Gate: `install` sobre el payload final → golden vault e2e pasa; + permission fixtures D9.3 y methodology e2e (D9) verdes. **Salvedad 2026-11-09: la methodology e2e queda diferida (D-P5-10); el gate se cierra con permission fixtures estáticas + install e2e + runbook entregado, y la corrida D9 pasa al QA de cierre.**

### Phase 6 — E2E Acceptance (los 7 criterios)

* Objetivo: validación integral contra docs/BACKLOG.md sobre sistema instalado como lo tendría un usuario.
* Metodología: [docs/TRD.md](TRD.md) §6 (protocolos 30s/500ms/2000tok/10k-1k) + checklist de criterio 1 (no-interferencia, spec-vault-structure §Testing).
* Tabla §6.3 de salida (llenar en la corrida):

| Criterio BACKLOG.md | Test | Result |
| --- | --- | --- |
| 1. Sin interferencias | checklist Vault-OK post-instalación (0 puertos, `.obsidian/` intacto, UI limpia) | ☑ **PASS**: `.obsidian/` byte-idéntico (`sha256 751186fc…`, 2 ficheros), **0 puertos nuevos** (12 listeners antes y después, lista archivada), 0 basura oculta y vault válido, con `index_refresh` real (`scanned=1 indexed=1`) + `search` (1 cita). Origen: `just python-no-interference --evidence …` sobre vault instalado por `install --non-interactive --skip-model` + [no-interference.json](acceptance/no-interference.json) (T9) |
| 2. Δ <30s | bench `index_refresh` 20 corridas típicas | ☑ **PASS**: Δ p95 **15 695 ms** (n=20, nearest-rank 19.º) con el corpus de **11 000** entradas en btrfs/NVMe = **52 % del presupuesto de 30 s**, y **4 299 ms** p95 tocando 50 notas (Phase 3.5). Los documentos binarios van **aparte** (D51): un PDF de 335 págs tarda 108,5 s con indexación, y se publica como coste de ingesta, no como Δ de texto (T2). Origen: `just python-bench-scale-ratio --phase …` + [scale-ratio.json](acceptance/scale-ratio.json) (T5) y [documents.md](acceptance/documents.md) (T2) |
| 3. Búsqueda <500ms | bench `search` p95 sobre corpus 10k/1k | ☑ **p95 cliente 97 ms** / 94 ms server (n=100, nearest-rank 95.º, btrfs/NVMe, 11 006 chunks). Origen: `just python-bench-search-scale --phase …` + [search-scale.json](acceptance/search-scale.json) (T4) |
| 4. ≤2000 tokens/consulta | fixture adverso + medidor e2e del harness | ☑ **total 1 995 < 2 000** en el peor caso (`top_k=20`, 4 resultados) y 1 675 en la consulta dorada, con **tokenizador real** `cl100k_base` (tiktoken 0.14.0; `o200k_base` 1 785/1 536 al lado); **payload del server**: 1 600 por el estimador del contrato y **1 789** reales. Desglose: query + `content[0].text` + esqueleto mínimo de respuesta citada (`source_path » heading (chars x–y)`). Margen del peor caso: **5 tokens** (hallazgo F-T6-1). Origen: `just python-test-file token_budget` (n=7 caras del fixture adverso de T7) + [token-budget.json](acceptance/token-budget.json) (T6) |
| 5. Citas precisas | golden answers: 100% con `source_path`+`heading`+offsets reproducibles | ☑ **PASS**: spot-check **6/6 (100 %)**, 0 citas rotas, `exit 0`, con `source_path` real y offsets reproducibles; `offsets_ref` **`source`** en md/txt y **`extract`** en pdf (`heading` nulo, D54). El criterio **sabe fallar**: editar el fichero tras indexar ⇒ **3/6** y `exit 1`; borrarlo ⇒ `MISSING` y `exit 1`. Snapshot de `db/` antes/después ⇒ **0 cambios** (solo lectura). Origen: `python -m tepochcalli_flow.verify --spot-check` + [citations.json](acceptance/citations.json) (T7); TD-13 cerrada |
| 6. 10k notas + 1k PDFs | stress corpus + regresión de latencia vs 10% | ☑ **Δ p95 15 695 ms al 100 % vs 2 543 ms al 10 % ⇒ ratio 6,17× = FAIL de la cota 2×** (el 100 % sí cabe en 30 s al 52 %); **`search` p95 87 ms vs 51 ms ⇒ ratio 1,71× = PASS**; walk-only 6 115 ms (11 000) vs 555 ms (1 100). Límite: fuseblk/NTFS-3G **Δ p95 52 996 ms = FAIL** (walk 22 945 ms), no decide el criterio (D-P6-3). Origen: `just python-bench-scale-ratio --phase …` (n=20 Δ nearest-rank, n=100 search, btrfs/NVMe + fuseblk) + [scale-ratio.json](acceptance/scale-ratio.json) (T5); hallazgo en TD-36 |
| 7. Multi-formato | matriz conversión (docx/xlsx/html/url) → indexable | ☑ **8/9 celdas PASS medidas**: `md`/`txt` ⇒ `offsets_ref=source`; `pdf`/`docx`/`pptx`/`xlsx`/`xls` ⇒ `extract`, `heading` nulo (D54) y `source_path` = **el original**; `html` ⇒ el convertido **no** es citable y el artefacto `.md` lo es **solo tras `index_refresh`**. **GAP declarado, no simulado**: `url` (el host de tests corre sin egress y el guard SSRF rechaza loopback por diseño) y `.doc`/`.ppt`/PDF escaneado, con mensaje accionable. Origen: `tests/e2e/test_format_matrix.py` + [format-matrix.json](acceptance/format-matrix.json) (T8); matriz en [TRD.md](TRD.md) §6.3 |

**Gate adicional (no criterio UH)** — no forma parte de la tabla de 7 criterios de BACKLOG.md (no se renumeran ni se añade un "criterio 8"):

| Gate | Test | Result |
| --- | --- | --- |
| Methodology e2e (§Phase 5 Validación D9) completo en corpus golden | corrida `/rubric→/update` con bandeajes D9.2 + permission fixtures D9.3 + frontmatters assertados | ☐ |

* Dependencias: Phases 1-5 verdes. Métricas: tabla completa; TECH_DEBT re-revisado.
* Gate: **v1 release** (o rollback de phase con nota en este documento).

### Phase 6.5 — Wizard flujo destino (H5-H11)

* **Estado (2026-11-18): AÑADIDA — GATED, no ejecutable.** Ninguna tarea arranca sin el gate de ENTRADA, que exige las 4 precondiciones: (a) [ADR-014](adr/adr-014-distribucion-uvx-pypi.md) y [ADR-015](adr/adr-015-dispositivo-inferencia-wizard.md) pasar de Proposed a **Accepted** por aprobación del dueño; (b) `maturin`+PyPI y la librería TUI aprobados como deps (regla R1 / SPEC.md «preguntar antes»); (c) alinear `Cargo.toml` (0.1.0-beta.1) → `.tepochcalli/pyproject.toml` (0.1.0) por la one-version rule de ADR-014; (d) las enmiendas «Enmienda 2026-11-18 — flujo destino (Proposed)» de `spec-installer-wizard` y `spec-embeddings` en Accepted. Es fase intermedia POST-6 (misma convención que Phase 3.5): NO renumera Phase 6, que sigue siendo la aceptación E2E del producto v1. Con 0 releases publicadas (M6) no hay usuarios que migrar del canal viejo.
* Objetivo: materializar el flujo destino de `docs/BACKLOG.md §2 «Wizard de instalación: flujo destino (2026-11-18)»` (H5-H11 + anexo Codice→Rust), declarado por el dueño como DESTINO.
* Dependencias: Phase 3/3.5 (wizard base + menú embedder), Phase 5 (payload), [ADR-014](adr/adr-014-distribucion-uvx-pypi.md) (supera el canal de ADR-013 — `cargo binstall`— y DECLARA el retiro del backend de ADR-003 — cargo-dist: `dist.toml` + `release.yml`—; ADR-004 uv+venv intacto; versión canónica = `.tepochcalli/pyproject.toml`), [ADR-015](adr/adr-015-dispositivo-inferencia-wizard.md) (refino de ADR-007/008).
* Tareas clave (scope FUTURO — no implementación en esta ola):
  * **Empaquetado:** wheel en PyPI vía maturin `bindings = "bin"`; `uvx tepochcalli` como único canal; refresco con `uvx --refresh tepochcalli`. **Riesgo no verificado (registrar):** el smoke de TTY/interacción del TUI bajo `uvx` en Windows nunca se ha probado.
  * **TUI full-screen:** sustituir el `dialoguer` line-based (D23) por botones reales con estado deshabilitado + razón visible; máquina de estados del menú H5 con los 4 escenarios de versión (no instalado / == wizard / < wizard / > wizard → todos menos Exit ofrecen el comando `uvx --refresh tepochcalli`). Librería TUI (`ratatui` como *ejemplo*, NO fijado) pendiente de aprobación.
  * **Versión:** lector de `.tepochcalli/pyproject.toml` (canónica) + comparador semver en el dominio + detección instalada-vs-wizard + mensaje de refresco.
  * **Update (use-case NUEVO, inexistente hoy):** sobrescribe `.opencode/`, `.tepochcalli/`, `.gitignore`, `opencode.json`, `AGENTS.md` con backup `.bak` + advertencia — alineado con la regla byte-a-byte de [CODE_STYLE.md](CODE_STYLE.md) enmendada (excepción del dueño 2026-11-18); NO es un bug de F3, es scope nuevo.
  * **Desinstall:** alcance `.opencode/`, `.tepochcalli/`, `opencode.json` + backup/advertencia (amplía el uninstall actual, que solo borra `.tepochcalli/`).
  * **Embedder wizard (H9):** campo `device` en `Preset`; escribir `[embedding].device`; la re-entrada `config embedder` PRESERVA el valor existente (corrige el drift que hoy hardcodea cpu en `embedder_config.rs`/`swap.rs`); detección de hardware + badges de procedencia (`declarado`/`estimado`/`medido`); gate `test-embed` con ID libre de HF + `HF_TOKEN` opcional; API externa = endpoint preestablecido de LiteLLM derivado del prefijo de `model` (sin campo endpoint); GPU **no** autoselecciona (la autoselección en runtime sigue RECHAZADA, ADR-015).
  * **Anexo:** reorganización de módulos Codice→Rust (requisito de organización — BACKLOG.md §4 «Anexo — Mapeo de módulos de Codice a Rust», «requisito, no implementado» —, sin gate de contrato).
* Gate / FTR Phase 6.5: VM limpia (Linux/macOS/Windows) sin Python/Node ni binario propio — con `uv` como único prerequisito — → `uvx tepochcalli` abre el wizard; botones correctos en los 4 escenarios de H5; install/update/desinstall e2e con `.bak` verificado; detección de versión instalada vs wizard; smoke TTY real en las 3 SO. **Lo NO verificable hoy:** ADR-014/015 en Proposed, deps sin aprobación, TTY Windows sin probar, 0 releases publicadas (M6).

## 3. Testing Strategy per Phase

| Phase | Tool | Scope | Success |
| --- | --- | --- | --- |
| 1 | pytest + cocoindex runtime | flujo unit/integración | como §Phase 1 métricas |
| 2 | pytest + fixture vault | contracts MCP, presupuestos, contrato `rag_status` + códigos `E_*` | shapes + cotas duras assertadas |
| 3 | cargo test + VM matrix | fases/rollback/idempotencia, menú embedder paths 1-5, swap D8.4 | sin datos del usuario perdidos en fallo |
| 4 | ls + grep + revisión humana del blueprint | tabla de invocación 9×4 + matriz de conflictos contra el inventario real; permisos YAML V2 | BLUEPRINT APPROVED por el usuario |
| 5 | smoke e2e + permission fixtures + methodology e2e (D9) | payload instalado desde el blueprint Approved | golden vault consulta citada OK; bandejas/frontmatters D9.2 assertados; coherencia blueprint vs archivos generados |
| 6 | suite TRD §6 + manual | criterios 1-7 | toda la tabla verde |

Gate de tipos: `just typecheck` (`uv run python -m mypy`) desde la raíz, en modo
`strict`; corre en CI entre `ruff format --check` y `pytest` y su superficie tipada es `flow/`
en Phase 1 y **`flow/` + `mcp/` desde Phase 2** (`files = ["flow", "mcp"]` en el pyproject,
[CODE_STYLE.md](CODE_STYLE.md) §Herramientas y comandos).

### Cobertura

`just coverage` es la ÚNICA cifra honesta: instrumenta también los subprocesos (`refresh` y el CLI
`verify`), vía `sitecustomize` + `[tool.coverage.run] parallel`. `pytest --cov` a secas sub-mide
(`verify.py` 0 %, `app.py` 74 % → real medido: `verify.py` 98 %, `app.py` 93 %,
total 98 %). Gate: `fail_under = 95`; por debajo, la receta falla.

**Alcance desde Phase 2 (decisión del usuario 2026-10-27):** `source = ["tepochcalli_flow",
"tepochcalli_mcp"]`. Antes el gate medía **solo el motor**: los 1.760 LOC del server (`tools/*`,
`errors`, `paths`, `embedder`, `budget`, `server`) quedaban fuera de todo umbral, así que `just
coverage` podía seguir verde con el server entero sin ejercitar. Medición del cambio, sobre HEAD
`28afe26` con 404 tests: **TOTAL 98 %** (1374 stmts, 25 sin cubrir, 236 ramas) — extender el gate
no lo tumbó. Por paquete, `mcp/tepochcalli_mcp` entre 94 % (`tools/add_source.py`) y 100 %
(`errors.py`, `budget.py`, `tools/rag_status.py`).

**Tras cubrir los gaps de la fase** (rito `/test`, 2026-10-27; 414 tests): **TOTAL 99 %** (1376
stmts, 14 sin cubrir, 238 ramas) y `mcp/tepochcalli_mcp` al **100 % en 13 de sus 14 ficheros** —
el único por debajo es `__main__.py` (91 %, rama `24->exit`). Lo que queda fuera son líneas de
**Phase 1** (`refresh_lock` 83 %, `verify` 94 %, `source` 96 %, `app.py:383`), inventariadas como
Q-2 en [TECH_DEBT.md](TECH_DEBT.md).

**La cobertura es una medición local, no un gate:** `just coverage` corre la misma suite
instrumentada (~1 h) y se ejecuta al cierre de fase — decisión del dueño 2026-11-12, que la sacó
de `just ci` para que el gate de integración sea corrible siempre. `just ci` = `python-sync` +
`quality` + `bench-smoke` + `rust-ci`. Ciclo corto sin cobertura: `just quality`. **Coincide con
CI:** `.github/workflows/phase1.yml` **tampoco** ejecuta cobertura; GitHub Actions sigue sin
haber corrido (M6).

## 4. Formal Technical Reviews (FTRs)

| Gate | Artefacto | Checklist | Participantes |
| --- | --- | --- | --- |
| Phase 0→1 | specs/ + ADRs | consistencia D1-D9, links, mermaid | Usuario + arquitecto |
| Phase 2→3 | contratos vs código | shapes = spec-mcp-server | arquitecto |
| Phase 3→4 | wizard crate + docs de cierre | CP-A..D (6/6 cada uno) + FTR checklist + suite local | Usuario |
| Phase 4→5 | blueprint: 5 specs del payload (`spec-payload-vault` **Approved** + `skills`/`permissions`/`agents`/`commands`) | tabla invocación + matriz conflictos + permisos V2 sin legacy — **checklist verde 2026-11-04 + gate concedido 2026-11-09 (freeze 40)** | Usuario + arquitecto |
| Phase 5→6 | payload + skills | Anexo A acciones ejecutadas + permission fixtures + methodology e2e verdes + coherencia blueprint vs archivos generados — **checklist ejecutado 2026-11-09 con la salvedad "methodology e2e diferido (D-P5-10); runbook entregado"** | Usuario |
| Phase 6.5 (gate de entrada) | wizard destino H5-H11 | gate de entrada: ADR-014/015 Accepted + deps (maturin/PyPI, TUI) aprobadas + one-version alineada + enmiendas 2026-11-18 Accepted; luego e2e `uvx` en 3 SO | Usuario + arquitecto |

**FTR Phase 0→1 — ejecutado 2026-10-23 (T12), checklist verde** (corrido sobre `specs/`, `docs/`, `AGENTS.md` y `SPEC.md`):

* **Consistencia D1-D9:** rastreo de cada `Dn` en todos los documentos — sin acepciones contradictorias (rangos `D1-D8`/`D1-D9` y subdecisiones `D7.x`/`D9.x` coherentes con el mapeo de AGENTS.md; D3 se cita solo vía ADR-002, nunca de forma suelta; el «D4» de ADR-002 §riesgos es el piso de RAM del modelo default, coherente con D4). Cero conflictos ⇒ cero notas de mapeo nuevas.
* **Enlaces relativos:** 95 enlaces revisados — los 90 reales resuelven; los 5 que no resuelven son placeholders intencionales `](url)`/`](path)` de `docs/diagnosis/diagnosis-template.md` (plantilla a rellenar).
* **Mermaid:** los **12 bloques** de docs/specs/AGENTS/SPEC renderizados con `mermaid-cli` (headless Chrome) — **12 OK, 0 fallos**, incluido el diagrama de componentes nuevo; labels con caracteres especiales entre comillas.
* **Lint:** `markdownlint-cli2 docs specs AGENTS.md SPEC.md` → **420 antes / 420 después**, mismo conjunto de rule IDs (D12: cero errores nuevos).
* **Efecto del gate:** `spec-rag-engine.md` y `spec-embeddings.md` → **Approved** en el índice de [SPEC.md](../SPEC.md) (metadatos actualizados en ambos archivos). La aprobación de usuario del gate (**M7**) se pidió por separado tras T12 y se concedió el **2026-10-23** (Phase 1 completada; Phase 2 liberada para planeación).

**FTR Phase 2→3 — ejecutado 2026-10-27 (T10), checklist verde** (artefacto: contratos vs código; `shapes = spec-mcp-server`):

* **Los 4 contratos verificados en el wire** (`tests/e2e/test_mcp_contract.py`, proceso real por stdio con el cliente del SDK): orden de claves exacto por tool, los 7 campos de `search`, `{scanned,indexed,skipped,elapsed_ms,locked}` de `index_refresh`, `{ok,written_to,indexed}` con 4 sub-campos de `add_source`, los 4 bloques de `rag_status` <200 tokens, los **5 `E_*`** con `{code,message,fix_hint}` y su precedencia. `structured_content = None` **declarado** (hallazgo H6: los handlers `-> CallToolResult` son salida *unstructured*), y jamás texto libre — probado con **controles negativos observados** (orden invertido ⇒ falla; un byte de corrimiento en offsets ⇒ falla).
* **e2e «pregunta → tool-call → JSON citado»** con fixture **grabado** (`tests/fixtures/golden_vault/`, md+PDF): `source_path` real, `heading` y **offsets reproducibles** — slice del original == `text` en md, `offsets_ref == "extract"` en PDF (cierra el punto que CP-B dejó pendiente).
* **Métricas medidas con método** (§Phase 2, tabla M1-M8): p95 `search` **52 ms** (<500) con **n=20, nearest-rank `sorted[ceil(0.95·n)−1]` → 19.º valor** y 20 muestras crudas publicadas; presupuesto por etapa 24.7/14.6/1.9/4.0 ms (embed medido directo, el resto por diferencia — F-T7-3); tokens **1590 ≤1600** por la fórmula de la spec (JSON literal ~1740 con cota de envoltura ≤200; decisión del usuario 2026-10-26); **M1** en el harness real: `opencode mcp list` ⇒ `tepochcalli-rag` + `markitdown` **connected**, log ⇒ **`tools=4`**, control desde la raíz ⇒ no listado.
* **Gate local:** `just ci` verde en **404 tests**, Phase 1 intacta (y su bug de PDFs, F-T7-2, **arreglado en esta fase**). **GitHub Actions sigue sin haber corrido (M6) — no se declara CI verde.** `litellm` probado con **proveedor falso**: sin credenciales no hay llamada real, y así queda escrito.
* **Enmiendas cerradas en este gate** (autorizadas por el usuario el 2026-10-27): `spec-installer-wizard` §config (console script → `python -m`, D17 — evitaba que Phase 3 leyera config vieja), `spec-mcp-server` §Security (el «salvo `file:` explícito» contradecía **D16**) y §Testing (la latencia se **mide** en el bench local, no se asserta en CI — regla anti-flake).
* **Efecto del gate:** `spec-mcp-server.md` y `spec-markitdown.md` → **Approved** en el índice de [SPEC.md](../SPEC.md) (metadatos actualizados en ambos archivos). **Aprobación de usuario concedida el 2026-10-27**: Phase 2 completada, **Phase 3 (wizard) liberada**.
* **Cierre posterior al FTR — rito de calidad y gate final (2026-10-27/28):** `/code-simplification` (veredicto «nada que simplificar», 1 commit de comentario `761c83d`) + `/code-review` multieje (5 ejes: 3 APPROVE + 2 REQUEST CHANGES) → **9 fixes atómicos aplicados** (`d68f978`..`b21e6af`) y deuda CR-1..CR-8 en [TECH_DEBT.md](TECH_DEBT.md) (`28e3a1f`). Gate final **`just ci` verde 2026-10-28**: cobertura **98 %** (`fail_under=95`), bench-smoke **Δ 976 ms < 10 000 ms PASS**, lint/fmt/typecheck/suites en verde. **M6 intacto: GitHub Actions sigue sin haber corrido — no se declara CI verde.**

**FTR Phase 3→4 — ejecutado 2026-10-28 (T20), checklist verde** (artefacto: wizard completo + docs de cierre; gate Phase 3→Phase 4):

* **Las 8 fases verificadas en local** (T7-T13): F1 prereqs (RAM < 8 GB ⇒ aborta 10-19) · F2 vault reutilizado sin borrar · F3 merge sin sobreescribir + `.install-intent` + `00-resources/` canónico con 2 placeholders (PDF válido parseable por Docling) · F4 `uv` en `.tepochcalli/bin/` con SHA-256, sin scripts remotos · F5 venv en `.tepochcalli/venv/` + `uv sync --frozen`, `import tepochcalli_mcp.tools.search` OK (**R6 cerrada**) · F6 menú 5 salidas con default `paraphrase-multilingual-MiniLM-L12-v2`, gate test-embed con RSS medido, config atómica, clave solo en `tepochcalli.toml` · F7 `python -m tepochcalli_flow` (`refresh`, `embed-check`), 2.ª corrida ⇒ `indexed: 0`, salida 5 omite F7 · F8 merge conservador con `.bak`, comando portable por SO, sin `markitdown`, `rag_status` e2e en ambos estados, idempotencia sin duplicados.
* **Atomicidad y post-instalación verificadas** (T14-T17): fallo inducido en las 8 fases ⇒ compensación correcta, 0 datos del usuario perdidos · `--resume` por artefactos + marker · `--offline` sin caché ⇒ `E_OFFLINE_NO_CACHE` (exit 21) antes de tocar el vault · swap D8.4 con índice viejo servible, rollback byte-idéntico, auto-GC del modelo viejo · `reindex --confirm` y `uninstall` reales (**TD-3 cerrada**).
* **Distribución escrita y revisada, no ejecutada** (T18/T19): `dist.toml` (5 targets, shell+powershell), `release.yml` + `phase3.yml` revisados a mano, recipes `just` nuevas, installers de referencia + regla one-version con SHA-256 — todo sin correr (deuda M6/D-b).
* **Efecto del gate:** `spec-installer-wizard.md` → **Approved** en el índice de [SPEC.md](../SPEC.md) (metadatos actualizados en el archivo). **Aprobación de usuario concedida el 2026-10-28**: Phase 3 completada, **Phase 4 (blueprint) liberada**.
* **Lo NO verificado** (registro explícito, deuda M6/D-b/F-T20 en [TECH_DEBT.md](TECH_DEBT.md)):
  1. La matrix CI (`phase3.yml`: ubuntu+macos + smoke path-5) **nunca se ejecutó** — `cargo test`/`rust-ci` solo corrieron en local; no se declara «CI verde».
  2. **No hay release publicada**: `release.yml` nunca corrió, no existe ningún asset `tepochcalli-workspace-<ver>.tar.gz` real ni installers generados por `dist`; la regla one-version solo está probada con payload local.
  3. **Windows sin probar**: target compilado pero fuera de la matriz; `install.ps1`, `venv/Scripts/python.exe` y el smoke path-5 nunca se ejecutaron en Windows.
  4. `just rust-ci` **verde en local desde 2026-10-28 (rito `/test` posterior al FTR)**: `rust-fmt` y
  `cargo clippy -D warnings` limpios, y `cargo test` con **311 passed, 0 failed, 2 ignored** (2026-10-29: pasada de simplificación que pagó TD-18 con `application/text.rs` [+692/−836] y revisión formal de 5 ejes sobre el crate entero — corrección/legibilidad/arquitectura/seguridad×4/performance con benchmarks ejecutados — que cerró 1 Critical, ~20 Important y ~15 Suggestion en 29 commits: C1 swap re-indexa con el embedder nuevo (config viva antes del refresh), timeouts de subprocess con kill, env allowlist, `0o600` para la api_key, caps de RAM, mirror https_only+confirmación, `uninstall --confirm`, checklist degraded, resume artifact-first; los deltas del conteo (+291→311: +22 neto) son pins nuevos de los fixes, tests-helper duplicados que murieron y tests de conducta re-escritos bajo contrato aprobado por el usuario.
  Los dos tests que dependían de red dejaron de mentir: F4 ya no reporta `DiskFull` cuando la
  red está caída (`map_fetch_error` clasifica los `io::ErrorKind` de transporte como
  `NetDownload`, con tabla unit en el adaptador) y los dos flujos reales que descargan `uv` y un
  CPython gestionado quedan `#[ignore]` con motivo, para el job `network` de `phase3.yml`
  (`cargo test -- --ignored`), que tampoco se ha ejecutado nunca (M6 sigue abierto).
  El tier 1 de `src/` pasó de 2 a 14 ficheros con `#[cfg(test)]` (79 unit tests), y ese trabajo
  destapó tres defectos ya corregidos: `join_checked` aceptaba `..`, los lectores de config no
  deshacían el escape de `toml_escape` y `commit()` borraba el config vivo en vez de restaurarlo.

**FTR Phase 4→5 — checklist verde 2026-11-04 + gate CONCEDIDO 2026-11-09** (artefacto: blueprint del payload en 5 specs; gate Phase 4→Phase 5). El dueño concedió el gate mediante el congelamiento del diseño en 40 skills definitivas (`cf17f31` + `2e62e60`): las 5 specs pasan a **Approved** y Phase 5 queda **READY TO PLAN** (planificación vía `/plan`, sin ejecución).

* **Inventario real verificado contra `obsidian-workspace/.opencode/`**: **209 skills · 170 agentes · 9 comandos**; **0 skills/subagentes inventados** (las 17 filas de la matriz cubren el 100 % del recuento `ls`).
* **5 specs del payload Approved desde 2026-11-09** (cabeceras actualizadas con el gate concedido por congelamiento; todas <500 líneas: vault 366 · skills 226 · permissions 408 · agents 443 · commands 476).
* **14 bloques del payload dentro de presupuesto**: 5 cuerpos de agente (56/54/58/58/56 ≤60) + 9 cuerpos de comando (24-30 ≤35); el blueprint del `AGENTS.md` del vault son 67 líneas, dentro del techo de 120.
* **0 marcadores de español** en los bloques del payload (D-P4-6): sin `ñ`, `¿`, `¡` ni las palabras sueltas del criterio; artefactos en inglés, prosa del repo en español. Las muestras del instalador quedan en español por decisión del dueño (D-P4-7 revocada).
* **0 links rotos**: 92 links relativos revisados en las 6 specs.
* **markdownlint: 0 errores** en `specs/`, `tasks/`, `docs/`, `AGENTS.md` y `SPEC.md`. El único error del baseline D12 (`docs/WORKFLOW.md:166`, MD005 de indentación) se corrigió en este cierre con un dedent de una línea; no queda ninguno.
* **Payload intacto**: `git diff --stat -- obsidian-workspace` **vacío**; ningún commit de la fase escribe `obsidian-workspace/`.
* **Skills — congelado 2026-11-09 (decisión del dueño): 40 dirs definitivos**, objetivo <60 **cumplido**; la matriz de 17 filas queda SUPERSEDED y Phase 5 solo verifica presencia (0 retiros). (El 2026-11-04 la base estricta era **60** y el objetivo fallaba por 1 — D-P4-10 retirada.)
* **Artefactos de guía**: `agent_example.md` y `command_example.md` siguen **untracked** en la raíz (D-P4-8); no se commitean.
* **Lo NO verificado**: nada de Phase 5 se ejecuta aquí (permission fixtures y methodology e2e son sus gates); GitHub Actions sigue sin haber corrido (M6).

## 5. Risk Management

| Riesgo | Prob | Impacto | Mitigación | Contingencia |
| --- | --- | --- | --- | --- |
| Bump roto de cocoindex/lancedb | med | alto | pineos, CI con lock, capa fina TD-1 | pin downgrade; target migration (ADR-002) |
| Criterio 3 falla en HW mínimo | med | crítico | presupuesto por etapas (spec-mcp-server), ANN tuning | top_k default 3 + re-ranking ligero; revisar ADR-006 (dimensión) |
| Wizard multi-OS complejo | med | alto | CI matrix temprana (Phase 3), `--resume` | Windows en v1.1 si bloquea (Linux/macOS first) |
| Skills audit toca `.opencode/` prohibido ahora | baja | medio | diseño (Phase 4) propone vía blueprint; ejecución (Phase 5) autorizada; en el repo padre nunca | mantener inventario actual + TD-7 nota |
| Renumeración de fases introduce staleness de referencias cruzadas | med | bajo | auditoría grep por ola (tax de D10; rev. 3 la aplica); refs en ADRs congelados se REPORTAN, no se editan | corregir refs en la misma ola; registro en §8 |
| Modelo HF custom inválido/erróneo elegido (D8) | med | medio | portero test-embed + badges D8.2 + warn-never-block (D8.3) | swap rápido vía `tepochcalli config embedder` (D8.4) sin reinstalar |

## 6. Progress Metrics

* Δ-time de refresh p95, latencia search p95, tokens/consulta p95 — post-instalados en fixtures, tendencial por release.
* Done per layer: flow (filas correctas) → server (contrato) → wizard (VM limpia) → diseño (blueprint Approved) → payload (golden e2e) → aceptación (tabla §6).

## 7. Schedule and Milestones

* Hitos: M0 (specs aprobadas) → M1 índice vivo → M2 agente cita → M3 un comando instala todo → M4 blueprint workflow Approved (diseño) → M5 payload limpio → M6 v1.
* Sin fechas comprometidas (proyecto individual); orden de dependencias como grafo de Phases arriba.

## 8. Change Control and Lessons Learned

* Cualquier desviación de un contrato = ADR nuevo (inmutabilidad Accepted).
* Cambios de scope solo con aprobación usuario; se registran al final de este documento.
* Lessons learned: sección a llenar tras cada gate (fallas de benches, sorpresas de plataformas).
  * **2026-10-29 (cierre Phase 3):** el informe verde de un subagente no sustituye la verificación propia — la re-corrida de las puertas en target limpio destapó clippy E0432 (re-export muerto `check_prereqs`) y 7 call sites de test con la firma vieja tras el reporte «verde» del aplicador; cierre en `b4ecaeb`.

### Registro de olas de scope (2026-10-21)

| Ola | Qué decidió | Aprobó | Artefactos afectados |
| --- | --- | --- | --- |
| **D7** (ADR-007, Accepted 2026-10-21) | Selección de embedder en instalación: menú "Embedding provider" 5 salidas con default preseleccionado; `presets.toml` como datos; modo degraded + `rag_status` y taxonomía `E_*`; re-entrada `tepochcalli config embedder` / `tepochcalli reindex --confirm`. Reemplaza solo ADR-006 §4.1 | Usuario vía follow-up entrevista /spec (question tool) | docs/adr/adr-007*, spec-embeddings, spec-installer-wizard, spec-mcp-server, ARCHITECTURE, AGENTS, SPEC, TECH_DEBT |
| **D8** (ADR-008, Accepted 2026-10-21; refina D7 sin reemplazarlo) | Transparencia de hardware: `medido` > `estimado` > `declarado` + fórmula de RAM; autodetección de host (`sysinfo`, `nvidia-smi`/`rocm-smi`) con badges `recommended`/`viable`/`no recomendado`; warn-never-block; swap de modelo atómico sin reinstalar (`--keep-previous`, auto-GC) | Usuario vía question tool (4 opciones "Recommended") | docs/adr/adr-008*, spec-embeddings, spec-installer-wizard, APPFLOW, ARCHITECTURE, AGENTS, SPEC |
| **D9** (sin ADR, por decisión explícita del usuario — spec-only) | Semántica de carpetas: tres zonas de propiedad (entrada del usuario / bandejas del agente / biblioteca personal); set de bandejas 6 con mapa comandos→bandejas total y único (`04-review/`, `05-outputs/`); desviación documentada del UH: Pochteca escribe solo `01-tasks/research/` | Usuario vía question tool | specs/spec-vault-structure, specs/spec-agent-workflow, docs/APPFLOW, AGENTS, SPEC, docs/WORKFLOW (esta ola de conformación, rev. 2) |
| **D10** (reestructuración WORKFLOW, rev. 3) | El diseño del agent workflow se convierte en PHASE 4 independiente (documentación pura; gate BLUEPRINT APPROVED); renumeración: Payload→Phase 5 (ejecución literal del blueprint), E2E→Phase 6. Decisión del usuario 2026-10-21 vía question tool, EN CONTRA de la recomendación del arquitecto (sub-fases dentro de Phase 4 rechazadas) | Usuario vía question tool | docs/WORKFLOW.md rev. 3 + referencias cruzadas en specs/docs (spec-vault-structure, spec-agent-workflow, AGENTS, SPEC) + spec-payload-vault como lienzo vivo de Phase 4 + conformación de tax refs (PRD, SECURITY, TECH_DEBT, spec-rag-engine, AGENTS L32) |
| **D11** (sin ADR — corrección documental, NO cambio de decisión) | Corrección de la API de cocoindex (pre-1.0 → v1, pineado `cocoindex==1.0.25`): el esqueleto de spec-rag-engine §Proposed Solution y sus afirmaciones de Fuentes/Chunking/Embeddings se reescriben contra la API v1 verificada por spike: F1 cita vía `chunk.start.char_offset`/`chunk.end.char_offset` y `heading` derivado (no campo de `Chunk`); F2 purga automática de filas al borrar la fuente; F3 `excluded_patterns=["**/.*"]` obligatorio — include-patterns solos NO excluyen dirs-punto; F4 el splitter mide en bytes ⇒ presupuesto **`chunk_size=1536`/`chunk_overlap=192`** (decisión usuario 2026-10-21: ~1024 chars de prosa española, overlap 12,5%); F5 `localfs` sin límite de tamaño ni hook de errores ⇒ regla ">100MB/symlink roto → skipped con motivo" es nuestra; F6 `normalize_embeddings` pertenece a `embed()`, no al constructor (source instalada manda sobre la doc); E1 `device` desde `[embedding]` en `tepochcalli.toml`, **default `"cpu"`** (decisión usuario 2026-10-21); E2 idempotencia leída de stats del data plane, CLI sin paso `setup`. El motor (D1/ADR-001) NO cambia ⇒ corrección de hechos, no de decisión ⇒ **sin ADR nuevo** (regla §8) | Usuario 2026-10-21 | specs/spec-rag-engine.md (§Proposed Solution, §Fuentes, §Chunking, §Embeddings), specs/spec-embeddings.md (§tepochcalli.toml: `[chunking]` 1536/192 bytes, `[embedding] device`), docs/WORKFLOW.md §Phase 1 (objetivo: RecursiveSplitter 1536/192 bytes) |
| **D12** (sin ADR — criterio de aceptación, no decisión técnica) | Creación de `.markdownlint.json` (deshabilita únicamente MD013) y relectura del AC de lint de T1 como "cero errores NUEVOS" sobre la línea base (63 preexistentes en spec-rag-engine + WORKFLOW: 58 MD060, 3 MD034, 1 MD038, 1 MD022) en lugar de "cero errores" absoluto | Usuario 2026-10-21 | `.markdownlint.json`, AC de lint de T1 |
| **D13** (sin ADR — clarificación de esquema y AC, no cambio de decisión) | **Nulabilidad de `heading`:** el campo **siempre está presente** (ADR-005: *"la cita precisa es estructural, no opcional"*) pero su **valor puede ser `null`** cuando el documento no tiene heading padre (`.txt` plano, nota suelta). Los ACs de T5 y la métrica **M2** de T6 pasan de "5 metadatos no nulos" / "100% de filas no nulos" a **"`source_path`, `char_start`, `char_end`, `doc_kind` no nulos + `heading` presente (valor nullable)**". Esquema LanceDB de T6: columna `heading` **nullable**; `heading_before` de T4 ya devolvía `None` y lo tenía testeado, de modo que T4 no cambia. Contradicción resuelta porque tres fuentes divergían (ADR-005 "siempre"/"no opcional" vs spec-rag-engine "último heading padre **visto**" vs ACs "no nulos" vs T4 `None`) | Usuario 2026-10-21 | specs/spec-rag-engine.md (§Target — nulabilidad explícita), `tasks/todo.md` (AC de T5, métrica M2 de T6), contratos T5/T6/T9 |
| **D14** (sin ADR — corrección de layout contradictorio, decisión explícita del usuario) | **Estado del engine en `.tepochcalli/db/cocoindex/`:** spec-vault-structure se contradecía — §Layout comentaba `flow/` como *"definición del pipeline CocoIndex + estado del engine"* mientras §gitignore declara `flow/` **código fuente versionado**; un usuario que `git init` su vault (rutinario en Obsidian) commitearía el **LMDB** del engine — artefacto regenerable, pesado y platform-dependent — dentro del directorio que el producto trata como fuente. Decisión (Usuario 2026-10-21): el estado derivado del engine vive en **`.tepochcalli/db/cocoindex/`** — `db/` ya está gitignored (regla T2, sin duplicar), ya es el hogar del dato derivado (LanceDB), y la promesa de spec-rag-engine §Rollback (*"borrar `.tepochcalli/db/` y re-ejecutar la indexación inicial lo reconstruye entero"*) queda literalmente verdadera. Actualizados `app.py` (`ENGINE_STATE_RELPATH` → `db/cocoindex`; `COCOINDEX_DB` sigue teniendo precedencia) y spec-vault-structure §Layout (solo definición) | Usuario 2026-10-21 | `obsidian-workspace/.tepochcalli/flow/tepochcalli_flow/app.py`, specs/spec-vault-structure.md (§Layout) |
| **D15** (sin ADR — corrección de hechos, NO cambio de decisión) | **`provider = "none"` como 3.er valor del loader:** `EMBEDDING_PROVIDERS` pasa a `("local", "litellm", "none")`. Hasta T6 el loader ADVERTÍA y caía a `local` EN SILENCIO, justamente cuando la instalación degradada (salida 5 del menú embedder de ADR-007) escribe `none` — la config degradada se ejecutaba como una sana. Con D15 la config se respeta, `embedder.mode`/`is_available` pasan de costura de test a hecho real y `search`/`index_refresh` emiten `E_NO_EMBEDDER` end-to-end. ADR-007 ya había decidido el estado `none` ⇒ corrección de hechos, **sin ADR nuevo** (regla §8 de este documento); decisión registrada en tasks/plan.md §2 (entrevista Phase 2, 2026-10-26) | Usuario 2026-10-26 (entrevista Phase 2; plan §2 D15) | `obsidian-workspace/.tepochcalli/flow/tepochcalli_flow/config.py` (`EMBEDDING_PROVIDERS` + sus docstrings), specs/spec-embeddings.md (§`tepochcalli.toml`: valores de `provider`), docs/WORKFLOW.md (esta fila) |
| **D16** (sin ADR — resolución de conflicto entre specs, decisión explícita del usuario) | **`add_source` rechaza `file:` fuera de la raíz del vault:** `spec-mcp-server` §Security permitía «salvo `file:` explícito» mientras `spec-markitdown` §Testing exigía el rechazo; se aplica la **versión estricta** — markitdown con `file:` leería cualquier archivo accesible al proceso y la tool la invoca un agente. Validación en el borde (`paths.validate_source_uri`/`resolve_file_uri`): esquema desconocido, `file:` sin host, `file:` fuera del vault, `subdir`/rutas con `..` o absolutos ⇒ `VALIDATION_ERROR` (negativos en `tests/integration/test_mcp_add_source.py`). **Pendiente reportado en T10:** `spec-mcp-server` §Security conserva el wording permisivo — `specs/` vedado salvo las 2 líneas de D17, enmienda para la siguiente pasada autorizada | Usuario 2026-10-26 (plan §2 D16; ratificado en paths.py) | `obsidian-workspace/.tepochcalli/mcp/tepochcalli_mcp/paths.py`, `tools/add_source.py`, docs/SECURITY.md, tests de integración |
| **D17** (sin ADR — corrección de ejecución, decisión del usuario) | **Invocación `python -m tepochcalli_mcp`, no console script:** lección (f) de Phase 1 — NTFS/fuseblk descarta el bit de ejecución y `venv/bin/tepochcalli-mcp` no arranca. `opencode.json` del payload lanza `[".tepochcalli/venv/bin/python", "-m", "tepochcalli_mcp"]` (mismo patrón `python -m markitdown_mcp`); `[project.scripts]` se conserva en el pyproject pero **no se usa**. T10 corrigió las **dos líneas** de specs que aún anunciaban el console script (autorización estrecha) | Usuario 2026-10-26 (plan §2 D17) | `obsidian-workspace/opencode.json` (T9), specs/spec-mcp-server.md §Empaquetado + specs/spec-markitdown.md §Config (corrección T10), docs/WORKFLOW.md (esta fila) |
| **D18** (sin ADR — decisión de coste, no técnica) | **`markitdown-mcp` se instala tal cual (`markitdown[all]`): +142 MB y +49 paquetes** (medido con `uv pip install --dry-run` contra PyPI, CPython 3.12). Lo exige el layout congelado (spec-vault-structure §Layout) y `--offline` (spec-markitdown); lo que pesa de más (PDF, audio, YouTube, Azure AI) queda fuera de alcance v1 — el PDF lo cubre Docling. Marginal sobre el venv ya existente (~2 GB con torch/Docling) | Usuario 2026-10-26 (plan §2 D18) | docs/TECH_DEBT.md (TD-12), tasks/plan.md §2/§3, docs/WORKFLOW.md (esta fila) |
| **D19** (sin ADR — corrección de contrato, decisión explícita del usuario) | **`mcp.servers.markitdown` NO se registra en F8** (y si el usuario la tuviese, se elimina): la conversión es en proceso vía `add_source`, coherente con el retiro `ee26073` y `tests/unit/test_opencode_payload_registration.py` (`MANAGED_KEYS`) — implementado por T13, anclado por T1 | Usuario 2026-10-28 (plan Phase 3 D19; ola T1) | specs/spec-installer-wizard.md §Merge, docs/WORKFLOW.md (esta fila) |
| **D20** (sin ADR — portabilidad, decisión explícita del usuario) | **Comando del MCP generado por SO:** `.tepochcalli/venv/bin/python` en POSIX, `.tepochcalli/venv/Scripts/python.exe` en Windows — implementado por T13, anclado por T1 | Usuario 2026-10-28 (plan Phase 3 D20; ola T1) | specs/spec-installer-wizard.md §Merge, docs/WORKFLOW.md (esta fila) |
| **D21** (sin ADR — cierra Open Question de la spec, decisión explícita del usuario) | **`--resume` = deducir por artefactos + marker `.tepochcalli/.install-state`**: reusa lo válido sin re-descargar — implementado por T14, anclado por T1 | Usuario 2026-10-28 (plan Phase 3 D21; ola T1) | specs/spec-installer-wizard.md §Open Questions, docs/WORKFLOW.md (esta fila) |
| **D22** (sin ADR — alcance de F3, decisión explícita del usuario) | **El wizard crea `00-resources/` + 2 placeholders** (1 `.md` + 1 `.pdf` válido parseable por Docling); TD-8 sigue en Phase 4/5 — implementado por T8, anclado por T1 | Usuario 2026-10-28 (plan Phase 3 D22; ola T1) | specs/spec-installer-wizard.md (fase 3), docs/WORKFLOW.md (esta fila) |
| **D23** (sin ADR — alcance de UI, decisión explícita del usuario) | **TUI line-based con `dialoguer`** (no `ratatui` full-screen): corre sin TTY vía `--non-interactive` — implementado por T6, anclado por T1 | Usuario 2026-10-28 (plan Phase 3 D23; ola T1) | specs/spec-installer-wizard.md §TUI, docs/WORKFLOW.md (esta fila) |
| **D24** (sin ADR — contrato flow↔wizard, decisión explícita del usuario) | **F7 y el gate test-embed invocan el CLI `python -m tepochcalli_flow`** (`refresh`, `embed-check`) — implementado por T12 | Usuario 2026-10-28 (plan Phase 3 D24) | `obsidian-workspace/.tepochcalli/flow/tepochcalli_flow/__main__.py`, docs/WORKFLOW.md (esta fila) |
| **D25** (sin ADR — reparto de responsabilidades, decisión explícita del usuario) | **El wizard NO descarga modelos:** lo hace el flow Python, que reporta el RSS pico medido — implementado por T11/T12 | Usuario 2026-10-28 (plan Phase 3 D25) | specs/spec-installer-wizard.md (fase 6), docs/WORKFLOW.md (esta fila) |
| **D26** (sin ADR — diseño hexagonal, decisión explícita del usuario) | **5 puertos** (`CommandRunner`, `HttpClient`, `HostProbe`, `PayloadSource`, `Ui`); **sin puerto de FS** (los tests usan `tempfile` real) — implementado por T4 | Usuario 2026-10-28 (plan Phase 3 D26) | `crates/tepochcalli/`, docs/WORKFLOW.md (esta fila) |
| **D27** (sin ADR — reparto spec↔código, decisión explícita del usuario) | **Los rangos de exit code los fija la spec; el número exacto y el mapeo a `E_*` los elige el wizard** — implementado por T3/T15 | Usuario 2026-10-28 (plan Phase 3 D27) | specs/spec-installer-wizard.md (§UX de fallo), docs/WORKFLOW.md (esta fila) |
| **D28-D67** (ADR-009/010/011, *Accepted* 2026-11-03; implementado y medido 2026-11-02/03) | **Phase 3.5 — conversor summary-only + índice multi-raíz + dieta de dos librerías.** (1) *Conversor*: 3 tools en `tepochcalli-rag` (`convert_document`/`convert_base64`/`list_formats`, markitdown en proceso, D28), resumen de 5 claves y cuerpo fuera del wire (D36), frontera B′ entrada **y** salida dentro del vault (D31), existencia y tipo validados en el borde MCP —`walk_dir` lanza `ValueError`, que saldría como `INTERNAL`— (D64), destino existente idempotente sin sobrescribir (D66), catálogo verificado contra `markitdown==0.1.9` (sin `.doc`/`.ppt`: no hay convertidor); standalone `markitdown` retirado del payload (D29) y `anydoc` sigue `disabled` como fallback (D30); el conversor **no** indexa (D49). (2) *Índice*: conjunto de raíces declarado en `INDEXER_DIR` sin estado en el motor (D32/D42, rev. 2), `source_path` relativo al vault (D41), whitelist de 8 extensiones (D43), recursión + raíz-fichero + dedup (D46), frontera de symlinks = vault (D47), `offsets_ref` source/extract (D50), documentos fuera del Δ de 30 s (D51), `ContextKey[Path]` estable ⇒ mover el vault no invalida el memo (D62), multi-raíz fail-fast atómico (D65), `rag_status.index.available_roots` (D67). (3) *Dieta*: dos librerías —`cocoindex` + `markitdown`— (D52); `docling`, `torchvision` y `markitdown-mcp` fuera (D53/D55); el PDF pierde headings (D54, coste aceptado y medido en el FTR); `@coco.fn` en los helpers para que editar un parser invalide el memo (D58); un solo embedder write+read (D59); `as_async` + batching (D60); sin memo de embeddings por chunk (D61); `litellm` por `cocoindex[litellm]` + `[tool.uv] constraint-dependencies` (D56, cierra TD-16); ledger de no-reinvención (D63). (4) *Payload*: skill `tepochcalli-mcp` con el catálogo de tools (D33/H4) | Usuario 2026-10-30 (entrevista `/plan`; D64-D67 vía question tool el mismo día) | docs/adr/adr-009/010/011\*, specs/spec-{markitdown,mcp-server,rag-engine,vault-structure}, tasks/plan.md, tasks/todo.md, docs/ARCHITECTURE.md, SPEC.md, docs/WORKFLOW.md (esta ola) |
| **D68** (sin ADR en esta ola — registro de planificación; las decisiones de fondo van en ADR-014/015 Proposed) | Creación de PHASE 6.5 "Wizard flujo destino (H5-H11)" como fase intermedia post-6 (misma convención que Phase 3.5, no renumera fases), GATED/no ejecutable: materializa docs/BACKLOG.md §2 «Wizard de instalación: flujo destino (2026-11-18)» (canal uvx, TUI botones, versión pyproject, Update/Desinstall ampliados, device/embedder). Aprobada por el dueño al ordenar la fase el 2026-11-18; su gate de entrada exige ADR-014/015 Accepted + deps aprobadas (maturin/PyPI, TUI) + one-version alineada (Cargo↔pyproject) + enmiendas 2026-11-18 Accepted | Usuario 2026-11-18 (esta orden) | docs/WORKFLOW.md (§1 tabla+estado, §2 Phase 6.5, §4 FTR, §8 esta ola) |

**Nota de mapeo D10 (lectura de ADRs congelados):** los ADR-002 (§4.1 "bench de Phase 5"), ADR-006 (§4.1 "Benchmark Phase 5"), ADR-007 (§8) y ADR-008 (§8) citan "Phase 5" con la numeración PRE-D10, donde significaba **aceptación E2E** — hoy **Phase 6**. Los ADR son Accepted y congelados por la regla de §8/AGENTS (nunca re-editar un ADR Accepted): no se re-editan; este párrafo es el mapeo canónico para quien ejecute sus benchmarks (10k/1k, Δ<30s, <500ms, contract tests D7.3/D8 → correr en Phase 6).

**Nota de mapeo D11 (lectura de ADRs congelados):** el ADR-002 §4.1 *Confirmation* describe su verificación de no-interferencia como "Tras `cocoindex setup`, `.tepochcalli/db/` contiene solo archivos Lance". `setup` es un subcomando de la CLI **pre-1.0**; en `cocoindex==1.0.25` **no existe** — la CLI de v1 expone `drop, init, ls, show, update`, y el estado del engine vive en la variable `COCOINDEX_DB` (D11/E2, verificado por spike). El ADR es Accepted y congelado por la regla de §8/AGENTS: **no se re-edita**; este párrafo es el mapeo canónico — quien ejecute esa confirmación debe leer `cocoindex setup` como `cocoindex update`.

### Lessons learned — Phase 1 (T1-T11, cierre 2026-10-23)

* **(a) Una spec congelada arrastra una API muerta pre-1.0 (D11).** `spec-rag-engine` se aprobó contra la API **pre-1.0** de cocoindex (`cocoindex setup`, campo `heading` en `Chunk`, include-patterns como mecanismo de exclusión); el spike contra el pin `cocoindex==1.0.25` la desmintió en T1 y obligó a la corrección documental **D11**. Los contratos se congelan, los **hechos de API se re-verifican**: una afirmación falsa se corrige sin ADR (es corrección de hechos, no de decisión) y queda mapeada aquí para los ADRs congelados que la heredan.
* **(b) Defecto de secuencia del plan, atrapado en el gate.** CP-B exigía el test de arquitectura (el dominio no importa infra) que el plan asignaba a **T9** — una tarea posterior: un gate no puede depender de un artefacto que aún no existe. Detectado al ejecutar el gate; el test se trasladó a sub-fase B (con RED demostrado en las dos direcciones) y T9 lo extendió poniendo `ports` en el conjunto protegido. Lección: contrastar cada CP contra las tareas que lo alimentan **antes** de ejecutar, no durante el gate.
* **(c) `RecursiveSplitter` mide bytes, y el «p95» con n=10 colapsaba al máximo.** El presupuesto es 1536/192 **bytes** (D11/F4), no chars; y con n=10 el percentil nearest-rank **es** el máximo, así que una sola query con page-fault (Docling ~2 GiB RSS empujando a la swap) hacía fallar la suite completa mientras el test aislado pasaba con holgura. Corrección: separar medición de corrección (marker `slow`, ya prescrito por T11) y publicar siempre **n + método de percentil** junto al número (el p95 de M1 es el 19.º de n=20).
* **(d) Docling cuesta más de lo que la spec estimaba.** spec-rag-engine estimaba «30 págs ≈ 5-30 s»; **medido**: 49–51 s en caliente (≈1,6–1,7 s/pág) + 29–37 s de carga fría de modelos, RSS pico 2 048–2 189 MiB (M5). TD-2 actualizado con la cifra medida. Lección: en specs, todo coste se etiqueta *estimado* hasta medirlo — la propia jerarquía de D8 lo dice: `medido > estimado > declarado`.
* **(e) `sentence-transformers` 6.x renombró el slug de caché y eso desactivó `HF_HUB_OFFLINE` en silencio.** El slug real es `models--sentence-transformers--paraphrase-…` (6.x prefija la org); el nuestro (`models--paraphrase-…`) nunca coincidió, así que el flag **no se fijaba** en el camino de caché cálido y la hermeticidad de M3(b) no probaba lo que creía probar. Corregido en `model_cache.py` con sondas que cubren las 5 ramas. Lección: un flag de hermeticidad se testea comprobando **que se fija**, no solo que el test pasa.
* **(f) El montaje fuseblk/NTFS y la herramienta `edit` mintieron.** `/mnt/HDDFish` (NTFS vía fuseblk) **descarta los bits de ejecución** (p. ej. `python -m` dejó de funcionar sobre rutas del repo) y la herramienta `edit` **reportó éxito sin persistir** la escritura — ambos mordieron durante Phase 1. Regla operativa: releer el archivo **tras cada edición**; si el cambio no está, reescribir por shell; no confiar en el exit code de una edición sobre fuse.
* **(g) El campo es `extend`, no `extends`.** En la config del toolchain (`uvx ruff` sobre `.ruff.toml`), ruff 0.17.1 rechaza `extends` con «unknown field»: el plural que «suena bien» no existe (verificado contra la doc de ruff y empíricamente, commit `a426250`). Relacionado: `extend-exclude` de `.opencode/` no es cosmético — sin él, `ruff check .` ve 2 167 hallazgos de un payload de terceros que AGENTS.md prohíbe tocar. Lección: el nombre del campo se confirma contra la doc del tool, no por intuición morfológica.

### Lessons learned — Phase 3.5 (T1-T16, cierre 2026-11-03)

* **(a) La dieta se mide, no se estima.** Venv **1,921 GiB / 135 paquetes** (antes 184) y lock
  **193 → 140** entradas; el pico de RSS del Δ bajó de **2 048–2 189 MiB** (Docling) a
  **1 486–1 601 MiB**. El Δ de texto pasó a **4 299 ms p95** (Phase 1: 5 385–5 952 ms) — mismo
  bench, n=20, 19.º valor. Un cambio de motor se publica con las dos cifras y el método, no con
  una promesa.
* **(b) Lo no medido se escribe como no medido.** El coste de un PDF de 30 páginas con markitdown
  no se extrapoló desde Docling: queda declarado en TD-2 y en §Phase 3.5. La jerarquía de D8
  (`medido > estimado > declarado`) vale también para las specs de esta fase.
* **(c) Un fixture rebasado convierte un test en una tautología.** El golden de merge se
  regeneró sobre el payload actual, así que compara el payload consigo mismo (TD-30): el verde
  no demuestra el merge conservador hasta que exista un merge sintético. Lección: un golden se
  valida por cómo se genera, no por el color del test.
* **(d) Cierre (2026-11-03):** Phase 3.5 cerrada con el **FTR aprobado** — ADR-009/010/011
  *Accepted* y las 4 specs enmendadas definitivas; Phase 4 (blueprint) desbloqueada.
