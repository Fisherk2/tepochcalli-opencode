"""T5: `add_source` end-to-end — file:, http local, colisión, D16 y candado, por stdio (plan §6).

Fuentes de verdad:

* tasks/plan.md §6 T5 AC + «Verificar» — positivos `file:` (Dentro del vault)
  → archivo en `00-Resources/_inbox/` con frontmatter + chunk indexado con
  `source_path` correcto; negativos: traversal en `subdir`, `subdir`
  absoluto, formato no convertible ⇒ `SOURCE_UNREACHABLE`, `file:` fuera
  del vault ⇒ rechazado.
* Revisión Phase 2 (2026-10-27, SSRF): `http(s)` contra hosts de red interna
  (loopback incluido — el antiguo servidor HTTP local ya NO es caso
  aceptado) ⇒ `VALIDATION_ERROR` SIN fetch (denylist de `paths`).
* specs/spec-markitdown.md §Testing (mismos positivos/negativos) y
  §Seguridad del canal; specs/spec-mcp-server.md §Tool `add_source` (forma
  exacta, 4 campos en `indexed`, SIN `locked`).
* D16 (docs/WORKFLOW.md §8): `file:` fuera del vault ⇒ `VALIDATION_ERROR`.

Decisiones de test, documentadas (patrones T3):

* **Server como SUBPROCESO por stdio** con `TEPOCHCALLI_VAULT_ROOT` propio:
  la tool se ejercita COMO LA VE EL HARNESS. El modelo se calienta UNA vez
  (fixture de módulo) porque el refresh INTERNO de `add_source` indexa el
  archivo escrito — el embedder es real, no simulado.
* **Canario `nonet` SIEMPRE** (`tests/support/nonet/sitecustomize.py`):
  cualquier `connect` AF_INET lanza `OSError`. Revisión Phase 2 (SSRF
  2026-10-27): ya no hay excepción de loopback — la denylist rechaza el
  `http://127.0.0.1` en el borde (sin fetch), y el canario protege TODOS los
  tests de este módulo.
* **ENGINE_LOCKED determinista** (sin reloj, gotera G1): el PADRE retiene el
  `flock` del refresh (`flow_app._acquire_refresh_lock`) mientras la tool
  corre — el solapamiento lo garantiza el kernel.
* **`converted_at` solo por PRESENCIA**: ningún assert depende del reloj
  (regla de la gotera G1: cero aserciones dependientes del tiempo).
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest
from mcp import ClientSession
from support.mcp_server import running_server, server_env, warm_model
from tepochcalli_flow import app as flow_app
from tepochcalli_flow import citation

INDEXED_FIELDS = ["scanned", "indexed", "skipped", "elapsed_ms"]
"""Los 4 campos del sub-objeto `indexed` — SIN `locked` (contrato congelado §5)."""

NOTAS = (
    "# Nota de staging para T5\n\n"
    "Texto distintivo para la busqueda: cohorte pediatria t5xyz-2026 con "
    "metricas de seguimiento y resultados observados en la muestra.\n"
)


async def _call_add_source(
    session: ClientSession, uri: str, subdir: str | None = None
) -> tuple[dict[str, object], bool]:
    """`add_source` por stdio: `(payload parseado, is_error)` — shape contrato o error."""
    arguments: dict[str, object] = {"uri": uri}
    if subdir is not None:
        arguments["subdir"] = subdir
    result = await session.call_tool("add_source", arguments)
    return json.loads(result.content[0].text), result.is_error


def _frontmatter_fields(text: Path) -> dict[str, str]:
    """Extrae `source_uri`/`converted_at` del frontmatter escrito (sin depend YAML)."""
    lines = text.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "---", "el archivo convertido DEBE abrir con frontmatter"
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line == "---":
            break
        key, _, value = line.partition(": ")
        fields[key] = value
    return fields


def _tree_snapshot(root: Path) -> dict[str, tuple[int, int | None]]:
    """`(mtime_ns, size)` por ruta relativa — detecta cualquier escritura (patrón T3)."""
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): (
            path.stat().st_mtime_ns,
            path.stat().st_size if path.is_file() else None,
        )
        for path in sorted(root.rglob("*"))
    }


@pytest.fixture(scope="module")
def source_vault(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """Vault T5 con `00-Resources/`, staging fuera del recurso y modelo calentado, SIN indexar."""
    vault = tmp_path_factory.mktemp("vault-t5")
    (vault / citation.RESOURCES_DIR).mkdir()
    staging = vault / "staging"
    staging.mkdir()
    (staging / "notas.md").write_text(NOTAS, encoding="utf-8")
    (staging / "datos.bin").write_bytes(os.urandom(64))

    models_link = warm_model(vault)
    return vault, models_link


# --- positivos --------------------------------------------------------------------------


def test_add_source_file_writes_frontmatter_and_indexes_the_chunk(
    source_vault: tuple[Path, Path],
) -> None:
    """`file:` dentro del vault → shape exacto, frontmatter de trazabilidad y chunk CITABLE."""
    vault, models_link = source_vault
    env = server_env(vault, models_link)
    uri = (vault / "staging" / "notas.md").as_uri()

    async def journey() -> tuple[dict[str, object], dict[str, object]]:
        async with running_server(env) as session:
            added, is_error = await _call_add_source(session, uri)
            assert not is_error, added
            found = await session.call_tool("search", {"query": "cohorte pediatria t5xyz-2026"})
            assert not found.is_error, found.content[0].text
            return added, json.loads(found.content[0].text)

    added, search = asyncio.run(journey())

    assert list(added) == ["ok", "written_to", "indexed"]
    assert added["ok"] is True
    assert added["written_to"] == "00-Resources/_inbox/notas.md"
    assert list(added["indexed"]) == INDEXED_FIELDS
    assert added["indexed"]["indexed"] >= 1, "el refresh interno indexa el archivo escrito"

    written = vault / added["written_to"]
    fields = _frontmatter_fields(written)
    assert fields["source_uri"] == json.dumps(uri, ensure_ascii=False)
    assert "converted_at" in fields, "presencia, nunca el valor (regla anti-tiempo)"
    assert "t5xyz-2026" in written.read_text(encoding="utf-8")

    assert search["results"], "el chunk recién escrito debe ser buscable"
    assert search["results"][0]["source_path"] == added["written_to"]


@pytest.mark.parametrize(
    "uri",
    [
        "http://127.0.0.1:9/articulo.html",  # 127.0.0.0/8 (antes era el ACEPTADO aquí)
        "http://localhost/articulo.html",  # loopback por nombre
        "http://169.254.169.254/latest/meta-data/",  # link-local: cloud metadata
        "http://192.168.1.1/articulo.html",  # 192.168.0.0/16
        "http://usuario@example.org/articulo.html",  # userinfo
    ],
)
def test_ssrf_denylist_rejects_internal_hosts_by_stdio(
    source_vault: tuple[Path, Path], uri: str
) -> None:
    """Denylist SSRF por stdio (review Phase 2 2026-10-27) ⇒ `VALIDATION_ERROR`, cero fetch.

    El URI es rechazado en el borde ANTES de que markitdown vea nada: ni
    connect ni DNS — bajo el canario `nonet` (que bloquearía cualquier
    connect) el rechazo nunca llega a red, y `00-Resources/` queda byte a
    byte. Sustituye al antiguo positivo `http://127.0.0.1` (test_add_source_http_
    from_local_server): con la denylist, TODA IP de loopback es rechazada por
    diseño, y el camino feliz de conversión real queda cubierto por `file:`
    (el mismo conversor markitdown EN PROCESO) y por los unit del handler.
    """
    vault, models_link = source_vault
    env = server_env(vault, models_link)
    before = _tree_snapshot(vault / citation.RESOURCES_DIR)

    async def call() -> tuple[dict[str, object], bool]:
        async with running_server(env) as session:
            return await _call_add_source(session, uri)

    payload, is_error = asyncio.run(call())

    assert is_error
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert (
        "red interna" in payload["error"]["message"] or "userinfo" in payload["error"]["message"]
    ), payload
    assert _tree_snapshot(vault / citation.RESOURCES_DIR) == before, (
        "un URI interno rechazado no puede escribir ni un byte"
    )


def test_add_source_twice_gets_the_numeric_suffix(source_vault: tuple[Path, Path]) -> None:
    """Segunda llamada con el mismo nombre ⇒ `<slug>-2.md` (plan §T5), en la MISMA sesión.

    Usa un slug PROPIO (`colision`) para no depender del orden respecto a los
    demás tests del vault de módulo (F.I.R.S.T.: independientes).
    """
    vault, models_link = source_vault
    (vault / "staging" / "colision.md").write_text(
        "# Colision\n\nFichero propio del test de sufijo numerico.\n", encoding="utf-8"
    )
    env = server_env(vault, models_link)
    uri = (vault / "staging" / "colision.md").as_uri()

    async def twice() -> tuple[object, object]:
        async with running_server(env) as session:
            first, first_error = await _call_add_source(session, uri)
            assert not first_error, first
            second, second_error = await _call_add_source(session, uri)
            assert not second_error, second
            return first["written_to"], second["written_to"]

    first_to, second_to = asyncio.run(twice())

    assert first_to == "00-Resources/_inbox/colision.md"
    assert second_to == "00-Resources/_inbox/colision-2.md"


# --- negativos ----------------------------------------------------------------------------


def test_file_outside_the_vault_is_rejected_d16(source_vault: tuple[Path, Path]) -> None:
    """D16: `file:` fuera del vault ⇒ `VALIDATION_ERROR`; `00-Resources/` queda byte a byte."""
    vault, models_link = source_vault
    env = server_env(vault, models_link)
    before = _tree_snapshot(vault / citation.RESOURCES_DIR)

    async def call() -> tuple[dict[str, object], bool]:
        async with running_server(env) as session:
            return await _call_add_source(session, "file:///etc/hostname")

    payload, is_error = asyncio.run(call())

    assert is_error
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert _tree_snapshot(vault / citation.RESOURCES_DIR) == before, (
        "el rechazo D16 no puede escribir ni un byte"
    )


def test_traversal_and_absolute_subdir_are_rejected(source_vault: tuple[Path, Path]) -> None:
    """`subdir` con `..` o absoluto ⇒ `VALIDATION_ERROR`; cero escrituras dentro o fuera."""
    vault, models_link = source_vault
    env = server_env(vault, models_link)
    (vault / "staging" / "subdir.md").write_text(
        "# Subdir\n\nFichero propio del test de subdir invalido.\n", encoding="utf-8"
    )
    uri = (vault / "staging" / "subdir.md").as_uri()
    before = _tree_snapshot(vault / citation.RESOURCES_DIR)

    async def calls() -> list[dict[str, object]]:
        async with running_server(env) as session:
            traversal, error_a = await _call_add_source(session, uri, "../escape")
            absolute, error_b = await _call_add_source(session, uri, "/etc")
            assert error_a and error_b
            return [traversal, absolute]

    for payload in asyncio.run(calls()):
        assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert not (vault / "escape").exists()
    assert _tree_snapshot(vault / citation.RESOURCES_DIR) == before, (
        "un subdir rechazado no puede escribir ni un byte"
    )


def test_unconvertible_format_maps_to_source_unreachable(source_vault: tuple[Path, Path]) -> None:
    """Binario sin conversor ⇒ `SOURCE_UNREACHABLE` con la guía literal; cero escrituras."""
    vault, models_link = source_vault
    env = server_env(vault, models_link)
    uri = (vault / "staging" / "datos.bin").as_uri()
    before = _tree_snapshot(vault / citation.RESOURCES_DIR)

    async def call() -> tuple[dict[str, object], bool]:
        async with running_server(env) as session:
            return await _call_add_source(session, uri)

    payload, is_error = asyncio.run(call())

    assert is_error
    error = payload["error"]
    assert error["code"] == "SOURCE_UNREACHABLE"
    assert "00-Resources/" in error["message"] and "index_refresh" in error["message"]
    assert error["details"]["cause"], "el tipo de la causa viaja en details (sin traceback)"
    assert _tree_snapshot(vault / citation.RESOURCES_DIR) == before, (
        "una conversión fallida no puede escribir ni un byte"
    )


def test_missing_resources_root_in_indexer_dir_is_rejected_before_converting(
    tmp_path: Path,
) -> None:
    """`INDEXER_DIR=documentos` sin `00-Resources` ⇒ `VALIDATION_ERROR` ANTES de convertir/escribir.

    Gate de raíz declarada ejercitado en el WIRE (server real por stdio, sin
    seams): el MCP no añade raíces al índice, así que sin `00-Resources` en
    `INDEXER_DIR` la tool responde `details.{requested,allowed,hint}` y NADA
    aparece en `00-Resources/` — snapshot byte a byte del vault completo
    demuestra que ni el conversor ni la escritura corrieron. Sin modelo: el
    gate precede a `E_NO_EMBEDDER`, así que el hijo corre con el canario
    `nonet` y sin cache de modelo (patrón del edge de `index_refresh`).
    """
    (tmp_path / "documentos").mkdir()
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "notas.md").write_text(NOTAS, encoding="utf-8")
    env = {**server_env(tmp_path), "INDEXER_DIR": "documentos"}
    uri = (staging / "notas.md").as_uri()
    before = _tree_snapshot(tmp_path)

    async def call() -> tuple[dict[str, object], bool]:
        async with running_server(env) as session:
            return await _call_add_source(session, uri)

    payload, is_error = asyncio.run(call())

    assert is_error
    error = payload["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"]["requested"] == "00-Resources"
    assert error["details"]["allowed"] == ["documentos"]
    assert not (tmp_path / citation.RESOURCES_DIR).exists(), "nada escrito en 00-Resources/"
    assert _tree_snapshot(tmp_path) == before, "el gate corre antes de convertir o escribir"


def test_locked_refresh_reports_engine_locked_and_keeps_the_file(
    source_vault: tuple[Path, Path],
) -> None:
    """DETERMINISTA: el padre retiene el flock ⇒ `ENGINE_LOCKED`; el archivo SÍ quedó escrito."""
    vault, models_link = source_vault
    uri = (vault / "staging" / "notas.md").as_uri()
    lock_fd = flow_app._acquire_refresh_lock(vault)
    assert lock_fd is not None, "nadie retenía el candado: el acquire debe triunfar"
    env = server_env(vault, models_link)
    try:

        async def call() -> tuple[dict[str, object], bool]:
            async with running_server(env) as session:
                return await _call_add_source(session, uri, "bloqueado")

        payload, is_error = asyncio.run(call())
    finally:
        flow_app._release_refresh_lock(lock_fd)

    assert is_error
    assert payload["error"]["code"] == "ENGINE_LOCKED"
    assert payload["error"]["details"] == {"written_to": "00-Resources/bloqueado/notas.md"}
    assert (vault / "00-Resources" / "bloqueado" / "notas.md").is_file()


def test_payload_db_and_models_are_never_created_by_the_tool() -> None:
    """Ningún `add_source` de este módulo materializa `db/` ni `models/` en el payload."""
    payload = Path(__file__).parents[2] / "obsidian-workspace" / ".tepochcalli"
    assert not (payload / "db").exists()
    assert not (payload / "models").exists()
