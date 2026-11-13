#!/usr/bin/env python3
"""Criterio 1 de `docs/UH.md` — el vault funciona sin interferencias (Phase 6 · T9).

Ejecuta el checklist de `specs/spec-vault-structure.md` §Testing sobre un vault
**instalado por el wizard** (`install --non-interactive --skip-model`) y publica
la evidencia:

(a) `.obsidian/` byte-idéntico antes/después de `index_refresh()` + `search`;
(b) 0 puertos nuevos escuchando (lista `ss -ltnp` antes/después publicada);
(c) 0 entradas con prefijo punto fuera de las carpetas ocultas esperadas;
(d) el vault sigue siendo válido (`opencode.json` parseable, `AGENTS.md`, bandejas).

Sale 1 si algo falla: es una guarda, no un informe decorativo.

Interpretación de (c) — declarada, no implícita: el producto puede dejar
carpetas ocultas **esperadas** en la raíz (`.tepochcalli/` runtime, `.opencode/`
harness, `.obsidian/` del usuario, `.git/`, `.trash/`, y el `.gitignore` del
payload) y el `.gitkeep` con que el payload versiona sus bandejas vacías. Lo que
se persigue es que el motor **no esparza** basura oculta: por eso cualquier otra
entrada punto-prefijada —en la raíz o a cualquier profundidad fuera de esos
subárboles— es violación.

`--fault obsidian|port` inyecta una interrupción a propósito (bytes en
`.obsidian/app.json` o un `socket` a la escucha) **entre** las dos capturas: es
la demostración archivada de que la guarda sabe fallar. Nunca se usa para
aceptar.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAYLOAD_SRC = REPO / "obsidian-workspace"

# Artefactos de runtime/desarrollo que NUNCA viajan en el payload versionado
# (mismas exclusiones que `.github/workflows/release.yml` al empaquetar).
PAYLOAD_SKIP = {
    "venv",
    "db",
    "models",
    "bin",
    "config",
    ".venv",
    ".payload-stage",
    ".install-intent",
    ".coverage",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    ".obsidian",
}

# Carpetas/ficheros ocultos esperados en la raíz del vault (interpretación de (c)).
HIDDEN_ALLOWED_ROOT = {".git", ".gitignore", ".obsidian", ".opencode", ".tepochcalli", ".trash"}
"""Entradas punto-prefijadas esperadas EN LA RAÍZ del vault."""

HIDDEN_ALLOWED_FILES = {".gitkeep"}
"""`.gitkeep` es un placeholder del payload (bandejas vacías versionadas), no basura."""

# Bandejas canónicas (D9.1); `00-Resources/` la crea el wizard (D22), las demás
# viajan en el payload del release.
TRAYS = ["00-Resources", "01-tasks", "02-drafts", "03-citations", "04-review", "05-outputs"]

INDEX_ROOT = "00-resources"
"""Raíz que reporta `index_refresh` por defecto (`INDEXER_DIR`, ADR-010).

Ojo: el wizard crea `00-Resources/` (D22) y el payload trae `00-resources/`
(alias pendiente en `spec-vault-structure` §Open Questions). La medición deja la
nota en la raíz REAL que indexa el motor —lo que se mide es no-interferencia,
no el alias— y el alias se publica como observación, nunca se silencia.
"""

NOTE_NAME = "nota-t9-no-interferencia.md"
NOTE_BODY = (
    "# Nota T9\n\n"
    "Marcador de la medición de no-interferencia: el motor indexa este fichero\n"
    "mientras el checklist comprueba que Obsidian no percibe nada.\n"
)
QUERY = "marcador de la medición de no-interferencia"
OBSIDIAN_FILES = {
    "app.json": '{\n  "alwaysUpdateLinks": true,\n  "newFileLocation": "root"\n}\n',
    "workspace.json": (
        '{\n  "main": {"id": "t9-root", "type": "split"},\n  "active": "t9-root"\n}\n'
    ),
}


def wizard_bin(explicit: str | None) -> Path:
    """Wizard compilado: `--wizard`, `TEPOCHCALLI_BIN` o el target de la casa."""
    candidates = [explicit, os.environ.get("TEPOCHCALLI_BIN")]
    target = os.environ.get("CARGO_TARGET_DIR", "/tmp/opencode/cargo-target")
    candidates += [
        str(Path(target) / "debug" / "tepochcalli"),
        str(REPO / "crates/tepochcalli/target/debug/tepochcalli"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise SystemExit(f"wizard no encontrado; compila con `just rust-build` (probado: {candidates})")


def run(argv: list[str], timeout: int, cwd: Path | None = None) -> dict[str, object]:
    """Subproceso en primer plano y observado: sin shell, con plazo y sin huérfanos."""
    proc = subprocess.run(
        argv,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return {
        "argv": argv,
        "exit": proc.returncode,
        "stdout_tail": proc.stdout.strip().splitlines()[-12:],
        "stderr_tail": proc.stderr.strip().splitlines()[-12:],
    }


def build_payload(dest: Path) -> None:
    """Copia el template COMPLETO del vault (lo que empaqueta el release), sin runtime."""

    def ignore(_dir: str, names: list[str]) -> set[str]:
        return {name for name in names if name in PAYLOAD_SKIP or name.endswith(".pyc")}

    shutil.copytree(PAYLOAD_SRC, dest, ignore=ignore, dirs_exist_ok=True)


def install_vault(work: Path, wizard: Path) -> tuple[Path, dict[str, object]]:
    """Instala un vault nuevo con el wizard; `--skip-model` = salida-5 degradada."""
    build_payload(work / "payload")
    vault = work / "vault"
    step = run(
        [
            str(wizard),
            "install",
            "--non-interactive",
            "--skip-model",
            "--vault",
            str(vault),
            "--payload",
            str(work / "payload"),
        ],
        timeout=1800,
    )
    if step["exit"] != 0:
        raise SystemExit(f"install falló (exit {step['exit']}): {step['stderr_tail']}")
    return vault, step


def enable_embedder(vault: Path, wizard: Path) -> dict[str, object]:
    """Re-entrada documentada por el propio wizard para la ruta 5 (RAG degradado).

    El snapshot del modelo se enlaza desde el cache HF del host: el gate lee del
    `<vault>/.tepochcalli/models` que el propio wizard exige y no descarga nada.
    """
    sys.path.insert(0, str(REPO / "tests"))
    from model_cache import link_model_cache, resolve_model_cache  # noqa: PLC0415

    link_model_cache(vault, resolve_model_cache())
    step = run(
        [
            str(wizard),
            "config",
            "embedder",
            "--non-interactive",
            "--confirm",
            "--vault",
            str(vault),
        ],
        timeout=1800,
    )
    if step["exit"] != 0:
        raise SystemExit(f"config embedder falló (exit {step['exit']}): {step['stderr_tail']}")
    return step


def seed_obsidian(vault: Path) -> None:
    """Simula un vault ya abierto por Obsidian (el wizard no toca `.obsidian/`)."""
    config = vault / ".obsidian"
    config.mkdir(exist_ok=True)
    for name, body in OBSIDIAN_FILES.items():
        (config / name).write_text(body, encoding="utf-8")
    (vault / INDEX_ROOT / NOTE_NAME).write_text(NOTE_BODY, encoding="utf-8")


def tree_hash(root: Path) -> dict[str, object]:
    """Hash de árbol: rutas relativas + bytes (nunca mtime, nunca solo nombres)."""
    digest = hashlib.sha256()
    files: list[str] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        relative = str(path.relative_to(root))
        files.append(relative)
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return {"hash": digest.hexdigest(), "files": files}


def ss_snapshot() -> dict[str, object]:
    """`ss -ltnp` (con la lista cruda); `ss -ltn` si el host no deja `-p`."""
    command = ["ss", "-ltnp"]
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        command = ["ss", "-ltn"]
        proc = subprocess.run(command, capture_output=True, text=True, check=False)
    raw = proc.stdout.strip().splitlines()
    endpoints = set()
    for line in raw[1:]:
        fields = line.split()
        if len(fields) >= 4:
            endpoints.add(fields[3])
    return {"command": " ".join(command), "raw": raw, "endpoints": sorted(endpoints)}


def hidden_violations(vault: Path) -> list[str]:
    """Entradas punto-prefijadas fuera del allowlist declarado (carpetas podadas)."""
    violations: list[str] = []
    for dirpath, dirnames, filenames in os.walk(vault):
        relative = Path(dirpath).relative_to(vault)
        at_root = relative == Path(".")
        for name in sorted(dirnames):
            if not name.startswith("."):
                continue
            if at_root and name in HIDDEN_ALLOWED_ROOT:
                dirnames.remove(name)  # subárbol esperado: no se desciende
            else:
                violations.append(str(relative / name))
        for name in sorted(filenames):
            allowed = (at_root and name in HIDDEN_ALLOWED_ROOT) or name in HIDDEN_ALLOWED_FILES
            if name.startswith(".") and not allowed:
                violations.append(str(relative / name))
    return violations


def validate_vault(vault: Path) -> dict[str, object]:
    """(d) el vault sigue siendo un vault: JSON parseable, AGENTS.md y bandejas."""
    checks: dict[str, object] = {}
    try:
        doc = json.loads((vault / "opencode.json").read_text(encoding="utf-8"))
        checks["opencode_json_parseable"] = True
        servers = doc.get("mcp", {}).get("servers", {})
        checks["tepochcalli_rag_registered"] = "tepochcalli-rag" in servers
    except (OSError, json.JSONDecodeError) as err:
        checks["opencode_json_parseable"] = False
        checks["error"] = str(err)
    checks["agents_md"] = (vault / "AGENTS.md").is_file()
    checks["trays"] = {tray: (vault / tray).is_dir() for tray in TRAYS}
    checks["valid"] = (
        checks.get("opencode_json_parseable") is True
        and checks.get("tepochcalli_rag_registered") is True
        and checks["agents_md"]
        and all(checks["trays"].values())  # type: ignore[union-attr]
    )
    return checks


def server_params(vault: Path) -> tuple[list[str], dict[str, str]]:
    """Spawnea el server EXACTAMENTE como lo hará el harness: `opencode.json`."""
    doc = json.loads((vault / "opencode.json").read_text(encoding="utf-8"))
    entry = doc["mcp"]["servers"]["tepochcalli-rag"]
    program = Path(entry["command"][0])
    argv = [str(program if program.is_absolute() else vault / program), *entry["command"][1:]]
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"COCOINDEX_DB", "PYTHONPATH", "TEPOCHCALLI_TOP_K"}
        and not key.startswith("TEPOCHCALLI_")
    }
    models = str(vault / ".tepochcalli" / "models")
    env.update(entry.get("environment", {}))
    env.update(
        {
            "TEPOCHCALLI_VAULT_ROOT": str(vault),
            "HF_HOME": models,
            "SENTENCE_TRANSFORMERS_HOME": models,
            "HF_HUB_OFFLINE": "1",
        }
    )
    return argv, env


def payload_of(result: object) -> dict[str, object]:
    """Payload del wire: un solo `TextContent` con JSON (nunca texto libre)."""
    content = result.content  # type: ignore[attr-defined]
    if len(content) != 1:
        raise SystemExit(f"wire inesperado: {len(content)} content blocks")
    return json.loads(content[0].text)  # type: ignore[union-attr]


async def drive_vault(vault: Path, query: str) -> dict[str, object]:
    """`index_refresh()` + `search` reales por stdio (sin puerto, hijo observado)."""
    from mcp import ClientSession, StdioServerParameters  # noqa: PLC0415
    from mcp.client.stdio import stdio_client  # noqa: PLC0415

    argv, env = server_params(vault)
    params = StdioServerParameters(command=argv[0], args=argv[1:], env=env, cwd=str(vault))
    async with stdio_client(params, errlog=sys.stderr) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            refresh = payload_of(await session.call_tool("index_refresh", {}))
            search = payload_of(await session.call_tool("search", {"query": query, "top_k": 5}))
    return {"refresh": refresh, "search": search}


def main() -> int:
    """Instala (o reusa) el vault, mide las cuatro caras y decide PASS/FAIL."""
    parser = argparse.ArgumentParser(description="Criterio 1: no-interferencia con Obsidian (T9)")
    parser.add_argument("--vault", help="vault YA instalado (omite el install del wizard)")
    parser.add_argument("--wizard", help="ruta al binario tepochcalli")
    parser.add_argument("--evidence", help="escribe el JSON de evidencia en esta ruta")
    parser.add_argument(
        "--fault",
        choices=["none", "obsidian", "port"],
        default="none",
        help="inyecta un fallo entre capturas (demuestra que la guarda falla)",
    )
    parser.add_argument("--keep", action="store_true", help="no borra el vault temporal")
    args = parser.parse_args()

    wizard = wizard_bin(args.wizard)
    work = (
        Path(args.vault)
        if args.vault
        else Path(
            tempfile.mkdtemp(
                prefix="tepochcalli-t9-", dir=os.environ.get("TEPOCHCALLI_T9_DIR", "/tmp/opencode")
            )
        )
    )
    evidence: dict[str, object] = {
        "criterion": 1,
        "task": "T9",
        "date": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "host": {"uname": os.uname().release, "nproc": os.cpu_count()},
        "command": {
            "install": (
                f"{wizard} install --non-interactive --skip-model "
                "--vault <vault> --payload <payload>"
                if not args.vault
                else None
            ),
            "script": " ".join([Path(__file__).name, *sys.argv[1:]]),
            "fault": args.fault,
        },
        "vault": str(work / "vault") if not args.vault else str(work),
    }
    listener: socket.socket | None = None
    try:
        if args.vault:
            vault = work
        else:
            vault, evidence["install"] = install_vault(work, wizard)
        evidence["embedder"] = enable_embedder(vault, wizard)
        seed_obsidian(vault)

        before = {"obsidian": tree_hash(vault / ".obsidian"), "ports": ss_snapshot()}
        if args.fault == "port":
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)

        tools = asyncio.run(drive_vault(vault, QUERY))

        if args.fault == "obsidian":
            with (vault / ".obsidian" / "app.json").open("a", encoding="utf-8") as handle:
                handle.write("\n")

        after = {"obsidian": tree_hash(vault / ".obsidian"), "ports": ss_snapshot()}
        new_ports = sorted(set(after["ports"]["endpoints"]) - set(before["ports"]["endpoints"]))
        if new_ports:  # confirmación: un puerto real persiste, un ruido del host no
            time.sleep(1.0)
            after["ports"] = ss_snapshot()
            new_ports = sorted(set(after["ports"]["endpoints"]) - set(before["ports"]["endpoints"]))

        hidden = hidden_violations(vault)
        valid = validate_vault(vault)
        roots = list(tools["refresh"].get("roots") or [])
        observations = []
        if (vault / "00-Resources").is_dir() and (vault / INDEX_ROOT).is_dir():
            observations.append(
                "alias de raíz: el wizard crea `00-Resources/` (D22) y el payload trae "
                f"`{INDEX_ROOT}/`; `index_refresh` indexa roots={roots} — la nota medida vive "
                "en la raíz efectiva, no en la del scaffold (Open Question de spec-vault-structure)"
            )
        results = {
            "obsidian_identical": before["obsidian"]["hash"] == after["obsidian"]["hash"],
            "no_new_ports": not new_ports,
            "no_hidden_litter": not hidden,
            "vault_valid": valid["valid"] is True,
            "engine_did_work": int(tools["refresh"].get("indexed", 0)) >= 1
            and len(tools["search"].get("results", [])) >= 1,
        }
        passed = all(results.values())

        evidence.update(
            {
                "obsidian": {"before": before["obsidian"], "after": after["obsidian"]},
                "ports": {
                    "command": before["ports"]["command"],
                    "before": before["ports"],
                    "after": after["ports"],
                    "new": new_ports,
                },
                "hidden": {
                    "allowed_root": sorted(HIDDEN_ALLOWED_ROOT),
                    "allowed_files": sorted(HIDDEN_ALLOWED_FILES),
                    "violations": hidden,
                },
                "vault_valid": valid,
                "observations": observations,
                "tools": {
                    "refresh": tools["refresh"],
                    "search_results": len(tools["search"].get("results", [])),
                    "sources": [
                        hit.get("source_path") for hit in tools["search"].get("results", [])
                    ],
                },
                "results": results,
                "verdict": "PASS" if passed else "FAIL",
            }
        )
        publish(evidence)
        if args.evidence:
            target = Path(args.evidence)
            target = target if target.is_absolute() else REPO / target  # relativa al repo
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        return 0 if passed else 1
    finally:
        if listener is not None:
            listener.close()
        if not args.vault and not args.keep:
            shutil.rmtree(work, ignore_errors=True)


def publish(evidence: dict[str, object]) -> None:
    """Informe humano: las dos listas `ss` completas, hashes y veredicto."""
    obsidian = evidence["obsidian"]
    ports = evidence["ports"]
    print("== Criterio 1 — no-interferencia con Obsidian (T9) ==")
    print(f"vault: {evidence['vault']}")
    print(
        f"(a) .obsidian/ hash={obsidian['after']['hash'][:16]}… "
        f"identical={obsidian['before']['hash'] == obsidian['after']['hash']} "
        f"files={obsidian['after']['files']}"
    )
    for stage in ("before", "after"):
        print(f"(b) {ports['command']} {stage} ({len(ports[stage]['raw']) - 1} listeners):")
        for line in ports[stage]["raw"]:
            print(f"    {line}")
    print(f"(b) puertos nuevos: {ports['new'] or 'ninguno'}")
    print(
        f"(c) ocultas permitidas: raíz={evidence['hidden']['allowed_root']} "
        f"ficheros={evidence['hidden']['allowed_files']}"
    )
    print(f"(c) violaciones: {evidence['hidden']['violations'] or 'ninguna'}")
    print(f"(d) vault válido: {json.dumps(evidence['vault_valid'], ensure_ascii=False)}")
    print(f"motor: index_refresh={json.dumps(evidence['tools']['refresh'], ensure_ascii=False)}")
    print(
        f"motor: search results={evidence['tools']['search_results']} "
        f"sources={evidence['tools']['sources']}"
    )
    for observation in evidence["observations"]:
        print(f"observación: {observation}")
    print(f"resultados: {json.dumps(evidence['results'])}")
    print(f"VERDICT: {evidence['verdict']}")


if __name__ == "__main__":
    raise SystemExit(main())
