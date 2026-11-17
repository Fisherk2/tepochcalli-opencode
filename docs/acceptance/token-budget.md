# Criterio 4: tokens por consulta < 2000, con tokenizador real (Phase 6 · T6)

> **Fecha:** 2026-11-13 · **Fase:** Phase 6 — E2E Acceptance · **Calpulli:** T6
> **Estado:** entregado; **sin commit** (lo integra el orquestador).
> **Fuente de verdad:** `docs/UH.md` línea 57 (inmutable) — «el consumo de tokens por consulta es
> inferior a 2000 tokens (incluyendo contexto)» · `tasks/plan.md` §Task T6 · `docs/TRD.md` §6.1
> (fila 4) y §6.2.
> **Jerarquía de evidencia (D8):** todo lo de aquí es **`medido`** con `tiktoken` en el host de
> referencia; cada tabla lleva su comando.
> **Evidencia archivada:** [token-budget.json](token-budget.json) (desglose por caso + sonda de
> sensibilidad).

## 1. Resultado en una línea

**PASS en las dos cifras: (a) payload del server = 1 600 tokens por el ESTIMADOR del contrato
(`chars/4 + 25`, invariante que garantiza `apply_budget`) y **1 789** con tokenizador real en el
peor caso; (b) total e2e = **1 995** tokens < 2 000 (peor caso adverso, n=4 resultados).**

El margen del peor caso son **5 tokens**: el criterio se cumple, pero **sin holgura** — ver
§5 (hallazgo F-T6-1). No se toca el contrato MCP ni el techo del server (no hace falta: se cumple).

## 2. Qué se mide y qué no

Una «consulta» = lo que el LLM ve en un turno con `search`. Se cuenta **pieza a pieza**, con el
mismo tokenizador, y se publica el total:

| Pieza | Origen | Cómo se obtiene |
| --- | --- | --- |
| **query** | el usuario | texto de la pregunta, tal cual |
| **payload** | server `tepochcalli-rag` | `content[0].text` real: se serializa con `tepochcalli_mcp.tools.json_result` — el empaquetador de PRODUCCIÓN (`ensure_ascii=False`, orden de claves del contrato). No se reconstruye el dict a mano |
| **respuesta** | agente | **esqueleto mínimo que el payload exige**: una afirmación (13 palabras ES) por resultado devuelto, anclada en el formato prescrito |

**Formato de cita: tomado del payload, no inventado.** Los 5 prompts y los 9 comandos prescriben
`source_path » heading (chars x–y)` con «only fields `search` returned»
(`specs/spec-payload-agents.md:96,159,225,293,358` · `specs/spec-payload-commands.md:61,87,122`).
Con `heading` nulo —PDF y binarios, TD-27/D54— el ancla se escribe `(sin heading)`: el agente no
puede inventar una sección que `search` no devolvió. Ejemplo del esqueleto medido:

```text
- Evidencia 1: El fragmento recuperado respalda la afirmación con el vocabulario del propio
  documento. `00-Resources/denso.md » Sección 0 de zarpatoria (chars 40–1470)`
```

**La respuesta medida es una COTA INFERIOR.** La prosa que el agente añade alrededor de las citas
no se cuenta aquí; el margen que sobra se publica en tokens y se convierte en frases extra en la
sonda de sensibilidad (§4).

**No se mide** (declarado, fuera de la cota de una consulta): definiciones de tools (esquema del
MCP), system prompt del agente, historial de turnos previos, ni el `reasoning` del modelo. Si
alguna de esas piezas creciera, el criterio se leería distinto — y no es lo que `docs/UH.md` pide.

## 3. Tokenizador: cuál, versión y fuente

| Hecho | Valor |
| --- | --- |
| Tokenizador del guard | **`cl100k_base`** |
| Librería y versión | **`tiktoken 0.14.0`** (ya en el venv del payload, transitiva — **cero dependencias nuevas**, R1) |
| Fuente | `tiktoken` (OpenAI), `tiktoken/get_encoding.py` + `MODEL_TO_ENCODING` — <https://github.com/openai/tiktoken> |
| Cross-check publicado | **`o200k_base`** (encoding de la familia gpt-4o/gpt-5 según `MODEL_TO_ENCODING`): mismo JSON, columna aparte |

**Por qué un tokenizador de referencia y no el del harness.** El payload corre modelos servidos por
el gateway OpenCode Zen (`opencode/big-pickle`, `minimax-m3.1-flash-free`, `mimo-v2.6-flash-free`,
`glm-5.3-flash-free`, `deepseek-v4.1-flash-free` — `obsidian-workspace/opencode.json`): sus
tokenizadores **no están en el repo ni se distribuyen con nombre estable y verificable**, así que no
son accesibles desde el repo. El AC de T6 obliga a declarar el sustituto y su motivo.

**Por qué el más caro de los dos BPE públicos.** Medido sobre este corpus (ES markdown del vault
golden y CJK del fixture adverso): `cl100k_base` = 0,27 tok/char ES y 1,04 tok/char CJK;
`o200k_base` = 0,24 y 0,81. Una cota que se cumple con el tokenizador caro se cumple también con el
barato, así que el guard **no depende de la elección**: se publican los dos totales y el guard usa
el peor. Si un futuro modelo del harness tokeniza peor que `cl100k_base` para ES/CJK, esta cifra se
queda corta y hay que re-medir con ese tokenizador (declarado, no descubierto tarde).

**Primer uso:** `tiktoken` descarga el vocabulario BPE una vez y lo cachea en
`$TMPDIR/data-gym-cache` (o `TIKTOKEN_CACHE_DIR`); como el modelo de embeddings, el primer arranque
necesita red una vez.

## 4. Cifras medidas

Fixture: el **adverso de T7, REUSADO** (`tests/integration/test_mcp_budget_adversarial.py`) —
unicode, CJK, emoji, tablas markdown de PDF y listas largas — indexado de verdad en subproceso; el
`search` es el **handler real** con el backend real sobre ese índice.

| Caso | n | query | payload | respuesta | **total (`cl100k`)** | total (`o200k`) | margen |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `dorada_corta` (consulta dorada, `top_k=5`) | 4 | 7 | 1 461 | 207 | **1 675** | 1 536 | 325 |
| `cjk_emoji` (`東京の天気…🚀`) | 3 | 20 | 1 649 | 151 | **1 820** | 1 464 | 180 |
| `emoji_latin` | 4 | 17 | 1 716 | 197 | **1 930** | 1 789 | 70 |
| `denso_corte` (chunks ~1 536 B, `truncated`) | 4 | 9 | 1 730 | 208 | **1 947** | 1 801 | 53 |
| `pdf_tablas` (tabla markdown de PDF) | 1 | 12 | 429 | 54 | **495** | 476 | 1 505 |
| `top_k_maximo` (`top_k=20` ⇒ 8 efectivo) | 4 | 7 | **1 789** | 199 | **1 995** | 1 785 | **5** |
| `error_query` (10 001 chars ⇒ `VALIDATION_ERROR`) | 0 | 1 251 | 51 | 9 | **1 311** | 1 306 | 689 |

La fila `error_query` cuenta **también la query**: un texto de 10 001 `x` que el agente ya escribió
no es gratis porque el tool lo rechace (`VALIDATION_ERROR` antes de tocar el índice). Aun así cabe:
1 311 < 2 000. Se publica la fila entera para que la decisión de qué cuenta sea visible, no
silenciosa.

**Sonda de sensibilidad (el guard no es vacío):** el mismo `denso_corte` con **2 frases por
resultado** (una más que el esqueleto mínimo) da **2 023** tokens ⇒ la aserción de 2 000 se dispara
con una frase extra. O dicho al revés: en el peor caso el agente puede añadir **~5 tokens** de prosa
y en el caso dorado **325**.

**Comando (reproducible, primer plano, ~70 s):**

```bash
TEPOCHCALLI_TOKEN_EVIDENCE="$PWD/docs/acceptance/token-budget.json" just python-test-file token_budget
```

El mismo comando **sin** la variable de entorno ejecuta el test y no escribe nada (es lo que corre la
suite `just test-mcp-tools`).

## 5. Las dos cifras, sin confundirlas

| # | Cifra | Valor | Qué la garantiza |
| --- | --- | --- | --- |
| **(a)** | payload del server **≤ 1600** | 1 600 por el **estimador** `chars/4 + 25` (`budget.apply_budget`, `PAYLOAD_TOKEN_CEILING`) | invariante del contrato, asertado por `test_mcp_budget_adversarial.py` (T7) en las 6 caras |
| (a′) | el mismo payload con **tokenizador real** | hasta **1 789** (`cl100k`) | medido aquí; **no** es una cota del contrato |
| **(b)** | **total e2e < 2000** | **1 995** peor caso / 1 675 caso dorado (`cl100k`); 1 801 / 1 536 (`o200k`) | este test, en la suite `just test-mcp-tools` |

### Hallazgo F-T6-1 — «1600» es del estimador, no del tokenizador: el margen real son 5 tokens

El techo 1 600 y la cota 2 000 se pensaron con 400 tokens de margen «para la pregunta y la respuesta
del agente» (`specs/spec-mcp-server.md` §Presupuesto). Medido con tokenizador real, ese margen está
casi consumido por dos motivos sumados:

1. **La envoltura del JSON no está en la fórmula.** El `Σ estimate_tokens(text)` que gatea
   `apply_budget` no cuenta el `query` echo, las claves JSON, los `source_path` ni los `score`
   flotantes: son **≈180-200 tokens reales** de envoltura (el hallazgo F-T7-1 lo acotó a ≤200 con
   el estimador).
2. **El estimador `chars/4` es optimista para ES en `cl100k`** (0,27 tok/char real vs 0,25 asumido):
   sobre 6 000 chars son ~120 tokens de diferencia.

Efecto: un payload «1 600» por contrato mide **1 789** de verdad, y el total queda a 5 tokens de la
cota en la configuración legal más cara (`top_k=20`). **El criterio 4 se cumple hoy** (1 995 < 2 000)
y la guarda lo vigila; pero cualquier engorde del payload (un campo más por resultado, un `heading`
más largo, un chunk mayor) lo pone rojo. Alternativas si eso pasa — **decisión del dueño, no de este
calpulli**: bajar el techo del server (p. ej. 1 500) o renegociar la fórmula de §5 del plan; el
contrato MCP (ADR-005) no se toca por esto.

## 6. Qué se cuenta cuando el payload viene truncado o con error

Elegir qué se cuenta es donde un presupuesto se maquilla. Reglas de este medidor, con su test:

* **Truncado** (`truncated: true`, 5 de las 7 filas): se cuenta el payload **tal como se entrega** —lo
  descartado no llega al modelo y por tanto no cuesta— y la respuesta se ancla **solo** a los
  resultados entregados.
* **Error** (`VALIDATION_ERROR`, `INDEX_EMPTY`, `E_*`): se cuenta el payload de error **y la query
  que lo provocó**; **jamás se descarta** la consulta por «no tener resultados»
  (`test_error_payloads_are_counted_never_skipped`). El desglose publica `error` en cada fila.
* **Query gigante rechazada**: el handler la rechaza antes de tocar el índice, pero el texto lo
  escribió el agente y se cuenta (fila `error_query`: 1 251 + 51 + 9 = 1 311 < 2 000). Descontarla
  sería el maquillaje más fácil de este presupuesto, así que el test la exige.

## 7. Guarda viva en la suite

`tests/integration/test_mcp_token_budget.py` (sin marcadores `slow`/`heavy`, sin aserciones de
reloj) — corre en `just test-mcp-tools`:

| Test | Qué afirma |
| --- | --- |
| `test_every_adversarial_consultation_stays_under_2000_tokens` | **total < 2 000** en las 7 caras del fixture adverso (incluida la query patológica) + **sensibilidad**: 2 frases/resultado > 2 000 ⇒ el guard no es vacío. Publica la tabla de desglose en el mensaje de fallo |
| `test_error_payloads_are_counted_never_skipped` | el payload de error se cuenta, se declara `error` y también queda bajo la cota |
| `test_published_payload_figure_is_the_wire_text_of_the_real_handler` | el desglose suma (query + payload + respuesta = total) y `n` coincide con el wire |

El medidor es `tests/support/token_budget.py` (tokenizador de referencia, `wire_text` con el
empaquetador de producción, esqueleto de respuesta y `TokenBudget`).

**Demostración de que la guarda puede fallar (RED real):**

```text
$ just python-test-file token_budget          # antes del medidor: colección
E   ModuleNotFoundError: No module named 'support.token_budget'

# Con el medidor y una respuesta de 2 frases por resultado (el guard se dispara):
AssertionError: guard vacío: 2 frases/resultado cuestan 2023 ≤ 2000
denso_corte: query=9 payload=1730 respuesta=284 total=2023 (n=4, truncated=True, ...)
```

**Estabilidad de la cifra.** El `payload` incluye `took_ms` (valor de reloj: 1-2 tokens según sus
dígitos) y el corte por score puede quedarse con un chunk de longitud vecina, así que el total oscila
**unos pocos tokens** entre corridas: observado 1 711↔1 716 en `emoji_latin` (total 1 930↔1 934),
1 730↔1 731 en `denso_corte` (total 1 947↔1 948) y 2 023↔2 024 en la sonda. El peor caso
`top_k_maximo` se midió **1 995 en las cuatro corridas** de esta sesión; su margen (5) es del orden
de esa oscilación, y así se publica.

## 8. Cómo se reproduce (y qué NO se hace)

* Índice: lo construye la propia suite (subproceso, `support.mcp_server.index_vault`) sobre el vault
  adverso de T7; **no** se reutiliza un índice de otro calpulli.
* Host: el de [protocol.md](protocol.md) §1 (fusión btrfs/NVMe, CPython 3.12.14 del venv del
  payload); el conteo de tokens no depende del filesystem.
* **No** se recorta el corpus ni el `top_k` para que la cifra pase: si el total superara 2 000, se
  publicaría el FAIL y se pararía a pedir decisión del dueño (`tasks/plan.md` §Task T6).
