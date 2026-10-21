# Code Style — Tepochcalli

> Convenciones del repositorio. Lo automatizado (linter/formatter) se aplica con herramientas;
> el resto se hace en revisión. Documentación en **español**; código y términos técnicos en inglés.

## Herramientas y comandos

| Área | Toolchain | Comandos |
|---|---|---|
| Python (`.tepochcalli/flow/`, `.tepochcalli/mcp/`) | ruff (lint+format), mypy vía ruff, pytest | `uv run ruff check --fix .` · `uv run ruff format .` · `uv run pytest` |
| Rust (wizard `crates/tepochcalli`) | rustfmt, clippy | `cargo fmt --all` · `cargo clippy --all-targets -- -D warnings` · `cargo test` |
| Docs | markdownlint (reglas desactivadas: líneas largas en MD) | `markdownlint docs specs AGENTS.md SPEC.md` |
| Commits | Conventional Commits manuales (hook a decisión en Phase 1) | ver §Commits |

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

## Nomenclatura de archivos y docs

| Constructo | Convención | Ejemplo |
|---|---|---|
| Specs | `specs/spec-<kebab>.md` | `spec-rag-engine.md` |
| ADRs | `specs/adr/adr-NNN-<kebab>.md` (3 dígitos, secuencial inmutable) | `adr-001-motor-rag-cocoindex.md` |
| Docs núcleo | `docs/<MAYUSCULAS>.md` fijos del proyecto | `APPFLOW.md`, `TECH_DEBT.md` |
| Términos canónicos | exactos, en todo documento (ver checklist AGENTS.md) | `tepochcalli-rag` · `.tepochcalli/` · `00-Resources/` · `paraphrase-multilingual-MiniLM-L12-v2` · `cocoindex` · `markitdown-mcp` |
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
* Nunca commitear artefactos: `.tepochcalli/{venv,db,models,bin,config}` (gitignore del vault,
  spec-vault-structure).
* `docs/UH.md` es inmutable: cambio de requisitos ⇒ nueva sección en `docs/PRD.md`/specs, no edición.
