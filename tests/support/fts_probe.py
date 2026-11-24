"""Sonda del mecanismo de deriva FTS ES/EN (Phase 6 · T4).

Por qué existe
--------------
El corpus de escala de T1 (`tests/support/corpus.py`) usa un vocabulario FIJO de
~50 palabras sin variación morfológica: en ese corpus el stemming no puede
cambiar nada, así que la medición de recall del criterio 3 **no puede demostrar**
la deriva del FTS con `language="English"` sobre texto español. Esta sonda sí:
un vault diminuto (9 objetivos + 52 distractores) donde cada consulta usa una
forma flexiva que su nota **no** contiene como token.

Qué mide
--------
Para cada par `(query, nota esperada)` publica, con el MISMO vault:

* rango del fichero esperado en la pierna **FTS sola** (`query_type="fts"`,
  BM25, profundidad 50) con el índice FTS declarado en **inglés** (el que
  declara el flow: `app.py` → `declare_fts_index(column="text")`, default
  `language="English"`) y, tras reconstruirlo con `language="Spanish"`, con el
  índice **español**;
* si el **híbrido** de producción (`LanceDBChunkReader.search`, ANN+FTS+RRF) lo
  devuelve en el top-5 con cada configuración.

Los dos últimos pares son controles en inglés (`budgets`, `run`): enseñan el
precio del cambio (un stemmer español deja de unir las formas inglesas).

Ventana de configuración (verificada, no de memoria)
----------------------------------------------------
`lancedb==0.40.0` (el pin del venv): `Table.create_fts_index(..., language: str
= "English", ...)` existe y `lancedb/index.py` mapea `"es" → "Spanish"`
(`lang_mapping`); cocoindex 1.0.25 lo expone como `declare_fts_index(language=…)`
(`connectors/lancedb/_target.py`). Un solo índice FTS gobierna la columna
`text`: la config es del ÍNDICE, no del query.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from typing import Any

from corpus import RESOURCES_DIR
from model_cache import link_model_cache, resolve_model_cache

PROBE_TARGETS: tuple[tuple[str, str, str], ...] = (
    ("presupuestos", "presupuesto.md", "El presupuesto del ayuntamiento se revisa cada año."),
    ("evaluaciones", "evaluacion.md", "La evaluación del alumnado se publica en junio."),
    ("ciudades", "ciudad.md", "La ciudad cambia su normativa de residuos."),
    ("mociones", "mocion.md", "La moción vecinal se debate en el pleno."),
    ("países", "pais.md", "El país firma el acuerdo climático."),
    ("investigar", "investigacion.md", "El grupo investigó el origen del brote."),
    ("aprobadas", "aprobado.md", "El informe fue aprobado por unanimidad."),
    ("budgets", "budget.md", "The city budget was approved last week."),
    ("run", "running.md", "We are running the benchmark on the old laptop."),
)
"""`(query, fichero esperado, frase del fichero con la OTRA forma)`."""


def _expected(name: str) -> str:
    """`source_path` vault-relativo del fichero de la sonda (el índice cita con la raíz)."""
    return f"{RESOURCES_DIR}/{name}"


PROBE_EN_CONTROLS = frozenset({_expected("budget.md"), _expected("running.md")})
"""Los dos pares ingleses: miden lo que cuesta indexar con stemmer español."""

PROBE_DISTRACTORS = 52
"""Relleno: sin él (`top_k=5` sobre 9 filas) el recall sería un techo y no mediría nada."""

PROBE_FILLER = (
    "Nota de trabajo {i:02d} sobre archivos y carpetas del sistema. El proceso de "
    "lectura y escritura del ordenador usa la pantalla, el teclado y la ventana. "
    "Cada ejemplo y cada método produce un resultado, un valor o una lista del "
    "grupo de trabajo. Tiempo, lugar, mundo, vida, caso, parte y forma."
)

FTS_DEPTH = 50


def _docs() -> dict[str, str]:
    """Documentos de la sonda: un objetivo por par morfológico + distractores distintos."""
    docs: dict[str, str] = {}
    for _, name, sentence in PROBE_TARGETS:
        docs[name] = f"# {name}\n\n{sentence} Documento de referencia del expediente."
    for index in range(PROBE_DISTRACTORS):
        docs[f"distractor-{index:02d}.md"] = f"# Distractor {index:02d}\n\n" + PROBE_FILLER.format(
            i=index
        )
    for query, name, _ in PROBE_TARGETS:
        if query.lower() in {token.lower() for token in docs[name].split()}:
            raise SystemExit(f"la sonda no discrimina: {query!r} ya es token de {name}")
    return docs


def _fts_index(vault: Path) -> dict[str, Any]:
    """Estado REAL del índice FTS (nombre, columnas, `language`) — leído, no supuesto."""
    import lancedb
    from tepochcalli_flow.layout import DB_RELPATH, TABLE_NAME

    table = lancedb.connect(str(vault / DB_RELPATH)).open_table(TABLE_NAME)
    fts = [cfg for cfg in table.list_indices() if cfg.index_type == "FTS"]
    if len(fts) != 1:
        # Dos índices FTS sobre la MISMA columna son ambiguos al consultar
        # (`fts_columns` no los distingue): la sonda exige exactamente uno.
        raise SystemExit(f"[probe] {len(fts)} índices FTS en 'text': medición ambigua")
    details = fts[0].index_details or {}
    return {
        "name": fts[0].name,
        "columns": list(fts[0].columns),
        "language": details.get("language"),
        "stem": details.get("stem"),
        "remove_stop_words": details.get("remove_stop_words"),
    }


def _rebuild_fts(vault: Path, language: str) -> dict[str, Any]:
    """Reemplaza el índice FTS `text` con `language` (API real del pin, no memoria)."""
    import lancedb
    from tepochcalli_flow.layout import DB_RELPATH, TABLE_NAME

    table = lancedb.connect(str(vault / DB_RELPATH)).open_table(TABLE_NAME)
    # `name="text"` = el nombre que declara cocoindex; con `replace=True` lo
    # REEMPLAZA (sin nombre, lancedb crea un segundo índice `text_idx` y deja la
    # columna con dos configuraciones: ambigua y no comparable).
    table.create_fts_index("text", name="text", language=language, replace=True)
    return _fts_index(vault)


def _arm(vault: Path, language: str, top_k: int) -> list[dict[str, Any]]:
    """Híbrido (producción) + pierna FTS sola para los 9 pares, con el índice actual."""
    import lancedb
    from tepochcalli_flow.adapters.lancedb_reader import LanceDBChunkReader
    from tepochcalli_flow.config import load_config
    from tepochcalli_flow.layout import DB_RELPATH, TABLE_NAME
    from tepochcalli_mcp.backend import _read_embedder

    config = load_config(vault)
    config.apply_model_cache_env()
    reader = LanceDBChunkReader(vault / DB_RELPATH, embed=_read_embedder(config))

    async def run() -> list[dict[str, Any]]:
        db = await lancedb.connect_async(str(vault / DB_RELPATH))
        try:
            table = await db.open_table(TABLE_NAME)
            records: list[dict[str, Any]] = []
            for query, name, _ in PROBE_TARGETS:
                expected = _expected(name)
                hybrid = [chunk.source_path for chunk in await reader.search(query, top_k)]
                fts = await table.search(query, query_type="fts", fts_columns="text")
                rows = await fts.select(["source_path"]).limit(FTS_DEPTH).to_list()
                paths = [str(row["source_path"]) for row in rows]
                records.append(
                    {
                        "language": language,
                        "query": query,
                        "expected": expected,
                        "hybrid_hit": expected in hybrid,
                        "fts_rank": paths.index(expected) + 1 if expected in paths else None,
                    }
                )
            return records
        finally:
            db.close()  # type: ignore[no-untyped-call]

    return asyncio.run(run())


def _summary(arm: list[dict[str, Any]]) -> dict[str, Any]:
    """Recuento ES/EN de aciertos híbridos y de pares que el BM25 llega a rankear."""
    es = [record for record in arm if record["expected"] not in PROBE_EN_CONTROLS]
    en = [record for record in arm if record["expected"] in PROBE_EN_CONTROLS]
    return {
        "es_hits": sum(record["hybrid_hit"] for record in es),
        "es_fts_ranked": sum(record["fts_rank"] is not None for record in es),
        "es_n": len(es),
        "en_hits": sum(record["hybrid_hit"] for record in en),
        "en_fts_ranked": sum(record["fts_rank"] is not None for record in en),
        "en_n": len(en),
    }


def run_probe(vault: Path, *, vault_root_env: str, top_k: int) -> dict[str, Any]:
    """Construye el vault de la sonda, mide inglés vs español y devuelve el bloque JSON."""
    from tepochcalli_flow import app as flow_app

    os.environ[vault_root_env] = str(vault)
    if vault.exists():
        shutil.rmtree(vault)  # vault de la sonda: se reconstruye entero en cada corrida
    (vault / RESOURCES_DIR).mkdir(parents=True)
    for name, text in _docs().items():
        (vault / RESOURCES_DIR / name).write_text(text, encoding="utf-8")
    link_model_cache(vault, resolve_model_cache())
    report = flow_app.refresh_blocking()
    expected = len(PROBE_TARGETS) + PROBE_DISTRACTORS
    if report.indexed != expected:
        raise SystemExit(f"[probe] indexed={report.indexed} != {expected}")

    # Explícito: el índice de la sonda es el de ESTA medición (el flow lo declara
    # en inglés; se reconstruye para no depender de un estado previo).
    english_index = _rebuild_fts(vault, "English")
    english = _arm(vault, "English", top_k)
    spanish_index = _rebuild_fts(vault, "Spanish")
    spanish = _arm(vault, "Spanish", top_k)
    return {
        "indexed": report.indexed,
        "rows_expected": expected,
        "top_k": top_k,
        "english_default": {"index": english_index, "records": english, **_summary(english)},
        "spanish": {"index": spanish_index, "records": spanish, **_summary(spanish)},
        "source": (
            "lancedb==0.40.0: Table.create_fts_index(language=...) + lancedb/index.py "
            "lang_mapping['es']='Spanish'; cocoindex 1.0.25: declare_fts_index(language=...)"
        ),
    }
