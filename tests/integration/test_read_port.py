"""T9: puerto de lectura `ChunkReader` + adaptador LanceDB — fila queryable (M4).

Fuentes de verdad:

* specs/spec-mcp-server.md §search — forma CONGELADA del resultado
  `{text, source_path, heading, char_start, char_end, score}`; `heading`
  nullable (D13) y SIEMPRE presente; `path_filter` como glob relativo al vault
  con la traducción `*`→`%` a `LIKE`; `score` ∈ [0,1] híbrido ANN+FTS
  descendente; campos extensiones solo aditivas (Hyrum, ADR-005).
* specs/spec-rag-engine.md §Target LanceDB + índices — la tabla `chunks` con
  ANN sobre `embedding` + FTS sobre `text` (ambos declarados por T6) es el
  almacén detrás del puerto (§Escape hatch de migración de motor).
* specs/adr/adr-005-mcp-ports-adapters.md — «la cita precisa es estructural,
  no opcional»: el puerto devuelve SIEMPRE los seis campos.
* tasks/todo.md → T9 AC — protocolo sin deps de LanceDB/CocoIndex, score
  normalizado, `path_filter` glob, verificador CLI, ANN+FTS <500ms p95
  (preliminar).

Decisiones de test, documentadas a propósito:

* **El vault indexado se construye en SUBPROCESO.** `app.update_blocking()`
  usa el environment global de cocoindex: una segunda llamada EN EL MISMO
  proceso reutiliza el environment de la primera y escribe en el vault
  equivocado (sonda empírica T9, confirmada). El fixture lanza el update en
  un `subprocess` con `TEPOCHCALLI_VAULT_ROOT` propio —aislamiento real— y
  con la red off cuando el cache resuelto ya contiene el modelo
  (`model_cache.offline_env`: `HF_HOME` externo > spike T1 si existe >
  `~/.cache/huggingface`, symlink dentro del vault; en frío se permite la
  única descarga que CI persiste con `actions/cache`, T11).
* **El lector solo LEE.** El test de verificador snapshot-ea
  `<vault>/.tepochcalli/db/` antes/después de la corrida del CLI y afirma
  byte a byte (mtime_ns + size) que nada cambió.
* **Latencia PRELIMINAR.** 10 consultas sobre el corpus dorado (~7 chunks):
  assertion de humo, no bench — el bench 10k/1k es Phase 6 (T10).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, get_type_hints

import pytest
from model_cache import link_model_cache, offline_env, resolve_model_cache
from sentence_transformers import SentenceTransformer
from tepochcalli_flow import app as flow_app
from tepochcalli_flow import citation
from tepochcalli_flow import config as flow_config
from tepochcalli_flow.adapters import lancedb_reader
from tepochcalli_flow.adapters.lancedb_reader import (
    LanceDBChunkReader,
    path_filter_to_like_predicate,
)
from tepochcalli_flow.layout import DB_RELPATH
from tepochcalli_flow.ports import ChunkReader, CitedChunk

FIXTURE_VAULT = Path(__file__).parents[1] / "fixtures" / "vault_markdown"

CONTRACT_FIELDS = [
    "text",
    "source_path",
    "heading",
    "char_start",
    "char_end",
    "score",
    "offsets_ref",
]

PLAIN_TXT_CONTENT = (
    "Texto plano de prueba sin jerarquía de headings.\n\n"
    "Segundo párrafo: un archivo sin ningún heading padre debe producir chunks "
    "cuyo campo `heading` exista en el resultado con valor null —nunca una "
    "cadena vacía— según D13 en spec-rag-engine.md §Target LanceDB.\n"
)

UNDERSCORE_CONTENT = (
    "# Nota con guion bajo\n\n"
    "Este archivo se llama `con_guion_bajo.md`: su ruta literal contiene un "
    "guion bajo, que un LIKE sin escapar confundiría con el comodín de un "
    "solo carácter. El glob exacto debe casar SOLO con esta nota.\n"
)

UPDATE_SCRIPT = "from tepochcalli_flow.app import app; app.update_blocking()"

GOLDEN_QUERIES = [
    "whitelist de extensiones indexables",
    "citas con offsets de carácter exactos",
    "anidamiento libre de carpetas",
    "archivos ocultos y privacidad",
    "parseo de markdown y texto plano",
    "heading nulo en archivo sin jerarquía",
    "guion bajo en el nombre del archivo",
    "solape entre chunks consecutivos",
    "qué formatos indexa el flujo",
    "derivación de metadatos por chunk",
]
"""10 consultas fijas para la medición preliminar de latencia (determinista)."""


@dataclass(frozen=True)
class IndexedVault:
    """Vault temporal T9 ya indexado por el flow real (subproceso)."""

    vault: Path
    """Raíz del vault temporal."""

    model_cache: Path
    """Cache de modelo al que apunta el symlink `.tepochcalli/models`."""


@pytest.fixture(scope="module")
def indexed_vault(tmp_path_factory: pytest.TempPathFactory) -> Iterator[IndexedVault]:
    """Vault temporal con la fixture dorada + plano.txt + guion_bajo, indexado.

    El update corre en subproceso (ver docstring del módulo): environment de
    cocoindex aislado, modelo desde el cache que resuelve `model_cache`
    (externo o spike) y red off cuando ese cache ya lo contiene.
    """
    vault = tmp_path_factory.mktemp("vault-t9")
    shutil.copytree(FIXTURE_VAULT, vault, dirs_exist_ok=True)
    (vault / citation.RESOURCES_DIR / "plano.txt").write_text(PLAIN_TXT_CONTENT, encoding="utf-8")
    (vault / citation.RESOURCES_DIR / "con_guion_bajo.md").write_text(
        UNDERSCORE_CONTENT, encoding="utf-8"
    )

    cache = resolve_model_cache()
    models_link = link_model_cache(vault, cache)

    env = {
        **os.environ,
        flow_app.VAULT_ROOT_ENV: str(vault),
        "HF_HOME": str(models_link),
        "SENTENCE_TRANSFORMERS_HOME": str(models_link),
        **offline_env(cache),
    }
    env.pop("COCOINDEX_DB", None)
    proc = subprocess.run(
        [sys.executable, "-c", UPDATE_SCRIPT],
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert proc.returncode == 0, (
        f"update_blocking() falló en subproceso:\n{proc.stdout}\n{proc.stderr}"
    )
    assert (vault / DB_RELPATH).exists(), "el update no materializó LanceDB en el vault"
    yield IndexedVault(vault=vault, model_cache=models_link)


@pytest.fixture(scope="module")
def reader(indexed_vault: IndexedVault) -> LanceDBChunkReader:
    """Adaptador real sobre el vault indexado, con el embedder MiniLM configurado."""
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setenv("HF_HOME", str(indexed_vault.model_cache))
        monkeypatch.setenv("SENTENCE_TRANSFORMERS_HOME", str(indexed_vault.model_cache))
        monkeypatch.setenv("HF_HUB_OFFLINE", "1")
        model = SentenceTransformer(flow_config.DEFAULT_EMBEDDING_MODEL, device="cpu")
        yield LanceDBChunkReader(
            db_uri=indexed_vault.vault / DB_RELPATH,
            embed=lambda query: model.encode(query).tolist(),
        )
    finally:
        monkeypatch.undo()


# --- contrato congelado del resultado (spec-mcp-server §search) ----------------


def test_chunk_result_shape_is_the_frozen_contract() -> None:
    """`CitedChunk` expone EXACTAMENTE los 6 campos congelados, en orden de spec."""
    assert [field.name for field in fields(CitedChunk)] == CONTRACT_FIELDS


def test_chunk_result_heading_is_nullable_and_the_rest_required() -> None:
    """D13 en el resultado: `heading: str | None`; los otros cinco, no nulos."""
    hints = get_type_hints(CitedChunk)
    assert hints["heading"] == str | None
    for name in CONTRACT_FIELDS:
        if name != "heading":
            assert hints[name] is not Any, f"{name} debe ser requerido y no anotado Any"


def test_lancedb_adapter_satisfies_the_port() -> None:
    """El adaptador LanceDB implementa el protocolo `ChunkReader` (structural)."""
    assert isinstance(LanceDBChunkReader.__new__(LanceDBChunkReader), ChunkReader)


def test_cited_chunk_row_mapping_pins_offsets_ref_from_doc_kind() -> None:
    """`offsets_ref` se deriva de `doc_kind` persistido en la fila: pdf→extract, md→source."""
    base = dict(
        text="t",
        source_path="00-Resources/a.md",
        heading=None,
        char_start=0,
        char_end=1,
        _relevance_score=1.0,
    )
    rows: list[dict[str, Any]] = [
        {**base, "doc_kind": "md"},
        {**base, "doc_kind": "pdf", "source_path": "00-Resources/articulo.pdf"},
    ]

    chunks = lancedb_reader._to_cited_chunks(rows)

    assert [chunk.offsets_ref for chunk in chunks] == ["source", "extract"]


def test_search_returns_the_frozen_shape_with_nullable_heading(
    reader: LanceDBChunkReader,
) -> None:
    """Toda devolución trae los 6 campos; `heading` es str o None, nunca ausente."""
    results = _search(reader, "markdown indexado con citas", top_k=10)
    assert results, "la consulta general devolvió cero chunks"
    paths = set()
    for chunk in results:
        assert isinstance(chunk, CitedChunk)
        assert isinstance(chunk.text, str) and chunk.text
        assert isinstance(chunk.source_path, str)
        assert chunk.heading is None or isinstance(chunk.heading, str)
        assert isinstance(chunk.char_start, int)
        assert isinstance(chunk.char_end, int)
        assert chunk.char_start < chunk.char_end
        assert isinstance(chunk.score, float)
        paths.add(chunk.source_path)
    assert any(chunk.heading is None for chunk in results), (
        "plano.txt produce chunks con heading null (D13)"
    )
    assert any(isinstance(chunk.heading, str) for chunk in results), (
        "nota.md produce chunks con heading padre"
    )
    assert "00-Resources/con_guion_bajo.md" in paths


def test_scores_are_normalised_to_unit_interval_and_descending(
    reader: LanceDBChunkReader,
) -> None:
    """`score` ∈ [0,1] y orden descendente garantizado (spec-mcp-server §search)."""
    results = _search(reader, "offsets y citas exactas", top_k=8)
    assert results
    scores = [chunk.score for chunk in results]
    assert all(0.0 <= score <= 1.0 for score in scores), scores
    assert scores == sorted(scores, reverse=True), scores


# --- path_filter: glob relativo al vault (equiv. * → % de Phase 2) -------------


def test_path_filter_glob_narrows_results_to_the_matching_subtree(
    reader: LanceDBChunkReader,
) -> None:
    """`sub/*` solo devuelve chunks de `sub/`; `*.md` excluye `.txt` (semántica LIKE).

    `*` se traduce a `%` de SQL LIKE (spec-mcp-server §search), que SÍ cruza
    `/`: `00-Resources/*.md` incluye también los `.md` anidados —casación
    distinta a la del shell, y esa ES la equivalencia congelada con la que
    Phase 2 filtrará en SQL—.
    """
    general = _search(reader, "indexación del flujo", top_k=10)
    assert {chunk.source_path for chunk in general} >= {
        "00-Resources/nota.md",
        "00-Resources/sub/carpeta/anidada.md",
    }

    sub = _search(reader, "indexación del flujo", top_k=10, path_filter="00-Resources/sub/*")
    assert sub, "el glob 00-Resources/sub/* devolvió cero chunks"
    assert all(chunk.source_path.startswith("00-Resources/sub/") for chunk in sub)

    md_only = _search(reader, "indexación del flujo", top_k=10, path_filter="00-Resources/*.md")
    assert md_only
    assert all(chunk.source_path.endswith(".md") for chunk in md_only)
    assert "00-Resources/sub/carpeta/anidada.md" in {chunk.source_path for chunk in md_only}, (
        "`*`≡`%` cruza `/`: los .md anidados también casan (semántica LIKE, §search)"
    )
    assert all(chunk.source_path != "00-Resources/plano.txt" for chunk in md_only)


def test_path_filter_exact_glob_with_literal_underscore_matches_only_it(
    reader: LanceDBChunkReader,
) -> None:
    """El `_` literal de `con_guion_bajo.md` está escapado: casación exacta."""
    exact = _search(
        reader,
        "guion bajo en el nombre",
        top_k=5,
        path_filter="00-Resources/con_guion_bajo.md",
    )
    assert exact
    assert all(chunk.source_path == "00-Resources/con_guion_bajo.md" for chunk in exact)

    # `?` es el comodín de un solo carácter: casa `con_guion_bajo` con cualquier
    # carácter en la posición del `_` — la semántica de Phase 2, sin escapar.
    wildcarded = _search(
        reader,
        "guion bajo en el nombre",
        top_k=5,
        path_filter="00-Resources/con?guion_bajo.md",
    )
    assert wildcarded
    assert all(chunk.source_path == "00-Resources/con_guion_bajo.md" for chunk in wildcarded)


def test_path_filter_to_like_predicate_pins_the_phase2_equivalence() -> None:
    """La traducción glob→LIKE queda congelada: `*`→`%`, `?`→`_`, escape y comillas."""
    assert path_filter_to_like_predicate("00-Resources/sub/*") == (
        "source_path LIKE '00-Resources/sub/%' ESCAPE '\\'"
    )
    # `**` se traduce como dos `%` y el `/` literal se conserva: `%%/%` ≡ `%`
    # en LIKE ( `%` cruza `/`), semánticamente idéntico al `*` simple.
    assert path_filter_to_like_predicate("00-Resources/lit/**/*.pdf") == (
        "source_path LIKE '00-Resources/lit/%%/%.pdf' ESCAPE '\\'"
    )
    assert path_filter_to_like_predicate("00-Resources/?.md") == (
        "source_path LIKE '00-Resources/_.md' ESCAPE '\\'"
    )
    # `_` literal escapado; `%` literal escapado; comilla duplicada (SQL seguro).
    assert path_filter_to_like_predicate("00-Resources/a_b.md") == (
        "source_path LIKE '00-Resources/a\\_b.md' ESCAPE '\\'"
    )
    assert path_filter_to_like_predicate("00-Resources/100%.md") == (
        "source_path LIKE '00-Resources/100\\%.md' ESCAPE '\\'"
    )
    assert path_filter_to_like_predicate("00-Resources/o'brien.md") == (
        "source_path LIKE '00-Resources/o''brien.md' ESCAPE '\\'"
    )
    # Multibyte del glob se conserva tal cual en el patrón (UTF-8 en LIKE).
    assert path_filter_to_like_predicate("00-Resources/lit/ñ-日-o'brien.md") == (
        "source_path LIKE '00-Resources/lit/ñ-日-o''brien.md' ESCAPE '\\'"
    )


def test_path_filter_to_like_predicate_rejects_globs_beyond_the_cap() -> None:
    """W-08: el tope de 1024 chars del borde MCP se revalida en el adaptador.

    Defensa en profundidad SIN duplicar la traducción: el mismo literal de
    longitud, dos bordes (`mcp.paths` —aquí el adaptador—).
    """
    ok = "00-Resources/" + "a" * (1024 - len("00-Resources/"))
    assert path_filter_to_like_predicate(ok).startswith("source_path LIKE ")
    with pytest.raises(ValueError, match="1024"):
        path_filter_to_like_predicate("00-Resources/" + "a" * 1025)


def test_invalid_inputs_are_rejected_at_the_boundary(
    reader: LanceDBChunkReader,
) -> None:
    """Validación en el borde del puerto: consulta vacía, top_k<1, glob absodo o `..`."""
    with pytest.raises(ValueError, match="consulta"):
        _search(reader, "   ")
    with pytest.raises(ValueError, match="top_k"):
        _search(reader, "markdown", top_k=0)
    with pytest.raises(ValueError, match="relativo"):
        _search(reader, "markdown", path_filter="/absoluto/*.md")
    with pytest.raises(ValueError, match=r"\.\."):
        _search(reader, "markdown", path_filter="00-Resources/../secreto/*.md")
    with pytest.raises(ValueError, match=r"\.\."):  # backslash normalizado → escape igual
        _search(reader, "markdown", path_filter="00-Resources\\..\\secreto\\*.md")
    with pytest.raises(ValueError, match="presupuesto"):  # query cap (frontera 10k)
        _search(reader, "x" * 10_001)


# --- híbrido ANN + FTS ----------------------------------------------------------


def test_hybrid_query_exercises_both_ann_and_fts_indexes(
    reader: LanceDBChunkReader,
) -> None:
    """El plan de la búsqueda del adaptador usa KNN (ANN) + FTS + fusión RRF."""
    plan = asyncio.run(reader.explain_plan("citas de markdown"))
    assert "KNNVectorDistance" in plan, f"sin pierna ANN:\n{plan}"
    assert "_score" in plan, f"sin pierna FTS:\n{plan}"
    assert "RRFReranker" in plan, f"sin fusión RRF:\n{plan}"


def test_explain_plan_rejects_invalid_inputs_and_honours_the_path_filter(
    reader: LanceDBChunkReader,
) -> None:
    """Diagnóstico T9 con el MISMO borde que `search`, y el prefiltro aplicado al plan.

    `explain_plan` debe rechazar consulta vacía y `top_k < 1` igual que `search`
    (ValueError en el borde del puerto, spec-mcp-server §search) y, con
    `path_filter`, el plan debe incluir el predicado SQL congelado
    (`source_path LIKE ...`): el filtro se aplica como PREFILTRO sobre ambas
    piernas, no después de fusionar.
    """
    with pytest.raises(ValueError, match="consulta"):
        asyncio.run(reader.explain_plan("   "))
    with pytest.raises(ValueError, match="top_k"):
        asyncio.run(reader.explain_plan("markdown", top_k=0))

    plan = asyncio.run(reader.explain_plan("citas", top_k=3, path_filter="00-Resources/sub/*"))

    assert "KNNVectorDistance" in plan
    assert "source_path LIKE" in plan, plan
    assert "00-Resources/sub/%" in plan, plan


def test_lexical_and_semantic_queries_both_return_cited_hits(
    reader: LanceDBChunkReader,
) -> None:
    """Tanto el término léxico exacto como la paráfrasis devuelven citas válidas."""
    lexico = _search(reader, "whitelist", top_k=3)
    assert lexico
    assert any("whitelist" in chunk.text.lower() for chunk in lexico), (
        "la pierna FTS debe traer el chunk que contiene 'whitelist'"
    )

    semantico = _search(reader, "¿qué formatos acepta el pipeline?", top_k=3)
    assert semantico
    for chunk in semantico:
        assert chunk.source_path.startswith("00-Resources/")
        assert 0.0 <= chunk.score <= 1.0


# --- latencia preliminar ---------------------------------------------------------


@pytest.mark.slow
def test_search_latency_p95_under_500ms_preliminary(reader: LanceDBChunkReader) -> None:
    """PRELIMINAR: p95 < 500ms sobre 10 consultas del corpus dorado (~7 chunks).

    **`@pytest.mark.slow`** — es una MEDICION, no una asercion de correccion, y
    con n=10 el p95 (nearest-rank) es el **maximo** de la muestra: cualquier
    outlier la tumba. Medido empiricamente: en la suite completa esta prueba
    falla mientras que aislada pasa holgadamente (39ms), porque Docling (~2GB
    RSS) y MiniLM empujan la maquina a **swap** (1.5GB usados) y una query que
    paga un page-fault supera 500ms. Lo que se mide ahi es la memoria de la
    maquina, no la latencia del buscador — por eso vive fuera de la suite de
    correccion (`addopts = "-m 'not slow'"`, el filtro que T11 ya prescribia).

    Assertion de humo, NO un bench: el corpus tiene ~7 chunks y el
    brute-force ya cumple (spec-rag-engine §Target), asi que esta cifra NO
    extrapola a 10k/1k (Phase 6 / T10 mide de verdad). Incluye el embed de la
    consulta, que es el punto de medicion de spec-mcp-server §Presupuestos.

    Ejecutar: `uv run python -m pytest -m slow`.
    """
    _search(reader, "calentamiento del embedder", top_k=1)  # warm-up: carga perezosa
    latencies_ms: list[float] = []
    for query in GOLDEN_QUERIES:
        start = time.perf_counter()
        results = _search(reader, query, top_k=5)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        assert results, f"consulta dorada sin resultados: {query!r}"
        latencies_ms.append(elapsed_ms)
    p95 = sorted(latencies_ms)[9]  # nearest-rank: ceil(0.95 * 10) = 10º elemento
    print(f"\n[T9 latencia preliminar] p95={p95:.1f}ms muestras={latencies_ms}")
    assert p95 < 500.0, f"p95 preliminar {p95:.1f}ms >= 500ms: {latencies_ms}"


# --- verificador CLI (M4) --------------------------------------------------------


def test_verify_cli_counts_rows_and_prints_cited_chunks_read_only(
    indexed_vault: IndexedVault,
) -> None:
    """El verificador abre el vault real, cuenta filas, cita resultados y NO escribe."""
    db_dir = indexed_vault.vault / ".tepochcalli" / "db"
    before = _snapshot(db_dir)

    env = {
        **os.environ,
        "HF_HOME": str(indexed_vault.model_cache),
        "SENTENCE_TRANSFORMERS_HOME": str(indexed_vault.model_cache),
        "HF_HUB_OFFLINE": "1",
    }
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "tepochcalli_flow.verify",
            str(indexed_vault.vault),
            "--query",
            "whitelist de extensiones",
            "--top-k",
            "3",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert proc.returncode == 0, f"verificador falló:\n{proc.stdout}\n{proc.stderr}"
    assert "Filas" in proc.stdout and str(_expected_row_count(indexed_vault)) in proc.stdout
    assert "00-Resources/" in proc.stdout  # source_path citado
    assert "score=" in proc.stdout
    assert "heading=" in proc.stdout
    assert "[char_start=" in proc.stdout
    # T2 (j): el verificador resuelve `source_path` contra el vault y comprueba el slice.
    assert "slice=OK" in proc.stdout
    assert "slice=BROKEN" not in proc.stdout

    assert _snapshot(db_dir) == before, (
        "el verificador modificó .tepochcalli/db/ (¡debe solo leer!)"
    )


def test_verify_cli_exits_nonzero_on_missing_vault(tmp_path: Path) -> None:
    """Un vault sin DB indexada sale con código 2 y mensaje accionable, sin traceback."""
    proc = subprocess.run(
        [sys.executable, "-m", "tepochcalli_flow.verify", str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 2
    assert "no existe" in proc.stderr.lower()


def test_verify_cli_exits_3_on_broken_db(tmp_path: Path) -> None:
    """DB presente pero tabla `chunks` ausente → exit 3 y mensaje accionable, sin traceback."""
    cache = resolve_model_cache()
    link_model_cache(tmp_path, cache)  # el CLI fija HF_HOME=<vault>/.tepochcalli/models
    env = {**os.environ, **offline_env(cache)}
    (tmp_path / ".tepochcalli" / "db" / "tepochcalli.lance").mkdir(parents=True)

    proc = subprocess.run(
        [sys.executable, "-m", "tepochcalli_flow.verify", str(tmp_path)],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert proc.returncode == 3, f"stderr:\n{proc.stderr}\nstdout:\n{proc.stdout}"
    assert "Traceback" not in proc.stderr
    assert "chunks" in proc.stderr


def test_verify_cli_rejects_top_k_below_one(tmp_path: Path) -> None:
    """`--top-k 0` → argparse error (exit 2 de argparse) con mensaje accionable."""
    proc = subprocess.run(
        [sys.executable, "-m", "tepochcalli_flow.verify", str(tmp_path), "--top-k", "0"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 2
    assert "--top-k" in proc.stderr


# --- helpers ----------------------------------------------------------------------


def _search(
    reader: LanceDBChunkReader,
    query: str,
    *,
    top_k: int = flow_config.DEFAULT_TOP_K,
    path_filter: str | None = None,
) -> list[CitedChunk]:
    """Corre `search` en su propio loop (cada test, aislado)."""
    return asyncio.run(reader.search(query, top_k, path_filter))


def _expected_row_count(indexed_vault: IndexedVault) -> int:
    """Cuenta las filas esperadas abriendo la tabla una vez (solo lectura)."""
    import lancedb

    async def _count() -> int:
        db = await lancedb.connect_async(str(indexed_vault.vault / DB_RELPATH))
        try:
            table = await db.open_table("chunks")
            return await table.count_rows()
        finally:
            db.close()

    return asyncio.run(_count())


def _snapshot(root: Path) -> dict[str, tuple[int, int | None]]:
    """(mtime_ns, size) por ruta relativa — detecta cualquier escritura o creación."""
    out: dict[str, tuple[int, int | None]] = {}
    for path in sorted(root.rglob("*")):
        out[str(path.relative_to(root))] = (
            path.stat().st_mtime_ns,
            path.stat().st_size if path.is_file() else None,
        )
    return out
