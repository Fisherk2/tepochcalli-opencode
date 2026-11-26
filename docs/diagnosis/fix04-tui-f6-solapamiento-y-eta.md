# Diagnosis: Solapamiento de la TUI en F6, ETA ilegible y pantalla no responsive

**Issue:** local (reporte del dueño, 2026-11-25; dos sesiones de análisis en lectura) — sin issue remoto
**Date:** 2026-11-25
**Severity:** high
**Status:** diagnosed

---

## Summary

Síntoma nuevo (no una actualización de [fix02](fix02-wizard-gate-modelinvalid-y-f6-silencioso.md)
ni de [fix03](fix03-desinstall-lento-por-venv.md)): en la rama `fix/tui-issues` (HEAD `bf077d3`,
`git status` limpio) el wizard queda bloqueado al llegar a la selección de embedder de F6 porque
dos dueños de terminal pintan y leen el mismo TTY a la vez: el watcher de `run_stages` y el prompt
de `dialoguer` usado por `TtyUi::select`. El resultado visible es una pantalla mezclada donde solo
la cancelación responde. En la misma pantalla, el ETA no tiene zona propia: se interpola dentro de
la fila del spinner y, en el install, ni siquiera se declara (`eta: None`), así que se lee `—`.
Los layouts son rígidos, recortan los headers y no reaccionan al resize. Severidad ALTA: bloquea la
instalación interactiva; no hay pérdida de datos. Este diagnóstico registra además la decisión del
dueño sobre la política de comentarios (§Política de comentarios).

## Symptoms

1. **F6 se mezcla y no deja elegir; solo cancelar funciona.** La barra exterior de siete hitos
   envuelve F3..F8 con `ui.run_stages` (`crates/tepochcalli/src/cli/install_phases.rs:86-98`); F6
   se alcanza en `crates/tepochcalli/src/cli/install_phases.rs:340` →
   `crates/tepochcalli/src/cli/install.rs:433` →
   `crates/tepochcalli/src/application/embedder_menu.rs:129`, donde
   `deps.ui.select("Embedding provider", &shown, 0)` abre el prompt de `dialoguer`. El watcher de
   la barra sigue repintando y consumiendo teclas; el token de cancelación es compartido
   (`crates/tepochcalli/src/cli/install_phases.rs:323-324`), por lo que Esc/Ctrl+C sí llega y
   flechas/Enter quedan repartidos entre dos lectores.

2. **ETA mezclado con el spinner y sin valor en el install.**
   `crates/tepochcalli/src/adapters/ui_ratatui.rs:172-179` interpola `spinner_frame(tick)`,
   `clock(elapsed)` y `ETA` en un único `Paragraph` de una sola fila (`clock` en `:127-130`).
   `crates/tepochcalli/src/ports/ui.rs:27-37` define `ProgressSpec { eta: Option<Duration> }`
   (`:36`) sin destino de render propio; el único productor con valor es
   `crates/tepochcalli/src/application/swap.rs:148-152`. El install declara `eta: None`
   (`crates/tepochcalli/src/cli/install_phases.rs:441-447`) y `render_progress` también
   (`crates/tepochcalli/src/adapters/ui_ratatui.rs:211-218`), así que la fila muestra `ETA —`.

3. **TUI no responsive.** `render_menu` usa
   `Layout::vertical([Length(1), Min(1), Length(notice_rows), Length(3)])`
   (`crates/tepochcalli/src/adapters/ui_ratatui.rs:45-51`, mínimo 8 filas); `render_stages` usa
   `[Length(1), Length(3), Length(1), Min(3))]` (`:142-148`, también mínimo 8, con hasta 8 líneas
   de detalle en `Min(3)` en `:181-206`). Los headers no llevan `.wrap()` (`:53-55`, `:150-152`):
   se recortan, no refluyen. No hay `terminal.size()`, `Viewport` ni guard de tamaño; el resize
   se ignora literalmente (`:450`) y el watcher solo redibuja cada 100 ms (`:350-374`).

4. **Falta el rediseño acordado.** Hoy el menú es header → lista → aviso → contacto; el progreso
   es header → gauge → spinner+ETA → detalle; y la selección de embedder es un prompt de
   `dialoguer`, no un panel central. No existe la zona central para mensajes, opciones,
   confirmaciones y selección, ni la franja inferior con el menú H5 y el contacto.

## Root Cause

> ¿Por qué ocurre? → Rankeado de la causa última a las consecuencias:

1. **CRITICAL — dos dueños de terminal en F6.** `TtyUi::select` usa `dialoguer::Select`
   (`crates/tepochcalli/src/adapters/ui.rs:24-39`), que escribe en stderr y lee teclas con
   `console::Term::read_key`. Al mismo tiempo, el watcher de `run_stages`
   (`crates/tepochcalli/src/adapters/ui_ratatui.rs:344-374`: `event::read()` en `:355`, redibujado
   en `:365-367` cada 100 ms) repinta la pantalla completa. `run_progress` **sí** tiene el guard
   `has_active_progress()` (`crates/tepochcalli/src/adapters/ui_ratatui.rs:232`), pero `select` no
   lo tiene: se invoca desde dentro de la barra activa sin cederla. Ambos comparten el token de
   cancelación (`crates/tepochcalli/src/cli/install_phases.rs:323-324`). Causa última: dos
   renderers y dos lectores del mismo tty; consecuencia: no se puede seleccionar, solo cancelar.

2. **IMPORTANT — ETA sin zona de render.** El único `eta` declarado
   (`crates/tepochcalli/src/application/swap.rs:148-152`) acaba dentro del `format!` del spinner
   (`crates/tepochcalli/src/adapters/ui_ratatui.rs:173-178`) y el layout solo es vertical
   (`:142-148`): no hay columna derecha que lo separe del cronómetro ni hueco para su contenido.

3. **IMPORTANT — layouts rígidos sin guard de tamaño.** Las cotas fijas de `:45-51` y `:142-148`
   y los headers sin `.wrap()` (`:53-55`, `:150-152`) asumen un terminal suficientemente alto y
   ancho; sin `terminal.size()`/`Viewport`, en 40x12/30x8/20x6 se recorta y la fila Cancelar
   queda sin cota mínima.

## Impact

| Dimension | Assessment |
| ----------- | ------------ |
| Users affected | Todos los usuarios que instalan desde un TTY real y quieren elegir embedder |
| Functionality | Broken — F6 no permite seleccionar; degradación de legibilidad del progreso |
| Data integrity | Safe — la purga de `embedder_gate.rs:64-66` solo toca snapshots nuevos del modelo |
| Reproducibility | Always en TTY; nunca sin TTY |

No hay pérdida de datos: ante `UserAborted`, `crates/tepochcalli/src/application/embedder_gate.rs:64-66`
llama a `purge_partials(vault, &before)` sobre el estado previo. CI y `--non-interactive` no se
afectan: las guardas de `is_terminal` en `crates/tepochcalli/src/adapters/ui.rs:65`, `:74` y `:89`
dejan correr la operación en línea sin abrir pantalla.

## Environment

- **Platform:** Linux; montaje fuseblk/NTFS-3G del repo (el `CARGO_TARGET_DIR` se fija bajo `/tmp/opencode/`).
- **Version:** rama `fix/tui-issues` creada desde `develop` en `bf077d3`; `git status` limpio; wizard `0.1.0-beta.3`.
- **Configuration:** TTY real (`stdout` y `stdin`) ⇒ full-screen ratatui 0.30 + `crossterm` 0.29; sin TTY ⇒ fallback line-based. Sin guard de tamaño de terminal.

## Proposed Solution

Decisiones ya tomadas por el dueño; pasos, sin código:

1. **Un único dueño de pantalla.** Eliminar `dialoguer` de F6 y renderizar la elección como
   **estado del frame ratatui**, con el watcher como único pintor y único lector de teclas.
   Se descarta extender el guard `has_active_progress()` a `select`: eso dejaría dos dueños.

2. **Layout compartido de tres zonas** para `render_menu` y `render_stages`:
   - ARRIBA: banner + progreso + spinner + ETA; el ETA va en columna derecha mediante
     `Layout::horizontal`, fuera del `format!` que hoy lo mezcla con el spinner (`:173-178`).
   - CENTRO: mensajes, avisos, opciones, confirmaciones y la selección de embedder, con
     `Min`/`Flex` y cota mínima para la fila Cancelar.
   - ABAJO: menú H5 (`Install`/`Update`/`Change Embedder`/`Desinstall`/`Exit`) + contacto.
   Headers con `.wrap()` o elipsis.

3. **Banner.** `header_line` (`crates/tepochcalli/src/adapters/ui.rs:137-144`) debe decir
   «listo para instalar» cuando `installed_version()`
   (`crates/tepochcalli/src/application/installed.rs:17-20`, que lee
   `<vault>/.tepochcalli/pyproject.toml`) devuelve `None`, y mostrar la versión instalada cuando
   exista. Reutilizar `READY_NOTICE` (`crates/tepochcalli/src/domain/menu.rs:84`). No tocar
   `installed_version`, `home_view`, `MenuView` ni la máquina de estados `installed_state`
   (`crates/tepochcalli/src/domain/menu.rs:100-112`).

4. **Flujo install.** Al elegir 🔵 Install, la selección de embedder es lo primero en la zona
   central; tras confirmar, empieza la instalación. Mover **solo la selección**: el gate
   test-embed se queda tras el venv (F5) para no romper ADR-015. Mostrar en pantalla el
   directorio de descarga del modelo (`<vault>/.tepochcalli/models/`, calculado como `HF_HOME` /
   `SENTENCE_TRANSFORMERS_HOME` en `crates/tepochcalli/src/application/flow_cli.rs:49-59`) en el
   título del gate (`crates/tepochcalli/src/application/embedder_gate.rs:50`).

5. **Contrato `Ui`.** Añadir una operación/estado de render central y propagarlo a `TtyUi`,
   `HeadlessUi`, `wait_key` y a los fakes `ScriptedUi`/`TapUi`/`StagesUi`. El campo `eta` ya existe
   en `crates/tepochcalli/src/ports/ui.rs:36`: solo cambia su ubicación en el render.

6. **Documentación y versión.** Enmendar `specs/spec-installer-wizard.md` en las secciones
   «Enmienda 2026-11-18 — flujo destino» (`:279`), «TUI full-screen y menú H5» (`:316-357`) y
   «Casos de uso destino (H6)» (`:361-367`), y añadir una fila a `docs/BACKLOG.md` §8. Sin ADR
   nuevo (UX reversible; D1-D8 intactas). Bump one-version a `0.1.0-beta.4` (11 ficheros, sin
   tag, Release ni PyPI).

7. **Tests.** `int_ui_layout.rs` con aserciones **posicionales** (ETA a la derecha, tres zonas)
   a 80x24/40x12/30x8/20x6; `int_ui_screen_ownership.rs` extendiendo
   `crates/tepochcalli/tests/int_progress_spec.rs:161-184` a `select`/`input`/`panel`;
   `e2e_install_tty.rs` con helper PTY (los e2e actuales usan pipes —
   `crates/tepochcalli/tests/e2e_ui.rs:121`, `:170`, `:308` — y nunca entran en `try_init`);
   regresión no-TTY (`crates/tepochcalli/tests/e2e_ui.rs:288-323`) y test de que `models/`
   aparece en pantalla. Actualizar los tests que hoy consagran el bug:
   `crates/tepochcalli/tests/int_progress_spec.rs:73-94` (contains ETA) y `:97-128` (fila propia
   por primer carácter), `crates/tepochcalli/src/adapters/ui.rs:363`, y
   `crates/tepochcalli/tests/int_ui_menu.rs:66,80` (literales del banner).

## Workarounds

> ⚠️ **WORKAROUND**
> No existe forma de elegir embedder en un TTY real mientras existan dos dueños de pantalla:
> solo Esc/Ctrl+C cancela. Como mitigación temporal, usar la ruta no-TTY / CI
> (`--non-interactive`, sin `is_terminal`) si el caso de uso admite la configuración por defecto;
> en caso contrario, cancelar y esperar al fix. No es una solución para el flujo destino H6.

## Recurrences

| Date | Similar Issue | Variation |
| --- | --- | --- |
| 2026-11-25 | [fix02](fix02-wizard-gate-modelinvalid-y-f6-silencioso.md) | Mismo F6, pero fallo silencioso de `embed-check`, no solapamiento de terminal |
| 2026-11-25 | [fix03](fix03-desinstall-lento-por-venv.md) | Misma release beta.3; desinstall lento por el venv, no TUI |

_Los tres síntomas comparten release, no mecanismo; no hay patrón de 3+ repeticiones que automatizar._

## file:lines evidencia

Rutas Rust relativas a `crates/tepochcalli/src/`; rutas de tests relativas a `crates/tepochcalli/tests/`.

| Evidencia (`ruta:línea`) | Qué sostiene |
| --- | --- |
| `ui_ratatui.rs:45-51` | Layout vertical del menú (mínimo 8 filas) |
| `ui_ratatui.rs:142-148` | Layout vertical del progreso (mínimo 8 filas) |
| `ui_ratatui.rs:172-179` | Spinner + cronómetro + ETA en un solo `Paragraph` |
| `ui_ratatui.rs:232` | Guard `has_active_progress()` solo en `run_progress` |
| `ui_ratatui.rs:344-374` | Watcher: `event::read()` y redibujado cada 100 ms |
| `adapters/ui.rs:24-39` | `TtyUi::select` con `dialoguer::Select` |
| `adapters/ui.rs:137-144` | `header_line` sin estado «listo para instalar» |
| `install_phases.rs:86-98` | `run_stages` envuelve F3..F8 |
| `install_phases.rs:323-324` | Token de cancelación compartido con F6 |
| `install_phases.rs:340` | Entrada a F6 |
| `install_phases.rs:441-447` | Install con `eta: None` |
| `embedder_menu.rs:129` | `select("Embedding provider", …)` |
| `ports/ui.rs:27-37` | `ProgressSpec.eta` sin destino de render |
| `installed.rs:17-26` | `installed_version()` lee `<vault>/.tepochcalli/pyproject.toml` |
| `domain/menu.rs:84`, `domain/menu.rs:100-112` | `READY_NOTICE` y máquina de estados, sin tocar |
| `flow_cli.rs:49-59` | `HF_HOME`/`SENTENCE_TRANSFORMERS_HOME` → `models/` |
| `embedder_gate.rs:50` | Título del gate de descarga |

Complementarias: `ui_ratatui.rs:127-130` (`clock`), `:150-152` y `:53-55` (headers sin `.wrap()`),
`:181-206` (8 líneas de detalle), `:211-218` (`render_progress` con `eta: None`), `:450` (resize
ignorado); `application/swap.rs:148-152` (único productor de ETA); `cli/install.rs:433`;
`application/embedder_gate.rs:64-66`; `adapters/ui.rs:65,74,89` (guardas no-TTY).

## Política de comentarios (observación adicional)

El dueño pidió en el mismo ticket una banda del **10–15 %** de comentarios sobre todo el codebase,
con limpieza si se excede. Medición lectora de las dos sesiones de análisis:

| Ámbito | Ficheros | Líneas | Comentarios | Densidad |
| --- | --- | --- | --- | --- |
| GLOBAL | 247 | 61.900 | 4.676 | **7,55 %** |
| Rust `src` | 60 | 13.183 | 2.174 | 16,49 % (sobre el aviso del 15 %) |
| Rust `tests` | 50 | 15.953 | 1.636 | 10,26 % |
| Python `flow` | 19 | 3.581 | 79 | 2,21 % |
| Python `mcp` | 23 | 3.705 | 93 | 2,51 % |
| Python `tests` | 95 | 25.478 | 694 | 2,72 % |

Comando de medición (`find`/`awk` en lectura; recuento por línea que empieza con `//` en Rust o
`#` en Python), que reproduce los totales de ficheros y líneas:

```bash
files=$(git ls-files '*.rs' '*.py' | grep -v '/\.opencode/')
echo "files=$(printf '%s\n' "$files" | wc -l) lines=$(printf '%s\n' "$files" | xargs cat | wc -l)"
printf '%s\n' "$files" | xargs awk '/^[[:space:]]*(\/\/|#)/ {n++} END {print n+0}'
```

Top-5 de densidad en Rust `src`: `ports/net.rs` 47,37 %, `ports/payload.rs` 44,07 %,
`domain/embedder.rs` 41,03 %, `ports/host.rs` 40,82 %, `ports/ui.rs` 31,97 %.

Conclusión: el global (7,55 %) está **por debajo de la banda**, así que **no procede limpieza**.
Rust `src` queda como _watch_ por estar por encima del aviso del 15 %, sin compactar hoy. No existe
receta `just` que mida esta densidad (búsqueda negativa en `Justfile`, `scripts/` y `.github/`):
**acción acordada: añadir una receta de medición**. Alcance del medidor: `.rs` y `.py` versionados
de producto; excluye artefactos gitignored (`venv/`, `db/`, `models/`, `target/`) y el payload
congelado `.opencode/skills/**`. Limitaciones declaradas: no cuenta docstrings Python ni bloques
`/* */`, y el recuento exacto de comentarios varía ligeramente según se traten los doc comments
`///`/`//!` y los atributos `#[…]`; las cifras de la tabla son las de las sesiones de análisis.

## References

- [Plantilla de diagnóstico](diagnosis-template.md) · [Guía de estilo](../../docs/CODE_STYLE.md) · [Arquitectura](../../docs/ARCHITECTURE.md)
- [spec-installer-wizard](../../specs/spec-installer-wizard.md) §§279, 316-357, 361-367 · [BACKLOG](../../docs/BACKLOG.md) §8
- [ADR-014](../../docs/adr/adr-014-distribucion-uvx-pypi.md) · [ADR-015](../../docs/adr/adr-015-dispositivo-inferencia-wizard.md)
- Tests: `crates/tepochcalli/tests/{int_progress_spec.rs,int_ui_menu.rs,e2e_ui.rs}` ·
  `crates/tepochcalli/src/adapters/{ui.rs,ui_ratatui.rs}` · `crates/tepochcalli/src/application/*`
- Sesiones de análisis (subsessions): `ses_deaf3f1c5ffe67dAYawuDiZEzc` y
  `ses_deaf3f1c4ffeMq1NwWY6GhPR8a`. No hay fuentes web nuevas.

---

_Diagnosis created by `/diagnosis`. Update this file if the fix reveals additional insights._
