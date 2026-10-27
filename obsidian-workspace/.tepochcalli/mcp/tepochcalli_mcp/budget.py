"""Presupuesto de tokens de `search` — estimador y truncado determinista (plan §5).

Dominio puro del server: sin `mcp` ni infraestructura — solo el puerto
congelado `tepochcalli_flow.ports.CitedChunk` y los defaults del flow (nada de
literales duplicados: `TOP_K_DEFAULT` es `config.DEFAULT_TOP_K`).

Fuentes de verdad:

* tasks/plan.md §5 «Presupuesto de tokens» — base `len(text)//4`, techo
  **1600**, corte por score descendente, `truncated: true` al cortar,
  `top_k` ∈ [1,20] con efectivo `min(solicitado, 8)`.
* specs/spec-mcp-server.md §Presupuesto de tokens — el estimador aproxima
  ES/EN a razón de 4 chars/token; revisión Phase 2 (eje 9): CJK/emoji pesa 1
  token POR CARÁCTER — el margen ≥400 tokens deja la pregunta y la respuesta
  del agente dentro de la cota 2000 de UH.md (criterio 4) en los cuatro scripts.
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


def _is_cjk(char: str) -> bool:
    """¿Pesa 1 token el carácter? CJK/hanja/hangul + emoji (peso por carácter, review eje 9)."""
    codepoint = ord(char)
    return (
        0x3000 <= codepoint <= 0x9FFF  # puntuación CJK + hiragana/katakana + ideographs
        or 0xF900 <= codepoint <= 0xFAFF  # ideographs de compatibilidad
        or 0x1100 <= codepoint <= 0x11FF  # hangul jamo
        or 0x1F300 <= codepoint <= 0x1FAFF  # emoji (arco simple)
    )


def estimate_tokens(text: str) -> int:
    """Coste de un resultado: peso por carácter + sobrecoste de citación.

    Revisión Phase 2 (eje 9): el viejo `len(text)//4` asumía ES/EN; en
    chino/japonés el tokenizer real consume ~1 token POR CARÁCTER — una cota
    chars/4 con CJK falseaba el criterio 4 (un payload "1600" podía ser
    >6000 tokens reales). Ahora: CJK/emoji ⇒ 1 token por carácter, resto ⇒
    0.25 (`latin//4`, misma aproximación de ES/EN válida). La COTA 2000 de
    UH.md es REAL ahora en los cuatro scripts.
    """
    heavy = sum(1 for char in text if _is_cjk(char))
    light = len(text) - heavy
    return light // 4 + heavy + CITATION_OVERHEAD_TOKENS


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
