# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

<!-- markdownlint-disable-next-line MD024 -->
### Fixed

- **Wizard: causas del `embed-check` ya no se aplanan.** El gate distingue repo no-embedding
  (`E_MODEL_INVALID`), fallo de red/descarga (`E_MODEL_DOWNLOAD_FAILED`) y carga/dispositivo
  (`E_MODEL_LOAD_FAILED`, también fallback de causa desconocida), con el `detail` real (≤300 chars).
  El consumer Rust mapea todo código desconocido o ausente a `ModelLoadFailed`, nunca a
  `ModelInvalid` (reservado al pre-filtro de tags de HuggingFace). La respuesta de éxito no cambia.
- **Wizard: fallo del gate en F6 visible.** El panel y el log muestran la causa real y el checklist
  de reentrada, manteniendo la degradación exit 0 con `provider = "none"` de ADR-016.
- **Wizard: desinstall acotado del venv.** El borrado en Unix es bottom-up y paralelo (N=8,
  std-only): no sigue symlinks, comprueba la cancelación por entrada y deja notas, PDFs y
  `.obsidian/` intactos; Windows conserva la primitiva estándar.
- **UX: barra de progreso real.** Avance monótono 0→100 por hito en install (7), swap (6),
  desinstall (`present.len()+1`) y update (1), en lugar de la barra indeterminada.
- **UX: spinner y cronómetro honestos.** Frames ASCII `|/-\` en fila propia alimentados por el
  watcher existente, `mm:ss` y `ETA —` cuando no hay estimación declarada (los MB de
  `presets.toml` nunca se convierten en segundos).
- **UX: progreso en los cuatro flujos.** `ProgressSpec`/`Progress`/`run_stages` se añaden de forma
  aditiva al puerto `Ui`; `run_cancellable` y sus call sites y fakes no cambian.

## [0.1.0-beta.2] - 2026-11-24

<!-- markdownlint-disable-next-line MD024 -->
### Fixed

- **Wizard: destino por defecto sin preguntar.** `resolve_vault_dir` usa el directorio corriente
  (`current_dir()`) cuando no hay `--vault` o llega en blanco; `--vault <dir>` sigue ganando.
- **Wizard: instalación en NTFS-3G.** El `uv` verificado se descarga, se comprueba por SHA-256, se
  hace ejecutable y se ejecuta desde el state dir del SO; `<vault>/.tepochcalli/bin/uv` es un
  symlink Unix (Windows conserva la copia `.exe`). El state root se crea o verifica privado
  (`0700`) y un directorio legacy `0755` de beta.1 se repara a `0700` —no se rechaza—; un symlink o
  un directorio no chmodeable falla de forma tipada. Corrige el `Permission denied (os error 13)`
  del montaje fuseblk/NTFS-3G ([ADR-017](docs/adr/adr-017-instalacion-filesystem-agnostica.md)).
- **Wizard: cancelación honesta por fase.** Al cancelar F3/F4/F5/F7, la pantalla de progreso de esa
  fase muestra «Cancelado — deshaciendo los cambios aplicados…» en lugar de un fallo genérico.
- **Wizard: diagnósticos de cwd y payload.** El reporte de fallo muestra el directorio corriente y
  el payload usado.

### Changed

- **Restricciones de dependencias del payload** ([ADR-018](docs/adr/adr-018-refresco-pines-dependencias-payload.md)):
  `pillow>=13.0.0` (5 CVEs CRITICAL corregidos), `litellm>=1.110.4,<1.111` (por encima de
  `GHSA-92x9-889m-jgmw`), `filelock>=4.2.1` (resuelve `4.3.1`; 13 advisories corregidos),
  `soupsieve>=4.0.0` y `opentelemetry-api>=1.45.2` (un advisory cada uno). Verificado contra OSV
  el 2026-11-24.

### Docs

- **README en inglés** con tarjetas de agentes y procedencia de los benchmarks.

## [0.1.0-beta.1] - 2026-11-23

### Added

- **Phase 6.6 — resiliencia offline del wizard (ADR-016, 2026-11-20):** preflight de red antes del
  primer escrito (sin red ⇒ cancelación tipada con rollback, nunca instalación parcial),
  cancelación de la descarga del modelo desde el TUI y con Ctrl+C con purga de artefactos
  parciales, rollback de la instalación fallida o cancelada (backup + journal) y pantalla de
  descarga cancelable. Sin dependencias nuevas.

### Added (Phase 6.5 — flujo destino materializado, 2026-11-19)

- **FTR del dueño firmado:** [ADR-014](docs/adr/adr-014-distribucion-uvx-pypi.md) y
  [ADR-015](docs/adr/adr-015-dispositivo-inferencia-wizard.md) pasan de *Proposed* a
  **Accepted**; las enmiendas «2026-11-18 — flujo destino» de `spec-installer-wizard` y
  `spec-embeddings` también. Versión alineada a **`0.1.0`** (`Cargo.toml` + `Cargo.lock` detrás
  de la canónica `.tepochcalli/pyproject.toml`, TD-45) y Phase 6.5 desbloqueada y cerrada.
- **Canal `uvx` preparado y verificado — sin publicar:** rueda
  `tepochcalli-0.1.0-py3-none-manylinux_2_39_x86_64.whl` (**2 401 134 B**) ejecutada con
  `uvx --from <rueda local> tepochcalli --version` ⇒ `tepochcalli 0.1.0` (Linux, glibc 2.39).
  **Nada se publicó:** 0 workflow runs, 0 releases y `https://pypi.org/pypi/tepochcalli/json` ⇒
  HTTP 404; en `.github/workflows/` solo hay 2 líneas sobre publicación a un **registro de
  paquetes**, ambas comentarios de no-publicación (`wheels.yml:1` y `:4`); el `publish:` de
  `release.yml` sube assets a un GitHub Release (backend heredado, TD-51), no a PyPI.
- **TUI full-screen con menú H5** (`ratatui` 0.30 + `crossterm` 0.29, sustituye `dialoguer`):
  cabecera con versión del wizard, instalada y estado del embedder; 5 botones
  (Install/Update/Change Embedder/Desinstall/Exit) con bloqueo = botón deshabilitado + razón
  visible. Verificado en **TTY real** (`script -qec`, 80×24):
  `Tepochcalli 0.1.0 · instalada: — · embedder: sin configurar`.
- **`device` electivo (H9)** en wizard y re-entrada (`cpu`/`cuda`/`cuda:N`), escrito en
  `[embedding].device` y **preservado** por `config embedder`; la autoselección en runtime sigue
  rechazada. Guarda anti-exfiltración de `model` con test (`tests/unit/test_config.py:412`).
- **`update` (H7) y `desinstall` (H8)** con backup y advertencia. Medido: update **0,293 s**
  (2 ficheros + 2 `.bak`; `venv/` de 2,0 GB y `00-resources/` intactos) y **0,081 s** en la
  segunda pasada con 0 entradas modificadas; desinstall **1,44 s**, `AGENTS.md` y
  `00-resources/` intactos, backup `.tepochcalli-backup-<ts>/` con permisos `drwx------` y
  segundo uninstall no-op.
- **Gates de la fase:** `just quality` **707 tests Python** · suite Rust **386 tests** ·
  `just ci` **exit 0 en 45m49s** · `just md-lint` **0 issues**.
- **Salvedades declaradas (no medidas):** Change Embedder e2e (solo integración con fakes;
  exige descargar ~470 MB y reindexar), Windows/TTY ⇒ TD-52, `uvx` desde PyPI o VM limpia
  (imposible sin publicar) e install con el payload del checkout (TD-53: `--payload` arrastra
  el `venv/` gitignored de 2,1 GB, 19m10s).

### Added (flujo destino del wizard — documentación, 2026-11-18) (superseded 2026-11-19)

- **ADR-014 (Proposed)** — [canal de distribución `uvx` + PyPI](docs/adr/adr-014-distribucion-uvx-pypi.md):
  wheel vía maturin (`bindings = "bin"`), instalación `uvx tepochcalli` y refresco
  `uvx --refresh tepochcalli`. Sustituye el **canal** de ADR-013 y **declara** el retiro del
  backend de ADR-003 (`dist.toml` + `release.yml`) como decisión del dueño — la materialización
  del retiro queda como tarea futura. ADR-004 intacto. Versión canónica =
  `.tepochcalli/pyproject.toml` (0.1.0) frente a `Cargo.toml` (0.1.0-beta.1) → alineación
  one-version pendiente; deps maturin/PyPI pendientes de visto bueno del dueño.
- **ADR-015 (Proposed)** — [elección explícita de device en wizard y re-entrada](docs/adr/adr-015-dispositivo-inferencia-wizard.md):
  campo `device` en `Preset`, el wizard escribe `[embedding].device` (destino
  `cpu`/`cuda`/`cuda:N` — BACKLOG.md §2 / US-H9 —; los valores sin soporte fallan al cargar el modelo, no al
  configurar; `mps` queda como trigger futuro ADR-015 §8) y la re-entrada `config embedder`
  **preserva** el valor (drift futuro a corregir en `presets.rs`,
  `embedder_config.rs:42`, `swap.rs:422`). **Refina** ADR-007/008 sin sustituirlos; la
  autoselección en runtime sigue rechazada; GPU sin sonda = botón deshabilitado con razón.
- **Enmiendas a las specs**: `specs/spec-installer-wizard.md` y `specs/spec-embeddings.md`
  reciben la sección "Enmienda 2026-11-18 — flujo destino (Proposed)".
- **`docs/CODE_STYLE.md`**: excepción del dueño (2026-11-18) a la regla byte-a-byte — Update
  (H7) y Desinstall (H8) sobrescriben/remueven `opencode.json` y `AGENTS.md` del vault con
  **backup obligatorio + advertencia visible**; primera Install y re-entradas `config` siguen
  con merge conservador.
- **`docs/WORKFLOW.md`**: nueva **Phase 6.5 — Wizard flujo destino (H5-H11)**, no ejecutable
  (precondiciones: ADR-014/015 Accepted + deps aprobadas + one-version alineada +
  enmiendas Accepted); ola **D68** registrada en §8.

  *Documentación solo — cero implementación, cero ADR Accepted.* Contexto: 0 tags publicados y
  M6 abierto (`cargo binstall` nunca corrió en producción) ⇒ no hay usuarios que migrar.

### Changed (canal de instalación `cargo binstall`, 2026-11-13)

- **El canal recomendado de instalación del wizard pasa a `cargo binstall tepochcalli`**
  (decisión del dueño, 2026-11-13; [ADR-013](docs/adr/adr-013-distribucion-cargo-binstall.md)),
  con `shell`/`powershell` conservados como **fallback sin toolchain**: el usuario objetivo no
  debe ejecutar un `.sh` como primer paso, y el dueño acepta `cargo` como dependencia del host.
  Reemplaza el **canal** de ADR-003 (que no se re-edita); cargo-dist sigue siendo el backend de
  release. La instalación son **dos pasos** (`cargo binstall` instala el binario y termina;
  `tepochcalli install --vault <ruta>` configura el vault) porque **binstall no reenvía flags**
  al binario — a diferencia de `bunx`. Requisito del host: `cargo` + `cargo-binstall`; assets
  solo para los 5 targets de `dist.toml`; el namespace `tepochcalli-v<ver>` exige
  `[package.metadata.binstall]` con `pkg-url`; orden de release tag → assets → `cargo publish`;
  `tepochcalli uninstall` no borra el binario; las versiones de crates.io no se borran (solo
  `cargo yank`). npm/homebrew/msi quedan fuera de v1 (activarlos exige token, no ADR nuevo).
  Propagado a `SPEC.md`, `specs/spec-installer-wizard.md` (§Enmienda canal), `docs/APPFLOW.md`
  §5, `docs/PRD.md` F6 y `docs/ARCHITECTURE.md`. Evidencia `declarado`: `cargo binstall` nunca
  se ejecutó contra un release (M6 abierto). Sin cambio de código.

### Changed (soporte de Windows en v1, 2026-11-13)

- **Windows está soportado con verificación pendiente** (decisión firmada por el dueño el
  2026-11-13, etiqueta `declarado`). En el repo existen el target `x86_64-pc-windows-msvc`
  (`dist.toml` y `release.yml`), el `install.ps1`, el layout `Scripts/` con
  `venv/Scripts/python.exe` (D20) y las ramas `cfg!(windows)` del wizard; **nada de ese camino se
  ejecutó nunca en Windows**: ni el instalador, ni el smoke path-5, ni la matriz CI (ubuntu+macos;
  `release.yml` jamás ha corrido — M6). Consecuencia para el usuario: puede instalar en Windows
  por ese camino, pero nadie ha verificado que funcione; si falla, no hay soporte comprometido.
  La coletilla «verificación pendiente» cae con un smoke path-5 (`--non-interactive --skip-model`)
  en un runner `windows-latest` sobre una release real, el layout `Scripts/` verificado, la
  evidencia archivada y una fila de Windows en la matriz CI. Propagado a `docs/TRD.md` §2,
  `specs/spec-installer-wizard.md` (§Enmienda D-b y Testing Strategy), `docs/APPFLOW.md` §5 y
  `docs/TECH_DEBT.md` §D-b (deuda cerrada y firmada). Sin cambio de código.

### Fixed (2026-11-13)

- **La carpeta de entrada del usuario pasa a `00-resources/` (minúsculas) en las tres capas** — el
  wizard creaba `00-Resources/` (y anunciaba «Escribe tus notas en `00-Resources/`») mientras el
  payload declaraba `INDEXER_DIR="00-resources"` y el flow usaba
  `citation.RESOURCES_DIR = "00-Resources"`: en un FS sensible a mayúsculas el vault quedaba con
  **dos** carpetas y el material que el usuario escribía en la carpeta anunciada **no se indexaba**
  (hermano de TD-8, `01-Tasks/` → `01-tasks/`). Se alinea el literal en `citation.py`,
  `installer.rs` y el payload, se renombran los directorios reales (fixtures) y se añade el gate
  cross-capa `tests/unit/test_resources_dir_canonical.py`, que cae si una sola capa se separa.
  Enmienda: `specs/spec-vault-structure.md` §Enmienda 2026-11-13. Sin cambio de contrato.

### Added (guardrails de esquema OpenCode V2, 2026-11-09)

- **Tests de forma, no de contenido** — `tests/unit/test_frontmatter_schema.py` (170 agentes vs
  `Config.AgentEncoded`, 9 comandos vs `CommandEncoded` sin `template`, 40 skills con `name` +
  `description` no vacíos) y `tests/unit/test_opencode_config_schema.py` (`opencode.json` vs el
  esquema oficial vendorizado en `tests/fixtures/opencode-config.schema.json`). 11 controles
  negativos prueban que el portero rechaza instancias mutadas; fuentes: docs oficiales de agents,
  commands y skills de OpenCode V2 + `https://opencode.ai/config.json` (descargado 2026-11-09).

### Removed (2026-11-09, decisión del dueño)

- **Tests de contenido sobre `obsidian-workspace/.opencode/`** —
  `tests/unit/test_payload_contract.py` (hash de las 40 skills, presupuestos de líneas, idioma,
  citas) y `tests/unit/test_opencode_skill_catalogue.py` (cuerpo de la skill `tepochcalli-mcp` vs
  el servidor). El alcance de tests sobre el payload queda en **frontmatters + esquema de
  `opencode.json`**; la puerta 42/42 de `test_payload_permissions.py` (permisos = frontmatter de
  agentes) se conserva.

### Fixed (2026-11-10)

- **Loopback real de F8 en el gate (`int_phase_f8_mcp_merge`)** — el probe colgaba >120 s en
  I/O FUSE (el venv de 2.1 GB vive en `fuseblk`/NTFS-3g; el hijo pasaba bloqueado en
  `fuse_chan_send`/`folio_wait_bit_common` con 7 s de CPU en 40 s de vida) y `PROBE_TIMEOUT` lo
  mataba: 2 corridas de `just ci` en rojo. Fix en el test (no en el producto): warm-up de la
  importación con el mismo hijo/cwd/env antes de cronometrar. RED documentado; `just ci` verde.

### Added (Phase 5 — payload materializado, 2026-11-09)

- **Payload materializado** — 15 artefactos de texto en `obsidian-workspace/`: **5 agentes**
  (`itzamna`, `nezahualcoyotl`, `pochteca`, `chilam`, `tlacuilo`; cuerpos de 55/53/57/57/55 líneas,
  ≤60), **9 comandos** (24-30 líneas, ≤35, byte-idénticos a `spec-payload-commands.md`) y el
  **`AGENTS.md` del vault** (7 secciones, 74 líneas) con la regla MCP-first, la de cita y la de
  no-contaminación de bandejas.
- **Permisos por agente en forma de bloque** (16/18/17/18/27 reglas) con 30 denies de secretos
  (5 agentes × 6 rutas), 5 `subagent * deny` y 0 reglas muertas; 0 campos legacy, 0 `model` repetido.
- **40 skills congeladas** (D-P5-1): 40 dirs / 687 ficheros, hash del árbol
  `169fe2c9…17fc398` **idéntico al baseline T0** — 0 altas, 0 bajas, 0 ediciones; contrato estático
  nombre a nombre con hash.
- **Scaffold canónico:** las 6 bandejas (`01-tasks/` con `research/`, `02-drafts/`, `03-citations/`,
  `04-review/`, `05-outputs/`, `00-Resources/`) con `.gitkeep`, y **`.gitignore` del vault** con las
  5 rutas de `spec-vault-structure`.
- **Gate estático del payload (`tests/unit/test_payload_permissions.py` +
  `test_payload_contract.py`):** 42/42 probes del intérprete last-match-wins, 0 nombres de skill
  inexistentes y presupuestos de líneas assertados.

### Changed (Phase 5 — payload materializado)

- **`opencode.json` del payload sin el array global de 313 reglas `permissions`** (D-P5-4): la
  política efectiva de cada agente es su bloque. `instructions` pasa a 4 rutas **vault-relative**
  resolubles; `default_agent: itzamna`; `mcp.servers` y `references` intactos.
- **`01-Tasks/` renombrada a `01-tasks/`** (TD-8: renombrar, nunca crear) y sus 3 ficheros de 0
  bytes eliminados.
- **El fixture del merge conservador se sustituye por un merge sintético** (D-P5-9): el test ya no
  compara el payload consigo mismo; fabrica servers de usuario y demuestra que el merge los preserva.
- **La enmienda fechada D-P5-2** sustituye las 8 skills inexistentes que citaban `/transform` y
  Tlacuilo por las reales del inventario de 40; `.opencode/skills/` queda intacto.

### Fixed (Phase 5 — payload materializado)

- **La segunda instalación fallaba en F5**: `uv venv` sobre un venv ya existente devolvía error y la
  compensación borraba el venv (dejando el vault sin runtime). Ahora F5 usa `uv venv --clear` sobre
  el venv derivado; test RED→GREEN en `int_install_f4_f5.rs`, y el e2e de dos instalaciones deja el
  digest del árbol idéntico (`ffa4db0e…eac0151`, 875 ficheros) con 0 duplicados y 0 `.bak`.

### Not verified (Phase 5 — payload materializado)

- **Corrida D9 (methodology e2e de los 9 comandos)**: **diferida al QA de cierre de proyecto**
  (D-P5-10). Se entrega el runbook `tests/phase5-methodology-runbook.md`; la deuda queda como TD-31
  y el gate Phase 5→6 se firma con esa salvedad, **no** como verde.
- GitHub Actions **nunca ha corrido** (M6); Windows/PowerShell, release/cargo-dist y la suite `slow`
  tampoco se ejecutaron.

### Added (Phase 4 — blueprint del payload, 2026-11-04)

- **Cinco specs del payload** (<500 líneas cada una): `spec-payload-vault` (spec padre: reglas de
  formato OpenCode V2, blueprint del `AGENTS.md` del vault, testing ejecutable y decisiones D-P4-*),
  `spec-payload-skills`, `spec-payload-permissions`, `spec-payload-agents` y
  `spec-payload-commands`. Las cinco quedan en **Proposed**: el gate BLUEPRINT APPROVED es del
  usuario y todavía no ha ocurrido (Phase 5 no arranca).
- **Inventario real verificado** contra `obsidian-workspace/.opencode/`: **209 skills · 170 agentes
  · 9 comandos**; matriz de **17 filas** que cubre el 100 % del recuento, sin skills ni
  subagentes inventados. Base estricta resultante: **60 skills** — el objetivo <60 falla por 1; no se corta: el dueño revisará cada skill manualmente.
- **5 bloques `permissions` re-verificados contra la documentación OpenCode V2 v2.1.2** y reescritos
  en **forma de bloque** (no array suelto), con la nota de fusión de **D-P4-2**: las reglas globales
  se concatenan **antes** de las del agente y no se sustituyen, así que el array global de **313
  reglas** se elimina en Phase 5 en lugar de convivir con los bloques.
- **5 system prompts de agente (56/54/58/58/56 líneas) y 9 cuerpos de comando (24-30 líneas)
  congelados en inglés** (D-P4-6), con el contrato de referencia en español conservado en la
  spec; el blueprint del **`AGENTS.md` del vault** (67 líneas, inglés) fija la regla MCP-first, la de
  cita y la de no-contaminación de bandejas.
- **Decisiones registradas:** D-P4-6 (artefactos del payload en inglés; prosa del repo en español);
  **D-P4-7 revocada** (las muestras del instalador se quedan como están, en español); **D-P4-11**
  (los permisos se extraen a una 5.ª spec para respetar <500 líneas); **D-P4-10 retirada** (sin
  corte de skills: el dueño revisará manualmente cada una).
- **Hallazgos honestos** (registrados, no ejecutados): `doom_loop` y `lsp` **no** son acciones core
  de V2 — `doom_loop` queda reservada sin uso y `lsp` se conserva como acción de casa ampliable por
  plugin; las familias que anticipaba la fila 15 de la matriz **no existían** en el inventario y el
  barrido las sustituyó por un recuento real (**109 out-of-domain medidos**); `gen_ejemplo_pdf.py`
  **no existe** en el repo aunque un comentario del instalador lo cite; y las muestras del payload
  son **artefactos de instalación** (las crea el wizard), no ficheros versionados en el blueprint;
  por decisión del dueño (2026-11-04) conservan su nombre y su contenido en español.

### Added (config por entorno, 2026-11-03)

- **`INDEXER_DIR`** (`opencode.json` → `mcp.servers.tepochcalli-rag.environment`): conjunto de
  raíces que indexa `index_refresh()` (la tool no acepta argumentos). Multi-valor separado
  por **comas** (`"00-Resources,03-Citations"`), `strip` y vacíos descartados; rutas relativas al
  vault (una absoluta solo si cae dentro), dedup de solapadas y raíz-fichero. Fallback
  `00-Resources` si está ausente o vacía. Reemplaza el default, no lo suma (ADR-010 §4.1,
  enmendado).
- **`TEPOCHCALLI_TOP_K`**: default de `top_k` en `search` (5), sobreescribible por llamada; rango
  útil 1–8 y un valor no entero o fuera de `[1,20]` cae a 5. Se lee al arrancar el MCP.
- **Diagnóstico de configuración en `rag_status`**: el bloque `config` gana `problems` (raíz de
  `INDEXER_DIR` inexistente o fuera del vault, `TEPOCHCALLI_ROOT` mal, `TEPOCHCALLI_TOP_K`
  inválido) y `unknown_env` (nombres que parecen nuestros y no lo son: `INDEXER_DRI`,
  `TEPOCHALLI_ROOT`…). `config.valid` pasa a `false` cuando hay problemas, así que un error de
  configuración se ve en la **primera** llamada, sin indexar. No añade códigos `E_*` ni degrada
  `health`.

### Changed (config por entorno)

- **`index_refresh` ya no acepta `directories`**: el conjunto de raíces es exclusivamente
  `INDEXER_DIR` y el MCP no puede añadir ni quitar raíces. Una pasada declara el estado completo
  del índice, así que un subconjunto purgaría las filas de las demás raíces; el delta memoizado
  hace que re-escanear el conjunto completo cueste solo lo que cambió. Un agente que pase el
  argumento no cambia nada: el SDK valida por firma y descarta las claves desconocidas, así que la
  tool indexa el conjunto configurado (sin error — fijado por test; ADR-010 §4.1, rev. 2 — ADR
  editado en sitio por orden del dueño).
- La sección **`[search]` de `tepochcalli.toml` queda jubilada**: `top_k` se declara en
  `environment`. Un toml viejo que la traiga solo recibe el aviso de sección desconocida — el
  loader no lanza y el valor se ignora. El server relee el toml en cada llamada (sin caché), así
  que un swap de modelo no exige reiniciar el MCP.

### Fixed (config por entorno)

- **`TEPOCHCALLI_TOP_K` fuera de `[1,20]` ya no rompe `search`**: antes un valor como `21` hacía el
  `default` del schema igual a 21, `effective_top_k` lanzaba `ValueError` y **toda** `search` sin
  argumento devolvía `VALIDATION_ERROR`, mientras `problems` no lo señalaba (solo chequeaba >0).
  Ahora cae a 5 igual que el resto de envs inválidas y aparece en `config.problems` (spec §tabla).
- **`add_source` rechaza** con `VALIDATION_ERROR` si `00-Resources` no está declarada** en
  `INDEXER_DIR` (`details: {requested, allowed, hint}`), **antes de escribir**: antes la añadía a
  la unión del refresh de esa llamada, y con el conjunto fijado en la variable eso solo podía
  hacerse modificando raíces. Escribir un fichero que el índice no va a ver era una promesa falsa.
- **F8 del wizard borraba `environment` del usuario al reinstalar**: ahora conserva las claves que
  no gestiona e impone solo `TEPOCHCALLI_ROOT`, así que las ediciones de `INDEXER_DIR` y
  `TEPOCHCALLI_TOP_K` sobreviven a una reinstalación.

### Changed (estados, 2026-11-03)

- **ADR-009/010/011 pasan a *Accepted*** (FTR 2026-11-03): las cuatro specs enmendadas
  (`spec-mcp-server`, `spec-markitdown`, `spec-rag-engine`, `spec-vault-structure`) quedan
  definitivas — la última promovida a *Approved* — y Phase 4 (blueprint) queda desbloqueada.

### Added (Phase 3.5, 2026-11-03)

- **Tres tools del conversor en `tepochcalli-rag`** — `convert_document`, `convert_base64` y
  `list_formats` —: markitdown **en proceso**, escritura atómica dentro del vault y respuesta
  **summary-only** (5 claves: `written_to`, `source_uri`, `bytes`, `chars`, `preview` ≤500
  chars). El cuerpo convertido nunca viaja al LLM (ADR-009). El server pasa de **4 a 7 tools**.
- **Índice multi-raíz**: `index_refresh()` indexa el conjunto de raíces que declara `INDEXER_DIR`,
  recursivo a cualquier profundidad; una raíz puede ser un fichero suelto; las solapadas se
  deduplican; `source_path` es **relativo al vault** y `rag_status` publica
  `last_refresh_roots`/`available_roots` (ADR-010).
- **RAG de documentos nativo**: `.pdf/.docx/.pptx/.xlsx/.xls` se indexan en su forma original
  (markitdown), con `doc_kind` propio y `offsets_ref="extract"` — sin convertirlos antes a `.md`
  (D49/D51). El PDF pierde `heading` y se declara (D54).
- **Skill `tepochcalli-mcp`** en el payload (`.opencode/skills/tepochcalli-mcp/SKILL.md`):
  catálogo único de decisión de las 7 tools, defaults, errores y fallback `anydoc`.
- Contract tests e2e de las 7 tools, negativos de la frontera B′ y e2e bulk de 1 000 páginas
  (test `slow`).

### Changed (Phase 3.5)

- **Dieta de dependencias (ADR-011):** `markitdown[docx,pptx,xlsx,xls,pdf]==0.1.9` en proceso y
  `cocoindex[lancedb,sentence-transformers,litellm]`; `litellm` deja de ser dependencia directa
  (pin por `[tool.uv] constraint-dependencies`). Venv medido: **1,921 GiB** y **135 paquetes**
  (antes 184); lock **193 → 140** entradas.
- **Extracción de documentos con markitdown** en el motor (antes Docling): Δ de texto p95
  **4 299 ms** (n=20, nearest-rank; Phase 1: 5 385/5 466/5 952 ms), RSS `VmHWM` **1 486 MiB**
  (texto) / **1 601 MiB** (documentos) frente a 2 048–2 189 MiB con Docling.
- Una sola implementación de embedder (write y read sobre el mismo path del snapshot) y
  `@coco.fn` en los helpers para que editar el parser invalide el memo (D58/D59).
- Frontera **B′** documentada en `docs/SECURITY.md`: entrada **y** salida dentro del vault,
  validación de raíces (existencia y tipo) y symlinks acotados al vault.

### Removed (Phase 3.5)

- `mcp.servers.markitdown` del payload: el server standalone ya no existe; la conversión es una
  librería en proceso de `tepochcalli-rag`.
- `docling`, `torchvision` y `markitdown-mcp` del venv (ADR-011).

### Fixed (Phase 3.5)

- Reintentos con backoff en el embedder remoto: llegan con `LiteLLMEmbedder` (**TD-16
  cerrada**), conservando `E_API_AUTH` y el scrub de la clave.
- Write y read resuelven **el mismo path pineado** del snapshot (bug de espacio vectorial
  desalineado: el índice se construía con «main» y la query con un SHA). `require_local_model`
  sigue comprobando solo que el directorio no esté vacío — deuda TD-29.
- `spec-rag-engine` §Target corregida: `offsets_ref` **no** es columna persistida; se deriva de
  `doc_kind` al leer.

**No verificado en esta fase:** GitHub Actions nunca ha corrido (M6); los 3 tests `slow`
(incluye el bulk) van aparte; el coste de un PDF de 30 páginas con markitdown **no se midió**;
Windows sigue sin probar. Detalle en `docs/WORKFLOW.md` §Phase 3.5.

### Added (Phase 3, 2026-10-28)

- **Wizard de instalación `tepochcalli`**: crate Rust
  (`crates/tepochcalli/`) con las 8 fases atómicas F1-F8 — prereqs, directorio del
  vault, extracción del payload con merge sin sobreescribir (+ `.install-intent`,
  `00-Resources/` con 2 placeholders), bootstrap de `uv` verificado por SHA-256,
  `uv venv` + `uv sync --frozen`, menú "Embedding provider" (5 salidas, default
  `paraphrase-multilingual-MiniLM-L12-v2` preseleccionado, badges con etiqueta
  `medido`/`estimado`/`declarado`, gate test-embed con RSS pico medido por
  `python -m tepochcalli_flow`), indexación inicial y merge conservador de
  `mcp.servers` (con `.bak`, comando portable por SO, sin registrar `markitdown`).
- Post-instalación: `--resume` (artefactos + marker `.install-state`), `--offline`
  (`E_OFFLINE_NO_CACHE`, exit 21), idempotencia install×2, UX de fallo con panel +
  log fuera del vault, swap atómico `tepochcalli config embedder` (`--confirm`
  obligatorio, índice viejo servible, auto-GC con `--keep-previous`), `tepochcalli
  reindex --confirm` (cierra TD-3) y `tepochcalli uninstall` (solo `.tepochcalli/`).
- Distribución: `dist.toml` (5 targets, installers shell+powershell), workflows
  de release y matriz CI (ubuntu+macos; Windows fuera de la matriz — deuda M6/D-b),
  installers de referencia en `crates/tepochcalli/installers/`, regla one-version
  (el binario instala siempre el payload de su propia versión, verificado por SHA-256).
  **No verificado**: ningún workflow ha corrido, no hay release publicada, Windows
  sin probar (ver FTR Phase 3→4 en `docs/WORKFLOW.md` §4).

### Changed (Phase 3)

- Nuevas recipes en el `Justfile`: `rust-fmt`, `rust-lint`, `rust-test`, `rust-ci`,
  `wizard-smoke` — nada de `cargo` crudo (CODE_STYLE).

### Fixed (Phase 3)

- **R6 cerrada** (T9): `pyproject.toml` del payload declara `tepochcalli_mcp.tools` —
  un wheel construido ya no perdería el subpaquete; verificado con
  `import tepochcalli_mcp.tools.search` en el venv del vault.

### Added (Phase 2, 2026-10-27)

- **Servidor MCP `tepochcalli-rag`**: paquete `tepochcalli_mcp`
  (stdio local) con las 4 tools del contrato congelado — `search`, `index_refresh`,
  `add_source`, `rag_status` — registrado en `opencode.json` del payload e invocado con
  `python -m tepochcalli_mcp` (D17).
- Dialecto de errores `E_*` (5 códigos con precedencia fija) y proveedor de embeddings
  `none | litellm` además de `local` (D15), con fábrica única de embedders.
- `add_source`: conversión con markitdown **en proceso**, escritura atómica dentro de
  `00-Resources/` y reindex en una llamada; **rechazo de `file:` fuera del vault** (D16) —
  ver docs/SECURITY.md.
- Contract tests D7.3 (`tests/e2e/test_mcp_contract.py`), e2e «pregunta → tool-call →
  JSON citado» con fixture golden grabada (`tests/fixtures/golden_vault/`) y bench
  `tests/benchmarks/bench_search.py` (p95 = 52 ms medido, n=20 nearest-rank, cota <500 ms).
- `markitdown-mcp` como segundo server local del payload: `markitdown[all]`, **+142 MB y
  49 paquetes** medidos (D18, coste registrado en TD-12).

### Changed (Phase 2)

- Superficie tipada de mypy estricto: `flow/` → **`flow/` + `mcp/`**
  (`files = ["flow", "mcp"]`).
- Docs de fase cerrados con métricas **medidas**: `docs/WORKFLOW.md` (Phase 2 + §8 D15-D18),
  `docs/ARCHITECTURE.md` (inventario y diagrama de la capa MCP), `docs/TECH_DEBT.md`
  (TD-1 pagada, TD-3 pagada, TD-12 nueva y deuda de Phase 2), `docs/CODE_STYLE.md`,
  `docs/SECURITY.md` (límite `file:` + clave de API).

### Fixed (Phase 2)

- **PDFs que nunca se indexaban en producción** (bug de Phase 1, F-T7-2): `app.index_file`
  leía el PDF como UTF-8 y absorbía el `UnicodeDecodeError` en `skipped` con `rc=0` —
  ahora delega la lectura en `extract_text` (Docling), con guardia TOCTOU preservada y
  offsets F1 byte-idénticos para md/txt.

### Changed (versión y README del beta, 2026-11-23)

- **Versión del árbol a `0.1.0-beta.1`** en `crates/tepochcalli/Cargo.toml` + `Cargo.lock`,
  `.tepochcalli/pyproject.toml` del payload y `__version__` del MCP; `uv.lock` normalizado por uv
  a `0.1.0b1`. `just rust-wheel-verify` verde ⇒ `uvx OK: tepochcalli 0.1.0-beta.1`.
- **`README.md`:** nueva sección «Instalación (beta 0.1.0-beta.1)» con el canal real (desde el
  código fuente) y el estado del canal `uvx`.

### Fixed (segunda revisión de Phase 6.5/6.6, 2026-11-23)

- **Rollback completo y medido** sobre todo lo que escribe el instalador (`.opencode/`,
  `10-templates/`, `AGENTS.md`, `.gitignore`, `opencode.json`), con journal antes del `fs::copy` y
  `compensate_phase3` que poda directorios vacíos.
- **Guardas de estado:** `run_menu` con `try_init` (sin panic fuera de TTY), frontera
  `application→adapters` cerrada moviendo `rollback_overwrite` al puerto, `config embedder` sin
  `--confirm` ⇒ exit 2 y `update` exige un workspace instalado.
- **Seguridad de ficheros:** symlinks rechazados en `.bak`, raíz del vault y miembros del tar;
  `ENOSPC` mapeado a `DiskFull` (exit 30).

### Security

- **`zip` 2.6.1 → 9.8.2** por `CVE-2026-115905` (CVSS4 crítico, corregido en 9.0.5) y 8 advisories
  más (verificado contra OSV el 2026-11-23). El único uso es `extract_zip`, con
  `validate_member` y extracción en dos fases.

### Known limitations

- **Sin rueda en PyPI ni binarios en el release:** `uvx tepochcalli` (canal objetivo de ADR-014)
  todavía no funciona; la instalación es **desde el código fuente** y el `install.sh` del repo
  solo sirve cuando existan assets de binario.
- **6 plugins npm del payload en `@latest`:** riesgo de supply-chain aceptado por el dueño.
- **Windows y TTY real:** declarados, no medidos.
- **C3 y C6:** benchmarks manuales, fuera del gate.

---

### Contributing to the CHANGELOG

When contributing to this project:

1. **Add entries** to the `[Unreleased]` section
2. **Follow semantic versioning** for breaking changes
3. **Use appropriate categories** (Added, Changed, Deprecated, Removed, Fixed, Security)
4. **Include dates** in `YYYY-MM-DD` format
5. **Provide clear descriptions** explaining the impact of changes
6. **Group by phase** (Define, Plan, Build, Verify, Review, Ship)
7. **Reference related issues** or pull requests when applicable

### Why This CHANGELOG Matters

This CHANGELOG serves as living documentation that:

- **Tracks the evolution** of the AI-assisted development template
- **Communicates changes** to users and contributors
- **Provides update guidance** for future releases
- **Documents architectural decisions** and their rationale
- **Enables automated release processes** with structured change tracking
