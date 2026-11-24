"""Bootstrap de la suite Tepochcalli.

Los tests importan el helper compartido como modulo de primer nivel
(`from model_cache import ...`). Con el import mode `prepend` de pytest solo
se anade el directorio del propio fichero de test a sys.path, asi que al
repartir la suite en unit/ e integration/ el helper dejaria de resolverse.
Este conftest se carga antes de recolectar cualquier subdirectorio y deja
`tests/` en el path una sola vez.
"""

from __future__ import annotations

import sys
from pathlib import Path

_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)
