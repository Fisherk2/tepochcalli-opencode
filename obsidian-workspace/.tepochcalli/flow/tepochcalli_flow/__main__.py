"""CLI mínimo del flow (T12, D24): `refresh` + `embed-check`.

Lo invoca el wizard Rust vía `CommandRunner` con el python del vault
(`<vault>/.tepochcalli/venv/bin/python -m tepochcalli_flow …`, cwd = vault) y
`HF_HOME`/`SENTENCE_TRANSFORMERS_HOME` apuntando a `.tepochcalli/models/`.
Toda la salida de contrato va a stdout como UNA línea JSON (el wizard la
parsea); los errores inesperados van a stderr con código distinto de cero.

* `refresh`: un ciclo Δ (`app.refresh_blocking`, el mismo entrypoint que el
  MCP `index_refresh`) e imprime `{scanned, indexed, skipped, elapsed_ms}`.
* `embed-check --model <id>`: descarga el modelo con la ruta del flow
  (`config.apply_model_cache_env` + `SentenceTransformer`), incrusta la frase
  de control e imprime `{ok, model, dims, rss_peak_bytes}` o `{ok: false,
  error_code}`. El RSS pico se mide EN ESTE PROCESO (D25).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

CONTROL_PHRASE: Final = "tepochcalli embedding check"
"""Frase de control del gate (AC T12/T11: literal congelado del contrato)."""

ERROR_MODEL_INVALID: Final = "E_MODEL_INVALID"
"""Código del portero: el repo no es un modelo de embeddings (plan §5.4)."""

ERROR_MODEL_DOWNLOAD_FAILED: Final = "E_MODEL_DOWNLOAD_FAILED"
"""Fallo de red/descarga del snapshot; el código viaja al panel del wizard."""

ERROR_MODEL_LOAD_FAILED: Final = "E_MODEL_LOAD_FAILED"
"""Fallo de carga/dispositivo; también el fallback de causa desconocida."""

# Heurística acotada, no una taxonomía de HF/transformers: basta con los nombres
# de las excepciones de descarga (huggingface_hub 1.33.0, verificado en su doc)
# y marcadores estables de «repo que no es de embeddings».
_DOWNLOAD_ERROR_NAMES: Final = frozenset(
    {
        "HfHubHTTPError",
        "EntryNotFoundError",
        "LocalEntryNotFoundError",
        "RemoteEntryNotFoundError",
        "OfflineModeIsEnabled",
        "HTTPError",
        "URLError",
        "ConnectError",
        "ConnectTimeout",
        "ReadTimeout",
        "TimeoutException",
    }
)
_NOT_EMBEDDING_MARKERS: Final = (
    "not a sentence-transformers",
    "no sentence-transformers model found",
    "not an embedding model",
)


def classify_embed_error(exc: Exception) -> str:
    """Clasifica la causa del gate en un único punto (sin importar HF).

    Solo mira nombres de clase y marcadores de texto: red antes que identidad
    (un error HTTP puede nombrar el modelo), y carga como fallback seguro para
    que una causa desconocida nunca se disfrace de `E_MODEL_INVALID`.
    """
    names = {base.__name__ for base in type(exc).__mro__}
    if _DOWNLOAD_ERROR_NAMES.intersection(names):
        return ERROR_MODEL_DOWNLOAD_FAILED
    detail = str(exc).lower()
    if any(marker in detail for marker in _NOT_EMBEDDING_MARKERS):
        return ERROR_MODEL_INVALID
    return ERROR_MODEL_LOAD_FAILED


class EmbedCheckError(Exception):
    """El embed-check no pudo medirse (plataforma sin `resource`, etc.)."""


def run_refresh() -> dict[str, int]:
    """Un ciclo Δ sobre el vault y su `RefreshReport` como dict (costura de test).

    Import perezoso de `app` (arrastra `cocoindex`): el import del CLI y su
    `--help` no pagan el arranque del motor. La raíz del vault sale de
    `TEPOCHCALLI_VAULT_ROOT` si está (tests, MCP) o del cwd (el wizard lo fija
    como cwd al invocar).
    """
    from .app import VAULT_ROOT_ENV, refresh_blocking

    os.environ.setdefault(VAULT_ROOT_ENV, str(Path.cwd()))
    report = refresh_blocking()
    return {
        "scanned": report.scanned,
        "indexed": report.indexed,
        "skipped": report.skipped,
        "elapsed_ms": report.elapsed_ms,
    }


def build_embedder_for_model(model: str, revision: str | None = None) -> SentenceTransformer:
    """Materializa el snapshot de `model@revision` y lo carga desde el path estable.

    Es la MISMA materialización del write path (`model_store.ensure_local_model`):
    `<models>/<slug>@<sha>/` con `revision` pineada. El `embed-check` del wizard
    (F6) usa esta función; el read path nunca descarga. Sin `revision`, se
    hereda la config resuelta del vault (default `MODEL_REVISION`).
    """
    from sentence_transformers import SentenceTransformer

    from .config import load_config
    from .model_store import ensure_local_model

    vault_root = Path(os.environ.get("TEPOCHCALLI_VAULT_ROOT", ""))
    config = load_config(vault_root if vault_root else Path.cwd())
    config.apply_model_cache_env()
    candidate = replace(
        config,
        embedding=replace(
            config.embedding,
            model=model,
            revision=revision or config.embedding.revision,
        ),
    )
    return SentenceTransformer(str(ensure_local_model(candidate)))


def rss_peak_bytes() -> int:
    """RSS pico del proceso actual, normalizado a BYTES (OM-6).

    `resource.getrusage(RUSAGE_SELF).ru_maxrss` informa kilobytes en Linux y
    bytes en macOS: la rama de plataforma es el contrato, no un detalle.
    """
    try:
        import resource
    except ImportError as exc:
        raise EmbedCheckError(
            "medición de RSS no disponible en esta plataforma (se exige POSIX)"
        ) from exc
    peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if sys.platform == "darwin":
        return peak
    return peak * 1024


def cmd_refresh() -> dict[str, int]:
    """Ejecuta `refresh` y devuelve el payload JSON del contrato."""
    return run_refresh()


def cmd_embed_check(model: str, revision: str | None = None) -> dict[str, object]:
    """Ejecuta `embed-check` para `model` y devuelve el veredicto JSON.

    Materializa `<models>/<slug>@<revision>/` (una sola función,
    `model_store.ensure_local_model`) y valida con la frase de control. Un
    único seam (`classify_embed_error`) separa tres causas con heurística
    acotada: tags no-embedding (`E_MODEL_INVALID`), red/descarga
    (`E_MODEL_DOWNLOAD_FAILED`) y carga/dispositivo (`E_MODEL_LOAD_FAILED`,
    código de fallback). El `detail` real se conserva (≤300 chars).
    """
    try:
        vector = build_embedder_for_model(model, revision).encode(CONTROL_PHRASE)
        return {
            "ok": True,
            "model": model,
            "dims": len(vector),
            "rss_peak_bytes": rss_peak_bytes(),
        }
    except Exception as exc:
        return {
            "ok": False,
            "model": model,
            "error_code": classify_embed_error(exc),
            "detail": str(exc)[:300],
        }


def main(argv: list[str] | None = None) -> int:
    """Entrypoint: parsea el subcomando, imprime su JSON en stdout, devuelve el exit."""
    parser = argparse.ArgumentParser(
        prog="python -m tepochcalli_flow",
        description="CLI mínimo del flow (T12/D24): refresh + embed-check.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("refresh", help="indexa el vault e imprime el RefreshReport en JSON")
    embed = sub.add_parser("embed-check", help="gate test-embed: frase de control + RSS pico")
    embed.add_argument("--model", required=True, help="id del modelo de HuggingFace")
    embed.add_argument(
        "--revision",
        default=None,
        help="SHA de la revisión HF (default: la de tepochcalli.toml / MODEL_REVISION)",
    )
    args = parser.parse_args(argv)
    try:
        payload = (
            cmd_refresh()
            if args.command == "refresh"
            else cmd_embed_check(args.model, args.revision)
        )
    except Exception as exc:  # noqa: BLE001 — el traceback íntegro va a stderr, nunca al JSON
        print(f"tepochcalli_flow {args.command}: {exc!r}", file=sys.stderr)
        return 1
    json.dump(payload, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
