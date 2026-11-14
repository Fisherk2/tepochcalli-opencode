"""Guarda de la metadata de publicación del crate `tepochcalli`.

Por qué existe: crates.io **rechaza** el `cargo publish` si el manifiesto no
declara `description`, `license`/`license-file`, `repository` y `readme` (y
exige 1..=5 `keywords` con `categories` válidas del catálogo), y
`cargo binstall` **no encuentra el asset** si el `pkg-url` no apunta al tag
real de la release (`tepochcalli-v<version>`, fijado por
`.github/workflows/release.yml`) ni al nombre que produce cargo-dist
(`tepochcalli-<target>.tar.gz|.zip`). Los tres fallos solo se ven al publicar,
tarde y en público: este test los adelanta a la suite.

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
    """`name` y ruta deben coincidir o binstall no encuentra el crate."""
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


def test_binstall_pkg_url_matches_release_tag_and_asset_names() -> None:
    """El `pkg-url` debe casar con el tag y el nombre de asset publicados."""
    pkg_url = _package()["metadata"]["binstall"]["pkg-url"]

    # Tag real de la release (`release.yml`): binstall solo prueba `<version>` y
    # `v<version>` por defecto, así que el tag con prefijo exige `pkg-url` explícito.
    assert "tepochcalli-v{ version }" in pkg_url
    # Asset de cargo-dist: `tepochcalli-<target>.tar.gz` / `.zip`.
    assert "{ name }-{ target }" in pkg_url
