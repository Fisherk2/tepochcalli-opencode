"""Presupuesto de tokens de `search` — estimador y truncado determinista (plan §5).

Dominio puro del server: sin `mcp` ni infraestructura — solo el puerto
congelado `tepochcalli_flow.ports.CitedChunk` y los defaults del flow (nada de
literales duplicados: `TOP_K_DEFAULT` sale de `config.DEFAULT_TOP_K`).

Fuentes de verdad:

* tasks/plan.md §5 «Presupuesto de tokens» — base `len(text)//4`, techo
  **1600**, corte por score descendente, `truncated: true` al cortar,
  `top_k` ∈ [1,20] con efectivo `min(solicitado, 8)`.
* specs/spec-mcp-server.md §Presupuesto de tokens — el estimador aproxima
  ES/EN a razón de 4 chars/token; revisión Phase 2 (eje 9): CJK/emoji pesa 1
  token POR CARÁCTER — el margen ≥400 tokens deja la pregunta y la respuesta
  del agente dentro de la cota 2000 de UH.md (criterio 4) en los cuatro scripts.

**Default de `top_k` (`TEPOCHCALLI_TOP_K`):** `TOP_K_DEFAULT` se deriva del
entorno en IMPORT (`opencode.json` → `environment`), jamás del toml: en import
no se conoce el vault. Rango ÚTIL 1–8 — `effective_top_k` recorta a
`TOP_K_CAP = 8` todo lo que pase de ahí (el `default` del schema lo refleja,
pero el corte es duro); valores no enteros o fuera de [1,20] caen a
`DEFAULT_TOP_K` — un default fuera del contrato rompería TODA `search` sin
`top_k` explícito (hueco #4).
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Final

from tepochcalli_flow.config import DEFAULT_TOP_K, TOP_K_ENV
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


def _top_k_from_env(raw: str | None) -> int:
    """`TEPOCHCALLI_TOP_K` crudo → entero en `[TOP_K_MIN, TOP_K_MAX]`; el resto ⇒ `DEFAULT_TOP_K`.

    Puro: el import del módulo lo llama con `os.environ.get(TOP_K_ENV)`. Solo
    entorno — en import no hay vault del que leer el toml, y una env mal puesta
    (no entero, ≤ 0 o fuera del contrato como `21`) no puede tumbar el
    arranque del server ni romper `search` con un default inválido.
    """
    try:
        value = int((raw or "").strip())
    except ValueError:
        return DEFAULT_TOP_K
    return value if TOP_K_MIN <= value <= TOP_K_MAX else DEFAULT_TOP_K


TOP_K_DEFAULT: Final = _top_k_from_env(os.environ.get(TOP_K_ENV))
"""Por omisión, `TEPOCHCALLI_TOP_K` (declarada en `opencode.json`) o 5.

Es el `default` del schema de `search`; `effective_top_k` sigue recortando a
`TOP_K_CAP` (rango útil 1–8).
"""


def _is_cjk(char: str) -> bool:
    """¿Pesa 1 token el carácter? CJK/hanzi/hangul + símbolos y emoji (peso por carácter).

    Review eje 9 + W-07: hangul silábico (AC00–D7AF), dingbats/símbolos
    (2600–27BF) y banderas (1F1E6–1F1FF, regional indicators) también pesan;
    la puntuación general (2000–206F) queda EN el arco ligero — no delata
    script y el tokenizer la fragmenta lejos de 1 token por carácter.
    """
    codepoint = ord(char)
    return (
        0x3000 <= codepoint <= 0x9FFF  # puntuación CJK + hiragana/katakana + ideographs
        or 0xF900 <= codepoint <= 0xFAFF  # ideographs de compatibilidad
        or 0x1100 <= codepoint <= 0x11FF  # hangul jamo
        or 0xAC00 <= codepoint <= 0xD7AF  # W-07: hangul syllables
        or 0x2600 <= codepoint <= 0x27BF  # W-07: dingbats/símbolos (✂ ✈ …)
        or 0x1F1E6 <= codepoint <= 0x1F1FF  # W-07: regional indicators (banderas 🇲🇽)
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
    `truncated: true`. Sedes de W-09: el HEADING cuenta — cruza el wire junto
    al `text` y se paga a la misma tarifa ligera (`len(heading)//4`; el `25`
    flat sigue cubriendo path+offsets). Borde documentado: si un ÚNICO chunk
    excede el techo por sí solo se entrega igual —una cita parcial vale más
    que un payload vacío— con `truncated: false` (no se descartó ninguno:
    `kept == ordered`); con el flow de Phase 1 no ocurre (chunks ≤1536 bytes,
    headings ≤200 por W-09).
    """
    ordered = sorted(chunks, key=lambda chunk: chunk.score, reverse=True)
    kept: list[CitedChunk] = []
    used = 0
    for chunk in ordered:
        # W-09: el heading cruza el wire junto al text — sus chars pagan token
        # (arco ligero //4); el `25` flat sigue cubriendo path + offsets.
        cost = estimate_tokens(chunk.text) + (len(chunk.heading or "") // 4)
        if kept and used + cost > PAYLOAD_TOKEN_CEILING:
            break
        kept.append(chunk)
        used += cost
    return kept, len(kept) < len(ordered)
