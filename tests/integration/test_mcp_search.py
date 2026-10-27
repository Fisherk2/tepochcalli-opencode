"""T2: `search` end-to-end sobre un vault indexado de verdad — camino caliente (plan §5).

Fuentes de verdad:

* tasks/plan.md §5 «Contrato de datos» + §6 T2 — shape `{query, took_ms,
  truncated, results:[…7 campos…]}`, `score` descendente en [0,1], `took_ms`
  >0 (incluye el embed, medido dentro del handler), `top_k` efectivo
  `min(solicitado, 8)`, presupuesto 1600 con `truncated`, `INDEX_EMPTY` y
  `E_MODEL_MISMATCH` sin cruzar dims.
* specs/spec-mcp-server.md §search / §Presupuesto de tokens / §errores.

Decisiones de test, documentadas a propósito (mismos patrones que T9/M3):

* **Indexación SIEMPRE en subproceso** con `TEPOCHCALLI_VAULT_ROOT` propio:
  el environment global de cocoindex no admite dos vaults en el mismo proceso
  (sonda empírica T9, ver `test_read_port.py`).
* **Dos fixtures, dos niveles** (decisión sobre el umbral de 60 s del plan):
  el vault PEQUEÑO (fixture dorada + `plano.txt`, ~9 chunks) corre en la suite
  de corrección — ahí viven todos los tests de contrato; el vault de
  **≥100 chunks** (AC de verificación de T2: corpus generado + `grande.md`)
  cuesta **~170 s de indexación** (medido), así que su test único va
  marcado `@pytest.mark.slow` y queda fuera de CI, EXIGIDO aquí: la suite
  normal SÍ tiene integración de `search` contra un vault indexado real.
* **Cero red y cero LLM** (AC de T2): el guard de socket de M3(b) se repite —
  búsqueda completa con `connect` AF_INET/AF_INET6 bloqueado y sin ni un
  intento; más el sello de módulos LLM en `sys.modules`.
* Los tests con `_FakeBackend` (modelo desalineado, precedencia de
  validación, corte de presupuesto) ejercitan el handler SIN indexar un vault
  con otro modelo — `E_MODEL_MISMATCH` es una comparación de strings, no un
  cruce de dims.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import socket
import subprocess
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest
from model_cache import link_model_cache, offline_env, resolve_model_cache
from tepochcalli_flow import app as flow_app
from tepochcalli_flow import citation
from tepochcalli_flow.config import DEFAULT_EMBEDDING_MODEL, load_config
from tepochcalli_flow.layout import DB_RELPATH, TABLE_NAME
from tepochcalli_flow.ports import CitedChunk
from tepochcalli_mcp import budget
from tepochcalli_mcp.server import _VaultSearchBackend
from tepochcalli_mcp.tools import json_result
from tepochcalli_mcp.tools import search as search_handler
from tepochcalli_mcp.tools.search import SearchBackend

FIXTURE_VAULT = Path(__file__).parents[1] / "fixtures" / "vault_markdown"

CONTRACT_RESULT_FIELDS = [
    "text",
    "source_path",
    "heading",
    "char_start",
    "char_end",
    "score",
    "offsets_ref",
]

LLM_MODULES = frozenset({"litellm", "openai", "anthropic"})

UPDATE_SCRIPT = "from tepochcalli_flow.app import app; app.update_blocking()"

GOLDEN_QUERY = "whitelist de extensiones indexables"
"""Consulta dorada determinista sobre la fixture de Phase 1 (vocabulario real del corpus)."""

VOCABULARY = [
    "pediatría",
    "métrica",
    "cobertura",
    "vacunación",
    "mortalidad",
    "cohorte",
    "prevalencia",
    "diagnóstico",
    "tratamiento",
    "seguimiento",
    "protocolo",
    "ensayo",
    "eficacia",
    "seguridad",
    "dosis",
]

GRANDE_UNIQUE_TERM = "zumbianko"
"""Término léxico único de `grande.md` — la consulta que fuerza el corte de presupuesto."""

PLANO_CONTENT = (
    "Texto plano de prueba sin jerarquía de headings: su chunk nace con "
    "heading null (D13) y el campo igualmente presente en el resultado.\n"
)


def _generated_corpus() -> str:
    """12 archivos × 20 secciones de ~700 chars: ≥100 chunks con vocabulario rotatorio."""
    blocks: list[str] = []
    for file_index in range(12):
        sections: list[str] = [f"# Tema {file_index} del corpus generado\n"]
        for section_index in range(20):
            words = [
                VOCABULARY[(file_index * 20 + section_index + offset) % len(VOCABULARY)]
                for offset in range(60)
            ]
            sections.append(
                f"## Sección {section_index}\n\n"
                f"Paragraph {file_index}.{section_index}: " + " ".join(words) + ".\n"
            )
        blocks.append("".join(sections))
    return "\n".join(blocks)


GRANDE_CONTENT = f"# Documento grande sobre {GRANDE_UNIQUE_TERM}\n\n" + "\n\n".join(
    f"## Capítulo {chapter}\n\n"
    + f"El fenómeno {GRANDE_UNIQUE_TERM} aparece en el capítulo {chapter} con "
    + "detalle suficiente para llenar chunks completos de mil quinientos bytes. "
    + "Esta prosa deliberadamente larga repite conceptos de métrica, cohorte y "
    + "seguimiento para que el segmentador empaque cada capítulo cerca del tamaño "
    + "máximo de chunk del flow, forzando que ocho resultados de este documento "
    + "excedan el presupuesto de mil seiscientos tokens del contrato de search. "
    + "La repetición es determinista: ni una consulta aleatoria ni un ordenador "
    + "distinto cambiarán el número de chunks que este archivo produce en total. "
    + f"Conclusión parcial del capítulo {chapter}: {GRANDE_UNIQUE_TERM} sigue aquí.\n"
    for chapter in range(12)
)


@dataclass(frozen=True)
class IndexedVault:
    """Vault temporal T2 ya indexado por el flow real (subproceso)."""

    vault: Path
    """Raíz del vault temporal."""

    model_cache: Path
    """Cache de modelo al que apunta el symlink `.tepochcalli/models`."""


def _build_vault(
    tmp_path_factory: pytest.TempPathFactory,
    name: str,
    *,
    with_generated_corpus: bool,
    min_rows: int | None = None,
) -> IndexedVault:
    """Fixture dorada (+ plano) indexada en subproceso; opcionalmente con corpus ≥100.

    El update corre en subproceso (docstring del módulo): environment de
    cocoindex aislado y red off cuando el cache resuelto ya contiene el modelo
    (`model_cache.offline_env`). `min_rows` aserta la premisa del AC (≥100).
    """
    vault = tmp_path_factory.mktemp(name)
    shutil.copytree(FIXTURE_VAULT, vault, dirs_exist_ok=True)
    (vault / citation.RESOURCES_DIR / "plano.txt").write_text(PLANO_CONTENT, encoding="utf-8")
    if with_generated_corpus:
        (vault / citation.RESOURCES_DIR / "generado.md").write_text(
            _generated_corpus(), encoding="utf-8"
        )
        (vault / citation.RESOURCES_DIR / "grande.md").write_text(GRANDE_CONTENT, encoding="utf-8")

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
    if min_rows is not None:
        assert _count_chunks(vault) >= min_rows, f"se esperaban ≥{min_rows} chunks reales"
    return IndexedVault(vault=vault, model_cache=models_link)


@pytest.fixture(scope="module")
def indexed_vault(tmp_path_factory: pytest.TempPathFactory) -> IndexedVault:
    """Vault PEQUEÑO (dorada + plano, ~9 chunks) para la suite de corrección."""
    return _build_vault(tmp_path_factory, "vault-t2-small", with_generated_corpus=False)


@pytest.fixture(scope="module")
def big_vault(tmp_path_factory: pytest.TempPathFactory) -> IndexedVault:
    """Vault de ≥100 chunks (AC de T2) — SOLO para tests marcados `slow` (~170 s)."""
    return _build_vault(
        tmp_path_factory,
        "vault-t2-big",
        with_generated_corpus=True,
        min_rows=100,
    )


def _backend_on(indexed: IndexedVault) -> Iterator[_VaultSearchBackend]:
    """Backend real sobre `indexed`, con MiniLM cacheado, offline y PRIMED.

    **Prime (patrón M3: warm ANTES del guard):** la PRIMERA construcción del
    lector — `SentenceTransformer` incluido, dentro de `cited_chunks`— puede
    sondear la red en proceso (sonda T6: los 41 dials IPv6 de `httpcore` con
    cache en disco completo; ni `HF_HUB_OFFLINE` en proceso —sus constantes se
    congelan al importar— ni el disco cálido lo evitan en esa primera carga).
    El fixture ejecuta UNA búsqueda real SIN canario con la MISMA env y el
    MISMO código que después usará el test: el reader queda cacheado en el
    backend y el canario mide SOLO la búsqueda (cero dials), que es lo que su
    nombre promete. En frío, `offline_env` permite la única descarga aquí.
    """
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setenv("HF_HOME", str(indexed.model_cache))
        monkeypatch.setenv("SENTENCE_TRANSFORMERS_HOME", str(indexed.model_cache))
        monkeypatch.setenv("HF_HUB_OFFLINE", "1")
        backend = _VaultSearchBackend(indexed.vault, load_config(indexed.vault))
        asyncio.run(backend.cited_chunks("calentamiento del lector", 1, None))
        yield backend
    finally:
        monkeypatch.undo()


@pytest.fixture(scope="module")
def backend(indexed_vault: IndexedVault) -> Iterator[_VaultSearchBackend]:
    """Backend sobre el vault pequeño — módulo-scoped: el modelo se carga UNA vez."""
    yield from _backend_on(indexed_vault)


@pytest.fixture(scope="module")
def big_backend(big_vault: IndexedVault) -> Iterator[_VaultSearchBackend]:
    """Backend sobre el vault de ≥100 chunks — solo lo consume el test `slow`."""
    yield from _backend_on(big_vault)


def _search(
    backend: SearchBackend,
    query: str,
    top_k: int = 5,
    path_filter: str | None = None,
) -> dict[str, object]:
    """Corre el handler en su propio loop (cada test, aislado).

    El backend va como FACTORY (decisión G1) y el embedder disponible como
    seam constante True (R1/T6: en la suite de `search` el proveedor local
    siempre está — la precedencia `E_NO_EMBEDDER` se prueba en
    `test_mcp_e_dialect.py`).
    """
    return asyncio.run(
        search_handler.search(
            query,
            top_k,
            path_filter,
            backend_factory=lambda: backend,
            embedder_available=lambda: True,
        )
    )


def _cited_chunk(index: int, *, chars: int = 20, score: float | None = None) -> CitedChunk:
    """Chunk sintético: `chars` baratos por omisión (el presupuesto no los corta)."""
    text = f"chunk-{index:02d}-" + "x" * max(0, chars - 11)
    return CitedChunk(
        text=text,
        source_path=f"00-Resources/sintetico-{index}.md",
        heading=None,
        char_start=0,
        char_end=len(text),
        score=1.0 - index * 0.01 if score is None else score,
    )


def _count_chunks(vault: Path) -> int:
    """Filas de la tabla `chunks` — la premisa del fixture ≥100 (solo lectura)."""
    import lancedb

    async def _count() -> int:
        db = await lancedb.connect_async(str(vault / DB_RELPATH))
        try:
            table = await db.open_table(TABLE_NAME)
            return await table.count_rows()
        finally:
            db.close()

    return asyncio.run(_count())


class _FakeBackend:
    """Doble mínimo del puerto `SearchBackend`: chunks y modelos dados de alta."""

    def __init__(
        self,
        *,
        chunks: Sequence[CitedChunk] = (),
        index_models: set[str] | None = None,
        expected_model: str = DEFAULT_EMBEDDING_MODEL,
        error: Exception | None = None,
        models_error: Exception | None = None,
    ) -> None:
        self._chunks = list(chunks)
        self._models = {DEFAULT_EMBEDDING_MODEL} if index_models is None else index_models
        self._expected = expected_model
        self._error = error
        self._models_error = models_error
        self.received_top_k: int | None = None
        """El `top_k` que el handler entregó al lector — pin del efectivo."""

    @property
    def expected_model(self) -> str:
        return self._expected

    async def index_models(self) -> set[str]:
        if self._models_error is not None:
            raise self._models_error  # G1: fallo NO-ValueError en la fase de estado
        return self._models

    async def cited_chunks(
        self, query: str, top_k: int, path_filter: str | None
    ) -> list[CitedChunk]:
        self.received_top_k = top_k
        if self._error is not None:
            raise self._error
        return self._chunks[:top_k]


# --- contrato congelado del resultado (vault real pequeño) ------------------------


def test_search_shape_is_the_frozen_contract_with_ordered_keys(backend: SearchBackend) -> None:
    """`{query, took_ms, truncated, results}` y los 7 campos por resultado, en orden."""
    payload = _search(backend, GOLDEN_QUERY)

    assert list(payload) == ["query", "took_ms", "truncated", "results"]
    assert payload["query"] == GOLDEN_QUERY
    assert isinstance(payload["took_ms"], int)
    assert isinstance(payload["truncated"], bool)
    results = payload["results"]
    assert isinstance(results, list) and results
    for result in results:
        assert list(result) == CONTRACT_RESULT_FIELDS
        assert isinstance(result["text"], str) and result["text"]
        assert isinstance(result["source_path"], str)
        assert result["source_path"].startswith("00-Resources/")
        assert result["heading"] is None or isinstance(result["heading"], str)  # D13
        assert isinstance(result["char_start"], int)
        assert isinstance(result["char_end"], int)
        assert result["char_start"] < result["char_end"]
        assert isinstance(result["score"], float)
        assert isinstance(result["offsets_ref"], str)


def test_scores_are_in_unit_interval_and_descending(backend: SearchBackend) -> None:
    """`score` ∈ [0,1] y orden descendente garantizado (spec-mcp-server §search)."""
    results = _search(backend, "citas con offsets de carácter exactos", 8)["results"]

    scores = [result["score"] for result in results]
    assert scores
    assert all(0.0 <= score <= 1.0 for score in scores), scores
    assert scores == sorted(scores, reverse=True), scores


def test_took_ms_is_positive_and_integer_for_a_real_search(backend: SearchBackend) -> None:
    """`took_ms` > 0: el reloj corre desde la entrada del handler e INCLUYE el embed."""
    payload = _search(backend, "parseo de markdown y texto plano")

    assert payload["took_ms"] > 0


def test_requested_top_k_below_default_returns_at_most_that_many(backend: SearchBackend) -> None:
    """`top_k=3` sobre el corpus real respeta el pedido cuando es válido."""
    results = _search(backend, "whitelist de extensiones", 3)["results"]

    assert 0 < len(results) <= 3


# --- top_k: default, tope efectivo y rango del contrato ---------------------------


def test_default_top_k_reaches_the_reader_as_five() -> None:
    """Sin `top_k`, el lector recibe 5 — pin EXACTO del default vía el doble."""
    fake = _FakeBackend(chunks=[_cited_chunk(index) for index in range(3)])

    payload = _search(fake, "pregunta barata")

    assert fake.received_top_k == budget.TOP_K_DEFAULT == 5
    assert len(payload["results"]) == 3, "chunks baratos: el presupuesto no corta"
    assert payload["truncated"] is False


def test_requested_top_k_is_clamped_to_the_hard_cap_before_the_reader() -> None:
    """`top_k=20` es válido pero el lector recibe `min(20, 8)` = 8 (plan §5)."""
    fake = _FakeBackend(chunks=[_cited_chunk(index) for index in range(10)])

    payload = _search(fake, "pregunta barata", 20)

    assert fake.received_top_k == budget.TOP_K_CAP == 8
    assert len(payload["results"]) == 8


@pytest.mark.parametrize("invalid", [0, -3, 21, 1000])
def test_top_k_outside_the_contract_range_is_a_validation_error(
    backend: SearchBackend, invalid: int
) -> None:
    """Fuera de [1,20] → `VALIDATION_ERROR` con la forma legada (plan §5)."""
    payload = _search(backend, "métricas", invalid)

    error = payload["error"]
    assert list(error) == ["code", "message", "details"]
    assert error["code"] == "VALIDATION_ERROR"


def test_oversized_query_is_a_validation_error_via_the_adapter(backend: SearchBackend) -> None:
    """Query >10 000 chars la rechaza el ADAPTADOR (`QUERY_MAX_CHARS`) y el handler la mapea."""
    payload = _search(backend, "x" * 10_001)

    assert payload["error"]["code"] == "VALIDATION_ERROR"


def test_empty_query_is_a_validation_error_via_the_adapter(backend: SearchBackend) -> None:
    """Consulta vacía: `ValueError` del puerto → `VALIDATION_ERROR` en el borde MCP."""
    payload = _search(backend, "   ")

    assert payload["error"]["code"] == "VALIDATION_ERROR"


def test_unicode_query_returns_results_without_escapes(backend: SearchBackend) -> None:
    """Fixture adversa unicode (CJK/emoji): el handler responde y serializa sin escapes."""
    payload = _search(backend, "métricas 日本語 🚀 vacunación")

    assert payload["query"] == "métricas 日本語 🚀 vacunación"
    assert payload.get("error") is None
    round_trip = json.loads(json.dumps(payload, ensure_ascii=False))
    assert round_trip == payload


# --- path_filter en el borde MCP ---------------------------------------------------


def test_invalid_path_filter_is_a_validation_error_before_touching_the_index() -> None:
    """Glob absoluto o con `..` → `VALIDATION_ERROR` validado en `paths.py` (sin traducir)."""
    backend = _FakeBackend()

    absolute = _search(backend, "métricas", path_filter="/absoluto/*.md")
    traversal = _search(backend, "métricas", path_filter="00-Resources/../secreto/*")

    assert absolute["error"]["code"] == "VALIDATION_ERROR"
    assert traversal["error"]["code"] == "VALIDATION_ERROR"


def test_valid_path_filter_restricts_results_to_the_subtree(backend: SearchBackend) -> None:
    """El glob validado llega AL ADAPTADOR y prefieltra: solo el subárbol pedido."""
    general = _search(backend, "indexación del flujo", 8)
    assert general["results"]
    assert any(
        not str(result["source_path"]).startswith("00-Resources/sub/")
        for result in general["results"]
    ), "sin filtro debe haber resultados fuera de sub/ (si no, el test es vacío)"

    filtered = _search(backend, "indexación del flujo", 8, path_filter="00-Resources/sub/*")

    assert filtered["results"]
    assert all(
        str(result["source_path"]).startswith("00-Resources/sub/") for result in filtered["results"]
    )


# --- presupuesto determinista (criterio 4) ------------------------------------------


def test_budget_cut_sets_truncated_at_the_handler_level() -> None:
    """Corte del presupuesto vía doble: techo respetado, `truncated` y score intacto."""
    costly = [_cited_chunk(index, chars=1500) for index in range(6)]  # 400 tokens c/u
    fake = _FakeBackend(chunks=costly)

    payload = _search(fake, "pregunta", 8)

    results = payload["results"]
    assert payload["truncated"] is True
    assert 0 < len(results) < 6
    total = sum(budget.estimate_tokens(str(result["text"])) for result in results)
    assert total <= budget.PAYLOAD_TOKEN_CEILING, total
    scores = [result["score"] for result in results]
    assert scores == sorted(scores, reverse=True)
    assert results[0]["score"] == max(chunk.score for chunk in costly), (
        "el de mayor score NUNCA se descarta"
    )


@pytest.mark.slow
def test_hundred_chunk_vault_search_shape_and_budget(
    big_backend: SearchBackend, big_vault: IndexedVault
) -> None:
    """AC de verificación T2: ≥100 chunks reales, shape completo y presupuesto cortado.

    El fixture de ≥100 chunks cuesta ~170 s de indexación (medido; >60 s) ⇒
    test `slow`, fuera de la suite de corrección — la suite normal cubre
    `search` con el vault pequeño real de este mismo fichero.
    """
    assert _count_chunks(big_vault.vault) >= 100

    payload = _search(big_backend, "métricas y cobertura del corpus generado", 20)

    assert list(payload) == ["query", "took_ms", "truncated", "results"]
    results = payload["results"]
    # `top_k=20` ⇒ efectivo 8; el presupuesto puede cortar ANTES (chunks reales
    # de ~1344 chars ≈ 361 tokens ⇒ caben ~4): el tope se pinna exacto con el
    # doble en `test_requested_top_k_is_clamped_to_the_hard_cap_before_the_reader`.
    assert 0 < len(results) <= budget.TOP_K_CAP
    for result in results:
        assert list(result) == CONTRACT_RESULT_FIELDS
    scores = [result["score"] for result in results]
    assert scores == sorted(scores, reverse=True)
    assert all(0.0 <= score <= 1.0 for score in scores)

    truncated_payload = _search(
        big_backend, GRANDE_UNIQUE_TERM, 8, path_filter="00-Resources/grande.md"
    )
    truncated_results = truncated_payload["results"]
    assert 2 <= len(truncated_results) < 8, "grande.md produce más chunks de los que caben"
    assert truncated_payload["truncated"] is True
    total = sum(budget.estimate_tokens(str(result["text"])) for result in truncated_results)
    assert total <= budget.PAYLOAD_TOKEN_CEILING, total


# --- taxonomía: INDEX_EMPTY y E_MODEL_MISMATCH -----------------------------------------


def test_missing_index_returns_index_empty(tmp_path: Path) -> None:
    """Vault sin DB → `INDEX_EMPTY` legado, SIN cargar el embedder (barato por diseño)."""
    backend = _VaultSearchBackend(tmp_path, load_config(tmp_path))

    payload = _search(backend, "cualquier pregunta")

    error = payload["error"]
    assert error["code"] == "INDEX_EMPTY"
    assert list(error) == ["code", "message", "details"]


def test_index_model_different_from_config_returns_e_model_mismatch() -> None:
    """Modelo del índice ≠ config → `E_MODEL_MISMATCH` + alias legado, sin cruzar dims."""
    backend = _FakeBackend(index_models={"modelo-viejo"}, expected_model=DEFAULT_EMBEDDING_MODEL)

    payload = _search(backend, "métricas")

    error = payload["error"]
    assert error["code"] == "E_MODEL_MISMATCH"
    assert error["details"]["legacy_code"] == "INDEX_STALE_MODEL"


def test_validation_precedes_index_checks() -> None:
    """Precedencia en el borde: args inválidos → `VALIDATION_ERROR` sin mirar el índice."""
    backend = _FakeBackend(index_models=set())  # índice vacío: no debe decidir nada

    payload = _search(backend, "métricas", 0)

    assert payload["error"]["code"] == "VALIDATION_ERROR"


def test_unexpected_backend_failure_maps_to_internal() -> None:
    """Fallo inesperado → `INTERNAL` legado; el detalle vive en el log, nunca en el payload."""
    backend = _FakeBackend(error=RuntimeError("detalle interno con traceback falso"))

    payload = _search(backend, "métricas")

    error = payload["error"]
    assert error["code"] == "INTERNAL"
    assert "traceback falso" not in error["message"]


# --- G1: la guarda compartida cubre estado Y arranque ------------------------------


def test_g1_unexpected_error_in_index_state_phase_is_canonical_internal() -> None:
    """G1: un fallo ≠ `ValueError` en la fase de ESTADO del índice → `INTERNAL` canónico.

    Antes de G1 esa excepción escapaba al SDK, que respondía con texto libre
    (spec-mcp-server §Manejo de errores: «payload JSON canónico, nunca texto
    libre»). El payload pasa además por el empaquetador real: `is_error = true`
    y el detalle jamás viaja al cliente.
    """
    fake = _FakeBackend(models_error=RuntimeError("tabla chunks sin columna model"))

    payload = _search(fake, "métricas")

    result = json_result(payload)
    assert result.is_error is True
    error = json.loads(result.content[0].text)["error"]
    assert list(error) == ["code", "message", "details"]
    assert error["code"] == "INTERNAL"
    assert "columna model" not in error["message"], "el detalle vive en el log, no al cliente"


def test_g1_backend_startup_failure_is_canonical_internal() -> None:
    """G1: el ARRANQUE del backend (`_backend()` en server) corre BAJO la guarda.

    El handler recibe una FACTORY, no la instancia: resolver la raíz del vault
    y cargar la config ocurre dentro del handler ya protegido — un fallo ahí
    también responde `INTERNAL` canónico, nunca texto libre del SDK.
    """

    def _boom() -> SearchBackend:
        raise RuntimeError("resolve_vault_root ilegible")

    payload = asyncio.run(
        search_handler.search("pregunta", backend_factory=_boom, embedder_available=lambda: True)
    )

    result = json_result(payload)
    assert result.is_error is True
    error = json.loads(result.content[0].text)["error"]
    assert error["code"] == "INTERNAL"
    assert "ilegible" not in error["message"]


def test_error_payloads_are_json_canonical_in_the_wire_form() -> None:
    """El payload de error sobrevive a `content[0].text`: JSON parseable, sin texto libre."""
    backend = _FakeBackend()  # el índice jamás se toca: la validación falla antes
    error_payload = _search(backend, "métricas", 99)

    text = json.dumps(error_payload, ensure_ascii=False)
    assert json.loads(text) == error_payload
    assert error_payload["error"]["code"] == "VALIDATION_ERROR"


# --- cero red y cero LLM (canario M3 repetido en T2) ------------------------------------


def test_search_completes_with_outbound_network_blocked_and_zero_llm(
    backend: SearchBackend,
) -> None:
    """Búsqueda real completa con AF_INET/AF_INET6 bloqueados: cero intentos, cero LLM.

    El guard de socket es quien realmente prohibiría cualquier salida —incluida
    una llamada LLM por API—; `HF_HUB_OFFLINE=1` evita que el cliente HF ni
    siquiera intente contactar (modelo ya cacheado → 0 intentos, M3(b)).
    """
    attempts: list[object] = []
    with _outbound_blocked(attempts):
        payload = _search(backend, "diagnóstico y tratamiento según la whitelist", 5)

    assert payload["results"], "la búsqueda con red bloqueada devolvió vacío"
    assert attempts == [], f"intentos de salida a red: {attempts[:5]}"
    imported = sorted(name for name in sys.modules if name.split(".")[0] in LLM_MODULES)
    assert imported == [], f"módulos LLM importados durante la búsqueda: {imported}"


@contextlib.contextmanager
def _outbound_blocked(attempts: list[object]) -> Iterator[None]:
    """Bloquea `connect` AF_INET/AF_INET6 registrando cada intento (M3(b)).

    Duplicado deliberadamente de `test_pipeline_integration._outbound_blocked`
    (regla de tres aún no alcanzada; ambos son el sello de hermeticidad de su
    respectiva fase).
    """
    real_connect = socket.socket.connect

    def _guard(self: socket.socket, address: object, *args: object, **kwargs: object) -> None:
        if self.family in (socket.AF_INET, socket.AF_INET6):
            attempts.append(address)
            raise OSError("T2: salida de red bloqueada durante la búsqueda")
        return real_connect(self, address, *args, **kwargs)  # type: ignore[attr-defined]

    socket.socket.connect = _guard  # type: ignore[method-assign]
    old_offline = os.environ.get("HF_HUB_OFFLINE")
    os.environ["HF_HUB_OFFLINE"] = "1"
    try:
        yield
    finally:
        socket.socket.connect = real_connect  # type: ignore[method-assign]
        if old_offline is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = old_offline
