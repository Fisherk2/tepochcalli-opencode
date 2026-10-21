# ADR-004: Aislar dependencias de Python con uv y un venv local del proyecto

* **Status:** Accepted
* **Date:** 2026-10-21
* **Decision Makers:** Arquitecto (entrevista /spec), Product Owner (usuario)
* **Consulted:** Capacidades de uv (bootstrap de CPython gestionado, `uv venv`, `uv sync`)
* **Informed:** Autor del wizard (ADR-003), mantenedores del flow/MCP
* **Traceability:** docs/UH.md (deuda cognitiva 3-4), specs/spec-vault-structure.md (layout `.tepochcalli/`), specs/spec-installer-wizard.md

## 1. Context and Problem Statement

El stack de procesamiento (CocoIndex + sentence-transformers + Docling + markitdown-mcp + LanceDB) es Python, con dependencias pesadas y nativas (pyarrow, torch). El usuario objetivo es investigador, no desarrollador Python: no debe instalar Python en su host, no debe gestionar entornos, y el vault debe seguir siendo portable. La pregunta de UH.md: ¿puede el wizard instalar todo automáticamente en un entorno seguro, tipo `.venv`, sin comandos extra?

## 2. Decision Drivers

* Cero instalación de Python por el usuario en el host.
* Aislamiento total: las dependencias viven dentro del vault (`/.tepochcalli/venv/`), no en site-packages globales.
* Reproducibilidad: versiones pineadas (`pyproject.toml` + lockfile) compartidas entre flow y MCP.
* Velocidad de instalación (peso de torch/pyarrow) y bajo overhead de disco relativo.
* Manejable por el wizard binario (ADR-003) sin invocar instaladores arbitrarios del host.

## 3. Considered Options

* **uv con venv del proyecto** — uv gestiona su propio CPython (descarga una interpretación gestionada si el host no tiene ninguna); `uv venv .tepochcalli/venv` + `uv sync` resuelven e instalan deps pineadas; un solo binario estático booteable en `.tepochcalli/bin/`.
* **pip + `python -m venv` estándar** — requiere Python preexistente en el host; resolución/instalación lenta para wheels pesados.
* **Poetry/PDM** — gestión de proyectos Python, pero asumen un intérprete base y añaden su propia capa de instalación.
* **Conda/miniforge** — resuelve binarios pesados, pero instalar un gestor de entornos grande en el host contradice "el usuario no instala nada".
* **Python embebido dentro del binario Rust (PyO3)** — elimina Python visible, pero acopila toda la cadena nativa al wizard y complica el uso de libs con ABI inestable.

## 4. Decision Outcome

**Chosen option: uv + venv local del proyecto.** El wizard bootea el binario `uv` en `.tepochcalli/bin/`; uv instala su propio CPython gestionado (el usuario no necesita Python); `uv venv` + `uv sync` materializan `.tepochcalli/venv/` con las dependencias pineadas de `.tepochcalli/pyproject.toml` (`cocoindex[lancedb]`, `sentence-transformers`, `docling`, `markitdown-mcp`). Se obtiene exactamente la semántica de ".venv seguro" que pidió UH.md, con cero fricción para el usuario.

### 4.1 Confirmation

* VM limpia sin Python: tras el wizard, `test -x .tepochcalli/venv/bin/python` y `.tepochcalli/venv/bin/python -c "import cocoindex"` tienen éxito.
* Ejecutar el wizard dos veces no duplica ni corrompe el entorno (test de idempotencia, SPEC.md §Testing).

## 5. Pros and Cons of the Options

### uv (elegido)

* ✅ **Pros:** Auto-instala CPython gestionado; resolver/instalador más rápido del ecosistema; lockfile reproducible; binario único fácil de bootstrap desde Rust; venv estándar del proyecto.
* ⚠️ **Cons:** Primer arranque requiere internet (wheels + interpretación); ~1-2GB extra de disco (presupuestado en TRD).
* ⚖️ **Neutral:** El vault pasa a contener un entorno ejecutable; gitignore de `.tepochcalli/venv/` obligatorio.
### pip + venv

* ✅ **Pros:** Universal, cero software nuevo.
* ⚠️ **Cons:** Exige Python ≥3.10 en host; lentitud dolorosa con torch; sin lockfile moderno por default.
* ⚖️ **Neutral:** —

### Poetry / PDM

* ✅ **Pros:** Excelentes para desarrollo.
* ⚠️ **Cons:** No resuelven la ausencia de intérprete base; más capa de instalación para el wizard.
* ⚖️ **Neutral:** —

### Conda / miniforge

* ✅ **Pros:** Binarios científicos robustos.
* ⚠️ **Cons:** El "instalador" pasa a ser 500MB+ de gestor en el host; UX pésima para el objetivo.
* ⚖️ **Neutral:** —

### Python embebido (PyO3)

* ✅ **Pros:** Distribución monocromática.
* ⚠️ **Cons:** Acopla ABI nativa de todo el stack RAG al wizard; reconstrucciones cross-platform prohibitivas.
* ⚖️ **Neutral:** —

## 6. Consequences

* ✅ **Positives:** El usuario ejecuta un comando y obtiene un entorno completo; flow y MCP comparten el mismo venv pineado; actualizar dependencias = bump en `pyproject.toml` + `uv sync`.
* ⚠️ **Negatives / Risks:** Disco ocupado por el vault crece (venv 1-2GB); el venv no es portable entre SO → reinstalar (no copiar) el vault entre máquinas de distinto sistema.
* ⚖️ **Neutral:** Aparece un artefacto `pyproject.toml` + `uv.lock` en `.tepochcalli/` que la plantilla del wizard mantiene.

## 7. Related Decisions

* ADR-003 — el wizard binario es quien bootea `uv` hacia `.tepochcalli/bin/`.
* ADR-002 / ADR-001 — este venv fija las versiones de `cocoindex[lancedb]`.
* ADR-005 — `opencode.json` apunta `mcp.servers.tepochcalli-rag.command` al python de este venv.

## 8. Compliance and Review

* **Success metrics:** 0 errores reportados de "conflicto de paquetes Python en host"; instalación <5 min en conexión típica.
* **Next review date:** 2027-04-21
* **Revisit triggers:** uv abandona bootstrap de intérpretes; corporativos air-gapped → necesitar bundles offline de wheels (flag `--offline`).

---
