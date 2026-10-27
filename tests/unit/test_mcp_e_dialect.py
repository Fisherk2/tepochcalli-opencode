"""T6: dialecto `E_*` completo — contrato por código, precedencia y la clave que jamás se filtra.

Fuentes: specs/spec-mcp-server.md §Códigos de error estructurados (los 5 `E_*`
y sus payloads) + §Manejo de errores (legacy vs `E_*`); tasks/todo.md → T6 AC;
plan §9 riesgo crítico «el traceback de litellm filtra la clave de API».

Arquitectura de los tests (y de la implementación), documentada:

* **Cero red por construcción:** el «proveedor falso» se inyecta con
  `monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(embedding=…))`
  (el wrapper importa litellm perezoso ⇒ ni siquiera se carga el paquete real)
  y con `sentence_transformers.SentenceTransformer` parcheado para la rama
  local. Ninguna llamada a API real.
* **La precedencia se prueba por pares adyacentes** —
  `E_NO_EMBEDDER > INDEX_EMPTY > E_MODEL_MISMATCH > E_API_AUTH` — con el
  siguiente eslabón COMPROBANDO que el paso anterior ni se invocó (fábrica o
  `cited_chunks` con registro de llamadas): transitiva por construcción.
* **Clave (plan §9):** el valor solo existe dentro del wrapper de litellm; se
  scrubea con `str.replace(valor, "***")` ANTES de elevar y se eleva `from
  None` (sin cadena) ⇒ ni payload, ni `repr`, ni el `logger.exception` del
  guard pueden contenerlo — testado con `caplog`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import types
from pathlib import Path

import pytest
from tepochcalli_flow.config import (
    DEFAULT_API_KEY_ENV,
    DEFAULT_EMBEDDING_MODEL,
    Config,
    EmbeddingConfig,
)
from tepochcalli_flow.ports import CitedChunk
from tepochcalli_mcp import embedder, errors
from tepochcalli_mcp.tools import add_source as add_source_handler
from tepochcalli_mcp.tools import index_refresh as refresh_handler
from tepochcalli_mcp.tools import json_result
from tepochcalli_mcp.tools import search as search_handler

FAKE_KEY = "sk-t6-sup-secreto-999"
LITELLM_MODEL = "openai/text-embedding-3-small"


def _config(provider: str = "local", *, model: str = DEFAULT_EMBEDDING_MODEL) -> Config:
    """Config de prueba directa (el loader real lo cubre `test_d15_provider_none`)."""
    return Config(
        models_dir=Path("/vault/.tepochcalli/models"),
        embedding=EmbeddingConfig(provider=provider, model=model),
    )


class _Backend:
    """Doble de `SearchBackend` con registro de llamadas y error inyectable."""

    def __init__(
        self,
        *,
        models: set[str] | None = None,
        cited_error: Exception | None = None,
        expected_model: str = DEFAULT_EMBEDDING_MODEL,
    ) -> None:
        self._models = {DEFAULT_EMBEDDING_MODEL} if models is None else models
        self._cited_error = cited_error
        self._expected = expected_model
        self.cited_calls = 0

    @property
    def expected_model(self) -> str:
        return self._expected

    async def index_models(self) -> set[str]:
        return self._models

    async def cited_chunks(
        self, query: str, top_k: int, path_filter: str | None
    ) -> list[CitedChunk]:
        self.cited_calls += 1
        if self._cited_error is not None:
            raise self._cited_error
        text = "chunk"
        return [
            CitedChunk(
                text=text,
                source_path="00-Resources/a.md",
                heading=None,
                char_start=0,
                char_end=len(text),
                score=1.0,
            )
        ]


def _search(
    *,
    available: bool = True,
    backend: _Backend | None = None,
    backend_factory_raises: Exception | None = None,
) -> dict[str, object]:
    """Corre `search` con seams de doble; por defecto, backend sano y disponible."""
    real_backend = backend if backend is not None else _Backend()

    def _factory() -> _Backend:
        if backend_factory_raises is not None:
            raise backend_factory_raises
        return real_backend

    return asyncio.run(
        search_handler.search(
            "consulta",
            backend_factory=_factory,
            embedder_available=lambda: available,
        )
    )


# --- precedencia: E_NO_EMBEDDER > INDEX_EMPTY > E_MODEL_MISMATCH > E_API_AUTH ----------


def test_no_embedder_precedes_everything_and_the_backend_is_never_built() -> None:
    """R1: `search` emite `E_NO_EMBEDDER` SIN construir el backend ni mirar el índice."""
    payload = _search(available=False, backend_factory_raises=AssertionError("no debe construir"))

    assert payload == errors.no_embedder()


def test_index_empty_precedes_model_mismatch() -> None:
    """Índice vacío ⇒ `INDEX_EMPTY`, no `E_MODEL_MISMATCH` (vacío ≠ desalineado)."""
    backend = _Backend(models=set())

    payload = _search(backend=backend)

    assert payload["error"]["code"] == "INDEX_EMPTY"  # type: ignore[index]


class _UnreadableIndex(_Backend):
    """Índice ilegible en el borde: `index_models` lanza el `ValueError` de lancedb."""

    async def index_models(self) -> set[str]:
        raise ValueError("tabla chunks ilegible")


def test_unreadable_index_state_maps_to_validation_error_not_internal() -> None:
    """`ValueError` al leer el estado del índice ⇒ `VALIDATION_ERROR` (no `INTERNAL`).

    El borde de solo lectura del backend (tabla con esquema incompatible)
    responde con el mismo dialecto de validación que el resto de argumentos
    inválidos — nunca con un `INTERNAL` opaco.
    """
    payload = _search(backend=_UnreadableIndex())

    assert payload == errors.validation_error("tabla chunks ilegible")


def test_model_mismatch_precedes_api_auth_and_never_embeds_the_query() -> None:
    """Mismatch ⇒ `E_MODEL_MISMATCH` ANTES de cruzar dims: `cited_chunks` NO se invoca.

    (La pierna de API ni siquiera se alcanza — es el «antes de cruzar dims»
    de spec §E_MODEL_MISMATCH.)
    """
    backend = _Backend(models={"modelo-viejo"}, cited_error=embedder.EmbedderAuthError("ENV"))

    payload = _search(backend=backend)

    assert payload["error"]["code"] == "E_MODEL_MISMATCH"  # type: ignore[index]
    assert backend.cited_calls == 0, "el embed de la query jamás debe ocurrir con mismatch"


def test_api_auth_is_emitted_when_all_prior_gates_pass() -> None:
    """Con índice sano y modelo alineado, el fallo de credenciales ⇒ `E_API_AUTH`."""
    backend = _Backend(cited_error=embedder.EmbedderAuthError(DEFAULT_API_KEY_ENV))

    payload = _search(backend=backend)

    result = json_result(payload)
    assert result.is_error is True
    error = json.loads(result.content[0].text)["error"]
    assert error["code"] == "E_API_AUTH"
    assert DEFAULT_API_KEY_ENV in error["message"]
    assert error["fix_hint"] == errors.FIX_API_AUTH
    assert backend.cited_calls == 1


# --- los E_* de modelo/offline mapeados desde el camino de lectura ----------------------


def test_offline_model_failure_maps_to_e_offline_no_cache() -> None:
    """Fallo de carga local con modo offline ⇒ `E_OFFLINE_NO_CACHE` (no INTERNAL)."""
    payload = _search(
        backend=_Backend(cited_error=embedder.EmbedderOfflineError("LocalEntryNotFound: x"))
    )

    assert payload["error"]["code"] == "E_OFFLINE_NO_CACHE"  # type: ignore[index]
    assert payload["error"]["fix_hint"] == errors.FIX_OFFLINE_NO_CACHE  # type: ignore[index]


def test_model_materialization_failure_maps_to_e_model_invalid() -> None:
    """Fallo de carga local SIN offline (descarga o no-es-modelo) ⇒ `E_MODEL_INVALID`."""
    payload = _search(
        backend=_Backend(cited_error=embedder.EmbedderModelError("ValueError: no es un modelo"))
    )

    assert payload["error"]["code"] == "E_MODEL_INVALID"  # type: ignore[index]


def test_unavailable_embedder_maps_to_e_no_embedder_as_defensive_second_layer() -> None:
    """Si alguien construyera un corte con config `none` (bypass del seam) ⇒ `E_NO_EMBEDDER`.

    Segunda capa del R1: el seam `embedder_available` es la primaria; esta
    demuestra que ni siquiera un bypass puede devolver algo distinto del
    dialecto correcto.
    """
    payload = _search(
        backend=_Backend(cited_error=embedder.EmbedderUnavailableError("provider none"))
    )

    assert payload == errors.no_embedder()


def test_api_throttling_failure_is_internal_with_scrubbed_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Fallo de API no cubierto (rate limit/timeout/red) ⇒ `INTERNAL` legado + log SIN la clave.

    El wrapper de litellm scrubea antes de elevar (`***`), así que lo único
    que el guard loggea ya está limpio; `details` queda `null` (legado) y el
    detalle vive solo en el log.
    """
    scrubbed = f"RateLimitError 429 durante embed de {FAKE_KEY} con retry"
    backend = _Backend(cited_error=embedder.EmbedderApiError(scrubbed.replace(FAKE_KEY, "***")))

    with caplog.at_level(logging.ERROR):
        payload = _search(backend=backend)

    error = payload["error"]
    assert error["code"] == "INTERNAL"  # type: ignore[index]
    assert list(error) == ["code", "message", "details"]
    assert error["details"] is None  # type: ignore[index]
    assert FAKE_KEY not in json.dumps(payload)
    assert FAKE_KEY not in caplog.text, "el valor de la clave jamás llega al log"
    assert "***" in caplog.text, "el detalle scrubbeado SÍ está en el log (accionable)"


# --- la fábrica de lectura: wrappers con el proveedor falso inyectado --------------------


def test_litellm_read_wrapper_raises_auth_error_on_401_without_key_in_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`litellm.embedding` 401 ⇒ `EmbedderAuthError` con SOLO el nombre de la env var.

    Proveedor falso: módulo literal en `sys.modules` — cero red y cero
    importación del paquete real (source-driven: el wrapper hace
    `import litellm` perezoso justo aquí).
    """
    monkeypatch.setenv(DEFAULT_API_KEY_ENV, FAKE_KEY)

    class _Fake401Error(Exception):
        status_code = 401

    calls: list[object] = []

    def _fake_embedding(**kwargs: object) -> object:
        calls.append(kwargs)
        raise _Fake401Error(f"unauthorized con {FAKE_KEY}")

    monkeypatch.setitem(sys.modules, "litellm", types.SimpleNamespace(embedding=_fake_embedding))

    cut = embedder.build_embedder(_config("litellm", model=LITELLM_MODEL))

    with pytest.raises(embedder.EmbedderAuthError) as exc_info:
        cut("una consulta")

    assert str(exc_info.value) == DEFAULT_API_KEY_ENV
    assert FAKE_KEY not in str(exc_info.value)
    assert FAKE_KEY not in repr(exc_info.value)
    assert len(calls) == 1, "la llamada al proveedor SÍ se hizo (401 viene de la API)"


def test_litellm_read_wrapper_returns_the_embedding_as_floats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Camino de ÉXITO del corte de API: `response.data[0]["embedding"]` ⇒ `list[float]`.

    Ejercita las líneas que convierten la respuesta del proveedor en el vector
    de la query: sin esta pierna, un cambio de forma en `litellm` (p. ej.
    devolver `int`/`str`) viajaría hasta el adaptador sin que nada lo afirme.
    """
    monkeypatch.setenv(DEFAULT_API_KEY_ENV, FAKE_KEY)
    calls: list[dict[str, object]] = []

    def _fake_embedding(**kwargs: object) -> object:
        calls.append(kwargs)
        return types.SimpleNamespace(data=[{"embedding": [0.25, 1, "2.5"]}])

    monkeypatch.setitem(sys.modules, "litellm", types.SimpleNamespace(embedding=_fake_embedding))

    cut = embedder.build_embedder(_config("litellm", model=LITELLM_MODEL))

    vector = cut("una consulta")

    assert vector == [0.25, 1.0, 2.5]
    assert all(type(value) is float for value in vector), "el contrato es list[float]"
    assert calls == [
        {"model": LITELLM_MODEL, "input": ["una consulta"], "api_key": FAKE_KEY},
    ], "una sola llamada, con el texto como `input` de una lista"


def test_litellm_read_wrapper_never_calls_the_provider_without_the_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sin `api_key_env` ⇒ `EmbedderAuthError` ANTES de tocar el proveedor (cero red).

    El chequeo vive en la CONSTRUCCIÓN del corte (`_litellm_cut`): fallar
    temprano es lo que garantiza que `litellm` ni se importe ni se llame.
    """
    monkeypatch.delenv(DEFAULT_API_KEY_ENV, raising=False)
    calls: list[object] = []

    def _fake_embedding(**kwargs: object) -> object:
        calls.append(kwargs)
        raise AssertionError("no debe llegar: sin clave no se llama al proveedor")

    monkeypatch.setitem(sys.modules, "litellm", types.SimpleNamespace(embedding=_fake_embedding))

    with pytest.raises(embedder.EmbedderAuthError) as exc_info:
        embedder.build_embedder(_config("litellm", model=LITELLM_MODEL))

    assert str(exc_info.value) == DEFAULT_API_KEY_ENV
    assert calls == [], "el chequeo de clave es local: ninguna llamada a la API"


def test_litellm_read_wrapper_scrubs_the_key_from_non_auth_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rate limit u otro fallo ⇒ `EmbedderApiError` con la clave SCRUBEADA (`***`) y `from None`."""
    monkeypatch.setenv(DEFAULT_API_KEY_ENV, FAKE_KEY)

    class _Fake429Error(Exception):
        status_code = 429

    def _fake_embedding(**kwargs: object) -> object:
        raise _Fake429Error(f"429 rate limit con la clave {FAKE_KEY} en el cuerpo")

    monkeypatch.setitem(sys.modules, "litellm", types.SimpleNamespace(embedding=_fake_embedding))

    cut = embedder.build_embedder(_config("litellm", model=LITELLM_MODEL))

    with pytest.raises(embedder.EmbedderApiError) as exc_info:
        cut("una consulta")

    error = exc_info.value
    assert FAKE_KEY not in str(error)
    assert FAKE_KEY not in repr(error)
    assert "***" in str(error)
    assert error.__cause__ is None, (
        "`from None`: la causa original (con la clave) no se encadena al log"
    )


@pytest.mark.parametrize("error_name", ["AuthenticationError", "PermissionDeniedError"])
def test_litellm_auth_errors_are_classified_by_class_name_without_status_code(
    monkeypatch: pytest.MonkeyPatch, error_name: str
) -> None:
    """401/403 que llegan SOLO por nombre de clase (sin `status_code`) ⇒ `EmbedderAuthError`.

    El clasificador no puede depender de `status_code`: hay wraps/proveedores
    que exponen la credencial rechazada únicamente en el nombre del tipo.
    """
    monkeypatch.setenv(DEFAULT_API_KEY_ENV, FAKE_KEY)
    fake_error = type(error_name, (Exception,), {})

    def _fake_embedding(**kwargs: object) -> object:
        raise fake_error(f"rechazado con {FAKE_KEY}")

    monkeypatch.setitem(sys.modules, "litellm", types.SimpleNamespace(embedding=_fake_embedding))

    cut = embedder.build_embedder(_config("litellm", model=LITELLM_MODEL))

    with pytest.raises(embedder.EmbedderAuthError) as exc_info:
        cut("una consulta")

    assert str(exc_info.value) == DEFAULT_API_KEY_ENV, "solo el nombre de la env var"
    assert FAKE_KEY not in str(exc_info.value)


def test_local_embedder_offline_failure_is_classified_as_offline_no_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Carga local que falla CON `HF_HUB_OFFLINE=1` ⇒ `EmbedderOfflineError` (por flag)."""
    import sentence_transformers

    monkeypatch.setenv("HF_HUB_OFFLINE", "1")

    def _broken(*args: object, **kwargs: object) -> object:
        raise OSError("cannot find the files in the disk cache and traffic is disabled")

    monkeypatch.setattr(sentence_transformers, "SentenceTransformer", _broken)

    with pytest.raises(embedder.EmbedderOfflineError):
        embedder.build_embedder(_config())


def test_local_embedder_failure_without_offline_is_classified_as_model_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Carga local que falla SIN offline ⇒ `EmbedderModelError` (descarga o no-es-modelo)."""
    import sentence_transformers

    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)

    def _broken(*args: object, **kwargs: object) -> object:
        raise ValueError("modelo corrupto o no es un embedding model")

    monkeypatch.setattr(sentence_transformers, "SentenceTransformer", _broken)

    with pytest.raises(embedder.EmbedderModelError):
        embedder.build_embedder(_config())


# --- cadena completa: fábrica REAL → handler (la composición de los dos niveles) ---------


def test_real_offline_factory_failure_surfaces_as_e_offline_in_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Punto de composición: el corte local REAL falla ⇒ el handler responde `E_OFFLINE_NO_CACHE`.

    El doble de backend invoca `embedder.build_embedder(config)(query)` dentro
    de `cited_chunks` — el mismo camino que `server._VaultSearchBackend`.
    """
    import sentence_transformers

    monkeypatch.setenv("HF_HUB_OFFLINE", "1")

    def _broken(*args: object, **kwargs: object) -> object:
        raise OSError("sin cache y sin red")

    monkeypatch.setattr(sentence_transformers, "SentenceTransformer", _broken)
    config = _config()

    class _RealCutoffBackend(_Backend):
        async def cited_chunks(
            self, query: str, top_k: int, path_filter: str | None
        ) -> list[CitedChunk]:
            self.cited_calls += 1
            embedder.build_embedder(config)(query)  # igual que el composition root
            return []

    payload = _search(backend=_RealCutoffBackend())

    assert payload["error"]["code"] == "E_OFFLINE_NO_CACHE"  # type: ignore[index]


# --- E_API_AUTH desde index_refresh y add_source (mismo seam de refresh) -----------------


def _auth_refresh() -> dict[str, object]:
    """El seam de refresh del composition root tradujo la clave ausente (server._refresh_once)."""
    raise embedder.EmbedderAuthError(DEFAULT_API_KEY_ENV)


def test_index_refresh_maps_key_missing_to_e_api_auth() -> None:
    """`index_refresh` emite `E_API_AUTH` cuando el flow rechaza la clave faltante."""
    payload = asyncio.run(
        refresh_handler.index_refresh(
            refresh=_auth_refresh,
            embedder_available=lambda: True,
            index_exists=lambda: True,
        )
    )

    error = payload["error"]
    assert error["code"] == "E_API_AUTH"  # type: ignore[index]
    assert error["fix_hint"] == errors.FIX_API_AUTH  # type: ignore[index]
    assert FAKE_KEY not in json.dumps(payload)


def test_add_source_maps_key_missing_to_e_api_auth(tmp_path: Path) -> None:
    """`add_source` también emite `E_API_AUTH` (spec §Códigos lo lista) — mismo seam de refresh."""
    payload = asyncio.run(
        add_source_handler.add_source(
            "https://example.org/paper",
            None,
            vault_root=lambda: tmp_path,
            convert=lambda uri: "# convertido\n",
            refresh=_auth_refresh,
            embedder_available=lambda: True,
        )
    )

    error = payload["error"]
    assert error["code"] == "E_API_AUTH"  # type: ignore[index]
    assert error["fix_hint"] == errors.FIX_API_AUTH  # type: ignore[index]


# --- los 5 payloads juntos: el dialecto completo -----------------------------------------


def test_all_five_e_codes_share_the_three_key_shape() -> None:
    """Los 5 `E_*` con `{code,message,fix_hint}` y orden exacto (contract test D7.3)."""
    payloads = [
        errors.no_embedder(),
        errors.api_auth(DEFAULT_API_KEY_ENV),
        errors.model_invalid(),
        errors.offline_no_cache(),
        errors.model_mismatch({"viejo"}, DEFAULT_EMBEDDING_MODEL),
    ]
    codes = []
    for payload in payloads:
        error = payload["error"]
        assert list(error)[:3] == ["code", "message", "fix_hint"], list(error)
        assert isinstance(error["fix_hint"], str) and error["fix_hint"]
        codes.append(error["code"])

    assert codes == [
        "E_NO_EMBEDDER",
        "E_API_AUTH",
        "E_MODEL_INVALID",
        "E_OFFLINE_NO_CACHE",
        "E_MODEL_MISMATCH",
    ]
