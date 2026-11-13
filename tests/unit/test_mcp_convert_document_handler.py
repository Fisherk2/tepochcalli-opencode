"""T9: handler de `convert_document` — borde B′ → costura → escritura → resumen (unit).

Fuentes de verdad:

* tasks/todo.md T9 AC (a)-(l) — `path` inexistente o directorio ⇒
  `VALIDATION_ERROR` (nunca `INTERNAL`/`SOURCE_UNREACHABLE`); `output_path`
  omitido ⇒ `00-resources/<slug>.md`; `format` fuerza la extensión; fuera del
  catálogo ⇒ `VALIDATION_ERROR` con la lista; markdown vacío ⇒
  `SOURCE_UNREACHABLE` con la guía de OCR y **sin** parciales; idempotencia
  D66; la respuesta es EXACTAMENTE el resumen de 5 claves.
* specs/adr/adr-009-conversor-resumen-sin-cuerpo.md §4 (D31/D36/D37/D39/D64/D66).
* specs/spec-markitdown.md §Contrato, §Catálogo, §Destino/idempotencia.

Se ejercita con costuras FALSAS (patrón T5): `vault_root` y `convert` los
inyecta el composition root en producción; aquí se prueba el dominio sin
markitdown. La conversión REAL vive en `tests/integration/test_mcp_convert_document.py`
y el cuerpo ausente del wire (OM-1) se gradúa allí, por stdio.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

import pytest
from tepochcalli_mcp import formats, summary
from tepochcalli_mcp.tools import convert_document as handler

CONTENT = "# Informe\n\ncuerpo convertido\n"
"""Markdown corto que la costura falsa devuelve en el camino feliz."""


def _vault(tmp_path: Path) -> Path:
    """Vault mínimo: `00-resources/` (destino default) y un documento de entrada."""
    vault = tmp_path / "vault"
    (vault / "00-resources").mkdir(parents=True)
    (vault / "documentos").mkdir()
    (vault / "documentos" / "informe.docx").write_bytes(b"docx sintetico")
    (vault / "documentos" / "datos.bin").write_bytes(b"binario sin converter")
    return vault


def _run(
    path: str,
    output_path: str | None = None,
    format: str | None = None,
    *,
    vault: Path,
    convert: Callable[..., str] | None = None,
) -> tuple[dict[str, object], list[tuple[Path, str]]]:
    """Ejecuta el handler con costuras falsas; devuelve `(payload, llamadas a convert)`."""
    calls: list[tuple[Path, str]] = []

    def fake_convert(source: Path, *, source_uri: str, extension_hint: str | None = None) -> str:
        calls.append((source, source_uri))
        return CONTENT

    payload = asyncio.run(
        handler.convert_document(
            path,
            output_path,
            format,
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


# --- camino feliz: resumen de 5 claves --------------------------------------------


def test_success_writes_the_file_and_returns_exactly_the_five_key_summary(
    tmp_path: Path,
) -> None:
    """`output_path` omitido ⇒ `00-resources/<slug>.md`; respuesta = `build_summary`."""
    vault = _vault(tmp_path)

    payload, calls = _run("documentos/informe.docx", vault=vault)

    assert list(payload) == ["written_to", "source_uri", "bytes", "chars", "preview"]
    assert "ok" not in payload, "D36: el éxito es la ausencia de error"
    assert payload["written_to"] == "00-resources/informe.md"
    assert payload["source_uri"] == "documentos/informe.docx"
    assert calls == [(vault / "documentos" / "informe.docx", "documentos/informe.docx")]
    written = vault / "00-resources" / "informe.md"
    assert written.read_text(encoding="utf-8") == CONTENT
    assert payload == summary.build_summary(
        written, source_uri="documentos/informe.docx", vault_root=vault
    )


def test_the_written_markdown_has_no_frontmatter_or_converted_at(tmp_path: Path) -> None:
    """D36: el frontmatter (`converted_at`) es exclusivo de `add_source` — aquí rompería D66."""
    vault = _vault(tmp_path)

    _run("documentos/informe.docx", vault=vault)

    text = (vault / "00-resources" / "informe.md").read_text(encoding="utf-8")
    assert text == CONTENT
    assert not text.startswith("---")
    assert "converted_at" not in text


def test_explicit_output_path_is_respected(tmp_path: Path) -> None:
    """`output_path` explícito dentro del vault (subcarpeta existente) se usa tal cual."""
    vault = _vault(tmp_path)
    (vault / "00-resources" / "fuentes").mkdir()

    payload, _calls = _run(
        "documentos/informe.docx", "00-resources/fuentes/informe.md", vault=vault
    )

    assert payload["written_to"] == "00-resources/fuentes/informe.md"
    assert (vault / "00-resources" / "fuentes" / "informe.md").is_file()


def test_format_forces_the_destination_extension(tmp_path: Path) -> None:
    """`format` es pista de tipo Y fuerza la extensión del destino (AC (e))."""
    vault = _vault(tmp_path)

    defaulted, _calls = _run("documentos/datos.bin", format="docx", vault=vault)
    explicit, _calls = _run("documentos/datos.bin", "00-resources/x.md", "pdf", vault=vault)

    assert defaulted["written_to"] == "00-resources/datos.docx"
    assert explicit["written_to"] == "00-resources/x.pdf"


def test_format_is_also_the_conversion_hint_for_a_suffixless_file(tmp_path: Path) -> None:
    """W-06 (orden del dueño): `format` fuerza el sufijo del destino Y es la pista.

    `informe` SIN extensión + `format=".txt"` ⇒ se convierte (`StreamInfo.
    extension` llega por la costura): hoy el conversor no ve pista alguna y
    responde `UnsupportedFormatException` engañoso.
    """
    vault = _vault(tmp_path)
    plain = vault / "documentos" / "informe"
    plain.write_text("cuerpo plano\n", encoding="utf-8")
    hints: list[str | None] = []

    def convert(source: Path, *, source_uri: str, extension_hint: str | None) -> str:
        hints.append(extension_hint)
        assert source_uri == "documentos/informe"
        return CONTENT

    payload, _calls = _run("documentos/informe", format=".txt", vault=vault, convert=convert)

    assert "error" not in payload
    assert hints == [".txt"], "la pista de conversión llega por la costura"
    assert payload["written_to"] == "00-resources/informe.txt"
    assert (vault / "00-resources" / "informe.txt").read_text(encoding="utf-8") == CONTENT


# --- frontera B′ y existencia/tipo (D31/D64) --------------------------------------


def test_missing_path_is_validation_error_without_converting(tmp_path: Path) -> None:
    """`path` inexistente ⇒ `VALIDATION_ERROR` con `details.suggestions`, sin costura."""
    vault = _vault(tmp_path)

    payload, calls = _run("Documentos/informe.docx", vault=vault)

    assert _error_code(payload) == "VALIDATION_ERROR"
    assert calls == [], "se decide en el borde, ANTES de tocar markitdown (D64)"
    details = payload["error"]["details"]
    assert details["exists"] is False
    assert details["suggestions"] == ["documentos"]


def test_a_directory_as_path_is_validation_error_not_internal(tmp_path: Path) -> None:
    """`path` que es un directorio ⇒ `VALIDATION_ERROR` con `{expected, found}`."""
    vault = _vault(tmp_path)

    payload, calls = _run("documentos", vault=vault)

    assert _error_code(payload) == "VALIDATION_ERROR"
    assert calls == []
    assert payload["error"]["details"] == {
        "requested": "documentos",
        "exists": True,
        "expected": "file",
        "found": "directory",
    }


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

    payload, calls = _run("documentos/informe.docx", output_path, vault=vault)

    assert _error_code(payload) == "VALIDATION_ERROR"
    assert calls == [], "la frontera del destino se valida ANTES de convertir (D31)"
    assert not outside.exists()
    assert not external.exists()


def test_missing_parent_of_the_output_path_is_validation_error(tmp_path: Path) -> None:
    """El padre del destino debe existir como directorio dentro del vault (D64)."""
    vault = _vault(tmp_path)

    payload, _calls = _run("documentos/informe.docx", "00-resources/fuentes/x.md", vault=vault)

    assert _error_code(payload) == "VALIDATION_ERROR"
    assert payload["error"]["details"]["exists"] is False


# --- catálogo de formatos (D39) ---------------------------------------------------


def test_extension_outside_the_catalog_is_validation_error_with_the_list(
    tmp_path: Path,
) -> None:
    """Extensión fuera del catálogo ⇒ `VALIDATION_ERROR` con la lista; no se convierte."""
    vault = _vault(tmp_path)

    payload, calls = _run("documentos/datos.bin", vault=vault)

    assert _error_code(payload) == "VALIDATION_ERROR"
    assert calls == []
    assert payload["error"]["details"] == {"formats": list(formats.SUPPORTED_FORMATS)}


def test_unsupported_format_from_the_seam_maps_to_validation_error(tmp_path: Path) -> None:
    """`UnsupportedFormatError` de la costura ⇒ `VALIDATION_ERROR` con la lista (D39)."""

    def unsupported(_source: Path, *, source_uri: str, extension_hint: str | None = None) -> str:
        raise formats.UnsupportedFormatError(f"sin convertidor para {source_uri}")

    vault = _vault(tmp_path)

    payload, _calls = _run("documentos/informe.docx", vault=vault, convert=unsupported)

    assert _error_code(payload) == "VALIDATION_ERROR"
    assert payload["error"]["details"] == {"formats": list(formats.SUPPORTED_FORMATS)}


# --- sin capa de texto: SOURCE_UNREACHABLE con guía OCR, sin parciales ------------


@pytest.mark.parametrize("markdown", ["", "   \n\t\n"])
def test_empty_markdown_is_source_unreachable_with_the_ocr_guide(
    tmp_path: Path, markdown: str
) -> None:
    """Escaneado sin texto ⇒ `SOURCE_UNREACHABLE` (guía OCR) y CERO parciales en disco."""
    vault = _vault(tmp_path)

    payload, _calls = _run(
        "documentos/informe.docx", vault=vault, convert=lambda *_a, **_k: markdown
    )

    assert _error_code(payload) == "SOURCE_UNREACHABLE"
    assert "OCR" in payload["error"]["message"]
    assert not (vault / "00-resources" / "informe.md").exists(), "sin parciales"


# --- idempotencia (D66) -----------------------------------------------------------


def test_identical_conversions_are_idempotent_and_do_not_touch_the_file(
    tmp_path: Path,
) -> None:
    """Dos llamadas idénticas ⇒ misma respuesta de éxito y mtime intacto."""
    vault = _vault(tmp_path)
    first, _calls = _run("documentos/informe.docx", vault=vault)
    written = vault / "00-resources" / "informe.md"
    stamp = written.stat().st_mtime_ns

    second, _calls = _run("documentos/informe.docx", vault=vault)

    assert second == first
    assert written.stat().st_mtime_ns == stamp


def test_different_content_on_an_existing_destination_is_validation_error(
    tmp_path: Path,
) -> None:
    """D66: contenido distinto ⇒ `VALIDATION_ERROR` con alternativo; original intacto."""
    vault = _vault(tmp_path)
    _run("documentos/informe.docx", vault=vault)
    original = (vault / "00-resources" / "informe.md").read_text(encoding="utf-8")

    payload, _calls = _run(
        "documentos/informe.docx",
        vault=vault,
        convert=lambda *_a, **_k: "# Otro\n\ncontenido distinto\n",
    )

    assert _error_code(payload) == "VALIDATION_ERROR"
    assert "output_path" in payload["error"]["message"]
    assert payload["error"]["details"]["suggested"] == "informe-2.md"
    assert (vault / "00-resources" / "informe.md").read_text(encoding="utf-8") == original


def test_unexpected_conversion_failure_is_source_unreachable(tmp_path: Path) -> None:
    """Un convertidor roto ⇒ `SOURCE_UNREACHABLE` con la causa tipada; nada escrito."""

    def broken(_source: Path, *, source_uri: str, extension_hint: str | None = None) -> str:
        raise RuntimeError("corrupto")

    vault = _vault(tmp_path)

    payload, _calls = _run("documentos/informe.docx", vault=vault, convert=broken)

    assert _error_code(payload) == "SOURCE_UNREACHABLE"
    assert payload["error"]["details"] == {"cause": "RuntimeError"}
    assert not (vault / "00-resources" / "informe.md").exists()


# --- W-05 (review 5-ejes): el log de `_convert_tail` no filtra el URI -------------------


def test_conversion_failure_log_redacts_and_truncates_the_uri(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """W-05: `logger.exception` redacta credenciales (`redact_uri`) y trunca a 300 chars.

    El URI fuega tal cual entró en el log stderr (review eje 4 W-05): la
    credencial en query (`pwd=…`) no puede escapar por la dimensión log-forge.
    """
    import logging

    from tepochcalli_mcp.tools._convert_tail import write_converted

    tail_uri = "https://api.com/i" + "p" * 900 + ".pdf?pwd=secret123"

    async def raising() -> str:
        msg = "corrupto"
        raise ValueError(msg)

    with caplog.at_level(logging.ERROR, logger="test.convert.log"):
        payload = asyncio.run(
            write_converted(
                run_convert=raising,
                target=Path("/tmp/irrelevante.md"),
                source_uri=tail_uri,
                vault_root=Path("/tmp"),
                tool="convert_document",
                logger=logging.getLogger("test.convert.log"),
            )
        )

    assert _error_code(payload) == "SOURCE_UNREACHABLE"
    record = next(r for r in caplog.records if r.message.startswith("convert_document:"))
    massage = record.getMessage()
    assert "secret123" not in massage, "la query secreta NO llega al log en claro"
    assert len(massage) < 400, "truncado a ~300 chars (el path era de 900)"
