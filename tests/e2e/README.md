# Tests E2E (end-to-end)

Nivel E2E de la pirámide: **proceso real de punta a punta** — el server MCP
`tepochcalli_mcp` lanzado por stdio con el cliente del SDK, vault indexado de
verdad y el contrato afirmado donde lo ve el harness. Poblado en **T8**
(Phase 2, gate CP-D); antes estaba intencionalmente vacío.

| Fichero | Qué gradúa |
|---|---|
| `test_mcp_contract.py` | Contract tests D7.3: shape exacto (claves y orden) de las 4 tools request/response en el wire; errores `is_error` + JSON canónico; los 5 `E_*` con escenarios REALES (config `none`, litellm sin clave, modelo ajeno, cache vacío offline/inválido); `rag_status` 4 bloques + <200 tokens; `path_filter` globs válidos e inválidos |
| `test_mcp_journey.py` | e2e «pregunta → tool-call → JSON citado» sobre el vault golden **grabado** (`tests/fixtures/golden_vault/`, md + PDF): `source_path` real, `heading` y offsets reproducibles — slice del original en md, `offsets_ref == "extract"` en PDF |
| `test_phase35_bulk.py` | **`slow`** (T13): 21 conversiones reales (20 familias + bulk de 1 000 páginas ≥1 MB generado en el test) con resumen-only y presupuesto por respuesta y por suma; re-medición del motor (Δ p95 n=20 nearest-rank sobre raíces múltiples, citas al 100 %, RSS `VmHWM`, coste de documentos aparte — D51) y venv medido (`du` + `*.dist-info`). Solo `just python-test-slow` |

## Contexto

La pirámide de tests se repartió el **2026-10-23**:

- `tests/unit/`: lógica pura. **No** toca modelos ni base de datos (sin
  `models/` ni `db/`, sin red).
- `tests/integration/`: cruza fronteras reales (LanceDB, Docling) pero **sin
  red**.
- `tests/e2e`: procesos completos por stdio con el cliente del SDK (T8+);
  los fixtures viven en `tests/fixtures/` y los ayudantes compartidos del
  server (`running_server`, `server_env`, `index_vault`, `wire_payload`) en
  `tests/support/mcp_server.py`.
- `tests/benchmarks/`: `bench_delta.py` y `bench_search.py` (scripts de
  medición, no suite de corrección).

Los fixtures compartidos viven en `tests/fixtures/` y el helper
`model_cache.py` en la raíz de `tests/`.

## Ejecución

```bash
cd obsidian-workspace/.tepochcalli
uv run python -m pytest ../../tests/e2e -v   # AC de verificación de T8
```

Los e2e cuestan lo que cuesta el mundo real (indexado + Docling + carga de
modelo por hijo ≈ 5 min en el host de desarrollo): por eso NO repiten aquí lo
que ya gradúan unit (`E_*` por código) e integración (shapes por módulo) —
solo el wire y el viaje golden. La latencia jamás se aserta aquí
(regla anti-flake): se mide en `tests/benchmarks/bench_search.py`.
