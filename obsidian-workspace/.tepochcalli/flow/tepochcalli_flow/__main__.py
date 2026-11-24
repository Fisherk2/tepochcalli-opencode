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
    `model_store.ensure_local_model`) y valida con la frase de control. Todo
    fallo de carga/embed —repo inexistente, no-embeddings, red caída— se
    reporta como `E_MODEL_INVALID` con `detail`.
    shortcut: el CLI no distingue «no-embedding» de «no-descargable» sin
    reimplementar la taxonomía de errores de HF/transformers; el wizard
    (T11) decide reintentos por su lado con el `detail` como pista.
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
            "error_code": ERROR_MODEL_INVALID,
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
