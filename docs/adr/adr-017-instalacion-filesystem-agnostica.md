# ADR-017: Instalación filesystem-agnóstica — ejecutables en el state dir del SO y vault por directorio corriente

* **Status:** Accepted 2026-11-24 (orden del dueño)
* **Date:** 2026-11-24
* **Age:** 2026-11-24 (decisión vigente desde la orden del dueño)
* **Decision Makers:** Fisherk2 (dueño del repo; orden de 2026-11-24); Arquitecto (redacción)
* **Consulted:** invariante de codice-opencode `InstallUseCaseBase.ts:59-105`, `AtomicStager.ts:452-550`, `ADR-011:30`, `symlinks.ts:17-21` (<https://github.com/Fisherk2/codice-opencode/tree/main/src>); [ADR-004](adr-004-uv-venv-aislado.md) §3/§4/§7 (uv + venv local), [ADR-003](adr-003-distribucion-cargo-dist.md) (backend de release), [ADR-014](adr-014-distribucion-uvx-pypi.md) (canal `uvx`)
* **Informed:** autor del wizard (Rust, `crates/tepochcalli/`), mantenedores de `specs/spec-installer-wizard.md` y `specs/spec-vault-structure.md`, usuarios del vault
* **Traceability:** [spec-installer-wizard](../../specs/spec-installer-wizard.md) §Enmienda 2026-11-24; [spec-vault-structure](../../specs/spec-vault-structure.md) §Layout de `.tepochcalli/` (D2); docs/BACKLOG.md §8 (fila 2026-11-24)

> **Nota de alcance:** este ADR **REFINA** la ubicación física descrita en [ADR-004](adr-004-uv-venv-aislado.md)
> §3 (opción «uv con venv del proyecto»), §4 (booteo de `uv` en `.tepochcalli/bin/`) y §7
> (relación con ADR-003), y se relaciona con ADR-003/ADR-014. **La decisión de fondo de ADR-004
> (uv + venv local, usuario sin Python en el host) permanece intacta**, igual que el canal `uvx`.
> ADR-003, ADR-004 y ADR-014 quedan **byte-idénticos**; no se reeditan ADRs *Accepted*.

## 1. Context and Problem Statement

El mounting de desarrollo del repo es fuseblk/NTFS-3G: `chmod` sobre los ficheros del vault es un
no-op y ejecutar un binario desde el vault falla con `Permission denied (os error 13)` (el mismo
límite que obligó a fijar `CARGO_TARGET_DIR` bajo `/tmp/opencode/`). ADR-004 §3/§4 sitúa el binario
`uv` en `<vault>/.tepochcalli/bin/` y lo ejecuta desde ahí; esa ubicación no es filesystem-agnóstica.

Existen dos fuerzas adicionales en la preparación de `0.1.0-beta.2`:

1. `resolve_vault_dir` preguntaba al usuario el destino aunque el proceso ya corriera dentro del
   vault destino; la TUI añadía fricción a una operación que puede deducirse del cwd.
2. Las fases F3/F4/F5/F7 no mostraban la barra indeterminada ya existente (`Ui::run_cancellable`),
   mientras F6 y el mirror sí son prompts interactivos que deben conservarse.

## 2. Decision Drivers

* **Filesystem-agnóstico:** el vault puede residir en NTFS-3G/fuseblk sin exigir bit de ejecución.
* **Cero cambio de contrato:** `Phase4Report.uv`, F5, `resume.rs` y la ruta runtime de
  `opencode.json` siguen apuntando a `.tepochcalli/bin/uv` / `.tepochcalli/venv/`.
* **Cero dependencia nueva:** reutilizar `state_dir()` (ya usado por los logs de fallo), el
  verificador SHA-256 y la barra `Ui::run_cancellable` existentes.
* **UX sin fricción:** el destino por omisión es el directorio corriente; `--vault <dir>` sigue
  ganando; los prompts interactivos de F6/mirror no se tocan.
* **Rollback sin pérdida:** la compensación de F4 no puede borrar el state root, porque los logs
  viven allí.

## 3. Considered Options

* **Ejecutables en el state root del SO + enlace simbólico en el vault (elegida):** `uv` se
  descarga, se verifica con SHA-256, se hace ejecutable y se ejecuta desde
  `application::failure::state_dir()`; `<vault>/.tepochcalli/bin/uv` es un symlink Unix al binario
  real (en Windows se conserva la copia `.exe`).
* **Ejecutar `uv` desde `.tepochcalli/bin/` con `chmod +x` (estatus quo de ADR-004):** rechazada —
  en el mount NTFS-3G el bit no se fija y la ejecución falla.
* **Copiar `uv` al vault sin bit de ejecución y ejecutarlo mediante un loader intermedio:**
  rechazada — añade una capa nueva sin beneficio frente al symlink y rompe la invariante de Codice.
* **Exigir `--vault` siempre:** rechazada — el usuario que ya está dentro del vault destino no debe
  repetir la ruta.

## 4. Decision Outcome

**Chosen option: ejecutables en el state root del SO + symlink en el vault**, porque satisface la
invariante extraída de codice-opencode: *«los ejecutables viven en la raíz de runner/caché fuera del
destino; el destino recibe solo ficheros de datos y symlinks — nunca se requiere un bit de
ejecución dentro del destino»* (`InstallUseCaseBase.ts:59-105`, `AtomicStager.ts:452-550`,
`ADR-011:30`, `symlinks.ts:17-21`). Aterrizaje en Tepochcalli:

* `application::failure::state_dir()` — `$XDG_STATE_HOME/tepochcalli` o
  `$HOME/.local/state/tepochcalli` en POSIX; `%LOCALAPPDATA%/tepochcalli` en Windows — aloja el
  `uv` verificado, chmoddeado y ejecutado; si no hay `HOME`/XDG, cae a `std::env::temp_dir()`
  (**no garantizado exec-capable**: limitación declarada, no promesa).
* `<vault>/.tepochcalli/bin/uv` es un **symlink Unix** a ese binario (`std::os::unix::fs::symlink`
  en `application/installer.rs`); en Windows se mantiene la copia `.exe`. La ruta pública sigue
  siendo la misma: `Phase4Report.uv`, F5, `resume.rs` y `opencode.json` no cambian.
* `compensate_phase4` retira `bin/` del vault, `bin/` del state root y `.uv-stage`, **nunca el state
  root** (logs). No toca `models/`, `db/` ni `config/`.
* `resolve_vault_dir` no pregunta: sin `--vault` o con valor en blanco ⇒ `current_dir()` absoluto;
  `--vault <dir>` sigue ganando. Help: `vault directory (default: current directory)`.
* F3/F4/F5/F7 usan la barra indeterminada existente (`Ui::run_cancellable`), con el vault destino
  en el título; F6/mirror siguen siendo prompts interactivos; las líneas de estado quedan fuera de
  la pantalla alternativa.

### 4.1 Confirmation

Instalación real sobre el montaje fuseblk/NTFS-3G: **exit 0**, F4+F5 en verde y
`venv/bin/python` → CPython 3.12.14. Citas de código (sin cambios documentales en él):
`application/prereqs.rs:97-107` (cwd), `application/installer.rs:167-173, 184-193, 387-402,
444-456` (symlink, report y compensación), `application/failure.rs:11-36` (`state_dir()`),
`cli/usage.rs:34,49,61,72,86` (help), `cli/install_phases.rs:150,244,266,316` (barras).

## 5. Pros and Cons of the Options

### Ejecutables en el state root + symlink (elegida)

* ✅ **Pros:** el vault recibe solo datos y un enlace; instala en NTFS-3G sin `chmod`; reutiliza
  `state_dir()` y el SHA-256 ya existentes; contrato MCP y rutas públicas intactos.
* ⚠️ **Cons:** el ejecutable real queda fuera del vault (no viaja con él); el symlink necesita un
  state root exec-capable; en Windows se mantiene una copia `.exe` por rama ya existente.
* ⚖️ **Neutral:** el directorio `.tepochcalli/bin/` sigue visible y gitignored como antes.

### `chmod` dentro del vault

* ✅ **Pros:** un solo árbol autocontenido.
* ⚠️ **Cons:** `Permission denied` en el mount real del repo; contradice la invariante de Codice.
* ⚖️ **Neutral:** —

### Loader intermedio / `--vault` obligatorio

* ✅ **Pros:** no mueven el ejecutable (loader) / hacen explícito el destino (`--vault`).
* ⚠️ **Cons:** nueva capa de ejecución; o fricción innecesaria cuando el cwd ya es el vault.
* ⚖️ **Neutral:** —

## 6. Consequences

* ✅ **Positives:** instalación filesystem-agnóstica verificada en el mount problemático; H6 sigue
  mostrando progreso y destino sin preguntar de más; rollback de F4 no destruye logs.
* ⚠️ **Negatives / Risks:** si `HOME` y `XDG_STATE_HOME` no están definidos, `state_dir()` cae a
  `temp_dir()`, sin garantía de ejecución; un vault copiado a otra máquina necesita re-bootstrap de
  `uv` (ya era así con el venv, ADR-004 §6).
* ⚠️ **Limitación declarada (cancelación solo visual):** en F3/F4/F5/F7 la barra `Ui::run_cancellable`
  usa un `CancelToken` nuevo, pero las APIs de esas fases no aceptan token: Esc/Ctrl+C cancela la
  pantalla y marca el token sin detener los subprocesos, así que el trabajo continúa y la fase puede
  completarse. La cancelación que sí detiene el trabajo sigue en F6 (descarga del modelo,
  `embedder_gate.rs`) y en update/uninstall/reindex; ampliarla exige ensanchar las APIs de fase y
  queda diferida.
* ⚖️ **Neutral:** no cambia canal (`uvx`, ADR-014), backend de release (ADR-003), venv pineado ni
  los contratos de `tepochcalli-rag`; la topología de cuatro capas queda intacta.

## 7. Related Decisions

* [ADR-004](adr-004-uv-venv-aislado.md) §3/§4/§7 — **refinado en la ubicación física**, no reemplazado.
* [ADR-003](adr-003-distribucion-cargo-dist.md) / [ADR-014](adr-014-distribucion-uvx-pypi.md) —
  backend/canal de release; el asset `uv` sigue siendo el publicado y verificado por SHA-256.
* [ADR-016](adr-016-resiliencia-offline-y-rollback.md) — preflight, cancelación y rollback de
  H6/H7/H9; esta decisión comparte su disciplina de compensación sin ampliar su alcance.

## 8. Compliance and Review

* **Success metrics:** `install` sobre fuseblk/NTFS-3G con exit 0, F4+F5 verdes y `uv --version`
  ejecutado desde el state root; `venv/bin/python` reporta CPython 3.12.x; sin prompts de destino
  cuando el cwd es el vault; F3/F4/F5/F7 con barra y F6/mirror interactivos intactos.
* **Next review date:** 2027-05-24
* **Revisit triggers:** un SO sin state root ejecutable (caída a `temp_dir()`), un cambio del
  canal `uvx` que mueva el ejecutable al vault, o un cambio del contrato `Phase4Report.uv`.
* **Evidencia:** `medido` en el mount de desarrollo (exit 0, F4+F5, CPython 3.12.14).

---
*Formato basado en [MADR v4.0](https://adr.github.io/madr/), igual que [adr-template.md](adr-template.md).*
