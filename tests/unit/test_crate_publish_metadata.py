"""Guarda de la metadata de publicación del crate `tepochcalli`.

Por qué existe: crates.io **rechaza** el `cargo publish` si el manifiesto no
declara `description`, `license`/`license-file`, `repository` y `readme` (y
exige 1..=5 `keywords` con `categories` válidas del catálogo). Ese fallo solo
se ve al publicar, tarde y en público: este test lo adelanta a la suite.
El canal del wizard es la rueda `uvx tepochcalli` (ADR-014); la metadata
`cargo binstall` que exigía el canal retirado de ADR-013 ya no existe.

Solo stdlib (`tomllib`): el manifiesto se lee como dato, sin invocar `cargo`.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

CRATE_DIR = Path(__file__).resolve().parents[2] / "crates" / "tepochcalli"
MANIFEST = CRATE_DIR / "Cargo.toml"

# Campos que crates.io exige (más los que la ficha del crate necesita para ser
# útil): sin ellos el índice rechaza el publish con `missing or empty metadata`.
REQUIRED_FIELDS = (
    "description",
    "license",
    "repository",
    "homepage",
    "readme",
    "keywords",
    "categories",
)


def _package() -> dict[str, Any]:
    with MANIFEST.open("rb") as handle:
        return tomllib.load(handle)["package"]


def test_package_declares_crates_io_metadata() -> None:
    """Sin estos campos el índice de crates.io rechaza el publish."""
    package = _package()

    missing = [field for field in REQUIRED_FIELDS if not package.get(field)]
    assert not missing, f"{MANIFEST} sin campos obligatorios para publicar: {missing}"

    assert package["license"] == "MIT"
    assert 1 <= len(package["keywords"]) <= 5, "crates.io acepta entre 1 y 5 keywords"


def test_package_name_matches_crate_directory() -> None:
    """`name` y ruta deben coincidir (cargo publica el crate con ese nombre)."""
    assert _package()["name"] == CRATE_DIR.name == "tepochcalli"


def test_readme_path_resolves() -> None:
    """El `readme` declarado debe existir (es lo que renderiza crates.io)."""
    readme = CRATE_DIR / _package()["readme"]

    assert readme.is_file(), f"readme del crate inexistente: {readme}"


def test_package_excludes_integration_tests() -> None:
    """Los tests de integración no viajan en el `.crate`."""
    assert "tests/" in _package().get("exclude", []), (
        "el .crate debe excluir tests/: cargo install no los usa y duplican el paquete"
    )
