# Implementation Plan — Tepochcalli v1

**Date:** 2026-10-21 | **Author:** Arquitecto (entrevista /spec) | **Methodology:** Especificación-driven, fases con gates (doc para `/plan`)

> Cada fase tiene: objetivo, entregables, dependencias, métricas de cierre y **gate** — la fase
> siguiente NO arranca sin gate verde. Los contratos (specs) se congelan en Phase 0; cambiar
> un contrato en vuelo requiere ADR, no solo código.

**Estado:** el cierre de cada fase está en la tabla de completadas y terminadas de §2; la tabla de pendientes está vacía y lista para futuras fases. GitHub Actions corre desde
2026-11-24 (run `45316624910`, gates `gitleaks`/`python`/`rust` verdes). Phase 6.8 quedó
**CERRADA EN LOCAL el 2026-11-25 con veredicto GO, sin desplegar**: sin tag, Release ni PyPI;
el bump `beta.2→beta.3` está diferido al prep de release.

## 1. Phase Overview

| Phase | Nombre | Objetivo | Gate (criterio de salida, medible) |
| --- | --- | --- | --- |
| 0 | Foundations | Specs/ADRs aprobadas y congeladas | APROBACIÓN: usuario confirma este set de docs; D1-D9 sin cambios; ADR-001..008 Accepted |
| 1 | Engine + Flow | Flujo CocoIndex indexa un vault real incrementalmente | `cocoindex update` sobre vault muestra: Δ <30s; filas en LanceDB queryables con `{source_path,heading,char_start,char_end}`; bench PDF-exclusión documentado |
| 2 | MCP Server | `tepochcalli-rag` conecta a OpenCode con contratos D6 — 4 tools: `search`, `index_refresh`, `add_source`, `rag_status` *(histórico: hoy son 7 — ver §2)* | opencode listá tools; `search` devuelve chunks citados <500ms en fixture; asserts de token-budget (≤1600 payload) en tests; taxonomía `E_*` + precedencia `INDEX_EMPTY` cubiertas (contract tests D7.3) |
| 3 | Wizard | Instalador Rust atomico end-to-end | VM limpia (Linux/macOS/Windows, sin Python/Node) → `cargo binstall` (fallback `curl \| sh`) + `tepochcalli install` → vault instalado + índice inicial + `mcp.servers` validados; prueba de idempotencia (2 corridas); instalación con menú de embedder (D7.1) en sus 5 salidas |
| 4 | Diseño del agent workflow (blueprint) | Completar specs/spec-payload-vault.md hasta Approved: system prompts definitivos de los 5 agentes, permisos YAML (last-match-wins), templates de los 9 comandos, tabla de invocación 9×4 y matriz de conflictos contra el inventario REAL de skills — documentación pura, cero escritura de payload | BLUEPRINT APPROVED por el usuario (status → Approved en SPEC.md index); matriz cubre el 100% del inventario (recuento ls vs filas); cero skills/subagents inventados; permisos sin campos legacy V2 |
| 5 | Payload + Skills audit (ejecución) | Ejecución LITERAL del blueprint Approved sobre `obsidian-workspace/` | `obsidian-workspace/` = payload versión-release generado del blueprint; muestras md+PDF; acciones Anexo A ejecutadas (duplicados consolidados, gaps Jupyter/R/Graphviz-PlantUML/LaTeX instalados o declarados won't); alias 00-Resources resuelto: canónico `00-resources/` (TD-8; 2026-11-13); Validación del agent workflow (D9) verde: permission fixtures + methodology e2e *(2026-11-09: fixtures verdes; methodology e2e diferida a QA de cierre — D-P5-10, runbook entregado)* |
| 6 | E2E Acceptance | Validar los 7 criterios de BACKLOG.md sobre sistema completo | Aceptación: evidencia de los 7 criterios en docs/acceptance/ (criterio 6 con salvedad TD-36) en HW mínimo (8GB CPU-only) y corpus 10k/1k; docs de producto alineados |
| 6.5 | Wizard flujo destino (H5-H11) | Materializar el estado objetivo del instalador: canal uvx, TUI full-screen con botones por estado, versión desde pyproject, Update/Desinstall ampliados, selección de device/embedder | **COMPLETADA 2026-11-19** — 4 precondiciones del gate de entrada resueltas (ADR-014/015 Accepted; deps `maturin`/PyPI + `ratatui`/`crossterm` aprobadas; one-version alineada en `0.1.0`; enmiendas 2026-11-18 Accepted). Verificado: rueda local por `uvx --from`, H5 en TTY real, install/update/desinstall e2e con backup, `just ci` exit 0 (45m49s), `just md-lint` 0. **Salvedades declaradas:** VM limpia/`uvx` desde PyPI (no se publica), TTY en Windows (TD-52), Change Embedder e2e, payload del checkout (TD-53) |
| 6.8 | Fallos visibles, desinstall acotado y progreso honesto | Corregir 3 bugs y añadir 3 mejoras UX de cara a `beta.3`, sin desplegar | **CERRADA EN LOCAL 2026-11-25 — GO, sin desplegar** — gate: C8–C12 verdes + `just rust-ci` y `just quality`; bump y tag diferidos al prep de release |

## 2. Phase Breakdown

> Los 7 criterios de `docs/BACKLOG.md` y el gate adicional D9 están documentados con su evidencia
> en `docs/acceptance/` y en `docs/BACKLOG.md`; el único FAIL de cota es el criterio 6 (TD-36).

### Fases completadas y terminadas

| Fase | Estado | Gate o issue encontrado | Resultado o solución (referencia) |
| --- | --- | --- | --- |
| 0 | Completada · 2026-10-21 | Gate limpio: Aprobación del usuario | ADR-001..008 *Accepted*; specs congeladas; D1-D9 sin cambios |
| 4 | Completada · 2026-11-09 | Gate limpio: BLUEPRINT APPROVED por congelamiento del dueño | 5 specs *Approved*; 40 skills; `obsidian-workspace/` intacto (`cf17f31`/`2e62e60`) |
| 1 | Terminada | Spec congelada con API pre-1.0 de cocoindex (`setup`, campo `heading`, include-patterns) | Corrección de hechos D11 contra `cocoindex==1.0.25`; sin ADR ni reescritura de ADRs *Accepted* (D11; `specs/spec-rag-engine.md`) |
| 1 | Terminada | p95 con n=10 colapsaba al máximo; `RecursiveSplitter` mide bytes; Docling 49–51 s/30 págs frente a 5–30 s de la spec | Publicar siempre n + método; separar medición y `slow`; TD-2 con la cifra medida (TD-2; §8) |
| 2 | Terminada | Bug de PDFs F-T7-2 heredado de Phase 1 | Arreglado en esta fase; gate final `just ci` verde (F-T7-2; §4) |
| 2 | Terminada | Fórmula 1590 tokens frente a JSON literal ~1740 | Decisión F-T7-1: manda la fórmula; cota de envoltura ≤200 con test (F-T7-1; 9 fixes `d68f978`..`b21e6af`; CR-1..CR-8) |
| 3 | Terminada | C1: el swap no re-indexaba con el embedder nuevo; timeouts, env, RAM y permisos | Revisión formal de 5 ejes: 29 commits, 311 passed (`b4ecaeb`; §4) |
| 3 | Terminada | F4 reportaba `DiskFull` con la red caída | `map_fetch_error` clasifica los `io::ErrorKind` de transporte como `NetDownload` (§4, fila Phase 3→4) |
| 3.5 | Terminada | `TEPOCHCALLI_TOP_K` fuera de `[1,20]` rompía toda `search` | Validación en el borde + `problems` en `rag_status.config` (`95082be`/`92efc16`/`f4a399c`) |
| 3.5 | Terminada | Golden de merge rebasado (comparaba el payload consigo mismo); guard SSRF en el prefetch del conversor | TD-30 declarado; cap de bytes y timeout (TD-30; W-02; `e191a45`..`6e00aa9`) |
| 5 | Terminada | 2.ª instalación fallaba en F5 (`uv venv` sobre venv existente y la compensación lo borraba) | `uv venv --clear` + test RED→GREEN (`int_install_f4_f5.rs`) |
| 5 | Terminada | Methodology e2e D9 diferida (D-P5-10) | Runbook entregado (TD-31; `tests/phase5-methodology-runbook.md`) |
| 6 | Terminada | Criterio 6: ratio 6,17× frente a la cota 2× (Δ p95 15 695 ms al 100 % vs 2 543 ms al 10 %) | Registrado; el 100 % sí cabe en 30 s al 52 % (TD-36; `docs/acceptance/scale-ratio.json`) |
| 6 | Terminada | Criterio 7: `url`/`.doc`/`.ppt`/PDF escaneado sin cubrir; margen de 5 tokens en el peor caso | GAP declarado con mensaje accionable; margen publicado (`docs/acceptance/format-matrix.json`; F-T6-1) |
| 6.5 | Terminada | Windows y `uvx` desde PyPI sin probar; Change Embedder e2e no ejecutado (~470 MB) | Fakes `e2e_swap`/`int_ui_menu`; salvedad TD-52 (TD-52; ADR-014/015) |
| 6.5 | Terminada | Payload completo del checkout: 19m10s | Salvedad declarada (TD-53) |
| 6.6 | Terminada | Sin journal por fichero en el install | Reutiliza `.install-intent`/`.bak`/marker/snapshot (ADR-016) |
| 6.6 | Terminada | Journal acumulativo sobre vault preexistente; TTY real, Ctrl+C, Windows y animación no medidos | Limitación declarada, sin maquillar (cierre de Phase 6.6, 2026-11-20) |
| 6.7 | Terminada | `zip` 2.6.1 con `CVE-2026-115905` | Actualizado a 9.8.2 (`CHANGELOG.md`) |
| 6.7 | Terminada | Sin rueda ni binarios (TD-71), workflow nuevo sin ejecutar (TD-72) | Salvedades declaradas (TD-71; TD-72) |
| 6.8 | Terminada | F6 degradaba sin panel; `E_MODEL_INVALID` aplanaba tres causas | Panel + log + causa real, con exit 0 y `none_config`, política intacta; seam con 3 códigos + fallback `ModelLoadFailed` (`docs/diagnosis/fix02-wizard-gate-modelinvalid-y-f6-silencioso.md`; ADR-016) |
| 6.8 | Terminada | `remove_dir_all` secuencial sobre ~51 k entradas; barra ondulada | Helper bottom-up con 8 workers, std-only sin `libc`; progreso monótono por hitos + spinner ASCII + cronómetro + ETA declarada (`docs/diagnosis/fix03-desinstall-lento-por-venv.md`; C8–C12) |

### Fases pendientes

> Sin fases pendientes a 2026-11-25. Esta tabla queda preparada para las fases que el dueño autorice.

| Fase | Objetivo | Dependencias | Gate de salida |
| --- | --- | --- | --- |

## 3. Testing Strategy per Phase

| Fase | Herramienta | Alcance | Éxito |
| --- | --- | --- | --- |
| 1 | pytest + cocoindex runtime | flow unit/integración | evidencia en `docs/acceptance/` |
| 2 | pytest + fixture vault | contratos MCP, presupuestos, `rag_status` y `E_*` | shapes + cotas duras |
| 3 | cargo test + VM matrix | fases/rollback/idempotencia, menú 5 salidas, swap D8.4 | sin datos del usuario perdidos |
| 4 | ls + grep + revisión humana | tabla 9×4 + matriz de conflictos; permisos V2 | BLUEPRINT APPROVED |
| 5 | smoke e2e + fixtures D9 | payload del blueprint | golden vault citado; bandejas/frontmatters |
| 6 | suite TRD §6 + manual | criterios 1-7 | tabla de evidencia en `docs/acceptance/` |

`just typecheck` (mypy `--strict`) corre en CI entre `ruff format --check` y `pytest`; superficie: `flow/` en Phase 1 y `flow/` + `mcp/` desde Phase 2 ([CODE_STYLE.md](CODE_STYLE.md)).

### Tiempo medido y cuándo ejecutarlo

| Receta | Cuándo | Tiempo medido (referencia) | Resultado / nota |
| --- | --- | --- | --- |
| `just quality` | gate táctico, cada cambio | 66–72 s (710 tests Python) | lint + fmt + typecheck + unit |
| `just python-test-file <patrón>` | un test suelto o depuración | segundos (sin medición publicada) | sustituye a la suite entera si se cancela |
| `just test-mcp-tools` | iteración en MCP tools | 13:23 (82 tests) | >10 min, informativo (**TD-38**) |
| `just test-mcp-wire` | iteración en el wire stdio | 7:09 (28 tests) | dentro del tope de 10 min |
| `just test-engine` | iteración en el flow | 15:03 (80 tests) | >10 min, informativo (**TD-38**) |
| `just test-converter` | iteración en el conversor | 1:15 (12 tests) | dentro del tope |
| `just test-acceptance` | gate de aceptación | 2,3 s (10 tests) | también corre en CI |
| `just rust-ci` | cada cambio Rust y CI | 2m45s caliente (506 passed / 4 ignored) | clippy `-D warnings` + tests |
| `just bench-smoke` | gate de integración | Δ 1,18 s < 10 s (índice frío 39,1 s) | PASS |
| `just ci` | cierre de fase / prep de release | 20:58–45m49s; última 2026-11-25: 1428 tests | **prohibido en CI** |
| `just coverage` | una vez al cierre de fase | 50m46s / 97 % | local, ausente de `ci`; `fail_under = 95` |
| CI en GitHub Actions | PR + push a `develop`/`main` | gitleaks 8–11 s · python 1m45–2m11 · rust 2m35–3m45 | `timeout-minutes: 10` por job |

Las suites de módulo solo informan su tiempo (sin gate que falle); `mcp-tools` y `engine` superan el tope informativo de 10 min (**TD-38**). No marcar tests `slow`: el coste está repartido entre integración y e2e.

### Cobertura

`just coverage` es la única cifra honesta: instrumenta también los subprocesos (`refresh` y `verify`) vía `sitecustomize` + `[tool.coverage.run] parallel`; `pytest --cov` a secas sub-mide. Alcance desde Phase 2 (decisión 2026-10-27): `source = ["tepochcalli_flow", "tepochcalli_mcp"]`. Medido: 98 % al ampliar el gate y 99 % tras cubrir gaps; las ramas sin cubrir son de Phase 1 ([TECH_DEBT.md](TECH_DEBT.md) Q-2). Es medición **local**, no gate: corre una vez al cierre de fase, no en `ci` ni en GitHub Actions (activo desde 2026-11-24, run `45316624910`).

## 4. Formal Technical Reviews (FTRs)

| Gate | Fecha | Resultado | Efecto / salvedades |
| --- | --- | --- | --- |
| Phase 0→1 | 2026-10-23 | Checklist verde: D1-D9 coherentes, 95 links, 12 bloques mermaid, lint 420→420 | `spec-rag-engine`/`spec-embeddings` → *Approved*; aprobación de usuario concedida |
| Phase 2→3 | 2026-10-27 | Checklist verde: 4 contratos en el wire, 5 `E_*`, e2e grabado | `spec-mcp-server`/`spec-markitdown` → *Approved*; Phase 3 liberada |
| Phase 3→4 | 2026-10-28 | Checklist verde: CP-A..D (6/6 cada uno) + suite local | `spec-installer-wizard` → *Approved*; salvedades: matriz CI no ejecutada, sin release, Windows sin probar |
| Phase 4→5 | 2026-11-04 / 2026-11-09 | Checklist verde + gate concedido por freeze 40 (`cf17f31`/`2e62e60`) | 5 specs del payload → *Approved*; `obsidian-workspace/` intacto |
| Phase 5→6 | 2026-11-09 | Checklist con salvedad D-P5-10 | Methodology e2e diferida; runbook entregado |
| Phase 6.5 | 2026-11-19 | Gate de entrada y cierre cumplidos | Rueda local y H5 en TTY real; salvedades TD-52/TD-53, `uvx` desde PyPI no probado |
| Phase 6.6–6.8 | — | Sin FTR formal | 6.6/6.7 con checkpoints internos; 6.8 con C8–C12 y GO local sin desplegar |

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
* Done per layer: flow (filas correctas) → server (contrato) → wizard (VM limpia) → diseño (blueprint Approved) → payload (golden e2e) → aceptación (docs/acceptance/).

## 7. Schedule and Milestones

* Hitos: M0 (specs aprobadas) → M1 índice vivo → M2 agente cita → M3 un comando instala todo → M4 blueprint workflow Approved (diseño) → M5 payload limpio → M6 v1.
* Sin fechas comprometidas (proyecto individual); orden de dependencias como grafo de Phases arriba.

## 8. Change Control and Lessons Learned

* Cualquier desviación de un contrato = ADR nuevo (inmutabilidad Accepted).
* Cambios de scope solo con aprobación usuario; se registran al final de este documento.
* Lessons learned: fallas de benches, sorpresas de plataformas y cierres de gate, consolidadas abajo.

### Lessons learned (consolidadas)

| Fase / fecha | Lección aprendida | Aplicación / referencia |
| --- | --- | --- |
| Phase 1 / 2026-10-21 | Una spec congelada arrastra una API muerta pre-1.0: los hechos de API se re-verifican aunque el contrato esté congelado | D11; corrección sin ADR |
| Phase 1 / 2026-10-23 | Un gate no puede depender de una tarea posterior (CP-B exigía el test asignado a T9) | Test trasladado a sub-fase B con RED demostrado; T9 lo extendió |
| Phase 1 | `RecursiveSplitter` mide bytes (1536/192) y el p95 con n=10 es el máximo | Publicar siempre n + método; separar medición y `slow` |
| Phase 1 | Coste estimado ≠ medido: Docling 49–51 s/30 págs frente a 5–30 s de la spec | TD-2 con la cifra medida; jerarquía `medido > estimado > declarado` |
| Phase 1 | Un flag de hermeticidad se testea comprobando que se fija (slug de caché de `sentence-transformers` 6.x) | `model_cache.py`, 5 ramas |
| Phase 1 | fuseblk/NTFS descarta el bit de ejecución y `edit` puede reportar éxito sin persistir | Releer tras editar; invocar con `python -m` (D17) |
| Phase 1 | El campo es `extend`, no `extends` (ruff 0.17.1) | `a426250`; `extend-exclude` de `.opencode/` |
| Phase 3 / 2026-10-29 | El informe verde de un subagente no sustituye la verificación propia | Re-corrida en target limpio: clippy E0432 y 7 call sites; `b4ecaeb` |
| Phase 3.5 | La dieta se mide, no se estima: 1,921 GiB / 135 paquetes y lock 193 → 140 entradas | ADR-011; cifras medidas, mismo bench con n + método |
| Phase 3.5 | Lo no medido se escribe como no medido: PDF de 30 páginas con markitdown | TD-2 |
| Phase 3.5 | Un fixture rebasado convierte un test en tautología (golden de merge) | TD-30 |
| Phase 3.5 / 2026-11-03 | Cierre con FTR aprobado | ADR-009/010/011 *Accepted*; 4 specs enmendadas definitivas |
| D10 / 2026-10-21 | Pre-D10, «Phase 5» significaba hoy Phase 6 en ADR-002/006/007/008 | ADRs *Accepted* no se reeditan; benchmarks 10k/1k → Phase 6 |
| D11 / 2026-10-21 | `cocoindex setup` no existe en v1 (`cocoindex==1.0.25`): leerlo como `cocoindex update` | ADR-002 §4.1; estado en `COCOINDEX_DB` |
