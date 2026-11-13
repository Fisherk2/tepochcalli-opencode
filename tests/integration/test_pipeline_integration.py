"""Integración T6: walk → parse → split → embed → fila LanceDB con cita completa.

Fuentes de verdad:

* specs/spec-rag-engine.md §Target LanceDB + índices — tabla `chunks` sobre
  `.tepochcalli/db/tepochcalli.lance`, índice ANN sobre `embedding` + FTS sobre
  `text`, esquema de 10 campos con `heading` **nullable** (D13) y los otros
  cuatro campos de cita no nulos.
* specs/spec-rag-engine.md §Embeddings — E1 (`device` leído de config, default
  `"cpu"`), F6 (`normalize_embeddings` vive en `embed()`), ADR-006 (384 dims y
  `model` por fila para detectar índices mixtos).
* tasks/todo.md → T6 AC — **M2** (100% de las filas escritas con cita no nula,
  `source_path` POSIX `00-resources/`-prefijado con anidamiento intacto,
  identidad F1 `text[char_start:char_end] == text`) y **M3** (indexación con
  cero llamadas LLM: ni módulos LLM importados ni salidas de red).

Decisiones de test, documentadas a propósito:

* **Cache de modelo FUERA del repo.** El MiniLM (~470MB) nunca debe aterrizar en
  `obsidian-workspace/.tepochcalli/models/` (payload). El cache lo resuelve
  `model_cache`: `HF_HOME` externo (CI) > spike T1 si ya existe >
  `~/.cache/huggingface` — jamás una ruta `/tmp` obligatoria (T11). El vault
  temporal crea `.tepochcalli/models` como **symlink** a ese cache: la
  `apply_model_cache_env()` real del lifespan apunta —como en producción— al
  vault de prueba, pero el binario vive fuera del repo y persiste entre corridas.
* **M3(b) a doble sello.** El `update_blocking()` corre con `socket.connect` de
  `AF_INET`/`AF_INET6` bloqueado (cualquier intento queda registrado y un
  intento = fallo del test) y `HF_HUB_OFFLINE=1` (verificado por probe que el
  modelo cacheado carga con **0** intentos de red; el patch de socket sigue
  siendo quien prohibe cualquier otra salida).
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import os
import shutil
import socket
import sys
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, fields
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, get_args, get_type_hints

import cocoindex as coco
import numpy as np
import pytest
from cocoindex.connectors import lancedb
from cocoindex.ops.sentence_transformers import SentenceTransformerEmbedder
from cocoindex.resources.schema import VectorSchema
from model_cache import link_model_cache, resolve_model_cache
from tepochcalli_flow import app as flow_app
from tepochcalli_flow import citation
from tepochcalli_flow import config as flow_config
from tepochcalli_flow import models as flow_models
from tepochcalli_flow import parsers as flow_parsers

FIXTURE_VAULT = Path(__file__).parents[1] / "fixtures" / "vault_markdown"

BOM = "\ufeff"
"""BOM UTF-8 como carácter: la lectura estricta lo conserva en el string de ambos decoders."""

# Contrato de fuentes del vault temporal: la fixture dorada (2 md) + un .txt plano SIN
# headings (D13) + un .md con BOM (decodificador único, F1) + un .md duplicado byte a
# byte de `anidada.md` (unicidad de ids entre archivos, T8) — los últimos dos creados
# por este módulo, como `plano.txt`.
EXPECTED_SOURCE_PATHS = {
    "00-resources/nota.md",
    "00-resources/sub/carpeta/anidada.md",
    "00-resources/plano.txt",
    "00-resources/con_bom.md",
    "00-resources/duplicada.md",
}

PLAIN_TXT_CONTENT = (
    "Texto plano de prueba sin jerarquía de headings.\n\n"
    "Segundo párrafo: un archivo sin ningún heading padre debe producir chunks "
    "cuyo campo `heading` exista en la fila con valor null —nunca una cadena "
    "vacía— según D13 en spec-rag-engine.md §Target LanceDB.\n"
)

CON_BOM_CONTENT = (
    "# Nota con BOM\n\n"
    "Este archivo de prueba comienza con un BOM UTF-8. El decodificador estricto lo "
    "conserva como carácter, y los offsets F1 almacenados deben reproducir exactamente "
    "`parsers.extract_text` sobre ESTE string, BOM incluido: si la ruta de escritura "
    "usara otro decodificador —`utf-8-sig` lo elimina, `errors='replace'` insera "
    "U+FFFD—, los offsets se desplazarían y la identidad se rompería.\n\n"
    + "Relleno para que el primer corte caiga ANTES de la segunda sección: "
    * 24
    + "\n\n## Sección tras el BOM\n\n"
    "Cierre breve: este chunk secundario aún cita el heading bajo el BOM.\n"
)
CON_BOM_BYTES = b"\xef\xbb\xbf" + CON_BOM_CONTENT.encode("utf-8")
"""Archivo con BOM real (bytes): se escribe crudo para que el BOM llegue al disco."""

CONTRACT_FIELDS = [
    "id",
    "source_path",
    "doc_kind",
    "heading",
    "char_start",
    "char_end",
    "text",
    "embedding",
    "model",
    "indexed_at",
]

LLM_MODULES = frozenset({"litellm", "openai", "anthropic"})


@dataclass(frozen=True)
class IndexedRun:
    """Resultado de la corrida de indexación del vault temporal (T6)."""

    vault: Path
    """Raíz del vault temporal indexado."""

    rows: list[dict[str, object]]
    """Todas las filas leídas de la tabla `chunks` tras el update."""

    blocked_attempts: list[object]
    """Direcciones IPv4/IPv6 que el parche de socket bloqueó durante el update."""

    update_completed: bool
    """True ⇔ `update_blocking()` retornó sin excepción con la red bloqueada."""

    model_cache: Path
    """Cache estable que resuelve el symlink `.tepochcalli/models` del vault."""


@pytest.fixture(scope="module")
def indexed_run(tmp_path_factory: pytest.TempPathFactory) -> Iterator[IndexedRun]:
    """Vault temporal indexado con la red de salida bloqueada (una sola corrida).

    El update es lo suficientemente caro (embeddings CPU) como para correrlo una
    vez por módulo: todos los tests de M2/M3 leen de esta única corrida. El
    `yield` mantiene el env del vault activo durante los tests y lo restaura en
    el teardown.
    """
    monkeypatch = pytest.MonkeyPatch()
    try:
        vault = tmp_path_factory.mktemp("vault-t6")
        shutil.copytree(FIXTURE_VAULT, vault, dirs_exist_ok=True)
        (vault / citation.RESOURCES_DIR / "plano.txt").write_text(
            PLAIN_TXT_CONTENT, encoding="utf-8"
        )
        (vault / citation.RESOURCES_DIR / "con_bom.md").write_bytes(CON_BOM_BYTES)
        # Duplicada byte a byte de la fixture anidada: los MISMOS chunks de texto en DOS
        # archivos distintos —pin de T8 para la unicidad de ids entre archivos.
        (vault / citation.RESOURCES_DIR / "duplicada.md").write_bytes(
            (FIXTURE_VAULT / citation.RESOURCES_DIR / "sub" / "carpeta" / "anidada.md").read_bytes()
        )

        model_cache = resolve_model_cache()
        models_link = link_model_cache(vault, model_cache)

        monkeypatch.setenv("HF_HOME", str(models_link))
        monkeypatch.setenv("SENTENCE_TRANSFORMERS_HOME", str(models_link))
        monkeypatch.setenv(flow_app.VAULT_ROOT_ENV, str(vault))
        # El lifespan fija `db_path` solo si COCOINDEX_DB no está definida: se
        # demuestra deliberadamente ese default (<vault>/.tepochcalli/db/…, D14).
        monkeypatch.delenv("COCOINDEX_DB", raising=False)

        _warm_model_cache()

        blocked_attempts: list[object] = []
        with _outbound_blocked(blocked_attempts):
            flow_app.app.update_blocking()
        update_completed = True

        rows = asyncio.run(_read_all_rows(vault))
        yield IndexedRun(
            vault=vault,
            rows=rows,
            blocked_attempts=blocked_attempts,
            update_completed=update_completed,
            model_cache=model_cache,
        )
    finally:
        monkeypatch.undo()


# --- M2: metadatos de cita en el 100% de las filas -----------------------------


def test_update_writes_rows_for_exactly_the_indexable_files(
    indexed_run: IndexedRun,
) -> None:
    """El update materializa filas SOLO para los indexables (`.oculto/` y `blob.bin` fuera)."""
    assert indexed_run.update_completed
    assert len(indexed_run.rows) >= 5  # nota.md ≥3 + anidada.md ≥1 + plano.txt/BOM/duplicada ≥1
    assert {row["source_path"] for row in indexed_run.rows} == EXPECTED_SOURCE_PATHS
    ids = [row["id"] for row in indexed_run.rows]
    assert all(isinstance(value, int) for value in ids)
    assert len(ids) == len(set(ids))  # clave primaria: ids únicos en la tabla


def test_duplicate_chunk_text_across_files_gets_unique_ids_t8(
    indexed_run: IndexedRun,
) -> None:
    """T8: chunks byte-idénticos en dos archivos reciben ids distintos.

    `duplicada.md` es un calco byte a byte de `anidada.md`, así que sus chunks
    de texto se repiten EXACTOS en dos `source_path` distintos. El `IdGenerator`
    de `index_file` (uno por componente de archivo) reparte ids propios; si una
    refactorización llegara a colapsarlos (p. ej. un `generate_id` memoizado por
    texto), este pin fallaría antes que el contrato de `search` de T8.
    """
    originales = [
        row
        for row in indexed_run.rows
        if row["source_path"] == "00-resources/sub/carpeta/anidada.md"
    ]
    duplicadas = [
        row for row in indexed_run.rows if row["source_path"] == "00-resources/duplicada.md"
    ]
    assert originales and duplicadas, "la fixture duplicada debe indexarse junto a su original"

    comunes = {row["text"] for row in originales} & {row["text"] for row in duplicadas}
    assert comunes, "los chunks de duplicada.md deben ser byte-idénticos a los de anidada.md"

    # Entre archivos: el mismo texto NO colisiona en id.
    for texto in comunes:
        id_original = next(row["id"] for row in originales if row["text"] == texto)
        id_duplicado = next(row["id"] for row in duplicadas if row["text"] == texto)
        assert id_original != id_duplicado, f"colisión de id para chunk duplicado: {texto[:60]!r}"

    # Por archivo (ordinal): cada archivo reparte ids propios sin repetir.
    for grupo in (originales, duplicadas):
        ids = [row["id"] for row in grupo]
        assert len(ids) == len(set(ids))


def test_every_row_carries_complete_non_null_citation_metadata_m2(
    indexed_run: IndexedRun,
) -> None:
    """M2: `source_path`/`char_start`/`char_end`/`doc_kind` no nulos y `heading` presente.

    «Presente» significa que la clave existe en la fila aunque su valor pueda ser
    `None` (D13); los otros cuatro campos de cita jamás son `None`.
    """
    assert indexed_run.rows
    for row in indexed_run.rows:
        for field_name in ("source_path", "char_start", "char_end", "doc_kind"):
            assert row[field_name] is not None, f"{field_name} nulo en {row['source_path']}"
        assert "heading" in row  # presente, aunque el valor pueda ser None (D13)
        assert row["heading"] is None or isinstance(row["heading"], str)
        assert isinstance(row["char_start"], int)
        assert isinstance(row["char_end"], int)
        assert row["char_start"] < row["char_end"]


def test_source_paths_are_posix_vault_relative_and_preserve_nesting_m2(
    indexed_run: IndexedRun,
) -> None:
    """M2: `source_path` POSIX, relativo al vault con prefijo `00-resources/` y anidado."""
    for row in indexed_run.rows:
        source_path = row["source_path"]
        assert isinstance(source_path, str)
        assert "\\" not in source_path  # POSIX, nunca separador Windows
        assert source_path.startswith("00-resources/")
        pure = PurePosixPath(source_path)
        assert not pure.is_absolute()
        assert ".." not in pure.parts
    assert "00-resources/sub/carpeta/anidada.md" in {
        row["source_path"] for row in indexed_run.rows
    }  # anidamiento de tres niveles intacto (D9.1)


def test_slice_identity_holds_for_every_row_written_m2(indexed_run: IndexedRun) -> None:
    """M2: `text[char_start:char_end] == text` en el 100% de las filas (identidad F1)."""
    texts_by_path = {
        source_path: (indexed_run.vault / source_path).read_text(encoding="utf-8")
        for source_path in EXPECTED_SOURCE_PATHS
    }
    checked = 0
    for row in indexed_run.rows:
        source_path = row["source_path"]
        char_start = row["char_start"]
        char_end = row["char_end"]
        chunk_text = row["text"]
        assert isinstance(source_path, str)
        assert isinstance(char_start, int)
        assert isinstance(char_end, int)
        assert isinstance(chunk_text, str)
        document = texts_by_path[source_path]
        assert citation.verify_slice_identity(document, char_start, char_end, chunk_text), (
            f"identidad F1 rota en {source_path} [{char_start}, {char_end})"
        )
        checked += 1
    assert checked == len(indexed_run.rows)


def test_bom_file_offsets_reproduce_extract_text_exactly_m2(
    indexed_run: IndexedRun,
) -> None:
    """Decodificador único + F1: en un archivo con BOM los offsets reproducen `extract_text`.

    El documento de referencia lo lee `parsers.extract_text` (UTF-8 estricto, BOM
    conservado como carácter) —el MISMO string que debe producir la ruta de
    escritura `app.index_file`. Con `utf-8-sig` (BOM auto-detectado) o con
    `errors="replace"` los offsets se desplazarían y la identidad de cada fila
    de `con_bom.md` rompería aquí.
    """
    ruta = indexed_run.vault / citation.RESOURCES_DIR / "con_bom.md"
    documento = flow_parsers.extract_text(ruta)
    assert documento.startswith(BOM)  # contrato: el BOM viaja dentro del string

    filas = [row for row in indexed_run.rows if row["source_path"] == "00-resources/con_bom.md"]
    assert len(filas) >= 2  # >1536 bytes: varios chunks, al menos uno con char_start > 0
    for row in filas:
        char_start = row["char_start"]
        char_end = row["char_end"]
        chunk_text = row["text"]
        assert isinstance(char_start, int)
        assert isinstance(char_end, int)
        assert isinstance(chunk_text, str)
        assert citation.verify_slice_identity(documento, char_start, char_end, chunk_text), (
            f"identidad F1 rota en con_bom.md [{char_start}, {char_end})"
        )
    assert any(row["heading"] == "Nota con BOM" for row in filas), (
        "el BOM no debe ocultar el heading ATX inicial para los chunks posteriores"
    )


def test_heading_is_stored_as_null_for_files_without_hierarchy_d13(
    indexed_run: IndexedRun,
) -> None:
    """D13: `plano.txt` (sin headings) escribe `heading=null`; `nota.md` escribe texto."""
    plain_rows = [row for row in indexed_run.rows if row["source_path"] == "00-resources/plano.txt"]
    assert plain_rows
    assert all(row["heading"] is None for row in plain_rows)
    assert any(isinstance(row["heading"], str) and row["heading"] for row in indexed_run.rows), (
        "alguna fila con heading padre no nulo (nota.md tiene secciones ##)"
    )


def test_model_matches_configured_embedder_and_vector_dimension_is_384_m2(
    indexed_run: IndexedRun,
) -> None:
    """M2: `model` = id configurado (ADR-006) y todo vector mide 384 dims."""
    for row in indexed_run.rows:
        assert row["model"] == citation.model_id() == flow_config.DEFAULT_EMBEDDING_MODEL
        embedding = row["embedding"]
        assert len(embedding) == flow_config.DEFAULT_EMBEDDING_DIMS == 384
    assert indexed_run.rows[0]["indexed_at"] is not None
    indexed_at = indexed_run.rows[0]["indexed_at"]
    assert isinstance(indexed_at, str)
    datetime.fromisoformat(indexed_at)  # ISO-8601 legible, nunca null


# --- M3: cero llamadas LLM -----------------------------------------------------


def test_update_completes_with_outbound_network_blocked_m3(
    indexed_run: IndexedRun,
) -> None:
    """M3(b): el update completa con AF_INET/AF_INET6 bloqueados y sin ni un intento."""
    assert indexed_run.update_completed, "update_blocking() no completó con la red bloqueada"
    assert indexed_run.blocked_attempts == [], (
        f"hubo {len(indexed_run.blocked_attempts)} intentos de salida a red: "
        f"{indexed_run.blocked_attempts[:5]}"
    )


def test_no_llm_client_modules_are_imported_during_indexing_m3(
    indexed_run: IndexedRun,
) -> None:
    """M3(a): tras indexar, ni `litellm` ni `openai` ni `anthropic` están en `sys.modules`."""
    imported = sorted(name for name in sys.modules if name.split(".")[0] in LLM_MODULES)
    assert imported == []
    assert indexed_run.rows  # la corrida que no importó LLMs sí escribió filas


# --- Índices ANN + FTS ----------------------------------------------------------


def test_ann_vector_index_and_fts_index_are_declared_on_the_table(
    indexed_run: IndexedRun,
) -> None:
    """Ambos índices declarados en el flow existen como índices de la tabla LanceDB."""
    indices = asyncio.run(_list_indices(indexed_run.vault))
    names = {info.name for info in indices}
    assert "embedding" in names  # declare_vector_index(column="embedding")
    assert "text" in names  # declare_fts_index(column="text")
    by_name = {info.name: info for info in indices}
    assert "embedding" in list(by_name["embedding"].columns)
    assert "text" in list(by_name["text"].columns)


def test_vector_query_and_fts_query_both_return_rows(indexed_run: IndexedRun) -> None:
    """La búsqueda vectorial (ANN) y la léxica (FTS) devuelven filas sobre la tabla."""
    vector_hits, fts_hits = asyncio.run(_query_both_indexes(indexed_run.vault))
    assert vector_hits, "la consulta vectorial devolvió cero filas"
    assert fts_hits, "la consulta FTS ('markdown') devolvió cero filas"
    assert {hit["source_path"] for hit in fts_hits} <= EXPECTED_SOURCE_PATHS


# --- Contrato del esquema (ChunkRow) --------------------------------------------


def test_chunk_row_has_exactly_the_ten_contract_fields() -> None:
    """`ChunkRow` expone exactamente los 10 campos del contrato de T9/Phase 2."""
    assert [field.name for field in fields(flow_models.ChunkRow)] == CONTRACT_FIELDS


def test_heading_field_is_nullable_and_citation_fields_are_not() -> None:
    """D13 a nivel de esquema: `heading` nullable; los 4 campos de cita, no nulos."""
    schema = asyncio.run(_schema_from_chunk_row())
    nullable = {name: column.nullable for name, column in schema.columns.items()}
    assert nullable["heading"] is True
    for field_name in ("source_path", "char_start", "char_end", "doc_kind"):
        assert nullable[field_name] is False, f"{field_name} debe ser no nulo (D13)"

    hints = get_type_hints(flow_models.ChunkRow, include_extras=True)
    assert hints["heading"] == str | None


def test_embedding_dims_come_from_the_embedder_annotation_not_a_literal() -> None:
    """`Annotated[NDArray, EMBEDDER]`: las dims las resuelve el embedder (no un 384 fijo)."""
    hints = get_type_hints(flow_models.ChunkRow, include_extras=True)
    annotation_args = get_args(hints["embedding"])
    assert annotation_args[0] is not None
    assert flow_models.EMBEDDER in annotation_args[1:]  # la ancla es la ContextKey real
    assert flow_models.EMBEDDER is flow_app.EMBEDDER  # una sola key, compartida con app


# --- E1: device y provider de config -------------------------------------------


def test_embedder_is_built_with_the_configured_model_and_device_e1(
    indexed_run: IndexedRun,
) -> None:
    """E1/T6: el embedder del lifespan carga el **path estable** `<slug>@<sha>` y `cpu`."""
    assert indexed_run.update_completed
    embedder = _embedder_from_default_env()
    model_path = flow_config.load_config(indexed_run.vault).embedding_model_path
    assert embedder.__coco_memo_key__() == (
        str(model_path),
        flow_config.DEFAULT_EMBEDDING_DEVICE,
        False,
    )


def test_apply_model_cache_env_runs_before_the_embedder_is_constructed() -> None:
    """AC: `apply_model_cache_env()` ANTES de construir el embedder en el lifespan.

    El orden no es observable en runtime (el embedder carga el modelo de forma
    perezosa, dentro de `embed()`), así que se afirma sobre el orden fuente del
    lifespan — la única prueba directa disponible.

    Limitación conocida (como su hermana de `test_elapsed_ms`): inspecciona
    TEXTO fuente — una refactorización equivalente pero de otro estilo (p. ej.
    extraer el orden a otro módulo) rompería este assert aunque el runtime
    siga bien; si eso pasa se reescribe la prueba, no el orden del AC.
    **T6 aplicó esa cláusula:** la construcción se extrajo a la fábrica
    `_build_embedder` (Strategy por provider), así que el ancla pasó de
    `SentenceTransformerEmbedder` a la LLAMADA `_build_embedder(config)` —
    que sigue DESPUÉS de `apply_model_cache_env` en el cuerpo del lifespan,
    y la fábrica internamente no construye nada antes de su propia entrada.
    """
    source = _lifespan_source()
    assert source.index("apply_model_cache_env") < source.index("_build_embedder(config)")


def test_model_cache_lands_outside_the_repo_never_in_the_payload(
    indexed_run: IndexedRun,
) -> None:
    """El cache de modelo del vault temporal resuelve FUERA del repo (payload intacto)."""
    models_link = indexed_run.vault / ".tepochcalli" / "models"
    assert models_link.is_symlink()
    assert models_link.resolve() == indexed_run.model_cache.resolve()
    assert os.environ["HF_HOME"] == str(models_link)
    assert os.environ["SENTENCE_TRANSFORMERS_HOME"] == str(models_link)
    payload_models = Path(__file__).parents[2] / "obsidian-workspace" / ".tepochcalli" / "models"
    assert not payload_models.exists()  # jamás se descargó el modelo en el payload


def test_engine_state_default_lives_under_the_gitignored_db_dir_d14(
    indexed_run: IndexedRun,
) -> None:
    """D14: el estado derivado del engine cae en `db/` (gitignored), nunca en `flow/` (fuente).

    La regla gitignore de `db/` la afirma T2 (`.gitignore` → `…/.tepochcalli/db/`);
    aquí se ancla la RUTA por código: co-localizada con LanceDB, un solo
    `rm -r .tepochcalli/db/` reconstruye ambos (spec-rag-engine §Rollback).
    """
    assert flow_app.ENGINE_STATE_RELPATH == Path(".tepochcalli/db/cocoindex")
    assert flow_app.ENGINE_STATE_RELPATH.parts[:2] == (".tepochcalli", "db")
    assert flow_app.ENGINE_STATE_RELPATH.parent == flow_app.DB_RELPATH.parent
    # El update de esta corrida (sin COCOINDEX_DB) materializó el estado ahí:
    assert (indexed_run.vault / flow_app.ENGINE_STATE_RELPATH).exists()


def test_litellm_provider_wires_lifespan_with_lite_llm_embedder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T6 INVIERTE el sentido de este test: `provider = "litellm"` YA se cablea.

    Antes (Phase 1) el lifespan lanzaba `EmbeddingProviderNotImplementedError`
    — T6 existe para levantar esa limitación. Ahora provee
    `LiteLLMEmbedder(model, api_key=…)` con la clave de `api_key_env` leída
    del entorno, SIN llamada a la API en el lifespan (el constructor es
    inerte; la dim se descubre en `__coco_vector_schema__`, dentro del update).
    `COCOINDEX_DB` se fija para saltar el settings del stub de builder.
    """
    from cocoindex.ops.litellm import LiteLLMEmbedder  # import perezoso: litellm pesa

    monkeypatch.setenv(flow_app.VAULT_ROOT_ENV, str(tmp_path))
    monkeypatch.setenv("COCOINDEX_DB", str(tmp_path / "engine-state"))
    monkeypatch.setenv("TEPOCHCALLI_EMBED_API_KEY", "sk-t6-fake-key")
    config_dir = tmp_path / ".tepochcalli" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "tepochcalli.toml").write_text(
        '[embedding]\nprovider = "litellm"\nmodel = "openai/text-embedding-3-small"\n',
        encoding="utf-8",
    )
    builder = _RecordingBuilder()
    lifespan = flow_app.provide_resources(builder)
    asyncio.run(_advance_and_close(lifespan))  # RED: hoy lanza el error tipado viejo

    embedders = [value for key, value in builder.provided if key is flow_app.EMBEDDER]
    assert len(embedders) == 1, "el lifespan debe proveer EXACTAMENTE el embedder"
    embedder = embedders[0]
    assert isinstance(embedder, LiteLLMEmbedder)
    # Memo key canónica (fuente instalada): (model, kwargs) — la clave viaja en kwargs.
    assert embedder.__coco_memo_key__() == (
        "openai/text-embedding-3-small",
        {"api_key": "sk-t6-fake-key"},
    )
    assert any(key is flow_app.LANCE_DB for key, _ in builder.provided), (
        "la conexión LanceDB se provee ANTES que el embedder (orden del lifespan)"
    )


# --- helpers ---------------------------------------------------------------------


def _warm_model_cache() -> None:
    """Carga el modelo UNA vez con red permitida (después: solo lectura de cache).

    Corre antes de bloquear sockets —el env ya apunta al symlink del vault—: en
    la primera corrida descarga ~470MB al cache estable; en las siguientes es
    solo un hit de cache local. Nunca re-descarga en corridas sucesivas.
    """
    from sentence_transformers import SentenceTransformer

    SentenceTransformer(flow_config.DEFAULT_EMBEDDING_MODEL, device="cpu")


@contextlib.contextmanager
def _outbound_blocked(attempts: list[object]) -> Iterator[None]:
    """Bloquea `connect` AF_INET/AF_INET6 registrando cada intento (M3(b)).

    `HF_HUB_OFFLINE=1` se añade para que el cliente HF ni siquiera INTENTE
    contactar (probe: cache cargado → 0 intentos); el patch de socket es quien
    en realidad prohibiría cualquier otra salida, incluida una llamada LLM.
    """
    real_connect = socket.socket.connect

    def _guard(self: socket.socket, address: object, *args: object, **kwargs: object) -> None:
        if self.family in (socket.AF_INET, socket.AF_INET6):
            attempts.append(address)
            raise OSError("T6 M3: salida de red bloqueada durante la indexación")
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


async def _read_all_rows(vault: Path) -> list[dict[str, object]]:
    """Lee la tabla `chunks` completa desde el disco (post-update)."""
    connection = await lancedb.connect_async(str(_db_uri(vault)))
    table = await connection.open_table("chunks")
    arrow = await table.to_arrow()
    return arrow.to_pylist()


async def _list_indices(vault: Path) -> list[Any]:
    """Lista los índices creados sobre la tabla `chunks`."""
    connection = await lancedb.connect_async(str(_db_uri(vault)))
    table = await connection.open_table("chunks")
    return list(await table.list_indices())


async def _query_both_indexes(
    vault: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Consulta ANN (con el vector de una fila almacenada) y FTS (`markdown`)."""
    rows = await _read_all_rows(vault)
    assert rows, "no hay filas que consultar"
    query_vector = rows[0]["embedding"]
    connection = await lancedb.connect_async(str(_db_uri(vault)))
    table = await connection.open_table("chunks")
    vector_search = await table.search(query_vector, vector_column_name="embedding")
    vector_hits = await vector_search.limit(3).to_list()
    fts_search = await table.search("markdown", query_type="fts")
    fts_hits = await fts_search.limit(5).to_list()
    return vector_hits, fts_hits


def _db_uri(vault: Path) -> Path:
    """Devuelve la base LanceDB del vault: `.tepochcalli/db/tepochcalli.lance` (§Target)."""
    return vault / ".tepochcalli" / "db" / "tepochcalli.lance"


class _RecordingBuilder:
    """Stub de `EnvironmentBuilder` que registra recursos y el exception handler.

    T6: el lifespan litellm ya NO falla antes, así que el stub debe cubrir el
    paso completo (incluido `set_exception_handler`).
    """

    def __init__(self) -> None:
        self.provided: list[tuple[object, object]] = []
        self.exception_handler: object | None = None

    def provide(self, key: object, value: object) -> None:
        self.provided.append((key, value))

    def set_exception_handler(self, handler: object) -> None:
        self.exception_handler = handler


async def _advance_and_close(lifespan: AsyncIterator[None]) -> None:
    """Ejecuta el primer paso (setup) del lifespan como haría el engine y lo cierra.

    Cierre en EL MISMO `asyncio.run` que el avance (T6): el gen asíncrono deja
    recursos proveídos (conexión lancedb) colgando del loop del avance; cerrarlo
    en el mismo loop evita finalizadores cruzados. Antes de T6 solo se usaba en
    el camino de error (que terminaba el gen) — el camino de ÉXITO requiere el
    cierre explícito.
    """
    await lifespan.__anext__()
    await lifespan.aclose()


def _lifespan_source() -> str:
    """Fuente del lifespan, para la aserción de orden cache→embedder."""
    return inspect.getsource(flow_app.provide_resources)


def _embedder_from_default_env() -> SentenceTransformerEmbedder:
    """Embedder real del Environment que corrió el update (E1).

    `default_env()` es async en cocoindex==1.0.25 y el environment ya vive en su
    loop de fondo (arrancado por el update): esperarlo es idempotente.
    """

    async def _get_embedder() -> SentenceTransformerEmbedder:
        environment = await coco.default_env()
        return environment.get_context(flow_app.EMBEDDER)

    return asyncio.run(_get_embedder())


async def _schema_from_chunk_row() -> lancedb.TableSchema[flow_models.ChunkRow]:
    """Devuelve el schema LanceDB de `ChunkRow` con un embedder sustituto (fuera del engine)."""

    class _FixedProvider:
        async def __coco_vector_schema__(self) -> VectorSchema:
            return VectorSchema(dtype=np.dtype(np.float32), size=384)

    return await lancedb.TableSchema.from_class(
        flow_models.ChunkRow,
        primary_key=["id"],
        column_specs={"embedding": _FixedProvider()},
    )
