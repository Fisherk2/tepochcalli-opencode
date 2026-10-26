"""T2: presupuesto de tokens del server — estimador y truncado determinista (plan §5).

Fuentes de verdad:

* tasks/plan.md §5 «Presupuesto de tokens» — `coste = len(text)//4 + 25`,
  techo **1600**, corte por score descendente, `truncated: true` al cortar.
* specs/spec-mcp-server.md §Presupuesto de tokens — el estimador es chars/4
  (aprox ES/EN) y el margen ≥400 tokens deja la pregunta y la respuesta del
  agente dentro de la cota 2000 de UH.md (criterio 4).
* `top_k` ∈ [1,20] (fuera → `VALIDATION_ERROR`), efectivo `min(solicitado, 8)`.

Dominio puro del server: sin infraestructura — solo `tepochcalli_flow.ports`
(puerto congelado de Phase 1). Corte por score: NUNCA se descarta el de mayor
score; los empatados conservan el orden estable (del más alto al más bajo).
"""

from __future__ import annotations

import pytest
from tepochcalli_flow.ports import CitedChunk
from tepochcalli_mcp import budget


def _chunk(
    score: float, text: str = "x" * 400, *, source_path: str = "00-Resources/a.md"
) -> CitedChunk:
    """Chunk sintético para el presupuesto: el text manda el coste, el score el orden."""
    return CitedChunk(
        text=text,
        source_path=source_path,
        heading=None,
        char_start=0,
        char_end=len(text),
        score=score,
    )


# --- estimador -----------------------------------------------------------------


def test_estimate_tokens_is_chars_over_four_plus_citation_overhead() -> None:
    """`len(text)//4 + 25`: el 25 es el sobrecoste de citación (path+heading+offsets)."""
    assert budget.estimate_tokens("") == budget.CITATION_OVERHEAD_TOKENS
    assert budget.estimate_tokens("x" * 400) == 100 + budget.CITATION_OVERHEAD_TOKENS
    assert budget.estimate_tokens("x" * 403) == 100 + budget.CITATION_OVERHEAD_TOKENS  # //4
    assert budget.estimate_tokens("x" * 404) == 101 + budget.CITATION_OVERHEAD_TOKENS


def test_estimate_tokens_counts_characters_not_bytes_for_multibyte_text() -> None:
    """Chars, no bytes: un chunk CJK/multibyte no dispara el estimador (fixture adversa)."""
    cjk = "日" * 400  # 1200 bytes UTF-8, 400 chars
    assert budget.estimate_tokens(cjk) == 100 + budget.CITATION_OVERHEAD_TOKENS


def test_constants_pin_the_contract_numbers() -> None:
    """Los literales del contrato viven como constantes, no repetidos (plan §5)."""
    assert budget.CITATION_OVERHEAD_TOKENS == 25
    assert budget.PAYLOAD_TOKEN_CEILING == 1600
    assert budget.TOP_K_MIN == 1
    assert budget.TOP_K_MAX == 20
    assert budget.TOP_K_CAP == 8
    assert budget.TOP_K_DEFAULT == 5


# --- top_k efectivo ------------------------------------------------------------


@pytest.mark.parametrize(("requested", "effective"), [(1, 1), (5, 5), (8, 8), (9, 8), (20, 8)])
def test_effective_top_k_clamps_to_the_hard_cap_of_eight(requested: int, effective: int) -> None:
    """`min(solicitado, 8)`: el tope duro evita payloads fuera de presupuesto (plan §5)."""
    assert budget.effective_top_k(requested) == effective


@pytest.mark.parametrize("invalid", [0, -1, 21, 100])
def test_effective_top_k_rejects_values_outside_the_contract_range(invalid: int) -> None:
    """Fuera de [1,20] → `ValueError`; el handler la mapea a `VALIDATION_ERROR`."""
    with pytest.raises(ValueError, match="top_k"):
        budget.effective_top_k(invalid)


# --- truncado determinista ------------------------------------------------------


def test_budget_keeps_everything_under_the_ceiling_without_truncating() -> None:
    """Tres chunks baratos caben holgados: nada se corta y `truncated` es False."""
    chunks = [_chunk(0.9), _chunk(0.8), _chunk(0.7)]

    kept, truncated = budget.apply_budget(chunks)

    assert kept == chunks
    assert truncated is False


def test_budget_cuts_lowest_scores_and_flags_truncated() -> None:
    """Exceder 1600 ⇒ se descartan los de MENOR score y `truncated` es True."""
    # 5 chunks de 400 chars: 5 * (100 + 25) = 625... no alcanza: uso chunks grandes.
    big = [_chunk(score, "x" * 1500) for score in (0.9, 0.8, 0.7, 0.6)]
    # coste c/u = 375 + 25 = 400; 4 * 400 = 1600 == techo => sin corte.
    kept, truncated = budget.apply_budget(big)
    assert len(kept) == 4 and truncated is False

    overflow = [*big, _chunk(0.5, "x" * 1500)]  # 5 * 400 = 2000 > 1600
    kept, truncated = budget.apply_budget(overflow)

    assert truncated is True
    assert len(kept) == 4, "el techo 1600 admite exactamente 4 chunks de 400 tokens"
    assert kept[0].score == 0.9, "el de mayor score NUNCA se descarta"
    assert [chunk.score for chunk in kept] == [0.9, 0.8, 0.7, 0.6]


def test_budget_sorts_by_score_descending_before_accumulating() -> None:
    """El corte es por score descendente aunque el lector entregue desordenado."""
    # coste c/u = 875 + 25 = 900: solo cabe el primero de los tres.
    unsorted = [_chunk(0.2, "x" * 3500), _chunk(0.95, "x" * 3500), _chunk(0.1, "x" * 3500)]

    kept, truncated = budget.apply_budget(unsorted)

    assert truncated is True
    assert [chunk.score for chunk in kept] == [0.95], "solo cabe el de mayor score"


def test_budget_total_never_exceeds_the_ceiling() -> None:
    """La suma de costes de los conservados ≤ 1600 (criterio 4: la cota es dura)."""
    chunks = [_chunk(score, "x" * 1536) for score in (1.0, 0.9, 0.8, 0.7, 0.6, 0.5)]

    kept, _truncated = budget.apply_budget(chunks)

    total = sum(budget.estimate_tokens(chunk.text) for chunk in kept)
    assert total <= budget.PAYLOAD_TOKEN_CEILING
    assert len(kept) < len(chunks), "6 chunks de 409 tokens exceden 1600: debe cortar"


def test_budget_of_empty_results_is_not_truncated() -> None:
    """Índice sin coincidencias: lista vacía, sin corte (ni bandera)."""
    assert budget.apply_budget([]) == ([], False)


def test_a_single_oversized_chunk_is_still_returned_not_dropped() -> None:
    """Borde: un solo chunk que por sí solo excede el techo se devuelve igual.

    Descartarlo dejaría al agente SIN contexto (payload vacío con bandera de
    truncado sería peor que un moderado exceso); `truncated` queda en False
    porque NO se descartó ningún resultado — la bandera documenta el CORTE,
    no el exceso. Los chunks reales son ≤1536 bytes, así que este caso no se
    produce con el flow de Phase 1 — la semántica queda fijada aquí.
    """
    huge = [_chunk(0.99, "x" * 8000)]

    kept, truncated = budget.apply_budget(huge)

    assert kept == huge
    assert truncated is False, "nada se descartó: no hay corte que reportar"
