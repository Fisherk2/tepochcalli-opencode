"""Verificador CLI del puerto de lectura — M4 «fila queryable» (T9).

Cierra el gate de Phase 1 «filas en LanceDB queryables con `{source_path,
heading, char_start, char_end}`» (tasks/todo.md → CP-C / M4) y el «verificador
CLI ejecutable» de T9 AC: abre la base de un vault REAL pasado como argumento,
cuenta las filas de `chunks`, ejecuta una consulta de ejemplo híbrida
ANN+FTS e imprime los chunks citados con su score.

**Solo LEE.** Toda la superficie usada (`connect_async`, `open_table`,
`count_rows`, búsqueda híbrida) es de lectura; el test de T9 snapshot-ea
`<vault>/.tepochcalli/db/` antes/después de esta corrida y afirma que nada
cambió. Nunca escribe en el vault ni en el índice (el índice es derivado y
reconstruible — spec-rag-engine §Rollback—, pero aun así jamás se le toca
un byte).

Uso:

    python -m tepochcalli_flow.verify <vault_root> [--query TEXTO]
        [--top-k N] [--path-filter GLOB]

El query vector lo produce el MISMO embedder configurado del vault
(`tepochcalli.toml` → `[embedding]`; el cache de modelos se resuelve con
`HF_HOME`/`SENTENCE_TRANSFORMERS_HOME` del entorno — en el vault real apunta
a `<vault>/.tepochcalli/models` vía `apply_model_cache_env`, en pruebas al
cache del spike T1). Sale con código 2 si la DB no existe (nunca la crea:
si el path falta, el usuario aún no indexó).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Final

from sentence_transformers import SentenceTransformer

from .adapters.lancedb_reader import LanceDBChunkReader
from .config import DEFAULT_EMBEDDING_DEVICE, DEFAULT_EMBEDDING_MODEL, load_config
from .ports import CitedChunk

DB_RELPATH: Final = Path(".tepochcalli/db/tepochcalli.lance")
"""Base LanceDB del vault (mismo relativo que `app.DB_RELPATH`; sin importar app)."""

EXIT_OK: Final = 0
EXIT_NO_DB: Final = 2
"""Código de salida cuando el vault no tiene índice — sin traceback."""


def main(argv: list[str] | None = None) -> int:
    """Entrypoint del verificador: parsea args, verifica el vault y cita chunks."""
    parser = argparse.ArgumentParser(
        prog="python -m tepochcalli_flow.verify",
        description=(
            "Verificador de lectura (T9/M4): cuenta filas de `chunks` en el vault "
            "y ejecuta una búsqueda híbrida ANN+FTS imprimiendo los chunks citados. "
            "SOLO LEE — nunca escribe en el vault ni en el índice."
        ),
    )
    parser.add_argument("vault_root", type=Path, help="Raíz del vault (contiene .tepochcalli/)")
    parser.add_argument(
        "--query",
        default="citas y offsets de carácter",
        help="Consulta de ejemplo (default: 'citas y offsets de carácter')",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Número de chunks citados a devolver (default: 5)",
    )
    parser.add_argument(
        "--path-filter",
        default=None,
        help="Glob relativo al vault, p. ej. '00-Resources/sub/**/*.md' (opcional)",
    )
    args = parser.parse_args(argv)

    vault_root: Path = args.vault_root
    db_uri = vault_root / DB_RELPATH
    if not db_uri.exists():
        print(
            f"ERROR: la base LanceDB no existe en {db_uri} — el vault aún no indexó "
            "(corre `app.update_blocking()` o `cocoindex update` sobre el flow primero)",
            file=sys.stderr,
        )
        return EXIT_NO_DB

    config = load_config(vault_root)
    model = SentenceTransformer(config.embedding.model, device=config.embedding.device)
    reader = LanceDBChunkReader(db_uri, embed=lambda text: model.encode(text).tolist())

    rows = asyncio.run(reader.count_rows())
    print(f"Vault:  {vault_root}")
    print(f"DB:     {db_uri} (solo lectura)")
    print(
        f"Modelo: {config.embedding.model or DEFAULT_EMBEDDING_MODEL} "
        f"@ {config.embedding.device or DEFAULT_EMBEDDING_DEVICE}"
    )
    print(f"Filas en `chunks`: {rows}")

    results = asyncio.run(reader.search(args.query, args.top_k, args.path_filter))
    print(f"\nConsulta: {args.query!r} (top_k={args.top_k}, path_filter={args.path_filter!r})")
    print(f"Chunks citados: {len(results)}")
    for position, chunk in enumerate(results, start=1):
        _print_chunk(position, chunk)
    return EXIT_OK


def _print_chunk(position: int, chunk: CitedChunk) -> None:
    """Imprime un chunk citado con los seis campos congelados de §search."""
    print(f"\n[{position}] score={chunk.score:.4f}")
    print(f"    source_path={chunk.source_path}")
    print(f"    heading={chunk.heading!r}")
    print(f"    [char_start={chunk.char_start}, char_end={chunk.char_end}]")
    print(f"    text={chunk.text!r}")


if __name__ == "__main__":
    sys.exit(main())
