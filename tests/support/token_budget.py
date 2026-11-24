"""Contabilidad de tokens de UNA consulta e2e con tokenizador REAL (T6, criterio 4).

Fuente de verdad: docs/BACKLOG.md §1 / C4 — «el consumo de tokens
por consulta es inferior a 2000 tokens (incluyendo contexto)».

Qué cuenta una consulta (y qué no)
----------------------------------
`total = query + payload + respuesta`. Cada pieza se mide por separado para
que la cifra publicada tenga desglose y origen:

* **query** — el texto que el usuario escribe, tal cual viaja al modelo.
* **payload** — `content[0].text` del server: se serializa con
  `tepochcalli_mcp.tools.json_result`, el MISMO empaquetador de producción
  (`ensure_ascii=False`, orden de claves del contrato). No se reconstruye a
  mano: si el wire cambia, cambia la cifra.
* **respuesta** — el ESQUELETO MÍNIMO que el payload exige: una afirmación
  por resultado devuelto, anclada en el formato que prescriben los prompts
  (`source_path » heading (chars x–y)`; specs/spec-payload-agents.md §RULES y
  specs/spec-payload-commands.md). Con `heading` nulo (PDF, TD-27/D54) el
  ancla se apoya solo en `source_path` + offsets y se escribe `(sin heading)`
  — el agente no puede inventar un heading que `search` no devolvió.
  Es una **cota inferior**: la prosa adicional del agente no se cuenta aquí.

Tokenizador de referencia (declarado, no asumido)
------------------------------------------------
`cl100k_base` de `tiktoken` (versión en cada `TokenBudget`). El harness del
payload corre modelos del gateway OpenCode Zen (`opencode/big-pickle`,
`minimax-m3.1-flash-free`, `glm-5.3-flash-free`…) cuyos tokenizadores no están
en el repo ni se distribuyen con nombre estable ⇒ se usa uno de REFERENCIA
documentado y se declara (AC de T6). Se elige el más CARO de los dos BPE
públicos de OpenAI medido sobre este corpus (ES 0,27 vs 0,24 tok/char, CJK
1,04 vs 0,81, `o200k_base`): una cota que se cumple con él se cumple con el
otro, así que el guard no depende de la elección. `o200k_base` —el encoding
de la familia gpt-4o/gpt-5, tiktoken `MODEL_TO_ENCODING`,
https://github.com/openai/tiktoken— va publicado al lado en la evidencia.

Caché del vocabulario: `tiktoken` descarga el BPE la primera vez y lo cachea
en `$TMPDIR/data-gym-cache` (o `TIKTOKEN_CACHE_DIR`); el primer uso necesita
red una vez, como el modelo de embeddings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from typing import Final

import tiktoken
from tepochcalli_mcp.tools import json_result

QUERY_TOKEN_CEILING: Final = 2000
"""Cota de docs/BACKLOG.md criterio 4: «inferior a 2000» ⇒ la aserción es `< 2000`."""

TOKENIZER_ENCODING: Final = "cl100k_base"
"""Tokenizador de REFERENCIA del guard: el más caro de los dos BPE públicos (ver módulo)."""

CROSS_CHECK_ENCODING: Final = "o200k_base"
"""Encoding de la familia gpt-4o/gpt-5 — se publica para auditar la elección."""

TOKENIZER_VERSION: Final = getattr(tiktoken, "__version__", "desconocida")
"""Versión de `tiktoken` que produce la cifra (la del venv pineado)."""

CLAIM: Final = (
    "El fragmento recuperado respalda la afirmación con el vocabulario del propio documento."
)
"""Afirmación de una frase (~13 palabras, ES) que el esqueleto ancla por resultado."""


@cache
def _encoder(encoding: str) -> tiktoken.Encoding:
    """Devuelve el encoding memoizado por nombre (el BPE se descarga una vez)."""
    return tiktoken.get_encoding(encoding)


def count_tokens(text: str, encoding: str = TOKENIZER_ENCODING) -> int:
    """Tokens de `text`.

    `disallowed_special=()`: el material del usuario puede contener literales
    tipo `<|endoftext|>`; contarlos debe ser texto, no una excepción.
    """
    return len(_encoder(encoding).encode(text, disallowed_special=()))


def wire_text(payload: dict[str, object]) -> str:
    """`content[0].text` del payload — el empaquetador REAL del server."""
    return json_result(payload).content[0].text  # type: ignore[union-attr]


def citation_anchor(result: dict[str, object]) -> str:
    """Ancla en el formato prescrito: `source_path » heading (chars x–y)`."""
    heading = result.get("heading") or "(sin heading)"
    return (
        f"`{result['source_path']} » {heading} (chars {result['char_start']}–{result['char_end']})`"
    )


def answer_skeleton(payload: dict[str, object], *, claims_per_result: int = 1) -> str:
    """Respuesta mínima con TODOS los resultados anclados (1 frase citable cada uno).

    `claims_per_result` solo lo usa el test de no-vacuidad: mide cuánto margen
    de prosa queda antes de incumplir la cota. Con `results` vacío (payload de
    error) devuelve solo el encabezado: se cuenta igual, jamás se omite.
    """
    results = payload.get("results") or []
    lines = ["Respuesta con citas del corpus indexado:"]
    for index, result in enumerate(results, start=1):
        assert isinstance(result, dict)  # contrato del wire
        lines.append(
            f"- Evidencia {index}: "
            + " ".join([CLAIM] * claims_per_result)
            + f" {citation_anchor(result)}"
        )
    return "\n".join(lines)


@dataclass(frozen=True)
class TokenBudget:
    """Desglose medido de una consulta: query + payload + respuesta, y su total."""

    case: str
    results: int
    truncated: bool
    error: str | None
    query_tokens: int
    payload_tokens: int
    answer_tokens: int
    totals_by_encoding: dict[str, int] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        """Total del guard: el del tokenizador de referencia."""
        return self.totals_by_encoding[TOKENIZER_ENCODING]

    def headroom(self) -> int:
        """Tokens que sobran hasta la cota (la prosa que el agente aún puede gastar)."""
        return QUERY_TOKEN_CEILING - self.total_tokens

    def line(self) -> str:
        """Una fila del desglose publicable (fallos y evidencia)."""
        return (
            f"{self.case}: query={self.query_tokens} payload={self.payload_tokens} "
            f"respuesta={self.answer_tokens} total={self.total_tokens} "
            f"(n={self.results}, truncated={self.truncated}, error={self.error}, "
            f"margen={self.headroom()})"
        )

    def as_dict(self) -> dict[str, object]:
        """Forma serializable del desglose (JSON de evidencia)."""
        return {
            "case": self.case,
            "results": self.results,
            "truncated": self.truncated,
            "error": self.error,
            "query_tokens": self.query_tokens,
            "payload_tokens": self.payload_tokens,
            "answer_tokens": self.answer_tokens,
            "total_tokens": self.total_tokens,
            "headroom_tokens": self.headroom(),
            "tokenizer": TOKENIZER_ENCODING,
            "tiktoken_version": TOKENIZER_VERSION,
            "totals_by_encoding": dict(self.totals_by_encoding),
        }


def measure(
    case: str,
    query: str,
    payload: dict[str, object],
    *,
    claims_per_result: int = 1,
) -> TokenBudget:
    """Mide la consulta completa: query del usuario + wire del server + respuesta citada."""
    text = wire_text(payload)
    answer = answer_skeleton(payload, claims_per_result=claims_per_result)
    error = payload.get("error")
    totals = {
        encoding: count_tokens(query, encoding)
        + count_tokens(text, encoding)
        + count_tokens(answer, encoding)
        for encoding in (TOKENIZER_ENCODING, CROSS_CHECK_ENCODING)
    }
    return TokenBudget(
        case=case,
        results=len(payload.get("results") or []),  # type: ignore[arg-type]
        truncated=bool(payload.get("truncated", False)),
        error=str(error.get("code")) if isinstance(error, dict) else None,  # type: ignore[union-attr]
        query_tokens=count_tokens(query),
        payload_tokens=count_tokens(text),
        answer_tokens=count_tokens(answer),
        totals_by_encoding=totals,
    )
