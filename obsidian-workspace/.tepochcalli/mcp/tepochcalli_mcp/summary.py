"""El resumen de éxito del conversor (D36/M3): 5 claves leídas del fichero ESCRITO.

Contrato de wire congelado (spec-mcp-server §Tools del conversor): `written_to`,
`source_uri`, `bytes`, `chars`, `preview` (≤500 caracteres) y `truncated` —
solo cuando el preview se recortó. No hay clave `ok`: el resumen ES la
confirmación y el fracaso es un payload `{error: …}`.

Se construye desde el DISCO (`stat` para `bytes`, el texto decodificado para
`chars` y `preview`), nunca desde el markdown en memoria: es lo que prueba que
el fichero escrito es la fuente de verdad (mitigación OM-1 del ADR-009).

`serialize_budget` aplica el techo de 1 400 caracteres SERIALIZADOS (M3,
≈200 tokens ES/EN): al pasarse recorta `preview` y marca `truncated`; el resto
de claves jamás se toca. Usa el mismo `json.dumps(ensure_ascii=False)` que
`tools.json_result`, así el presupuesto mide exactamente lo que viaja en
`content[0].text`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

PREVIEW_CHARS: Final = 500
"""Tope del preview: el agente necesita reconocer el documento, no leerlo (D36)."""

SUMMARY_CHAR_CEILING: Final = 1400
"""Techo del resumen serializado — M3 (≈200 tokens ES/EN con el estimador de `budget`)."""


def build_summary(
    target: Path, *, source_uri: str, vault_root: Path | None = None
) -> dict[str, object]:
    """Resumen de 5 claves (orden fijo) leído del fichero ya escrito en `target`.

    `vault_root` convierte `written_to` en la ruta relativa al vault que el wire
    publica; sin él se reporta `target` tal cual. `truncated` aparece solo si el
    texto excede `PREVIEW_CHARS` — el fichero completo sigue en disco.
    """
    text = target.read_text(encoding="utf-8")
    written_to = (
        target.as_posix()
        if vault_root is None
        else target.resolve().relative_to(vault_root.resolve()).as_posix()
    )
    summary: dict[str, object] = {
        "written_to": written_to,
        "source_uri": source_uri,
        "bytes": target.stat().st_size,
        "chars": len(text),
        "preview": text[:PREVIEW_CHARS],
    }
    if len(text) > PREVIEW_CHARS:
        summary["truncated"] = True
    return summary


def serialize_budget(summary: dict[str, object]) -> str:
    """JSON canónico del resumen, con `preview` recortado hasta caber en 1 400 caracteres.

    Solo se recorta `preview` (y se marca `truncated`): las demás claves son el
    contrato. Un `preview` vacío que aún no cupiera se entrega igual — un
    resumen incompleto nunca justifica romper la forma del payload.
    """
    text = json.dumps(summary, ensure_ascii=False)
    if len(text) <= SUMMARY_CHAR_CEILING:
        return text
    payload = {**summary, "truncated": True}
    preview = str(payload.get("preview", ""))
    while preview:
        payload["preview"] = preview
        text = json.dumps(payload, ensure_ascii=False)
        if len(text) <= SUMMARY_CHAR_CEILING:
            return text
        # Recorta al menos lo que sobra; un carácter escapado (`\n`) libera 2 y el bucle sigue.
        preview = preview[: len(preview) - max(1, len(text) - SUMMARY_CHAR_CEILING)]
    payload["preview"] = ""
    return json.dumps(payload, ensure_ascii=False)
