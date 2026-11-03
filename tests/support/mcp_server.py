"""Ayudantes compartidos de los tests del server MCP `tepochcalli-rag` (extracción R4 de T8).

Este módulo es la casa única de los ayudantes que estaban duplicados con
firmas distintas en la sub-fase B/C (riesgo R4 del CP-B):

* `running_server` (stdio + `initialize`) — `test_mcp_server` (variante
  `vault_root`) y `test_mcp_{refresh,rag_status,add_source}` (variante `env`).
* `server_env` — 3 firmas: `model_cache` opcional (T3/T4) vs requerido con
  `allow_loopback` (T5).
* `WARM_SCRIPT` + calentamiento — idéntico en T3, T4 y T5.
* indexado en subproceso (`UPDATE_SCRIPT` + env canónica) —
  `test_mcp_search._build_vault` (T2) y `test_mcp_budget_adversarial` (T7).

**Reconciliación de firmas SIN cambiar comportamiento**: `server_env` acepta
`model_cache` opcional (las llamadas T3/T4 sin cache siguen sin env de modelo)
y el keyword `allow_loopback` (T5 retira el canario `nonet` solo para su
servidor HTTP local); `running_server` recibe la `env` completa (la cuarta
variante de `test_mcp_server` sigue montando la suya con `vault_root` como
adaptador). Al extraer, **ninguna aserción cambió de comportamiento**: los
módulos conservaron sus pruebas idénticas y la suite quedó verde.

También vive aquí el invariante del **wire** (`wire_payload`) y las constantes
de forma que los e2e de T8 pinan desde la spec — nunca desde la
implementación: si el contrato cambia en el código, el test falla y obliga a
decisión, en vez de seguir al literal del paquete.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult
from model_cache import link_model_cache, offline_env, resolve_model_cache
from tepochcalli_flow import app as flow_app
from tepochcalli_flow.config import MODEL_REVISION
from tepochcalli_flow.layout import DB_RELPATH

NONET_DIR = Path(__file__).parent / "nonet"
"""Canario de cero red (`sitecustomize.py`) — va al `PYTHONPATH` de los hijos."""

WARM_SCRIPT = (
    "from sentence_transformers import SentenceTransformer\n"
    "from tepochcalli_flow.config import DEFAULT_EMBEDDING_MODEL, MODEL_REVISION\n"
    f"SentenceTransformer(DEFAULT_EMBEDDING_MODEL, device='cpu', revision={MODEL_REVISION!r})\n"
    "print('warm ok')\n"
)
"""Calienta el cache del modelo UNA vez (en frío: la única descarga permitida)."""

UPDATE_SCRIPT = "from tepochcalli_flow.app import app; app.update_blocking()"
"""Indexa `00-Resources/` del vault en `TEPOCHCALLI_VAULT_ROOT` — el MISMO de T2/T7."""

REFRESH_FIELDS = ["scanned", "indexed", "skipped", "elapsed_ms", "locked", "roots"]
"""Orden exacto de `asdict(RefreshReport)` — plan §5 «Contrato de datos»."""

SEARCH_TOP_LEVEL_FIELDS = ["query", "took_ms", "truncated", "results"]
"""Orden exacto del payload de `search` — plan §5."""

SEARCH_RESULT_FIELDS = [
    "text",
    "source_path",
    "heading",
    "char_start",
    "char_end",
    "score",
    "offsets_ref",
]
"""Los 7 campos congelados por resultado de `search` — plan §5 (Hyrum/ADR-005)."""

ADD_SOURCE_FIELDS = ["ok", "written_to", "indexed"]
"""Orden exacto del payload de `add_source` — plan §5."""

ADD_SOURCE_INDEXED_FIELDS = ["scanned", "indexed", "skipped", "elapsed_ms"]
"""Los 4 campos del sub-objeto `indexed` — SIN `locked` (plan §5 congelado)."""

RAG_STATUS_BLOCKS = ["embedder", "index", "config", "health"]
"""Los 4 bloques exactos de `rag_status` — D7.3/ADR-007."""

RAG_STATUS_INNER_KEYS = {
    "embedder": ["mode", "model", "dims", "provider"],
    "index": [
        "rows",
        "model_matches_config",
        "last_refresh",
        "db_size_bytes",
        "last_refresh_roots",
        "available_roots",
    ],
    "config": ["path", "valid"],
    "health": ["state", "reason", "fix_hint"],
}
"""Orden exacto DENTRO de cada bloque de `rag_status` — spec §rag_status literal."""


def server_env(
    vault: Path,
    model_cache: Path | None = None,
    *,
    allow_loopback: bool = False,
) -> dict[str, str]:
    """Env completa del hijo: vault propio + canario `nonet` + modelo offline si se pasa cache.

    * `vault` → `TEPOCHCALLI_VAULT_ROOT` (el hijo NO ve el índice del repo).
    * `model_cache` → `HF_HOME`/`SENTENCE_TRANSFORMERS_HOME` + `HF_HUB_OFFLINE=1`
      (el warm/indexado previo ya dejó los pesos en cache); SIN cache la env
      de modelo no se fija — la usan T4 (toml malformado), T6 (litellm sin
      clave) y T8 (validación/mismatch: escenarios que jamás cargan un modelo).
    * `allow_loopback=False` inyecta `tests/support/nonet` por `PYTHONPATH`:
      cualquier `connect` AF_INET lanza `OSError` en el hijo (canario M3(b)).
      T5 lo retira SOLO para su servidor HTTP local de test.
    """
    pythonpath: list[str] = []
    if not allow_loopback:
        pythonpath.append(str(NONET_DIR))
    if existing := os.environ.get("PYTHONPATH"):
        pythonpath.append(existing)
    env = {
        **os.environ,
        flow_app.VAULT_ROOT_ENV: str(vault),
    }
    if pythonpath:
        env["PYTHONPATH"] = os.pathsep.join(pythonpath)
    if model_cache is not None:
        env["HF_HOME"] = str(model_cache)
        env["SENTENCE_TRANSFORMERS_HOME"] = str(model_cache)
        env["HF_HUB_OFFLINE"] = (
            "1"  # el warm/indexado ya lo dejó en cache: tras esto, cero descargas
        )
    return env


@asynccontextmanager
async def running_server(env: dict[str, str] | None = None) -> AsyncIterator[ClientSession]:
    """Levanta `python -m tepochcalli_mcp` por stdio y devuelve la sesión cliente.

    `env=None` hereda el entorno del padre (la variante `vault_root=None` de
    `test_mcp_server`); con env completo el hijo corre aislado con su vault.
    """
    params = StdioServerParameters(command=sys.executable, args=["-m", "tepochcalli_mcp"], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def warm_model(vault: Path) -> Path:
    """Calienta el cache del modelo UNA vez y devuelve el symlink `models` del vault.

    En frío esta es la ÚNICA ventana con red permitida (subproceso sin
    canario); tras ella, `server_env(vault, link)` fija `HF_HUB_OFFLINE=1` y
    los hijos corren sin descargar nada.
    """
    cache = resolve_model_cache()
    models_link = link_model_cache(vault, cache)
    proc = subprocess.run(
        [sys.executable, "-c", WARM_SCRIPT],
        env={
            **os.environ,
            "HF_HOME": str(models_link),
            "SENTENCE_TRANSFORMERS_HOME": str(models_link),
            **offline_env(cache),
        },
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert proc.returncode == 0, f"calentamiento del modelo falló:\n{proc.stderr}"
    return models_link


def index_vault(vault: Path) -> Path:
    """Indexa `vault` en SUBPROCESO (env canónica T2/T7) y devuelve su symlink `models`.

    El environment global de cocoindex no admite dos vaults en el mismo
    proceso (sonda T9 de Phase 1), así que TODO indexado corre aquí, en hijo:
    misma env que `test_mcp_search._build_vault` y
    `test_mcp_budget_adversarial._build_adversarial_vault` antes de la
    extracción R4 — incluido el `COCOINDEX_DB` heredado, que se retira para
    que el hijo no reutilice la DB del padre.
    """
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
    assert proc.returncode == 0, f"indexación en subproceso falló:\n{proc.stdout}\n{proc.stderr}"
    assert (vault / DB_RELPATH).exists(), "el update no materializó LanceDB en el vault"
    return models_link


def wire_payload(result: CallToolResult) -> dict[str, object]:
    """Extrae el payload JSON de un `CallToolResult` y afirma los invariantes del wire.

    * un SOLO `TextContent` en `content`;
    * `content[0].text` **JSON parseable** — nunca texto libre
      (spec-mcp-server §Manejo de errores: `json.loads` lanza si es prosa);
    * `structured_content is None` — **coherencia con el shape** (hallazgo H6
      del spike T1, verificado en la fuente del SDK v2): los handlers están
      anotados `-> CallToolResult`, el SDK trata eso como salida *unstructured*,
      anula el `outputSchema` y deja `structured_content = None` **también en
      éxito**. Se afirma explícitamente (y no solo se asume) para que nadie
      persiga un JSON estructurado que el SDK no va a dar: el contrato del
      plan §5 vive SOLO en `content[0].text`.
    """
    assert result.structured_content is None, (
        "H6: handlers `-> CallToolResult` ⇒ salida unstructured ⇒ structured_content "
        f"debe ser None, no {result.structured_content!r}"
    )
    assert len(result.content) == 1, f"el contrato entrega UN TextContent, no {len(result.content)}"
    assert result.content[0].type == "text", result.content[0].type
    payload = json.loads(result.content[0].text)  # JSON parseable: el fallo si es texto libre
    assert isinstance(payload, dict), f"el payload es un objeto JSON, no {type(payload).__name__}"
    return payload
