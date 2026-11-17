"""Tepochcalli RAG flow: incremental CocoIndex pipeline (Phase 1 scaffold)."""

import os

# cocoindex 1.0.25 emite el `tracing` de su núcleo Rust a STDOUT, y su telemetría
# escribe `usage tracking event ... failed` cuando el ping a
# `cocoindex.gateway.scarf.sh` no llega (timeout 5 s, fire-and-forget). Aquí
# stdout es el wire JSON-RPC (ADR-005) y el JSON de una línea que parsea el
# wizard: una sola línea de log rompe el protocolo. Se reprodujo y se caza en
# `tests/integration/test_mcp_refresh_progress.py`.
#
# Upstream lo movió a stderr en PR #2717 (2026-11-07), un mes DESPUÉS del pin
# `cocoindex==1.0.25` ⇒ este release no lo lleva. Se fija en el `__init__` del
# paquete porque es lo primero que corre en toda ruta de import
# (`tepochcalli_flow.app`, `python -m tepochcalli_mcp`, `python -m tepochcalli_flow`)
# y el subscriber se instala exactamente en `import cocoindex`.
#
# Asignación incondicional: si el operador exporta `RUST_LOG=info` vuelve a
# romper el protocolo. Retirar estas dos líneas al subir el pin de cocoindex a un
# release posterior a 2026-11-07 (incluye #2717) — cambio de dependencia pineada
# que exige visto bueno del dueño.
os.environ["RUST_LOG"] = "off"
os.environ["COCOINDEX_DISABLE_USAGE_TRACKING"] = "1"

__version__ = "0.1.0"
