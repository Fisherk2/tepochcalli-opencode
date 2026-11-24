"""Adaptadores de infraestructura del flow — ES código de infraestructura (T9).

`tepochcalli_flow.adapters` implementa los puertos de `tepochcalli_flow.ports`
concreto el almacén real (LanceDB, ADR-002/005). A diferencia del puerto, ESTE
paquete SÍ importa `lancedb`: la frontera hexagonal corre entre `ports.py` (sin
motor) y aquí (con motor) — el test de arquitectura de CP-B la verifica en
ambas direcciones.

Importar este paquete NO arranca nada: `__init__.py` está vacío a propósito
los adaptadores se importan por su submódulo (p. ej.
`tepochcalli_flow.adapters.lancedb_reader`).
"""
