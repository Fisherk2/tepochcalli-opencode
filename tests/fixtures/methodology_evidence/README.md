# Evidencia sintética — verificador de la corrida D9 (T14)

Estos directorios **no son una corrida real** (D-P6-2): son el juego de prueba del
verificador `tests/e2e/verify_methodology_evidence.py`, ejecutado por
`tests/e2e/test_methodology_evidence.py`.

- `good/` — debe dar **exit 0**.
- `bad-tray/` — el artefacto de `/rubric` aparece en `02-drafts/` (bandeja ajena).
- `bad-frontmatter/` — el artefacto de `/cite` pierde el campo `style`.
- `bad-transcript/` — falta el transcript de `/review`.
- `bad-mcp-first/` — el transcript de `/draft` lee crudo `00-resources/` antes del `search`.

Cada defecto debe dar **exit ≠ 0** y un `FAIL (a|b|c|d)` que nombre el fichero.
