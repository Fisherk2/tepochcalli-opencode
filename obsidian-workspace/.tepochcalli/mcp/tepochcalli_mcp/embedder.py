"""Hechos del embedder y estrategia de LECTURA inyectable — dialecto `E_*` (T6/D59).

Este módulo **no importa `cocoindex`, `litellm` ni `sentence_transformers`**
(la fábrica de providers vive en el composition root `server.py`, que construye
`cocoindex.ops.sentence_transformers.SentenceTransformerEmbedder` o
`cocoindex.ops.litellm.LiteLLMEmbedder` y los inyecta aquí como dobles/op
objects). Así el read path usa la MISMA implementación que el write path
(D59) sin que el paquete `tepochcalli_mcp` dependa del motor.

**Una sola referencia de modelo:** ambos caminos resuelven
`config.embedding_model_path` = `<vault>/.tepochcalli/models/<slug>@<sha>/`.
El write path lo materializa (`tepochcalli_flow.model_store.ensure_local_model`);
el read path lo **exige** con `require_local_model` y NUNCA descarga: si falta,
`EmbedderModelError` → `E_MODEL_INVALID` con la guía de reconfiguración.

**Excepciones de dominio** (las que los handlers traducen al dialecto `E_*`):

* `EmbedderAuthError` → `E_API_AUTH`: clave AUSENTE (chequeo local, sin red)
  o rechazada (401/403). Transporta SOLO el nombre de `api_key_env`.
* `EmbedderOfflineError` → `E_OFFLINE_NO_CACHE`: carga local que falla CON
  modo offline (`HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE`).
* `EmbedderModelError` → `E_MODEL_INVALID`: snapshot ausente o carga local
  que falla sin offline (modelo corrupto/no-embeddings).
* `EmbedderUnavailableError` → `E_NO_EMBEDDER`: corte pedido con config
  `none` (defensa tras la costura `embedder_available`).
* `EmbedderApiError` → `INTERNAL` (vía guard): rate limit/timeout/red — con
  la clave SCRUBEADA (`str.replace(valor, "***")`) y elevado `from None`.

**Seguridad de la clave:** la precedencia env > fichero vive en
`EmbeddingConfig.resolve_api_key` (compartida con el flow); aquí solo se
consume para pasarla a la op y para el scrub. Jamás se concatena a mensajes.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Literal, Protocol, cast

from tepochcalli_flow.config import Config
from tepochcalli_flow.model_store import is_materialized

type EmbedderMode = Literal["local", "api", "none"]
"""Vocabulario D7.3/ADR-007 de `rag_status.embedder.mode` (spec §rag_status)."""

_OFFLINE_ENV_VARS = ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")
"""Flags de modo offline de la cadena HF/transformers (spec §`--offline`, D7/ADR-007)."""


# --- excepciones de dominio: los handlers las traducen al dialecto E_* -------------------


class EmbedderAuthError(RuntimeError):
    """Clave ausente o rechazada (401/403) — transporta SOLO el nombre de la env var.

    Hereda de `RuntimeError` —NUNCA de `ValueError`—: en los handlers el
    `ValueError` de validación se captura primero y se respondería
    `VALIDATION_ERROR` en vez del dialecto `E_API_AUTH` (lección del primer
    GREEN de T6: el orden de los `except` importa tanto como las clases).
    """

    def __init__(self, api_key_env: str) -> None:
        """`api_key_env` es el nombre de la variable (nunca un valor de clave)."""
        super().__init__(api_key_env)


class EmbedderOfflineError(RuntimeError):
    """Carga local fallida CON modo offline y sin cache — `E_OFFLINE_NO_CACHE`."""


class EmbedderModelError(RuntimeError):
    """Snapshot ausente o carga local fallida sin offline — `E_MODEL_INVALID`."""


class EmbedderUnavailableError(RuntimeError):
    """Corte pedido con config `none` — `E_NO_EMBEDDER` (defensa tras el seam R1)."""


class EmbedderApiError(RuntimeError):
    """Fallo de API no cubierto (rate limit/timeout/red) — `INTERNAL` vía guard.

    El mensaje llega YA SCRUBEADO desde `api_cut` y se eleva `from None`: el
    traceback que el guard loggea no puede contener la clave.
    """


class AsyncEmbedder(Protocol):
    """Superficie mínima de la op de cocoindex que este módulo consume (D59)."""

    async def embed(self, text: str) -> object:
        """Vector del texto (la op devuelve un `NDArray`; aquí solo se itera)."""
        ...


type LocalOpFactory = Callable[[Path, str], AsyncEmbedder]
"""`(path_estable, device) -> op` — el composition root inyecta `SentenceTransformerEmbedder`."""

type ApiOpFactory = Callable[[str, str], AsyncEmbedder]
"""`(model, api_key) -> op` — el composition root inyecta `LiteLLMEmbedder`."""


def _offline_mode() -> bool:
    """¿Modo offline declarado por el entorno? (los dos flags de la cadena HF)."""
    return any(os.environ.get(name) for name in _OFFLINE_ENV_VARS)


def mode(config: Config) -> EmbedderMode:
    """Hecho rico D7.3: el `mode` del embedder para `config` — de aquí deriva `is_available`.

    Mapeo (spec §rag_status): `provider = "litellm"` ⇒ `"api"`;
    `"local"` ⇒ `"local"`; `"none"` ⇒ `"none"`.
    """
    provider = config.embedding.provider
    if provider == "litellm":
        return "api"
    if provider == "none":
        return "none"
    return "local"


def is_available(config: Config) -> bool:
    """Indica si `config` tiene embedder utilizable — costura `E_NO_EMBEDDER`.

    Derivada de `mode(config)`: `none` ⇒ False; `local`/`api` ⇒ True. Desde
    D15 el loader acepta `none`, así que esta costura decide sobre configs
    REALES — `search` e `index_refresh` responden `E_NO_EMBEDDER` antes de
    tocar el índice (precedencia D7.3).
    """
    return mode(config) != "none"


def require_local_model(config: Config) -> Path:
    """Path estable exigido por el read path; ausente ⇒ `E_MODEL_INVALID` (cero red).

    NO materializa ni importa torch: solo comprueba el directorio
    `<models>/<slug>@<sha>/` (el mismo que escribe el write path). El mensaje
    incluye la guía `tepochcalli config embedder` que el agente reporta.
    """
    path = config.embedding_model_path
    if not is_materialized(config):
        raise EmbedderModelError(
            f"snapshot local ausente en {path}; ejecuta `tepochcalli config embedder`"
        )
    return path


def build_read_cut(
    config: Config,
    *,
    local_op_factory: LocalOpFactory,
    api_op_factory: ApiOpFactory,
) -> Callable[[str], list[float]]:
    """Corte texto→vector del read path con las ops inyectadas desde el root (D59).

    `local`: exige el snapshot y construye la op con el **path estable**.
    `api`: resuelve la clave ANTES de llamar a la factory (sin clave no se
    toca el proveedor); conserva el mapeo `E_API_AUTH`/scrub de la casa.
    `none`: error tipado defensivo (el seam `is_available` ya respondió antes).
    """
    provider_mode = mode(config)
    if provider_mode == "none":
        raise EmbedderUnavailableError(
            "provider='none' (D15): no hay corte de embeddings que construir"
        )
    if provider_mode == "api":
        api_key_env = config.embedding.api_key_env
        api_key = config.embedding.resolve_api_key()
        if api_key is None:
            raise EmbedderAuthError(api_key_env)
        op = api_op_factory(config.embedding.model, api_key)
        return api_cut(op, api_key=api_key, api_key_env=api_key_env)
    path = require_local_model(config)
    return local_cut(local_op_factory(path, config.embedding.device))


def local_cut(op: AsyncEmbedder) -> Callable[[str], list[float]]:
    """Ejecuta la op local y clasifica sus fallos (offline vs inválido) — flag D7."""

    def cut(text: str) -> list[float]:
        try:
            # `asyncio.run` en el hilo del lector (`asyncio.to_thread`): la op
            # es async y este callable es sync por contrato del puerto.
            return _to_floats(asyncio.run(op.embed(text)))
        except Exception as exc:  # noqa: BLE001 — frontera: se clasifica TODO
            detail = f"{type(exc).__name__}: {exc}"
            if _offline_mode():
                raise EmbedderOfflineError(detail) from None
            raise EmbedderModelError(detail) from None

    return cut


def api_cut(
    op: AsyncEmbedder,
    *,
    api_key: str,
    api_key_env: str,
) -> Callable[[str], list[float]]:
    """Ejecuta la op de API y conserva NUESTRO dialecto + scrub de la clave.

    401/403 (por `status_code` o por nombre de clase) ⇒ `EmbedderAuthError`
    con SOLO el nombre de la variable; cualquier otro fallo ⇒
    `EmbedderApiError` con la clave reemplazada por `***` y `from None`.
    """

    def cut(text: str) -> list[float]:
        try:
            return _to_floats(asyncio.run(op.embed(text)))
        except EmbedderAuthError:
            raise
        except Exception as exc:  # noqa: BLE001 — frontera: se traduce TODO antes de elevar
            if _is_auth_error(exc):
                raise EmbedderAuthError(api_key_env) from None
            raise EmbedderApiError(_scrub(str(exc), api_key)) from None

    return cut


def _to_floats(vector: object) -> list[float]:
    """Normaliza el `NDArray` de la op a `list[float]` (contrato del puerto)."""
    return [float(value) for value in cast(Iterable[float], vector)]


def _is_auth_error(exc: BaseException) -> bool:
    """401/403 por status o por nombre de clase (patrón de la fuente cocoindex)."""
    if getattr(exc, "status_code", None) in (401, 403):
        return True
    return type(exc).__name__ in {"AuthenticationError", "PermissionDeniedError"}


def _scrub(message: str, secret: str) -> str:
    """Elimina el valor de la clave de cualquier texto de terceros (plan §9)."""
    return message.replace(secret, "***")
