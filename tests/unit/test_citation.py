"""Tests del dominio de cita (Phase 1, T4) — escritos en rojo antes que el módulo.

Fuentes de verdad:

* specs/spec-rag-engine.md §Chunking — campos derivados por chunk y F1:
  `text[char_start:char_end] == chunk.text` sobre offsets de carácter.
* specs/spec-mcp-server.md §search — forma congelada del resultado
  `{text, source_path, heading, char_start, char_end, score}`.
* tasks/todo.md → T4 (AC): `source_path` POSIX con prefijo `00-resources/`,
  `heading` = último heading padre, offsets verificables, `doc_kind` ∈
  {md, markdown, txt, pdf}, `model` = embedder configurado, 100% cobertura.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tepochcalli_flow import citation
from tepochcalli_flow import config as flow_config

# --- source_path ---------------------------------------------------------------


def test_source_path_is_vault_relative_and_preserves_free_nesting() -> None:
    """La cita es POSIX relativa al VAULT: no prefija ni retira raíz (ADR-010 D41)."""
    assert citation.normalize_source_path("lit/pediatría/ruiz2024.md") == (
        "lit/pediatría/ruiz2024.md"
    )
    assert citation.normalize_source_path(Path("a/b/c/d.txt")) == "a/b/c/d.txt"


def test_source_path_keeps_existing_prefix_unchanged() -> None:
    """Un path ya relativo al vault se devuelve tal cual (spec-mcp-server §search)."""
    assert (
        citation.normalize_source_path("00-resources/lit-pediatría/ruiz2024.pdf")
        == "00-resources/lit-pediatría/ruiz2024.pdf"
    )


def test_source_path_drops_dot_segments_and_resolves_internal_parents() -> None:
    """`./` se elimina y `..` se resuelve dentro del vault, sin prefijar nada."""
    assert citation.normalize_source_path("./lit/a.md") == "lit/a.md"
    assert citation.normalize_source_path("lit/tema/../a.md") == "lit/a.md"
    assert citation.normalize_source_path("00-resources/../a.md") == "a.md"


def test_source_path_rejects_a_parent_segment_that_escapes_the_vault() -> None:
    """`..` sin segmento previo que resolver escapa del vault ⇒ `CitationError` (D41)."""
    for escaping in ("../a.md", "../../a.md", "lit/../../a.md"):
        with pytest.raises(citation.CitationError, match="escapa"):
            citation.normalize_source_path(escaping)


def test_source_path_converts_backslashes_to_posix() -> None:
    r"""Entrada con `\` (Windows) → separadores POSIX hacia delante."""
    assert citation.normalize_source_path("lit\\a.md") == "lit/a.md"
    assert citation.normalize_source_path("00-resources\\lit\\a.md") == "00-resources/lit/a.md"


def test_source_path_collapses_duplicate_separators() -> None:
    """Separadores repetidos no producen segmentos vacíos en la salida."""
    assert citation.normalize_source_path("00-resources//lit///a.md") == "00-resources/lit/a.md"


def test_source_path_rejects_an_empty_citation() -> None:
    """Vacío (`` | `.` | `./` | `/`) no es una cita: `CitationError`."""
    for empty in ("", ".", "./", "/"):
        with pytest.raises(citation.CitationError):
            citation.normalize_source_path(empty)


# --- heading -------------------------------------------------------------------


def test_heading_returns_last_parent_before_offset() -> None:
    """El heading devuelto es el último (más interno) que precede a `char_start`."""
    text = "# Introducción\n\n## Sección dos\n\nContenido del chunk.\n"
    char_start = text.index("Contenido")

    assert citation.heading_before(text, char_start) == "Sección dos"


def test_heading_is_none_without_preceding_heading() -> None:
    """Sin heading previo → `None` (ni `""` ni el nombre del archivo; F1/T4)."""
    text = "Solo prosa.\n\nMás prosa.\n"

    assert citation.heading_before(text, len(text)) is None


def test_heading_ignores_hash_lines_inside_backtick_fence() -> None:
    """``` con info string: el `#` dentro del bloque cercado no cuenta (§Chunking)."""
    text = "# Real\n\n```python\n# comentario de código\n```\n\nDespués del bloque.\n"
    char_start = text.index("Después")

    assert citation.heading_before(text, char_start) == "Real"


def test_heading_ignores_hash_lines_inside_tilde_fence() -> None:
    """Bloque `~~~` (cerrado con más tildes): ningún `#` de ahí dentro cuenta."""
    text = "~~~\n# falso\n~~~~\nCuerpo sin heading.\n"
    char_start = text.index("Cuerpo")

    assert citation.heading_before(text, char_start) is None


def test_heading_ignores_hash_inside_inline_code_span() -> None:
    """`#` dentro de un span de código inline en la misma línea no es heading."""
    text = "Párrafo con `# no es heading` y cierre del span.\n\nContenido.\n"
    char_start = text.index("Contenido")

    assert citation.heading_before(text, char_start) is None


def test_heading_ignores_span_opened_on_a_previous_line() -> None:
    """Span multi-línea: el `#` de la línea interior sigue dentro del span (CommonMark)."""
    text = "# Título real\n\nPárrafo con `código\n# dentro del span\nsigue aquí`.\n\nCierre.\n"
    char_start = text.index("Cierre")

    assert citation.heading_before(text, char_start) == "Título real"


def test_heading_after_char_start_never_affects_the_result() -> None:
    """`#` posterior a `char_start` no puede alterar la cita (spec-mcp-server §search)."""
    text = "Contenido citado primero.\n\n# Posterior\n\nMás contenido.\n"
    char_start = text.index("Contenido")

    assert citation.heading_before(text, char_start) is None


def test_heading_skips_yaml_frontmatter_including_hash_comments() -> None:
    """Frontmatter YAML: delimitadores `---` y comentarios `#` no son headings."""
    text = "---\n# comentario YAML\ntitle: Nota\n---\n\n# Real\n\nCuerpo.\n"
    char_start = text.index("Cuerpo")

    assert citation.heading_before(text, char_start) == "Real"


def test_heading_does_not_half_support_setext() -> None:
    """Setext (`===`/`---`) no soportado — limitación documentada: solo ATX."""
    setext_equal = "Título setext\n=============\n\nContenido.\n"
    setext_dash = "Título setext\n------------\n\nContenido.\n"

    assert citation.heading_before(setext_equal, setext_equal.index("Contenido")) is None
    assert citation.heading_before(setext_dash, setext_dash.index("Contenido")) is None


def test_heading_strips_atx_closing_sequence() -> None:
    """`## Título ##` → `Título`: la secuencia de cierre no forma parte del título."""
    text = "## Título ##\n\nContenido.\n"

    assert citation.heading_before(text, text.index("Contenido")) == "Título"


def test_heading_ignores_a_hash_after_a_mismatched_backtick_run_inside_an_open_span() -> None:
    """Span inline abierto: un run de backticks de OTRA longitud no lo cierra (CommonMark).

    `_update_code_span` documenta que solo un run de la MISMA longitud cierra el
    span. Aquí la primera línea abre un span con un backtick y dentro trae un
    run de dos (`` `` ``) más un `#` —que tampoco cierra—, de modo que la
    siguiente línea, que empieza por `#`, sigue DENTRO del span y no es un
    heading: `heading_before` la ignora. Si cualquier backtick cerrara el
    span, `# falso dentro del span` se citaría como heading padre.

    El control positivo va en el mismo arco: con un run de la MISMA longitud
    que cierra el span, un `#` posterior vuelve a citarse — el escáner no se
    queda atascado.
    """
    text = "`a ``b`` # no-es-heading\n# falso dentro del span\nsigue el span\n`\n\nCuerpo real.\n"
    mismo_run_cierra = "`a ``b`` c`\n\n# Real después\n\nCuerpo real.\n"

    assert citation.heading_before(text, text.index("Cuerpo real")) is None
    assert (
        citation.heading_before(mismo_run_cierra, mismo_run_cierra.index("Cuerpo real"))
        == "Real después"
    )


# --- offsets -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("doc_kind", "expected"),
    [
        ("md", "source"),
        ("markdown", "source"),
        ("txt", "source"),
        ("pdf", "extract"),
        ("docx", "extract"),
        ("pptx", "extract"),
        ("xlsx", "extract"),
        ("xls", "extract"),
    ],
)
def test_offsets_ref_for_pins_the_t7_coordinate_space(
    doc_kind: citation.DocKind, expected: str
) -> None:
    """Decisión T7/D50 congelada: `source` para texto plano; `extract` para binarios."""
    assert citation.offsets_ref_for(doc_kind) == expected


def test_citation_offsets_are_character_level_for_multibyte_text() -> None:
    """Los offsets F1 son CHAR-level (Python): multibyte no desplaza el slice.

    `'😀 ñ 日'` —3 caracteres— mide offsets por CARÁCTER, nunca por byte de
    UTF-8 (que daría 10). El slice por char reproduce el chunk exacto.
    """
    text = "\U0001f600 ñ 日fragmento multibyte"
    char_start = text.index("fragmento")
    char_end = char_start + len("fragmento multibyte")

    assert citation.verify_slice_identity(text, char_start, char_end, "fragmento multibyte")
    assert text[char_start:char_end] == "fragmento multibyte"
    # La longitud del índice de bytes no puede ser el offset: char-level explícito.
    assert char_start != len(text.encode("utf-8"))


def test_validate_offsets_returns_the_exact_slice_bounds() -> None:
    """Límites válidos se devuelven tal cual: `0 <= start < end <= len(text)`."""
    text = "hola mundo"

    assert citation.validate_offsets(text, 0, len(text)) == (0, len(text))
    assert citation.validate_offsets(text, 6, 10) == (6, 10)


def test_validate_offsets_rejects_end_beyond_text_length() -> None:
    """`char_end > len(text)` se rechaza: la cita nunca sobresale del texto (F1)."""
    text = "hola mundo"

    with pytest.raises(citation.CitationError, match="Offsets inválidos"):
        citation.validate_offsets(text, 0, len(text) + 1)


@pytest.mark.parametrize(
    ("char_start", "char_end"),
    [(-1, 5), (5, 5), (7, 3)],
)
def test_validate_offsets_rejects_bad_ranges(char_start: int, char_end: int) -> None:
    """Negativo, vacío (`start == end`) o invertido → `CitationError`."""
    with pytest.raises(citation.CitationError):
        citation.validate_offsets("hola mundo", char_start, char_end)


def test_verify_slice_identity_holds_for_real_chunk_text() -> None:
    """Identidad F1: `text[char_start:char_end] == chunk_text` → True."""
    text = "# Título\n\nfragmento exacto del chunk.\n"
    char_start = text.index("fragmento")
    char_end = char_start + len("fragmento exacto del chunk.")

    assert citation.verify_slice_identity(text, char_start, char_end, "fragmento exacto del chunk.")


def test_verify_slice_identity_is_false_on_mismatch() -> None:
    """Texto de chunk que no coincide con el slice → False, nunca un True parcial."""
    text = "contenido real"

    assert not citation.verify_slice_identity(text, 0, 5, "otro texto")


def test_verify_slice_identity_is_false_on_out_of_bounds_offsets() -> None:
    """Offsets fuera de rango → False sin lanzar, para assert barato en T5/T6."""
    text = "contenido real"

    assert not citation.verify_slice_identity(text, 0, len(text) + 1, "contenido real")


# --- doc_kind ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("nota.md", "md"),
        ("nota.markdown", "markdown"),
        ("nota.txt", "txt"),
        ("paper.pdf", "pdf"),
        ("informe.docx", "docx"),
        ("presentacion.pptx", "pptx"),
        ("hoja.xlsx", "xlsx"),
        ("viejo.xls", "xls"),
        ("NOTA.MD", "md"),
    ],
)
def test_doc_kind_from_extension(filename: str, expected: citation.DocKind) -> None:
    """`doc_kind` ∈ las 8 extensiones soportadas, en minúsculas, derivado de la extensión."""
    assert citation.doc_kind_for(filename) == expected


def test_doc_kind_raises_on_unknown_extension() -> None:
    """Extensión desconocida → `UnsupportedDocKindError`; nunca se asume `txt`."""
    with pytest.raises(
        citation.UnsupportedDocKindError, match="md, markdown, txt, pdf, docx, pptx, xlsx, xls"
    ):
        citation.doc_kind_for("pagina.html")


def test_doc_kind_raises_when_extension_is_missing() -> None:
    """Sin extensión también es un error tipado y cuelga de `CitationError` (CODE_STYLE)."""
    with pytest.raises(citation.CitationError):
        citation.doc_kind_for("sin-extension")


# --- model ---------------------------------------------------------------------


def test_model_id_defaults_to_the_single_config_constant() -> None:
    """El default proviene de `config.DEFAULT_EMBEDDING_MODEL` (literal en un solo sitio)."""
    assert citation.model_id() == flow_config.DEFAULT_EMBEDDING_MODEL


def test_model_id_literal_is_not_duplicated_in_citation_module() -> None:
    """`citation.py` no re-escribe el literal del modelo: lo importa de `config.py`."""
    assert citation.__file__ is not None
    module_source = Path(citation.__file__).read_text(encoding="utf-8")

    assert flow_config.DEFAULT_EMBEDDING_MODEL not in module_source


def test_model_id_uses_the_resolved_config_model() -> None:
    """Con config resuelta, `model` guarda el id real del embedder configurado (ADR-006)."""
    cfg = flow_config.Config(
        models_dir=Path("/tmp/modelos"),
        embedding=flow_config.EmbeddingConfig(model="otro-embedder"),
    )

    assert citation.model_id(cfg) == "otro-embedder"


# --- W-09 (review 5-ejes): heading con tope al construir el CitedChunk ------------------


def test_cited_chunk_heading_is_truncated_to_two_hundred_chars() -> None:
    """W-09: un heading de 300 chars se entrega truncado a 200 en el `CitedChunk`.

    El heading cruza el wire en cada resultado de `search`: sin tope, un
    heading kilométrico (un `#` de 50k chars) infla el payload fuera del
    presupuesto (criterio 4). Constante única-homed en `citation`.
    """
    from tepochcalli_flow.adapters import lancedb_reader

    rows: list[dict[str, object]] = [
        {
            "text": "cuerpo",
            "source_path": "00-resources/a.md",
            "heading": "H" * 300,
            "char_start": 0,
            "char_end": 6,
            "score": 1.0,
            "doc_kind": "md",
            "_relevance_score": 1.0,
        }
    ]
    (chunk,) = lancedb_reader._to_cited_chunks(rows)
    assert chunk.heading is not None and len(chunk.heading) == 200, "recortado al tope"
    assert str(citation.MAX_HEADING_LENGTH) == "200"
