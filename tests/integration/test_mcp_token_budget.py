"""T6: criterio 4 de BACKLOG.md — la consulta COMPLETA < 2000 tokens, con tokenizador real.

Fuentes de verdad:

* docs/BACKLOG.md §1 / C4: «el consumo de tokens por
  consulta es inferior a 2000 tokens (incluyendo contexto)».
* specs/spec-mcp-server.md §Presupuesto de tokens — el techo **1600** del
  payload es sobre el ESTIMADOR (`chars/4 + 25`), no sobre un tokenizador
  real; ese invariante lo gradúa `test_mcp_budget_adversarial.py`.
* tasks/plan.md §Task T6 + docs/TRD.md §6.1 fila 4 — la cifra que falta es la
  del TOTAL e2e (query + payload + respuesta con citas) medida de verdad.

Qué mide este módulo y por qué así:

* **Tokenizador de REFERENCIA `o200k_base` de `tiktoken`** (versión en el
  JSON de evidencia). El harness del payload corre modelos servidos por el
  gateway OpenCode Zen (`opencode/big-pickle`, `minimax-m3.1-flash-free`,
  `glm-5.3-flash-free`…), cuyos tokenizadores no están en el repo ni se
  distribuyen con nombre estable: se usa el de referencia DOCUMENTADO y se
  declara (AC de T6). `o200k_base` es el encoding de la familia gpt-4o/gpt-5
  (tiktoken `MODEL_TO_ENCODING`, https://github.com/openai/tiktoken) y es el
  BPE moderno más exigente en material ES/CJK entre los públicos; `cl100k`
  va publicado al lado en la evidencia para que la elección sea auditable.
* **El payload es el del WIRE**: se serializa con `json_result` — el mismo
  empaquetador del server que produce `content[0].text` — y NO se recuenta el
  dict a mano.
* **La respuesta es el ESQUELETO MÍNIMO que el payload exige**: una
  afirmación por resultado devuelto, anclada en el formato prescrito por los
  prompts (`source_path » heading (chars x–y)`, specs/spec-payload-agents.md
  y specs/spec-payload-commands.md). Es una COTA INFERIOR de la respuesta
  (la prosa adicional del agente no se cuenta aquí): el margen que queda
  hasta 2000 se publica en tokens y lo convierte en frases extra
  `test_the_guard_is_not_vacuous…`.
* **Fixture adverso COMPARTIDO**, no duplicado: `adversarial_vault` es el
  fixture de SESIÓN del conftest de `integration/` (unicode, CJK, emoji,
  tablas, listas largas) y `_backend_on` viene de T7. El índice se construye
  en subproceso UNA vez por sesión y lo consumen T7 y este módulo (P0-1:
  antes cada módulo indexaba el mismo vault — dos pasadas de ~50 s; misma
  premisa que T7, el environment global de cocoindex no admite dos vaults en
  el proceso padre, por eso TODO indexado corre en subproceso).
* **Nada de latencia** (regla anti-flake T3): aquí solo se cuentan tokens.

Hallazgo que este módulo deja por escrito (medido, no estimado):
`F-T6-1` — ver docs/acceptance/token-budget.md.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from support.token_budget import (
    QUERY_TOKEN_CEILING,
    TOKENIZER_ENCODING,
    TOKENIZER_VERSION,
    TokenBudget,
    measure,
)
from tepochcalli_mcp.server import _VaultSearchBackend
from test_mcp_budget_adversarial import (
    CJK_QUERY,
    DENSE_QUERY,
    EMOJI_LATIN_QUERY,
    GOLDEN_QUERY,
    PDF_QUERY,
)
from test_mcp_search import IndexedVault, _backend_on, _search


@pytest.fixture(scope="module")
def backend(adversarial_vault: IndexedVault) -> Iterator[_VaultSearchBackend]:
    """Backend real sobre el vault adverso COMPARTIDO de sesión — su `_backend_on` de T7.

    El índice lo construye UNA vez por sesión el fixture `adversarial_vault`
    del conftest de este directorio (P0-1): antes este módulo re-indexaba el
    mismo vault adverso que T7 (~50 s duplicados).
    """
    yield from _backend_on(adversarial_vault)


EVIDENCE_ENV = "TEPOCHCALLI_TOKEN_EVIDENCE"
"""Ruta del JSON de evidencia; ausente ⇒ el test solo guarda (no escribe nada)."""

CASES = [
    ("dorada_corta", GOLDEN_QUERY, 5, None),
    ("cjk_emoji", CJK_QUERY, 5, None),
    ("emoji_latin", EMOJI_LATIN_QUERY, 5, None),
    ("denso_corte", DENSE_QUERY, 5, "00-resources/denso.md"),
    ("pdf_tablas", PDF_QUERY, 5, "00-resources/tablas.pdf"),
    ("top_k_maximo", "métricas de cobertura", 20, None),
    ("error_query", "x" * 10_001, 5, None),
]
"""Las caras del fixture adverso: `top_k=5` (AC), `top_k=20` (peor caso útil) y la query
patológica (10 001 chars ⇒ `VALIDATION_ERROR`) — su texto TAMBIÉN se cuenta: una consulta
rechazada por el tool no es una consulta gratis, es una consulta que el agente ya escribió."""


def _write_evidence(budgets: list[TokenBudget], probe: TokenBudget) -> None:
    """Vuelca el desglose medido al JSON de evidencia si el env lo pide (AC de T6)."""
    target = os.environ.get(EVIDENCE_ENV)
    if not target:
        return
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "command": f'{EVIDENCE_ENV}="{path}" just python-test-file token_budget',
                "ceiling": QUERY_TOKEN_CEILING,
                "tokenizer": TOKENIZER_ENCODING,
                "tiktoken_version": TOKENIZER_VERSION,
                "cases": [budget.as_dict() for budget in budgets],
                "sensitivity_probe": probe.as_dict(),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_every_adversarial_consultation_stays_under_2000_tokens(backend: object) -> None:
    """AC criterio 4: query + payload del server + respuesta citada < 2000 en TODAS las caras.

    Guarda VIVA (no un número en un documento): si el techo del server, el
    chunker o el formato de cita engordan la consulta por encima de 2000, este
    test se pone rojo con la tabla de desglose en el mensaje.

    Y no es vacía: la MISMA medición con 2 frases por resultado (una más que el
    esqueleto mínimo) pasa de la cota ⇒ el margen sobrante es exactamente la
    prosa extra que el agente puede añadir.
    """
    budgets = [
        measure(case, query, _search(backend, query, top_k, path_filter=path_filter))
        for case, query, top_k, path_filter in CASES
    ]
    probe = measure(
        "sensibilidad_2_frases",
        DENSE_QUERY,
        _search(backend, DENSE_QUERY, 5, path_filter="00-resources/denso.md"),
        claims_per_result=2,
    )
    _write_evidence(list(budgets), probe)
    table = "\n".join(budget.line() for budget in budgets)
    worst = max(budgets, key=lambda budget: budget.total_tokens)

    assert worst.total_tokens < QUERY_TOKEN_CEILING, (
        f"{worst.case}: total {worst.total_tokens} ≥ {QUERY_TOKEN_CEILING} tokens "
        f"({TOKENIZER_ENCODING} {TOKENIZER_VERSION})\n{table}"
    )
    assert probe.total_tokens > QUERY_TOKEN_CEILING, (
        f"guard vacío: 2 frases/resultado cuestan {probe.total_tokens} ≤ {QUERY_TOKEN_CEILING}"
        f"\n{probe.line()}\n{table}"
    )


def test_error_payloads_are_counted_never_skipped(backend: object) -> None:
    """Un payload de ERROR también es una consulta: se cuenta y se guarda igual.

    Elegir qué se cuenta es donde se maquilla un presupuesto. Aquí el error
    (`VALIDATION_ERROR` de query >10 000 chars) entra con `results=0`, su
    `error` declarado y **su query contada**: un texto que el agente ya
    escribió no es gratis porque el tool lo rechace.
    """
    budget = measure("error_query", "x" * 10_001, _search(backend, "x" * 10_001))

    assert budget.error == "VALIDATION_ERROR", budget.line()
    assert budget.results == 0
    assert budget.payload_tokens > 0 and budget.query_tokens > 0, budget.line()
    assert budget.total_tokens < QUERY_TOKEN_CEILING, budget.line()


def test_published_payload_figure_is_the_wire_text_of_the_real_handler(backend: object) -> None:
    """La cifra (a) publicada es el `content[0].text` real, no una reconstrucción.

    El desglose separa payload (wire) de query y de respuesta para que cada
    número de docs/acceptance/token-budget.md tenga su origen en el código.
    """
    payload = _search(backend, GOLDEN_QUERY, 5)
    budget = measure("dorada_corta", GOLDEN_QUERY, payload)

    assert budget.payload_tokens > 0 and budget.query_tokens > 0 and budget.answer_tokens > 0
    assert budget.total_tokens == budget.query_tokens + budget.payload_tokens + budget.answer_tokens
    assert budget.results == len(payload["results"])  # type: ignore[arg-type]
