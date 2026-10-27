"""Hechos del embedder por provider — Strategy de LECTURA con el dialecto de fallos (T6).

Fábrica `build_embedder(config)`: `local` ⇒ `SentenceTransformer` pineado a
`config.MODEL_REVISION` (el único binario que reproduce los embeddings del
índice, spec-embeddings §provenance); `litellm` ⇒ `litellm.embedding(model,
input, api_key=…)` sincrónico (fuente instalada `litellm/main.py:6303`,
`EmbeddingResponse.data[0]["embedding"]`); `none` ⇒ error tipado defensivo.

**Excepciones de dominio** (T6 — las que los handlers traducen al dialecto
`E_*`; la escritura usa las hermanas del flow en `app.py`):

* `EmbedderAuthError` → `E_API_AUTH`: clave AUSENTE (chequeo local, sin red)
  o rechazada (401/403). transporta SOLO el nombre de `api_key_env`.
* `EmbedderOfflineError` → `E_OFFLINE_NO_CACHE`: carga local que falla CON
  modo offline (`HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE`).
* `EmbedderModelError` → `E_MODEL_INVALID`: carga local que falla SIN offline
  (descarga fallida o no es modelo de embeddings).
* `EmbedderUnavailableError` → `E_NO_EMBEDDER`: corte pedido con config
  `none` (defensa tras el seam `embedder_available` del R1).
* `EmbedderApiError` → `INTERNAL` (vía guard): rate limit/timeout/red — con
  la clave SCRUBEADA (`str.replace(valor, "***")`) y elevado `from None`, de
  modo que ni `repr` ni el `logger.exception` del guard pueden verla (plan §9
  riesgo crítico).

**Seguridad de la clave (spec-embeddings §Security):** config guarda solo el
NOMBRE `api_key_env`; el valor se lee de `os.environ` aquí, se pasa como kwarg
a litellm y JAMÁS se concatena en mensajes — el scrub del wrapper es la red de
seguridad para los errores de terceros (security-and-hardening: traducir las
excepciones de la biblioteca en el borde).

**Módulo LIGERO en import:** `sentence_transformers` (⇒ torch) y `litellm`
(pesado) se importan DENTRO de las ramas — `tools/rag_status.py` importa
`mode`/`is_available` y el arranque stdio no paga nada de esto hasta la
primera búsqueda (pereza de `_backend()` en `server.py`). Un módulo falso en
`sys.modules` basta para testear sin red (contract tests T6).

El cache de modelos del vault debe estar aplicado ANTES de construir el corte
(`config.apply_model_cache_env()`, spec-rag-engine §Embeddings E1/T3): los
pesos caen en `<vault>/.tepochcalli/models`, jamás en `~/.cache` del usuario.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Literal

from tepochcalli_flow import citation
from tepochcalli_flow.config import MODEL_REVISION, Config

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
    """Carga local fallida SIN offline (descarga fallida o no-es-modelo) — `E_MODEL_INVALID`."""


class EmbedderUnavailableError(RuntimeError):
    """Corte pedido con config `none` — `E_NO_EMBEDDER` (defensa tras el seam R1)."""


class EmbedderApiError(RuntimeError):
    """Fallo de API no cubierto (rate limit/timeout/red) — `INTERNAL` vía guard.

    El mensaje llega YA SCRUBEADO desde el wrapper de litellm y se eleva
    `from None`: el traceback que el guard loggea no puede contener la clave.
    """


def _offline_mode() -> bool:
    """¿Modo offline declarado por el entorno? (los dos flags de la cadena HF)."""
    return any(os.environ.get(name) for name in _OFFLINE_ENV_VARS)


def mode(config: Config) -> EmbedderMode:
    """Hecho rico D7.3: el `mode` del embedder para `config` — de aquí deriva `is_available`.

    Mapeo (spec §rag_status): `provider = "litellm"` ⇒ `"api"`;
    `"local"` ⇒ `"local"`; `"none"` ⇒ `"none"`.

    D15 (T6) hizo `none` EXPRESABLE por el loader: hasta T6 era inalcanzable
    vía `tepochcalli.toml` y solo un `Config` construido a mano lo daba; hoy
    el loader lo acepta (3.er valor) y `is_available` devuelve `False` para
    configs reales degradados — la precedencia `E_NO_EMBEDDER` dejó de ser
    costura de test y es comportamiento end-to-end.
    """
    provider = config.embedding.provider
    if provider == "litellm":
        return "api"
    if provider == "none":
        return "none"
    return "local"


def is_available(config: Config) -> bool:
    """Indica si `config` tiene embedder utilizable — costura `E_NO_EMBEDDER` (T3/T6).

    Derivada de `mode(config)` (una sola fuente de verdad): `none` ⇒ False;
    `local`/`api` ⇒ True. Desde D15 el loader acepta `none`, así que esta
    costura decide sobre configs REALES — `search` e `index_refresh` responden
    `E_NO_EMBEDDER` antes de tocar el índice (precedencia D7.3).
    """
    return mode(config) != "none"


def build_embedder(config: Config) -> Callable[[str], list[float]]:
    """Corte texto→vector del provider configurado — Strategy de lectura (T6).

    `local` pinea `MODEL_REVISION` para que la query se vectorice con el MISMO
    binario que indexó (ADR-006). Los fallos de carga se traducen AQUÍ al
    dominio (offline vs inválido por flag) y los de API en la rama litellm —
    nunca dejan una excepción de terceros viva hacia el handler (que la
    convertiría en `INTERNAL` con el texto crudo de litellm en el log).
    """
    provider_mode = mode(config)
    if provider_mode == "none":
        raise EmbedderUnavailableError(
            "provider='none' (D15): no hay corte de embeddings que construir"
        )
    if provider_mode == "api":
        return _litellm_cut(config)
    return _local_cut(config)


def _local_cut(config: Config) -> Callable[[str], list[float]]:
    """Rama `local`: `SentenceTransformer` con clasificación offline/inválido (flag D7)."""
    from sentence_transformers import SentenceTransformer

    try:
        model = SentenceTransformer(
            citation.model_id(config),
            device=config.embedding.device,
            revision=MODEL_REVISION,
        )
    except Exception as exc:  # noqa: BLE001 — frontera: cualquier fallo de carga se clasifica
        detail = f"{type(exc).__name__}: {exc}"
        if _offline_mode():
            raise EmbedderOfflineError(detail) from None
        raise EmbedderModelError(detail) from None
    return lambda text: model.encode(text).tolist()


def _litellm_cut(config: Config) -> Callable[[str], list[float]]:
    """Rama `litellm`: clave SOLO del entorno + `litellm.embedding` sincrónico con scrub.

    La clave se lee UNA vez en la construcción: ausente ⇒ `EmbedderAuthError`
    ANTES de importar litellm ni llamar a la API (chequeo local, cero red).
    En la llamada, cualquier excepción no-credenciales se traduce a
    `EmbedderApiError` con la clave reemplazada por `***` y `from None` — el
    valor jamás llega a `repr`, logs ni payloads.
    """
    api_key_env = config.embedding.api_key_env
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise EmbedderAuthError(api_key_env)
    model = config.embedding.model

    def cut(text: str) -> list[float]:
        import litellm  # perezoso: paquete pesado; testeable con un módulo falso en sys.modules

        try:
            response = litellm.embedding(model=model, input=[text], api_key=api_key)
            embedding = response.data[0]["embedding"]
        except Exception as exc:  # noqa: BLE001 — frontera: se traduce TODO antes de elevar
            if _is_auth_error(exc):
                raise EmbedderAuthError(api_key_env) from None
            raise EmbedderApiError(_scrub(str(exc), api_key)) from None
        return [float(value) for value in embedding]

    return cut


def _is_auth_error(exc: BaseException) -> bool:
    """401/403 por status o por nombre de clase (patrón de la fuente cocoindex: name sets)."""
    if getattr(exc, "status_code", None) in (401, 403):
        return True
    return type(exc).__name__ in {"AuthenticationError", "PermissionDeniedError"}


def _scrub(message: str, secret: str) -> str:
    """Elimina el valor de la clave de cualquier texto de terceros (plan §9)."""
    return message.replace(secret, "***")
