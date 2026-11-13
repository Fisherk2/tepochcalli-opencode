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
        [--top-k N] [--path-filter GLOB] [--spot-check N]

`--spot-check N` (TD-13) muestrea hasta N filas y re-verifica la identidad F1
(`text[char_start:char_end] == chunk.text`) contra el ARCHIVO VIVO: `source`
corta el original, `extract` re-extrae el documento con markitdown (D50). Si
alguna cita ya no reproduce su texto —edición externa posterior a la
indexación, TD-4— publica la tasa y sale con código 1.

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

from .adapters.lancedb_reader import LanceDBChunkReader, build_reader
from .citation import OFFSETS_REF_SOURCE, verify_slice_identity
from .config import load_config
from .layout import DB_RELPATH
from .parsers import ExtractionError, extract_text
from .ports import CitedChunk

EXIT_OK: Final = 0
EXIT_NO_DB: Final = 2
"""Código de salida cuando el vault no tiene índice — sin traceback."""
EXIT_DB_BROKEN: Final = 3
"""Salida cuando la DB existe pero el índice/tabla falla (esquema roto, a medio
indexar): distinta a 2 para diferenciar «aún no hay índice» de «hay índice pero
no sirve». Mensaje accionable por stderr, sin traceback."""
EXIT_SPOT_BROKEN: Final = 1
"""Salida cuando `--spot-check` encuentra citas no reproducibles (TD-13).

El índice existe y se leyó, pero al menos una cita ya no reproduce su texto
contra el archivo VIVO (editado por otra app, borrado o re-extraído distinto):
la cita es estructuralmente válida y falsa — daño directo al criterio 5.
"""


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
    parser.add_argument(
        "--spot-check",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Re-verifica la identidad F1 de hasta N filas muestreadas contra el "
            "archivo vivo (TD-13); exit 1 si alguna cita ya no reproduce su texto"
        ),
    )
    args = parser.parse_args(argv)
    if args.top_k < 1:
        parser.error(f"--top-k debe ser >= 1, recibido: {args.top_k}")
    if args.spot_check is not None and args.spot_check < 1:
        parser.error(f"--spot-check debe ser >= 1, recibido: {args.spot_check}")

    vault_root: Path = args.vault_root.resolve()
    db_uri = vault_root / DB_RELPATH
    if not db_uri.exists():
        print(
            f"ERROR: la base LanceDB no existe en {db_uri} — el vault aún no indexó "
            "(corre `app.update_blocking()` o `cocoindex update` sobre el flow primero)",
            file=sys.stderr,
        )
        return EXIT_NO_DB

    try:
        reader = build_reader(vault_root)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_DB_BROKEN
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
        _print_chunk(position, vault_root, chunk)
    if args.spot_check is not None:
        return _run_spot_check(vault_root, reader, args.spot_check)
    return EXIT_OK


def _live_identity(vault_root: Path, chunk: CitedChunk) -> str | None:
    """Re-verifica la identidad F1 contra el archivo VIVO (TD-13); `None` si reproduce.

    `offsets_ref == "source"` corta el archivo ORIGINAL (md/markdown/txt);
    `"extract"` corta el texto que markitdown extrae HOY del binario (D50) —
    el binario nunca es espacio de cita. Devuelve la severidad del fallo:
    `MISSING` si el archivo ya no está, `BROKEN` si el slice no reproduce
    `text` o la extracción falla. Nunca lanza: una cita rota es el hallazgo,
    no un crash del verificador.
    """
    path = vault_root / chunk.source_path
    if not path.is_file():
        return "MISSING"
    try:
        text = (
            path.read_text(encoding="utf-8")
            if chunk.offsets_ref == OFFSETS_REF_SOURCE
            else extract_text(path)
        )
    except (OSError, ValueError, ExtractionError):
        return "BROKEN"
    if verify_slice_identity(text, chunk.char_start, chunk.char_end, chunk.text):
        return None
    return "BROKEN"


def _run_spot_check(vault_root: Path, reader: LanceDBChunkReader, requested: int) -> int:
    """Muestrea hasta `requested` filas y publica la tasa de citas reproducibles (TD-13)."""
    rows = asyncio.run(reader.sample_rows(requested))
    print(f"\nSpot-check (TD-13): {len(rows)} filas muestreadas (pide {requested})")
    broken = 0
    for chunk in rows:
        severity = _live_identity(vault_root, chunk)
        if severity is not None:
            broken += 1
        print(
            f"  [{severity or 'OK'}] {chunk.source_path} offsets_ref={chunk.offsets_ref} "
            f"[{chunk.char_start}, {chunk.char_end})"
        )
    reproducible = len(rows) - broken
    rate = 100.0 * reproducible / len(rows) if rows else 100.0
    print(f"Tasa de citas reproducibles: {reproducible}/{len(rows)} ({rate:.1f}%) — {broken} rotas")
    return EXIT_SPOT_BROKEN if broken else EXIT_OK


def _source_slice_ok(vault_root: Path, chunk: CitedChunk) -> bool | None:
    """Comprueba la identidad F1 contra el ORIGINAL (o `None` si no aplica).

    `source_path` es relativo al vault (D41), así que el original se resuelve
    como `vault_root / source_path` — nunca `vault_root / 00-Resources / …`.
    Solo aplica a `offsets_ref == "source"`; un binario extraído no es espacio
    de cita (D50). Un fichero ausente devuelve `False`: la cita no es
    reproducible y el verificador debe decirlo.
    """
    if chunk.offsets_ref != "source":
        return None
    try:
        original = (vault_root / chunk.source_path).read_text(encoding="utf-8")
    except OSError:
        return False
    return verify_slice_identity(original, chunk.char_start, chunk.char_end, chunk.text)


def _print_chunk(position: int, vault_root: Path, chunk: CitedChunk) -> None:
    """Imprime un chunk citado con los siete campos congelados de §search."""
    slice_ok = _source_slice_ok(vault_root, chunk)
    slice_label = "n/a" if slice_ok is None else ("OK" if slice_ok else "BROKEN")
    print(f"\n[{position}] score={chunk.score:.4f}")
    print(f"    source_path={chunk.source_path}")
    print(f"    heading={chunk.heading!r}")
    print(f"    [char_start={chunk.char_start}, char_end={chunk.char_end}]")
    print(f"    offsets_ref={chunk.offsets_ref}")
    print(f"    slice={slice_label}")
    print(f"    text={chunk.text!r}")


if __name__ == "__main__":
    sys.exit(main())
