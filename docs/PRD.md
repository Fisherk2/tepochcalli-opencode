# Product Requirements Document — Tepochcalli v1 (MVP)
**Date:** 2026-10-21 | **Author:** Arquitecto (entrevista /spec) | **Status:** Approved (requisitos: docs/UH.md)

## 0. General Description

Tepochcalli es un **workspace de Obsidian para investigación y estudio, potenciado con
OpenCode V2 y un motor RAG local**. Permite consultas semánticas sobre notas de investigación,
PDFs académicos y documentación técnica, minimizando el consumo de tokens del LLM mediante
indexación incremental y recuperación precisa de fragmentos. Se instala con un wizard (TUI en
Rust) que deja el vault listo-para-usar sin que el usuario instale Python, Node ni dependencias
nativas.

## 1. Usuario objetivo

* **Investigador/a o estudiante de posgrado** con vault de Obsidian propio (cientos–miles de
  notas, PDFs en español e inglés), sin perfil DevOps, que ya usa (o adoptará) OpenCode como
  harness de agente.
* Contexto de uso: laptop con 8GB RAM, CPU sin GPU dedicada, disco razonablemente libre.

## 2. Problema

* Los RAG-as-a-service y los pipelines "hazlo tú mismo" obligan a (a) instalar/cuidar toolchains,
  (b) pagar tokens en indexación/consulta, (c) exponer el material de investigación, o (d) aceptar
  respuestas sin citas verificables.
* Obsidian es una carpeta: cualquier sistema que meta demonios, puertos o archivos visibles
  interfiere con la herramienta principal del usuario.

## 3. Objetivos (éxito = criterios de §6)

1. Búsqueda semántica **con citas precisas** al archivo/encabezado/offset original.
2. Coste de tokens mínimo: indexación sin LLM; respuesta con contexto acotado (≤2000 tokens).
3. Transparencia cero: el vault sigue siendo un vault de Obsidian normal.
4. Instalación de un comando; actualización de índice en segundos cuando el agente lo pide.
5. Metodología de investigación completa (9 comandos, 5 agentes) sobre la base RAG.

## 4. Features

| # | Feature | Descripción | Spec |
|---|---|---|---|
| F1 | Vault plantillado | Carpetas numeradas `00-Resources/` (indexable, anidamiento libre), `01-tasks/`, `02-drafts/`, `03-citations/`; `.opencode/` con agentes+comandos+skills; `AGENTS.md` con regla MCP-first; muestras md+PDF | spec-vault-structure, spec-agent-workflow |
| F2 | Motor RAG incremental | CocoIndex flow: live-watch `00-Resources/**`, chunking RecursiveSplitter, embeddings locales MiniLM, LanceDB ANN+FTS; Δ-only | spec-rag-engine |
| F3 | Herramientas MCP | `tepochcalli-rag`: `search` (chunks citables), `index_refresh` (delta+reporte), `add_source` (ingesta convertida) | spec-mcp-server |
| F4 | Conversor Markdown | markitdown-mcp local: URL/DOCX/PPTX/XLSX/HTML → Markdown indexable; fallback de formato (criterio 7) | spec-markitdown |
| F5 | Wizard atomico | TUI Rust, 8 fases con rollback, bootstrap uv→venv→modelo→índice→config MCP; flags `--offline`, `--skip-model` | spec-installer-wizard |
| F6 | Distribución versionada | cargo-dist + GitHub Releases: `curl \| sh` / `cargo binstall tepochcalli`; payload y wizard versionan juntos | ADR-003 |
| F7 | Metodología de investigación | `/rubric /research /validate /synthesize /cite /draft /review /transform /update` con agentes Itzamná/Nezahualcóyotl/Pochteca/Chilam/Tlacuilo | spec-agent-workflow |

## 5. Out of scope (v1)

* **Implementar un motor RAG propio** — se incorpora CocoIndex (decisión D1/ADR-001).
* **Sincronización/cloud/multi-usuario del índice** — el índice es local al vault (ADR-002).
* **UI propia** (app, web, plugin gráfico) — la UI del usuario es Obsidian + TUI de OpenCode.
* Indexar `01/02/03` por defecto; OCR de imágenes; plugin OpenCode sustituto del AGENTS.md (futuro).
* Gestión de referencias tipo Zotero completo (eso lo aporta el flujo `/cite` + skills).

## 6. Acceptance Criteria (textuales de docs/UH.md — contrato de v1)

1. El vault de Obsidian funciona normalmente sin interferencias
2. Los archivos nuevos se indexan automáticamente en menos de 30 segundos cuando Opencode invoca la función del MCP correspondiente
3. Las búsquedas semánticas devuelven resultados relevantes en menos de 500ms
4. El consumo de tokens por consulta es inferior a 2000 tokens (incluyendo contexto)
5. Las respuestas del agente incluyen citas precisas a las fuentes originales
6. El sistema puede manejar vaults de hasta 10,000 notas y 1,000 PDFs sin degradación de rendimiento
7. Pueda procesar distintos formatos de texto, si no, utilizar el convertidor Markdown para que pueda manipularse adecuadamente.

Verificación: metodología y fixtures en [docs/TRD.md](TRD.md); gate final en
[docs/WORKFLOW.md](WORKFLOW.md) Phase 5; enlaces de cobertura en [SPEC.md](../SPEC.md).

## 7. Métricas de producto

* Tiempo primera-instalación→primera-respuesta-citada < 15 min en HW mínimo.
* % de respuestas sin cita estructural ≈ 0 (garantizado por contrato, no por prompt).
* Re-index delta p95 < 30s; latencia `search` p95 < 500ms; tokens/consulta p95 < 2000.

## 8. Riesgos principales (con dueños)

| Riesgo | Mitigación | Dónde |
|---|---|---|
| CocoIndex API inestable (early-stage) | pin de versión en pyproject; escape hatch documentado | ADR-001/004, spec-rag-engine |
| Docling lento en PDFs enormes | exclusión del criterio de 30s para casos extremos; progreso visible; TD-2 | TECH_DEBT |
| Payload de skills inflado (208) | auditoría Anexo A → aseo Phase 4 | spec-agent-workflow |
| Usuario espera funcionamiento offline total | comunicación clara: primer arranque requiere internet; `--offline` solo con caché | TRD, wizard UX |
