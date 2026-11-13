"""Gate D9.3: simulador last-match-wins de la política EFECTIVA del payload.

La política efectiva de un agente es `global ++ inline` (spec-payload-permissions
§Enmienda 2026-11-12): el array `permissions` de
`obsidian-workspace/opencode.json` se concatena delante del bloque `permissions`
del frontmatter del agente y gana la ÚLTIMA regla que casa. Glob: `*` = cero o
más caracteres (incluido `/`), `?` = un carácter; sin coincidencia, `ask`.

La tabla de probes es la política **vigente del payload v1**. Si un bloque o el
global pierde o reordena una regla, este test cae. El intérprete es una copia
independiente: no importa código del payload ni del wizard.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from functools import cache, lru_cache
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
VAULT_ROOT = REPO_ROOT / "obsidian-workspace"
AGENTS_DIR = VAULT_ROOT / ".opencode" / "agents"
GLOBAL_JSON = VAULT_ROOT / "opencode.json"

PRIMARY_AGENTS = ("itzamna", "nezahualcoyotl", "pochteca", "chilam", "tlacuilo")

# Rutas de secretos que el bloque global SÍ deniega (spec-payload-permissions
# §Enmienda 2026-11-12). Si mañana desaparece una regla, el test cae.
SECRET_PATHS = (
    ".env",
    "sub/.env",
    ".env.local",
    "config/.env",
    "secrets.env",
    ".npmrc",
    "id_rsa",
    "server.pem",
    ".ssh/id_rsa",
    ".aws/credentials",
    "service-account-prod.json",
    "credentials.json",
    ".kube/config",
)

# GAP declarado en la Enmienda 2026-11-12: cae en el `read * allow` global.
GAP_READ_PATH = ".tepochcalli/config/tepochcalli.toml"

# Tabla explícita: (agente, acción, recurso, efecto esperado). 9+6+6+15+6 = 42.
PROBES: tuple[tuple[str, str, str, str], ...] = (
    # Pochteca (9): única escritura 01-tasks/research/**; web abierta.
    ("pochteca", "edit", "01-tasks/research/x.md", "allow"),
    ("pochteca", "edit", "02-drafts/x.md", "deny"),
    ("pochteca", "edit", "01-tasks/x.md", "deny"),
    ("pochteca", "edit", "00-resources/x.md", "deny"),
    ("pochteca", "read", "00-resources/x.md", "allow"),
    ("pochteca", "webfetch", "*", "allow"),
    ("pochteca", "websearch", "*", "allow"),
    ("pochteca", "shell", "touch foo", "deny"),
    ("pochteca", "subagent", "nezahualcoyotl", "deny"),
    # Nezahualcóyotl (6): 01-tasks/** salvo 01-tasks/resources/**; sin web.
    ("nezahualcoyotl", "edit", "01-tasks/plan.md", "allow"),
    ("nezahualcoyotl", "edit", "01-tasks/resources/x.md", "deny"),
    ("nezahualcoyotl", "edit", "02-drafts/x.md", "deny"),
    ("nezahualcoyotl", "read", "*", "allow"),
    ("nezahualcoyotl", "webfetch", "*", "deny"),
    ("nezahualcoyotl", "subagent", "*", "deny"),
    # Chilam (6): escribe en todas las bandejas vía `edit * allow`; web abierta.
    ("chilam", "edit", "03-citations/x.md", "allow"),
    ("chilam", "edit", "04-review/x.md", "allow"),
    ("chilam", "edit", "02-drafts/x.md", "allow"),
    ("chilam", "edit", "00-resources/x.md", "allow"),
    ("chilam", "webfetch", "*", "allow"),
    ("chilam", "subagent", "nezahualcoyotl", "deny"),
    # Tlacuilo (15): `edit * allow` sin deny-list en el payload v1.
    ("tlacuilo", "edit", "05-outputs/x.csv", "allow"),
    ("tlacuilo", "edit", "02-drafts/x.md", "allow"),
    ("tlacuilo", "edit", "00-resources/x.md", "allow"),
    ("tlacuilo", "edit", "01-tasks/x.md", "allow"),
    ("tlacuilo", "edit", "03-citations/x.md", "allow"),
    ("tlacuilo", "edit", "04-review/x.md", "allow"),
    ("tlacuilo", "edit", ".git/config", "allow"),
    ("tlacuilo", "edit", "AGENTS.md", "allow"),
    ("tlacuilo", "edit", "opencode.json", "allow"),
    ("tlacuilo", "edit", "tepochcalli.toml", "allow"),
    ("tlacuilo", "edit", ".obsidian/app.json", "allow"),
    ("tlacuilo", "edit", ".opencode/agents/x.md", "allow"),
    ("tlacuilo", "edit", ".tepochcalli/config/x", "allow"),
    ("tlacuilo", "shell", "*", "ask"),
    ("tlacuilo", "subagent", "nezahualcoyotl", "deny"),
    # Itzamná (6): enruta, lee y navega; `edit * ask`.
    ("itzamna", "edit", "02-drafts/x.md", "ask"),
    ("itzamna", "read", "*", "allow"),
    ("itzamna", "webfetch", "*", "allow"),
    ("itzamna", "websearch", "*", "allow"),
    ("itzamna", "shell", "touch foo", "deny"),
    ("itzamna", "subagent", "nezahualcoyotl", "deny"),
)

# `subagent *` efectivo: el global pide `ask`; el bloque inline decide después.
SUBAGENT_BROAD = {
    "itzamna": "allow",
    "nezahualcoyotl": "deny",
    "pochteca": "allow",
    "chilam": "allow",
    "tlacuilo": "allow",
}


def _agent_path(name: str) -> Path:
    """Ruta del `.md` de un agente primario."""
    return AGENTS_DIR / f"{name}.md"


@lru_cache(maxsize=1)
def _global_rules() -> tuple[dict[str, str], ...]:
    """Array `permissions` global de `opencode.json` (313 reglas)."""
    doc = json.loads(GLOBAL_JSON.read_text(encoding="utf-8"))
    assert isinstance(doc, dict), "opencode.json no es un objeto"
    rules = doc["permissions"]
    assert isinstance(rules, list), "`permissions` global no es una lista"
    return tuple(rules)


@cache
def _inline_rules(name: str) -> tuple[dict[str, str], ...]:
    """Lista `permissions` del frontmatter YAML de un agente."""
    text = _agent_path(name).read_text(encoding="utf-8")
    frontmatter = yaml.safe_load(text.split("---", 2)[1])
    assert isinstance(frontmatter, dict), f"{name}: frontmatter no es un mapa"
    rules = frontmatter["permissions"]
    assert isinstance(rules, list), f"{name}: `permissions` no es una lista"
    return tuple(rules)


def _effective_rules(name: str) -> list[dict[str, str]]:
    """Política efectiva: global ++ inline (los bloques se añaden al final)."""
    return [*_global_rules(), *_inline_rules(name)]


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Glob anclado: escapa el literal y traduce `*`→`.*` (cruza `/`) y `?`→`.`."""
    translated = re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".")
    return re.compile(rf"^{translated}$")


def _decide(
    rules: list[dict[str, str]] | tuple[dict[str, str], ...], action: str, resource: str
) -> str:
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


def test_global_block_holds_the_secret_policy() -> None:
    """Hecho medido (Enmienda 2026-11-12): 313 globales y 0 reglas `read` inline."""
    assert len(_global_rules()) == 313
    for agent in PRIMARY_AGENTS:
        assert not [rule for rule in _inline_rules(agent) if rule["action"] == "read"], (
            f"{agent}: el bloque inline ya no declara `read`; la política vive en el global"
        )


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
    """Cada probe de la spec: el efecto efectivo es exactamente el esperado."""
    real = _decide(_effective_rules(agent), action, resource)
    assert real == expected, f"{agent}: {action} {resource} esperado={expected} real={real}"


@pytest.mark.parametrize("agent", PRIMARY_AGENTS)
@pytest.mark.parametrize("path", SECRET_PATHS)
def test_secrets_are_never_readable(agent: str, path: str) -> None:
    """Los 5 agentes siguen denegando los secretos que el bloque global deniega."""
    assert _decide(_effective_rules(agent), "read", path) == "deny", f"{agent} puede leer {path}"


@pytest.mark.parametrize("agent", PRIMARY_AGENTS)
def test_tepochcalli_config_is_a_declared_gap(agent: str) -> None:
    """GAP declarado, no un fallo del test: la config del motor cae en `read * allow`.

    El global no tiene `.tepochcalli/config/**`; el último `read` que casa es
    `* allow` (opencode.json:1506), así que la lectura es `allow`, no `ask`.
    Cerrarlo exige una regla global nueva (cambio de payload, fuera de Phase 6).
    """
    assert _decide(_effective_rules(agent), "read", GAP_READ_PATH) == "allow"


@pytest.mark.parametrize("agent", PRIMARY_AGENTS)
def test_env_example_remains_readable(agent: str) -> None:
    """La excepción `.env.example allow` (opencode.json:1522) sigue siendo la última."""
    assert _decide(_effective_rules(agent), "read", ".env.example") == "allow"


@pytest.mark.parametrize("agent", PRIMARY_AGENTS)
def test_subagent_policy_matches_payload(agent: str) -> None:
    """`subagent *` efectivo por rol y bloqueo de los otros 4 primarios por nombre."""
    rules = _effective_rules(agent)
    assert _decide(rules, "subagent", "any-child-agent") == SUBAGENT_BROAD[agent]
    for child in PRIMARY_AGENTS:
        if child == agent:
            continue
        assert _decide(rules, "subagent", child) == "deny", f"{agent} puede invocar a {child}"


@pytest.mark.parametrize("agent", PRIMARY_AGENTS)
def test_no_rule_is_shadowed(agent: str) -> None:
    """Dentro del bloque inline, cada regla es la última que casa consigo misma."""
    rules = _inline_rules(agent)
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
