# Code Style — Tepochcalli

> Convenciones del repositorio. Lo automatizado (linter/formatter) se aplica con herramientas;
> el resto se hace en revisión. Documentación en **español**; código y términos técnicos en inglés.

## Herramientas y comandos

| Área | Toolchain | Comandos (recetas del Justfile raíz) |
| --- | --- | --- |
| Python (`.tepochcalli/flow/`, `.tepochcalli/mcp/`) | ruff (lint+format) + mypy `--strict` + pytest | `just python-lint-fix` · `just python-fmt` · `just python-typecheck` · `just python-test-unit` · `just test-mcp-tools`/`test-mcp-wire`/`test-engine`/`test-converter` |
| Rust (wizard `crates/tepochcalli`) | rustfmt, clippy | `just rust-fmt` · `just rust-lint` · `just rust-test` · `just rust-ci` |
| Docs | markdownlint (reglas desactivadas: líneas largas en MD) | `just md-lint` |
| Commits | Conventional Commits manuales (hook a decisión en Phase 1) | ver §Commits |

`just quality` y `just ci` cubren los dos lenguajes; las recetas `just python-*` / `just rust-*`
tocan uno solo.

Python se ejecuta SIEMPRE vía recetas de `just`: el Justfile exporta `UV_PROJECT_ENVIRONMENT=venv`
(quirk uv 0.12.9: sin esa var, uv crea un `.venv` paralelo con deriva impredecible). Un `uv` crudo
a mano fuera de la receta es la fuente de entornos dobles. El
gate de tipos es **real y estricto**: `just typecheck` corre `mypy` con `strict = true` fijado en
`[tool.mypy]` de su
`pyproject.toml` — sin `[[tool.mypy.overrides]]` para el código propio ni flags de relajación, y en
CI entre `ruff format --check` y `pytest` (`.github/workflows/phase1.yml`). Superficie tipada:
**`flow/` + `mcp/`** (`files = ["flow", "mcp"]` — ampliada en Phase 2 T1 con la creación del
paquete `tepochcalli_mcp`), y los tests viven fuera de este proyecto uv (no se tipan). Los bordes de terceros sin
anotaciones útiles se acotan con `cast` o `# type: ignore[código]` puntual y comentado — nunca con
un override de módulo completo.

## Convenciones Python (flow + MCP)

* **Type hints estrictos en firmas públicas** de herramientas y transformaciones del flow;
  `from __future__ import annotations`; sin `Any` en el borde de contrato — se validan args
  explícitamente en las handlers de tool (spec-mcp-server).
* Módulos pequeños: `flow/` = definición declarativa de transformaciones (funciones puras por
  etapa, memoizadas con `@coco.fn(memo=True)`); `mcp/` = handlers + schemas + config loader;
  sin lógica de negocio en `__main__`.
* Errores: excepciones tipadas internas → mapeo único a códigos públicos
  (`VALIDATION_ERROR` etc., spec-mcp-server §errores); nunca texto libre como error de tool.
* Nombres: `snake_case` funciones/variables, `PascalCase` clases, constantes `UPPER_SNAKE`;
  paquetes: `tepochcalli_flow`, `tepochcalli_mcp`.
* Docstrings breves en español con ejemplo cuando la función afecta un criterio de aceptación
  (latencia, tokens, citas).

```python
def _truncate_for_budget(results: list[Chunk], max_tokens: int = 1600) -> list[Chunk]:
    """Recorta resultados por score hasta el presupuesto de tokens del contrato.

    Garantiza criterio 4 (≤2000 tokens/consulta incluyendo contexto). El estimador
    es chars/4 (aprox ES/EN); el margen hasta 2000 cubre pregunta + citas del agente.
    """
    out: list[Chunk] = []
    used = 0
    for chunk in sorted(results, key=lambda c: c.score, reverse=True):
        cost = len(chunk.text) // 4 + CITATION_OVERHEAD_TOKENS
        if used + cost > max_tokens:
            break
        out.append(chunk)
        used += cost
    return out
```

## Convenciones Rust (wizard)

* `rustfmt` default; `cargo clippy -D warnings` en CI de PR.
* Fases del instalador: un módulo por fase con `execute()` y `compensate()` explícitos
  (rollback por compensación — spec-installer-wizard); estado como enum de fases, no booleans sueltos.
* Códigos de salida del §UX de fallo como constantes nombradas (`EXIT_NETWORK_*`).
* `thiserror` para errores del wizard; nada de `unwrap()` en rutas de usuario.

### Tests: el nivel va en la ubicación y en el nombre

`crates/tepochcalli/tests/` no se divide en `unit/ integration/ e2e/`: Cargo solo compila
`tests/*.rs` y `tests/<dir>/main.rs`, y un subdirectorio sin `main.rs` se ignora **en silencio**.

* **Tier 1** — `src/<módulo>.rs` con `#[cfg(test)] mod tests`: lógica pura o privada
  (parsers, escaping, estimadores, mapeos de error).
* **`int_<tema>.rs`** — sin proceso hijo: puertos falsos, `tempfile`, API pública
  (`int_swap.rs`, `int_ports.rs`, `int_domain.rs`).
* **`e2e_<tema>.rs`** — lanza el binario (`bin()`, `env!("CARGO_BIN_EXE_…")`) o un script
  (`e2e_installers.rs`, `e2e_cli_help.rs`).
* **`tests/common/`** — soporte compartido, no es un target.

La convención la hace cumplir `int_architecture.rs` (`tests_layout_uses_tier_prefix`,
`e2e_tests_spawn_a_process`, `int_tests_do_not_spawn_a_process`): un fichero mal clasificado
pone el gate rojo, no la memoria del revisor. Al añadir un test: ¿necesita el binario? `e2e_`;
¿necesita FS o fakes? `int_`; ¿es lógica pura? `#[cfg(test)]` en `src/`. Los instaladores se
prueban por su costura `TEPOCHCALLI_RELEASE_BASE_URL` (mirror en loopback); PowerShell solo se
fija de forma estática porque no corre en la CI Linux.

## Umbral de líneas por fichero (código)

Aplica a los ficheros de código del proyecto (`.py` bajo `flow/`/`mcp/`, `.rs` bajo
`crates/`); los artefactos gitignored (`venv/`, `db/`, `models/`, `target/`) y la
**documentación** (umbral propio en la sección siguiente) no cuentan. Objetivo: ficheros
legibles, modulares y editables. Recuento = líneas totales del fichero (`wc -l`);
**todo refactor exigido por la tabla baja el fichero a <500**.

| Líneas | Regla |
| --- | --- |
| ≤ 500 | Conforme. |
| 501 – 700 | Si **no** es justificable o necesario: refactorizar, simplificar y/o generar ficheros nuevos hasta <500. Si **es** justificable o necesario: se permite esa cifra. |
| 701 – 1000 | Mismo criterio que el tramo anterior, pero la justificación solo se acepta **con advertencia** de refactorizar el código lo antes posible. |
| > 1000 | **Obligatorio** refactorizar, simplificar y/o generar ficheros nuevos para reducir a **<500** — sin excepción por justificación. |

* La justificación de una cifra admitida (501–1000) consta en el commit/PR que crea o alarga
  el fichero; si el porqué no se ve en el código, se deja comentario en el fichero.
* Es regla de revisión, todavía **sin gate automático**: quien alargue un fichero por encima
  de un umbral lo declara en la revisión.

## Umbral de líneas por documentación (.md)

Aplica a los `.md` del proyecto — raíz, `docs/`, `specs/`, `tasks/` — **sin
`obsidian-workspace/`** (payload congelado hasta Phase 5); tampoco cuentan los assets
gitignored (`skills/`, `agents/`, `commands/` de la raíz) ni los `.md` que son datos de
test (`tests/fixtures/`). Recuento = líneas totales (`wc -l`). Objetivo: documentación
legible y mantenible.

| Documento | Umbral |
| --- | --- |
| `CHANGELOG.md` · `README.md` (raíz) · `docs/BACKLOG.md` | **Sin límite** (historial y fuente de verdad; todo cambio se registra en §8 del BACKLOG y, si es decisión, exige ADR/enmienda; objetivo <500, ver §7 Split policy). |
| `tasks/**` · `docs/diagnosis/**` | **< 1000** líneas. |
| `docs/WORKFLOW.md` · `docs/TECH_DEBT.md` | **< 700** líneas. |
| El resto de documentación | **< 500** líneas. |

Al superar el umbral, las acciones dependen del tramo — el objetivo es bajar **por debajo del
umbral de su propio tramo**, no a <500:

* **Tramo `<500`:** refactorizar, simplificar, contraer y/o **generar documentos nuevos**
  (dividir; actualizar el índice y los enlaces que referencien el documento dividido).
* **Tramos `<700` y `<1000`:** solo refactorizar, simplificar, contraer, resumir contenido o
  eliminar contenido desactualado e irrelevante — **sin dividir en documentos nuevos** (son
  largos por naturaleza: plan, registro de deuda, tareas, diagnóstico).
* El umbral lo fija la **ruta**, no el nombre: `docs/diagnosis/README.md` es tramo `<1000`,
  no el README exento de la raíz.

## Nomenclatura de archivos y docs

| Constructo | Convención | Ejemplo |
| --- | --- | --- |
| Specs | `specs/spec-<kebab>.md` | `spec-rag-engine.md` |
| ADRs | `docs/adr/adr-NNN-<kebab>.md` (3 dígitos, secuencial inmutable) | `adr-001-motor-rag-cocoindex.md` |
| Docs núcleo | `docs/<MAYUSCULAS>.md` fijos del proyecto | `APPFLOW.md`, `TECH_DEBT.md` |
| Términos canónicos | exactos, en todo documento (ver checklist AGENTS.md) | `tepochcalli-rag` · `.tepochcalli/` · `00-resources/` · `paraphrase-multilingual-MiniLM-L12-v2` · `cocoindex` · `markitdown` |
| Branches | `feature/…` `fix/…` `chore/…` (git-workflow skill) | `feature/wizard-phase5` |

* Archivos de código fuente Python/Rust: inglés (los artefactos viajan con el payload).
* Prosa de documentación y mensajes de commit: español; identifiers y nombres de tools: los del contrato (inglés).

## Markdown y diagramas

* Mermaid: sintaxis valida en cada bloque (no se puede ejecutar "por ojo" — revisar balance de
  corchetes/comillas); labels con caracteres especiales se entrecomillan: `A["texto (con) paréntesis"]`.
* Tablas para comparaciones; código con ejemplo > párrafo descriptivo.
* Enlaces relativos entre specs/docs siempre funcionales (verificar tras renombrar).

## Commits (Conventional Commits)

* Formato: `type: resumen` (≤72 columnas; español permitido en subject) + cuerpo opcional
  explicando el **por qué** + trailer obligatorio `Co-Authored-By: …`.
* Tipos: `docs` `feat` `fix` `refactor` `test` `chore`. Un commit = una decisión lógica
  (atomacidad; ej.: los ADRs entran separados de las specs y de los docs).
* Nada de commits "megapatch": grupos lógicos alineados con las fases de docs/WORKFLOW.md.

## Reglas específicas del payload

* `obsidian-workspace/opencode.json`: el wizard solo puede tocar `mcp.servers.*` de las
  entradas gestionadas; el resto del JSON se preserva byte-a-byte (merge conservador).
  **Excepción aprobada por el dueño (2026-11-18):** en el flujo destino, **Update (H7)**
  sobrescribe `.opencode/`, `.tepochcalli/`, `.gitignore`, `opencode.json` y `AGENTS.md`;
  **Desinstall (H8)** remueve `.opencode/`, `.tepochcalli/` y `opencode.json` — **no**
  `AGENTS.md` (BACKLOG.md §2 / US-H8) —; en ambos, **backup obligatorio del fichero existente antes de
  pisarlo/quitarlo y advertencia
  visible**; la primera Install y las re-entradas `config` siguen con merge conservador
  byte-a-byte salvo los `mcp.servers.*` gestionados. Referencias:
  specs/spec-installer-wizard.md §Enmienda 2026-11-18 — flujo destino (Accepted 2026-11-19) y ADR-014
  (Accepted 2026-11-19).
* Nunca commitear artefactos: `.tepochcalli/{venv,db,models,bin,config}` (gitignore del vault,
  spec-vault-structure).
* `docs/BACKLOG.md` es la fuente de verdad: todo cambio se registra en su §8 y, si es decisión, exige ADR/enmienda; el detalle nuevo vive en `docs/PRD.md`/specs.
