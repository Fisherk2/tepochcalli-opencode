# Checklist D9 — ejemplo sintético

| # | Comando | Agente | Bandeja | Frontmatter | Gate vigente | MCP-first | Sin contaminación | Veredicto QA | Evidencia |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `/rubric` | nezahualcoyotl | `01-tasks/` | command/agent/date | Phase 0 con `question` | S | S | ok | `01-rubric-transcript.txt` |
| 2 | `/research` | pochteca | `01-tasks/research/` | agent/timestamp/source/method/origin | origin serializado (4 estados) | S | S | ok | `02-research-transcript.txt` |
| 3 | `/validate` | chilam | `04-review/` | command/agent/target_doc/verdict | 4 fases; 4 clases | S | S | ok | `03-validate-transcript.txt` |
| 4 | `/synthesize` | nezahualcoyotl | `01-tasks/` | command/agent/phase/date | Pre-Flight de evidencia | S | S | ok | `04-synthesize-transcript.txt` |
| 5 | `/cite` | chilam | `03-citations/` | command/agent/style/date | gate sin red | S | S | ok | `05-cite-transcript.txt` |
| 6 | `/draft` | tlacuilo | `02-drafts/` | command/agent/outline/date | 3 insumos | S | S | ok | `06-draft-transcript.txt` |
| 7 | `/review` | chilam | `02-drafts/` | command/agent/source/rev | no edita hasta confirmar | S | S | ok | `07-review-transcript.txt` |
| 8 | `/transform` | tlacuilo | `05-outputs/` | command/agent/source_draft/formats/date | A-G; list_formats antes | S | S | ok | `08-transform-transcript.txt` |
| 9 | `/update` | tlacuilo | `02-drafts/` | command/agent/date/revision_note | quirúrgico (1 de 3 scopes) | S | S | ok | `09-update-transcript.txt` |
