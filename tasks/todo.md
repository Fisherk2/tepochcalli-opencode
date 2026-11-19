# TODO — Phase 6.5 (wizard, flujo destino H5-H11)

> Checklist operativo del plan: [tasks/plan.md](./plan.md). Fuente de verdad del requisito:
> [docs/BACKLOG.md](../docs/BACKLOG.md) §2 «Wizard de instalación: flujo destino (2026-11-18)».
> Actualizado el 2026-11-19 por Moctezuma. **Sin publicar en ningún gestor de paquetes.**

**Leyenda:** `[ ]` pendiente · `[~]` en curso · `[x]` hecho · `[!]` bloqueado (motivo en la línea) · `[!]` ⇒ exige decisión del dueño.

---

## 🔒 Guardarraíles (aplican a TODA la fase)

- [ ] **Ningún publish.** Ni `twine upload`, ni `pypi` auth, ni `maturin publish`, ni un job de
      upload en CI. `just rust-publish-dry-run` (crates.io) tampoco se ejecuta: es otro registro.
- [ ] **Ningún binario ni rueda versionado.** `.whl` y `target/` fuera de git.
- [ ] **Ningún cambio en el payload** `obsidian-workspace/` salvo orden explícita del dueño.
- [ ] **Ninguna decisión D1-D8 re-litigada** en código. ADR nuevo solo con aprobación.
- [ ] **Un dueño por fichero** en cada momento: `lib.rs` y `cli/commands.rs` los escribe un solo frente.
- [ ] **`CARGO_TARGET_DIR` siempre bajo `/tmp/opencode/`** → `just rust-ci /tmp/opencode/cargo-target`.
- [ ] **Comandos vía `just`**, nunca `cargo`/`uv`/`pytest` crudos.

---

## 🔄 Ronda 0 — Formalización (secuencial, 1 frente)

### T0 · Aceptar ADR-014 y ADR-015

*Dueño: `docs-writer` · Revisión: `code-reviewer`*

- [ ] `Status: Accepted` + fecha de aprobación 2026-11-19 en `docs/adr/adr-014-distribucion-uvx-pypi.md`
- [ ] `Status: Accepted` + fecha de aprobación 2026-11-19 en `docs/adr/adr-015-dispositivo-inferencia-wizard.md`
- [ ] Nota de «no entra en vigor hasta la aprobación del usuario» → constancia de aprobación (sin borrar el historial *Proposed*)
- [ ] §4.3 de ADR-014: `maturin`/PyPI/`ratatui`/`crossterm` quedan **aprobadas como deps**; la publicación sigue **no ejecutada**
- [ ] `Decision Makers`: «Dueño del repo» → «Fisherk2» en ambos ADR
- [ ] **ADR-003, ADR-004, ADR-007, ADR-008, ADR-011, ADR-013 byte-idénticos** (`git diff --exit-code`)
- [ ] `grep -rn 'Status: Proposed' docs/adr/` → vacío
- [ ] `just md-lint` → 0 issues

### T1 · Enmiendas Accepted + versión alineada + des-GATE

*Dueño: `docs-writer` · Revisión: `code-reviewer` · Depende de: T0*

- [ ] `specs/spec-installer-wizard.md`: enmienda 2026-11-18 → **Accepted**; deja de decir «no se aprueba ni se implementa aquí»
- [ ] `specs/spec-embeddings.md`: enmienda 2026-11-18 → **Accepted**; formaliza `[embedding].device` electivo
- [ ] `crates/tepochcalli/Cargo.toml` → `version = "0.1.0"` (detrás de la canónica `0.1.0` del payload) → **cierra TD-45**
- [ ] `docs/WORKFLOW.md` §Phase 6.5: «GATED, no ejecutable» → desbloqueada, con las 4 precondiciones resueltas
- [ ] `docs/TECH_DEBT.md`: TD-46 cerrada, TD-45 cerrada, **TD-51** nueva (retiro de cargo-dist diferido)
- [ ] `docs/BACKLOG.md` §8: filas de los cambios estructurales
- [ ] `SPEC.md` §Boundaries: `maturin`/PyPI y `ratatui`/`crossterm` registradas como **aprobadas** con fecha
- [ ] `grep -rn 'Proposed' specs/spec-installer-wizard.md specs/spec-embeddings.md` → vacío
- [ ] `just md-lint` → 0 issues

### 🛑 Checkpoint 0 — el FTR está registrado

- [ ] Las 4 precondiciones de `docs/WORKFLOW.md:299` están marcadas como resueltas
- [ ] Revisión de `code-reviewer` con contexto limpio: **APROBAR**
- [ ] Commit único (documental): `docs: acepta ADR-014/015 y abre Phase 6.5`

---

## ⚡ Ronda 1 — Paralela (3 frentes simultáneos)

### T2 · Sondas de viabilidad del empaquetado 🚦 PUERTA DE PARADA

*Dueño: `build-engineer` · Si falla: `debugger` · Depende de: T1*

> Ejecutar **antes** que T3. Sin veredicto, T3 no se escribe.

- [ ] **Sonda A:** crate de prueba con `lib.rs` + `main.rs` y `bindings = "bin"` → `maturin build` sin error
- [ ] Sonda A (cont.): `unzip -l` de la rueda → **no** arrastra el rlib
- [ ] **Sonda B:** `uvx --from <rueda local> <cmd>` ejecuta el binario desde la rueda
- [ ] Sonda B (cont.): si `--from` no acepta ruta local → probar `uv tool install <rueda>` + `uv tool run --from` y documentar el camino válido
- [ ] **Sonda C:** `maturin build` sobre el crate real → nombre de rueda con la convención esperada
- [ ] Informe en el cuerpo del commit: veredicto por sonda + comando exacto + salida cruda
- [ ] `git status --short` sin binarios ni ruedas

### T4 · H9 — dispositivo de inferencia electivo (TD-47)

*Dueño: `rust-engineer` · Revisión: `code-reviewer` · Depende de: T1*

- [ ] `config/presets.rs`: `Preset` gana `device`; `presets.toml` lo declara en las 2 entradas
- [ ] `application/embedder_menu.rs`: pregunta explícita de dispositivo (`cpu` preseleccionado)
- [ ] Sin GPU ⇒ `cuda` **deshabilitada con razón visible** «GPU no detectada» (nunca oculta)
- [ ] `application/embedder_config.rs`: `local_config()` escribe el dispositivo **elegido** (fin del hardcode `device = "cpu"`)
- [ ] `application/swap.rs`: `picked_config_body()` **preserva** el `device` existente en `config embedder`
- [ ] Autoselección en runtime **sigue rechazada** (sin `device` ⇒ default `cpu`, sin tocar GPU)
- [ ] Dispositivo forzado no disponible ⇒ **advertencia** `medido`, nunca bloqueo
- [ ] Tests nuevos: `int_embedder_menu.rs` (pregunta + GPU ausente) y `int_presets.rs` (parseo de `device`)
- [ ] Test de no-destructividad: TOML con `device = "cuda:0"` sobrevive a `config embedder`
- [ ] `just rust-ci /tmp/opencode/cargo-target` verde

### T6 · TD-50 — test de la guarda anti-exfiltración

*Dueño: `python-pro` · Revisión: `test-engineer` · Depende de: T1 · **Pythón, no Rust: no choca con T2/T4***

- [ ] Test unitario que ejercita `flow/tepochcalli_flow/config.py:357-369` con `://`, `http` y `@` en `model`
- [ ] Afirma el fallback al modelo default **con warning**
- [ ] El test **falla** si se desactiva la guarda (mutación verificada y revertida)
- [ ] Vive en el módulo `test-unit` (≤10 min), no en la suite pesada
- [ ] `just python-test-unit` y `just typecheck` verdes

### 🛑 Checkpoint 1 — veredicto de viabilidad (tras T2)

- [ ] Veredicto por sonda con comando y salida cruda
- [ ] **Si alguna sonda es inviable sin workaround ⇒ PARAR y consultar al dueño antes de T3**

---

## 🔀 Ronda 2 — Paralela (2 frentes simultáneos)

### T3 · Canal `uvx`: rueda preparada y verificada en local

*Dueño: `build-engineer` · Revisión: `deployment-engineer` · Depende de: T2*

- [ ] `crates/tepochcalli/pyproject.toml` nuevo: `[build-system] maturin`, `[project]` name `tepochcalli` v `0.1.0`, `[project.scripts] tepochcalli = "tepochcalli:main"`, `[tool.maturin] bindings = "bin"`
- [ ] Receta `just rust-wheel` (build + lista la rueda)
- [ ] Receta `just rust-wheel-verify` (contenido, versión, script y **ejecución real**)
- [ ] `uvx --from <rueda local> tepochcalli --help` imprime la ayuda ⇒ el canal sirve el binario
- [ ] CI: el workflow **construye** ruedas para la matriz de targets y las sube como artefactos
- [ ] CI: **no existe paso de publicación**; comentario que lo declara explícitamente
- [ ] `dist.toml` **NO se borra** en esta fase (TD-51) — si se reescribe `release.yml`, los dos workflows conviven sin colisionar nombres
- [ ] `grep -rn 'twine\|pypi upload\|maturin publish' .github/` → solo comentarios que declaran que **no** se publica
- [ ] `git status --short` sin ninguna `.whl`

### T5 · H7 Update + H8 Desinstall (TD-48)

*Dueño: `rust-engineer` · Revisión: `code-reviewer` · Depende de: T4 (exclusividad de `lib.rs`)*

- [ ] `application/update.rs` nuevo: sobrescribe `.opencode/`, `.tepochcalli/`, `.gitignore`, `opencode.json`, `AGENTS.md` — **y solo eso**
- [ ] **Backup `.bak` obligatorio** de cada fichero existente antes de pisar
- [ ] **Advertencia visible** con el directorio objetivo
- [ ] Rollback por compensación: un fallo restaura el estado previo desde los `.bak`
- [ ] `run_uninstall()` amplía su alcance a `.opencode/`, `.tepochcalli/` y `opencode.json`
- [ ] `AGENTS.md` **NO** se borra en `uninstall` (lo fija US-H8) → test explícito
- [ ] `00-resources/` intacto tras `uninstall` → test explícito
- [ ] Subcomando `update` en `cli/commands.rs` + entrada en `print_help()` + código de salida
- [ ] Idempotencia: `update` x2 ⇒ el segundo es no-op; `uninstall` sobre vault vacío ⇒ no-op
- [ ] La **primera Install** y la re-entrada `config` **siguen** con merge conservador byte-a-byte
- [ ] Tests: `tests/e2e_update.rs` nuevo + ampliación de `tests/e2e_maintenance.rs`
- [ ] `just rust-ci /tmp/opencode/cargo-target` verde

### 🛑 Checkpoint 2 — corte 1 cerrado

- [ ] `just quality` verde
- [ ] `just rust-ci /tmp/opencode/cargo-target` verde
- [ ] La rueda se construye y `uvx` la ejecuta
- [ ] TD-47, TD-48 y TD-50 cerrados
- [ ] Revisión de `code-reviewer` con contexto limpio: **APROBAR**
- [ ] Commits atómicos (uno por tarea), con trailer `Co-Authored-By`

---

## ➡️ Ronda 3 — Secuencial (1 frente)

### T7 · Dominio H5 puro: menú, botones y comparador semver

*Dueño: `rust-engineer` · Revisión: `software-architect` · Depende de: T5*

- [ ] `domain/menu.rs` nuevo: `MenuSpec` (botón: etiqueta, habilitada, razón) + 4 escenarios (`NoInstalado`, `Igual`, `Atrasada`, `Adelantada`)
- [ ] Matriz de habilitación **exactamente** la de la spec (4 escenarios × botones + razón)
- [ ] `domain/version.rs` nuevo: comparador semver **propio** (sin dep nueva) + lector de `.tepochcalli/pyproject.toml`
- [ ] Semver: `0.1.0-beta.1 < 0.1.0 < 0.2.0` ordenado correctamente
- [ ] Estado del embedder (API key externa o modelo local) calculado como dato de dominio
- [ ] `domain/` sin imports de `adapters/`, `ports/` ni crates externos (test de arquitectura)
- [ ] `tests/int_domain.rs` ampliado: matriz de los 4 escenarios + casos semver

### T8 · Puerto `Ui` ampliado + adapter ratatui

*Dueño: `rust-engineer` · Revisión: `code-reviewer` · Depende de: T7, T3*

- [ ] `ports/ui.rs`: **un** método nuevo (`menu`); los 4 actuales no cambian de firma
- [ ] `adapters/ui_ratatui.rs` nuevo: full-screen, botones reales, deshabilitado visible + **razón visible**, navegación por teclado
- [ ] Repo + `dev@fisherk2.com` siempre visibles (H5)
- [ ] `TtyUi` (dialoguer) pasa a **fallback** line-based con la misma información
- [ ] `HeadlessUi` responde al `menu` por índice
- [ ] `Cargo.toml`: `ratatui` 0.30 + `crossterm` 0.29 (únicas deps nuevas) + `Cargo.lock` actualizado
- [ ] Fakes de test del puerto actualizados en el mismo commit
- [ ] `--non-interactive` sin regresión (CI idéntica)
- [ ] Los 33 call sites del puerto siguen funcionando
- [ ] `just rust-ci /tmp/opencode/cargo-target` verde

### T9 · Cableado CLI: `tepochcalli` → H5 → H6..H11

*Dueño: `cli-developer` · Revisión: `code-reviewer` · Depende de: T8*

- [ ] `tepochcalli` sin subcomando ⇒ menú H5
- [ ] Subcomandos existentes (`install`, `config embedder`, `reindex`, `uninstall`) siguen funcionando
- [ ] 🟢 Update → T5 · 🔴 Desinstall → T5 · 🟣 Change Embedder → swap existente · 🔵 Install → 8 fases · 🟠 Exit → **cero cambios**
- [ ] H11: cierre pulsando cualquier tecla + agradecimiento a Tepochcalli
- [ ] H5 muestra versión del wizard, versión instalada, estado del embedder, repo y contacto
- [ ] Escenario «instalada > wizard» ⇒ comando copiable `uvx --refresh tepochcalli`
- [ ] `tests/e2e_cli_help.rs` ampliado con el menú y los 4 escenarios
- [ ] Recorrido manual e2e en un vault temporal de los 4 escenarios

### 🛑 Checkpoint 3 — corte 2 cerrado

- [ ] `just rust-ci /tmp/opencode/cargo-target` verde
- [ ] Matriz de los 4 escenarios de H5 verificada
- [ ] Fallback line-based y `--non-interactive` sin regresión
- [ ] Revisión de `code-reviewer` con contexto limpio: **APROBAR**

---

## 🏁 Ronda 4 — Secuencial (1 frente)

### T10 · Verificación e2e del canal (sin publicar)

*Dueño: `test-automation-engineer` · Apoyo: `testing-reality-checker` · Depende de: T3, T6, T9*

- [ ] Build de la rueda desde árbol limpio
- [ ] `uvx --from <rueda local> tepochcalli` abre el wizard y el menú H5 (transcript/captura)
- [ ] Recorrido Install → Update → Change Embedder → Desinstall con backup verificado
- [ ] `just ci` verde (suite completa + módulos + bench-smoke + rust-ci)
- [ ] `just md-lint` → 0 issues
- [ ] **Prueba negativa:** ninguna ruta de publicación activa (ni upload, ni credencial, ni auth)
- [ ] Transcript en el cuerpo del commit; `git status --short` limpio

### T11 · Cierre documental

*Dueño: `docs-writer` · Revisión: `technical-writer` · Depende de: T10*

- [ ] `docs/WORKFLOW.md` §Phase 6.5 → completada, con métricas **medidas** y salvedad de lo no verificado (TTY Windows, VM limpia real, publicación)
- [ ] `docs/TECH_DEBT.md`: TD-45/46/47/48/50 cerradas · **TD-51** (retiro de cargo-dist) abierta con plan de pago · **TD-52** si el smoke de TTY en Windows sigue sin ejercitarse
- [ ] `docs/ARCHITECTURE.md` §Key decisions: canal vigente `uvx`; ADR-003 como backend retirado
- [ ] `SPEC.md` §Índice: las 2 specs con enmienda Accepted
- [ ] `CHANGELOG.md`: entrada de la fase
- [ ] `docs/BACKLOG.md` §8: filas de todos los cambios estructurales
- [ ] `docs/APPFLOW.md`: journeys d/e/f al flujo destino (menú H5)
- [ ] `AGENTS.md`: sin cambios — verificado y declarado
- [ ] `grep -rn 'cargo binstall' docs/ SPEC.md README.md` → solo como canal **heredado**
- [ ] `just md-lint` → 0 issues

### 🛑 Checkpoint 4 — fase cerrada

- [ ] `just ci` verde · `just md-lint` 0
- [ ] Recorrido e2e con transcript en el commit
- [ ] **Cero rutas de publicación activas**
- [ ] Revisión final de `code-reviewer`: **APROBAR**
- [ ] `git-workflow-manager`: commits atómicos por corte, sin push

---

## 📌 Deuda abierta al cierre (esperado)

| ID | Deuda | Por qué no se cierra aquí |
| --- | --- | --- |
| **TD-51** | Retiro materializado de cargo-dist (`dist.toml` + `release.yml` heredado) | Decisión del dueño: la preparación del canal nuevo no incluye el borrado del backend viejo |
| **TD-52** | Smoke de TTY/interacción bajo `uvx` en Windows | Requiere un runner `windows-latest`; en este entorno no hay Windows → queda `declarado`, no `medido` |
| **M6** | CI y release nunca ejecutados en GitHub Actions | 0 releases publicadas; sin `cargo-dist` instalado no se puede regenerar el backend viejo |
| — | Publicación real a PyPI | Fuera de alcance por orden explícita del dueño (2026-11-19) |

---

*Redactado por Moctezuma (tlatoani) el 2026-11-19. Plan: [tasks/plan.md](./plan.md). Ningún cambio
de código implementado en esta sesión.*
