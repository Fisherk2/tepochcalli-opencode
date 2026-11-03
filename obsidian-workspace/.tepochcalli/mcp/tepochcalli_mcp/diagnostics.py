"""Diagnóstico de configuración del server: problemas visibles en la primera llamada.

Hoy una clave mal escrita en `opencode.json` → `environment` se ignoraba en
silencio y un `INDEXER_DIR` inexistente solo estallaba al indexar; `rag_status`
publicaba `config.valid: true`. Este módulo hace visible el error SIN indexar:
`config_problems` revisa el entorno de la config (raíz contractual, cada raíz de
`Config.indexer_roots`, `TEPOCHCALLI_TOP_K`) y `unknown_env` caza nombres que
PARECEN nuestros y no lo son (`INDEXER_DRI`, `TEPOCHALLI_ROOT`…).

Los mensajes son cortos (≤80 chars) y planos: el bloque `config` de
`rag_status` tiene un presupuesto de <200 tokens (spec-mcp-server §Presupuesto).
El tope de 3 elementos —el último es `… y N más`— evita que una config muy rota
hinche el payload; el contador sale del propio `len`, sin claves nuevas.

Reutiliza `paths.validate_vault_path` (misma frontera B′ que `index_refresh`):
aquí se recogen TODAS las raíces malas, no solo la primera — el borde de
`index_refresh` es fail-fast por diseño (D65), esto es diagnóstico.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from tepochcalli_flow.config import TOP_K_ENV, Config

from tepochcalli_mcp import budget, paths

PROBLEM_LIMIT: Final = 3
"""Máximo de elementos por lista (el último es el contador `… y N más`)."""

_CONTRACT_ROOT_ENV: Final = "TEPOCHCALLI_ROOT"
"""Nombre de la raíz del vault en el contrato MCP (`opencode.json` → `environment`)."""

KNOWN_ENV: Final = frozenset(
    {
        _CONTRACT_ROOT_ENV,
        "TEPOCHCALLI_VAULT_ROOT",  # nombre del flow (traducido por `_vault_root`)
        "INDEXER_DIR",
        TOP_K_ENV,
        "TEPOCHCALLI_EMBED_API_KEY",  # default de `EmbeddingConfig.api_key_env`
    }
)
"""Variables que el sistema SÍ lee; `unknown_env` no las reporta."""


def config_problems(config: Config, vault_root: Path) -> tuple[str, ...]:
    """Problemas de configuración visibles en `rag_status.config.problems`.

    Orden: raíz contractual, cada raíz de `INDEXER_DIR`, default de `top_k`.
    `TEPOCHCALLI_ROOT` solo se juzga si está presente (sin él el vault es el
    cwd del harness); una raíz que es un FICHERO es válida (D46). Tope 3.
    """
    problems: list[str] = []
    contract_root = os.environ.get(_CONTRACT_ROOT_ENV)
    if contract_root is not None and not Path(contract_root).is_dir():
        problems.append(f"TEPOCHCALLI_ROOT: {contract_root!r} no existe o no es un directorio")
    for root in config.indexer_roots:
        try:
            paths.validate_vault_path(root, vault_root, must_exist=True)
        except paths.VaultPathError as exc:
            problems.append(_root_problem(root, exc))
    top_k = os.environ.get(TOP_K_ENV)
    if top_k is not None:
        try:
            value: int | None = int(top_k.strip())
        except ValueError:
            value = None
        if value is None or value < budget.TOP_K_MIN:
            problems.append(f"TEPOCHCALLI_TOP_K: {top_k!r} no es un entero > 0 (se usa 5)")
        elif value > budget.TOP_K_MAX:
            problems.append(
                f"TEPOCHCALLI_TOP_K: {top_k!r} fuera de "
                f"[{budget.TOP_K_MIN},{budget.TOP_K_MAX}] (se usa 5)"
            )
    return _capped(problems)


def unknown_env(environ: Mapping[str, str]) -> tuple[str, ...]:
    """Nombres que PARECEN nuestras variables y no están en `KNOWN_ENV`.

    Puro: recibe el mapping (no lee `os.environ`) para que el test fije el
    entorno. Criterio: empieza por `TEPOCH` —cubre `TEPOCHCALLI_` y el typo
    `TEPOCHALLI_`, que es justo el que se cuela— o contiene `INDEXER`
    (case-insensitive). Orden alfabético y tope 3.
    """
    suspects = sorted(
        name
        for name in environ
        if name not in KNOWN_ENV and (name.startswith("TEPOCH") or "INDEXER" in name.upper())
    )
    return _capped(suspects)


def _root_problem(root: str, exc: paths.VaultPathError) -> str:
    """Mensaje corto de una raíz rechazada, con la sugerencia si la hay (D64)."""
    details = exc.details or {}
    if details.get("exists") is False:
        suggestions = details.get("suggestions")
        first = suggestions[0] if isinstance(suggestions, list) and suggestions else None
        hint = f" (¿{first!r}?)" if first is not None else ""
        return f"INDEXER_DIR: {root!r} no existe{hint}"
    return f"INDEXER_DIR: fuera del vault: {root!r}"


def _capped(messages: list[str]) -> tuple[str, ...]:
    """Recorta a `PROBLEM_LIMIT`; con más, el último elemento cuenta el resto."""
    if len(messages) <= PROBLEM_LIMIT:
        return tuple(messages)
    return (*messages[: PROBLEM_LIMIT - 1], f"… y {len(messages) - (PROBLEM_LIMIT - 1)} más")
