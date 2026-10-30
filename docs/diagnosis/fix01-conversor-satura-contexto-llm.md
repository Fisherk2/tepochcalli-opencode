# Diagnosis: El conversor devuelve el documento completo al LLM y satura la ventana de contexto

**Issue:** local (reporte del dueño, 2026-10-30) — sin issue remoto
**Date:** 2026-10-30
**Severity:** high
**Status:** diagnosed

---

## Summary

Al convertir un documento grande con la tool `convert_to_markdown` del MCP standalone
`markitdown` (registrado y **habilitado** en el payload `opencode.json:111-116` para testing,
commit `31cfe34`), el contenido íntegro del documento viaja por el wire como texto de la
respuesta de la tool y queda en la ventana de contexto del agente; con documentos pequeños el
agente lo re-escribe a mano sin daño visible, pero con documentos grandes (p. ej. 1000 páginas)
el contexto se satura y la sesión degenera. El conversor es una **herramienta**: debe leer el
documento, convertirlo y escribirlo a disco él mismo, devolviendo al LLM únicamente un resumen
de la operación — nunca el contenido convertido. La regla ya está codificada como objetivo en
las historias H1/H2 de [docs/UH.md](../UH.md) (anexo 2026-10-30) y en el diseño `add_source`
(D-b), que hoy es el único camino que la cumple.

## Symptoms

- Documento de 1 página: conversión funciona; el agente escribe el output a mano — costoso pero invisible.
- Documento grande (reporte del dueño: «si le paso un documento de 1000 páginas se satura»): la ventana de contexto del LLM se llena con el markdown íntegro devuelto por la tool; el agente intenta re-escribirlo por partes o la sesión se degrada.
- No hay error ni stack trace: el fallo es de presupuesto, no de excepción — viola directamente el criterio 4 de docs/UH.md (≤2000 tokens/consulta) y la disciplina de token-budget de [spec-mcp-server](../../specs/spec-mcp-server.md).
- Contradicción de estado en el repo: [spec-markitdown.md:58](../../specs/spec-markitdown.md) declara el standalone «retirado» (2026-10-27), pero el payload lo tiene `disabled: false` (`31cfe34`, testing en vivo autorizado por el dueño, decisión revertir-vs-consolidar explícitamente pendiente).

## Root Cause

El contrato de la tool standalone devuelve el artefacto completo como contenido de respuesta:
`convert_to_markdown(uri) -> markdown completo` vía `content[0].text`. El agente, sin otra vía
prevista, es el encargado de materializar el archivo a disco — por lo que el contenido cruza el
wire dos veces (LLM→contexto, LLM→escritura) y escala O(tamaño documento) en tokens.

> ¿Por qué el MVC de contratos no lo impide? → La misma clase de defecto se corrigió en Phase 2
> para `search` (presupuesto 1600 tokens, truncado) y para `add_source` (conversión D-b
> **en proceso**: el server convierte y escribe, y solo `{written_to, indexed}` cruza el wire —
> spec-markitdown §65-74). El standalone sobrevivió como «testing» sin esa disciplina, y nada
> en el wire o en el AGENTS.md del vault **prohíbe** a una tool devolver artefactos completos:
> la regla «el conversor jamás devuelve contenido, solo el resumen» estaba en diseño (H2,
> summary-only) pero sin enforcement ni redacción de contrato al día del conversor objetivo H1.

## Impact

| Dimension | Assessment |
| ----------- | ------------ |
| Users affected | all (cualquier conversión de documento grande) |
| Functionality | degraded (sesión satura; no explota) |
| Data integrity | at risk (escritura del .md a cargo del LLM: alucinación/truncamiento silencioso del contenido) |
| Reproducibility | always (determinista por tamaño de documento) |

Criterios UH tocados: **4** (tokens/consulta) degradado en conversiones grandes; **7** (multi-formato) funciona pero sin presupuesto.

## Environment

- **Platform:** payload `obsidian-workspace/`, harness OpenCode V2
- **Version:** commit `31cfe34` (2026-10-30) — entrada `markitdown` standalone habilitada para testing
- **Configuration:** `opencode.json:111-116` — `command: [python -m markitdown_mcp]`, `disabled: false`; `anydoc` presente pero `disabled: true`

## Proposed Solution

(Caminos de fix — la implementación pertenece al plan de **Phase 3.5**; salidas en action `/plan`.)

1. **Cerrar la pugna revert-vs-consolidar** (abierta en `31cfe34`): retirar (o `disabled: true`) la entrada standalone `markitdown` del payload — el camino single-consumer de conversión es vía conversor objetivo H1 / `add_source` (D-b); el standalone es superficie de ataque sin cliente y sin presupuesto (análoga a la razón de su retirada original, spec-markitdown.md:58) + test `MANAGED_KEYS` inconsistente.
2. **Aterrizar H1+H2 como el conversor de proyecto** (target de las historias anexadas): tools `convert_document(path[, output_path, format])`, `convert_base64`, `list_formats` con semántica de la skill `local-doc-to-markdown`; el MCP escribe a disco vía `output_path` (bulk incluido) y el wire solo junta un resumen `{written_to, source_uri, bytes/chars, preview ≤500, truncated}` (~200 tokens) — **regla de oro: ninguna tool del conversor devuelve el artefacto convertido al LLM**.
3. **Enforzar la regla en contrato y tests:** el shape de respuesta del conversor (resumen-only) se fija en spec (ampliación de spec-markitdown + contract tests del estilo de `test_mcp_contract.py`; cualquier parcial o markdown íntegro por el wire ⇒ test rojo), y el fallback anydoc (motor Rust, para cuando el conversor de proyecto no cubra el formato) queda evaluate bajo la MISMA disciplina de devolución.
4. **Ampliar a la skill `tepochcalli-mcp` (H4)** el workflow de decisión del agente: cuando el usuario pida «convierte X», el agente invoca la tool del MCP (que escribe a disco) y confirma con la ruta — jamás interpreta/re-emite el contenido; tabla de catálogo único de tools descrita en H4.
5. **Atender también el lado del contenido en contexto de tercera vía:** documentos añadidos al vault como fuentes indexables pasan por `add_source` (ya resumen-only); ningún camino nuevo de conversión debe reabrir el wire.

## Workarounds

> ⚠️ **WORKAROUND** (hasta Phase 3.5)
> Para materiales destinados a indexación usar `add_source` del server `tepochcalli-rag` (conversión en proceso, escribe a disco, resumen en el wire).
> Para conversiones cuyo destino no sea `00-Resources/`: evitar pasar documentos grandes por el standalone `markitdown` de testing; usar la skill `local-doc-to-markdown` fuera de la sesión del agente (conversión local, contenido nunca entra en contexto).

## Recurrences

| Date | Similar Issue | Variation |
| --- | --- | --- |
| 2026-10-30 | Este diagnóstico (standalone `markitdown` testing) | Saturación por devolución de artefacto completo |
| 2026-10-27 | Retirada del standalone markitdown (review Phase 2, spec-markitdown.md:58) | Misma raíz (superficie sin cliente) detectada por review, no por síntoma |
_Patrón 2/3: si la skill anydoc-fallback se integra sin devolución resumen, cierra la terna — sugerir un contract test transversal tipo «ninguna tool devuelve artefacto >N bytes»._

## References

- Anexo H1–H4 (conversor + skill + summary-only): [docs/UH.md](../UH.md) §Historias de conversión
- Contrato de conversión en proceso (D-b, el camino que ya cumple la regla): [specs/spec-markitdown.md](../../specs/spec-markitdown.md) §Conversión en proceso
- Retirada original del standalone + config payload: [spec-markitdown.md:58](../../specs/spec-markitdown.md)
- Entry del payload habilitada para testing (contradicción con la spec): `obsidian-workspace/opencode.json:111-116`, commit `31cfe34`
- Presupuesto de tokens y disciplinas del wire: [specs/spec-mcp-server.md](../../specs/spec-mcp-server.md)
- Depure de peso del venv (relacionada, el peso sobra si se retira el standalone): TD-12 en [docs/TECH_DEBT.md](../TECH_DEBT.md)

---

_Diagnosis created by `/diagnosis`. Update this file if the fix reveals additional insights._
