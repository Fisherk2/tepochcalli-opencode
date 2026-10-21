# ADR-003: Distribuir el wizard de instalación con cargo-dist + GitHub Releases

* **Status:** Accepted
* **Date:** 2026-10-21
* **Decision Makers:** Arquitecto (entrevista /spec), Product Owner (usuario)
* **Consulted:** Referencia de arquitectura de instalación del proyecto hermano Fisherk2/codice-opencode
* **Informed:** Usuarios finales (investigadores sin toolchain garantizada), CI
* **Traceability:** docs/UH.md (sección "Wizard de instalación"), specs/spec-installer-wizard.md, ADR-004

## 1. Context and Problem Statement

El instalador de Tepochcalli es un TUI nativo en Rust que debe ejecutarse en máquinas Linux/macOS/Windows donde el usuario **no necesariamente tiene Python, Node o bun**. Necesitamos un canal de distribución que entregue un binario único, versionado, actualizable y instalable con un solo comando, replicando la filosofía de payload "template/ → vault del usuario" ya validada en codice-opencode (que hoy se distribuye vía bunx).

## 2. Decision Drivers

* Un solo comando de instalación sin runtime previo en el host (`curl … | sh` o `cargo binstall`).
* Binarios multi-plataforma generados en CI ante un tag `v*` (x86_64/aarch64, Linux/macOS/Windows).
* Versionado semver explícito del instalador y del payload del vault.
* Cero dependencia de registrarse en un registro de paquetes para publicar (coste operativo bajo).
* coherencia con codice-opencode: el contenido de `obsidian-workspace/` actúa como payload instalable.

## 3. Considered Options

* **cargo-dist + GitHub Releases** — herramienta de release para crates de Rust: dado un tag `v*`, la CI compila multi-plataforma, arma artefactos `.tar.gz`/`.zip` + `install.sh`/`install.ps1` y publica una GitHub Release con check-sums.
* **bunx / npx (npm registry)** — el modelo actual de codice-opencode; exige bun/Node en el host y publicar en un registry (npmjs).
* **crates.io + `cargo install`** — distribución oficial de Rust, pero obliga al usuario a tener toolchain Rust y compilar (minutos, sin pre-link).
* **Descargas manuales de artefactos de CI** — sin semver empaquetado ni instalador unificado; fácil de romper.

## 4. Decision Outcome

**Chosen option: cargo-dist + GitHub Releases**, porque cumple el driver principal — instalación con `curl -L <install.sh> | sh` o `cargo binstall tepochcalli` **sin toolchain ni runtime previo** — usando únicamente el repositorio GitHub existente como registro. Publicar en crates.io queda como paso opcional posterior, no bloqueante. Se descarta bunx explícitamente: introducir Node/bun en hosts de investigadores contradice el objetivo de "el usuario no instala dependencias nativas" (UH.md, deuda cognitiva 3-4).

### 4.1 Confirmation

* Un tag `v*` dispara la matriz CI y produce releases con `install.sh` + binarios por plataforma + SHA-256.
* Prueba de aceptación en VM limpia (sin Python/Node/Rust): `curl | sh` instala el wizard y este completa el flujo de Phase 3 de docs/WORKFLOW.md.

## 5. Pros and Cons of the Options

### cargo-dist + GitHub Releases (elegido)

* ✅ **Pros:** Binarios precompilados multi-OS/arch; `install.sh`/`ps1` y soporte de `cargo binstall` generados; semver y changelog de release automáticos; sin registro externo obligatorio; check-sums incluidos.
* ⚠️ **Cons:** La CI de release es más compleja que `npm publish`; artefactos dispersos en Releases (mitigado por install.sh); requiere mantenimiento de la matriz de targets.
* ⚖️ **Neutral:** El proyecto gana un workspace de Rust (crates `tepochcalli` wizard + `template/` payload).

### bunx / npx

* ✅ **Pros:** Probado en codice-opencode; cero compilación cross.
* ⚠️ **Cons:** Runtime Node/bun obligatorio en el host; registro npmjs; mezcla lenguajes (TS) con un wizard pedido en Rust.
* ⚖️ **Neutral:** —

### crates.io + cargo install

* ✅ **Pros:** Canonal de Rust; `cargo binstall` puede resolverlo después.
* ⚠️ **Cons:** El usuario necesita Rust y espera compilación; no sirve al perfil "investigador".
* ⚖️ **Neutral:** Opcional para Phase posterior (no bloqueante).

### Artefactos crudos de CI

* ✅ **Pros:** Control total.
* ⚠️ **Cons:** Sin instalador unificado ni versionado de payload; UX de actualización manual.
* ⚖️ **Neutral:** —

## 6. Consequences

* ✅ **Positives:** Experiencia "one-liner" reproducible; el wizard y el payload versionan juntos (el wizard instala la release que lo contiene, modelo espejo de codice-opencode).
* ⚠️ **Negatives / Risks:** Seguir el esquema de tags `v*` es contractual: romperlo = no hay release. Las descargas de payload/modelo en primer arranque requieren internet (documentado como restricción, flags `--offline`/`--skip-model` mitigan re-instalaciones).
* ⚖️ **Neutral:** Publicación en crates.io queda como mejora opcional futura.

## 7. Related Decisions

* ADR-004 — el wizard bootea `uv` en `.tepochcalli/bin/`; ninguna de las dos cosas exige Python en el host.
* specs/spec-installer-wizard.md — fases, atomicidad y rollback del binario distribuido aquí.

## 8. Compliance and Review

* **Success metrics:** ≥95% de instalaciones desde cero exitosas en las 3 plataformas soportadas; tiempo de release CI <30 min.
* **Next review date:** 2027-04-21
* **Revisit triggers:** Requirement de instalación air-gapped corporativa → evaluar bundle offline; adopción masiva que justifique crates.io/homebrew.

---
