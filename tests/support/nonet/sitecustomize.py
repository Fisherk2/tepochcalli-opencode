"""Guard canario de CERO RED: bloquea toda salida AF_INET/AF_INET6 al arrancar Python.

Patrón M3(b) de Phase 1 (`test_pipeline_integration._outbound_blocked`), llevado
al HIJO: un `sitecustomize` en `PYTHONPATH` se importa en cada proceso de
Python que arranque con ese env — aquí, el server MCP `tepochcalli_mcp` que
ejecuta `index_refresh`. Cualquier intento de `connect` IPv4/IPv6 LANZA
`OSError`, así que:

* una descarga del modelo o cualquier dial HTTP rompería el refresh ⇒ el tool
  respondería `INTERNAL` canónico y el test de éxito fallaría (auto-exigente);
* una llamada LLM por API es, ella misma, una conexión saliente — el mismo
  guard cubre «cero red» y «cero LLM» (M3: el patch de socket es quien
  realmente prohíbe cualquier salida, incluida la del proveedor LLM).

`HF_HUB_OFFLINE=1` (fijado por el test) evita siquiera el intento del cliente
HF; este guard es la red de seguridad que lo DEMUESTRA en vez de creerlo.
Deliberadamente igual al de M3: solo `connect` — la resolución DNS del sistema
queda fuera, como en Phase 1.
"""

from __future__ import annotations

import socket

_real_connect = socket.socket.connect


def _guard(self: socket.socket, address: object, *args: object, **kwargs: object) -> None:
    """Lanza `OSError` en cualquier conexión saliente IPv4/IPv6 (canario M3)."""
    if self.family in (socket.AF_INET, socket.AF_INET6):
        raise OSError(f"canario nonet: salida de red prohibida hacia {address!r}")
    return _real_connect(self, address, *args, **kwargs)  # type: ignore[attr-defined]


socket.socket.connect = _guard  # type: ignore[method-assign]
