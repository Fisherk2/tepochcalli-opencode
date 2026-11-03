"""Handler de `list_formats`: publica el catálogo REAL del conversor (T11).

El agente no adivina extensiones ni promete formatos que fallarían: la tool lee
el catálogo de `formats.py` (dato puro) y devuelve `{formats, count, notes}`.
`count` se DERIVA de la tupla —nunca se escribe a mano: un catálogo que crezca
sin actualizar el contador sería una mentira silenciosa— y `notes` declara los
dos límites que el agente debe respetar: no hay OCR y `.doc`/`.ppt` quedan
fuera porque `markitdown 0.1.9` no trae convertidor legacy (spec-markitdown
§Catálogo; prometerlos fallaría en tiempo de conversión, no en `list_formats`).

Sin costuras y sin `markitdown` (test de arquitectura): es dato curado, no una
llamada al extractor. La respuesta queda < 200 tokens con el estimador de
`budget` (`chars/4 + 25`); si la nota creciera, se acorta la nota — nunca el
catálogo.
"""

from __future__ import annotations

from tepochcalli_mcp import formats


def list_formats() -> dict[str, object]:
    """Publica `{formats, count, notes}` en ese orden: el catálogo tal como se publica (AC a)."""
    return {
        "formats": list(formats.SUPPORTED_FORMATS),
        "count": len(formats.SUPPORTED_FORMATS),
        "notes": formats.NOTES,
    }
