"""T3 (Phase 6): eval de relevancia — recall@5 sobre consultas etiquetadas (TD-15).

Fuentes de verdad:

* `docs/TRD.md` §6.2 — umbral **fijado en T0/CP-0 (2026-11-12) y no revisable aquí**
  (D-P6-8): **recall@5 = 1.0** con **n = 10** consultas etiquetadas ES/EN y
  `search(top_k=5)` en subproceso. Si la corrida no llega a 1.0 se documenta el
  hallazgo; no se relajan las etiquetas.
* `tasks/todo.md` §T3 — los AC literales.
* `specs/spec-mcp-server.md` §search — shape del payload (`source_path` real,
  `heading` nullable, `truncated`).

Decisiones de test, y el porqué de cada una:

* **Fixture PROPIO (`tests/fixtures/relevance_vault/`, 20 notas ES/EN) en vez del
  golden vault.** Con 1 md + 1 pdf, etiquetar 10 consultas sería tautológico: el
  top-5 lo llenarían chunks de esos dos ficheros y el recall no mediría
  recuperación. Las notas son **datos grabados** (no se regeneran en la corrida);
  el índice sí es por corrida y en **subproceso** (`index_vault`), porque el
  environment global de cocoindex no admite dos vaults en un mismo proceso
  (sonda T9 de Phase 1).
* **Distractores cercanos**: 5 familias de 4 notas (hidroponía, fotovoltaica,
  glaciares, epidemiología, compiladores) de modo que el top-5 no sea trivial y
  dos consultas de la misma familia compitan por los mismos vecinos.
* **Notas de un solo chunk** (~1 KB, por debajo del presupuesto de 1536 B del
  splitter). El techo de 1600 tokens de `search` recorta el payload **por score**:
  con chunks de tamaño completo devolvería 4 resultados y el denominador de
  «recall@5» dejaría de ser 5. El test afirma `truncated is False` y
  `len(results) == 5` para que el 5 sea real; si alguien engorda las notas, el
  test falla con el motivo en el mensaje.
* **`heading` se etiqueta donde aplica**: en las notas de un chunk el chunk empieza
  en `char_start = 0` y `heading_before(0)` es `None` (D13: nullable). Las dos
  notas largas sitúan la respuesta en una sección `##` **posterior**, cuyo chunk sí
  cita heading; ahí la etiqueta lo afirma.
* **Cero aserciones de latencia** (regla anti-flake): no se lee `took_ms` ni ningún
  reloj. La relevancia es determinista; el tiempo vive en `tests/benchmarks/`.
* **Guardas anti-tautología**, una por invariante:
  (a) `test_labels_are_distinct` — 10 etiquetas ⇒ 10 ficheros distintos y
      presentes en el fixture (si alguien las colapsa, el recall sería trivial);
  (b) `test_metric_discriminates` — con las etiquetas desplazadas una posición, el
      recall **baja de 1.0**: la métrica distingue, no aprueba siempre;
  (c) `test_empty_vault_fails_the_gate` — vault vacío ⇒ `search` responde
      `INDEX_EMPTY`, cero resultados y el gate cae (`0.0 < 1.0`). Sin `skip`: si el
      fixture desapareciera, el rojo es el comportamiento correcto.
* Este test es de **corrección**: entra en la suite diaria, sin `slow` ni `heavy`.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest
from support.mcp_server import index_vault, running_server, server_env

FIXTURES = Path(__file__).parents[1] / "fixtures"
RELEVANCE_VAULT = FIXTURES / "relevance_vault"
"""Vault de relevancia GRABADO (20 notas ES/EN) — se copia a tmp, nunca se regenera."""

LABELS_FILE = FIXTURES / "relevance_queries.json"
"""Etiquetas: `[{query, source_path, heading|null, lang}]` — datos, no lógica."""

TOP_K = 5
"""Slots del umbral (§6.2)."""

RECALL_TARGET = 1.0
"""Umbral de `docs/TRD.md` §6.2 (T0/CP-0) — se aplica, no se negocia."""

LABEL_COUNT = 10
"""n del umbral (§6.2)."""

RESOURCES = "00-resources"


@dataclass(frozen=True)
class Label:
    """Una consulta etiquetada: la pregunta y el fichero que la responde."""

    query: str
    source_path: str
    heading: str | None
    lang: str


def labels() -> list[Label]:
    """Lee las etiquetas del fixture (datos) y falla ruidosamente si faltan claves."""
    raw = json.loads(LABELS_FILE.read_text(encoding="utf-8"))
    assert isinstance(raw, list), "relevance_queries.json es una lista de etiquetas"
    out: list[Label] = []
    for entry in raw:
        assert isinstance(entry, dict), entry
        heading = entry["heading"]
        out.append(
            Label(
                query=str(entry["query"]),
                source_path=str(entry["source_path"]),
                heading=None if heading is None else str(heading),
                lang=str(entry["lang"]),
            )
        )
    return out


def recall(queries: Sequence[Label], found: Mapping[str, Sequence[str]], k: int = TOP_K) -> float:
    """Fracción de consultas cuyo `source_path` etiquetado aparece en el top-k devuelto.

    Recall de DOCUMENTO (no de chunk): basta con que un chunk del fichero esperado
    esté entre los `k` resultados — es lo que el agente necesita para citar.
    """
    assert queries, "sin etiquetas no hay recall que medir"
    hits = sum(1 for label in queries if label.source_path in list(found[label.query])[:k])
    return hits / len(queries)


def path_ranking(results: Mapping[str, dict[str, object]], query: str) -> list[str]:
    """`source_path` de los resultados del wire, en orden de score."""
    payload = results[query]
    items = payload["results"]
    assert isinstance(items, list), payload
    return [str(item["source_path"]) for item in items]  # type: ignore[index]


def missing_report(
    queries: Sequence[Label], found: Mapping[str, Sequence[str]], k: int = TOP_K
) -> str:
    """Diagnóstico legible: por consulta fallida, qué devolvió realmente el top-k."""
    lines = []
    for label in queries:
        ranked = list(found[label.query])[:k]
        if label.source_path not in ranked:
            lines.append(f"  ✗ {label.query!r} → esperaba {label.source_path}, top-{k}: {ranked}")
    return "\n".join(lines) or "  (ninguna consulta fallida)"


@pytest.fixture(scope="module")
def results_by_query(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[str, dict[str, object]]:
    """Copia el fixture a tmp, lo indexa en subproceso y corre las 10 consultas por stdio.

    Una sola sesión stdio para las 10 consultas (el modelo cargado vive entre
    llamadas, como en el harness); un solo indexado para los tres tests que
    consumen el resultado. El fixture se copia porque el índice se escribe en
    `<vault>/.tepochcalli/db/`: el repo no se toca.
    """
    vault = tmp_path_factory.mktemp("vault-t3-relevance")
    shutil.copytree(RELEVANCE_VAULT, vault, dirs_exist_ok=True)
    models_link = index_vault(vault)
    env = server_env(vault, models_link)

    async def run() -> dict[str, dict[str, object]]:
        payloads: dict[str, dict[str, object]] = {}
        async with running_server(env) as session:
            for label in labels():
                result = await session.call_tool("search", {"query": label.query, "top_k": TOP_K})
                text = result.content[0].text  # type: ignore[union-attr]
                payload = json.loads(text)
                assert not result.is_error, f"search falló para {label.query!r}: {payload}"
                payloads[label.query] = payload
        return payloads

    return asyncio.run(run())


# --- guarda (a): las etiquetas distinguen 10 ficheros reales ---------------------------


def test_labels_are_distinct() -> None:
    """10 etiquetas, 10 ficheros DISTINTOS y presentes: el recall no es trivial.

    Si alguien colapsa las etiquetas a un solo fichero (o a dos), el top-5 lo
    acierta por construcción y el test deja de medir recuperación.
    """
    entries = labels()
    assert len(entries) == LABEL_COUNT, f"el umbral de §6.2 es n={LABEL_COUNT}, no {len(entries)}"
    assert len({label.query for label in entries}) == LABEL_COUNT, "hay consultas repetidas"
    assert len({label.source_path for label in entries}) == LABEL_COUNT, (
        "las etiquetas deben apuntar a 10 ficheros distintos (si no, el top-5 acierta solo)"
    )
    for label in entries:
        assert label.source_path.startswith(f"{RESOURCES}/"), label.source_path
        assert (RELEVANCE_VAULT / label.source_path).is_file(), (
            f"etiqueta huérfana: {label.source_path} no existe en el fixture"
        )
    assert {label.lang for label in entries} == {"es", "en"}, (
        "el conjunto debe cubrir ES y EN (T4 mide la deriva del FTS con estas etiquetas)"
    )


# --- el gate: recall@5 = 1.0 -----------------------------------------------------------


def test_recall_at_5_is_one(results_by_query: dict[str, dict[str, object]]) -> None:
    """El umbral de §6.2: las 10 respuestas etiquetadas aparecen en el top-5.

    Afirma además que el top-5 es de 5: `truncated is False` y 5 resultados. Sin
    eso el denominador real sería menor y el «recall@5» mentiría.
    """
    entries = labels()
    for label in entries:
        payload = results_by_query[label.query]
        assert payload["truncated"] is False, (
            f"presupuesto de 1600 tokens recortó {label.query!r}: el top-5 debe ser de 5 "
            "(notas del fixture demasiado grandes)"
        )
        assert len(path_ranking(results_by_query, label.query)) == TOP_K, label.query
    found = {label.query: path_ranking(results_by_query, label.query) for label in entries}
    value = recall(entries, found)
    assert value == RECALL_TARGET, (
        f"recall@{TOP_K} = {value:.2f} < umbral {RECALL_TARGET} (§6.2, fijado en T0).\n"
        f"{missing_report(entries, found)}"
    )


def test_heading_labels_match_the_cited_section(
    results_by_query: dict[str, dict[str, object]],
) -> None:
    """Cuando la etiqueta declara `heading`, el resultado de ese fichero lo cita.

    `heading` es nullable (D13) y solo aplica a los ficheros que se parten en más
    de un chunk: el chunk que empieza en `char_start = 0` no tiene heading previo.
    """
    documented = [label for label in labels() if label.heading is not None]
    assert documented, "el fixture debe etiquetar al menos un heading real (notas largas)"
    for label in documented:
        items = results_by_query[label.query]["results"]
        assert isinstance(items, list)
        cited = [
            str(item["heading"])  # type: ignore[index]
            for item in items
            if str(item["source_path"]) == label.source_path  # type: ignore[index]
        ]
        assert label.heading in cited, (
            f"{label.query!r}: esperaba heading {label.heading!r} en un chunk de "
            f"{label.source_path}; el top-5 citó {cited}"
        )


# --- guarda (b): la métrica discrimina -------------------------------------------------


def test_metric_discriminates(results_by_query: dict[str, dict[str, object]]) -> None:
    """Con las etiquetas desplazadas una posición, el recall BAJA de 1.0.

    Demuestra que el 1.0 del test anterior no sale de un test que siempre pasa:
    mismas respuestas, etiquetas rotadas ⇒ la métrica cae. Si siguiera en 1.0, el
    conjunto de etiquetas no estaría discriminando y el gate sería una tautología.
    """
    entries = labels()
    shifted = [
        Label(
            query=entries[index].query,
            source_path=entries[(index + 1) % len(entries)].source_path,
            heading=None,
            lang=entries[index].lang,
        )
        for index in range(len(entries))
    ]
    found = {label.query: path_ranking(results_by_query, label.query) for label in entries}
    value = recall(shifted, found)
    assert value < RECALL_TARGET, (
        f"recall con etiquetas desplazadas = {value:.2f}: la métrica no discrimina "
        "(las etiquetas reales y las rotadas dan lo mismo)"
    )


# --- guarda (c): sin vault no hay verde ------------------------------------------------


def test_empty_vault_fails_the_gate(tmp_path: Path) -> None:
    """Un vault VACÍO responde `INDEX_EMPTY` y el gate cae: 0.0 < 1.0, nunca `skip`.

    Si el fixture desapareciera (o alguien vaciara `00-resources/`), el test tiene
    que ponerse rojo por la razón correcta: no hay nada que recuperar.
    """
    vault = tmp_path / "vault-t3-empty"
    (vault / RESOURCES).mkdir(parents=True)

    async def run() -> list[dict[str, object]]:
        payloads: list[dict[str, object]] = []
        async with running_server(server_env(vault)) as session:
            for label in labels():
                result = await session.call_tool("search", {"query": label.query, "top_k": TOP_K})
                payloads.append(json.loads(result.content[0].text))  # type: ignore[union-attr]
        return payloads

    payloads = asyncio.run(run())
    for payload in payloads:
        assert "results" not in payload, f"un vault vacío no devuelve resultados: {payload}"
        assert payload["error"]["code"] == "INDEX_EMPTY", payload  # type: ignore[index]
    empty = {label.query: [] for label in labels()}
    assert recall(labels(), empty) == 0.0 < RECALL_TARGET
