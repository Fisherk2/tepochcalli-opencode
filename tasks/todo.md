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

---

## 🛡️ Fase 6.6 — resiliencia offline y rollback cancelable (H6/H7/H9)

> Checklist operativo de [tasks/plan.md](./plan.md) §11. Fuente de verdad:
> [docs/BACKLOG.md](../docs/BACKLOG.md) §2 US-H6/H7/H9 (edge case 2026-11-20) + §4 D-009 +
> [ADR-016](../docs/adr/adr-016-resiliencia-offline-y-rollback.md). Añadido el 2026-11-20.
> **Leyenda:** `[ ]` pendiente · `[~]` en curso · `[x]` hecho · `[!]` bloqueado (motivo en la línea).

### Enunciado canónico (no re-inventar)

- **R-offline-1 (preflight):** Antes de escribir cualquier fichero, el wizard comprueba la conectividad mínima que la operación necesita. Si no hay red, cancela la operación con rollback y deja el workspace del usuario exactamente como estaba; muestra error tipado con razón y acción correctiva. No hay modo degradado ni instalación parcial en tiempo de instalación.
- **R-offline-2 (cancelación en progreso):** Durante la descarga del modelo, el usuario puede cancelar en cualquier momento desde el TUI y con Ctrl+C. La cancelación detiene la descarga, elimina los artefactos parciales y compensa todo cambio ya aplicado (rollback), cancelando la instalación completa. No queda modelo a medias en `.tepochcalli/models/`.
- **R-offline-3 (integridad):** El rollback restaura el estado previo de los ficheros gestionados usando el backup + journal ya existentes de H7/H8. Notas, PDFs, `.obsidian/` y configuración propia del usuario nunca se tocan. Tras el rollback se verifica que no quedan restos.
- **R-offline-4 (distinción crítica):** El modo degradado de **runtime** (ADR-007 / `rag_status`) NO cambia: en instalación/cambio de embedder, **sin red = cancelación, no degradación**. «Si la API no responde, se muestra `sin dato` sin fallar la instalación» aplica **solo a la estimación previa de requisitos**, no a la descarga real.

### 🔒 Guardarraíles de la fase

- [ ] **Ningún publish** (ni `twine`, ni `maturin publish`, ni job de upload). Sin excepciones.
- [ ] **Cero dependencias nuevas** (regla R1): reutilizar `ureq` (ya en `crates/tepochcalli/Cargo.toml`, v3) y lo ya en `Cargo.lock`. Antes de proponer una alta, verificar el lock.
- [ ] **`CARGO_TARGET_DIR` siempre bajo `/tmp/opencode/`** → `just rust-ci /tmp/opencode/cargo-target`.
- [ ] **Comandos vía `just`**, nunca `cargo`/`uv`/`pytest` crudos.
- [ ] **Jamás en segundo plano**: sin `&`, `nohup` ni procesos huérfanos; las corridas largas en primer plano y por partes.
- [ ] **La suite por defecto nunca depende de red real**: red falsa en loopback (`int_fetch_verified`) o tests `#[ignore]` con receta (`int_model_availability`).
- [ ] **El rollback deja los ficheros del usuario byte-idénticos**: notas, PDFs, `.obsidian/` y config propia intactos.
- [ ] **Fuera de alcance**: H8 (Desinstall) no se toca; degradado de runtime (ADR-007) no cambia; `sin dato` sigue siendo solo estimación.

### T12 · Formalización documental

*Dueño: `docs-writer` · Revisión: `code-reviewer` · Depende de: ninguna · **en ejecución en este cambio documental***

- [x] ADR-016 creado con `Status: Accepted` y fecha 2026-11-20 (lo crea OTRO frente; este frente solo toca `tasks/`)
- [x] ADR-016 decide **cancelación con rollback**, no degradación; ≥2 alternativas rechazadas con razón
- [x] Enmienda 2026-11-20 en `specs/spec-installer-wizard.md`: R-offline-1/2/3/4 + estados de botón y mensajes de cancelación para H6/H7/H9
- [x] Enmienda 2026-11-20 en `specs/spec-embeddings.md`: `sin dato` = solo estimación previa; degradado de runtime intacto
- [x] `docs/BACKLOG.md`: D-009 en §4 + fila en §8 + edge case en US-H6/H7/H9
- [x] `git diff --exit-code` sobre ADR-007/008/014/015 → 0 líneas (no se reescriben)
- [x] `just md-lint` → 0 issues

### T13 · Preflight de red y error tipado antes de escribir (R-offline-1)

*Dueño: `rust-engineer` · Revisión: `code-reviewer` · Depende de: T12*

- [x] Preflight con `ureq` (sin dep nueva) del endpoint que la operación necesita, con timeout corto y fallo rápido
- [x] Preflight corre **antes** del primer write de H6/H7/H9
- [x] Sin red ⇒ **test sin red falla con error tipado** (razón + acción correctiva, no texto libre) y `git status` del vault temporal limpio: **cero ficheros escritos**
- [x] `sin dato` de la estimación previa **no** cuenta como preflight (R-offline-4)
- [x] Test: `tests/int_offline_preflight.rs` (nuevo) con red falsa en fallo
- [x] `just rust-test /tmp/opencode/cargo-target` y `just rust-ci /tmp/opencode/cargo-target` verdes

**Evidencia 2026-11-20.** `HttpClient::probe` (8 s, `http_status_as_error(false)`, guard L4-2 antes de tocar red) + `FakeHttp`/`DeadNetwork`. H9 sondea HF solo con provider `local`; H7 solo la rama `--payload-url`; H6 antes de `ensure_vault_dir` (el write que se colaba era `.install-state`, no F3). Tests: `int_offline_preflight` (2, loopback), `e2e_offline_preflight` (2: install/update sin red ⇒ exit 20 y vault vacío), `swap_sin_red_no_escribe_ni_la_config` (config byte-idéntica **e inode** intacto). 406 tests Rust, `rust-ci` exit 0. Exclusión declarada: con `--payload` local no se sondea (F3 no toca red; F4/F5 compensan por fase) y el mirror http sin TLS espera su consentimiento. `tests/e2e_swap.rs` queda en 999 líneas — tramo 701-1000 del umbral, justificado: fichero de escenarios del swap, sin división posible sin duplicar fixtures; ultrapasó 1000 en T15 (1042) y esta ronda lo deja en 1068 — deuda sin ID en docs/TECH_DEBT.md.

### T14 · Cancelación de descarga en progreso + limpieza (R-offline-2)

*Dueño: `rust-engineer` · Revisión: `code-reviewer` · Depende de: T13*

- [x] Descarga cancelable por botón del TUI **y** Ctrl+C mediante una señal compartida; `ureq` se aborta y el stream se cierra
- [x] Bytes parciales van a un temporal y se borran en **todas** las salidas (éxito, error, cancelación)
- [x] Tras cancelar a mitad, **no queda modelo a medias en `.tepochcalli/models/`** (ni temporal ni versión incompleta) — test explícito
- [x] Cancelación propaga rollback (T15) y aborta la instalación completa
- [x] Test: `tests/int_download_cancel.rs` (nuevo) con servidor loopback que entrega a trozos + señal inyectada (sin matar el proceso de test)
- [x] `just rust-test /tmp/opencode/cargo-target` verde

**Evidencia 2026-11-20.** `CancelToken` (`Arc<AtomicBool>`, clon comparte disparo) en `domain/`; `CommandRunner::run_cancellable` con default (token disparado ⇒ `UserAborted` sin spawn) y `std_proc` que extrae `run_inner` + watcher con `Verdict::{Exited,Cancelled}` que mata y reapea al hijo. Token atravesando `run_flow_cli`→`spawn_gate`→`run_gate` en F6/H9 (`maintenance`/F8/refresh pasan `None`); `Deps` lo **poseen** (sin `Box::leak`). Purga: snapshot de `models/` antes del gate y borrado solo de lo nuevo si hay `UserAborted`; un gate roto conserva el degradado. Tests: 412 Rust (+6), `rust-ci` exit 0.

**Desviación declarada del plan.** La descarga del modelo ocurre en el subproceso `venv python -m tepochcalli_flow embed-check`, no en `ureq`: la unidad cancelable es el **hijo** (se mata), no un stream HTTP. Por eso `int_download_cancel` usa un hijo largo (`sleep 30`) y no un servidor loopback a trozos; está documentado en el doc-comment del fichero. El disparador real desde el TUI llega en T16 (hoy el token se crea siempre vivo).

### T15 · Journal/backup + compensación y verificación post-rollback (R-offline-3)

*Dueño: `rust-engineer` · Revisión: `software-architect` · Depende de: T14*

- [x] Journal registra cada fichero gestionado **antes** de tocarlo (mismo mecanismo que el rollback de `application/update.rs`)
- [x] Preflight fallido (T13) y cancelación (T14) invocan **la misma** compensación; un solo camino de rollback
- [x] Ficheros gestionados **byte-idénticos** al estado previo tras el rollback (comparación de bytes, no solo existencia)
- [x] Test de no-interferencia: `00-resources/`, `.obsidian/` y config propia del usuario byte-idénticos tras rollback forzado en H6, H7 y H9
- [x] Verificación de que no quedan restos (temporales, `.bak` huérfanos) tras el rollback
- [x] Test: `tests/int_rollback_integrity.rs` (nuevo), comparando el árbol completo antes/después
- [x] `just rust-test /tmp/opencode/cargo-target` y `just rust-ci /tmp/opencode/cargo-target` verdes

**Evidencia 2026-11-20.** `InstallSnapshot::capture` (read-only, antes de `ensure_vault_dir`) + `rollback_install` en `application/rollback.rs`: `executed = completed_phases(now) − snapshot.completed`, compensadores en orden inverso (F8 → F7 → F3 → runtime), `remove_dir_all(.tepochcalli)` de una vez si el runtime no existía, por fase si existía, y `remove_dir_all(vault)` si el vault lo creó esta corrida. **F6 no usa `compensate_phase6`** (escribe `provider = "none"`): config por bytes del snapshot. Punto único en `run_install` (`code != 0`) + línea `install: rollback aplicado`. Tests: `int_rollback_integrity` (4, árbol byte a byte), `install_offline_fails_at_f4_and_rolls_back_the_vault` (renombrado: ya no queda `.install-intent` ni payload, la nota del usuario sobrevive), `swap_cancelado_en_el_gate_no_deja_modelo_parcial`. 417 tests Rust, `rust-ci` exit 0.

**Desviaciones declaradas.** (a) No se añade un journal por fichero para install: se reutilizan los que ya existen (`.install-intent` de F3, `.opencode` `.bak` de F8, marker de fases) más el snapshot — menos mecanismo, mismo invariante. (b) En un vault **con `.install-intent` previo**, la re-ejecución de F3 no promete borrar los ficheros que esa pasada añadió (journal acumulativo); probado con marker `F1/F2`. (c) La rama de re-ejecución no promete byte-identidad dentro de `db/`, `bin/` ni `venv/` (estado derivado; solo se borran si los creó la corrida). (d) Pueden quedar **directorios vacíos** en un vault preexistente (el `remove_dir_all` del final solo aplica al vault creado por la corrida).

### T16 · TUI: estados de botón, razón visible y mensajes (H6/H7/H9)

*Dueño: `rust-engineer` · Revisión: `code-reviewer` · Depende de: T15*

- [x] Durante la descarga: botón de cancelar habilitado y conectado a T14; otros botones deshabilitados con razón visible «descarga en curso»
- [x] Sin red en preflight: error tipado de T13 con razón y acción correctiva; **sin salida «modo degradado»**
- [x] Tras cancelar/rollback: mensaje visible que confirma que el workspace quedó como estaba
- [x] Regla H5: botón deshabilitado con razón, nunca oculto
- [x] `HeadlessUi` y `--non-interactive` sin regresión; cancelación inyectable por índice/señal en tests
- [x] `tests/e2e_ui.rs` ampliado con los 3 estados nuevos; 33 call sites del puerto `Ui` intactos
- [x] `just rust-ci /tmp/opencode/cargo-target` verde

**Evidencia 2026-11-20.** `Ui::run_cancellable` (no genérico: un genérico rompería `&dyn Ui`) con default inline; `TtyUi` lo sobrescribe solo con TTY ⇒ `ui_ratatui::run_progress` (pantalla alternativa, `RestoreOnDrop`, watcher de 100 ms que dispara el token con Esc/Ctrl+C, redibujo «Cancelado — deshaciendo los cambios aplicados…»; si el draw falla degrada a `work()`). `render_progress` puro: Cancelar habilitado + las 5 acciones en `DIM` con «descarga en curso» + aviso de no-destrucción. Wiring en **un solo punto**: `run_gate_cancellable` envuelve solo el gate (los paneles de F6/swap no quedan ocultos tras la pantalla). `failure_body(UserAborted)`: línea `estado: cancelado… el workspace quedó como estaba` y **sin** `retry:`. Tests: `int_ui_progress` (5: render, DIM en buffer, mapeo de tecla, Headless inline), +1 unit de `failure_body`, +1 e2e de panel. 424 Rust, `rust-ci` exit 0.

**No medido (declarado, no se presenta como cubierto):** TTY real (pantalla alternativa y teclas desde `/dev/tty`), Ctrl+C inyectado por el SO —incluido Windows— y animación de progreso (el gate bloquea el hilo principal: la pantalla dibuja estado, no avance). El render se verifica en `TestBackend` y el disparo del token en fakes.

### T17 · Verificación y cierre: gates + e2e con red falsa

*Dueño: `test-automation-engineer` · Apoyo: `testing-reality-checker` · Depende de: T16*

- [x] Todo test de red usa loopback o es `#[ignore]` con receta (`int_fetch_verified` / `int_model_availability`)
- [x] `just rust-test` y `just ci` pasan **sin red**
- [x] E2E sobre vault temporal: H6/H7/H9 × {sin red, cancelación a mitad}, con comparación byte-a-byte del árbol antes/después
- [x] `just quality` · `just ci` · `just rust-ci /tmp/opencode/cargo-target` · `just md-lint` → 0 issues
- [x] `grep -rn 'https://huggingface' crates/tepochcalli/tests/` → solo en tests `#[ignore]`
- [x] Cierre documental: WORKFLOW §Phase 6.6 con métricas medidas; TECH_DEBT con la deuda esperada; BACKLOG §8
- [x] Transcript del recorrido en el cuerpo del commit; `git status --short` sin modelos parciales ni artefactos

**Evidencia 2026-11-20 (cierre de fase).** Matriz real ejercitada: **H6 sin red** (`e2e_offline_preflight::install_sin_red_no_escribe_nada`: exit 20, vault con 0 entradas), **H7 sin red** (`update_sin_red_no_escribe_nada`), **H9 sin red** (`swap_sin_red_no_escribe_ni_la_config`: config byte-idéntica **e inode** intacto), **cancelación** por inyección del token (`int_download_cancel`, `swap_cancelado_en_el_gate_no_deja_modelo_parcial`, `int_ui_progress`) y **rollback** (`int_rollback_integrity`, árbol byte a byte). **No** hay celda de «cancelación con TTY real»: se declara deuda, no cobertura. Gates: `just quality` 707 tests/69,45 s · `just ci` **exit 0 en 37m26s** · `just rust-ci` exit 0 (424 tests) · `just md-lint` 0 en 63 ficheros. `grep https://huggingface` en `tests/` solo aparece en `int_model_availability.rs` (`#[ignore]`).

### 🛑 Checkpoints de la fase

- [x] **C5 (tras T12):** ADR-016 Accepted · enmiendas + D-009 presentes · `just md-lint` 0 → si falla, el núcleo no arranca
- [x] **C6 (tras T13-T15):** `just rust-test`/`just rust-ci` verdes · cero ficheros sin red · cero modelos parciales al cancelar · byte-idéntico tras rollback → si falla, se revierte el corte
- [x] **C7 (tras T16-T17):** `just quality` · `just ci` · `just md-lint` 0 · e2e con red falsa + transcript → si falla, no se cierra la fase

### 📌 Deuda esperada al cierre (sin ID nuevo)

| Deuda | Por qué no se cierra aquí |
| --- | --- |
| Cancelación/rollback y Ctrl+C en Windows | Requiere runner `windows-latest`; en este entorno no hay Windows ⇒ queda `declarado`, no `medido`. No se afirma cobertura; se registra en TECH_DEBT con el ID que el dueño asigne. |
| `uvx` desde PyPI y publicación real | Fuera de alcance por orden explícita del dueño; TD-51/TD-52 siguen como estaban. |

---

*Fase 6.6 añadida el 2026-11-20. Plan: [tasks/plan.md](./plan.md) §11. Sin código implementado por este frente.*
