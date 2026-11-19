# ADR-014: Publicar el binario del wizard como rueda de PyPI y hacer de `uvx` el único canal recomendado

* **Status:** Proposed
* **Date:** 2026-11-18
* **Decision Makers:** Dueño del repo (orden del flujo destino, 2026-11-18, docs/UH.md §"Wizard de instalación: flujo destino"); Arquitecto (redacción)
* **Consulted:** [ADR-013](adr-013-distribucion-cargo-binstall.md) (canal vigente), [ADR-003](adr-003-distribucion-cargo-dist.md) (backend), [ADR-004](adr-004-uv-venv-aislado.md), [ADR-011](adr-011-politica-dependencias-dos-librerias.md); documentación de maturin (`bindings = "bin"`) y de `uv tool run` (`uvx`)
* **Informed:** Usuarios finales (investigadores), CI de release, docs/ARCHITECTURE.md §Key decisions (4)
* **Traceability:** docs/UH.md:253-261 (flujo destino; `:255` «no se implementan ni se aprueban aquí»), docs/UH.md:258 («este flujo exige un ADR-014 que supere el canal de ADR-013 (que rechazó uv/PyPI) y el backend de ADR-003»), [spec-installer-wizard](../spec-installer-wizard.md):181 (one-version rule), [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md):294

> **Nota de alcance:** este ADR está **Proposed**: no entra en vigor hasta la aprobación
> explícita del usuario (AGENTS.md:205 — «Decisiones D1-D6: NO se re-litigan en código —
> requieren ADR nuevo aprobado por el usuario», aplicable a D1-D8). Los ADRs citados son
> *Accepted* y **no se re-editan ni se borran**: este documento registra la sustitución del
> canal y la intención de retiro del backend; la materialización (tocar `dist.toml`,
> `release.yml`, `crates/`) es tarea futura fuera del alcance de este ADR.

## 1. Context and Problem Statement

El flujo destino del wizard ordenado por el dueño (docs/UH.md:253-261, 2026-11-18) exige un
**comando único** que abra el wizard Rust sin binario instalado en PATH y sin descargas en
runtime: `uvx tepochcalli`. El canal vigente (ADR-013, *Accepted*) son **dos pasos** —
`cargo binstall tepochcalli` instala y termina; `tepochcalli install --vault <ruta>` configura
(ADR-013 §6(a), `:125-128`)— y exige toolchain Rust en el host del investigador. Además,
ADR-013 evaluó y **descartó** explícitamente uv/PyPI, premisa que el dueño invierte hoy.

¿Cuál es el canal único recomendado de instalación del wizard `tepochcalli`?

## 2. Decision Drivers

* **One-liner real:** un solo comando abre el wizard; nada de «instalar el instalador» como
  paso previo (débacle de los dos pasos de ADR-013 §6(a)).
* **Sin binario en PATH y sin descargas en runtime** (docs/UH.md:257): la rueda queda en la
  caché de `uv` hasta su limpieza.
* **Reutilizar la toolchain que el producto ya trae:** el wizard bootea `uv` en
  `.tepochcalli/bin/` (ADR-004 §4, `:32`); `uvx` es el mismo `uv` — cero gestor nuevo para el
  usuario.
* **Cero herencia de usuarios rota:** hoy no hay nada que migrar (ver §6).
* **Refresco determinista:** el TUI debe poder mostrar un comando exacto de refresco
  (`uvx --refresh tepochcalli`, docs/UH.md:257 y `:273`).

## 3. Considered Options

* **Option A:** `uvx tepochcalli` — rueda de PyPI que empaqueta el binario Rust vía maturin
  `bindings = "bin"` (script embebido, sin módulo Python). Elegida.
* **Option B:** `cargo binstall tepochcalli` — el canal vigente de ADR-013; dos pasos, exige
  `cargo` + `cargo-binstall` en el host (ADR-013 §6(b), `:129-131`).
* **Option C:** `shell`/`powershell` de cargo-dist (`curl | sh` / `irm | iex`) — un paso pero
  pipe de script remoto, exactamente lo que el dueño quiere desterrar (ADR-013 §1, `:17-22`).
* **Option D:** `bunx` (modelo de codice-opencode) — exige bun en el host; ADR-003 §4 `:31` ya
  descartó introducir Node/bun en hosts de investigadores.

## 4. Decision Outcome

**Chosen option: Option A — `uvx tepochcalli` como ÚNICO canal recomendado.** El crate se
publica en PyPI como rueda generada con **maturin `bindings = "bin"`**: empaqueta el binario
Rust como script ejecutable sin escribir código Python. El usuario ejecuta `uvx tepochcalli`
y el wizard se abre directo (docs/UH.md:257). Refresco: `uvx --refresh tepochcalli`
(alternativa `uvx tepochcalli@latest`); ese es el comando que el TUI muestra cuando la
versión instalada supera a la del wizard (docs/UH.md:273).

### 4.1 Relación con los ADRs existentes (sin editarlos)

* **Sustituye el CANAL de ADR-013 — invierte su descarte de uv/PyPI.** ADR-013 §3 `:52-53`
  rechazó la opción: «uv/PyPI (`uv tool install tepochcalli`) — reutilizar el gestor que el
  wizard ya usa; **descartado: el wizard es Rust, no hay paquete Python que publicar**, y
  añade otra toolchain», y §5 `:115-119` remató: «no existe paquete Python que publicar (el
  wizard es Rust); produce un canal más que mantener para cero ganancia. **Descartado.**».
  Esta decisión **INVIERTE ese descarte** de forma explícita: la premisa «no hay paquete
  Python que publicar» deja de ser cierta porque maturin `bindings = "bin"` fabrica la rueda
  sin código Python, y el «otro gestor» no es nuevo — es el `uv` que ADR-004 ya instala.
  Registrada la inversión, no queda drift de trazabilidad: ADR-013 queda desplazado en su
  canal al aprobarse este ADR; no se re-edita (es *Accepted*).
* **Declara el RETIRO del backend de ADR-003 (cargo-dist).** Por decisión EXPLÍCITA del dueño
  (2026-11-18, docs/UH.md:257 «Se retira `cargo binstall` / cargo-dist como canal recomendado»
  y `:258`), ADR-014 decreta retirar `crates/tepochcalli/dist.toml` y
  `.github/workflows/release.yml` (ambos existen hoy). **La MATERIALIZACIÓN del retiro (borrar
  esos ficheros, reescribir la CI) es TAREA FUTURA** fuera del alcance de `/evolve`; este ADR
  solo documenta la intención. ADR-003 **no se re-edita** (es *Accepted*); su driver «Cero
  dependencia de registrarse en un registro de paquetes para publicar» (`:19`) queda revertido
  — ver §6.
* **ADR-004 (uv + venv del proyecto) queda INTACTO.** `uvx` es el mismo binario `uv` que el
  wizard bootea; el runtime del vault (venv, deps pineadas) no cambia. Precedente de esta
  redacción: ADR-013 §7 `:155` — «ADR-004 — el wizard sigue booteando `uv`; instalar el wizard
  con cargo no cambia nada del runtime del vault»—, aplicable igual con `uvx`.
* **ADR-011 (ledger de dos librerías Python) queda INTACTO.** `maturin` y la cuenta de PyPI
  son **toolchain de build/distribución** del crate Rust, no dependencias del ledger Python de
  runtime (`cocoindex` + `markitdown`); el `pyproject.toml` pineado del vault no gana ni una
  dependencia por este ADR.

### 4.2 Versión canónica (one-version rule)

La versión canónica la fija `.tepochcalli/pyproject.toml` (`:3` — hoy `0.1.0`);
`crates/tepochcalli/Cargo.toml` (`:3` — hoy `0.1.0-beta.1`) **se alinea detrás** de ella.
Esto resuelve la contradicción actual: [spec-installer-wizard](../spec-installer-wizard.md):181
exige la one-version rule («wizard y vault versionan juntos»), pero las dos versiones medidas
hoy divergen (docs/UH.md:260 lo constata: «deben alinearse antes de implementar»). Con `uvx`
la versión del wizard la gestiona el **paquete publicado en PyPI** y la instalada se detecta
leyendo `.tepochcalli/pyproject.toml` (docs/UH.md:260); wizard y payload viajan en la misma
rueda, que es la satisfacción mecánica de la regla.

### 4.3 Dependencias de release — PENDIENTES de visto bueno

`maturin` + cuenta/publicación en **PyPI** constituyen una **toolchain de release NUEVA**.
Quedan listados aquí pero **NO fijados**: añadir capacidad de distribución fuera de lo
transitivo exige el visto bueno del dueño (R1 en AGENTS.md §Research & Reuse; "Ask first" en
[SPEC.md](../../SPEC.md):97). Este ADR los propone; la aprobación del Status cierra la puerta.

### 4.4 Confirmation

* Con `uvx tepochcalli` en un host **sin** `cargo` ni binario en PATH se abre el wizard en un
  solo paso; `uvx --refresh tepochcalli` levanta la última release.
* La rueda para los targets de la matriz actual (x86_64/aarch64 Linux, x86_64/aarch64 macOS,
  x86_64 Windows) se resuelve e instala sin compilar en el host.
* **Estado de la evidencia: `declarado`.** Nada de esto está implementado (el ADR es
  *Proposed*); ver §4.5 sobre M6.

### 4.5 Cero herencia rota

**No rompe usuarios: no existen.** `cargo binstall tepochcalli` **nunca corrió en producción**:
0 tags publicados y `release.yml` nunca se ejecutó — **M6 sigue abierto**
([docs/TECH_DEBT.md](../../docs/TECH_DEBT.md)), evidencia declarada en ADR-013 §4.1 `:73-75`
(«`cargo binstall` nunca se ha ejecutado contra un release de este repo y `release.yml` nunca
ha corrido»). Migrar el canal hoy cuesta cero instalaciones huérfanas.

## 5. Pros and Cons of the Options

### Option A — `uvx` + rueda PyPI (elegida)

* ✅ **Pros:** un solo comando, sin toolchain Rust ni Node en el host; reutiliza el `uv` que
  ADR-004 ya bootea; registro con nombre `tepochcalli` y checksums de rueda; la rueda persiste
  en caché (sin descargas en runtime); el refresco es un comando copiabile del TUI.
* ⚠️ **Cons:** exige cuenta y publicación en PyPI (revert del driver de ADR-003 `:19`); una
  rueda publicada es **inmutable** — no se borra ni sobrescribe, solo nueva versión (mismo
  coste que ADR-013 §6(g) `:145-146` atribuía a crates.io); pipeline de release nuevo que
  mantener (maturin, matriz de targets de rueda); requiere `uv` en el host para el primer
  arranque (mitigable con el installers de uv documentados, o aceptado: es el gestor del
  propio vault).
* ⚖️ **Neutral:** el flag `--vault` vuelve a viajar en el one-liner (`uvx tepochcalli install
  --vault <ruta>` reenvía args, a diferencia de binstall — corrige el two-step de ADR-013
  §6(a)).

### Option B — `cargo binstall` (canal vigente, ADR-013)

* ✅ **Pros:** verificabilidad crates.io + checksums; ya especificado y *Accepted*.
* ⚠️ **Cons:** dos pasos obligatorios; toolchain Rust en el host del investigador; sin assets
  para targets fuera de la lista cae a `cargo install` y compila (ADR-013 §5 `:84-86`).
  Descartado por este ADR por orden del dueño (docs/UH.md:257).

### Option C — `shell`/`powershell` (`curl | sh`)

* ✅ **Pros:** cero toolchain; ya generado por cargo-dist.
* ⚠️ **Cons:** pipe de script remoto como primer paso — el obstáculo de adopción que el dueño
  declaró desde ADR-013 §1. Descartado como recomendado.

### Option D — `bunx` (modelo Codice)

* ✅ **Pros:** uno-liner probado en codice-opencode; acepta flags.
* ⚠️ **Cons:** introduce bun en hosts de investigadores — descartado en ADR-003 §4 `:31` y no
  reabierto aquí.

## 6. Consequences

* ✅ **Positives:** el flujo destino de docs/UH.md:257 queda con canal documentado y con el
  descarte previo de ADR-013 explícitamente invertido (trazabilidad cerrada); la one-version
  rule pasa a tener dueño de versión único (PyPI + `pyproject.toml` canónico); cero usuarios
  que migrar (§4.5).
* ⚠️ **Negatives / Risks:** **PyPI pasa a ser un registro requerido** del proyecto — revierte
  el driver "cero registro de paquetes" de ADR-003 `:19`; riesgo operativo de publicar:
  inmutabilidad de la rueda (un error de empaquetado solo se corrige con versión nueva,
  nunca se sobrescribe) y exposición del nombre del paquete; nuevo coste de mantenimiento del
  pipeline uvx (maturin + matriz de ruedas + orden tag→rueda→anuncio).
* ⚖️ **Paradigm shifts:** la distribución del binario Rust pasa del ecosistema Rust
  (crates.io/cargo-dist) al ecosistema Python (PyPI/uv) sin que el wizard deje de ser Rust;
  `docs/ARCHITECTURE.md` §Key decisions 4 (`:294`) y `spec-installer-wizard.md` §Versionado y
  release describen el canal viejo — se actualizan cuando este ADR pase a *Accepted*
  (enmienda hermana), no antes.

## 7. Related Decisions

* [ADR-013](adr-013-distribucion-cargo-binstall.md) — **sustituido en su canal** (cargo
  binstall deja de ser recomendado); no se re-edita (Accepted). Este ADR invierte su §3 `:52-53`
  y §5 `:115-119`.
* [ADR-003](adr-003-distribucion-cargo-dist.md) — backend cargo-dist **decretado en retiro**
  por el dueño (2026-11-18): `crates/tepochcalli/dist.toml` +
  `.github/workflows/release.yml`; materialización = tarea futura; no se re-edita (Accepted).
* [ADR-004](adr-004-uv-venv-aislado.md) — **INTACTO**: `uvx` es `uv`; precedente de la
  declaración en ADR-013 §7 `:155`.
* [ADR-011](adr-011-politica-dependencias-dos-librerias.md) — **INTACTO**: maturin/PyPI no son
  deps del ledger Python de runtime.
* [spec-installer-wizard](../spec-installer-wizard.md) §Versionado y release (`:179-186`) —
  exige enmienda al aprobarse (flags del one-liner, orden de release, refresco).

## 8. Compliance and Review

* **Success metrics:** tras la aprobación, `uvx tepochcalli` abre el wizard en VM limpia (sin
  `cargo`, sin binario previo) y completa las 8 fases; `uvx --refresh tepochcalli` actualiza
  en una release real. Hoy todo es `declarado` (M6 abierto, ADR-013 §4.1 `:73-75`).
* **Next review date:** 2027-05-18
* **Revisit triggers:** PyPI indisponible o el nombre del paquete en disputa → reevaluar canal
  espejo (TestPyPI primero); targets de rueda insuficientes que fuercen compilación en host →
  reabrir `shell` como fallback; usuarios que exijan cero `uv` en host → reevaluar.

## References

* docs/UH.md:253-261 — «Wizard de instalación: flujo destino (2026-11-18)» (requisito del dueño; `:255`: «no se implementan ni se aprueban aquí»)
* maturin — `bindings = "bin"` (mixed Rust-binary packaging): <https://www.maturin.rs/project_layout.html>
* uv — `uv tool run` (`uvx`) y `--refresh`: <https://docs.astral.sh/uv/concepts/tools/>
* [ADR-013](adr-013-distribucion-cargo-binstall.md) · [ADR-003](adr-003-distribucion-cargo-dist.md) · [ADR-004](adr-004-uv-venv-aislado.md) · [ADR-011](adr-011-politica-dependencias-dos-librerias.md)
* [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) §Key decisions (4), `:294`
* M6 (release nunca ejecutado): [docs/TECH_DEBT.md](../../docs/TECH_DEBT.md)

---
*Formato basado en [MADR v4.0](https://adr.github.io/madr/), igual que [adr-template.md](adr-template.md).*
