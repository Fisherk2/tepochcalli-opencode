"""Presupuesto de tokens de `search` — estimador y truncado determinista (plan §5).

Dominio puro del server: sin `mcp` ni infraestructura — solo el puerto
congelado `tepochcalli_flow.ports.CitedChunk` y los defaults del flow (nada de
literales duplicados: `TOP_K_DEFAULT` es `config.DEFAULT_TOP_K`).

Fuentes de verdad:

* tasks/plan.md §5 «Presupuesto de tokens» — `coste = len(text)//4 + 25`,
  techo **1600**, corte por score descendente, `truncated: true` al cortar,
  `top_k` ∈ [1,20] con efectivo `min(solicitado, 8)`.
* specs/spec-mcp-server.md §Presupuesto de tokens — el estimador chars/4
  aproxima ES/EN; el margen ≥400 tokens deja la pregunta y la respuesta del
  agente dentro de la cota 2000 de UH.md (criterio 4).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from tepochcalli_flow.config import DEFAULT_TOP_K
from tepochcalli_flow.ports import CitedChunk

CITATION_OVERHEAD_TOKENS: Final = 25
"""Sobrecoste de citación por resultado: path + heading + offsets compactos (§presupuesto)."""

PAYLOAD_TOKEN_CEILING: Final = 1600
"""Techo duro del payload de `search` — la cota 2000 de UH.md menos el margen del agente."""

TOP_K_MIN: Final = 1
"""Mínimo del contrato: por debajo, `VALIDATION_ERROR` (plan §5)."""

TOP_K_MAX: Final = 20
"""Máximo del contrato: por encima, `VALIDATION_ERROR` (plan §5)."""

TOP_K_CAP: Final = 8
"""Tope duro del `top_k` efectivo: `min(solicitado, 8)` (plan §5)."""

TOP_K_DEFAULT: Final = DEFAULT_TOP_K
"""Por omisión, 5 — el default canónico del flow, sin duplicar el literal."""


def estimate_tokens(text: str) -> int:
    """Coste de un resultado: chars/4 (aprox ES/EN) + sobrecoste de citación.

    Cuenta CARACTERES, no bytes: un chunk multibyte (CJK/emoji) no dispara el
    estimador (fixture adversa de T7).
    """
    return len(text) // 4 + CITATION_OVERHEAD_TOKENS


def effective_top_k(top_k: int) -> int:
    """Valida `top_k` ∈ [1,20] y devuelve el efectivo `min(solicitado, 8)`.

    Fuera de rango → `ValueError`, que el handler mapea a `VALIDATION_ERROR`.
    Ejemplo: `search(query, top_k=20)` ⇒ el lector recibe 8 (plan §5).
    """
    if not TOP_K_MIN <= top_k <= TOP_K_MAX:
        raise ValueError(f"top_k debe estar en [{TOP_K_MIN},{TOP_K_MAX}]; recibido: {top_k}")
    return min(top_k, TOP_K_CAP)


def apply_budget(chunks: Sequence[CitedChunk]) -> tuple[list[CitedChunk], bool]:
    """Recorta al techo 1600 por score descendente: `(conservados, truncated)`.

    Acumula el coste de cada resultado mientras el total ≤ `PAYLOAD_TOKEN_CEILING`;
    al cortar descarta los de MENOR score — el de mayor score NUNCA se descarta
    (los empatados conservan el orden estable) — y el caller marca
    `truncated: true`. Borde documentado: si un ÚNICO chunk excede el techo por
    sí solo se entrega igual —una cita parcial vale más que un payload vacío—
    con `truncated: false` (no se descartó ninguno: `kept == ordered`); con el
    flow de Phase 1 no ocurre (chunks ≤1536 bytes).
    """
    ordered = sorted(chunks, key=lambda chunk: chunk.score, reverse=True)
    kept: list[CitedChunk] = []
    used = 0
    for chunk in ordered:
        cost = estimate_tokens(chunk.text)
        if kept and used + cost > PAYLOAD_TOKEN_CEILING:
            break
        kept.append(chunk)
        used += cost
    return kept, len(kept) < len(ordered)
