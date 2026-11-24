"""T10: handler de `convert_base64` — pista de tipo → bytes → disco → resumen (unit).

Fuentes de verdad:

* tasks/todo.md T10 AC (b)-(i) — `format` o `filename` con extensión conocida
  (sin pista ⇒ `VALIDATION_ERROR` que nombra `list_formats`, D38); base64
  inválido ⇒ `VALIDATION_ERROR` (nunca `INTERNAL`); `output_path` con la
  frontera B′; `source_uri` = `filename` o `base64:<sha256-8>`; el mismo
  resumen de 5 claves e idempotencia de T9 (D66).
* docs/adr/adr-009-conversor-resumen-sin-cuerpo.md §D37/D38, §D39, §D66.
* specs/spec-markitdown.md §Contrato, §Destino/idempotencia.

Costuras FALSAS (patrón T9): la conversión real vive en
`tests/integration/test_mcp_convert_base64.py`.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest
from tepochcalli_mcp import formats, paths, summary
from tepochcalli_mcp.tools import convert_base64 as handler

DATA = b"docx sintetico"
"""Bytes del documento: el caso feliz no necesita un `.docx` real (eso es integración)."""

ENCODED = base64.b64encode(DATA).decode("ascii")
"""El mismo contenido en base64, tal como lo manda el agente."""

CONTENT = "# Informe\n\ncuerpo convertido\n"
"""Markdown que la costura falsa devuelve en el camino feliz."""

DIGEST8 = hashlib.sha256(DATA).hexdigest()[:8]
"""Los 8 primeros hex del sha256: la identidad de `source_uri` sin `filename` (D38)."""


def _vault(tmp_path: Path) -> Path:
    """Vault mínimo con `00-resources/` (destino default)."""
    vault = tmp_path / "vault"
    (vault / "00-resources").mkdir(parents=True)
    return vault


def _run(
    data: str = ENCODED,
    output_path: str | None = None,
    format: str | None = None,
    filename: str | None = None,
    *,
    vault: Path,
    convert: Callable[..., str] | None = None,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Ejecuta el handler con costuras falsas; devuelve `(payload, llamadas a convert)`."""
    calls: list[dict[str, object]] = []

    def fake_convert(raw: bytes, *, filename: str | None, extension: str, source_uri: str) -> str:
        calls.append(
            {"data": raw, "filename": filename, "extension": extension, "source_uri": source_uri}
        )
        return CONTENT

    payload = asyncio.run(
        handler.convert_base64(
            data,
            output_path,
            format,
            filename,
            vault_root=lambda: vault,
            convert=convert or fake_convert,
        )
    )
    return payload, calls


def _error_code(payload: dict[str, object]) -> object:
    """Código del payload de error (el camino de éxito no tiene clave `error`)."""
    error = payload.get("error")
    assert isinstance(error, dict)
    return error["code"]


def _catalog(payload: dict[str, object]) -> dict[str, object]:
    """`details` del error de catálogo: la lista de `list_formats` (D39)."""
    error = payload["error"]
    assert isinstance(error, dict)
    details = error["details"]
    assert isinstance(details, dict)
    return details


# --- camino feliz: pista de tipo, decodificación y resumen -------------------------


def test_filename_gives_the_source_uri_and_the_default_destination(tmp_path: Path) -> None:
    """`filename` ⇒ `source_uri` = filename (D38); destino `00-resources/<slug>.md`."""
    vault = _vault(tmp_path)

    payload, calls = _run(filename="informe.docx", vault=vault)

    assert list(payload) == ["written_to", "source_uri", "bytes", "chars", "preview"]
    assert "ok" not in payload, "D36: el éxito es la ausencia de error"
    assert payload["written_to"] == "00-resources/informe.md"
    assert payload["source_uri"] == "informe.docx"
    assert calls == [
        {
            "data": DATA,
            "filename": "informe.docx",
            "extension": ".docx",
            "source_uri": "informe.docx",
        }
    ]
    written = vault / "00-resources" / "informe.md"
    assert written.read_text(encoding="utf-8") == CONTENT
    assert payload == summary.build_summary(written, source_uri="informe.docx", vault_root=vault)


def test_without_filename_the_source_uri_is_the_base64_sha_prefix(tmp_path: Path) -> None:
    """Sin `filename`: `base64:<sha256-8>` y destino derivado de esa misma identidad."""
    vault = _vault(tmp_path)

    payload, calls = _run(format="docx", vault=vault)

    assert payload["source_uri"] == f"base64:{DIGEST8}"
    assert payload["written_to"] == f"00-resources/base64-{DIGEST8}.docx"
    assert calls[0]["source_uri"] == f"base64:{DIGEST8}"
    assert calls[0]["extension"] == ".docx"
    assert calls[0]["filename"] is None


def test_explicit_output_path_and_format_are_respected(tmp_path: Path) -> None:
    """`output_path` explícito + `format` que fuerza la extensión (D37)."""
    vault = _vault(tmp_path)
    (vault / "00-resources" / "fuentes").mkdir()

    payload, _calls = _run(
        output_path="00-resources/fuentes/x.md", format="pdf", filename="informe.docx", vault=vault
    )

    assert payload["written_to"] == "00-resources/fuentes/x.pdf"
    assert (vault / "00-resources" / "fuentes" / "x.pdf").is_file()


# --- pista de tipo obligatoria (D38) ----------------------------------------------


@pytest.mark.parametrize("filename", [None, "informe"])
def test_no_type_hint_is_validation_error_naming_list_formats(
    tmp_path: Path, filename: str | None
) -> None:
    """Sin `format` ni extensión conocida ⇒ `VALIDATION_ERROR` que nombra `list_formats`."""
    vault = _vault(tmp_path)

    payload, calls = _run(filename=filename, vault=vault)

    assert _error_code(payload) == "VALIDATION_ERROR"
    assert "list_formats" in payload["error"]["message"]
    assert _catalog(payload) == {"formats": list(formats.SUPPORTED_FORMATS)}
    assert calls == [], "sin pista de tipo no se adivina el extractor (D38)"


def test_an_unknown_hint_is_validation_error_with_the_catalog(tmp_path: Path) -> None:
    """Pista presente pero fuera del catálogo ⇒ `VALIDATION_ERROR` con la lista."""
    vault = _vault(tmp_path)

    payload, calls = _run(format="bin", vault=vault)

    assert _error_code(payload) == "VALIDATION_ERROR"
    assert _catalog(payload) == {"formats": list(formats.SUPPORTED_FORMATS)}
    assert calls == []


# --- base64 inválido: VALIDATION_ERROR, nunca INTERNAL (AC (d)) --------------------


@pytest.mark.parametrize("data", ["no-es-base64!!", "####", "abc"])
def test_invalid_base64_is_validation_error_and_never_reaches_the_seam(
    tmp_path: Path, data: str
) -> None:
    """`b64decode(validate=True)` falla ⇒ `VALIDATION_ERROR` sin convertir ni escribir."""
    vault = _vault(tmp_path)

    payload, calls = _run(data=data, filename="informe.docx", vault=vault)

    assert _error_code(payload) == "VALIDATION_ERROR"
    assert payload["error"]["details"] == {"field": "data"}
    assert calls == []
    assert list((vault / "00-resources").iterdir()) == []


# --- frontera B′ del destino (D31) ------------------------------------------------


@pytest.mark.parametrize(
    "output_path", ["../fuera.md", "/etc/fuera.md", "00-resources/../fuera.md"]
)
def test_output_path_outside_the_vault_is_rejected_and_nothing_is_written(
    tmp_path: Path, output_path: str
) -> None:
    """B′: `..` o absoluta externa ⇒ `VALIDATION_ERROR`; el fichero externo NO se crea."""
    vault = _vault(tmp_path)
    outside = tmp_path / "fuera.md"
    external = Path("/etc/fuera.md")

    payload, calls = _run(output_path=output_path, filename="informe.docx", vault=vault)

    assert _error_code(payload) == "VALIDATION_ERROR"
    assert calls == [], "la frontera del destino se valida ANTES de convertir (D31)"
    assert not outside.exists()
    assert not external.exists()


def test_missing_parent_of_the_output_path_is_validation_error(tmp_path: Path) -> None:
    """El padre del destino debe existir como directorio dentro del vault (D64)."""
    vault = _vault(tmp_path)

    payload, _calls = _run(
        output_path="00-resources/fuentes/x.md", filename="informe.docx", vault=vault
    )

    assert _error_code(payload) == "VALIDATION_ERROR"
    assert payload["error"]["details"]["exists"] is False


# --- sin capa de texto: SOURCE_UNREACHABLE con guía OCR, sin parciales ------------


@pytest.mark.parametrize("markdown", ["", "   \n\t\n"])
def test_empty_markdown_is_source_unreachable_with_the_ocr_guide(
    tmp_path: Path, markdown: str
) -> None:
    """Escaneado sin texto ⇒ `SOURCE_UNREACHABLE` (guía OCR) y CERO parciales en disco."""
    vault = _vault(tmp_path)

    payload, _calls = _run(filename="informe.docx", vault=vault, convert=lambda *_a, **_k: markdown)

    assert _error_code(payload) == "SOURCE_UNREACHABLE"
    assert "OCR" in payload["error"]["message"]
    assert not (vault / "00-resources" / "informe.md").exists(), "sin parciales"


def test_unexpected_conversion_failure_is_source_unreachable(tmp_path: Path) -> None:
    """Un convertidor roto ⇒ `SOURCE_UNREACHABLE` con la causa tipada; nada escrito."""

    def broken(*_args: object, **_kwargs: object) -> str:
        raise RuntimeError("corrupto")

    vault = _vault(tmp_path)

    payload, _calls = _run(filename="informe.docx", vault=vault, convert=broken)

    assert _error_code(payload) == "SOURCE_UNREACHABLE"
    assert payload["error"]["details"] == {"cause": "RuntimeError"}
    assert not (vault / "00-resources" / "informe.md").exists()


# --- idempotencia (D66) -----------------------------------------------------------


def test_identical_conversions_are_idempotent_and_do_not_touch_the_file(tmp_path: Path) -> None:
    """Dos llamadas idénticas ⇒ misma respuesta de éxito y mtime intacto."""
    vault = _vault(tmp_path)
    first, _calls = _run(filename="informe.docx", vault=vault)
    written = vault / "00-resources" / "informe.md"
    stamp = written.stat().st_mtime_ns

    second, _calls = _run(filename="informe.docx", vault=vault)

    assert second == first
    assert written.stat().st_mtime_ns == stamp


def test_different_content_on_an_existing_destination_is_validation_error(
    tmp_path: Path,
) -> None:
    """D66: contenido distinto ⇒ `VALIDATION_ERROR` con alternativo; original intacto."""
    vault = _vault(tmp_path)
    _run(filename="informe.docx", vault=vault)
    original = (vault / "00-resources" / "informe.md").read_text(encoding="utf-8")

    payload, _calls = _run(
        filename="informe.docx",
        vault=vault,
        convert=lambda *_a, **_k: "# Otro\n\ncontenido distinto\n",
    )

    assert _error_code(payload) == "VALIDATION_ERROR"
    assert "output_path" in payload["error"]["message"]
    assert payload["error"]["details"]["suggested"] == "informe-2.md"
    assert (vault / "00-resources" / "informe.md").read_text(encoding="utf-8") == original


# --- W-08 (review 5-ejes): tope de tamaño de `data` --------------------------------------


def test_decode_rejects_base64_beyond_the_size_cap() -> None:
    """W-08: >140M chars base64 (~100MB decodificados) ⇒ `VaultPathError` con el tope.

    Los bytes viajan EN CONTEXTO del agente: sin tope, la decodificación sería
    un DoS de memoria en el proceso del vault.
    """
    with pytest.raises(paths.VaultPathError, match="140000000"):
        handler._decode("A" * (140_000_000 + 1))


def test_decode_accepts_exactly_the_size_cap() -> None:
    """W-08, límite exacto: `len(data) == 140_000_000` NO dispara el corte (usaré `>`)."""
    decoded = handler._decode("A" * 140_000_000)
    assert len(decoded) == 105_000_000, "4 chars base64 → 3 bytes decodificados"
