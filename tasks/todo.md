# TODO — Phase 6.9: rediseño del TUI y preparación de 0.1.0-beta.4

> Fichero de seguimiento. Creado limpio el 2026-11-25 sobrescribiendo el contenido anterior. Una sola fase, sin deploy. Detalles y tablas de asignación en `tasks/plan.md`.

## Estado

- [x] Pre-flight y diagnóstico (`docs/diagnosis/fix04-tui-f6-solapamiento-y-eta.md`)
- [x] Decisión del dueño: todo C1–C6 en una fase, dentro de `0.1.0-beta.4`, sin deploy
- [x] Fase registrada en `docs/WORKFLOW.md` §Phase 6.9
- [x] Plan y TODO escritos-from-scratch en estos dos ficheros
- [x] Implementación en curso

## Tareas

### T1 — Dueño único de pantalla (BLOQUEANTE)

- [x] RED: `tests/int_ui_screen_ownership.rs` con guard de `select`/`input`/`panel`
- [x] GREEN: estado de selección en `ports/ui.rs`; `TtyUi::select` en frame; sin segundo `try_init()`
- [x] Limpieza de estado en todo exit + abort tipado
- [x] Fakes y `HeadlessUi` compilan; orden de colas intacto
- [x] `wc -l ui_ratatui.rs ≤ 500` (o `ui_selection.rs` extraído)
- [x] CHECKPOINT A: `just rust-test-filter int_ui_screen_ownership` + `just rust-ci` + revisión

### T6 — Receta de densidad de comentarios (PARALELO)

- [x] Receta nueva en `Justfile` (nombre verificado con `just --list`)
- [x] Reproduce 7,55 % global / 16,49 % Rust `src`, con excluidores y limitaciones
- [x] Fila en `docs/BACKLOG.md` §8; **sin compactar comentarios**
- [x] CHECKPOINT C: receta ejecutada + `just md-lint` si aplica

### T2 — Orden del install (TRAS A, PARALELO)

- [x] RED: aserciones de orden en `int_embedder_menu.rs` e `int_install_f4_f5.rs`
- [x] Selección antes de F3; gate test-embed tras F5; `models/` en el título
- [x] `--resume` y cola `for_install` sin robo de índice
- [x] `run_f6_or_degraded` conserva degradación y exit 0

### T3 — Layout y ETA (TRAS A, PARALELO)

- [x] RED: `tests/int_ui_layout.rs` a 80x24/40x12/30x8/20x6 con aserciones posicionales
- [x] ETA en columna derecha; tres zonas; Cancelar siempre visible; headers con wrap
- [x] Reescritos `int_progress_spec.rs:73-94` y `:97-128`
- [x] CHECKPOINT B: `just rust-test-filter int_ui_layout` + `just rust-ci`

### T4 — Banner semántico (TRAS A, PARALELO)

- [x] RED: literales en `adapters/ui.rs:363` e `int_ui_menu.rs:66,80`
- [x] «listo para instalar» sin pyproject; versión instalada cuando exista
- [x] `domain/menu.rs` sin cambios (`git diff` vacío)

### T5 — No-TTY + e2e TTY (SECUENCIAL)

- [x] `e2e_ui.rs:288-323` sin regresión
- [x] `e2e_install_tty.rs` con PTY **o** salvedad documentada + demo manual
- [x] `models/` asertado en el título del gate y en el header PTY; tests viejos reescritos: 2 en `int_progress_spec.rs` + literales en `int_ui_menu.rs`

### T7 — Bump beta.4 y docs (ÚLTIMO)

- [x] 11 ficheros alineados a `0.1.0-beta.4` (`git show --stat 9b29a4c`)
- [x] `just rust-lock-refresh` → `just payload-lock` → `just payload-lock-check` → `just third-party`
- [x] Spec enmendada (§§279/316-357/361-367) + fila en BACKLOG §8; sin ADR
- [x] `git tag --list` sin tag nuevo; sin Release ni PyPI
- [x] CHECKPOINT D: `just rust-ci` + `just quality` + `just md-lint` + `just ci` completo; demo manual documentada

## Cierre (sin deploy)

- [x] Referencias entrantes a estos dos ficheros verificadas tras el borrado
- [x] `just md-lint` 0 issues
- [x] `git status --short` solo con los ficheros intencionados
- [x] Fase terminada «lista para desplegar» — **sin tag, Release ni PyPI**

**Cierre 2026-11-25:** los 7 tasks están implementados y verificados; commits relevantes `03525ac`, `eb6d6fc`, `04a0382`, `6a109a4`, `519c6b8`, `253da2a`, `987aec0`, `5295910`, `6c6e42c`, `9a58b52`, `9b5c47b`. Fase COMPLETADA, lista para desplegar y sin deploy.
