"""T7: fixtures ADVERSAS del presupuesto — ≤1600 tokens en TODAS (plan §6, AC de CP-C).

Fuentes de verdad:

* tasks/todo.md T7 + tasks/plan.md §6 T7 — fixtures adversas (unicode CJK/emoji,
  query >10 000 chars → `VALIDATION_ERROR` vía el ADAPTADOR, chunk de 1536
  bytes, PDF con tablas, chunk multibyte); payload de `search` ≤1600 tokens en
  todas ellas; con corte ⇒ `truncated: true` y orden por score respetado.
* specs/spec-mcp-server.md §Presupuesto de tokens — techo 1600 sobre la suma
  estimada (chars/4 + 25 por resultado); `rag_status` <200 lo cubre T4
  (`test_mcp_rag_status.py`, ya verde).
* docs/BACKLOG.md criterio 4 — ≤2000 tokens/consulta incluyendo contexto (el techo
  1600 deja ≥400 de margen para pregunta + respuesta).

Decisiones de test, documentadas a propósito (convención de T2/T6):

* **Indexación SIEMPRE en subproceso** con `TEPOCHCALLI_VAULT_ROOT` propio
  (mismo patrón e indexador compartido que T2 — hoy
  `support.mcp_server.index_vault`, extracción R4 de T8): el environment
  global de cocoindex no admite dos vaults en el proceso padre.
* **Reutilización de T2**: `IndexedVault`, `_search` y `_backend_on` se
  importan del módulo de T2; la COMPOSICIÓN del vault adverso vive en el
  `conftest.py` de este directorio como fixture de SESIÓN (P0-1): T7 y T6
  comparten UNA indexación del mismo contenido en vez de dos.
* **Premisas de fixture vía `parsers`** (chunker real de Phase 1, sin red): el
  tamaño de chunk (1536 BYTES, D11), la multibyte-idad y la tabla del PDF son
  propiedades deterministas de `parsers.extract_text`/`chunk_document`; lo que
  `search` devuelve sobre las fuentes MD se verifica aparte CON retrieval real
  (`path_filter` para anclar cada fixture). El PDF se prueba además a nivel
  handler (budget post-retrieval) Y con retrieval real sobre el índice
  (F-T7-2 cerrado: `app.index_file` ya delega en `parsers.extract_text`).
* **Cero aserciones de reloj** (regla anti-flake T3): aquí SOLO se miden
  tokens — la latencia vive en `tests/benchmarks/bench_search.py` (medición
  local, jamás en la suite de corrección).

Hallazgos de T7 que este módulo deja por escrito (medidos, no estimados):

* **F-T7-1 — la envoltura del JSON no está en la fórmula de plan §5.** El gate
  del contrato (Σ `estimate_tokens(text)` ≤ 1600, la «suma estimada» de
  spec §Presupuesto que `apply_budget` garantiza) se cumple en TODAS las
  fixtures; pero el JSON completo (`content[0].text`) suma **≈ +150 tokens** de
  envoltura — query echo + claves JSON + paths — que plan §5 no contabiliza.
  Peor caso medido en este módulo: contract **1590** → serializado **1740**.
  Por eso `_assert_within_budget` hace gate del contrato, ACOTA el exceso de la
  envoltura (≤200 tokens) y PUBLICA ambos números en cada fallo: recortar más
  exigiría cambiar la fórmula congelada de plan §5 (decisión de docs, vedada
  aquí — se propone al lead para T10).
* **F-T7-2 — el flow NO indexaba PDFs (CERRADO con este fix).** `app.index_file`
  (flow/) leía TODO con `read_text(utf-8)`; un PDF fallaba con `UnicodeDecodeError`
  y el fallo por fichero se ABSORBE en `skipped` (rc=0, sin abortar), así que
  un vault con PDFs los indexa en silencio… nunca. La rama Docling
  (`parsers.extract_text`) existe y funciona (lo prueba este módulo) pero
  NUNCA se enganchó en `index_file` — los tests de Phase 1 llaman a `parsers`
  directamente y no lo vieron. Prueba reproducida aquí con traceback
  (`'utf-8' codec can't decode byte 0xe2 in position 10'` sobre el header del
  PDF). **Fix aplicado:** `index_file` delega en `parsers.extract_text(file_path)`
  (vía `asyncio.to_thread`: Docling corre en un thread y no satura el loop del
  environment), el PDF indexa de verdad y este módulo lo prueba de punta a
  punta: filas con identidad F1 sobre el markdown extraído + `search` real con
  `offsets_ref == "extract"`.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest
from tepochcalli_flow import citation, parsers
from tepochcalli_flow.config import DEFAULT_EMBEDDING_MODEL
from tepochcalli_flow.layout import DB_RELPATH, TABLE_NAME
from tepochcalli_flow.parsers import DocumentChunk
from tepochcalli_flow.ports import CitedChunk
from tepochcalli_mcp import budget
from tepochcalli_mcp.server import _VaultSearchBackend
from tepochcalli_mcp.tools.search import SearchBackend
from test_mcp_search import (
    IndexedVault,
    _backend_on,
    _search,
)

# Mismo filtro que `test_pdf.py` (TD-9): los DeprecationWarnings INTERNOS de
# Docling al usarse su propia API default no son de este código ni de los
# nuestros. Scope de módulo (igual que allí) para preservar la regla de la
# suite: exactamente UN warning — el FutureWarning esperado de TD-9.
pytestmark = [
    pytest.mark.filterwarnings("ignore:`force_full_page_ocr` is deprecated:DeprecationWarning"),
    pytest.mark.filterwarnings(
        "ignore:This field is deprecated. Use `generate_page_images=True`:DeprecationWarning"
    ),
]

TABLE_PDF = Path(__file__).parents[1] / "fixtures" / "pdf" / "tablas_t7.pdf"
"""PDF adverso CON TABLA rejillada (regenerable: `gen_fixture_pdf.py <destino> --tabla`)."""

DENSE_ANCHOR = "zarpatoria"
"""Término léxico único del fixture denso — la consulta que fuerza el corte."""

DENSE_SECTIONS = 8
"""Secciones del fixture denso: ≥8 chunks casi al tope de 1536 bytes."""

CJK_QUERY = "東京の天気とメトリクスの観測 🚀"
"""Fixture adversa unicode: consulta CJK + emoji."""

EMOJI_LATIN_QUERY = "métricas 📊 de cobertura 🚀 pediatría"
"""Fixture adversa emoji embebidos en texto latin-1."""

DENSE_QUERY = f"{DENSE_ANCHOR} segmentación de texto denso"
"""Consulta sobre el fixture denso (con `path_filter` ancla, es determinista)."""

PDF_QUERY = "presupuesto de latencia embed ensamblado ipc"
"""Consulta cuyo vocabulario vive en la TABLA del PDF adverso."""

GOLDEN_QUERY = "whitelist de extensiones indexables"
"""Consulta dorada corta — el caso base dentro del mismo payload."""

CONTRACT_CEILING = budget.PAYLOAD_TOKEN_CEILING
"""Techo del contrato: 1600 tokens (plan §5, criterio 4)."""

WRAPPER_TOKENS_BOUND = 200
"""Cota diagnosticada (T7) para el exceso del JSON completo sobre plan §5.

Medido en este módulo: ≤150 tokens (query echo corta + claves JSON + paths);
200 deja holgura y convierte cualquier ensanchamiento de la envoltura (p. ej.
scores float más largos) en un fallo VISIBLE. NO es un techo del contrato: el
1600 vive sobre la fórmula de plan §5 — ver hallazgo F-T7-1 del docstring.
"""

_DENSE_SENTENCES = (
    f"La segmentación de {DENSE_ANCHOR} mide cuántos bytes caben antes de partir el texto.",
    "Cada oración se repite con variación mínima para que el separador llene chunks completos.",
    "El presupuesto de mil seiscientos tokens obliga a descartar los resultados de menor score.",
    "Esta prosa deliberadamente larga empuja al RecursiveSplitter contra su tope de bytes.",
    f"Nota de método: {DENSE_ANCHOR} es un vocablo único que ninguna otra fuente contiene.",
    "Los offsets de carácter se miden sobre el markdown crudo, igual que en cualquier otra nota.",
    "La repetición es determinista: ni el orden de las secciones ni su número cambian.",
    "Un chunk de mil quinientos bytes cuesta trescientos setenta y cinco tokens más la citación.",
)

_CJK_SENTENCES = (
    "東京の天気は曇りで、観測メトリクスは安定しています。",
    "中国語の分词と検索は多字节文字の慎重な処理を必要とします。",
    "データの前処理は重要です 🚀 絵文字も含む本文をそのまま索引化する。",
    "检索预算以字符计数为准，而不是字节数 📊。",
    "気象観測の記録は毎日同じ形式で保存されます。",
    "多字节文本的成本按字符估算，emoji 也占用一个字符位置。",
)


def _dense_content() -> str:
    """Prosa densa (~30 KB, 8 secciones) para chunks cerca del tope de 1536 bytes."""
    sections = [f"# Documento denso sobre {DENSE_ANCHOR}\n"]
    for index in range(DENSE_SECTIONS):
        body = " ".join(
            _DENSE_SENTENCES[(index + offset) % len(_DENSE_SENTENCES)] for offset in range(32)
        )
        sections.append(f"\n## Sección {index} de {DENSE_ANCHOR}\n\n{body}\n")
    return "".join(sections)


def _cjk_content() -> str:
    """CJK denso + emoji (~4 500 chars ≈ 13 KB): chunks multibyte, bytes ≫ chars."""
    sections = ["# 東京の天気観測ノート\n"]
    for index in range(6):
        body = " ".join(
            _CJK_SENTENCES[(index + offset) % len(_CJK_SENTENCES)] for offset in range(8)
        )
        sections.append(f"\n## 観測 {index}\n\n{body}\n")
    return "".join(sections)


# El vault adverso y su builder viven en `conftest.py` de este directorio
# (fixture de SESIÓN compartido con `test_mcp_token_budget` — P0-1): aquí solo
# se consume. El PDF se COPIA y se INDEXA de verdad allí (fix de F-T7-2:
# `index_file` delega en `parsers.extract_text`, Docling corre dentro del
# subproceso): su presencia en el índice es lo que hace firme el test de
# búsqueda sobre el PDF indexado.


@pytest.fixture(scope="module")
def backend(adversarial_vault: IndexedVault) -> Iterator[_VaultSearchBackend]:
    """Backend real sobre el vault adverso — PRIMED (patrón M3 de T2, `_backend_on`)."""
    yield from _backend_on(adversarial_vault)


@pytest.fixture(scope="module")
def pdf_markdown() -> str:
    """Texto del PDF tabular extraído por markitdown (rama real de `parsers`)."""
    return parsers.extract_text(TABLE_PDF)


@pytest.fixture(scope="module")
def pdf_chunks(pdf_markdown: str) -> list[DocumentChunk]:
    """Chunks REALES del PDF tabular (`chunk_document` sobre su markdown, F1 intacta)."""
    return parsers.chunk_document(pdf_markdown, "00-resources/tablas.pdf")


def _read_pdf_rows(vault: Path) -> list[dict[str, object]]:
    """Filas de `tablas.pdf` en LanceDB — solo lectura (patrón `_count_chunks` de T2)."""
    import lancedb

    async def _go() -> list[dict[str, object]]:
        db = await lancedb.connect_async(str(vault / DB_RELPATH))
        try:
            table = await db.open_table(TABLE_NAME)
            arrow = await table.to_arrow()
        finally:
            db.close()
        return [row for row in arrow.to_pylist() if row["source_path"] == "00-resources/tablas.pdf"]

    return asyncio.run(_go())


class _StaticBackend:
    """Doble mínimo del puerto `SearchBackend` con chunks REALES dados de alta.

    Patrón sancionado por T2 para presupuesto: `apply_budget` corre DESPUÉS del
    retrieval, así que entregar los `DocumentChunk` reales del PDF convertidos
    al puerto `CitedChunk` ejercita handler y budget idénticos a producción —
    solo cambia quién elige los chunks.
    """

    def __init__(self, chunks: Sequence[CitedChunk]) -> None:
        """Guarda los chunks que `cited_chunks` devolverá (hasta `top_k`)."""
        self._chunks = list(chunks)

    @property
    def expected_model(self) -> str:
        """Modelo configurado — el mismo que las filas del vault real."""
        return DEFAULT_EMBEDDING_MODEL

    async def index_models(self) -> set[str]:
        """Índice «con modelo conocido»: el default, igual que el vault dorado."""
        return {DEFAULT_EMBEDDING_MODEL}

    async def cited_chunks(
        self, query: str, top_k: int, path_filter: str | None
    ) -> list[CitedChunk]:
        """Los primeros `top_k` chunks del fixture, en orden (scores ya descendentes)."""
        del query, path_filter  # el fixture no busca: entrega su lista fija
        return self._chunks[:top_k]


def _cited_chunks(chunks: Sequence[DocumentChunk]) -> list[CitedChunk]:
    """`DocumentChunk` real → puerto `CitedChunk` con score sintético descendente (patrón T2)."""
    return [
        CitedChunk(
            text=chunk.text,
            source_path=chunk.source_path,
            heading=chunk.heading,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
            score=1.0 - index * 0.01,
            offsets_ref=citation.offsets_ref_for(chunk.doc_kind),
        )
        for index, chunk in enumerate(chunks)
    ]


def _assert_within_budget(payload: dict[str, object]) -> None:
    """≤1600 por la fórmula del contrato + envoltura acotada y PUBLICADA (F-T7-1).

    * `contract` = Σ `estimate_tokens(text)` sobre los resultados — la «suma
      estimada» de spec §Presupuesto que `apply_budget` garantiza: ES el gate
      de 1600, y es sobre el que plan §5 define el techo del payload.
    * `serialized` = `estimate_tokens` del JSON COMPLETO (`ensure_ascii=False`,
      idéntico a `content[0].text`): su EXCESO sobre el contrato (query echo +
      claves JSON + paths, ≈150 medidos) se acota a `WRAPPER_TOKENS_BOUND` y
      AMBOS números viajan en el mensaje de cualquier fallo — ver hallazgo
      F-T7-1 del docstring del módulo antes de tocar este gate.
    """
    assert "error" not in payload, payload
    results = payload["results"]
    assert isinstance(results, list)
    contract = sum(budget.estimate_tokens(str(result["text"])) for result in results)
    scores = [float(result["score"]) for result in results]
    serialized = budget.estimate_tokens(json.dumps(payload, ensure_ascii=False))
    assert contract <= CONTRACT_CEILING, (
        f"coste de contrato {contract} > {CONTRACT_CEILING} (serialized={serialized})"
    )
    assert 0 <= serialized - contract <= WRAPPER_TOKENS_BOUND, (
        f"envoltura {serialized - contract} tokens fuera de cota "
        f"(contract={contract}, serialized={serialized})"
    )
    assert scores == sorted(scores, reverse=True), scores


# --- premisas de fixture: el chunker de Phase 1 produce lo que el AC pide -------------


def test_dense_fixture_yields_near_cap_chunks_of_at_most_1536_bytes() -> None:
    """Chunk de 1536 bytes (D11): ≥8 chunks, alguno cerca del tope, NUNCA >1536.

    El splitter empaqueta en fronteras de oración, así que los chunks quedan
    CERCA del tope (no exactos en 1536); la premisa que importa para el corte
    es la última: 8 chunks así no caben en 1600, luego `top_k=8` SIEMPRE corta.
    """
    chunks = parsers.chunk_document(_dense_content(), "00-resources/denso.md")
    sizes = [len(chunk.text.encode("utf-8")) for chunk in chunks]

    assert len(sizes) >= 8, f"el fixture denso necesita ≥8 chunks para forzar corte: {len(sizes)}"
    assert max(sizes) >= 1400, f"ningún chunk cerca del tope de 1536: {sizes}"
    assert max(sizes) <= 1536, f"tope D11 roto: {max(sizes)} bytes"
    cheapest = min(sizes) // 4 + budget.CITATION_OVERHEAD_TOKENS
    assert 8 * cheapest > CONTRACT_CEILING, (
        f"8 chunks de {cheapest} tokens no superarían 1600: el corte dejaría de estar garantizado "
        f"(sizes={sizes})"
    )


def test_cjk_fixture_yields_multibyte_chunks_where_bytes_far_outweigh_chars() -> None:
    """Chunk multibyte: bytes ≥ 2× chars en al menos un chunk del fixture CJK."""
    chunks = parsers.chunk_document(_cjk_content(), "00-resources/cjk.md")

    multibyte = [
        chunk
        for chunk in chunks
        if len(chunk.text.encode("utf-8")) >= 900
        and len(chunk.text.encode("utf-8")) >= 2 * len(chunk.text)
    ]
    assert multibyte, "ningún chunk CJK es multibyte de verdad (bytes ≥ 2× chars)"


# --- search real sobre cada fixture adversa ------------------------------------------


def test_cjk_emoji_query_returns_results_within_both_budget_readings(
    backend: SearchBackend,
) -> None:
    """Consulta CJK+emoji: responde sin error, redonda por JSON y ≤1600."""
    payload = _search(backend, CJK_QUERY)

    assert payload.get("error") is None
    round_trip = json.loads(json.dumps(payload, ensure_ascii=False))
    assert round_trip == payload
    _assert_within_budget(payload)


def test_emoji_latin_mixed_query_stays_within_budget(backend: SearchBackend) -> None:
    """Emoji incrustados en latin-1: el estimador cuenta CHARS, no bytes (fixture adversa)."""
    _assert_within_budget(_search(backend, EMOJI_LATIN_QUERY))


def test_dense_cut_is_flagged_truncated_with_score_order_and_full_results(
    backend: SearchBackend,
) -> None:
    """El fixture denso con `top_k=8` excede 1600 ⇒ corte, `truncated` y orden intactos."""
    payload = _search(backend, DENSE_QUERY, 8, path_filter="00-resources/denso.md")

    results = payload["results"]
    assert payload["truncated"] is True, "8 chunks de ~400 tokens no caben en 1600"
    assert 0 < len(results) < 8
    assert any(len(str(result["text"]).encode("utf-8")) >= 1400 for result in results), (
        "la premisa del chunk de ~1536 bytes debe sobrevivir al retrieval"
    )
    _assert_within_budget(payload)


def test_multibyte_chunks_survive_retrieval_within_budget(backend: SearchBackend) -> None:
    """Retrieval anclado al fixture CJK: chunks multibyte reales dentro del techo."""
    payload = _search(backend, CJK_QUERY, 8, path_filter="00-resources/cjk.md")

    results = payload["results"]
    assert results, "path_filter cjk.md debe devolver chunks"
    assert all(str(result["source_path"]).endswith("cjk.md") for result in results)
    assert any(
        len(str(result["text"]).encode("utf-8")) >= 900
        and len(str(result["text"]).encode("utf-8")) >= 2 * len(str(result["text"]))
        for result in results
    ), "el retrieval debe traer un chunk multibyte de verdad"
    _assert_within_budget(payload)


def test_pdf_with_table_is_extracted_as_markdown_table_by_markitdown(
    pdf_markdown: str,
) -> None:
    """Premisa «PDF con tablas»: markitdown emite la rejilla como TABLA markdown.

    ≥10 líneas que empiezan por `|` (13 filas + separador de la rejilla de
    `gen_fixture_pdf.py --tabla`) con sus celdas: la tabla SE EXTRAE.
    """
    pipe_lines = [line for line in pdf_markdown.splitlines() if line.strip().startswith("|")]

    assert len(pipe_lines) >= 10, f"markitdown no emitió tabla markdown: {pdf_markdown!r}"
    assert "Etapa" in pdf_markdown and "120 ms" in pdf_markdown


def test_pdf_table_chunks_flow_through_the_real_handler_within_budget(
    pdf_chunks: list[DocumentChunk],
) -> None:
    """«PDF con tablas» en el handler REAL: citas sobre `tablas.pdf`, ≤1600, D11 intacto.

    Los chunks REALES del PDF (markitdown → `chunk_document`) entran al handler
    a través del puerto `SearchBackend` con scores sintéticos (patrón T2 de
    presupuesto): el corte es POST-retrieval, así que el budget ejercitado es
    el de producción — el retrieval REAL sobre el mismo PDF indexado lo cubre
    `test_search_over_the_indexed_pdf_returns_its_table_chunks`.
    """
    backend = _StaticBackend(_cited_chunks(pdf_chunks))

    payload = _search(backend, PDF_QUERY, 8)

    results = payload["results"]
    assert results, "el fixture PDF debe producir chunks"
    assert all(str(result["source_path"]) == "00-resources/tablas.pdf" for result in results)
    assert any("|" in str(result["text"]) for result in results), (
        "ningún chunk entrega contenido de la tabla markdown"
    )
    sizes = [len(chunk.text.encode("utf-8")) for chunk in pdf_chunks]
    assert max(sizes) <= 1536, f"tope D11 también rige el markdown del PDF: {sizes}"
    _assert_within_budget(payload)


def test_search_over_the_indexed_pdf_returns_its_table_chunks(
    backend: SearchBackend,
) -> None:
    """AC end-to-end «PDF con tablas» vía SEARCH: F-T7-2 cerrado, el PDF SÍ se indexa."""
    payload = _search(backend, PDF_QUERY, 8, path_filter="00-resources/tablas.pdf")

    assert payload["results"], "path_filter tablas.pdf debe devolver chunks del PDF"
    assert all(
        str(result["source_path"]) == "00-resources/tablas.pdf" for result in payload["results"]
    )
    assert all(
        result["offsets_ref"] == citation.OFFSETS_REF_EXTRACT for result in payload["results"]
    ), "los offsets de un PDF citan el markdown extraído (decisión T7 congelada)"
    _assert_within_budget(payload)


def test_pdf_is_indexed_as_rows_whose_offsets_cite_the_extracted_markdown(
    adversarial_vault: IndexedVault,
) -> None:
    """AC de aceptación (F-T7-2 cerrado): el PDF dentro de `00-resources/` queda INDEXADO.

    Cada fila de `tablas.pdf` existe en la tabla con `doc_kind="pdf"` y su
    identidad F1 se cumple sobre el texto que markitdown extrajo — nunca sobre
    el binario (D50). El buscado va aparte, en
    `test_search_over_the_indexed_pdf_returns_its_table_chunks`.
    """
    rows = _read_pdf_rows(adversarial_vault.vault)

    assert rows, "el PDF debe producir filas en la tabla chunks (F-T7-2)"
    markdown = parsers.extract_text(TABLE_PDF)
    for row in rows:
        assert row["doc_kind"] == "pdf"
        assert citation.verify_slice_identity(
            markdown, int(row["char_start"]), int(row["char_end"]), str(row["text"])
        ), f"identidad F1 rota en [{row['char_start']}, {row['char_end']})"


def test_short_golden_query_stays_within_budget(backend: SearchBackend) -> None:
    """El caso BASE (consulta corta sobre la dorada) también queda bajo el techo."""
    _assert_within_budget(_search(backend, GOLDEN_QUERY))


def test_oversized_query_is_rejected_by_the_adapter_with_a_small_error_payload(
    backend: SearchBackend,
) -> None:
    """Query >10 000 chars: `VALIDATION_ERROR` del ADAPTADOR (reader) y payload de error ≤1600."""
    payload = _search(backend, "x" * 10_001)

    assert payload["error"]["code"] == "VALIDATION_ERROR"
    serialized = budget.estimate_tokens(json.dumps(payload, ensure_ascii=False))
    assert serialized <= CONTRACT_CEILING, serialized


@pytest.mark.parametrize(
    ("label", "query", "top_k", "path_filter"),
    [
        ("cjk_emoji", CJK_QUERY, 5, None),
        ("emoji_latin", EMOJI_LATIN_QUERY, 5, None),
        ("denso_corte", DENSE_QUERY, 8, "00-resources/denso.md"),
        ("cjk_multibyte", CJK_QUERY, 8, "00-resources/cjk.md"),
        ("dorada", GOLDEN_QUERY, 5, None),
        ("top_k_maximo", "métricas de cobertura", 20, None),
    ],
)
def test_every_adversarial_payload_stays_under_1600_tokens(
    backend: SearchBackend, label: str, query: str, top_k: int, path_filter: str | None
) -> None:
    """AC: ≤1600 tokens EN TODAS las fixtures — contrato gateado + envoltura publicada.

    El caso PDF tabular no está aquí: su presupuesto lo cubren
    `test_pdf_table_chunks_flow_through_the_real_handler…` (handler) y
    `test_search_over_the_indexed_pdf_returns_its_table_chunks` (retrieval real).
    """
    payload = _search(backend, query, top_k, path_filter=path_filter)

    assert list(payload) == ["query", "took_ms", "truncated", "results"], label
    _assert_within_budget(payload)
