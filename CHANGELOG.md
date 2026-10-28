# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
  `release.yml` + `phase3.yml` (ubuntu+macos; Windows fuera de la matriz — deuda M6/D-b),
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
