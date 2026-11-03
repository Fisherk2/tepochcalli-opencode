"""Similitud de nombres para `details.suggestions` (D64) — dominio puro, solo stdlib.

`Documentos` ⇒ propone `documentos`: la comparación normaliza a casefold pero
devuelve SIEMPRE el nombre **real** del vault — el agente reintenta con una
ruta que existe, no con su propia normalización. `difflib` (stdlib) cubre el
typo sin una dependencia nueva (R1/ADR-011).
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable
from typing import Final

SUGGESTION_LIMIT: Final = 3
"""Máximo de nombres propuestos: el agente corrige en un reintento, no elige de un menú."""

SUGGESTION_CUTOFF: Final = 0.6
"""Umbral de `difflib`: por debajo son nombres distintos, no un typo."""


def suggest_names(requested: str, candidates: Iterable[str]) -> list[str]:
    """Nombres de `candidates` parecidos a `requested` (sin distinguir mayúsculas).

    Devuelve los nombres tal como existen en el disco (el `casefold` es solo la
    clave de comparación); lista vacía si ninguno se parece.
    """
    real_by_folded = {name.casefold(): name for name in candidates}
    matches = difflib.get_close_matches(
        requested.casefold(), list(real_by_folded), n=SUGGESTION_LIMIT, cutoff=SUGGESTION_CUTOFF
    )
    return [real_by_folded[match] for match in matches]
