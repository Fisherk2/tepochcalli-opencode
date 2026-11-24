"""T2: presupuesto de tokens del server — estimador y truncado determinista (plan §5).

Fuentes de verdad:

* tasks/plan.md §5 «Presupuesto de tokens» — `coste = len(text)//4 + 25`,
  techo **1600**, corte por score descendente, `truncated: true` al cortar.
* specs/spec-mcp-server.md §Presupuesto de tokens — el estimador es chars/4
  (aprox ES/EN) y el margen ≥400 tokens deja la pregunta y la respuesta del
  agente dentro de la cota 2000 de BACKLOG.md (criterio 4).
* `top_k` ∈ [1,20] (fuera → `VALIDATION_ERROR`), efectivo `min(solicitado, 8)`.

Dominio puro del server: sin infraestructura — solo `tepochcalli_flow.ports`
(puerto congelado de Phase 1). Corte por score: NUNCA se descarta el de mayor
score; los empatados conservan el orden estable (del más alto al más bajo).
"""

from __future__ import annotations

import pytest
from tepochcalli_flow.ports import CitedChunk
from tepochcalli_mcp import budget


def _chunk(score: float, text: str = "x" * 400, *, heading: str | None = None) -> CitedChunk:
    """Chunk sintético para el presupuesto: el text manda el coste, el score el orden."""
    return CitedChunk(
        text=text,
        source_path="00-resources/a.md",
        heading=heading,
        char_start=0,
        char_end=len(text),
        score=score,
    )


# --- estimador -----------------------------------------------------------------


def test_estimate_tokens_is_chars_over_four_plus_citation_overhead() -> None:
    """Peso latin: 4 chars/token + el 25 de citación (path+heading+offsets)."""
    assert budget.estimate_tokens("") == budget.CITATION_OVERHEAD_TOKENS
    assert budget.estimate_tokens("x" * 400) == 100 + budget.CITATION_OVERHEAD_TOKENS
    assert budget.estimate_tokens("x" * 403) == 100 + budget.CITATION_OVERHEAD_TOKENS  # //4
    assert budget.estimate_tokens("x" * 404) == 101 + budget.CITATION_OVERHEAD_TOKENS


def test_estimate_tokens_weights_cjk_one_token_per_character() -> None:
    """Peso CJK: 1 token POR CARÁCTER — la cota 2000 es REAL en chino/japonés (review eje 9)."""
    cjk = "日" * 400  # 400 chars (antes estimaba 100; el tokenizer real consume ~400)
    assert budget.estimate_tokens(cjk) == 400 + budget.CITATION_OVERHEAD_TOKENS
    mixed = "cohorte 日" * 100  # 900 chars: 800 latin / 100 CJK
    assert budget.estimate_tokens(mixed) == 800 // 4 + 100 + budget.CITATION_OVERHEAD_TOKENS


def test_estimate_tokens_counts_emoji_as_heavy() -> None:
    """Emoji (U+1F300+) también pesa 1 token por carácter — multibyte no escapa la cota."""
    assert budget.estimate_tokens("🧪" * 100) == 100 + budget.CITATION_OVERHEAD_TOKENS


def test_estimate_tokens_weights_hangul_dingbats_and_flags_one_per_character() -> None:
    """W-07: hangul silábico, dingbats/símbolos y banderas pesan 1 token POR carácter.

    Conteos exactos: 10 syllables → 30 tokens (no `30//4`); la puntuación
    general (0x2000–0x206F) SÍ queda en el arco ligero.
    """
    assert budget.estimate_tokens("한국어" * 10) == 30 + budget.CITATION_OVERHEAD_TOKENS
    assert budget.estimate_tokens("🇲🇽") == 2 + budget.CITATION_OVERHEAD_TOKENS, "bandera"
    assert budget.estimate_tokens("✂✈") == 2 + budget.CITATION_OVERHEAD_TOKENS, "dingbats"
    punctuation = "—…–"
    assert budget.estimate_tokens(punctuation) == budget.CITATION_OVERHEAD_TOKENS, (
        "0x2000–0x206F NO es heavy: 3 chars ligeros → 3//4 = 0"
    )
    mixed = "cohorte ✂" * 100
    assert budget.estimate_tokens(mixed) == 800 // 4 + 100 + budget.CITATION_OVERHEAD_TOKENS


def test_constants_pin_the_contract_numbers() -> None:
    """Los literales del contrato viven como constantes, no repetidos (plan §5)."""
    assert budget.CITATION_OVERHEAD_TOKENS == 25
    assert budget.PAYLOAD_TOKEN_CEILING == 1600
    assert budget.TOP_K_MIN == 1
    assert budget.TOP_K_MAX == 20
    assert budget.TOP_K_CAP == 8
    assert budget.TOP_K_DEFAULT == 5


def test_budget_counts_the_heading_in_the_chunk_cost() -> None:
    """W-09: el heading crusa el wire y sus chars entran en el coste del chunk.

    Antes el heading pagaba solo el `25` flat: dos chunks con headings
    kilométricos sumaban >3200 tokens estimados sin truncarse — el payload
    mentía la cota (criterio 4).
    """
    heavy = _chunk(0.9, text="cuerpo", heading="H" * 6000)  # ~25 + 6000//4 = 1526
    light = _chunk(0.5)  # "x"*400 → 125 tokens: 1526 + 125 > 1600 ⇒ corta
    kept, truncated = budget.apply_budget([heavy, light])

    assert kept == [heavy], "el de mayor score se conserva (ídem antes)"
    assert truncated is True, "corta: el heading ya paga su talla"


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


# --- `TEPOCHCALLI_TOP_K`: el default de `search` se declara en el entorno -------------


def test_top_k_from_env_reads_a_positive_integer() -> None:
    """`TEPOCHCALLI_TOP_K=7` ⇒ default 7 (leído en import; nunca del toml)."""
    assert budget._top_k_from_env("7") == 7


def test_top_k_from_env_falls_back_without_a_value() -> None:
    """Sin valor (o vacío/solo espacios) ⇒ `DEFAULT_TOP_K`."""
    assert budget._top_k_from_env(None) == 5
    assert budget._top_k_from_env("") == 5
    assert budget._top_k_from_env("   ") == 5


@pytest.mark.parametrize("bad", ["0", "-3", "siete"])
def test_top_k_from_env_ignores_values_outside_the_useful_range(bad: str) -> None:
    """No entero o ≤ 0 ⇒ default: el import del server nunca cae por una env mal puesta."""
    assert budget._top_k_from_env(bad) == 5


def test_top_k_from_env_falls_back_above_the_contract_range() -> None:
    """`TEPOCHCALLI_TOP_K=21` ⇒ 5: el default no puede exceder el contrato [1,20].

    Regresión (hueco #4): un entero > 0 fuera del rango se aceptaba como
    default; el schema de `search` heredaba 21 y `effective_top_k(21)` lanzaba
    `ValueError` — TODA `search` sin `top_k` explícito devolvía
    `VALIDATION_ERROR` sin diagnóstico alguno.
    """
    assert budget._top_k_from_env("21") == 5
