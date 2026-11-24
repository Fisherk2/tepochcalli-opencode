"""Tepochcalli MCP server: `tepochcalli-rag`, la capa de comunicación (Phase 2).

Proceso stdio local que expone las 4 tools con contrato congelado
(specs/spec-mcp-server.md): `search`, `index_refresh`, `add_source` y
`rag_status` (ADR-005: la frontera ports/adapters entre harness y motor).
"""

__version__ = "0.1.0-beta.1"
