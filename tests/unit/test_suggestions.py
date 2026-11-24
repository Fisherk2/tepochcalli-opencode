"""Límites de `suggestions` (D64): `SUGGESTION_LIMIT` y `SUGGESTION_CUTOFF` fijados.

La frontera B′ propone nombres en `details.suggestions` con `difflib` (stdlib,
R1/ADR-011). Hasta ahora solo corría el happy path con UN candidato
(`test_paths_frontier.py::test_missing_path_reports_exists_false…`); aquí se
congelan los dos umbrales que el módulo declara:

* `SUGGESTION_LIMIT = 3` — el agente corrige en un reintento, no elige de un
  menú: con más candidatos se devuelven exactamente 3, de mejor a peor;
* `SUGGESTION_CUTOFF = 0.6` — por debajo son nombres distintos, no un typo, y
  el corte es INCLUSIVO (`difflib.get_close_matches` usa `ratio >= cutoff`).
"""

from __future__ import annotations

from tepochcalli_mcp import suggestions


def test_more_candidates_than_the_limit_return_exactly_the_limit_best_first() -> None:
    """4 candidatos sobre el corte ⇒ exactamente `SUGGESTION_LIMIT`, de mejor a peor.

    Los ratios (mismo criterio que `difflib`, verificado): documentoss 0.952,
    documento 0.947, documentas 0.900, documental 0.800 — los tres primeros
    entran; el cuarto se corta por el tope, no por el corte.
    """
    result = suggestions.suggest_names(
        "documentos", ["documental", "documentas", "documento", "documentoss"]
    )

    assert len(result) == suggestions.SUGGESTION_LIMIT == 3
    assert result == ["documentoss", "documento", "documentas"], "ordenado por score descendente"


def test_candidates_below_the_cutoff_are_discarded() -> None:
    """Nombres poco parecidos (ratio < 0.6) se descartan: lista vacía, no ruido.

    materiales 0.300, notas 0.400, fotos 0.533 — ninguno es un typo de
    `documentos`, y proponerlo haría al agente reintentar con una ruta que
    tampoco existe.
    """
    assert suggestions.suggest_names("documentos", ["materiales", "notas", "fotos"]) == []


def test_a_ratio_exactly_at_the_cutoff_is_kept_and_just_below_is_dropped() -> None:
    """El corte es INCLUSIVO: `ratio == 0.6` se propone, `0.5` no (`>=`, no `>`).

    Parejas de aritmética exacta sobre `SequenceMatcher`:
    `("abcde","abcxy")` = 2·3/10 = 0.6 (bloque común `abc`) — justo en
    `SUGGESTION_CUTOFF` ⇒ se devuelve; `("abcd","abxy")` = 2·2/8 = 0.5 ⇒ no.
    Si el corte cambiara a estricto (`>`) el primer assert fallaría.
    """
    assert suggestions.SUGGESTION_CUTOFF == 0.6

    assert suggestions.suggest_names("abcde", ["abcxy"]) == ["abcxy"]
    assert suggestions.suggest_names("abcd", ["abxy"]) == []
