"""T5: `add_source` end-to-end — file:, http local, colisión, D16 y candado, por stdio (plan §6).

Fuentes de verdad:

* tasks/plan.md §6 T5 AC + «Verificar» — positivos `http(s):` (servidor HTTP
  LOCAL, sin red externa) y `file:` dentro del vault → archivo en
  `00-Resources/_inbox/` con frontmatter + chunk indexado con `source_path`
  correcto; negativos: traversal en `subdir`, `subdir` absoluto, formato no
  convertible ⇒ `SOURCE_UNREACHABLE`, `file:` fuera del vault ⇒ rechazado.
* specs/spec-markitdown.md §Testing (mismos positivos/negativos) y
  §Seguridad del canal; specs/spec-mcp-server.md §Tool `add_source` (forma
  exacta, 4 campos en `indexed`, SIN `locked`).
* D16 (docs/WORKFLOW.md §8): `file:` fuera del vault ⇒ `VALIDATION_ERROR`.

Decisiones de test, documentadas (patrones T3):

* **Server como SUBPROCESO por stdio** con `TEPOCHCALLI_VAULT_ROOT` propio:
  la tool se ejercita COMO LA VE EL HARNESS. El modelo se calienta UNA vez
  (fixture de módulo) porque el refresh INTERNO de `add_source` indexa el
  archivo escrito — el embedder es real, no simulado.
* **Canario `nonet` por defecto** (`tests/support/nonet/sitecustomize.py`):
  cualquier `connect` AF_INET lanza `OSError`. La ÚNICA excepción es el test
  `http:`, que apunta SOLO a `127.0.0.1` con un servidor local del propio
  test — cero red EXTERNA por construcción (AC: «cero red salvo el servidor
  HTTP local de test»).
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
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from model_cache import link_model_cache, offline_env, resolve_model_cache
from tepochcalli_flow import app as flow_app
from tepochcalli_flow import citation
from tepochcalli_flow.config import MODEL_REVISION

NONET_DIR = Path(__file__).parents[1] / "support" / "nonet"
"""Directorio con el `sitecustomize.py` canario (cero red) — va al PYTHONPATH del hijo."""

INDEXED_FIELDS = ["scanned", "indexed", "skipped", "elapsed_ms"]
"""Los 4 campos del sub-objeto `indexed` — SIN `locked` (contrato congelado §5)."""

NOTAS = (
    "# Nota de staging para T5\n\n"
    "Texto distintivo para la busqueda: cohorte pediatria t5xyz-2026 con "
    "metricas de seguimiento y resultados observados en la muestra.\n"
)
ARTICLE_HTML = (
    "<html><head><title>Articulo local T5</title></head><body>"
    "<h1>Articulo local</h1>"
    "<p>Texto distintivo del servidor local: biomarcadores t5http-2026 en sangre.</p>"
    "</body></html>"
)
WARM_SCRIPT = (
    "from sentence_transformers import SentenceTransformer\n"
    "from tepochcalli_flow.config import DEFAULT_EMBEDDING_MODEL, MODEL_REVISION\n"
    f"SentenceTransformer(DEFAULT_EMBEDDING_MODEL, device='cpu', revision={MODEL_REVISION!r})\n"
    "print('warm ok')\n"
)
"""Calienta el cache del modelo UNA vez (en frío: la única descarga permitida)."""


@asynccontextmanager
async def _running_server(env: dict[str, str]) -> AsyncIterator[ClientSession]:
    """Server `python -m tepochcalli_mcp` por stdio con `env` dado (patrón T1/T3)."""
    params = StdioServerParameters(command=sys.executable, args=["-m", "tepochcalli_mcp"], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def _server_env(vault: Path, model_cache: Path, *, allow_loopback: bool = False) -> dict[str, str]:
    """Env del hijo: vault propio + modelo cacheado OFFLINE; canario `nonet` salvo `http:`."""
    pythonpath: list[str] = []
    if not allow_loopback:
        pythonpath.append(str(NONET_DIR))
    if existing := os.environ.get("PYTHONPATH"):
        pythonpath.append(existing)
    env = {
        **os.environ,
        flow_app.VAULT_ROOT_ENV: str(vault),
        "HF_HOME": str(model_cache),
        "SENTENCE_TRANSFORMERS_HOME": str(model_cache),
        "HF_HUB_OFFLINE": "1",
    }
    if pythonpath:
        env["PYTHONPATH"] = os.pathsep.join(pythonpath)
    return env


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

    cache = resolve_model_cache()
    models_link = link_model_cache(vault, cache)
    warm_env = {
        **os.environ,
        "HF_HOME": str(models_link),
        "SENTENCE_TRANSFORMERS_HOME": str(models_link),
        **offline_env(cache),
    }
    proc = subprocess.run(
        [sys.executable, "-c", WARM_SCRIPT],
        env=warm_env,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert proc.returncode == 0, f"calentamiento del modelo falló:\n{proc.stderr}"
    return vault, models_link


# --- positivos --------------------------------------------------------------------------


def test_add_source_file_writes_frontmatter_and_indexes_the_chunk(
    source_vault: tuple[Path, Path],
) -> None:
    """`file:` dentro del vault → shape exacto, frontmatter de trazabilidad y chunk CITABLE."""
    vault, models_link = source_vault
    env = _server_env(vault, models_link)
    uri = (vault / "staging" / "notas.md").as_uri()

    async def journey() -> tuple[dict[str, object], dict[str, object]]:
        async with _running_server(env) as session:
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


def test_add_source_http_from_local_server(source_vault: tuple[Path, Path]) -> None:
    """`http:` contra un servidor LOCAL del test → convertido, escrito y con `source_uri` URL.

    Única prueba sin canario `nonet`: el fetch es loopback a 127.0.0.1 (AC:
    «cero red salvo el servidor HTTP local de test»); el hijo nunca ve red
    externa porque el URI apunta al puerto efímero de ESTE proceso.
    """
    vault, models_link = source_vault

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 — API de BaseHTTPRequestHandler
            body = ARTICLE_HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args: object) -> None:
            """Silencioso: el stderr del servidor de test ensucia la salida del hijo."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        uri = f"http://127.0.0.1:{port}/articulo.html"
        env = _server_env(vault, models_link, allow_loopback=True)

        async def call() -> dict[str, object]:
            async with _running_server(env) as session:
                added, is_error = await _call_add_source(session, uri)
                assert not is_error, added
                return added

        added = asyncio.run(call())
    finally:
        server.shutdown()
        thread.join(timeout=30)

    assert list(added) == ["ok", "written_to", "indexed"]
    assert added["written_to"] == "00-Resources/_inbox/articulo.md"
    written = vault / added["written_to"]
    fields = _frontmatter_fields(written)
    assert fields["source_uri"] == json.dumps(uri, ensure_ascii=False)
    assert "t5http-2026" in written.read_text(encoding="utf-8")


def test_add_source_twice_gets_the_numeric_suffix(source_vault: tuple[Path, Path]) -> None:
    """Segunda llamada con el mismo nombre ⇒ `<slug>-2.md` (plan §T5), en la MISMA sesión.

    Usa un slug PROPIO (`colision`) para no depender del orden respecto a los
    demás tests del vault de módulo (F.I.R.S.T.: independientes).
    """
    vault, models_link = source_vault
    (vault / "staging" / "colision.md").write_text(
        "# Colision\n\nFichero propio del test de sufijo numerico.\n", encoding="utf-8"
    )
    env = _server_env(vault, models_link)
    uri = (vault / "staging" / "colision.md").as_uri()

    async def twice() -> tuple[object, object]:
        async with _running_server(env) as session:
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
    env = _server_env(vault, models_link)
    before = _tree_snapshot(vault / citation.RESOURCES_DIR)

    async def call() -> tuple[dict[str, object], bool]:
        async with _running_server(env) as session:
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
    env = _server_env(vault, models_link)
    (vault / "staging" / "subdir.md").write_text(
        "# Subdir\n\nFichero propio del test de subdir invalido.\n", encoding="utf-8"
    )
    uri = (vault / "staging" / "subdir.md").as_uri()
    before = _tree_snapshot(vault / citation.RESOURCES_DIR)

    async def calls() -> list[dict[str, object]]:
        async with _running_server(env) as session:
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
    env = _server_env(vault, models_link)
    uri = (vault / "staging" / "datos.bin").as_uri()
    before = _tree_snapshot(vault / citation.RESOURCES_DIR)

    async def call() -> tuple[dict[str, object], bool]:
        async with _running_server(env) as session:
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


def test_locked_refresh_reports_engine_locked_and_keeps_the_file(
    source_vault: tuple[Path, Path],
) -> None:
    """DETERMINISTA: el padre retiene el flock ⇒ `ENGINE_LOCKED`; el archivo SÍ quedó escrito."""
    vault, models_link = source_vault
    uri = (vault / "staging" / "notas.md").as_uri()
    lock_fd = flow_app._acquire_refresh_lock(vault)
    assert lock_fd is not None, "nadie retenía el candado: el acquire debe triunfar"
    env = _server_env(vault, models_link)
    try:

        async def call() -> tuple[dict[str, object], bool]:
            async with _running_server(env) as session:
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
