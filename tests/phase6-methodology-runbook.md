# Runbook — Phase 6 methodology e2e (D9)

> **Para:** QA humano · **Fase:** Phase 6, gate D9 (TD-31) · **Decisión:** D-P6-2
> **Verificador:** `tests/e2e/verify_methodology_evidence.py` (mecánico, sin LLM)
> **Plantilla de checklist:** `tests/phase6-methodology-checklist.md`
> **Histórico:** `tests/phase5-methodology-runbook.md` describe el formato **anterior** a la ola
> del 2026-11-12; se conserva tal cual y **no** se usa para esta corrida.

Este runbook es la guía operativa: **el QA ejecuta los 9 comandos a mano** en el harness y archiva
lo que observa. Los subagentes no simulan la corrida. La fuente de verdad de cada comando es su
cuerpo vigente en `obsidian-workspace/.opencode/commands/`; si este runbook y un cuerpo divergen,
manda el cuerpo y se anota la observación.

Regla de honestidad: **lo no ejecutado se marca `NO EJECUTADO`**, nunca `ok`.

## 1. Preparación

1. Instala/verifica el vault:

   ```bash
   python3 tests/e2e/verify_payload_install.py /tmp/opencode/phase6-vault
   ```

2. Crea el corpus en `00-resources/fotosintesis.md` (material de prueba, no del repo):

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

3. Abre el harness en el vault y comprueba el índice: `rag_status()` y, si el estado no es
   `ok`/`degraded` coherente, `index_refresh()`. Confirma con
   `search("fase luminosa fotosistema II")` que aparece `00-resources/fotosintesis.md`.
   Copia la salida de `rag_status()` como línea base de la evidencia (pégala al inicio de
   `01-rubric-transcript.txt`).
4. Crea el directorio de archivo: `tests/evidence/phase6/`.

## 2. Nombres deterministas

El verificador es mecánico porque los nombres son un contrato. Copia cada artefacto del vault a
`<NN>-<comando>-artifact.md` **sin editar** su contenido (el frontmatter se verifica tal cual).

| # | Comando | Agente | Bandeja | Artefacto en el vault | Evidencia |
| --- | --- | --- | --- | --- | --- |
| 1 | `/rubric` | nezahualcoyotl | `01-tasks/` | `01-tasks/rubric.md` | `01-rubric-{transcript,artifact}` |
| 2 | `/research` | pochteca | `01-tasks/research/` | `01-tasks/research/evidence.md` | `02-research-{transcript,artifact}` |
| 3 | `/validate` | chilam | `04-review/` | `04-review/validation.md` | `03-validate-{transcript,artifact}` |
| 4 | `/synthesize` | nezahualcoyotl | `01-tasks/` | `01-tasks/outline.md` | `04-synthesize-{transcript,artifact}` |
| 5 | `/cite` | chilam | `03-citations/` | `03-citations/bibliography.md` | `05-cite-{transcript,artifact}` |
| 6 | `/draft` | tlacuilo | `02-drafts/` | `02-drafts/draft.md` | `06-draft-{transcript,artifact}` |
| 7 | `/review` | chilam | `02-drafts/` | `02-drafts/draft-revA.md` | `07-review-{transcript,artifact}` |
| 8 | `/transform` | tlacuilo | `05-outputs/` | `05-outputs/comparison.csv`, `05-outputs/fotosintesis.md`, `05-outputs/transform-manifest.md` | `08-transform-{transcript,artifact}` |
| 9 | `/update` | tlacuilo | `02-drafts/` | `02-drafts/draft-revB.md` | `09-update-{transcript,artifact}` |

Notas del formato vigente:

- **`chilam` no tiene bandeja propia**: escribe donde su comando produce el artefacto
  (`/cite` en `03-citations/`, `/validate` en `04-review/`, `/review` en `02-drafts/`).
- `/review` ya **no** deja el informe en `04-review/`: escribe la siguiente revisión
  `draft-revA.md` en `02-drafts/` (el runbook de Phase 5 reflejaba el formato anterior).
- `/transform` es el único escritor de `05-outputs/`; el `.md` convertido **no** es citable.

## 3. Guion por comando

Orden: `/rubric → /research → /validate → /synthesize → /cite → /draft → /review → /transform
→ /update`. Cada comando consume la salida del anterior; si uno falla, se documenta y se decide
si continuar. Pega el prompt, observa y archiva.

### 1 — `/rubric`

**Prompt:**
> /rubric Define el alcance de una revisión breve sobre la fotosíntesis en `00-resources/`:
> compara la fase luminosa y el ciclo de Calvin, y fija 3 preguntas de investigación.

**Produce:** `01-tasks/rubric.md` (puede crear `plan.md` y `todo.md`).
**Frontmatter:** `{command, agent, date}`.
**Observa:** Phase 0/1 con la tool `question` (no decide el alcance solo); Phase 2 escribe **una**
rúbrica; no escribe fuera de `01-tasks/`.

### 2 — `/research`

**Prompt:**
> /research Recoge evidencia del corpus para las 3 preguntas de la rúbrica. Para cada fuente
> externa registra `{source, status, url_o_doi, query_date}`. Incluye una fuente que no puedas
> confirmar y una que no exista.

**Produce:** `01-tasks/research/evidence.md` (una nota por hallazgo si aplica).
**Frontmatter:** `{agent, timestamp, source, method, origin}`.
**Observa:** `origin` **siempre serializado** (aunque sea `[]`); los 4 estados del cuerpo vigente
—`verified`, `web_search_unconfirmed`, `no_found`, `no_available`—; `web_search_unconfirmed`
nunca presentado como `verified`; escritura solo en `01-tasks/research/`.

### 3 — `/validate` (4 fases)

**Prompt:**
> /validate Valida las claims del informe de investigación contra el índice. Incluye el claim
> ambiguo del corpus y una cita inventada a un heading que no existe.

**Produce:** `04-review/validation.md`.
**Frontmatter:** `{command, agent, target_doc, verdict}`; `verdict` ∈
{`ok`, `ok_with_warnings`, `rejected`}.
**Observa:** Fase 0 inventario del índice; Fase 1 claims `C1..Cn` clasificados en
`backed`/`no_anchor`/`external_citation`/`no_citation` con re-query alternativa; Fase 2
contradicciones, sesgo y autoridad; Fase 3 informe y regla de veredicto. `ok` es **imposible**
con `no_anchor` o `no_citation`; la ambigüedad nunca cuenta como `backed`.

### 4 — `/synthesize`

**Prompt:**
> /synthesize Sintetiza la evidencia validada en un outline de 4 secciones para un texto de
> divulgación sobre fotosíntesis.

**Produce:** `01-tasks/outline.md`.
**Frontmatter:** `{command, agent, phase, date}`.
**Observa:** Pre-Flight que solo admite evidencia con verdict `ok`/`ok_with_warnings` (si falta,
STOP y sugiere `/research`); 3–6 ejes; anclas `source_path » heading (chars x–y)`; cero prosa
redactada; no escribe en `02-drafts/`.

### 5 — `/cite`

**Prompt:**
> /cite Compila la bibliografía del outline. Si alguna referencia no tiene `origin`, falla
> nombrando el culpable; no generes una bibliografía parcial.

**Produce:** `03-citations/bibliography.md`.
**Frontmatter:** `{command, agent, style, date}`.
**Observa:** Pre-Flight `R1..Rn` con `origin`; gate determinista **sin red**; `checked` compila,
`web_search_unconfirmed` se incluye **marcado**, `no_found`/`inaccessible` se descartan con log
(`inaccesible` es alias normalizado); 0 supervivientes ⇒ fallo, nunca bibliografía vacía; cero
salida parcial si falta `origin`.

### 6 — `/draft`

**Prompt:**
> /draft Redacta un borrador de 500 palabras a partir del outline y de las citas compiladas.
> Mantén cada cita como `source_path » heading (chars x–y)`.

**Produce:** `02-drafts/draft.md`.
**Frontmatter:** `{command, agent, outline, date}`.
**Observa:** Pre-Flight de los **tres insumos** (outline, bibliografía, evidencia con verdict);
sin navegación nueva; cada afirmación con su ancla o su `R`; citas congeladas sin parafrasear;
no escribe en `05-outputs/`.

### 7 — `/review`

**Prompt:**
> /review Revisa el borrador sin editarlo: claridad, coherencia y anclas de cita. Nombra la
> ubicación de cada hallazgo. Después de mi confirmación, aplica solo los hallazgos aceptados.

**Produce:** `02-drafts/draft-revA.md` (la revisión; el informe es la tabla de hallazgos del
transcript).
**Frontmatter:** `{command, agent, source, rev}`.
**Observa:** Fase 0 resuelve el target con `question`; Fase 1 categoriza
`spelling`/`argument`/`clarity`/`structure`/`evidence`/`no_anchor` **sin editar**; el input queda
byte-idéntico hasta la confirmación; Fase 2 aplica solo lo confirmado y nombra la revisión por la
regla determinista (`A→B→…`, luego `revAA`); una cita que no resuelve se reporta, no se arregla
en silencio.

### 8 — `/transform` (opciones A–G)

**Prompt:**
> /transform Genera un CSV comparando fase luminosa y ciclo de Calvin (opción B) y convierte
> `00-resources/fotosintesis.md` a Markdown en `05-outputs/` (opción G). Antes de prometer el
> formato, consulta cuáles soporta el conversor.

**Produce:** `05-outputs/comparison.csv`, `05-outputs/fotosintesis.md` y
`05-outputs/transform-manifest.md` (manifiesto con frontmatter).
**Frontmatter del manifiesto:** `{command, agent, source_draft, formats, date}`.
**Observa:** Phase 1 confirma intención y ofrece el menú **A–G** con `question`; en G llama
`list_formats` **antes** de prometer o convertir; una incompatibilidad se declara y se ofrecen
alternativas (no se fuerza); el `.md` convertido **no** se trata como fuente citable; no inventa
citas ni cifras; todo aterriza en `05-outputs/`.

### 9 — `/update`

**Prompt:**
> /update Corrige en el borrador revisado el dato de absorción de la clorofila a (430/662 nm) y
> ajusta la frase que lo usa. No reescribas el resto.

**Produce:** `02-drafts/draft-revB.md`.
**Frontmatter:** `{command, agent, date, revision_note}`.
**Observa:** Pre-Flight resuelve el target y clasifica el cambio en **un** scope
(`inject-new-info`, `correct-data`, `refresh-stale-cite`); `index_refresh()` antes si el material
es nuevo; solo las secciones afectadas cambian, el resto byte-idéntico; no re-planifica el
outline ni re-redacta secciones ajenas.

## 4. Convención del transcript

Pega el transcript **crudo**: nombre de la tool, argumentos y resultado resumido (no resumas el
JSON de `search`). No reordenes líneas. El verificador reconoce:

- **llamada al índice:** una línea con `tepochcalli-rag` y el token `search`;
- **lectura cruda:** una línea con `read`/`cat`/`head`/`open`/`grep`/`glob` y una ruta
  `00-resources/`.

La regla **MCP-first** exige que la primera lectura cruda de `00-resources/` esté precedida por un
`search` de `tepochcalli-rag`. Si un comando no lee crudo (p. ej. `/cite`), el punto pasa como
«sin lectura cruda». El conjunto de los 9 transcripts debe ejercitar `search` al menos una vez.

## 5. Archivo

```text
tests/evidence/phase6/
├── <NN>-<comando>-transcript.txt   # 9, crudos
├── <NN>-<comando>-artifact.md      # 9, copia del artefacto del vault
├── vault-tree.txt
└── checklist.md                    # copia rellena de la plantilla
```

`vault-tree.txt` (desde la raíz del repo, con `<vault>` sustituido):

```bash
find <vault>/{01-tasks,02-drafts,03-citations,04-review,05-outputs} -type f | sort
```

Copia primero `tests/phase6-methodology-checklist.md` a `tests/evidence/phase6/checklist.md` y
rellénalo: cada fila enlaza su transcript en la columna **Evidencia**.

## 6. Verificación mecánica

```bash
python3 tests/e2e/verify_methodology_evidence.py tests/evidence/phase6
```

Comprueba, con `PASS`/`FAIL` por punto y exit `0`/`1`/`2`:

- **(a)** cada artefacto en su bandeja y ninguna bandeja ajena con ficheros;
- **(b)** frontmatter con los campos del formato vigente (y `origin` serializado como lista);
- **(c)** transcript de los 9 comandos y `checklist.md` presente;
- **(d)** MCP-first observado en cada transcript que lee crudo.

El script **no juzga la prosa**, la relevancia de las citas ni el veredicto editorial: eso queda
en el checklist del QA. Un `FAIL` mecánico no se «arregla» editando el artefacto: se corrige la
evidencia y se vuelve a archivar.

## 7. Criterio de cierre

- 9/9 comandos ejecutados y **45/45 puntos** (9 × 5) con evidencia enlazada.
- `verify_methodology_evidence.py` ⇒ **exit 0** sobre la evidencia real.
- Cualquier fallo conserva su causa y su transcript; si afecta al contrato, vuelve a Phase 4 como
  enmienda fechada (no se parchea el payload desde el QA).
- Si la corrida no se ejecuta: **NO EJECUTADO** con motivo, TD-31 sigue abierta y Phase 6 no se
  declara cerrada.

## 8. Límites y divergencias conocidas

- **No prueba** calidad subjetiva de la prosa, latencia/tokens de la metodología, Windows ni el CI
  de GitHub Actions (M6).
- **`vault-tree.txt` es una foto del QA**, no un escaneo independiente del vault: el verificador
  comprueba lo listado, no puede detectar un fichero omitido. El runbook fija el comando `find`
  para que la foto sea reproducible.
- **`/review` en `02-drafts/`:** divergencia con la tabla D9.2 de `specs/spec-agent-workflow.md`
  (que lo asignaba a `04-review/`). Manda el cuerpo vigente; anótalo como observación, no lo
  «corrijas» en el payload.
- **Estados de procedencia:** `/research` serializa `verified`/`web_search_unconfirmed`/
  `no_found`/`no_available`; `/cite` normaliza a `checked`/`web_search_unconfirmed`/`no_found`/
  `inaccessible` (alias legacy `inaccesible`). Si la correspondencia no es explícita en el
  transcript, anótalo como hallazgo del QA.
- **Manifiesto de `/transform`:** sus campos son la convención de evidencia de este runbook; el
  cuerpo del comando solo pide un resumen en Phase 2.
