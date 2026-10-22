"""Tests de fuentes y parseo Markdown/TXT (Phase 1, T5) — escritos en rojo antes que los módulos.

Fuentes de verdad:

* specs/spec-rag-engine.md §Fuentes — whitelist `.md/.markdown/.txt/.pdf`,
  exclusiones de segmentos-punto y `.git/**`, F3 (los include patterns por sí
  solos NO excluyen dirs-punto) y F5 (`localfs` sin límite de tamaño ni hook:
  >100MB / symlink roto / ilegible → `skipped` con motivo, sin abortar el delta).
* specs/spec-rag-engine.md §Chunking — `RecursiveSplitter` con
  `chunk_size=1536`, `chunk_overlap=192` en BYTES (D11); metadatos por chunk:
  `source_path`, `heading` (nullable, D13), `char_start`/`char_end`, `doc_kind`
  no nulos y `model`; identidad F1 `text[char_start:char_end] == chunk.text`.
* tasks/todo.md → T5 (AC): fixture de anidamiento libre con 2 indexados y 1
  excluido; skips tipados sin abortar el pase.
"""

from __future__ import annotations

import itertools
import os
from collections.abc import Iterable
from pathlib import Path

import pytest
from cocoindex.resources.file import PatternFilePathMatcher
from tepochcalli_flow import citation, parsers, source
from tepochcalli_flow import config as flow_config

FIXTURE_VAULT = Path(__file__).parent / "fixtures" / "vault_markdown"

# --- walk: fixture dorada de T5 ------------------------------------------------


def _entries(items: Iterable[source.WalkItem]) -> list[source.SourceEntry]:
    """Filtra los elementos indexables de un pase de walk."""
    return [item for item in items if isinstance(item, source.SourceEntry)]


def _skips(items: Iterable[source.WalkItem]) -> list[source.SkippedSource]:
    """Filtra los elementos descartados de un pase de walk."""
    return [item for item in items if isinstance(item, source.SkippedSource)]


def test_walk_sources_returns_two_indexable_files_with_canonical_source_paths() -> None:
    """La fixture produce exactamente 2 entradas, con `source_path` POSIX prefijado (AC)."""
    items = source.walk_sources(FIXTURE_VAULT)

    assert {entry.source_path for entry in _entries(items)} == {
        "00-Resources/nota.md",
        "00-Resources/sub/carpeta/anidada.md",
    }
    assert _skips(items) == []


def test_walk_sources_excludes_dot_directories_f3() -> None:
    """`.oculto/ignorar.md` jamás aparece: los segmentos-punto exigen excluded_patterns (F3)."""
    items = source.walk_sources(FIXTURE_VAULT)

    assert all(".oculto" not in entry.source_path for entry in _entries(items))


def test_walk_sources_excludes_non_whitelisted_extensions() -> None:
    """`blob.bin` queda fuera de la whitelist sin abortar el pase (§Fuentes)."""
    items = source.walk_sources(FIXTURE_VAULT)

    assert all(entry.doc_kind != "bin" for entry in _entries(items))
    assert all("blob" not in entry.source_path for entry in _entries(items))


def test_include_patterns_alone_would_index_dot_paths_proving_excludes_are_mandatory_f3() -> (
    None
):
    """Control F3: SOLO con include patterns el globset real sí casa `.oculto/ignorar.md`.

    Este test fallaría si `excluded_patterns=["**/.*", "**/.git/**"]` dejara de
    aplicarse: con el matcher de solo-inclusión el archivo oculto se indexa.
    """
    include_only = PatternFilePathMatcher(
        included_patterns=list(source.WHITELIST_PATTERNS)
    )

    with_excludes = source.walk_sources(FIXTURE_VAULT)
    without_excludes = source.walk_sources(FIXTURE_VAULT, path_matcher=include_only)

    assert all(
        not entry.source_path.endswith(".oculto/ignorar.md")
        for entry in _entries(with_excludes)
    )
    assert any(
        entry.source_path == "00-Resources/.oculto/ignorar.md"
        for entry in _entries(without_excludes)
    )


def test_default_matcher_rejects_dot_paths_at_file_and_dir_level() -> None:
    """El matcher por defecto rechaza en tiempo de globset `.oculto/`, `.git/` y `.oculto-secreto.md`."""
    matcher = source.build_path_matcher()

    assert not matcher.is_dir_included(Path(".oculto"))
    assert not matcher.is_dir_included(Path(".git"))
    assert not matcher.is_file_included(Path(".oculto/ignorar.md"))
    assert not matcher.is_file_included(Path(".oculto-secreto.md"))
    assert not matcher.is_file_included(Path(".git/config.md"))
    assert matcher.is_dir_included(Path("sub"))
    assert matcher.is_file_included(Path("sub/carpeta/anidada.md"))


def test_walk_sources_raises_when_resource_root_is_missing() -> None:
    """Un vault sin `00-Resources/` es una instalación rota: fallo ruidoso, no vacío silencioso."""
    with pytest.raises(FileNotFoundError, match="00-Resources"):
        source.walk_sources(Path("/definitely/not/a/vault"))


# --- walk: skips tipados por archivo (F5) --------------------------------------


def test_walk_sources_skips_oversized_files_without_aborting_the_pass_f5(
    tmp_path: Path,
) -> None:
    """Un archivo sobre el umbral se reporta como `oversized` y el resto del pase sigue (F5).

    El umbral es inyectable para no generar ficheros de 100MB en el repo: la
    spec fija 100MB (DEFAULT_MAX_FILE_BYTES) y aquí un fichero de bytes basta.
    """
    recursos = tmp_path / citation.RESOURCES_DIR
    recursos.mkdir(parents=True)
    (recursos / "grande.md").write_text("x" * 100, encoding="utf-8")
    (recursos / "chica.md").write_text("x" * 10, encoding="utf-8")

    items = source.walk_sources(tmp_path, max_file_bytes=32)

    assert [(skip.source_path, skip.reason) for skip in _skips(items)] == [
        ("00-Resources/grande.md", source.SkipReason.OVERSIZED),
    ]
    assert [entry.source_path for entry in _entries(items)] == ["00-Resources/chica.md"]
    assert _skips(items)[0].detail  # el motivo lleva explicación, no solo el enum


def test_walk_sources_reports_broken_symlinks_with_reason_without_aborting_f5(
    tmp_path: Path,
) -> None:
    """Un symlink roto se emite como `broken_symlink` —el conector lo traga en silencio (F5)—."""
    recursos = tmp_path / citation.RESOURCES_DIR
    recursos.mkdir(parents=True)
    (recursos / "sana.md").write_text("# Sana\n\nprosa.\n", encoding="utf-8")
    try:
        (recursos / "roto.md").symlink_to(tmp_path / "objetivo_inexistente.md")
    except (OSError, NotImplementedError) as exc:  # pragma: no cover - FS sin symlinks
        pytest.skip(f"el filesystem no soporta symlinks: {exc}")

    items = source.walk_sources(tmp_path)

    assert [(skip.source_path, skip.reason) for skip in _skips(items)] == [
        ("00-Resources/roto.md", source.SkipReason.BROKEN_SYMLINK),
    ]
    assert [entry.source_path for entry in _entries(items)] == ["00-Resources/sana.md"]


def test_walk_sources_skips_unreadable_files_without_aborting_f5(
    tmp_path: Path,
) -> None:
    """Un archivo sin permiso de lectura se emite como `unreadable` y el pase completa (F5)."""
    recursos = tmp_path / citation.RESOURCES_DIR
    recursos.mkdir(parents=True)
    prohibido = recursos / "prohibido.md"
    prohibido.write_text("secreto\n", encoding="utf-8")
    legible = recursos / "legible.md"
    legible.write_text("# Legible\n\nprosa.\n", encoding="utf-8")
    os.chmod(prohibido, 0o000)
    if os.access(prohibido, os.R_OK):
        os.chmod(prohibido, 0o644)
        pytest.skip("el filesystem no enforce permisos de lectura (NTFS/fuseblk)")

    try:
        items = source.walk_sources(tmp_path)
    finally:
        os.chmod(prohibido, 0o644)

    assert [(skip.source_path, skip.reason) for skip in _skips(items)] == [
        ("00-Resources/prohibido.md", source.SkipReason.UNREADABLE),
    ]
    assert [entry.source_path for entry in _entries(items)] == [
        "00-Resources/legible.md"
    ]


def test_walk_sources_skips_pdfs_until_the_docling_parser_lands_t7(
    tmp_path: Path,
) -> None:
    """Los `.pdf` pasan la whitelist pero T5 no los parsea: skip con motivo `pdf_parser_pending`."""
    recursos = tmp_path / citation.RESOURCES_DIR
    recursos.mkdir(parents=True)
    (recursos / "articulo.pdf").write_bytes(b"%PDF-1.4 fake")
    (recursos / "notas.md").write_text("# Notas\n\nprosa.\n", encoding="utf-8")

    items = source.walk_sources(tmp_path)

    assert [(skip.source_path, skip.reason) for skip in _skips(items)] == [
        ("00-Resources/articulo.pdf", source.SkipReason.PDF_PARSER_PENDING),
    ]
    assert [entry.source_path for entry in _entries(items)] == ["00-Resources/notas.md"]


def test_default_max_file_bytes_is_the_spec_threshold_of_100_mb() -> None:
    """El umbral por defecto es el de la spec: >100MB → skipped (§Fuentes, F5)."""
    assert source.DEFAULT_MAX_FILE_BYTES == 100 * 1024 * 1024


# --- extract_text ---------------------------------------------------------------


def test_extract_text_reads_markdown_and_txt_directly(tmp_path: Path) -> None:
    """`.md`, `.markdown` y `.txt` se leen directamente (§Fuentes: lectura directa en T5)."""
    md = tmp_path / "una.md"
    md.write_text("# Una\n\ncontenido **md**.\n", encoding="utf-8")
    markdown = tmp_path / "dos.markdown"
    markdown.write_text("# Dos\n\ncontenido markdown.\n", encoding="utf-8")
    txt = tmp_path / "tres.txt"
    txt.write_text("texto plano sin jerarquía\n", encoding="utf-8")

    assert parsers.extract_text(md) == "# Una\n\ncontenido **md**.\n"
    assert parsers.extract_text(markdown) == "# Dos\n\ncontenido markdown.\n"
    assert parsers.extract_text(txt) == "texto plano sin jerarquía\n"


def test_extract_text_rejects_pdfs_until_t7(tmp_path: Path) -> None:
    """La rama PDF no existe en T5: error tipado, nunca una lectura cruda del binario."""
    pdf = tmp_path / "articulo.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    with pytest.raises(parsers.PdfParserPendingError, match="T7"):
        parsers.extract_text(pdf)


def test_extract_text_rejects_extensions_outside_the_whitelist(tmp_path: Path) -> None:
    """`doc_kind_for` de T4 manda: extensión fuera de {md,markdown,txt,pdf} lanza, nunca degrada."""
    binario = tmp_path / "blob.bin"
    binario.write_bytes(b"\x00\x01")

    with pytest.raises(citation.UnsupportedDocKindError, match="bin"):
        parsers.extract_text(binario)


# --- chunk_document -------------------------------------------------------------


def test_chunk_document_respects_the_byte_budget_and_overlap_d11() -> None:
    """Chunks ≤1536 BYTES, solape ≤192 BYTES aplicado y sin contenido perdido (D11).

    El splitter corta limpio en bordes de heading (solo cae el separador, sin
    solape); dentro de prosa sí aplica el solape pedido. Por eso se afirma el
    PRESUPUESTO —ningún solape supera 192 bytes y alguno existe— y que los
    huecos entre chunks son únicamente separadores en blanco.
    """
    text = (FIXTURE_VAULT / citation.RESOURCES_DIR / "nota.md").read_text(
        encoding="utf-8"
    )

    chunks = parsers.chunk_document(text, "nota.md")

    assert len(chunks) >= 3  # la fixture debe producir «varios» chunks
    for chunk in chunks:
        assert len(chunk.text.encode("utf-8")) <= 1536
    overlaps: list[int] = []
    for previous, current in itertools.pairwise(chunks):
        if current.char_start <= previous.char_end:
            overlaps.append(
                len(text[current.char_start : previous.char_end].encode("utf-8"))
            )
        else:
            gap = text[previous.char_end : current.char_start]
            assert gap.strip() == ""  # corte limpio en heading: solo cae el separador
    assert overlaps, "el chunk_overlap debe producir solape real entre chunks"
    assert max(overlaps) <= 192  # y jamás exceder el presupuesto de solape (bytes)


def test_every_chunk_carries_complete_non_null_citation_metadata() -> None:
    """`source_path`, `char_start`, `char_end`, `doc_kind` y `model` no nulos en todo chunk (AC)."""
    text = (FIXTURE_VAULT / citation.RESOURCES_DIR / "nota.md").read_text(
        encoding="utf-8"
    )

    chunks = parsers.chunk_document(text, "nota.md")

    assert chunks
    for chunk in chunks:
        assert chunk.source_path == "00-Resources/nota.md"  # POSIX, prefijado
        assert chunk.doc_kind == "md"
        assert isinstance(chunk.char_start, int)
        assert isinstance(chunk.char_end, int)
        assert chunk.model == citation.model_id() == flow_config.DEFAULT_EMBEDDING_MODEL


def test_heading_is_present_and_nullable_per_chunk_d13() -> None:
    """`heading` siempre presente: el último `##` previo en md; `None` en un .txt sin jerarquía."""
    text = (FIXTURE_VAULT / citation.RESOURCES_DIR / "nota.md").read_text(
        encoding="utf-8"
    )
    chunks = parsers.chunk_document(text, "nota.md")
    headings = [chunk.heading for chunk in chunks]

    assert any(heading is not None for heading in headings)
    assert all(
        heading is None or isinstance(heading, str) for heading in headings
    )  # presente y nullable, jamás "" sintético

    plano = "Primera línea de texto plano.\nSegunda línea también plana.\n"
    txt_chunks = parsers.chunk_document(plano, "plano.txt")

    assert txt_chunks, "un .txt debe producir chunks aunque no tenga headings"
    for chunk in txt_chunks:
        assert chunk.heading is None  # D13: nullable explícito, campo presente
        assert chunk.doc_kind == "txt"


def test_chunk_document_returns_no_chunks_for_empty_text() -> None:
    """Texto vacío → lista vacía: nada que citar, nada que validar."""
    assert parsers.chunk_document("", "vacia.md") == []


def test_chunk_document_normalizes_source_path_before_citing() -> None:
    """La ruta citada se normaliza con el dominio de T4: sin prefijo, sin `./`, anidamiento intacto."""
    text = "# Título\n\nprosa.\n"

    chunks = parsers.chunk_document(text, "./sub/archivo.markdown")

    assert {chunk.source_path for chunk in chunks} == {
        "00-Resources/sub/archivo.markdown"
    }
    assert {chunk.doc_kind for chunk in chunks} == {"markdown"}


# --- camino vertical end-to-end (T5) -------------------------------------------


def test_end_to_end_walk_extract_chunk_preserves_nesting_and_slices() -> None:
    """Walk → extract → chunk sobre la fixture: anidamiento conservado e identidad F1 por chunk."""
    items = source.walk_sources(FIXTURE_VAULT)
    entries = _entries(items)

    assert len(entries) == 2
    total_chunks = 0
    for entry in entries:
        text = parsers.extract_text(entry.path)
        for chunk in parsers.chunk_document(text, entry.source_path):
            total_chunks += 1
            assert citation.verify_slice_identity(
                text, chunk.char_start, chunk.char_end, chunk.text
            ), (
                f"identidad F1 rota en {chunk.source_path} [{chunk.char_start}, {chunk.char_end})"
            )

    assert total_chunks >= 4  # la nota raíz da varios chunks y la anidada al menos uno
    assert {entry.source_path for entry in entries} == {
        "00-Resources/nota.md",
        "00-Resources/sub/carpeta/anidada.md",  # anidamiento libre preservado (D9.1)
    }
