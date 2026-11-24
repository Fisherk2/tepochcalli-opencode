"""Diagnóstico de configuración: problemas visibles en la primera llamada.

Contrato: `config_problems` recoge TODAS las raíces malas (no fail-fast), la
raíz contractual y un `TEPOCHCALLI_TOP_K` inválido; `unknown_env` caza nombres
que parecen nuestras. Ambos topan a 3 elementos con `… y N más`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tepochcalli_flow.config import Config
from tepochcalli_mcp import diagnostics


def _config(*roots: str) -> Config:
    """Config mínima con las raíces dadas (`models_dir` no participa)."""
    return Config(models_dir=Path("/vault/.tepochcalli/models"), indexer_roots=roots)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aísla el diagnóstico de las variables del proceso de test."""
    monkeypatch.delenv("TEPOCHCALLI_ROOT", raising=False)
    monkeypatch.delenv("TEPOCHCALLI_TOP_K", raising=False)


def test_missing_root_suggests_the_closest_existing_dir(tmp_path: Path) -> None:
    """Raíz inexistente con typo: el mensaje propone el nombre real del vault (D64)."""
    (tmp_path / "documentos").mkdir()

    problems = diagnostics.config_problems(_config("Documentos"), tmp_path)

    assert problems == ("INDEXER_DIR: 'Documentos' no existe (¿'documentos'?)",)


def test_root_outside_the_vault_is_named_as_such(tmp_path: Path) -> None:
    """Raíz que escapa del vault ⇒ mensaje de frontera B′ (sin sugerencia)."""
    problems = diagnostics.config_problems(_config("/etc"), tmp_path)

    assert problems == ("INDEXER_DIR: fuera del vault: '/etc'",)


def test_root_that_is_a_file_is_valid(tmp_path: Path) -> None:
    """D46: una raíz puede ser un fichero suelto — no es un problema."""
    (tmp_path / "nota.md").write_text("# nota\n", encoding="utf-8")

    assert diagnostics.config_problems(_config("nota.md"), tmp_path) == ()


def test_every_bad_root_is_reported_and_capped_at_three(tmp_path: Path) -> None:
    """Cuatro raíces malas ⇒ las dos primeras + contador (tope 3, sin claves nuevas)."""
    problems = diagnostics.config_problems(_config("a", "b", "c", "d"), tmp_path)

    assert len(problems) == 3
    assert problems[0] == "INDEXER_DIR: 'a' no existe"
    assert problems[1] == "INDEXER_DIR: 'b' no existe"
    assert problems[2] == "… y 2 más"


def test_missing_contract_root_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`TEPOCHCALLI_ROOT` apuntando a algo inexistente ⇒ problema nombrado."""
    (tmp_path / "00-resources").mkdir()
    monkeypatch.setenv("TEPOCHCALLI_ROOT", "no-existe-xyz")

    problems = diagnostics.config_problems(_config(), tmp_path)

    assert problems == ("TEPOCHCALLI_ROOT: 'no-existe-xyz' no existe o no es un directorio",)


def test_contract_root_that_is_a_file_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`TEPOCHCALLI_ROOT` que existe pero no es directorio ⇒ problema."""
    (tmp_path / "00-resources").mkdir()
    file_root = tmp_path / "vault.md"
    file_root.write_text("no soy un directorio\n", encoding="utf-8")
    monkeypatch.setenv("TEPOCHCALLI_ROOT", str(file_root))

    problems = diagnostics.config_problems(_config(), tmp_path)

    assert problems == (f"TEPOCHCALLI_ROOT: {str(file_root)!r} no existe o no es un directorio",)


@pytest.mark.parametrize("raw", ["cinco", "0", "-3", ""])
def test_invalid_top_k_is_reported(
    raw: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`TEPOCHCALLI_TOP_K` no entero o ≤0 ⇒ mensaje con el default usado (5)."""
    (tmp_path / "00-resources").mkdir()
    monkeypatch.setenv("TEPOCHCALLI_TOP_K", raw)

    problems = diagnostics.config_problems(_config(), tmp_path)

    assert problems == (f"TEPOCHCALLI_TOP_K: {raw!r} fuera de [1,20] (se usa 5)",)


def test_valid_top_k_is_not_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Un `TEPOCHCALLI_TOP_K` válido no genera problema."""
    (tmp_path / "00-resources").mkdir()
    monkeypatch.setenv("TEPOCHCALLI_TOP_K", "8")

    assert diagnostics.config_problems(_config(), tmp_path) == ()


def test_top_k_above_the_contract_range_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`TEPOCHCALLI_TOP_K=21` (entero, pero fuera de [1,20]) ⇒ problema visible.

    Regresión (hueco #4): sin esta entrada el usuario veía su búsqueda rota
    (default 21 ⇒ `VALIDATION_ERROR`) sin ninguna pista en
    `rag_status.config.problems`.
    """
    (tmp_path / "00-resources").mkdir()
    monkeypatch.setenv("TEPOCHCALLI_TOP_K", "21")

    problems = diagnostics.config_problems(_config(), tmp_path)

    assert problems == ("TEPOCHCALLI_TOP_K: '21' fuera de [1,20] (se usa 5)",)


def test_unknown_env_catches_lookalikes_and_spares_known_names() -> None:
    """Caza typos del namespace; no toca PATH/HOME ni las variables del contrato."""
    environ = {
        "INDEXER_DRI": "00-resources",
        "TEPOCHALLI_ROOT": "/vault",
        "TEPOCHALLI_TOPX": "5",
        "PATH": "/usr/bin",
        "HOME": "/home/u",
        "TEPOCHCALLI_EMBED_API_KEY": "k",
        "TEPOCHCALLI_VAULT_ROOT": "/vault",
        "TEPOCHCALLI_ROOT": "/vault",
        "INDEXER_DIR": "00-resources",
        "TEPOCHCALLI_TOP_K": "5",
    }

    assert diagnostics.unknown_env(environ) == (
        "INDEXER_DRI",
        "TEPOCHALLI_ROOT",
        "TEPOCHALLI_TOPX",
    )


def test_unknown_env_is_ordered_and_capped_at_three() -> None:
    """Orden alfabético y tope 3 con contador (`my_indexer_dir` entra por INDEXER)."""
    environ = {
        "TEPOCHALLI_Z": "1",
        "TEPOCHALLI_A": "1",
        "INDEXER_X": "1",
        "my_indexer_dir": "1",
    }

    assert diagnostics.unknown_env(environ) == ("INDEXER_X", "TEPOCHALLI_A", "… y 2 más")
