#!/usr/bin/env python3
"""Verificador mecánico de la evidencia de la corrida D9 (Phase 6, TD-31).

Uso:

    python3 tests/e2e/verify_methodology_evidence.py [DIR]

`DIR` (por defecto `tests/evidence/phase6`) debe contener los artefactos de la
corrida del QA: `<NN>-<comando>-transcript.txt`, `<NN>-<comando>-artifact.md`,
`vault-tree.txt` y `checklist.md`.

Comprueba SOLO lo mecánico:

    (a) cada artefacto en su bandeja y ninguna bandeja ajena con ficheros;
    (b) el frontmatter de cada artefacto trae los campos del formato vigente;
    (c) existe transcript de los 9 comandos y los ficheros de soporte;
    (d) MCP-first: `search` de `tepochcalli-rag` antes de leer crudo
        `00-resources/` en el transcript.

NO juzga la prosa, la calidad de las citas ni el veredicto editorial: eso es
del QA humano. Aquí solo se afirma forma y presencia.

Exit: 0 si todo pasa; 1 si algo falla (informe por punto); 2 si el directorio
no existe o no se puede leer.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

REPO: Final = Path(__file__).resolve().parents[2]
DEFAULT_EVIDENCE_DIR: Final = REPO / "tests" / "evidence" / "phase6"


@dataclass(frozen=True)
class Command:
    """Contrato mínimo de un comando: bandeja, artefactos, agente y frontmatter."""

    n: int
    name: str
    agent: str
    fields: tuple[str, ...]
    artifacts: tuple[str, ...]


# Contrato con tests/phase6-methodology-runbook.md §2: nombres deterministas.
# Si el runbook cambia un campo o una ruta, este bloque cambia en el mismo commit.
COMMANDS: Final = (
    Command(1, "rubric", "nezahualcoyotl", ("command", "agent", "date"), ("01-tasks/rubric.md",)),
    Command(
        2,
        "research",
        "pochteca",
        ("agent", "timestamp", "source", "method", "origin"),
        ("01-tasks/research/evidence.md",),
    ),
    Command(
        3,
        "validate",
        "chilam",
        ("command", "agent", "target_doc", "verdict"),
        ("04-review/validation.md",),
    ),
    Command(
        4,
        "synthesize",
        "nezahualcoyotl",
        ("command", "agent", "phase", "date"),
        ("01-tasks/outline.md",),
    ),
    Command(
        5,
        "cite",
        "chilam",
        ("command", "agent", "style", "date"),
        ("03-citations/bibliography.md",),
    ),
    Command(
        6, "draft", "tlacuilo", ("command", "agent", "outline", "date"), ("02-drafts/draft.md",)
    ),
    Command(
        7,
        "review",
        "chilam",
        ("command", "agent", "source", "rev"),
        ("02-drafts/draft-revA.md",),
    ),
    Command(
        8,
        "transform",
        "tlacuilo",
        ("command", "agent", "source_draft", "formats", "date"),
        (
            "05-outputs/comparison.csv",
            "05-outputs/fotosintesis.md",
            "05-outputs/transform-manifest.md",
        ),
    ),
    Command(
        9,
        "update",
        "tlacuilo",
        ("command", "agent", "date", "revision_note"),
        ("02-drafts/draft-revB.md",),
    ),
)

TRAY_ALLOWED: Final = {
    "01-tasks": (
        re.compile(r"^(?:rubric|plan|todo|outline)\.md$"),
        re.compile(r"^research/[^/]+\.md$"),
    ),
    "02-drafts": (re.compile(r"^draft(?:-rev[A-Z]+)?\.md$"),),
    "03-citations": (re.compile(r"^bibliography\.md$"),),
    "04-review": (re.compile(r"^validation\.md$"),),
    "05-outputs": (re.compile(r"^[^/]+\.(?:md|csv|xlsx|xls|pdf|png)$"),),
}

TRAY_PATH_RE: Final = re.compile(r"(?:(?:^|/)(0[1-5]-[a-z-]+))/(.+)$")
TOOL_MARKER_RE: Final = re.compile(
    r"\b(?:search|index_refresh|add_source|rag_status|list_formats|convert_document"
    r"|read|write|question|websearch)\b",
    re.IGNORECASE,
)
SEARCH_RE: Final = re.compile(r"\bsearch\b")
RAW_READ_RE: Final = re.compile(r"\b(?:read|cat|head|open|grep|glob)\b", re.IGNORECASE)
VERDICTS: Final = {"ok", "ok_with_warnings", "rejected"}


class Report:
    """Acumula PASS/FAIL por punto y decide el exit code al final."""

    def __init__(self) -> None:
        """Inicializa el contador de comprobaciones y fallos."""
        self.checks = 0
        self.failures = 0

    def check(self, point: str, ok: bool, message: str) -> None:
        """Imprime una comprobación y suma un fallo si no pasó."""
        self.checks += 1
        if not ok:
            self.failures += 1
        print(f"{'PASS' if ok else 'FAIL'} {point} {message}")


def parse_frontmatter(text: str) -> dict[str, str | list[str]] | None:
    """Devuelve el frontmatter YAML simple (clave → valor o lista) o ``None``."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return None
    data: dict[str, str | list[str]] = {}
    key: str | None = None
    for line in lines[1:end]:
        if not line.strip():
            continue
        match = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if match:
            key = match.group(1)
            data[key] = match.group(2).strip()
        elif key is not None and line.lstrip().startswith("- "):
            current = data.get(key)
            items = current if isinstance(current, list) else []
            items.append(line.lstrip()[2:].strip())
            data[key] = items
    return data


def frontmatter_body(text: str) -> str:
    """Devuelve el cuerpo tras el segundo delimitador ``---``."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return ""
    return "\n".join(lines[end + 1 :]).strip()


def normalize_path(raw: str) -> str | None:
    """Normaliza una línea de ``vault-tree.txt`` a ``<bandeja>/<resto>``."""
    match = TRAY_PATH_RE.search(raw.strip())
    if match is None:
        return None
    return f"{match.group(1)}/{match.group(2)}"


def load_tree(root: Path, report: Report) -> set[str]:
    """Lee ``vault-tree.txt`` y devuelve las rutas dentro de las bandejas 01-05."""
    path = root / "vault-tree.txt"
    if not path.is_file():
        report.check("(a)", False, "falta vault-tree.txt")
        return set()
    tree: set[str] = set()
    text = path.read_text(encoding="utf-8", errors="replace")
    for raw in text.splitlines():
        if not raw.strip():
            continue
        normalized = normalize_path(raw)
        if normalized is None:
            report.check("(a)", False, f"ruta fuera de las bandejas 01-05: {raw.strip()}")
            continue
        tree.add(normalized)
    report.check("(a)", bool(tree), f"vault-tree.txt con {len(tree)} ficheros en bandejas")
    return tree


def check_trays(tree: set[str], report: Report) -> None:
    """Comprueba (a): cada artefacto en su bandeja y ninguna bandeja ajena con ficheros."""
    for path in sorted(tree):
        tray, _, rest = path.partition("/")
        allowed = TRAY_ALLOWED.get(tray, ())
        if not any(pattern.match(rest) for pattern in allowed):
            report.check("(a)", False, f"fichero no permitido en {tray}/: {path}")

    for command in COMMANDS:
        for artifact in command.artifacts:
            report.check(
                "(a)",
                artifact in tree,
                f"{command.name}: esperado {artifact} en vault-tree.txt",
            )

    for command in COMMANDS:
        for artifact in command.artifacts:
            name = Path(artifact).name
            for path in sorted(tree - {artifact}):
                if Path(path).name == name:
                    report.check("(a)", False, f"artefacto {name} en bandeja ajena: {path}")


def check_frontmatter(root: Path, report: Report) -> None:
    """(b) Frontmatter con los campos del formato vigente por comando."""
    for command in COMMANDS:
        path = root / f"{command.n:02d}-{command.name}-artifact.md"
        if not path.is_file():
            report.check("(b)", False, f"falta {path.name}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(text)
        if frontmatter is None:
            report.check("(b)", False, f"{path.name}: sin frontmatter")
            continue
        missing = [field for field in command.fields if field not in frontmatter]
        detail = f"; faltan {missing}" if missing else ""
        report.check("(b)", not missing, f"{path.name}: campos vigentes{detail}")
        report.check("(b)", bool(frontmatter_body(text)), f"{path.name}: cuerpo no vacío")

        if command.name != "research" and "command" in frontmatter:
            report.check(
                "(b)",
                frontmatter["command"] == command.name,
                f"{path.name}: command={frontmatter['command']!r} (esperado {command.name!r})",
            )
        if "agent" in frontmatter:
            report.check(
                "(b)",
                frontmatter["agent"] == command.agent,
                f"{path.name}: agent={frontmatter['agent']!r} (esperado {command.agent!r})",
            )
        if command.name == "validate" and "verdict" in frontmatter:
            report.check(
                "(b)",
                frontmatter["verdict"] in VERDICTS,
                f"{path.name}: verdict={frontmatter['verdict']!r} (válidos: {sorted(VERDICTS)})",
            )
        if command.name == "research" and "origin" in frontmatter:
            value = frontmatter["origin"]
            serialized = isinstance(value, list) or (
                isinstance(value, str) and value.startswith("[")
            )
            report.check(
                "(b)",
                serialized,
                f"{path.name}: origin debe serializarse como lista (aunque sea [])",
            )


def check_transcripts(root: Path, report: Report) -> None:
    """(c) Transcript no vacío de los 9 comandos y ficheros de soporte."""
    for command in COMMANDS:
        path = root / f"{command.n:02d}-{command.name}-transcript.txt"
        if not path.is_file():
            report.check("(c)", False, f"falta transcript {path.name}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        ok = bool(text.strip()) and TOOL_MARKER_RE.search(text) is not None
        report.check("(c)", ok, f"{path.name}: transcript no vacío con marcas de tool")

    checklist = root / "checklist.md"
    ok = checklist.is_file() and bool(
        checklist.read_text(encoding="utf-8", errors="replace").strip()
    )
    report.check("(c)", ok, "checklist.md presente y no vacío")


def _first_line(lines: Sequence[str], predicate: Callable[[str], bool]) -> int | None:
    """Índice 0-based de la primera línea que cumple el predicado."""
    return next((i for i, line in enumerate(lines) if predicate(line)), None)


def _is_search(line: str) -> bool:
    """Indica si la línea es una llamada ``search`` de ``tepochcalli-rag``."""
    return "tepochcalli-rag" in line and SEARCH_RE.search(line) is not None


def _is_raw_read(line: str) -> bool:
    """Indica si la línea lee crudo un fichero bajo ``00-resources/``."""
    return "00-resources/" in line and RAW_READ_RE.search(line) is not None


def check_mcp_first(root: Path, report: Report) -> None:
    """(d) ``search`` del índice antes de leer crudo ``00-resources/``."""
    searched = False
    for command in COMMANDS:
        path = root / f"{command.n:02d}-{command.name}-transcript.txt"
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        search = _first_line(lines, _is_search)
        raw = _first_line(lines, _is_raw_read)
        searched = searched or search is not None
        if raw is None:
            report.check("(d)", True, f"{path.name}: sin lectura cruda bajo 00-resources/")
        elif search is None:
            report.check(
                "(d)",
                False,
                f"{path.name}: lectura cruda sin search de tepochcalli-rag: {lines[raw].strip()}",
            )
        elif search < raw:
            report.check(
                "(d)",
                True,
                f"{path.name}: search (línea {search + 1}) antes de leer crudo (línea {raw + 1})",
            )
        else:
            report.check(
                "(d)",
                False,
                f"{path.name}: lectura cruda (línea {raw + 1}) antes del search "
                f"(línea {search + 1}): {lines[raw].strip()}",
            )
    report.check("(d)", searched, "al menos un transcript llama search de tepochcalli-rag")


def main(argv: Sequence[str] | None = None) -> int:
    """Ejecuta las cuatro comprobaciones y devuelve el exit code."""
    parser = argparse.ArgumentParser(description="Verifica la evidencia de la corrida D9.")
    parser.add_argument(
        "evidence_dir",
        nargs="?",
        default=str(DEFAULT_EVIDENCE_DIR),
        help="directorio con transcripts, artefactos, vault-tree.txt y checklist.md",
    )
    args = parser.parse_args(argv)
    root = Path(args.evidence_dir)
    if not root.is_dir():
        print(f"ERROR: no existe el directorio de evidencia: {root}", file=sys.stderr)
        return 2

    report = Report()
    print(f"Evidencia: {root}")
    tree = load_tree(root, report)
    check_trays(tree, report)
    check_frontmatter(root, report)
    check_transcripts(root, report)
    check_mcp_first(root, report)
    print(f"RESUMEN: {report.checks} comprobaciones, {report.failures} fallos")
    return 1 if report.failures else 0


if __name__ == "__main__":
    sys.exit(main())
