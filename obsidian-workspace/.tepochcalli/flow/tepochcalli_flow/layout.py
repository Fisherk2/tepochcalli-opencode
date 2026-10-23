"""Layout del runtime `.tepochcalli/` — ruta ÚNICA de verdad para app/reader/verify (D11).

Constantes de layout compartidas: antes vivían duplicadas en `app`, el adaptador
y `verify` con docstrings cross-module («sin importar app», «mismo relativo»).
Un solo módulo sin motor --std diseño en spec-vault-structure.md-- del que
apuntan write-path, read-path, verificador y tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

DB_RELPATH: Final = Path(".tepochcalli/db/tepochcalli.lance")
"""Base LanceDB embebida bajo el vault (ADR-002; spec-rag-engine §Target)."""

TABLE_NAME: Final = "chunks"
"""Tabla única del índice (spec-rag-engine §Target LanceDB + índices)."""

ENGINE_STATE_RELPATH: Final = Path(".tepochcalli/db/cocoindex")
"""Estado derivado del engine (D14): bajo `db/`, gitignored, junto a LanceDB.

Co-localizado con `DB_RELPATH` para que un solo `rm -r .tepochcalli/db/` —la
promesa de spec-rag-engine §Rollback— reconstruya LanceDB y el estado del
engine a la vez; jamás en `flow/`, que es código fuente versionado
(spec-vault-structure §gitignore).
"""

LOCK_RELPATH: Final = Path(".tepochcalli/db/refresh.lock")
"""Lock file del refresh bajo `.tepochcalli/db/` — decisión deliberada T8 (T2, D14).

* **Ubicación:** `db/` es el artefacto gitignored que el refresh PROTEGE
  (LanceDB + estado del engine): candado junto a lo que muta, sin ensuciar
  `git status` y limpiado por el mismo `rm -r .tepochcalli/db/` del rollback.
* **El candado NO es el archivo: es el lock exclusivo del SO sobre él.** El
  kernel lo libera aunque el proceso muera con SIGKILL, así que UN CRASH NO
  PUEDE DEJAR UN CANDADO RETENIDO. Un lock file residual (p. ej. con el pid de
  un proceso muerto) es inofensivo: no retiene lock alguno y la siguiente
  pasada lo reutiliza — jamás se borra, porque el par `unlink`/`create`
  introduce carreras entre adquirentes.
* Segunda invocación concurrente ⇒ el lock falla ⇒ `RefreshReport(...,
  locked=True)` SIN arrancar update: cierra el doble-write que ADR-002 §6
  acepta como riesgo.
* Rama POSIX (`fcntl.flock`) + rama Windows (`msvcrt.locking`, ADR-003); la
  win32 no tiene cobertura en la CI de fase 1 (solo se prueba el flock real).
"""
