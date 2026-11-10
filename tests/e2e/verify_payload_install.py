#!/usr/bin/env python3
"""Phase 5 T12 gate: assert an installed Tepochcalli vault against the blueprint.

Standalone (not a pytest module, so `just python-test` never collects it):

    python3 tests/e2e/verify_payload_install.py <vault>
    python3 tests/e2e/verify_payload_install.py <vault> --install --idempotency

Without `--install` it only asserts an already-installed vault. With `--install`
it packages `obsidian-workspace/` exactly like the release asset
(`.github/workflows/release.yml`), extracts it and runs the real wizard
(`install --non-interactive --skip-model`) into `<vault>`. `--idempotency`
adds a second install and proves the payload tree is byte-identical with no
new files and no `*.bak` leftover. Exit code is non-zero on the first failed
assertion group, with a clear `FAIL: ...` line per missing contract item.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAYLOAD_SRC = REPO / "obsidian-workspace"
CARGO_MANIFEST = REPO / "crates" / "tepochcalli" / "Cargo.toml"

# Mirror of `.github/workflows/release.yml` (payload asset exclusions).
TAR_EXCLUDES = [
    "./.obsidian",
    "./.tepochcalli/venv",
    "./.tepochcalli/db",
    "./.tepochcalli/models",
    "./.tepochcalli/bin",
    "./.tepochcalli/config",
    "./.tepochcalli/.venv",
    "./.tepochcalli/.uv-stage",
    "./.tepochcalli/.payload-stage",
    "./.tepochcalli/.install-intent",
    "./.tepochcalli/.coverage",
    "./.tepochcalli/.mypy_cache",
    "./.tepochcalli/.pytest_cache",
    "./.tepochcalli/.ruff_cache",
    "__pycache__",
    "*.pyc",
    "target",
]

# The 5 primary workspace agents: name -> (permission rules, mode).
EXPECTED_AGENTS = {
    "itzamna": (16, "primary"),
    "nezahualcoyotl": (18, "primary"),
    "pochteca": (17, "primary"),
    "chilam": (18, "primary"),
    "tlacuilo": (27, "primary"),
}

# The 9 commands: name -> exact body line count (`wc -l`).
EXPECTED_COMMANDS = {
    "rubric": 24,
    "research": 30,
    "validate": 26,
    "synthesize": 24,
    "cite": 24,
    "draft": 24,
    "review": 24,
    "transform": 25,
    "update": 24,
}

EXPECTED_TOP_NAMES = {
    "00-Resources",
    "01-tasks",
    "02-drafts",
    "03-citations",
    "04-review",
    "05-outputs",
    ".opencode",
    "AGENTS.md",
    "opencode.json",
    ".gitignore",
}

EXPECTED_GITIGNORE = {
    ".tepochcalli/venv/",
    ".tepochcalli/bin/",
    ".tepochcalli/db/",
    ".tepochcalli/models/",
    ".tepochcalli/config/",
}

RAG_COMMAND = [".tepochcalli/venv/bin/python", "-m", "tepochcalli_mcp"]

failures: list[str] = []


def check(ok: bool, message: str) -> None:
    """Record a contract failure without aborting the remaining checks."""
    if not ok:
        failures.append(message)


def frontmatter(path: Path) -> str:
    """Return the YAML frontmatter block of a markdown file."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    return text[: end if end != -1 else len(text)]


def permission_rules(front: str) -> int:
    """Count the `- action:` entries in an agent's permissions block."""
    return sum(1 for line in front.splitlines() if line.startswith("  - action:"))


def first_field(front: str, key: str) -> str | None:
    """Return the value of a top-level frontmatter field, if present."""
    prefix = f"{key}:"
    for line in front.splitlines():
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    return None


def payload_files(vault: Path) -> list[Path]:
    """List the payload-tree files covered by the idempotency digest."""
    roots = [
        vault / ".opencode" / "agents",
        vault / ".opencode" / "commands",
        vault / ".opencode" / "skills",
        *[
            vault / name
            for name in ("01-tasks", "02-drafts", "03-citations", "04-review", "05-outputs")
        ],
    ]
    files = [
        vault / "AGENTS.md",
        vault / "opencode.json",
        vault / ".gitignore",
    ]
    for root in roots:
        files.extend(p for p in root.rglob("*") if p.is_file())
    return [p for p in files if not p.name.endswith(".bak")]


def tree_digest(vault: Path) -> tuple[str, int]:
    """Hash of the payload tree (runtime `.tepochcalli/` and `*.bak` excluded)."""
    digest = hashlib.sha256()
    files = sorted(payload_files(vault), key=lambda p: p.relative_to(vault).as_posix())
    for path in files:
        rel = path.relative_to(vault).as_posix()
        digest.update(rel.encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest(), len(files)


def assert_vault(vault: Path) -> None:
    """Assert every Phase 5 contract item against an installed vault."""
    print(f"asserting vault: {vault}")

    # 1. Canonical tree with exact capitalization (top-level listing, so a
    #    case-insensitive filesystem cannot accept `00-resources/`).
    check(vault.is_dir(), f"vault directory missing: {vault}")
    if not vault.is_dir():
        return
    top = set(os.listdir(vault))
    missing_top = EXPECTED_TOP_NAMES - top
    check(not missing_top, f"missing/wrong-case top-level entries: {sorted(missing_top)}")
    required_dirs = [
        "00-Resources",
        "01-tasks/research",
        "02-drafts",
        "03-citations",
        "04-review",
        "05-outputs",
        ".opencode/agents",
        ".opencode/commands",
        ".opencode/skills",
    ]
    for rel in required_dirs:
        check((vault / rel).is_dir(), f"missing directory: {rel}/")

    # 2. The 5 primary agents: permissions block + mode.
    for name, (rules, mode) in EXPECTED_AGENTS.items():
        path = vault / ".opencode" / "agents" / f"{name}.md"
        if not path.is_file():
            check(False, f"missing agent: .opencode/agents/{name}.md")
            continue
        front = frontmatter(path)
        got_rules = permission_rules(front)
        got_mode = first_field(front, "mode")
        check(
            got_rules == rules,
            f"agent {name}: {got_rules} permission rules (expected {rules})",
        )
        check(got_mode == mode, f"agent {name}: mode={got_mode!r} (expected {mode!r})")

    # 3. The 9 commands with their body length.
    for name, expected_lines in EXPECTED_COMMANDS.items():
        path = vault / ".opencode" / "commands" / f"{name}.md"
        if not path.is_file():
            check(False, f"missing command: .opencode/commands/{name}.md")
            continue
        got_lines = len(path.read_text(encoding="utf-8").splitlines())
        check(
            got_lines == expected_lines,
            f"command {name}: {got_lines} lines (expected {expected_lines})",
        )

    # 4. AGENTS.md with its 7 sections.
    agents_md = vault / "AGENTS.md"
    if agents_md.is_file():
        sections = [
            line
            for line in agents_md.read_text(encoding="utf-8").splitlines()
            if line.startswith("## ")
        ]
        check(len(sections) == 7, f"AGENTS.md: {len(sections)} sections (expected 7)")
    else:
        check(False, "missing AGENTS.md")

    # 5. Installed opencode.json: no global permissions, default agent, F8 merge.
    config_path = vault / "opencode.json"
    if not config_path.is_file():
        check(False, "missing opencode.json")
    else:
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            check(False, f"opencode.json is not valid JSON: {exc}")
            config = {}
        check("permissions" not in config, "opencode.json has a global `permissions` key")
        check(
            config.get("default_agent") == "itzamna",
            f"default_agent={config.get('default_agent')!r} (expected 'itzamna')",
        )
        servers = config.get("mcp", {}).get("servers", {})
        check(
            "markitdown" not in servers,
            "opencode.json still registers the stale `markitdown` server",
        )
        entry = servers.get("tepochcalli-rag")
        if not isinstance(entry, dict):
            check(False, "opencode.json missing mcp.servers['tepochcalli-rag']")
        else:
            check(entry.get("type") == "local", f"tepochcalli-rag type={entry.get('type')!r}")
            check(
                entry.get("command") == RAG_COMMAND,
                f"tepochcalli-rag command={entry.get('command')!r} (expected {RAG_COMMAND})",
            )
            check(entry.get("cwd") == ".", f"tepochcalli-rag cwd={entry.get('cwd')!r}")
            env = entry.get("environment")
            check(
                isinstance(env, dict) and env.get("TEPOCHCALLI_ROOT") == ".",
                f"tepochcalli-rag environment TEPOCHCALLI_ROOT={env!r} (expected '.')",
            )
            check(
                entry.get("disabled") is False,
                f"tepochcalli-rag disabled={entry.get('disabled')!r}",
            )

    # 6. The 2 wizard samples in 00-Resources/.
    md = vault / "00-Resources" / "ejemplo.md"
    pdf = vault / "00-Resources" / "ejemplo.pdf"
    check(md.is_file() and md.stat().st_size > 0, "missing/empty 00-Resources/ejemplo.md")
    check(pdf.is_file() and pdf.stat().st_size > 0, "missing/empty 00-Resources/ejemplo.pdf")
    if pdf.is_file():
        check(pdf.read_bytes()[:5] == b"%PDF-", "00-Resources/ejemplo.pdf is not a PDF")

    # 7. .gitignore with the 5 runtime routes.
    gitignore = vault / ".gitignore"
    if not gitignore.is_file():
        check(False, "missing .gitignore")
    else:
        lines = {
            line.strip()
            for line in gitignore.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        missing = EXPECTED_GITIGNORE - lines
        check(not missing, f".gitignore missing routes: {sorted(missing)}")


def package_payload(work: Path) -> Path:
    """Package `obsidian-workspace/` exactly like the release asset and extract it."""
    archive = work / "payload.tar.gz"
    payload = work / "payload"
    for stale in (archive, payload):
        if stale.is_dir():
            shutil.rmtree(stale)
        elif stale.exists():
            stale.unlink()
    payload.mkdir(parents=True)
    cmd = [
        "tar",
        "-czf",
        str(archive),
        "-C",
        str(PAYLOAD_SRC),
        *[f"--exclude={pattern}" for pattern in TAR_EXCLUDES],
        "--sort=name",
        "--mtime=UTC 2020-01-01",
        "--owner=0",
        "--group=0",
        "--numeric-owner",
        ".",
    ]
    subprocess.run(cmd, check=True)
    subprocess.run(["tar", "-xzf", str(archive), "-C", str(payload)], check=True)
    print(f"payload packaged: {archive} ({archive.stat().st_size} bytes)")
    return payload


def run_install(
    vault: Path, payload: Path, cargo_target_dir: str | None
) -> subprocess.CompletedProcess[bytes]:
    """Run the real wizard (`install --non-interactive --skip-model`) and return the result."""
    env = dict(os.environ)
    if cargo_target_dir:
        env["CARGO_TARGET_DIR"] = cargo_target_dir
    cmd = [
        "cargo",
        "run",
        "--locked",
        "--manifest-path",
        str(CARGO_MANIFEST),
        "--",
        "install",
        "--non-interactive",
        "--skip-model",
        "--vault",
        str(vault),
        "--payload",
        str(payload),
    ]
    return subprocess.run(cmd, check=False, env=env)


def main() -> int:
    """Parse args, optionally install, assert, and return the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("vault", type=Path, help="installed vault directory to assert")
    parser.add_argument(
        "--install",
        action="store_true",
        help="package the payload and run the real wizard into <vault> first",
    )
    parser.add_argument(
        "--idempotency",
        action="store_true",
        help="run install a second time and prove the payload tree is unchanged (needs --install)",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=Path("/tmp/opencode/phase5-e2e")
        if Path("/tmp/opencode").is_dir()
        else Path(os.environ.get("TMPDIR", "/tmp")) / "tepochcalli-phase5-e2e",
        help="scratch dir for the packaged payload",
    )
    parser.add_argument(
        "--cargo-target-dir",
        default=os.environ.get("CARGO_TARGET_DIR")
        or (
            str(Path("/tmp/opencode/tepochcalli-target"))
            if Path("/tmp/opencode/tepochcalli-target").is_dir()
            else None
        ),
        help="CARGO_TARGET_DIR for the wizard build (fuseblk exec-bit workaround)",
    )
    args = parser.parse_args()

    if args.idempotency and not args.install:
        parser.error("--idempotency requires --install (there is no second run to make)")

    vault = args.vault.resolve()
    if args.install:
        args.work_dir.mkdir(parents=True, exist_ok=True)
        payload = package_payload(args.work_dir)
        first = run_install(vault, payload, args.cargo_target_dir)
        check(first.returncode == 0, f"install exited {first.returncode}")

    assert_vault(vault)

    if args.idempotency:
        before_digest, before_count = tree_digest(vault)
        second = run_install(vault, args.work_dir / "payload", args.cargo_target_dir)
        after_digest, after_count = tree_digest(vault)
        print(f"idempotency digest before: {before_digest} ({before_count} files)")
        print(f"idempotency digest after:  {after_digest} ({after_count} files)")
        check(
            second.returncode == 0,
            f"second install exited {second.returncode}; a full re-run is not a no-op "
            "(spec-installer-wizard §Idempotencia)",
        )
        check(before_digest == after_digest, "second install changed the payload tree")
        check(
            before_count == after_count,
            f"second install changed file count {before_count} -> {after_count}",
        )
        leftovers = list(vault.rglob("*.bak"))
        check(not leftovers, f"leftover backups: {[p.name for p in leftovers]}")

    if failures:
        for message in failures:
            print(f"FAIL: {message}", file=sys.stderr)
        print(f"\n{len(failures)} assertion(s) failed", file=sys.stderr)
        return 1
    print("OK: vault matches the Phase 5 payload contract")
    return 0


if __name__ == "__main__":
    sys.exit(main())
