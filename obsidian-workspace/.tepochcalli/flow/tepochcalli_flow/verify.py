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
(`tepochcalli.toml` → `[embedding]`), montado por
`adapters.lancedb_reader.build_reader`. Sale con código 2 si la DB no existe
(nunca la crea: si el path falta, el usuario aún no indexó) y 3 si la DB
existe pero la tabla/índice falla (indexación a medias o esquema roto).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Final

from .adapters.lancedb_reader import build_reader
from .config import load_config
from .ports import CitedChunk

DB_RELPATH: Final = Path(".tepochcalli/db/tepochcalli.lance")
"""Base LanceDB del vault (mismo relativo que `app.DB_RELPATH`; sin importar app)."""

EXIT_OK: Final = 0
EXIT_NO_DB: Final = 2
"""Código de salida cuando el vault no tiene índice — sin traceback."""
EXIT_DB_BROKEN: Final = 3
"""Salida cuando la DB existe pero el índice/tabla falla (esquema roto, a medio
indexar): distinta a 2 para diferenciar «aún no hay índice» de «hay índice pero
no sirve». Mensaje accionable por stderr, sin traceback."""


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
    if args.top_k < 1:
        parser.error(f"--top-k debe ser >= 1, recibido: {args.top_k}")

    vault_root: Path = args.vault_root
    db_uri = vault_root / DB_RELPATH
    if not db_uri.exists():
        print(
            f"ERROR: la base LanceDB no existe en {db_uri} — el vault aún no indexó "
            "(corre `app.update_blocking()` o `cocoindex update` sobre el flow primero)",
            file=sys.stderr,
        )
        return EXIT_NO_DB

    reader = build_reader(vault_root)
    config = load_config(vault_root)  # para el print: construir embedder es lo caro

    try:
        rows = asyncio.run(reader.count_rows())
    except Exception as exc:  # noqa: BLE001  # frontera CLI: lance/esquema/IO cuentan igual
        print(
            f"ERROR: la DB existe ({db_uri}) pero la tabla 'chunks' no se pudo leer — "
            f"el índice está a medio indexar o el esquema cambió: {exc}\n"
            "(borra .tepochcalli/db/ y reconstruye el índice con `app.update_blocking()`)",
            file=sys.stderr,
        )
        return EXIT_DB_BROKEN
    print(f"Vault:  {vault_root}")
    print(f"DB:     {db_uri} (solo lectura)")
    print(f"Modelo: {config.embedding.model} @ {config.embedding.device}")
    print(f"Filas en `chunks`: {rows}")

    try:
        results = asyncio.run(reader.search(args.query, args.top_k, args.path_filter))
    except Exception as exc:  # noqa: BLE001  # frontera CLI, misma política que count_rows
        print(
            f"ERROR: la búsqueda sobre 'chunks' falló (índice roto o esquema inesperado): {exc}",
            file=sys.stderr,
        )
        return EXIT_DB_BROKEN
    print(f"\nConsulta: {args.query!r} (top_k={args.top_k}, path_filter={args.path_filter!r})")
    print(f"Chunks citados: {len(results)}")
    for position, chunk in enumerate(results, start=1):
        _print_chunk(position, chunk)
    return EXIT_OK


def _print_chunk(position: int, chunk: CitedChunk) -> None:
    """Imprime un chunk citado con los siete campos congelados de §search."""
    print(f"\n[{position}] score={chunk.score:.4f}")
    print(f"    source_path={chunk.source_path}")
    print(f"    heading={chunk.heading!r}")
    print(f"    [char_start={chunk.char_start}, char_end={chunk.char_end}]")
    print(f"    offsets_ref={chunk.offsets_ref}")
    print(f"    text={chunk.text!r}")


if __name__ == "__main__":
    sys.exit(main())
