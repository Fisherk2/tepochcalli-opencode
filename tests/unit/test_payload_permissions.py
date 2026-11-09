"""Gate D9.3: simulador last-match-wins de los permisos del payload (T11).

Reimplementa el intérprete de `spec-payload-vault` §Semántica de `permissions`
sobre los 5 bloques reales de `obsidian-workspace/.opencode/agents/`: las reglas
se evalúan en orden, gana la ÚLTIMA que casa, `*` es cero o más caracteres
(incluido `/`), `?` exactamente un carácter y, sin coincidencia, el efecto es
`ask`. Los 42 probes de `spec-payload-permissions` §Verificación deben dar
esperado == real.

El intérprete es deliberadamente una copia independiente del payload: si el
bloque cambia de orden o pierde una regla, este test lo detecta.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "obsidian-workspace" / ".opencode" / "agents"

PRIMARY_AGENTS = ("itzamna", "nezahualcoyotl", "pochteca", "chilam", "tlacuilo")

# Rutas de secretos que ningún agente debe leer (spec-payload-permissions §Verificación).
SECRET_PATHS = (
    ".env",
    "sub/.env",
    ".env.local",
    "config/.env",
    "secrets.env",
    ".tepochcalli/config/tepochcalli.toml",
)

# Tabla explícita: (agente, acción, recurso, efecto esperado). 9+6+6+15+6 = 42.
PROBES: tuple[tuple[str, str, str, str], ...] = (
    # Pochteca (9): única escritura 01-tasks/research/**; web abierta.
    ("pochteca", "edit", "01-tasks/research/x.md", "allow"),
    ("pochteca", "edit", "02-drafts/x.md", "deny"),
    ("pochteca", "edit", "01-tasks/x.md", "deny"),
    ("pochteca", "edit", "00-Resources/x.md", "deny"),
    ("pochteca", "read", "00-Resources/x.md", "allow"),
    ("pochteca", "webfetch", "*", "allow"),
    ("pochteca", "websearch", "*", "allow"),
    ("pochteca", "shell", "*", "deny"),
    ("pochteca", "subagent", "*", "deny"),
    # Nezahualcóyotl (6): 01-tasks/** salvo research/**; sin web.
    ("nezahualcoyotl", "edit", "01-tasks/research/x.md", "deny"),
    ("nezahualcoyotl", "edit", "01-tasks/plan.md", "allow"),
    ("nezahualcoyotl", "edit", "02-drafts/x.md", "deny"),
    ("nezahualcoyotl", "read", "*", "allow"),
    ("nezahualcoyotl", "webfetch", "*", "deny"),
    ("nezahualcoyotl", "subagent", "*", "deny"),
    # Chilam (6): 03-citations/** y 04-review/**; sin web.
    ("chilam", "edit", "03-citations/x.md", "allow"),
    ("chilam", "edit", "04-review/x.md", "allow"),
    ("chilam", "edit", "02-drafts/x.md", "deny"),
    ("chilam", "edit", "00-Resources/x.md", "deny"),
    ("chilam", "webfetch", "*", "deny"),
    ("chilam", "subagent", "*", "deny"),
    # Tlacuilo (15): denylist completa detrás de `edit * allow`.
    ("tlacuilo", "edit", "05-outputs/x.csv", "allow"),
    ("tlacuilo", "edit", "02-drafts/x.md", "allow"),
    ("tlacuilo", "edit", "00-Resources/x.md", "deny"),
    ("tlacuilo", "edit", "01-tasks/x.md", "deny"),
    ("tlacuilo", "edit", "03-citations/x.md", "deny"),
    ("tlacuilo", "edit", "04-review/x.md", "deny"),
    ("tlacuilo", "edit", ".git/config", "deny"),
    ("tlacuilo", "edit", "AGENTS.md", "deny"),
    ("tlacuilo", "edit", "opencode.json", "deny"),
    ("tlacuilo", "edit", "tepochcalli.toml", "deny"),
    ("tlacuilo", "edit", ".obsidian/app.json", "deny"),
    ("tlacuilo", "edit", ".opencode/agents/x.md", "deny"),
    ("tlacuilo", "edit", ".tepochcalli/config/x", "deny"),
    ("tlacuilo", "shell", "*", "deny"),
    ("tlacuilo", "subagent", "*", "deny"),
    # Itzamná (6): enruta y lee; sin edit ni web ni shell.
    ("itzamna", "edit", "02-drafts/x.md", "deny"),
    ("itzamna", "read", "*", "allow"),
    ("itzamna", "webfetch", "*", "deny"),
    ("itzamna", "websearch", "*", "deny"),
    ("itzamna", "shell", "*", "deny"),
    ("itzamna", "subagent", "*", "deny"),
)


def _agent_path(name: str) -> Path:
    """Ruta del `.md` de un agente primario."""
    return AGENTS_DIR / f"{name}.md"


def _rules(name: str) -> list[dict[str, str]]:
    """Lista `permissions` del frontmatter YAML de un agente."""
    text = _agent_path(name).read_text(encoding="utf-8")
    frontmatter = yaml.safe_load(text.split("---", 2)[1])
    assert isinstance(frontmatter, dict), f"{name}: frontmatter no es un mapa"
    rules = frontmatter["permissions"]
    assert isinstance(rules, list), f"{name}: `permissions` no es una lista"
    return rules


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Glob anclado: escapa el literal y traduce `*`→`.*` (cruza `/`) y `?`→`.`."""
    translated = re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".")
    return re.compile(rf"^{translated}$")


def _decide(rules: list[dict[str, str]], action: str, resource: str) -> str:
    """Efecto de la última regla que casa; `ask` si ninguna casa."""
    effect = "ask"
    for rule in rules:
        if rule["action"] != action:
            continue
        if _glob_to_regex(rule["resource"]).match(resource):
            effect = rule["effect"]
    return effect


def _candidate(rule: dict[str, str]) -> str:
    """Recurso fabricado que debería casar con la regla (detector de reglas muertas)."""
    return rule["resource"].replace("**", "probe").replace("*", "probe")


def test_probe_table_has_the_42_cases_of_the_spec() -> None:
    """La tabla cubre los 42 probes con la distribución 9/6/6/15/6 de la spec."""
    assert len(PROBES) == 42
    assert Counter(probe[0] for probe in PROBES) == {
        "pochteca": 9,
        "nezahualcoyotl": 6,
        "chilam": 6,
        "tlacuilo": 15,
        "itzamna": 6,
    }


@pytest.mark.parametrize(("agent", "action", "resource", "expected"), PROBES)
def test_probe_matches_the_spec(agent: str, action: str, resource: str, expected: str) -> None:
    """Cada probe de la spec: el efecto simulado es exactamente el esperado."""
    real = _decide(_rules(agent), action, resource)
    assert real == expected, f"{agent}: {action} {resource} esperado={expected} real={real}"


@pytest.mark.parametrize("agent", PRIMARY_AGENTS)
@pytest.mark.parametrize("path", SECRET_PATHS)
def test_secrets_are_never_readable(agent: str, path: str) -> None:
    """Los 5 agentes deniegan la lectura de `.env*` y de la config del motor."""
    assert _decide(_rules(agent), "read", path) == "deny", f"{agent} puede leer {path}"


@pytest.mark.parametrize("agent", PRIMARY_AGENTS)
def test_subagent_is_declared_denied_and_effective(agent: str) -> None:
    """`subagent * deny` está presente y ningún id de hijo se cuela."""
    rules = _rules(agent)
    assert any(
        rule["action"] == "subagent" and rule["resource"] == "*" and rule["effect"] == "deny"
        for rule in rules
    ), f"{agent}: falta `subagent * deny`"
    assert _decide(rules, "subagent", "any-child-agent") == "deny"


@pytest.mark.parametrize("agent", PRIMARY_AGENTS)
def test_no_rule_is_shadowed(agent: str) -> None:
    """Cada regla es la última que casa consigo misma: 0 reglas muertas."""
    rules = _rules(agent)
    for rule in rules:
        candidate = _candidate(rule)
        assert _decide(rules, rule["action"], candidate) == rule["effect"], (
            f"{agent}: regla sombreada por otra posterior: {rule}"
        )


def test_star_crosses_slash_and_last_match_wins() -> None:
    """`*` cruza `/`: el allow final gana sobre el deny amplio anterior."""
    rules = [
        {"action": "edit", "resource": "*", "effect": "deny"},
        {"action": "edit", "resource": "05-outputs/**", "effect": "allow"},
    ]
    assert _decide(rules, "edit", "05-outputs/a/b.csv") == "allow"


def test_star_matches_nested_paths() -> None:
    """Un `*` inicial casa rutas con varios niveles (`sub/.env` cuenta para `*.env`)."""
    rules = [{"action": "read", "resource": "*.env", "effect": "deny"}]
    assert _decide(rules, "read", "deep/sub/.env") == "deny"


def test_question_mark_matches_exactly_one_character() -> None:
    """`?` casa exactamente un carácter, ni cero ni dos."""
    rules = [{"action": "edit", "resource": "notes/?.md", "effect": "allow"}]
    assert _decide(rules, "edit", "notes/a.md") == "allow"
    assert _decide(rules, "edit", "notes/ab.md") == "ask"


def test_no_matching_rule_defaults_to_ask() -> None:
    """Sin regla que case (acción o recurso), el efecto por defecto es `ask`."""
    rules = [{"action": "edit", "resource": "01-tasks/**", "effect": "allow"}]
    assert _decide(rules, "read", "whatever") == "ask"
    assert _decide(rules, "edit", "02-drafts/x.md") == "ask"
