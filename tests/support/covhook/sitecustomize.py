"""Arranca coverage en CUALQUIER proceso si COVERAGE_PROCESS_START está definido.

El flow ejecuta `refresh_blocking()` y el CLI `python -m tepochcalli_flow.verify`
en subprocesos (`subprocess.run([sys.executable, ...])`). pytest-cov solo mide el
padre, así que sin este hook verify.py aparece al 0 % y app.py al 74 % — cifras
falsas, no deuda. Patrón documentado por coverage para subprocesos.
"""

from __future__ import annotations

import os

if os.environ.get("COVERAGE_PROCESS_START"):
    import coverage

    coverage.process_startup()
