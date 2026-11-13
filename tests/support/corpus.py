"""Corpus de escala reproducible con manifiesto (Phase 6, T1).

Un solo generador determinista de **10 000 notas md** (10 subdirs × 1 000) y
**1 000 PDF de 1 página** válidos (xref computado, texto extraíble por
markitdown) bajo `root/00-resources/`, más el manifiesto `corpus-manifest.json`
en la raíz del corpus (fuera de la raíz indexable).

Por qué existe
--------------
El bench de escala (`tests/benchmarks/bench_delta_scale.py`) ya sabía generar
este corpus, pero lo borraba al terminar y no dejaba rastro verificable. Phase 6
necesita el MISMO corpus dos veces (criterios 3 y 6) y poder demostrar que es el
mismo byte a byte: de ahí el manifiesto (sha256 por fichero + hash de árbol) y
la reutilización sin reindexar.

Contrato
--------
* `materialize(root, md_count=, pdf_count=, seed=)` — escribe el corpus y su
  manifiesto; devuelve el `Manifest`.
* `verify(root, manifest)` — lista de discrepancias (vacía = OK).
* `materialize_or_verify(...)` — reutiliza el corpus si el manifiesto verifica y
  **lanza** si no verifica: un corpus alterado no se regenera en silencio.

Nunca borra nada que no haya escrito él mismo, y nunca toca
`obsidian-workspace/.tepochcalli/{db,models}` (materializa solo en `root`).
Sigue siendo herramienta de medición: no es un `test_*` y no entra en `just ci`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

RESOURCES_DIR = "00-resources"
"""Raíz indexable del vault: el manifiesto queda FUERA para no indexarse."""

MANIFEST_NAME = "corpus-manifest.json"
"""Nombre del manifiesto, relativo a la raíz del corpus."""

GENERATOR_VERSION = "1"
"""Bump obligatorio si cambia el contenido generado (invalida manifiestos)."""

DEFAULT_SEED = 20261103
DEFAULT_MD_FILES = 10_000
DEFAULT_PDF_FILES = 1_000
MD_PER_SUBDIR = 1_000

WORDS = (
    "notas citas offsets índice lancedb cocoindex chunking vault obsidian "
    "recursos agente flujo delta refresh incremental heading párrafo "
    "documento texto fuente confianza percentil latencia presupuesto parser "
    "tablas unicode identidad fila tabla índice ann fts benchmark escala "
).split()

PDF_WORDS = (
    "brisa orfandad oficina temblor rincon laurel noria aldeas comercio "
    "tablas escala nota credito inviernos nieblas arboles cortijo "
).split()
"""Vocabulario ASCII del cuerpo del PDF: Helvetica + `Tj` sin escaping ni encoding raro."""


@dataclass(frozen=True)
class CorpusFile:
    """Una entrada del manifiesto: ruta relativa a la raíz del corpus + su hash."""

    path: str
    sha256: str
    bytes: int
    kind: str


@dataclass(frozen=True)
class Manifest:
    """Value object del corpus: inmutable, sin timestamps ni rutas absolutas."""

    seed: int
    generator_version: str
    files: tuple[CorpusFile, ...]

    @property
    def tree_sha256(self) -> str:
        """Hash del árbol: sha256 de las líneas `<sha256>  <path>` ordenadas."""
        ordered = sorted(self.files, key=lambda entry: entry.path)
        lines = "".join(f"{entry.sha256}  {entry.path}\n" for entry in ordered)
        return hashlib.sha256(lines.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        """Forma serializable completa (incluye totales y hash de árbol)."""
        ordered = sorted(self.files, key=lambda entry: entry.path)
        return {
            "files": [asdict(entry) for entry in ordered],
            "generator_version": self.generator_version,
            "seed": self.seed,
            "totals": {
                "bytes": sum(entry.bytes for entry in ordered),
                "files": len(ordered),
                "md": sum(1 for entry in ordered if entry.kind == "md"),
                "pdf": sum(1 for entry in ordered if entry.kind == "pdf"),
            },
            "tree_sha256": self.tree_sha256,
        }

    def canonical_json(self) -> str:
        """JSON canónico: `sort_keys=True`, sin espacios ⇒ el mismo corpus da el mismo texto."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Manifest:
        """Reconstruye el manifiesto leído de `corpus-manifest.json`."""
        return cls(
            seed=int(data["seed"]),
            generator_version=str(data["generator_version"]),
            files=tuple(CorpusFile(**entry) for entry in data["files"]),
        )


def corpus_text(i: int, rng: random.Random) -> str:
    """Cuerpo determinista y PEQUEÑO (~0,5-1,2 KB ⇒ 1 chunk con el split 1536/192)."""
    target = rng.randint(500, 1_100)
    title = f"Nota {i:05d}"
    lines = [f"# {title}", ""]
    size = len(title) + 4
    while size < target:
        body = " ".join(rng.choice(WORDS) for _ in range(rng.randint(30, 60)))
        body = body[0].upper() + body[1:] + "."
        lines.append(body)
        lines.append("")
        size += len(body) + 4
    return "\n".join(lines)


def _minimal_pdf(title: str, body_lines: list[str]) -> bytes:
    """PDF 1 página VÁLIDO (xref correcto, offsets computados) — no dummy vacío.

    Sin dependencias nuevas: los objetos mínimos de PDF-1.4 que un extractor
    real (pdfminer vía markitdown) parsea con texto extraíble en `contents`.
    El vocabulario usa solo ASCII sin `(`/`)` ⇒ no hay escaping en `Tj`.
    """
    content = b"BT\n/F1 12 Tf\n72 720 Td\n"
    content += b"".join(f"({line}) Tj\n0 -14 Td\n".encode("ascii") for line in body_lines)
    content += b"ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref_pos = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref_pos,
    )
    return bytes(out)


def materialize(root: Path, *, md_count: int, pdf_count: int, seed: int) -> Manifest:
    """Materializa el corpus determinista bajo `root` y escribe su manifiesto."""
    files: list[CorpusFile] = []
    resources = root / RESOURCES_DIR
    rng = random.Random(seed)
    for i in range(md_count):
        sub = resources / f"notas-{i // MD_PER_SUBDIR:02d}"
        if i % MD_PER_SUBDIR == 0:
            sub.mkdir(parents=True, exist_ok=True)
        payload = corpus_text(i, rng).encode("utf-8")
        files.append(_write(sub / f"nota-{i:05d}.md", payload, root, "md"))

    if pdf_count:
        (resources / "pdfs").mkdir(parents=True, exist_ok=True)
    for i in range(pdf_count):
        rng_pdf = random.Random(seed + i)
        title = f"Informe PDF {i:05d}"
        lines = [title, *[rng_pdf.choice(PDF_WORDS).capitalize() for _ in range(5)]]
        payload = _minimal_pdf(title, lines)
        files.append(_write(resources / "pdfs" / f"informe-{i:05d}.pdf", payload, root, "pdf"))

    manifest = Manifest(seed=seed, generator_version=GENERATOR_VERSION, files=tuple(files))
    (root / MANIFEST_NAME).write_text(manifest.canonical_json() + "\n", encoding="utf-8")
    return manifest


def verify(root: Path, manifest: Manifest) -> list[str]:
    """Discrepancias entre el manifiesto y el disco (lista vacía = corpus íntegro)."""
    problems: list[str] = []
    for entry in sorted(manifest.files, key=lambda item: item.path):
        path = root / entry.path
        if not path.is_file():
            problems.append(f"falta {entry.path}")
            continue
        payload = path.read_bytes()
        if len(payload) != entry.bytes:
            problems.append(f"tamaño distinto en {entry.path}: {len(payload)} != {entry.bytes}")
        if hashlib.sha256(payload).hexdigest() != entry.sha256:
            problems.append(f"sha256 distinto en {entry.path}")
    declared = {entry.path for entry in manifest.files}
    for extra in sorted(set(_tree_files(root)) - declared):
        problems.append(f"fichero no declarado en el manifiesto: {extra}")
    return problems


def materialize_or_verify(
    root: Path, *, md_count: int, pdf_count: int, seed: int
) -> tuple[Manifest, bool]:
    """Reutiliza el corpus si su manifiesto verifica; si no hay manifiesto, lo materializa.

    Devuelve `(manifest, reused)`. Un manifiesto presente pero inválido **no** se
    regenera en silencio: lanza `RuntimeError` (borrar 11k ficheros ajenos por
    una discrepancia es exactamente lo que no debe pasar sin permiso).
    """
    existing = _read_manifest(root)
    if existing is None:
        return materialize(root, md_count=md_count, pdf_count=pdf_count, seed=seed), False
    counts = {
        kind: sum(1 for entry in existing.files if entry.kind == kind) for kind in ("md", "pdf")
    }
    if (
        existing.seed != seed
        or existing.generator_version != GENERATOR_VERSION
        or counts != {"md": md_count, "pdf": pdf_count}
    ):
        raise RuntimeError(
            f"el manifiesto de {root} no describe seed={seed}, {md_count} md y {pdf_count} pdf "
            f"(seed={existing.seed}, v{existing.generator_version}, {counts}): usa otra raíz"
        )
    problems = verify(root, existing)
    if problems:
        sample = "; ".join(problems[:5]) + (" …" if len(problems) > 5 else "")
        raise RuntimeError(f"corpus alterado en {root} ({len(problems)} discrepancias): {sample}")
    return existing, True


def _write(path: Path, payload: bytes, root: Path, kind: str) -> CorpusFile:
    path.write_bytes(payload)
    return CorpusFile(
        path=path.relative_to(root).as_posix(),
        sha256=hashlib.sha256(payload).hexdigest(),
        bytes=len(payload),
        kind=kind,
    )


def _tree_files(root: Path) -> dict[str, Path]:
    base = root / RESOURCES_DIR
    if not base.is_dir():
        return {}
    return {path.relative_to(root).as_posix(): path for path in base.rglob("*") if path.is_file()}


def _read_manifest(root: Path) -> Manifest | None:
    path = root / MANIFEST_NAME
    if not path.is_file():
        return None
    return Manifest.from_dict(json.loads(path.read_text(encoding="utf-8")))


def main() -> int:
    """CLI: materializa (o reutiliza) el corpus y publica sus cifras como JSON."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, required=True, help="raíz del corpus (fuera del repo)")
    parser.add_argument("--md", type=int, default=DEFAULT_MD_FILES, help="número de notas md")
    parser.add_argument("--pdf", type=int, default=DEFAULT_PDF_FILES, help="número de PDFs")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="semilla del generador")
    args = parser.parse_args()

    started = time.monotonic()
    manifest, reused = materialize_or_verify(
        args.root, md_count=args.md, pdf_count=args.pdf, seed=args.seed
    )
    elapsed_ms = int((time.monotonic() - started) * 1000)

    print(
        json.dumps(
            {
                "root": str(args.root.resolve()),
                "reused": reused,
                "elapsed_ms": elapsed_ms,
                "seed": manifest.seed,
                "generator_version": manifest.generator_version,
                "totals": manifest.to_dict()["totals"],
                "tree_sha256": manifest.tree_sha256,
                # Hash del fichero tal cual: cuadra con `sha256sum corpus-manifest.json`.
                "manifest_sha256": hashlib.sha256(
                    (args.root / MANIFEST_NAME).read_bytes()
                ).hexdigest(),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
