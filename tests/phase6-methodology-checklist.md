# Checklist — corrida D9 (Phase 6)

> Copia este fichero a `tests/evidence/phase6/checklist.md` y rellénalo durante la corrida.
> Las columnas mecánicas (bandeja, frontmatter, MCP-first, contaminación) las confirma
> `tests/e2e/verify_methodology_evidence.py`; **Veredicto QA** y las observaciones son del humano.
> Marca `S`/`N`; lo no ejecutado se escribe `NO EJECUTADO`, nunca `ok`.

| # | Comando | Agente | Bandeja | Frontmatter | Gate vigente | MCP-first | Sin contaminación | Veredicto QA | Evidencia |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `/rubric` | nezahualcoyotl | `01-tasks/` | command/agent/date | Phase 0/1 con `question`; una sola rúbrica | | | | `01-rubric-transcript.txt` |
| 2 | `/research` | pochteca | `01-tasks/research/` | agent/timestamp/source/method/origin | `origin` serializado; 4 estados | | | | `02-research-transcript.txt` |
| 3 | `/validate` | chilam | `04-review/` | command/agent/target_doc/verdict | 4 fases; 4 clases; `ok` imposible con `no_anchor`/`no_citation` | | | | `03-validate-transcript.txt` |
| 4 | `/synthesize` | nezahualcoyotl | `01-tasks/` | command/agent/phase/date | Pre-Flight de verdicts; 3–6 ejes; cero prosa | | | | `04-synthesize-transcript.txt` |
| 5 | `/cite` | chilam | `03-citations/` | command/agent/style/date | gate determinista sin red; cero salida parcial | | | | `05-cite-transcript.txt` |
| 6 | `/draft` | tlacuilo | `02-drafts/` | command/agent/outline/date | 3 insumos; sin navegación nueva | | | | `06-draft-transcript.txt` |
| 7 | `/review` | chilam | `02-drafts/` | command/agent/source/rev | no edita hasta confirmar; rev determinista | | | | `07-review-transcript.txt` |
| 8 | `/transform` | tlacuilo | `05-outputs/` | command/agent/source_draft/formats/date | menú A–G; `list_formats` antes de prometer | | | | `08-transform-transcript.txt` |
| 9 | `/update` | tlacuilo | `02-drafts/` | command/agent/date/revision_note | quirúrgico; 1 de 3 scopes | | | | `09-update-transcript.txt` |

## Observaciones

- **MCP-first:** `S` si el transcript muestra `search` de `tepochcalli-rag` antes de leer crudo
  `00-resources/` (o si no hubo lectura cruda).
- **Sin contaminación:** `S` si no aparece escritura en bandeja ajena ni edición del material del
  usuario en `01-…-05-…`.
- **Evidencia:** enlaza el fichero del transcript; si el hallazgo no es mecánico, cita la línea o
  el fragmento exacto.

```text
Observaciones libres:
- ...
Veredicto global: OK | OK CON AVISOS | RECHAZADO | NO EJECUTADO
Motivo (si no es OK):
```
