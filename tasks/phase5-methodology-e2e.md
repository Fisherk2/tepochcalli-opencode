# Phase 5 — Methodology e2e (D9): protocolo y evidencia

> **Fecha:** 2026-11-09 · **Fase:** Phase 5 (gate D9) · **Decisión:** D-P5-3
> **Plan:** [tasks/plan.md](plan.md) §T13 · **Precondición:** [T12](todo.md) (vault instalado)
> **Runbook de QA:** [tests/phase5-methodology-runbook.md](../tests/phase5-methodology-runbook.md)
> **Estado:** protocolo y runbook listos; **corrida pendiente de QA** (sin corrida, la fase queda ABIERTA).

## Por qué manual y no automatizado

D-P5-3: el gate D9 tiene dos piezas. La primera es el **contrato estático automatizado**
(`tests/unit/test_payload_permissions.py` + `tests/unit/test_payload_contract.py`, T11). La
segunda es esta **corrida manual con evidencia**: un LLM real ejecutando los 9 comandos sobre un
vault real. No se automatiza porque el resultado depende del modelo (no determinista) y porque el
criterio es observar el **comportamiento de ruteo y citación**, no comparar bytes.

Regla de honestidad (lección Phase 3.5 (b)): **lo no verificado se escribe como no verificado**.
Ningún "verde" sin su método y su salida.

## Precondiciones

| # | Requisito | Cómo se comprueba |
| --- | --- | --- |
| 1 | Vault instalado por T12 en `/tmp/opencode/phase5-vault` | `ls /tmp/opencode/phase5-vault` |
| 2 | Árbol canónico + 5 agentes + 9 comandos + `AGENTS.md` | checklist de T12 |
| 3 | `opencode.json` con `tepochcalli-rag` (F8) y **sin** array global | `python3 -c "import json;…"` |
| 4 | Corpus mínimo: `00-Resources/ejemplo.md` + `ejemplo.pdf` (muestras del wizard) | `ls /tmp/opencode/phase5-vault/00-Resources` |
| 5 | Índice construido y fresco | `rag_status()` → estado `ok`; si no, `index_refresh()` |
| 6 | Harness OpenCode V2 abierto en el vault | sesión con `itzamna` como `default_agent` |

Si (5) falla, **no se continúa**: se reporta `E_*` crudo y el `fix_hint` de `rag_status()`.

## Orden de la corrida

```text
/rubric → /research → /validate → /synthesize → /cite → /draft → /review → /transform → /update
```

El orden es el del pipeline (`docs/UH.md` líneas 66-76). Cada comando consume la salida del
anterior: `/research` necesita el alcance de `/rubric`; `/cite` necesita las claims validadas;
`/transform` necesita un borrador aceptado; `/update` cierra el ciclo.

## Qué se asserta por comando (checklist de 5 puntos)

(a) **Bandeja única** — el artefacto aterriza SOLO en la bandeja de D9.2 y en ninguna otra.
(b) **Frontmatter exacto** — las claves y sus valores permitidos, sin campos de más ni de menos.
(c) **Cero contaminación cruzada** — ningún comando escribe en la bandeja de otro.
(d) **MCP-first observado** — `search` (`tepochcalli-rag`) antes de cualquier lectura cruda de
    `00-Resources/`; `index_refresh()` si la frescura es dudosa; ante `E_*`, `rag_status()` y su
    `fix_hint` (nunca el error crudo).
(e) **No-contaminación** — si aparecen ficheros del usuario en las bandejas 01-05, el agente
    avisa (WARN) y no los edita.

### Tabla de referencia (contrato de cada comando)

| Comando | Agente | Bandeja | Frontmatter esperado |
| --- | --- | --- | --- |
| `/rubric` | Nezahualcóyotl | `01-tasks/` | `{command, agent, date}` |
| `/research` | Pochteca | `01-tasks/research/` | `{agent, timestamp, fuentes, método, procedencia}` |
| `/validate` | Chilam | `04-review/` | `{command, agent, target_doc, verdict}` |
| `/synthesize` | Nezahualcóyotl | `01-tasks/` | `{command, agent, phase, date}` |
| `/cite` | Chilam | `03-citations/` | `{command, agent, style, date}` |
| `/draft` | Tlacuilo | `02-drafts/` | `{command, agent, outline, date}` |
| `/review` | Chilam | `04-review/` | `{command, agent, target_doc, verdict}` |
| `/transform` | Tlacuilo | `05-outputs/` | `{command, agent, source_draft, formats, date}` + manifiesto |
| `/update` | Tlacuilo | `02-drafts/` | `{command, agent, date, revision_note}` |

Enums que deben aparecer intactos donde corresponda: `procedencia` ∈ {`verificada`,
`web_search_unconfirmed`, `no_encontrada`, `inaccesible`}; `verdict` ∈ {`ok`, `ok_con_avisos`,
`rechazado`}; clases de claim ∈ {`respaldada`, `sin_ancla`, `cita_ajena`, `sin_cita`}.

## Procedimiento

El guion operativo con los prompts listos para copiar está en
[tests/phase5-methodology-runbook.md](../tests/phase5-methodology-runbook.md) (corpus de
fotosíntesis). Este protocolo solo fija el contrato; el runbook es lo que ejecuta QA.

1. **Preparar**: fijar el vault de T12 y comprobar las 6 precondiciones; anotar la salida de
   `rag_status()` como línea base.
2. **Ejecutar un comando a la vez** con un prompt fijo y realista sobre el corpus:
   - `/rubric` — «Define el alcance de una revisión sobre el material de `00-Resources/`».
   - `/research` — «Recoge evidencia del corpus para la rúbrica anterior».
   - `/validate` — «Valida las claims del informe de investigación».
   - `/synthesize` — «Sintetiza la evidencia en un outline».
   - `/cite` — «Compila la bibliografía del outline».
   - `/draft` — «Redacta el borrador a partir del outline y las citas».
   - `/review` — «Revisa el borrador sin editarlo».
   - `/transform` — «Produce un CSV con la tabla del borrador».
   - `/update` — «Incorpora esta corrección puntual al borrador».
3. **Capturar** por comando: (i) transcript de tool-calls (nombre + argumentos + resultado
   resumido), (ii) ruta del artefacto, (iii) frontmatter, (iv) veredicto de los 5 puntos.
4. **Cerrar** con `find /tmp/opencode/phase5-vault/{01-tasks,02-drafts,03-citations,04-review,05-outputs} -type f`
   y el diff de bandejas contra el estado previo.
5. **Firmar** el checklist: 9/9 filas con `ok`/`fallo`; los fallos conservan su evidencia.

## Evidencia a archivar

```text
tasks/evidence/phase5/<command>-transcript.txt   # tool-calls del comando
tasks/evidence/phase5/<command>-artifact.md      # ruta + frontmatter copiado
tasks/evidence/phase5/vault-tree.txt             # árbol final de las 5 bandejas
tasks/evidence/phase5/checklist.md               # 9 filas × 5 puntos, firmado
```

Los transcripts se pegan **crudos** (sin resumir el JSON de las tools). Si un comando no se
ejecuta, su fila se marca `NO EJECUTADO`, no `ok`.

## Criterio de cierre

* 9/9 comandos ejecutados y 45/45 puntos (9 × 5) con evidencia enlazada.
* Cualquier `fallo` se documenta con su causa; si afecta al contrato, vuelve a Phase 4 como
  enmienda fechada (no se parchea el payload).
* Si QA no ejecuta la corrida, **Phase 5 no se cierra**: la fase queda ABIERTA con el
  motivo declarado (D-P5-3).

## Lo que este protocolo NO verifica

* Calidad subjetiva de la prosa del agente (solo ruteo, bandejas, frontmatter y citas).
* Latencia/tokens de la metodología completa (cubiertos por benchmarks de Phase 2/3.5).
* Windows/PowerShell (la corrida es Linux; el instalador tiene cobertura estática).
* El CI de GitHub Actions (nunca ejecutado — M6, `docs/TECH_DEBT.md`).
