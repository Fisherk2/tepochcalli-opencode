"""T7 (D31/D64/D65): frontera B′ — dentro/fuera, existencia y tipo, sugerencias, fail-fast.

Fuentes de verdad:

* tasks/todo.md T7 AC (a), (b), (i), (j) — `validate_vault_path` devuelve la ruta
  ABSOLUTA si está dentro del vault; fuera (absoluta externa, `..`, symlink que
  escapa) ⇒ error tipado que el borde mapea a `VALIDATION_ERROR`.
* tasks/plan.md §5.9 — tres cubos: inexistente ⇒ `details: {requested,
  exists: false, suggestions[], vault_dirs[]}`; tipo equivocado ⇒ `{requested,
  exists: true, expected, found}`; sugerencias por similitud SIN distinguir
  mayúsculas (`Documentos` → `documentos`).
* ADR-010 §4.8 (D64) y D65 (fail-fast atómico: una raíz mala ⇒ no se indexa
  ninguna).

El error es `paths.VaultPathError` (subclase de `ValueError`: lo que el AC (a)
llama «`ValueError` → `VALIDATION_ERROR`») y lleva sus `details` al payload.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tepochcalli_mcp import paths


def _vault(tmp_path: Path) -> Path:
    """Vault mínimo con dos carpetas de primer nivel indexables y una de punto."""
    vault = tmp_path / "vault"
    for name in ("00-resources", "documentos", "materiales", ".tepochcalli"):
        (vault / name).mkdir(parents=True)
    (vault / "documentos" / "informe.docx").write_text("x", encoding="utf-8")
    return vault


# --- dentro del vault -----------------------------------------------------------


def test_relative_path_inside_resolves_to_the_absolute_path(tmp_path: Path) -> None:
    """Dentro ⇒ ruta ABSOLUTA resuelta (la que el motor y el conversor consumen)."""
    vault = _vault(tmp_path)

    resolved = paths.validate_vault_path(
        "documentos/informe.docx", vault, must_exist=True, expect="file"
    )

    assert resolved == (vault / "documentos" / "informe.docx").resolve()
    assert resolved.is_absolute()


def test_absolute_path_inside_is_accepted(tmp_path: Path) -> None:
    """Una ruta absoluta DENTRO del vault es legítima (el agente a veces la conoce)."""
    vault = _vault(tmp_path)

    resolved = paths.validate_vault_path(vault / "documentos", vault, must_exist=True)

    assert resolved == (vault / "documentos").resolve()


def test_a_destination_with_existing_parent_returns_the_future_target(tmp_path: Path) -> None:
    """Destino (`must_exist=False`): se valida el PADRE; el fichero aún no existe."""
    vault = _vault(tmp_path)

    target = paths.validate_vault_path("documentos/nuevo.md", vault, must_exist=False)

    assert target == (vault / "documentos" / "nuevo.md").resolve()
    assert not target.exists()


# --- fuera del vault o escape ----------------------------------------------------


def test_absolute_path_outside_the_vault_is_rejected(tmp_path: Path) -> None:
    """Absoluta externa ⇒ error; el fichero externo no se crea (B′, D31)."""
    vault = _vault(tmp_path)
    outside = tmp_path / "fuera.md"

    with pytest.raises(paths.VaultPathError):
        paths.validate_vault_path(outside, vault, must_exist=False)

    assert not outside.exists()


@pytest.mark.parametrize(
    "raw",
    [
        "00-resources/../fuera.md",
        "../fuera.md",
        "documentos/../../fuera.md",
        "/etc/passwd",
    ],
)
def test_parent_segments_and_external_absolutes_are_rejected(tmp_path: Path, raw: str) -> None:
    """`..` en cualquier forma y absolutas fuera del vault ⇒ error tipado."""
    vault = _vault(tmp_path)

    with pytest.raises(paths.VaultPathError):
        paths.validate_vault_path(raw, vault, must_exist=True)


def test_symlink_that_escapes_the_vault_is_rejected(tmp_path: Path) -> None:
    """Un enlace DENTRO del vault que apunta FUERA también cae (frontera = vault)."""
    vault = _vault(tmp_path)
    outside = tmp_path / "secreto.md"
    outside.write_text("no debe leerse", encoding="utf-8")
    (vault / "link.md").symlink_to(outside)

    with pytest.raises(paths.VaultPathError):
        paths.validate_vault_path("link.md", vault, must_exist=True)


def test_empty_path_is_rejected(tmp_path: Path) -> None:
    """Ruta vacía no es una ruta: error de validación, no una lectura del vault entero."""
    vault = _vault(tmp_path)

    with pytest.raises(paths.VaultPathError):
        paths.validate_vault_path("   ", vault, must_exist=False)


# --- existencia y tipo (D64) ----------------------------------------------------


def test_missing_path_reports_exists_false_with_suggestions_and_vault_dirs(
    tmp_path: Path,
) -> None:
    """Inexistente ⇒ `details: {requested, exists: false, suggestions[], vault_dirs[]}`."""
    vault = _vault(tmp_path)

    with pytest.raises(paths.VaultPathError) as excinfo:
        paths.validate_vault_path("Documentos/informe.docx", vault, must_exist=True)

    details = excinfo.value.details
    assert details is not None
    assert details["requested"] == "Documentos/informe.docx"
    assert details["exists"] is False
    assert details["suggestions"] == ["documentos"], "sugerencia case-insensitive, nombre REAL"
    assert details["vault_dirs"] == ["00-resources", "documentos", "materiales"]


def test_missing_parent_of_a_destination_is_a_validation_error(tmp_path: Path) -> None:
    """El padre del destino debe existir y ser directorio (D64), antes de escribir."""
    vault = _vault(tmp_path)

    with pytest.raises(paths.VaultPathError) as excinfo:
        paths.validate_vault_path("00-resources/fuentes/x.md", vault, must_exist=False)

    details = excinfo.value.details
    assert details is not None
    assert details["exists"] is False
    assert "suggestions" in details and "vault_dirs" in details


def test_wrong_type_reports_expected_and_found(tmp_path: Path) -> None:
    """Tipo equivocado ⇒ `{requested, exists: true, expected, found}`."""
    vault = _vault(tmp_path)
    (vault / "00-resources" / "nota.md").write_text("x", encoding="utf-8")

    with pytest.raises(paths.VaultPathError) as excinfo:
        paths.validate_vault_path("00-resources/nota.md/sub.md", vault, must_exist=False)

    assert excinfo.value.details == {
        "requested": "00-resources/nota.md/sub.md",
        "exists": True,
        "expected": "directory",
        "found": "file",
    }


def test_expect_file_on_a_directory_is_a_validation_error(tmp_path: Path) -> None:
    """`expect` declara el tipo del borde: un directorio donde un documento ⇒ error."""
    vault = _vault(tmp_path)

    with pytest.raises(paths.VaultPathError) as excinfo:
        paths.validate_vault_path("documentos", vault, must_exist=True, expect="file")

    assert excinfo.value.details == {
        "requested": "documentos",
        "exists": True,
        "expected": "file",
        "found": "directory",
    }


# --- vault_dirs (D67, reutilizado por rag_status en T8) --------------------------


def test_vault_dirs_lists_non_dotted_top_level_directories(tmp_path: Path) -> None:
    """Primer nivel, ordenado, sin los de punto (`.tepochcalli/`, `.obsidian/`…)."""
    vault = _vault(tmp_path)

    assert paths.vault_dirs(vault) == ("00-resources", "documentos", "materiales")


def test_vault_dirs_of_a_missing_vault_is_empty(tmp_path: Path) -> None:
    """Vault ausente ⇒ lista vacía (T8 reporta `available_roots: []`, no INTERNAL)."""
    assert paths.vault_dirs(tmp_path / "no-existe") == ()


# --- validate_roots (D44/D65) ----------------------------------------------------


def test_missing_directories_defaults_to_resources(tmp_path: Path) -> None:
    """`None` y lista vacía ⇒ `("00-resources",)` (D42: el default del producto)."""
    vault = _vault(tmp_path)

    assert paths.validate_roots(None, vault) == ("00-resources",)
    assert paths.validate_roots([], vault) == ("00-resources",)


def test_existing_roots_are_returned_normalized_in_order(tmp_path: Path) -> None:
    """N raíces válidas (carpetas y un fichero suelto, D46) ⇒ tupla relativa al vault."""
    vault = _vault(tmp_path)

    roots = paths.validate_roots(["documentos/", "materiales", "documentos/informe.docx"], vault)

    assert roots == ("documentos", "materiales", "documentos/informe.docx")


def test_one_bad_root_among_three_is_fail_fast_atomic(tmp_path: Path) -> None:
    """D65: 1 raíz mala entre 3 ⇒ error que NOMBRA la mala; no se devuelve ninguna."""
    vault = _vault(tmp_path)

    with pytest.raises(paths.VaultPathError) as excinfo:
        paths.validate_roots(["00-resources", "Documentos", "materiales"], vault)

    details = excinfo.value.details
    assert "Documentos" in str(excinfo.value)
    assert details is not None
    assert details["requested"] == "Documentos"
    assert details["exists"] is False
    assert details["suggestions"] == ["documentos"]
    assert details["vault_dirs"] == ["00-resources", "documentos", "materiales"]


def test_a_root_outside_the_vault_is_rejected(tmp_path: Path) -> None:
    """Mismas reglas que la entrada: `..` y absolutas externas no son raíces (D31)."""
    vault = _vault(tmp_path)

    with pytest.raises(paths.VaultPathError):
        paths.validate_roots(["../fuera"], vault)


def test_the_vault_itself_is_not_a_root(tmp_path: Path) -> None:
    """`.` no es una raíz: el índice razona por carpetas, no por el vault entero (D67)."""
    vault = _vault(tmp_path)

    with pytest.raises(paths.VaultPathError, match="vault entero"):
        paths.validate_roots(["."], vault)
