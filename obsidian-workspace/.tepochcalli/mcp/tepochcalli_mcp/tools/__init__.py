"""Empaquetado de resultados: payload dict canónico → `CallToolResult` (T2).

Este módulo ES frontera del SDK: aquí sí se importa `mcp.types` (decisión T2
documentada en `tests/unit/test_architecture.py`). `errors.py` devuelve dicts
puros — el handler serializa y ESTE módulo los envuelve en el
`CallToolResult` explícito que el spike T1 ancló: `ToolError` mete texto libre
y dejaría `structured_content = None` (plan §3 «omen mayor», hallazgo H4), lo
que rompería el contrato `content[0].text` = JSON canónico (spec-mcp-server
§Manejo de errores: «nunca texto libre»).
"""

from __future__ import annotations

import json

from mcp.types import CallToolResult, TextContent


def json_result(payload: dict[str, object]) -> CallToolResult:
    """JSON canónico en `content[0].text`; un payload con clave `error` viaja con `is_error`.

    `ensure_ascii=False` conserva el texto ES/EN/multibyte tal cual (citas y
    chunks CJK sin escapes); el orden de claves del dict —el del contrato— se
    preserva en el dumps (Python 3.7+). El campo Python es `is_error` y viaja
    en el wire como `isError` (alias de `mcp_types`, spike T1).
    """
    return json_text_result(json.dumps(payload, ensure_ascii=False), is_error="error" in payload)


def json_text_result(text: str, *, is_error: bool = False) -> CallToolResult:
    """Empaqueta un JSON YA serializado (presupuesto aplicado) en `content[0].text`.

    Lo usa el conversor: `summary.serialize_budget` decide el recorte del
    `preview` sobre el texto final, y volver a serializar aquí podría cambiar
    el tamaño medido (ADR-009 D36/M3).
    """
    return CallToolResult(content=[TextContent(type="text", text=text)], is_error=is_error)
