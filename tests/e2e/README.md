# Tests E2E (end-to-end)

Reservado para **smoke tests de extremo a extremo**: payload instalado, consulta
citada de punta a punta y vault dorado de Phase 5/D9. Hoy está **intencionalmente
vacío**: el nivel E2E se activará cuando exista el payload materializado que
ejercitar.

## Contexto

La pirámide de tests se repartió el **2026-10-23**:

- `tests/unit/`: lógica pura. **No** toca modelos ni base de datos (sin
  `models/` ni `db/`, sin red).
- `tests/integration/`: cruza fronteras reales (LanceDB, Docling) pero **sin
  red**.
- `tests/e2e/`: flujos completos sobre el payload instalado; se poblará en
  fases posteriores.
- `tests/benchmarks/`: `bench_delta.py` (script de medición, no suite de
  corrección).

Los fixtures compartidos viven en `tests/fixtures/` y el helper
`model_cache.py` en la raíz de `tests/`.
