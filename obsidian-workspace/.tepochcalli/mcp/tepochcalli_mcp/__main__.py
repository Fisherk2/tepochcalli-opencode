"""Arranque stdio del server `tepochcalli-rag` (`python -m tepochcalli_mcp`, D17).

La invocación real del harness es `python -m tepochcalli_mcp`: el bit de
ejecución se pierde en NTFS/fuseblk (lección (f) de Phase 1), así que el
console script `tepochcalli-mcp` existe pero no es la forma canónica.
"""

from __future__ import annotations

import logging
import sys

from tepochcalli_mcp.server import server


def main() -> None:
    """Sirve el server MCP por stdio; stdout queda reservado al JSON-RPC."""
    # basicConfig escribe a stderr por defecto; se declara explícito porque
    # stdout es el canal del protocolo y nunca debe recibir logs (plan §3).
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    server.run()  # transport="stdio" por omisión (mcp 2.3.0)


if __name__ == "__main__":
    main()
