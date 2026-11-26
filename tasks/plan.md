# Plan de tareas — Phase 6.9: rediseño del TUI del wizard y preparación de 0.1.0-beta.4

> Fuente: `docs/diagnosis/fix04-tui-f6-solapamiento-y-eta.md` y `docs/WORKFLOW.md` §Phase 6.9 (autorización del dueño 2026-11-25). Una sola fase, todo C1–C6 dentro de `0.1.0-beta.4`, **sin deploy** (sin tag, Release ni PyPI).

## 1. Decisiones congeladas

No re-litigar: dueño único de pantalla con selección renderizada en el frame ratatui (dialoguer fuera de F6); mover **solo** la selección al inicio y el gate tras F5; layout 3 zonas + ETA en columna derecha + responsive; banner «listo para instalar»/versión; receta de densidad (banda 10–15 %, global medido 7,55 % ⇒ **no compactar**); bump one-version beta.4 en 11 ficheros; enmienda de spec + §8 del BACKLOG, **sin ADR** (UX reversible, D1-D8 intactas). Skills usadas en la planificación: `planning-and-task-breakdown`, `codebase-design`, `clean-ddd-hexagonal`.

## 2. Mapa de dependencias

Flecha `X → Y` = «X depende de Y». Arquitectura (dependencia hacia dentro): `cli/install_phases.rs` + `cli/install.rs` → `application/{embedder_menu,embedder_gate,installed,home}.rs` → `ports/ui.rs` (trait `Ui`, `MenuView`, `ProgressSpec{eta}`, `ACTIVE_PROGRESS`) ← implementado por `adapters/ui.rs` (`TtyUi`/`HeadlessUi`) → `adapters/ui_ratatui.rs` (watcher/render) ← fakes de `tests/common/mod.rs` ← `tests/int_*` y `tests/e2e_*`. `domain/menu.rs` (`READY_NOTICE`, `installed_state`) es hoja: **no tocar**. Justfile, spec, BACKLOG §8 y los 11 ficheros de versión son salida final; ningún módulo de código depende de ellos. Regla ADR-005: `adapters` no puede ser importado por `application`; `domain` no importa I/O. El cambio de propiedad se hace en el seam `Ui`, nunca con un segundo `try_init()`.

Paralelismo: **T1** es el único bloqueante inicial (toca `ports/ui.rs`, `adapters/ui.rs` y `ui_ratatui.rs`). Tras el checkpoint A: **T2, T3, T4 y T6** pueden correr en paralelo entre sí — salvo T3 (mismo `ui_ratatui.rs` que T1) y T4 (mismo `adapters/ui.rs` que T1), que esperan a A. **T5** y **T7** son secuenciales al final. **T6** es independiente desde el inicio.

## 3. Orden por riesgo

1. **T1** (ALTO, fail fast): dos dueños del TTY en F6. 2. **T6** (BAJO, paralelo): receta nueva. 3. **T2** (MEDIO-ALTO): orden del install, `--resume` y ADR-015. 4. **T3** (MEDIO): aserciones posicionales; `ui_ratatui.rs` a 494 líneas. 5. **T4** (BAJO-MEDIO): banner. 6. **T5** (MEDIO-ALTO): PTY flaky. 7. **T7** (MEDIO): 11 ficheros + locks.

## 4. Tareas verticales

Cada task es un camino completo (puerto → adaptador → aplicación → CLI → tests → doc cuando aplica), demostrable por sí mismo, con criterios, verificación e instrucciones deterministas.

### T1 — Un dueño de pantalla: la selección de embedder vive en el frame

El puerto `Ui` gana estado de selección central junto a `ACTIVE_PROGRESS` (`ports/ui.rs:74-99`); `TtyUi::select` deja de usar `dialoguer::Select` (`adapters/ui.rs:24-39`) y delega en el watcher de `ui_ratatui.rs:320-395`, único pintor y lector (↑/↓/Enter/Esc/Ctrl+C). Conservar la firma de `Ui::select` si es posible para no tocar los 6 fakes. El gate sigue cediendo el frame con `has_active_progress()` (`ui_ratatui.rs:232`). Si `ui_ratatui.rs` pasa de 500 líneas, extraer `adapters/ui_selection.rs`.

**Aceptación:** sin segundo `try_init()` en la selección; token de cancelación compartido con un solo lector; `int_ui_screen_ownership.rs` extiende el guard de `int_progress_spec.rs:161-184` a `select`/`input`/`panel`; fakes compilan sin cambiar el orden de colas; `dialoguer` permanece en `Cargo.toml:22` para `input`/`input_secret`/`line_menu` (R1).

**Verificación:** `just rust-test-filter int_ui_screen_ownership` · `just rust-test-filter int_progress_spec` · `just rust-ci`.

**Instrucciones:** (1) RED: crear `tests/int_ui_screen_ownership.rs` espejo de `int_progress_spec.rs:161-184` y confirmar que falla. (2) GREEN: estado central en `ports/ui.rs`; `TtyUi::select` renderiza en frame; reutilizar `is_cancel_key`/`RestoreOnDrop`; limpiar estado en **todo** exit y abort tipado. (3) Propagar solo lo necesario a `HeadlessUi` y fakes; no cambiar `for_install` (`adapters/ui.rs:215-227`). (4) Verificar `wc -l ui_ratatui.rs ≤ 500` o extracción hecha.

**Archivos:** `ports/ui.rs`, `adapters/ui.rs`, `adapters/ui_ratatui.rs` (+ `ui_selection.rs` si aplica), `tests/common/mod.rs`, `tests/int_ui_screen_ownership.rs` (nuevo).

| subagents | criteria | skills | tools | resources | conventions |
| --- | --- | --- | --- | --- | --- |
| `rust-engineer` (1º, secuencial), `rust-refactoring-specialist` (revisión del seam), `code-reviewer` (cierre) | Dueño único; firma conservada; guard cubre `select`/`input`/`panel`; sin segundo `try_init` | `rust-best-practices`, `codebase-design`, `clean-ddd-hexagonal`, `test-driven-development`, `incremental-implementation` | `read`, `grep`, `execute`, `shell`, `write`/`edit`, `question` | diagnosis §Root Cause 1; WORKFLOW C1; spec §§316-357; `int_progress_spec.rs:161-184` | `AGENTS.md`, `CODE_STYLE.md`, Justfile-first, `/tmp/opencode`, sin background, commit ≤72 + trailer |

### T2 — Install elige embedder primero; gate tras F5 y `models/` en el título

Separar en `application/embedder_menu.rs` la selección del gate/config; mover solo la selección al inicio del install (antes de F3, en la zona central de T1); dejar el test-embed detrás del venv (F5) para no romper ADR-015; mostrar `<vault>/.tepochcalli/models/` en el título del gate (`embedder_gate.rs:50`; ruta en `flow_cli.rs:49-59`). `install_progress_spec` (`:441-447`) intacto; cancel compartido compensa vía `purge_partials` (`embedder_gate.rs:64-66`).

**Aceptación:** al elegir Install aparece primero la selección y luego la barra de 7 hitos; gate después de F5; `--resume` con F6 hecha y la cola `HeadlessUi::for_install` no roban el índice; título del gate contiene `.tepochcalli/models/`; `run_f6_or_degraded` conserva degradación y exit 0.

**Verificación:** `just rust-test-filter int_embedder_menu` · `just rust-test-filter int_install_f4_f5` · `just rust-ci`.

**Instrucciones:** (1) RED: aserciones de orden en `int_embedder_menu.rs` y `int_install_f4_f5.rs`. (2) GREEN: extraer la selección de `run_phase6`; invocarla antes de `run_stages` y el gate tras el hito F5 (`advance_active_stage()`, `:315`); no tocar `install_progress_spec`. (3) Comprobar `take_gate_stage()` (`:327`,`:350`). (4) No cambiar `EMBEDDER_PATHS` ni `menu_order_is_the_adr_numbering` (`embedder_menu.rs:324-336`).

**Archivos:** `application/embedder_menu.rs`, `application/embedder_gate.rs`, `cli/install.rs`, `cli/install_phases.rs`, `tests/int_embedder_menu.rs`, `tests/int_install_f4_f5.rs`.

| subagents | criteria | skills | tools | resources | conventions |
| --- | --- | --- | --- | --- | --- |
| `rust-engineer` (tras A, paralelo), `test-engineer` (RED), `minimal-change-engineer` (solo mover selección) | Orden demostrable; gate tras F5; ADR-015 intacto; `models/` visible | `test-driven-development`, `incremental-implementation`, `rust-best-practices`, `doubt-driven-development` | `read`, `grep`, `execute`, `shell`, `write`/`edit`, `question` | WORKFLOW C1/C4; diagnosis §Solution 4; spec §§361-367; `flow_cli.rs:49-59`; ADR-015 | `AGENTS.md`, `CODE_STYLE.md`, `rust-test-filter`, `/tmp/opencode`, sin background, trailer |

### T3 — Layout de tres zonas, ETA a la derecha y responsive

Reestructurar `render_menu` (`ui_ratatui.rs:45-51`) y `render_stages` (`:142-148`) en ARRIBA (banner+progreso+spinner+ETA), CENTRO (mensajes/opciones/confirmaciones/selección) y ABAJO (menú H5+contacto). El ETA sale del `format!` de `:173-178` y va a columna derecha con `Layout::horizontal` (el campo `ProgressSpec.eta` ya existe en `ports/ui.rs:36`). Headers con `.wrap()`/elipsis (`:53-55`,`:150-152`); cota mínima para la fila Cancelar; sin pérdida a 80x24/40x12/30x8/20x6. Reescribir los tests que consagran el bug: `int_progress_spec.rs:73-94` y `:97-128`; crear `int_ui_layout.rs` con aserciones posicionales.

**Aceptación:** `int_ui_layout.rs` verifica ETA a la derecha y tres zonas en los 4 tamaños; Cancelar nunca desaparece; headers refluyen o se elipsan; sin dependencias nuevas; `render_progress` (`:211-218`) sigue con `eta: None`.

**Verificación:** `just rust-test-filter int_ui_layout` · `just rust-test-filter int_progress_spec` · `just rust-ci`.

**Instrucciones:** (1) RED: `int_ui_layout.rs` con `TestBackend` a los 4 tamaños y aserciones de posición. (2) Reescribir `int_progress_spec.rs:73-94`/`:97-128`. (3) GREEN: `Layout::horizontal` para cronómetro/ETA en zona superior; `Constraint::{Min,Flex}` en centro; `.wrap(Wrap { trim: true })` en headers. (4) Extraer `ui_selection.rs` si se supera 500 líneas.

**Archivos:** `adapters/ui_ratatui.rs` (+ `ui_selection.rs` si aplica), `tests/int_ui_layout.rs` (nuevo), `tests/int_progress_spec.rs`.

| subagents | criteria | skills | tools | resources | conventions |
| --- | --- | --- | --- | --- | --- |
| `rust-engineer` (tras A, paralelo), `test-engineer` (posicionales RED), `rust-refactoring-specialist` (si >500 líneas) | 3 zonas + ETA derecha en 4 tamaños; Cancelar presente; umbral respetado | `rust-best-practices`, `test-driven-development`, `incremental-implementation`, `codebase-design` | `read`, `grep`, `execute` (Context7 ratatui 0.30.2), `shell`, `write`/`edit`, `question` | diagnosis §Symptoms 2-4 y §Solution 2; WORKFLOW C2; `ports/ui.rs:27-37`; `CODE_STYLE.md` §Umbral | `AGENTS.md`, `CODE_STYLE.md`, Justfile-first, `/tmp/opencode`, sin background, trailer |

### T4 — Banner con semántica

`header_line` (`adapters/ui.rs:137-144`) dice «listo para instalar» cuando `installed_version()` (`application/installed.rs:17-20`) devuelve `None`, y muestra la versión instalada cuando exista; reutilizar `READY_NOTICE` (`domain/menu.rs:84`). **No tocar** `installed_version`, `home_view`, `MenuView` ni `installed_state` (`domain/menu.rs:100-112`). Actualizar literales `adapters/ui.rs:363` y `int_ui_menu.rs:66,80`.

**Aceptación:** sin pyproject el banner contiene `directorio listo para instalar`; con versión muestra esa versión (no `—`); `domain/menu.rs` byte-a-byte intacto; máquina H5 sin cambios.

**Verificación:** `just rust-test-filter int_ui_menu` · `just rust-test-filter header` · `just rust-ci`.

**Instrucciones:** (1) RED: ajustar los literales y confirmar fallo. (2) GREEN: `header_line` consulta `view.installed` y usa `READY_NOTICE` si es `None`. (3) `git diff domain/menu.rs` vacío.

**Archivos:** `adapters/ui.rs`, `tests/int_ui_menu.rs`.

| subagents | criteria | skills | tools | resources | conventions |
| --- | --- | --- | --- | --- | --- |
| `rust-engineer` (tras A, paralelo), `test-engineer` (literales RED), `minimal-change-engineer` (dominio intacto) | Semántica en dos estados; `READY_NOTICE` reutilizado; dominio sin cambios | `test-driven-development`, `rust-best-practices`, `codebase-design` | `read`, `grep`, `execute`, `shell`, `write`/`edit`, `question` | diagnosis §Solution 3; WORKFLOW C3; `int_ui_menu.rs:50-99`; `menu.rs:84` | `AGENTS.md`, `CODE_STYLE.md`, Justfile-first, `/tmp/opencode`, sin background, trailer |

### T5 — Sin TTY sin regresión + e2e con PTY

Con `--non-interactive`, `HeadlessUi` responde en el mismo orden y no emite marcadores de progreso por stderr (`e2e_ui.rs:288-323`). Añadir `e2e_install_tty.rs` con helper PTY para entrar en `try_init` (los e2e actuales usan pipes: `e2e_ui.rs:121,170,308`) y un test de que `models/` aparece en pantalla. Si el PTY es flaky en fuseblk: degradar a `int_ui_screen_ownership` + demo manual y **declarar la salvedad**, sin maquillar el gate.

**Aceptación:** `e2e_ui.rs:288-323` sigue verde sin `transcurrido`/`ETA`/`█`/`Cancelar — Esc` en stderr; evidencia de ruta TTY o salvedad documentada; cola de `for_install` intacta; 4 tests viejos reescritos.

**Verificación:** `just rust-test-filter e2e_install_tty` · `just rust-test-filter e2e_ui` · `just rust-ci`.

**Instrucciones:** (1) RED: crear `e2e_install_tty.rs` con helper PTY y aserción de `models/`; decidir **antes** de escribir código si se añade dependencia — `Cargo.toml` no tiene `portable-pty`/`nix`, y añadirla exige visto bueno del dueño (R1); vía preferida: degradar a `int` + demo manual. (2) `just rust-test-filter e2e_ui`. (3) GREEN: integrar T1–T4 y demo manual con `uvx tepochcalli --payload <fixture local> --skip-model` sin red. (4) Documentar salvedad si el PTY no es estable.

**Archivos:** `tests/e2e_install_tty.rs` (nuevo), `tests/e2e_ui.rs`, `tests/common/mod.rs` (solo si cambia el contrato), `tests/int_ui_screen_ownership.rs`.

| subagents | criteria | skills | tools | resources | conventions |
| --- | --- | --- | --- | --- | --- |
| `test-engineer` (tras T1–T4), `test-results-analyzer` (flakiness), `code-reviewer` (salvedad honesta) | No-TTY sin regresión; PTY o salvedad; 4 tests reescritos | `test-driven-development`, `rust-best-practices`, `doubt-driven-development`, `incremental-implementation` | `read`, `grep`, `execute`, `shell`, `write`/`edit`, `question` | diagnosis §Solution 7; WORKFLOW C5; `e2e_ui.rs:121,170,288-323`; `Cargo.toml:21-23` | `AGENTS.md` (R1), `CODE_STYLE.md` (`int_*`/`e2e_*`), `/tmp/opencode`, sin background, trailer |

### T6 — Receta de densidad de comentarios (banda 10–15 %, sin compactar)

Añadir al `Justfile` una receta que mida densidad de comentarios sobre `.rs`/`.py` versionados de producto, excluyendo gitignored (`venv/`, `db/`, `models/`, `target/`) y el payload congelado `.opencode/skills/**`. Declarar limitaciones: no cuenta docstrings Python ni bloques `/* */`; el recuento varía con `///`/`//!`. Global medido = **7,55 %** ⇒ **no procede limpieza**; Rust `src` = 16,49 % queda como *watch*. Documentar en `docs/BACKLOG.md` §8 (y `docs/CODE_STYLE.md` si aplica), sin tocar código.

**Aceptación:** `just --list` muestra la receta con su nombre real verificado; reproduce 247 ficheros / 61.900 líneas / 4.676 comentarios / 7,55 % global; excluidores y limitaciones declarados; cero cambios de densidad en código.

**Verificación:** `just --list` · ejecutar la receta y comparar con el comando `find`/`awk` de `fix04` · `just md-lint` si se tocó documentación.

**Instrucciones:** (1) Partir del comando validado en el diagnóstico (`git ls-files '*.rs' '*.py' | grep -v '/\.opencode/'` + `awk`). (2) Añadir la receta al Justfile y **verificar su nombre con `just --list` antes de citarlo**. (3) Fila de §8 con el resultado y la salvedad de Rust `src` como watch. (4) No ejecutar limpieza.

**Archivos:** `Justfile`, `docs/BACKLOG.md` §8, `docs/CODE_STYLE.md` (solo si se documenta allí).

| subagents | criteria | skills | tools | resources | conventions |
| --- | --- | --- | --- | --- | --- |
| `minimal-change-engineer` (paralelo, sin solapamiento), `docs-writer` (fila §8), `code-reviewer` (excluidores) | 7,55 % reproducido; excluidores declarados; sin compactar | `bash-defensive-patterns`, `documentation-and-adrs`, `incremental-implementation` | `read`, `grep`, `shell`, `write`/`edit`, `execute`, `question` | diagnosis §Política de comentarios; `docs/BACKLOG.md` §8; `Justfile` (sin receta hoy) | `AGENTS.md`, `CODE_STYLE.md`, sin background, commit ≤72 + trailer |

### T7 — Bump one-version a `0.1.0-beta.4` + enmienda de spec y BACKLOG

Bump en los **11 ficheros** del precedente `9b29a4c`: `.github/ISSUE_TEMPLATE/bug_report.yml`, `.github/workflows/release.yml`, `CHANGELOG.md`, `CONTRIBUTING.md`, `THIRD-PARTY.md`, `crates/tepochcalli/Cargo.lock`, `crates/tepochcalli/Cargo.toml`, `crates/tepochcalli/installers/install.ps1`, `crates/tepochcalli/installers/install.sh`, `obsidian-workspace/.tepochcalli/pyproject.toml`, `obsidian-workspace/.tepochcalli/uv.lock`. `Cargo.toml`/`lock` vía `just rust-lock-refresh`; `pyproject.toml`/`uv.lock` vía `just payload-lock` + `just payload-lock-check`; `THIRD-PARTY.md` vía `just third-party`. Enmendar `specs/spec-installer-wizard.md` §§279/316-357/361-367 y añadir fila a `docs/BACKLOG.md` §8. **Sin tag, Release, PyPI ni ADR.**

**Aceptación:** 11 ficheros en `0.1.0-beta.4`; locks regenerados y `payload-lock-check` verde; spec enmendada; sin ADR; `git tag --list 'tepochcalli-v*'` sin tag nuevo.

**Verificación:** `just rust-lock-refresh` → `just payload-lock` → `just payload-lock-check` → `just third-party` → `just rust-ci` → `just quality` → `just md-lint` → `just ci` completo (requisito del dueño; **nunca en GitHub Actions**). Demo manual con CLI reportando `0.1.0-beta.4`.

**Instrucciones:** (1) Confirmar los 11 con `git show --stat 9b29a4c`. (2) Cambiar versión en `Cargo.toml` y `pyproject.toml`; ejecutar `rust-lock-refresh` y `payload-lock`. (3) Regenerar `THIRD-PARTY.md`. (4) Enmendar spec y §8; sin ADR. (5) Verificar tags y gates.

**Archivos:** los 11 + spec + BACKLOG §8 + WORKFLOW §Phase 6.9 (checkpoint final).

| subagents | criteria | skills | tools | resources | conventions |
| --- | --- | --- | --- | --- | --- |
| `git-workflow-master` (último), `docs-writer` (spec/BACKLOG), `minimal-change-engineer` (auditar 11), `code-reviewer` (gate final) | 11 alineados; locks listos; sin tag/Release/ADR | `git-workflow-and-versioning`, `documentation-and-adrs`, `incremental-implementation`, `code-review-and-quality` | `read`, `grep`, `shell` (git/just, sin push/tag), `write`/`edit`, `execute`, `question` | `git show --stat 9b29a4c`; WORKFLOW C7; spec §§279/316-357/361-367; BACKLOG §8; ADR-014 | `AGENTS.md`, `CODE_STYLE.md`, `/tmp/opencode`, sin background, commit ≤72 + trailer, sin deploy |

## 5. Checkpoints

| Checkpoint | Tras | Gates (nombres reales del Justfile) | Criterio de paso |
| --- | --- | --- | --- |
| **A** | T1 | `just rust-test-filter int_ui_screen_ownership` · `just rust-test-filter int_progress_spec` · `just rust-ci` | Dueño único probado; `wc -l ui_ratatui.rs ≤ 500` o extracción; revisión de `code-reviewer` |
| **B** | T3 | `just rust-test-filter int_ui_layout` · `just rust-test-filter int_progress_spec` · `just rust-ci` | Posiciones ETA/zonas correctas a los 4 tamaños; Cancelar presente; umbral de líneas |
| **C** | T6 | `just --list` · ejecutar la receta nueva · `just md-lint` si aplica | 7,55 % global reproducido; excluidores declarados; sin compactar. Independiente de A/B |
| **D** | T7 | `just rust-lock-refresh` · `just payload-lock` · `just payload-lock-check` · `just third-party` · `just rust-ci` · `just quality` · `just md-lint` · `just ci` completo | 11 ficheros en `0.1.0-beta.4`; demo documentada; sin tag nuevo; **sin deploy** |

Verificación de nombres: `rust-test-filter` (Justfile:374) es la receta Rust; **`test-file` (Justfile:507) es Python, no usarla aquí**. Confirmados: `rust-ci` (386), `quality` (575), `md-lint` (531), `ci` (592), `rust-lock-refresh` (329), `payload-lock` (332), `payload-lock-check` (336), `third-party` (536). La receta de densidad no existe hoy: su nombre se fija en T6 y se verifica con `just --list` antes de citarlo.

## 6. Riesgos

| Riesgo | Impacto | Mitigación |
| --- | --- | --- |
| Handshake watcher↔selección deadlock-prone | Alto — F6 vuelve a bloquearse | Limpiar estado en todo exit y abort tipado; checkpoint A |
| 6 fakes y 4 tests consagran contrato/orden actuales | Alto — regresión silenciosa | Seam que conserva `Ui::select`; RED primero en T1/T2 |
| `--resume` y cola `HeadlessUi::for_install` roban el índice | Medio — embedder distinto | Aserciones de orden en `int_install_f4_f5.rs` / `int_embedder_menu.rs` |
| `ui_ratatui.rs` a 494 líneas | Medio — gate de estilo | Extraer `ui_selection.rs` al pasar de 500; checkpoints A/B |
| PTY flaky en fuseblk | Medio — gate rojo no reproducible | Degradar a `int_ui_screen_ownership` + demo manual y declarar salvedad; **no maquillar** |
| `dialoguer` sigue en `Cargo.toml:22` | Bajo — dependencia aparentemente muerta | Queda para `input`/`input_secret`/`line_menu` (R1) |
| H9 swap/device prompt con el mismo patrón | Medio — deuda futura | Declarar como deuda, fuera de esta fase |
| **Borrado de los dos ficheros de tareas** | Medio — referencias rotas | Sobrescritura completa + `grep` de referencias entrantes; reportar sin modificar otros docs |
| Locks desincronizados en el bump | Medio — CI rojo | `rust-lock-refresh` + `payload-lock` + `payload-lock-check` en checkpoint D |
