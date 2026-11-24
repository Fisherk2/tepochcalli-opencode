# Runbook — Phase 5 methodology e2e (D9) sobre fotosíntesis

> **Para:** QA humano · **Fase:** Phase 5, gate D9 · **Decisión:** D-P5-3
> **Protocolo:** [tasks/phase5-methodology-e2e.md](../tasks/phase5-methodology-e2e.md)
> **Precondición:** vault instalado (`python3 tests/e2e/verify_payload_install.py <vault>` → `OK`)

Este runbook es la guía operativa: **el QA ejecuta los 9 comandos a mano** en el harness y anota
lo que observa. No se ejecuta con un LLM automático: el criterio es el comportamiento de ruteo,
bandejas, frontmatter y citas, no comparar bytes.

Regla de honestidad: **lo no ejecutado se marca `NO EJECUTADO`**, nunca `ok`.

## 1. Preparar el vault y el corpus

1. Instala/verifica el vault (T12):
   ```bash
   python3 tests/e2e/verify_payload_install.py /tmp/opencode/phase5-vault
   ```
2. Crea el corpus de fotosíntesis en `00-resources/`. Guarda este fichero como
   `00-resources/fotosintesis.md` (es material de prueba, no del repo):

   ```markdown
   # Fotosíntesis — notas de estudio

   ## Fase luminosa
   La fotosíntesis oxigénica ocurre en los cloroplastos. En las membranas de los tilacoides,
   el fotosistema II (P680) absorbe luz y oxida agua, liberando O2 y electrones. La cadena de
   transporte (plastoquinona, complejo citocromo b6f, plastocianina) bombea protones al lumen.
   El fotosistema I (P700) reduce ferredoxina y produce NADPH. El gradiente de protones mueve
   la ATP sintasa, que genera ATP.

   ## Fase oscura (ciclo de Calvin-Benson)
   La RuBisCO fija CO2 sobre ribulosa-1,5-bisfosfato. Por cada CO2 se consumen 3 ATP y 2 NADPH
   y se produce gliceraldehído-3-fosfato (G3P). Parte del G3P regenera RuBP; el resto sale como
   azúcar. El ciclo ocurre en el estroma.

   ## Absorción de luz
   La clorofila a tiene picos de absorción cerca de 430 nm y 662 nm; la clorofila b, cerca de
   453 nm y 642 nm. Los carotenoides amplían la captación entre 400 y 500 nm.

   ## Adaptaciones
   Las plantas C4 separan la fijación inicial de CO2 (PEP carboxilasa) del ciclo de Calvin;
   las CAM separan temporalmente (noche/día). Ambas reducen la fotorrespiración en ambientes
   cálidos y secos.

   ## Claim ambiguo (para la prueba negativa)
   "La fotosíntesis produce exactamente la misma cantidad de ATP que la respiración celular."
   ```

3. Puedes añadir un PDF de tu elección (p. ej. un artículo de arXiv o de acceso abierto) sobre
   fotosíntesis. Solo material confiable: markitdown lee cualquier ruta que se le pase.
4. Abre el harness en el vault y comprueba el índice:
   - pide `rag_status()`; si el estado no es `ok`/`degraded` coherente, ejecuta `index_refresh()`;
   - confirma con `search("fase luminosa fotosistema II")` que aparecen chunks de
     `00-resources/fotosintesis.md`.

**Línea base para la evidencia:** copia la salida de `rag_status()` antes de empezar.

## 2. Orden de ejecución

```text
/rubric → /research → /validate → /synthesize → /cite → /draft → /review → /transform → /update
```

Cada comando consume la salida del anterior. No adelantes pasos: si uno falla, se documenta y se
decide si se continúa (el artefacto siguiente puede quedar incompleto).

## 3. Guion por comando

Para cada paso, pega el prompt en el harness, observa y rellena la tabla de §4.

### Paso 1 — `/rubric` (Nezahualcóyotl · `01-tasks/`)

**Prompt:**
> /rubric Define el alcance de una revisión breve sobre la fotosíntesis en `00-resources/`:
> compara la fase luminosa y el ciclo de Calvin, y fija 3 preguntas de investigación.

**Frontmatter esperado:** `{command, agent, date}`.
**Observa además:** que lea el índice (`search`) antes de abrir el `.md` crudo; que NO escriba en
`01-tasks/research/` (esa es de Pochteca).

### Paso 2 — `/research` (Pochteca · `01-tasks/research/`)

**Prompt:**
> /research Recoge evidencia del corpus para las 3 preguntas de la rúbrica. Para cada fuente
> registra `{fuente, estado, url_o_doi, fecha_consulta}`. Incluye una fuente web que no puedas
> confirmar y una que no exista.

**Frontmatter esperado:** `{agent, timestamp, fuentes, método, procedencia}`.
**Observa además:** `procedencia` **siempre serializada** (aunque sea `[]`); los 4 estados
(`verificada`, `web_search_unconfirmed`, `no_encontrada`, `inaccesible`); `web_search_unconfirmed`
**nunca** presentado como `verificada`; escritura solo en `01-tasks/research/`.

### Paso 3 — `/validate` (Chilam · `04-review/`)

**Prompt:**
> /validate Valida las claims del informe de investigación contra el índice. Incluye el claim
> ambiguo del corpus y una cita inventada a un heading que no existe.

**Frontmatter esperado:** `{command, agent, target_doc, verdict}`; `verdict` ∈ {`ok`,
`ok_con_avisos`, `rechazado`}.
**Observa además:** las 4 clases (`respaldada`, `sin_ancla`, `cita_ajena`, `sin_cita`); la
ambigüedad **nunca** cuenta como `respaldada`; `ok` es imposible si hay `sin_ancla` o `sin_cita`.

### Paso 4 — `/synthesize` (Nezahualcóyotl · `01-tasks/`)

**Prompt:**
> /synthesize Sintetiza la evidencia validada en un outline de 4 secciones para un texto de
> divulgación sobre fotosíntesis.

**Frontmatter esperado:** `{command, agent, phase, date}`.
**Observa además:** que no invente claims fuera de la evidencia validada; que no escriba en
`02-drafts/`.

### Paso 5 — `/cite` (Chilam · `03-citations/`)

**Prompt:**
> /cite Compila la bibliografía del outline. Si alguna referencia no tiene `procedencia`, falla
> nombrando el culpable; no generes una bibliografía parcial.

**Frontmatter esperado:** `{command, agent, style, date}`.
**Observa además:** gate determinista **sin red**; 0 supervivientes ⇒ fallo (nunca bibliografía
vacía); `web_search_unconfirmed` se compila **marcado**.

### Paso 6 — `/draft` (Tlacuilo · `02-drafts/`)

**Prompt:**
> /draft Redacta un borrador de 500 palabras a partir del outline y de las citas compiladas.
> Mantén cada cita como `source_path » heading (chars x–y)`.

**Frontmatter esperado:** `{command, agent, outline, date}`.
**Observa además:** que arranque del outline (no de cero); que cada claim del índice lleve su cita
exacta; que no escriba en `05-outputs/`.

### Paso 7 — `/review` (Chilam · `04-review/`)

**Prompt:**
> /review Revisa el borrador sin editarlo: claridad, coherencia y anclas de cita. Nombra la
> ubicación de cada hallazgo.

**Frontmatter esperado:** `{command, agent, target_doc, verdict}`.
**Observa además:** que **no modifique** `02-drafts/`; que toda observación nombre heading o
fragmento; que una cita que ya no resuelve se reporte `sin_ancla`, no se arregle en silencio.

### Paso 8 — `/transform` (Tlacuilo · `05-outputs/`)

**Prompt:**
> /transform Genera un CSV con la comparación fase luminosa vs ciclo de Calvin del borrador.
> Después intenta también un manuscrito LaTeX.

**Frontmatter esperado:** `{command, agent, source_draft, formats, date}` + nota de manifiesto.
**Observa además:** que llame `list_formats` **antes** de prometer formato; que el `.md` convertido
no se trate como fuente citable; que LaTeX se declare **GAP** pendiente, sin inventar skill ni
simular el artefacto.

### Paso 9 — `/update` (Tlacuilo · `02-drafts/`)

**Prompt:**
> /update Corrige en el borrador el dato de absorción de la clorofila a (430/662 nm) y ajusta la
> frase que lo usa. No reescribas el resto.

**Frontmatter esperado:** `{command, agent, date, revision_note}`.
**Observa además:** que aplique solo el cambio pedido (sin re-planificar ni re-redactar secciones
ajenas); que el borrador siga en `02-drafts/`.

## 4. Tabla de registro (rellenar a mano)

Marca `S`/`N` en cada punto y anota la evidencia (ruta o fragmento del transcript).

| # | Comando | Agente real | Bandeja | Frontmatter | MCP-first | Sin contaminación | Veredicto | Evidencia |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `/rubric` | | `01-tasks/` | | | | | |
| 2 | `/research` | | `01-tasks/research/` | | | | | |
| 3 | `/validate` | | `04-review/` | | | | | |
| 4 | `/synthesize` | | `01-tasks/` | | | | | |
| 5 | `/cite` | | `03-citations/` | | | | | |
| 6 | `/draft` | | `02-drafts/` | | | | | |
| 7 | `/review` | | `04-review/` | | | | | |
| 8 | `/transform` | | `05-outputs/` | | | | | |
| 9 | `/update` | | `02-drafts/` | | | | | |

**MCP-first** = hay un `search` de `tepochcalli-rag` antes de cualquier lectura cruda de
`00-resources/` en el transcript del comando. **Sin contaminación** = no aparece escritura en
bandeja ajena ni edición de ficheros del usuario en 01-05.

## 5. Evidencia a archivar

```text
tests/evidence/phase5/photosynthesis/<NN>-<command>-transcript.txt
tests/evidence/phase5/photosynthesis/<NN>-<command>-artifact.md
tests/evidence/phase5/photosynthesis/vault-tree.txt
tests/evidence/phase5/photosynthesis/checklist.md
```

`vault-tree.txt`:
```bash
find <vault>/{01-tasks,02-drafts,03-citations,04-review,05-outputs} -type f | sort
```

El transcript se pega **crudo** (nombres y argumentos de las tools, resultados resumidos). No se
resume el JSON de `search`.

## 6. Criterio de cierre

- 9/9 comandos ejecutados y **45/45 puntos** (9 × 5) con evidencia enlazada.
- Cualquier `fallo` conserva su causa y su transcript; si afecta al contrato, vuelve a Phase 4
  como enmienda fechada (no se parchea el payload).
- Si no se ejecuta la corrida, **Phase 5 no se cierra**: queda ABIERTA con el motivo declarado.

## 7. Qué NO prueba este runbook

- Calidad subjetiva de la prosa (solo ruteo, bandejas, frontmatter y citas).
- Latencia/tokens de la metodología completa (benchmarks de Phase 2/3.5).
- Windows/PowerShell ni el CI de GitHub Actions (nunca ejecutado — M6).
