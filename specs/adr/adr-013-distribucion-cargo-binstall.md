# ADR-013: Recomendar `cargo binstall` como canal de instalación del wizard

* **Status:** Accepted
* **Date:** 2026-11-13
* **Decision Makers:** Dueño del repo (decisión directa, 2026-11-13); Arquitecto (redacción)
* **Consulted:** Documentación oficial de `cargo-binstall` (README/SUPPORT) y de cargo-dist (config reference, installers)
* **Informed:** Usuarios finales (investigadores), CI de release, docs/APPFLOW.md §journey (d)
* **Traceability:** [ADR-003](adr-003-distribucion-cargo-dist.md) (reemplazado en su **canal**, no en sus fundamentos), [spec-installer-wizard](../spec-installer-wizard.md), [docs/PRD.md](../../docs/PRD.md) F6, [docs/APPFLOW.md](../../docs/APPFLOW.md) §5, `crates/tepochcalli/dist.toml`

> **Nota de alcance:** esta decisión la tomó el dueño del repo. **Reemplaza el canal de
> ADR-003, no sus fundamentos**: cargo-dist sigue siendo el backend de release (matriz de
> targets, artefactos, check-sums, `install.sh`/`install.ps1`) y ADR-004 (uv/venv) no cambia.
> ADR-003 no se re-edita (es Accepted).

## 1. Context and Problem Statement

El canal que ADR-003 dejó como principal es un script (`curl -L …/install.sh | sh`) servido
desde GitHub Releases. El dueño del repo considera ese camino un obstáculo real de adopción:
el usuario objetivo (investigador sin perfil DevOps) **no debe tener que decidir qué
ejecutar ni ver un `.sh`** antes de haber instalado nada. Al mismo tiempo, el dueño acepta
explícitamente el coste de una dependencia adicional en el host —una toolchain de Rust— si
con ella el camino de instalación se vuelve auditable y repetible.

¿Cuál es el canal recomendado de instalación del wizard `tepochcalli` en v1?

## 2. Decision Drivers

* **Confianza del usuario**: nada de «pipear un script a un shell» como primer paso.
* **Descubribilidad y verificabilidad**: un registro con nombre `tepochcalli`, checksum del
  crate y un índice auditado (crates.io) en lugar de una URL de release recordada de memoria.
* **Sin compilación en el caso común**: `cargo binstall` descarga el binario precompilado de
  la release en vez de compilar — el coste de Rust se paga una vez (toolchain) y no por
  instalación.
* **Coste de dependencia aceptado**: el dueño asume que el usuario tenga `cargo` (y
  `cargo-binstall`) como requisito previo.
* **Compatibilidad con lo ya construido**: `dist.toml` (targets, check-sums,
  `installers = ["shell", "powershell"]`) y la regla one-version payload↔binario se conservan.

## 3. Considered Options

* **`cargo binstall tepochcalli` (crates.io + GitHub Releases)** — binstall lee el manifiesto
  del crate en crates.io, resuelve el asset de la release y lo instala sin compilar (con
  `cargo install` como último recurso).
* **`shell`/`powershell` de cargo-dist (`curl | sh`, `irm | iex`)** — el camino de ADR-003;
  cero toolchain, pero ejecuta un script descargado.
* **npm (installer de cargo-dist)** — paquete npm con binarios precompilados; exige Node/npm
  en el host y un token de publicación npm.
* **Homebrew (installer de cargo-dist)** — fórmula en un tap propio; exige macOS/Linux con
  Homebrew y un repositorio tap con token.
* **msi (installer de cargo-dist)** — instalador Windows firmable; exige Windows, firma y
  plantilla WiX.
* **uv/PyPI (`uv tool install tepochcalli`)** — reutilizar el gestor que el wizard ya usa;
  descartado: el wizard es Rust, no hay paquete Python que publicar, y añade otra toolchain.

## 4. Decision Outcome

**Chosen option: `cargo binstall tepochcalli` como canal recomendado**, con `shell` y
`powershell` conservados como **fallback sin toolchain**. El razonamiento del dueño: si el
único requisito extra es instalar `cargo`, el intercambio (toolchain por confianza y
verificabilidad) es aceptable; binstall no ejecuta código arbitrario del instalador y
verifica checksums — ventaja que el propio README de la herramienta contrasta con un
`curl … | sh`.

Corrección de una premisa frecuente: **`bunx` sí acepta flags y `cargo binstall` no**. Binstall
no reenvía argumentos al binario (instala y termina); el wizard se ejecuta como comando aparte.

### 4.1 Confirmation

* `cargo publish --dry-run` del crate pasa con `description`/`license`/`repository`/`readme`
  presentes (los añade otro calpulli en `crates/tepochcalli/Cargo.toml`).
* Tras una release real, `cargo binstall tepochcalli` instala el binario en una máquina sin
  toolchain de build y `tepochcalli install --vault <ruta>` completa las 8 fases.
* **Estado de la evidencia: `declarado`.** `cargo binstall` **nunca se ha ejecutado contra un
  release de este repo** y `release.yml` nunca ha corrido (**M6** sigue abierto en
  [docs/TECH_DEBT.md](../../docs/TECH_DEBT.md)). Nada de lo anterior es una medición.

## 5. Pros and Cons of the Options

### `cargo binstall tepochcalli` (elegido)

* ✅ **Pros:** sin scripts en el camino principal; checksum del crate y del asset; nombre
  reservado y descubrible en crates.io; sin compilar en el caso común; el mismo binario que
  entregan `install.sh`/`install.ps1`.
* ⚠️ **Cons:** exige `cargo` en el host; dos pasos (instalar + `tepochcalli install`); si no
  hay asset para el target (musl, ARMv7) cae a `cargo install` y compila, lo que exige linker;
  el namespace de tags obliga a metadatos `pkg-url`; crates.io no permite borrar versiones.
* ⚖️ **Neutral:** el orden de release se vuelve contractual (tag → assets → publish).

### `shell`/`powershell` (fallback conservado)

* ✅ **Pros:** cero toolchain; un solo paso; es el camino que ya declara `dist.toml`; sirve en
  hosts corporativos sin Rust.
* ⚠️ **Cons:** ejecuta un script remoto; el usuario debe inspeccionarlo; es exactamente lo que
  el dueño quiere dejar de recomendar.
* ⚖️ **Neutral:** sigue en la release y en `dist.toml`; no se retira.

### npm

* ✅ **Pros:** `npx tepochcalli` familiar para el perfil JS; cargo-dist ya lo soporta
  (`npm-scope`).
* ⚠️ **Cons:** añade Node/npm al host del investigador (lo que ADR-003 ya rechazaba) más un
  token npm; fuera de v1.

### Homebrew

* ✅ **Pros:** UX excelente en macOS; cargo-dist lo soporta (`tap`, `formula`).
* ⚠️ **Cons:** requiere un tap propio y su token; no cubre Linux sin Homebrew; fuera de v1.

### msi

* ✅ **Pros:** instalador nativo de Windows, instalable por GPO.
* ⚠️ **Cons:** exige firma y plantilla WiX, y Windows es hoy `declarado` con verificación
  pendiente (M6); fuera de v1.

### uv/PyPI

* ✅ **Pros:** el host que ya completa el wizard tiene `uv` en `.tepochcalli/bin/`.
* ⚠️ **Cons:** no existe paquete Python que publicar (el wizard es Rust); produce un canal más
  que mantener para cero ganancia. Descartado.

## 6. Consequences

Lo que cambia, sin maquillar:

* **(a) Son dos pasos, no uno.** `cargo binstall tepochcalli` **instala** y termina;
  `tepochcalli install --vault <ruta>` **configura** el vault. Binstall no reenvía flags al
  binario, así que `--vault`, `--offline` y `--skip-model` van en el segundo comando. Quien
  venga de `bunx` (que sí acepta flags) se equivoca si asume un one-liner con argumentos.
* **(b) Requisito nuevo en el host:** `cargo` + `cargo-binstall`. Binstall se instala sin
  `curl` con `cargo install cargo-binstall --locked` (documentado en su README). Si binstall
  cae al fallback `cargo install`, además hace falta linker/compilador C en el host.
* **(c) Cobertura por targets:** los 5 de `crates/tepochcalli/dist.toml`
  (`x86_64`/`aarch64` Linux GNU, `x86_64`/`aarch64` macOS, `x86_64` Windows MSVC). Un target
  fuera de esa lista (musl, ARMv7 Linux, Windows ARM64) **no tiene asset** y binstall compila.
* **(d) Namespace de tags:** los releases se etiquetan `tepochcalli-v<version>`; binstall
  busca por defecto `{ version }` o `v{ version }`, así que el crate necesita
  `[package.metadata.binstall]` con `pkg-url` explícito. Sin ese bloque, binstall no encuentra
  ningún asset y compila siempre (degradación silenciosa, no error).
* **(e) Orden de release obligatorio:** tag → release con assets → `cargo publish`. Si se
  publica primero, binstall resuelve el crate y no encuentra el asset de esa versión: compila
  (o falla) justo en la ventana en que el usuario más lo nota.
* **(f) `tepochcalli uninstall --vault <ruta>` no borra el binario.** Solo elimina
  `.tepochcalli/` del vault; el ejecutable queda en `~/.cargo/bin/` y se retira con
  `cargo uninstall tepochcalli`. Hay que decirlo en la salida del comando y en la doc.
* **(g) crates.io es permanente:** una versión publicada no se borra ni se sobrescribe; solo se
  puede `cargo yank`. Un error de empaquetado se corrige con una versión nueva.
* **(h) Segundo camino sin binstall:** al estar publicado el crate,
  `cargo install --locked tepochcalli` funciona en cualquier host con toolchain, aunque
  `cargo-binstall` no exista.

## 7. Related Decisions

* [ADR-003](adr-003-distribucion-cargo-dist.md) — se mantiene: cargo-dist sigue generando los
  artefactos y los installers `shell`/`powershell`. Esta ADR cambia **qué canal se recomienda**.
* [ADR-004](adr-004-uv-venv-aislado.md) — el wizard sigue booteando `uv`; instalar el wizard
  con cargo no cambia nada del runtime del vault.
* [spec-installer-wizard](../spec-installer-wizard.md) §Enmienda 2026-11-13 — fases, flags y
  orden de los dos pasos.

## 8. Compliance and Review

* **Success metrics:** `cargo binstall tepochcalli` instala y el wizard completa las 8 fases en
  las plataformas con asset, medido en una release real (hoy `declarado`).
* **Next review date:** 2027-05-13
* **Revisit triggers:** el crate se queda sin publicar o despublicado (yank) → revisar el canal
  recomendado; aparición de usuarios sin toolchain que abandonen la instalación → reevaluar
  `shell` como principal; activación de npm/homebrew/msi (solo exige token, no ADR nuevo).

## References

* cargo-dist — config reference: <https://axodotdev.github.io/cargo-dist/book/reference/config.html>
* cargo-dist — installers (shell/powershell/npm/homebrew/msi):
  <https://axodotdev.github.io/cargo-dist/book/installers/index.html> ·
  <https://axodotdev.github.io/cargo-dist/book/installers/npm.html> ·
  <https://axodotdev.github.io/cargo-dist/book/installers/homebrew.html>
* cargo-binstall — README: <https://github.com/cargo-bins/cargo-binstall>
* cargo-binstall — SUPPORT (metadatos `pkg-url`/`bin-dir`): <https://github.com/cargo-bins/cargo-binstall/blob/main/SUPPORT.md>
* Cargo Book — Publishing on crates.io: <https://doc.rust-lang.org/cargo/reference/publishing.html>
* M6 (release nunca ejecutado): [docs/TECH_DEBT.md](../../docs/TECH_DEBT.md)

---
*Formato basado en [MADR v4.0](https://adr.github.io/madr/), igual que [adr-template.md](adr-template.md).*
