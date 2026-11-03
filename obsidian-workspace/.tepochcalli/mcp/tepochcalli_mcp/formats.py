"""Catálogo de formatos del conversor (D55/D39) — DATO puro, sin `markitdown`.

Verificado contra `markitdown==0.1.9` con los extras `[pdf,docx,pptx,xlsx,xls]`
(no estimado: specs/spec-markitdown.md §Catálogo ata cada extensión a una
conversión real en los contract tests de T11). El módulo NO importa el
conversor — el catálogo es dato, no una llamada al extractor, y el test de
arquitectura prohíbe que el dominio alcance `markitdown`.

Fuera del catálogo v1, con motivo: `.doc`/`.ppt` (markitdown 0.1.9 no tiene
convertidor legacy), `.zip`/`.epub`/`.ipynb`/`.xml`/`.jpg` (multiplican la
superficie de decodificación de entrada no confiable sin OCR) y `.msg`
(depende de `olefile`, que sale con la dieta de extras).
"""

from __future__ import annotations

from typing import Final

SUPPORTED_FORMATS: Final[tuple[str, ...]] = (
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".xls",
    ".html",
    ".htm",
    ".csv",
    ".txt",
    ".md",
    ".markdown",
    ".json",
    ".jsonl",
)
"""Las 13 extensiones del contrato §5.5, en el orden en que `list_formats` las publica."""

NOTES: Final = (
    "Sin OCR: un PDF escaneado no tiene capa de texto y no se convierte. "
    "Fuera del catálogo: `.doc`/`.ppt`, porque markitdown 0.1.9 no trae "
    "convertidor legacy para esos binarios."
)
"""La nota del wire (H1): el catálogo es honesto sobre lo que la instalación NO hace."""


class UnsupportedFormatError(ValueError):
    """Extensión sin convertidor en `markitdown`: el borde responde `VALIDATION_ERROR`.

    La infraestructura (`convert.py`) traduce aquí la `UnsupportedFormatException`
    de markitdown: `tools/` no puede importar la librería (test de arquitectura),
    así que la costura devuelve un tipo de dominio — mismo patrón que el dialecto
    `E_*` de `embedder`.
    """


def is_supported(suffix: str) -> bool:
    """¿La extensión (`.pdf`, `pdf` o `PDF`) está en el catálogo? Normaliza antes de mirar."""
    normalized = suffix.strip().lower()
    if normalized and not normalized.startswith("."):
        normalized = f".{normalized}"
    return normalized in SUPPORTED_FORMATS
