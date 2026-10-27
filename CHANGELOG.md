# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Phase 2 — servidor MCP `tepochcalli-rag`** (2026-10-27): paquete `tepochcalli_mcp`
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

### Changed

- Superficie tipada de mypy estricto: `flow/` → **`flow/` + `mcp/`**
  (`files = ["flow", "mcp"]`).
- Docs de fase cerrados con métricas **medidas**: `docs/WORKFLOW.md` (Phase 2 + §8 D15-D18),
  `docs/ARCHITECTURE.md` (inventario y diagrama de la capa MCP), `docs/TECH_DEBT.md`
  (TD-1 pagada, TD-3 pagada, TD-12 nueva y deuda de Phase 2), `docs/CODE_STYLE.md`,
  `docs/SECURITY.md` (límite `file:` + clave de API).

### Fixed

- **PDFs que nunca se indexaban en producción** (bug de Phase 1, F-T7-2): `app.index_file`
  leía el PDF como UTF-8 y absorbía el `UnicodeDecodeError` en `skipped` con `rc=0` —
  ahora delega la lectura en `extract_text` (Docling), con guardia TOCTOU preservada y
  offsets F1 byte-idénticos para md/txt.

---

## Project Information

### Repository
- **Name**: [Project Name]
- **Description**: [Project Description]
- **Repository**: https://github.com/[username]/[repository-name]
- **License**: MIT License

### Technology Stack
...

### Related Documentation
...

### Update Instructions

#### From Previous Versions
...

#### For Future Versions
...

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
