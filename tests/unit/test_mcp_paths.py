"""T2: validación de rutas en el borde MCP — glob de `search` y `subdir` de `add_source`.

Fuentes de verdad:

* SPEC.md §Boundaries — «validar entradas en el borde MCP (`add_source` rutas)».
* tasks/plan.md §5 — `path_filter` absoluto o con `..` → `VALIDATION_ERROR`;
  `subdir` normalizado, sin `..`, sin absolutos, destino siempre dentro de
  `00-Resources/`, por omisión `_inbox` (T5).
* specs/spec-mcp-server.md §Security — path traversal → `VALIDATION_ERROR`.

Decisión documentada: ESTE módulo valida la forma del glob (relativo, sin `..`)
en el borde del server, pero NO lo traduce a SQL — la traducción `*`→`%` vive
y se congela en `tepochcalli_flow.adapters.lancedb_reader.
path_filter_to_like_predicate` y el adaptador la aplica (importarla aquí
arrastraría `lancedb` al paquete del server; test de arquitectura). El
adaptador además re-valida en su propio borde: defensa en profundidad, sin
duplicar la traducción.
"""

from __future__ import annotations

import pytest
from tepochcalli_mcp import paths

# --- path_filter (glob relativo al vault) ---------------------------------------


def test_none_is_a_valid_path_filter() -> None:
    """Sin filtro busca en todo el índice: `None` es válido y se devuelve tal cual."""
    assert paths.validate_path_filter(None) is None


@pytest.mark.parametrize(
    "glob",
    [
        "00-Resources/*.md",
        "00-Resources/sub/*",
        "00-Resources/lit-pediatría/**/*.pdf",
        "00-Resources/con_guion_bajo.md",
        "00-Resources/?.md",
        "00-Resources/ñ-日.md",
    ],
)
def test_relative_globs_under_resources_are_accepted(glob: str) -> None:
    """Globs relativos multibyte incluidos: se aceptan sin tocarlos (semántica del adaptador)."""
    assert paths.validate_path_filter(glob) == glob


@pytest.mark.parametrize(
    "glob",
    [
        "/absoluto/*.md",
        "00-Resources/../secreto/*.md",
        "00-Resources\\..\\secreto\\*.md",  # backslash normalizado: mismo rechazo
        "../fuera-del-vault.md",
        "sub/../../etc/passwd",
    ],
)
def test_absolute_or_traversal_globs_are_rejected(glob: str) -> None:
    """Absoluto o con `..` → `ValueError`; el handler lo mapea a `VALIDATION_ERROR`."""
    with pytest.raises(ValueError):
        paths.validate_path_filter(glob)


def test_empty_glob_is_rejected_as_well() -> None:
    """Un glob vacío no filtra nada y no es una ruta: se rechaza en el borde."""
    with pytest.raises(ValueError):
        paths.validate_path_filter("")


# --- subdir (add_source, T5 sobre esta base) -------------------------------------


def test_missing_subdir_defaults_to_inbox() -> None:
    """`None`, vacío o en blanco → `_inbox` (destino canónico del plan §add_source)."""
    assert paths.validate_subdir(None) == paths.DEFAULT_SUBDIR
    assert paths.validate_subdir("") == paths.DEFAULT_SUBDIR
    assert paths.validate_subdir("   ") == paths.DEFAULT_SUBDIR


@pytest.mark.parametrize(
    ("given", "normalized"),
    [
        ("lit", "lit"),
        ("lit-pediatría", "lit-pediatría"),
        ("lit/pediatría", "lit/pediatría"),
        ("./lit/", "lit"),
        ("lit\\pediatría", "lit/pediatría"),  # backslash → POSIX (D9.1)
        ("ñ-日", "ñ-日"),
    ],
)
def test_subdir_is_normalized_to_a_relative_posix_path(given: str, normalized: str) -> None:
    """`subdir` queda relativo, POSIX y sin segmentos vacíos (D9.1)."""
    assert paths.validate_subdir(given) == normalized


@pytest.mark.parametrize(
    "subdir",
    [
        "/absoluto",
        "../fuera",
        "lit/../../fuera",
        "lit\\..\\fuera",
    ],
)
def test_subdir_that_escapes_resources_is_rejected(subdir: str) -> None:
    """Absoluto o `..` → `ValueError`: jamás se escribe fuera de `00-Resources/` (D9.1)."""
    with pytest.raises(ValueError):
        paths.validate_subdir(subdir)


def test_subdir_root_is_canonicalized_to_the_default() -> None:
    """`00-Resources` o `.` caen al default: no son un subdirectorio del recurso."""
    assert paths.validate_subdir(".") == paths.DEFAULT_SUBDIR
    assert paths.validate_subdir("00-Resources/") == paths.DEFAULT_SUBDIR


def test_validated_subdir_joins_resources_dir() -> None:
    """La helper de destino compone `00-Resources/<subdir>` sin duplicar prefijo."""
    assert str(paths.resources_destination("lit")) == "00-Resources/lit"
    assert str(paths.resources_destination(None)) == "00-Resources/_inbox"
