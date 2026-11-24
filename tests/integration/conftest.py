"""Fixtures compartidas de los tests de integración (P0-1, 2026-11-16).

El vault ADVERSARIO (dorada + cjk + denso + PDF tabular) se indexa UNA vez por
SESIÓN y lo consumen `test_mcp_budget_adversarial` (T7) y
`test_mcp_token_budget` (T6): antes cada módulo construía su propio índice
sobre el mismo contenido — dos indexaciones en subproceso de ~50 s cada una.

Por qué vive el builder AQUÍ y no como fixture importado entre módulos: un
fixture importado en otro módulo registra un `FixtureDef` POR MÓDULO
(`_pytest/fixtures.py::_register_fixture`, sin dedupe por función) y correría
dos veces aunque diga `scope="session"`. Solo conftest registra UN
`FixtureDef` con nodo en este directorio, visible por igual para todos los
módulos hijos.

Los helpers que el builder usa (`TABLE_PDF`, `_dense_content`, `_cjk_content`)
se importan desde el módulo de T7: acíclico (T7 no importa este conftest) y
`test_*.py` entra en el patrón de reescritura de aserciones de pytest, así que
los asserts de T7 siguen con mensajes detallados.
"""

from __future__ import annotations

import shutil

import pytest
from support.mcp_server import index_vault
from tepochcalli_flow import citation
from test_mcp_budget_adversarial import TABLE_PDF, _cjk_content, _dense_content
from test_mcp_search import FIXTURE_VAULT, IndexedVault


@pytest.fixture(scope="session")
def adversarial_vault(tmp_path_factory: pytest.TempPathFactory) -> IndexedVault:
    """Vault adverso indexado UNA vez por sesión — lo comparten T7 y T6 (P0-1).

    Indexación SIEMPRE en subproceso con env canónica (patrón T2): el
    environment global de cocoindex no admite dos vaults en el proceso padre.
    Ambos módulos SOLO leen el índice (búsqueda + filas), cada uno con su
    propio `_backend_on` módulo-scoped — el índice compartido no muta.
    """
    vault = tmp_path_factory.mktemp("vault-t7-adversarial")
    shutil.copytree(FIXTURE_VAULT, vault, dirs_exist_ok=True)
    resources = vault / citation.RESOURCES_DIR
    (resources / "cjk.md").write_text(_cjk_content(), encoding="utf-8")
    (resources / "denso.md").write_text(_dense_content(), encoding="utf-8")
    shutil.copy(TABLE_PDF, resources / "tablas.pdf")

    models_link = index_vault(vault)
    return IndexedVault(vault=vault, model_cache=models_link)
