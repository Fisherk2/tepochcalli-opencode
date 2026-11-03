# TODO — Phase 3.5: conversor summary-only + índice multi-raíz + RAG de documentos + dieta + skill `tepochcalli-mcp`

> Detalle completo en [tasks/plan.md](plan.md). Orden impuesto por el grafo de dependencias.
> Regla de la casa: **una calpulli = un camino completo**, con criterio de aceptación y verificación.
> Nada de Phase 4-5 (blueprint y payload), nada del wizard más allá de lo autorizado en T6.

**Rama:** `feat/workspace-obsidian` · **Fuente:** [docs/WORKFLOW.md](../docs/WORKFLOW.md) §Phase 3.5
**Motor (tocado):** `obsidian-workspace/.tepochcalli/flow/tepochcalli_flow/`
**Server (tocado):** `obsidian-workspace/.tepochcalli/mcp/tepochcalli_mcp/`
**Deps (tocado):** `obsidian-workspace/.tepochcalli/pyproject.toml` + `uv.lock` (T4)
**Tests:** `tests/unit/` · `tests/integration/` · `tests/e2e/` · `tests/benchmarks/`
**Payload (tocado):** `obsidian-workspace/opencode.json` (T14) · `obsidian-workspace/.opencode/skills/tepochcalli-mcp/` (T15)
**Documentos:** `specs/adr/adr-009|010|011-*.md` (nuevos) · `specs/spec-markitdown.md` · `specs/spec-mcp-server.md` · `specs/spec-rag-engine.md` · `specs/spec-vault-structure.md` · `docs/WORKFLOW.md` · `docs/ARCHITECTURE.md` · `docs/SECURITY.md` · `docs/TECH_DEBT.md` · `docs/TRD.md` · `SPEC.md` · `CHANGELOG.md`
**Historial:** sustituye al TODO de Phase 3 (`git show a10706e:tasks/todo.md`).

---

## Sub-fase A — Contratos (fail-fast)

- [ ] **T1 · ADR-009 + ADR-010 + ADR-011 + enmiendas a 4 specs + olas D28-D67**
  - Subagentes: `technical-writer` (lead), `software-architect`, `code-reviewer` · Skills: `documentation-and-adrs`, `api-and-interface-design`, `spec-driven-development` · Herramientas: `gitmcp`, `codebase-memory-mcp`, `context7`
  - AC: (a) **ADR-009** (conversor summary-only): D28 (3 tools en `tepochcalli-rag`, markitdown in-process), D31 (frontera B′), D36 (resumen de 5 claves), D37/D38/D39 (defaults y taxonomía), **D66** (destino ya existente ⇒ idempotencia: contenido idéntico ⇒ `ok`, distinto ⇒ `VALIDATION_ERROR`; **nunca** se sobrescribe material del usuario), y por qué no un server aparte ni reusar el `markitdown` standalone; (b) **ADR-010** (índice multi-raíz + cita): D32 (raíces por llamada, sin estado), **D64** (existencia y tipo se validan en el **borde MCP**, no en el motor: el `ValueError` de `walk_dir` saldría como `INTERNAL`), **D65** (fail-fast atómico: una raíz mala ⇒ **no se indexa ninguna**), D41 (`source_path` relativo al vault — superior al relativo-a-la-raíz porque dos raíces pueden compartir relativo), D43 (whitelist ampliada), D46 (recursión + raíz-fichero + dedup), D47 (frontera de symlinks = vault), D50 (`offsets_ref="extract"`), D51 (documentos fuera del Δ), **D62** (cada raíz es una `ContextKey[Path]` de cocoindex: identidad de memo estable ⇒ mover el vault no invalida el índice) y la alternativa descartada de config persistente; (c) **ADR-011** (política de dependencias): D52 (dos librerías: cocoindex + markitdown, y lo que arrastran), D53 (docling fuera), D55 (`markitdown-mcp` fuera y extras granulares), D54 (**el PDF pierde headings** — el coste explícito), D58 (`@coco.fn` en los helpers: change detection real), D59 (una sola implementación de embedder + modelo local), D60 (`as_async` + batching), D61 (sin memo de embeddings por chunk, con el coste cuantificado), **D63** (el **ledger de no-reinvención**: lo que delegamos a cocoindex/markitdown y lo que conservamos **con su razón**: el lector ANN+FTS+RRF —el conector es solo de escritura—, `heading_before` —CocoIndex no da heading—, los skips tipados —el conector se traga rotos/ilegibles—, `paths` —frontera D16—, `write_atomic` —`declare_file` es target state—, el estimador de tokens —no hay equivalente— y la ausencia de watchers —ADR-002 los prohíbe—), y la regla de que **cualquier** dependencia nueva requiere ADR; (d) `spec-markitdown`: H1/H2, B′, standalone retirado (D29), catálogo, y que el conversor **no** es el camino de indexación (D49); (e) `spec-mcp-server`: 3 tools, `index_refresh(directories=?)` + `roots` aditivo, `rag_status` con las raíces de sesión **y `index.available_roots` (D67)**, taxonomía (D39) **con la frontera de existencia y tipo (D64): `VALIDATION_ERROR` con `details.suggestions` + `vault_dirs`; `SOURCE_UNREACHABLE` solo para contenido ilegible; y el fail-fast atómico multi-raíz (D65)**, §Security con el wording **estricto** de D16 **más** B′; (f) `spec-rag-engine`: §Fuentes (raíces, whitelist), §Target (`source_path` vault-relativo, `doc_kind`, `offsets_ref`), §Ruta de documentos (markitdown; **sin headings en PDF**; fuera del Δ), §Embeddings (el modelo por ruta local y por qué), §Alternatives (Docling fuera: la regla de oro y el coste medido); (g) `spec-vault-structure`: `00-Resources/` = convención, no imposición; (h) `docs/WORKFLOW.md` §8 con D28-D67 y §Phase 3.5 con el alcance nuevo; (i) `docs/UH.md` **intacto**
  - Verificar: `just md-lint` sin errores · `git diff docs/UH.md` vacío · las 4 tools preexistentes de `spec-mcp-server` sin cambios de forma · los ADRs no re-editan ADR-005
  - 📌 **Por qué primero:** T2-T15 implementan estos contratos; el ADR-011 es el que fija la regla de oro
  - Dep.: — · Tamaño: L

---

## Sub-fase B — El motor

- [x] **T2 · Motor multi-raíz + `source_path` vault-relativo + `verify.py`**
  - Subagentes: `rag-pipeline-engineer` (lead), `python-pro`, `code-reviewer` · Skills: `clean-ddd-hexagonal`, `test-driven-development`, `incremental-implementation` · Herramientas: `codebase-memory-mcp`
  - AC: (a) `citation.normalize_source_path` deja de prefijar `RESOURCES_DIR/` y devuelve la ruta **relativa al vault**; `..` que escape ⇒ `CitationError`; (b) `source.walk_sources(vault_root, roots)` acepta **N raíces**, cada una validada (dentro del vault, sin `..`, sin symlink fuera) **antes** de tocar el disco; inexistente ⇒ error tipado (D44); (c) **recursión a cualquier profundidad** (D46): test con `materiales/1-geografia/x.pdf` y `documentos/pdf/y.pdf`; (d) una raíz puede ser un **fichero suelto**; (e) **dedup** de raíces solapadas (`scanned == indexed + skipped` se mantiene); (f) `classify_file` calcula el `source_path` relativo al vault y la **frontera del symlink es el vault** (D47); (g) **cada raíz es una `ContextKey[Path]` de cocoindex con clave estable** (D62) ⇒ la identidad de memo de la raíz no depende de su ruta ⇒ mover el vault no invalida el índice (test: mismo `ContextKey` con otra ruta ⇒ misma clave de memo); (h) `app.refresh_blocking(directories=None)` con `None` ⇒ `["00-Resources"]` y `RefreshReport` gana `roots` (aditivo); (i) `parsers.py`/`adapters/lancedb_reader.py` siguen coherentes con el path nuevo (`path_filter` sigue siendo un glob relativo al vault); (j) `verify.py` resuelve el `source_path` vault-relativo; (k) el **golden-vault** se re-verifica: el slice del original == el `text` de la fila, con el `source_path` nuevo; (l) el `FilePath` de cada raíz se construye con **`base_dir=ContextKey[Path]` explícito** (un `Path` pelado usaría el **CWD** como base ⇒ la clave de memo dependería del proceso — D62); (m) la raíz-suelta **no** se pasa a `walk_dir` (lanza `ValueError("Path is not a directory: …")`): el motor la entrega aparte (D46); (n) el walk **poda** los directorios excluidos ⇒ un `.md` dentro de `.tepochcalli/` **no** se indexa (la exclusión `**/.*` excluye el subárbol — no hacen falta patrones nuevos); (o) los **bucles de symlink los corta el conector** (cadena de ancestros `(dev, ino)`) ⇒ **no** escribimos un visited-set (R1)
  - Verificar: `just typecheck` verde · `just python-test` verde · golden-vault re-verificado (e2e) · `just coverage` ≥95 % · test de arquitectura verde
  - 📌 **OM-8 fail-fast:** cambia el contrato de cita; sin el golden-vault re-verificado, las citas dejan de reproducir el fichero y el daño es silencioso
  - Dep.: T1 · Tamaño: L

- [ ] **T3 · Motor: documentos con markitdown (`doc_kind`, whitelist, skips tipados)**
  - Subagentes: `rag-pipeline-engineer` (lead), `python-pro` · Skills: `source-driven-development`, `test-driven-development`, `design-patterns` · Herramientas: `context7`, `gitmcp`
  - AC: (a) `parsers.extract_text` usa **markitdown** para todo lo que no sea texto plano (D48): `.md/.markdown/.txt` se leen en UTF-8 estricto (offsets `source`); `.pdf/.docx/.pptx/.xlsx/.xls` vía `MarkItDown().convert(Path).markdown` (offsets `extract`); el anclaje a la **fuente instalada** (`markitdown==0.1.9`) queda escrito en el docstring; (b) `citation.DocKind` gana `docx/pptx/xlsx/xls` (aditivo) y `offsets_ref_for` queda `{md,markdown,txt}→"source"`, resto → `"extract"` (D50); (c) `source.WHITELIST_PATTERNS` amplía con los documentos (D43) en el «único lugar»; (d) **el PDF pierde la jerarquía de headings** (D54): `heading` nulo en sus citas — el AC lo afirma, no lo oculta; (e) un extractor que falla (corrupto, cifrado, sin capa de texto) **no aborta el pase**: `SkippedSource` con motivo tipado, y un documento **sin texto** no se indexa como vacío (OM-11); (f) `doc_kind` nuevo = columna de texto (sin enum) ⇒ esquema aditivo
  - Verificar: `just typecheck` verde · unit de `doc_kind_for`/`offsets_ref_for` · integration con un `.docx`/`.xlsx` de fixture ⇒ indexado, con `heading` cuando el documento lo tiene · el PDF **sin** headings (afirmado) · `just coverage` ≥95 %
  - 📌 **Nota:** con markitdown, el texto indexado y el `.md` del conversor **coinciden** (misma librería) — se afirma en un test
  - Dep.: T2 · Tamaño: M

- [x] **T4 · Dieta: pyproject + `uv.lock` + medición del venv**
  - Subagentes: `dependency-manager` (lead), `devops-engineer`, `build-engineer` · Skills: `dependency-audit`, `bash-defensive-patterns`, `ci-cd-and-automation` · Herramientas: `codebase-memory-mcp`
  - AC: (a) el pyproject del payload declara **`markitdown[docx,pptx,xlsx,xls,pdf]==0.1.9`** y **quita** `markitdown-mcp==0.0.1a8`, `docling>=2,<3` y `torchvision==0.29.1` (D55, D53); los comentarios del pyproject se actualizan (torch sigue declarado **por el pin del índice CPU**); (b) **`litellm` deja de ser dependencia directa**: el pyproject pide `cocoindex[lancedb,sentence-transformers,litellm]` y el **pin de seguridad** (GHSA-92x9-889m-jgmw) se expresa como `[tool.uv] constraint-dependencies = ["litellm>=1.106.2,<1.107.0"]` — una restricción de la resolución de **toda** la gráfica, no una declaración (D56); el lock debe resolver la versión segura (hoy `1.106.4`); (c) `uv.lock` regenerado y **committeado** (ADR-004: el wizard instala desde el lock); (d) **medición antes/después**: tamaño del venv en disco y nº de paquetes, con el método publicado (objetivo ≤ 1,95 GB y ≤ ~560 paquetes; si no se alcanza, se reporta la cifra real, no la estimada) — **la cifra dice **qué** venv se mide**: el canónico `venv/` (el que exporta el Justfile y usa el wizard); el `.venv/` paralelo que uv crea sin `UV_PROJECT_ENVIRONMENT` es un artefacto local (hoy **2,4 GB duplicados**) y no cuenta (queda documentado para que nadie mida dos veces); (e) `uv sync --frozen` verde con el lock nuevo y el **import-check** del wizard ampliado a `import markitdown` (el motor ahora la usa); (f) el modo `--offline` del wizard verificado con el lock nuevo (OM-13); (g) el **formato de archivo** que el motor declara se ajusta a los extras instalados (los `.rtf/.odt/.epub` de markitdown quedan fuera de alcance v1 y se documentan)
  - Verificar: `uv sync --frozen` sin cambios · `python -c "import markitdown, tepochcalli_mcp.tools.search"` OK dentro del venv · la cifra del venv medida y publicada · `grep -c "name = " uv.lock` antes/después
  - Dep.: T3 · Tamaño: M

- [x] **T5 · Change detection: `@coco.fn` en los helpers + `as_async`**
  - Subagentes: `rag-pipeline-engineer` (lead), `python-pro` · Skills: `source-driven-development`, `test-driven-development`, `performance-analysis` · Herramientas: `context7`
  - AC: (a) `parsers.extract_text`, `parsers.chunk_document` y los helpers de cita que influyen en el texto indexado se decoran con **`@coco.fn`** (sin `memo=True`) para que su lógica participe en el fingerprint (D58); (b) el salto a hilo manual (`asyncio.to_thread(extract_text, …)`) se sustituye por **`@coco.fn.as_async`** (D60); (c) el **test que lo demuestra**: tocar la lógica del parser (o del troceo) **invalida** el memo del componente por fichero ⇒ el índice se rehace; (d) `deps`/`version` se usan donde el valor no es visible en el cuerpo (p. ej. el id del modelo si queda fuera de los argumentos) — si el modelo ya viaja en `config` (argumento), no hace falta `deps`; (e) **no** se añade memo de embeddings por chunk (D61: ~600 MB por 100k chunks); (f) el batching de embeddings según la op se **evalúa** (no se activa a ciegas): se mide con y sin y se reporta
  - Verificar: test de invalidación (rojo si se quita un `@coco.fn`) · `just python-test` verde · la métrica Δ comparable (T13)
  - 📌 **Por qué importa:** hoy, cambiar el parser **no** invalida el índice ⇒ resultados stale en silencio (bug verificado)
  - Dep.: T2 · Tamaño: M

- [x] **T6 · Una sola implementación de embedder (write y read) + modelo local**
  - Subagentes: `rag-pipeline-engineer` (lead), `python-pro`, `mcp-builder` · Skills: `source-driven-development`, `test-driven-development`, `debugging-and-error-recovery` · Herramientas: `context7`
  - AC: (a) el **write path** usa `cocoindex.ops.sentence_transformers.SentenceTransformerEmbedder` (ya lo hace) y el **read path** usa **la misma clase** (vía costura desde el composition root: el módulo `embedder` del MCP tiene `cocoindex` en su banned-set) ⇒ una sola implementación (D59); (b) la referencia del modelo es **inequívoca**: la config lleva `[embedding].model` (id, para mostrar) y `[embedding].revision` (SHA), y **ambos** caminos resuelven el **mismo path local** `<models>/<slug>@<sha>/` materializado por el wizard (la op acepta «name **or path**»); (c) el wizard (F6) materializa el modelo en ese directorio estable (no el layout interno de la caché de HF) y su import-check lo verifica; (d) si el snapshot no está ⇒ el read path responde **`E_MODEL_INVALID`** con guía («ejecuta `tepochcalli config embedder`»), **nunca** descarga otro modelo en silencio (que es el bug que se cierra); (e) `rag_status` sigue reportando `embedder.mode/model/dims` con la misma forma (el id, no el path); (f) la detección de drift `config.model ≠ fila.model` sigue funcionando y ahora **significa** lo mismo (mismo binario); (g) **la rama `api` deja de llamar a litellm directamente**: el MCP usa `cocoindex.ops.litellm.LiteLLMEmbedder` (construido en el composition root e inyectado por costura), y conserva **nuestro** mapeo de errores (`E_API_AUTH` por 401/403 o nombre de clase, `E_API_AUTH` sin clave antes de tocar la red) y **nuestro** scrub de la clave en los mensajes (la op no lo garantiza); (h) se documentan los rasgos de la op que cambian el comportamiento: **reintentos con backoff** en fallos transitorios (⇒ **TD-16 cerrada**), `timeout` propio de 10 min, batching de 64, y el caso de que un texto que empieza por `data:…;base64,` / `gs://` / `files/` se incruste con un espacio delante (afecta a **ambos** lados por igual ⇒ la búsqueda sigue siendo consistente)
  - Verificar: test que afirma que write y read resuelven **el mismo path** (no solo el mismo nombre) · test del snapshot ausente ⇒ `E_MODEL_INVALID` y **cero red** (el `nonet` de `tests/support/` lo permite) · la rama `api` usa la op (test con un doble de la op: el `E_API_AUTH` por 401/403 y el scrub de la clave se siguen produciendo) · el wizard: `cargo test` verde con el materializador del modelo · `just ci` verde
  - 📌 **Cierra el bug verificado:** hoy el índice se construye con «main» y la query se incrusta con un SHA pineado ⇒ modelos distintos
  - Dep.: T4, T5 · Tamaño: L

### ✅ CP-A · Contratos — **6/6** ⬜ (pendiente)

- [ ] ADR-009, ADR-010 y ADR-011 escritos (MADR, *Proposed*)
- [ ] WORKFLOW §8 con D28-D67 y §Phase 3.5 con el alcance nuevo
- [ ] `docs/UH.md` intacto y `just md-lint` sin errores
- [ ] `spec-markitdown` con el standalone retirado y la regla de oro
- [ ] `spec-rag-engine` con raíces recursivas, documentos y **el PDF sin headings**
- [ ] ▶️ **Desbloquea T2-T16.**

---

## Sub-fase C — Dominio puro y MCP del índice

- [ ] **T7 · Dominio puro: frontera B′, resumen, catálogo, escritor atómico**
  - Subagentes: `python-pro` (lead), `security-auditor`, `test-engineer` · Skills: `clean-ddd-hexagonal`, `test-driven-development`, `security-and-hardening` · Herramientas: `codebase-memory-mcp`
  - AC: (a) `paths.validate_vault_path(raw, vault_root, *, must_exist)` — dentro ⇒ ruta absoluta; fuera (absoluta fuera, `..` que escapa, symlink fuera) ⇒ `ValueError` → `VALIDATION_ERROR`; distingue entrada (debe existir) de salida (se crea el destino); (b) `paths.validate_roots(directories, vault_root)` — valida N raíces (mismas reglas + existencia, D44); (c) `summary.build_summary(...)` — dict de **5 claves en orden fijo** leyendo el **fichero escrito**; `preview` ≤500 chars; `truncated` correcto; (d) `summary.serialize_budget` — tope de 1 400 chars serializados; (e) `formats.SUPPORTED_FORMATS` — catálogo puro (sin `markitdown`), con la nota «sin OCR»; (f) `writer.write_atomic(target, content)` — **la misma** escritura atómica que usa `add_source` (sube de `tools/add_source.py`); (g) `errors.source_unreachable(..., guide=...)` admite la guía de OCR sin cambiar la forma del payload; (h) `paths.py` sigue **< 500 líneas**; (i) `paths.validate_vault_path` y `paths.validate_roots` comprueban **existencia y tipo** (D64): inexistente ⇒ `VALIDATION_ERROR` con `details: {requested, exists: false, suggestions[], vault_dirs[]}` (sugerencias por similitud **sin distinguir mayúsculas**: `Documentos` → `documentos`); tipo equivocado ⇒ `details: {expected, found}`; (j) `validate_roots` es **fail-fast atómico** (D65): si una raíz falla la validación, **no se indexa ninguna** y el error nombra la raíz mala + las que sí existen + las sugerencias; (k) `writer.write_atomic` aplica la **idempotencia** (D66): destino existente con contenido **idéntico** ⇒ no se escribe y se devuelve el mismo `written_to`; con contenido **distinto** ⇒ `VALIDATION_ERROR` («elige otro output_path») — **nunca** sobrescribe
  - Verificar: `just typecheck` verde · unit de los 4 módulos nuevos · test de arquitectura verde sin modificarlo · cobertura ≥95 % · test de `validate_roots` con 1 raíz mala entre 3 ⇒ **no se indexa ninguna** · test de idempotencia del escritor (idéntico ⇒ misma respuesta de éxito, sin clave `ok`; distinto ⇒ `VALIDATION_ERROR`) · test de sugerencias (`Documentos` ⇒ propone `documentos`)
  - Dep.: T1 · Tamaño: M

- [ ] **T8 · `index_refresh(directories=…)` + `rag_status` con las raíces**
  - Subagentes: `mcp-builder` (lead), `rag-pipeline-engineer` · Skills: `api-and-interface-design`, `test-driven-development` · Herramientas: `codebase-memory-mcp`
  - AC: (a) la firma pasa a `index_refresh(directories: list[str] | None = None)`; `None` ⇒ `["00-Resources"]` (D42); (b) `directories` se valida **antes** de la costura ⇒ raíz inexistente ⇒ `VALIDATION_ERROR` (D44); (c) la respuesta conserva las **5 claves** y **añade** `roots` (aditivo); (d) la costura de refresh pasa las raíces al motor; (e) `rag_status` **añade** `index.last_refresh_roots` (raíces de la última indexación **de la sesión**, en memoria — documentado); (f) `add_source` no cambia (D45); (g) `VALIDATION_ERROR` precede a `E_NO_EMBEDDER`; (h) el pre-chequeo de existencia ocurre en el **borde, antes de la costura** ⇒ una raíz inexistente **nunca** produce `INTERNAL` (OM-15); (i) **directorio vacío no es error**: `{scanned: 0, indexed: 0, skipped: 0}` + `roots` — el agente no lo lee como fallo; (j) `rag_status` **añade** `index.available_roots` (D67): los directorios de primer nivel del vault que son indexables (los de punto —`.tepochcalli/`, `.obsidian/`, `.trash/`— quedan fuera)
  - Verificar: unit con costura falsa · integration con dos raíces sobre `tempfile` · `index_refresh()` sin argumento indexa `00-Resources/` · raíz inexistente ⇒ `VALIDATION_ERROR` (y **nunca** `INTERNAL`) · N raíces con una mala ⇒ **nada indexado** · directorio vacío ⇒ `ok` con `scanned: 0` · `rag_status` trae `index.available_roots`
  - Dep.: T2, T3, T7 · Tamaño: M

### ✅ CP-B · Motor multi-raíz — **7/7** ⬜ (pendiente)

- [ ] `source_path` relativo al vault; walk recursivo y con dedup
- [ ] Raíz fuera / con `..` / inexistente ⇒ error tipado antes de tocar el disco; symlink fuera ⇒ `SYMLINK_ESCAPE`
- [ ] El walk **no baja** a los directorios excluidos: un `.md` dentro de `.tepochcalli/` **no** se indexa (la exclusión poda el subárbol)
- [ ] Golden-vault re-verificado (md + PDF) con el `source_path` nuevo
- [ ] `RefreshReport.roots` aditivo; `index_refresh` devuelve las 5 claves + `roots`
- [ ] `just typecheck` y `just coverage` verdes; test de arquitectura verde
- [ ] ▶️ **Desbloquea T3-T16.**

---

## Sub-fase D — Los tres caminos verticales del conversor

- [ ] **T9 · `convert_document`: borde B′ → costura → escritura → resumen → wire**
  - Subagentes: `mcp-builder` (lead), `python-pro`, `security-auditor` · Skills: `api-and-interface-design`, `test-driven-development`, `error-handling-patterns`, `source-driven-development` · Herramientas: `context7`, `gitmcp`
  - AC: (a) `convert.py` gana `convert_local(path, *, source_uri)` — markitdown en proceso, **sin frontmatter ni `converted_at`** (D36: un timestamp rompería la idempotencia de D66; el frontmatter de trazabilidad es exclusivo del artefacto de `add_source`); (b) el handler **no** importa `markitdown` (costura desde `server.py`); (c) firma `convert_document(path, output_path=None, format=None)`; (d) `path` y `output_path` pasan la frontera B′ de T7 (fuera ⇒ `VALIDATION_ERROR` **antes** de tocar el disco); (e) `output_path` omitido ⇒ `00-Resources/<slug>.md` (D37); `format` fuerza la extensión; (f) markdown vacío ⇒ `SOURCE_UNREACHABLE` con la guía «este conversor no hace OCR», sin parciales; `UnsupportedFormatException` ⇒ `VALIDATION_ERROR` con la lista; (g) la respuesta es **exactamente** el resumen de 5 claves, construido desde el fichero escrito; (h) la tool queda registrada en `server.py` con una `description` que dice «escribe a disco, devuelve solo el resumen» y que **no** es el camino de indexación (D49); (i) **test nuclear** (OM-1): el cuerpo del documento no aparece en `content[0].text` (documento ≥100 000 chars con una marca única); (j) `path` que **no existe** o que **es un directorio** ⇒ `VALIDATION_ERROR` (ni `INTERNAL` ni `SOURCE_UNREACHABLE`); (k) `output_path` ya existente ⇒ **idempotencia** (D66): contenido idéntico ⇒ **la misma respuesta de éxito** (5 claves, sin clave `ok`); distinto ⇒ `VALIDATION_ERROR`; (l) `add_source(file:)` con un `file:` **inexistente** ⇒ `VALIDATION_ERROR` (hoy muere como `SOURCE_UNREACHABLE` con un mensaje que culpa al documento — OM-15)
  - Verificar: unit con costuras falsas · integration con un `.docx` real sobre `tempfile` · `opencode mcp list` ⇒ 5 tools · negativos: path inexistente, path que es un directorio, `output_path` ya existente (idéntico ⇒ misma respuesta de éxito; distinto ⇒ `VALIDATION_ERROR`)
  - Dep.: T7, T8 · Tamaño: L

- [ ] **T10 · `convert_base64`: bytes en contexto → disco → resumen**
  - Subagentes: `mcp-builder` (lead), `python-pro` · Skills: `test-driven-development`, `error-handling-patterns`, `security-and-hardening` · Herramientas: `context7`
  - AC: (a) `convert.py` gana `convert_bytes(data, *, filename, extension, source_uri)` — markitdown con `BytesIO` + `StreamInfo(extension=…, filename=…)`; (b) firma `convert_base64(data, output_path=None, format=None, filename=None)`; (c) **exige `format` o `filename` con extensión conocida** (D38) ⇒ si no, `VALIDATION_ERROR` que nombra `list_formats`; (d) base64 inválido ⇒ `VALIDATION_ERROR` (no `INTERNAL`); (e) `output_path` con la frontera B′; (f) `source_uri` = el `filename` cuando vino (D38); sin `filename`, `base64:<sha256-8>` — la entrada tal como llegó, nunca inventada; (g) el mismo resumen de 5 claves; (h) el material es **dato no confiado** (OM-7); (i) `output_path` ya existente ⇒ la **misma** regla idempotente de T9 (D66)
  - Verificar: integration con un `.docx` en base64 ⇒ `.md` equivalente al de T9 · negativos (sin `format`, base64 corrupto, salida fuera del vault) · `opencode mcp list` ⇒ 6 tools
  - Dep.: T9 · Tamaño: M

- [ ] **T11 · `list_formats`: el catálogo de formatos, atado al motor**
  - Subagentes: `mcp-developer` (lead), `technical-writer` · Skills: `source-driven-development`, `clean-code` · Herramientas: `context7`
  - AC: (a) `list_formats()` sin argumentos devuelve `{formats, count, notes}` del catálogo; (b) la respuesta es **< 200 tokens**; (c) la nota aclara que **no hay OCR**; (d) un test ata cada extensión del catálogo a una conversión real (o a la lista de «best-effort»); (e) registrada en `server.py` con su `description`
  - Verificar: integration que itera el catálogo · < 200 tokens por el estimador de `budget` · `opencode mcp list` ⇒ 7 tools
  - Dep.: T10 · Tamaño: S

### ✅ CP-C · Documentos + dieta + embedder — **6/6** ⬜ (pendiente)

- [ ] `.docx/.pptx/.xlsx/.xls` indexados en su forma original, `doc_kind` propio, `offsets_ref="extract"`
- [ ] `uv.lock` regenerado; `uv sync --frozen` verde; `docling`/`torchvision`/`markitdown-mcp` fuera; venv ≤1,95 GB **medido**
- [ ] Editar el parser o el troceo **invalida** el índice (test que lo demuestra)
- [ ] Write y read resuelven **el mismo path** de modelo; sin snapshot ⇒ `E_MODEL_INVALID` (sin red)
- [ ] El wizard materializa `<models>/<slug>@<sha>/`; import-check con `markitdown`
- [ ] `just ci` verde
- [ ] ▶️ **Desbloquea T9-T16.**

---

## Sub-fase E — El contrato en el wire

- [ ] **T12 · Contract tests e2e: 7 tools, multi-raíz, documentos, change detection, embedder único**
  - Subagentes: `test-engineer` (lead), `mcp-builder`, `code-reviewer` · Skills: `test-driven-development`, `api-and-interface-design` · Herramientas: `codebase-memory-mcp`
  - AC: (a) **forma exacta** (orden de claves) de las 3 respuestas nuevas y de `index_refresh` con `roots`; (b) **presupuesto**: respuesta ≤1 400 chars, `preview` ≤500 (ES/EN y CJK documentados); (c) **test transversal**: ninguna de las 7 tools devuelve un artefacto (la marca única del cuerpo no aparece en ninguna respuesta); (d) **negativos**: entrada/salida fuera del vault, `..`, raíz inexistente (fichero **y** directorio), tipo equivocado, **N raíces con una mala ⇒ nada indexado**, formato no soportado, base64 sin pista, documento sin capa de texto, `output_path` ya existente con contenido distinto ⇒ todos `VALIDATION_ERROR`/`SOURCE_UNREACHABLE` con JSON canónico, y **ninguno** devuelve `INTERNAL` por una ruta mal escrita (OM-15); (e) las 4 tools preexistentes no cambian de forma salvo `roots`; (f) **caso de cita vault-relativa y recursiva** (`materiales/1-geografia/x.pdf`); raíz-fichero suelto; raíces solapadas contadas una vez; (g) **caso de documento**: un `.docx` indexado devuelve `source_path` vault-relativo y `offsets_ref="extract"`, y su texto == el `text` de la fila; (h) **caso de change detection**: tocar el parser invalida el índice (integrado en la suite, no solo unit); (i) **caso de embedder**: write y read usan el mismo path de modelo
  - Verificar: `just python-test` verde · el test transversal falla si alguien devuelve el markdown (comprobado rompiéndolo y revirtiendo) · `just coverage` ≥95 %
  - Dep.: T2, T3, T5, T6, T9, T10, T11 · Tamaño: L

- [ ] **T13 · e2e bulk ~1 000 páginas + re-medición (Δ, RSS, venv, métricas)**
  - Subagentes: `test-automation-engineer` (lead), `performance-benchmarker` · Skills: `test-driven-development`, `performance-analysis` · Herramientas: `codebase-memory-mcp`
  - AC: (a) fixture sintético de **~1 000 páginas** (≥1 MB, generado en el test) + 20 ficheros de familias distintas; (b) las **21 conversiones** devuelven el resumen y ningún cuerpo; (c) el contenido íntegro queda en disco y el `preview` es ≤500 chars; (d) presupuesto verificado por respuesta y por suma; (e) **re-medición del motor** (n=20, nearest-rank, publicando n y método): Δ p95 con raíces múltiples y metadatos de cita al 100 % con `source_path` vault-relativo; (f) el **RSS pico** del Δ con documentos binarios (el perfil de TD-2 cambia: sin Docling) y el coste de los documentos **medido aparte** (D51); (g) el tamaño del venv y el nº de paquetes **medidos** (M9); (h) el tiempo del bulk se mide y se publica, sin aserción de latencia (regla anti-flake); (i) el test queda `slow`
  - Verificar: `just python-test-slow` verde · el informe publica n, corpus, presupuesto, Δ p95, RSS pico, coste de documentos y tamaño del venv · si algo se degrada, **se reporta**
  - Dep.: T12 · Tamaño: M

### ✅ CP-D · Dominio puro y MCP del índice — **8/8** ⬜ (pendiente)

- [ ] `validate_vault_path`/`validate_roots` cubren todas las formas de escape
- [ ] Existencia **y tipo** en el borde: ruta inexistente, tipo equivocado y N-raíces-con-una-mala ⇒ `VALIDATION_ERROR` con `details.suggestions`; **fail-fast atómico** (no se indexa ninguna)
- [ ] `build_summary`: 5 claves en orden fijo, `preview` ≤500, ≤1 400 chars
- [ ] `write_atomic` es la MISMA función que usa `add_source`
- [ ] `index_refresh(directories=…)` indexa lo pedido; `None` ⇒ `00-Resources/`; raíz inexistente ⇒ `VALIDATION_ERROR`; **directorio vacío no es error**
- [ ] `rag_status` reporta las raíces de la sesión **y** `index.available_roots`
- [ ] Test de arquitectura verde sin excepciones
- [ ] ▶️ **Desbloquea T9-T16.**

---

## Sub-fase F — Payload y skill

- [ ] **T14 · Payload: retirar la entrada `markitdown` y arreglar el test de merge**
  - Subagentes: `mcp-builder` (lead), `code-reviewer` · Skills: `git-workflow-and-versioning`, `clean-code` · Herramientas: `opencode` (MCP)
  - AC: (a) `opencode.json` **deja de registrar** `mcp.servers.markitdown` (D29); (b) `anydoc` sigue `disabled: true` (D30) y `excel`/`jupyter` intactos; (c) `MANAGED_KEYS` incluye `anydoc` (D40) con el docstring explicando el fixture pre-T9; (d) **sin cambios en Rust** (F8 ya borra `markitdown`, D19) — `cargo test` verde sin tocar `crates/`; (e) el resto del JSON byte-idéntico; (f) JSON estricto con la forma de `tepochcalli-rag` (`python -m`, D17)
  - Verificar: `just python-test-unit` verde (el test de merge deja de estar rojo) · `cargo test` verde · `opencode mcp list` sin `markitdown`
  - Dep.: T1 (paralelo con T2-T13) · Tamaño: S

- [ ] **T15 · Skill `tepochcalli-mcp` (H4) en el payload**
  - Subagentes: `prompt-engineer` (lead), `technical-writer`, `obsidian-vault-writer` · Skills: `opencode-skill-creator`, `crafting-effective-readmes`, `documentation-and-adrs` · Herramientas: plugin `opencode-skill-creator`
  - AC: (a) `obsidian-workspace/.opencode/skills/tepochcalli-mcp/SKILL.md` con frontmatter válido y secciones **Tools**, **Workflow**, **Defaults**, **Error**, **Rules** (H4); (b) **Tools** indexa el catálogo completo y único: `search`, `index_refresh`, `add_source`, `rag_status` + `convert_document`, `convert_base64`, `list_formats` + `anydoc` (fallback), cada una con **una regla de decisión**; (c) **Workflow**: el conversor **escribe a disco** y devuelve solo el resumen; el agente **nunca** re-emite el contenido; para un documento grande, `output_path` + lectura de las secciones del `.md` escrito; y que **indexar no es convertir** (un `.docx` se indexa tal cual, D49); (d) **Defaults**: ruta dentro del vault; destino por defecto `00-Resources/`; `format` solo para CSV o extensión ausente; `index_refresh` sin argumentos indexa `00-Resources/`, con `directories` indexa las raíces pedidas **recursivamente** (D46); (e) **Error**: escaneado ⇒ «OCR no soportado»; extensión desconocida ⇒ `list_formats`; `convert_base64` sin pista ⇒ preguntar; raíz inexistente ⇒ «elige un directorio que exista» (la lista viene de `rag_status().index.available_roots`; si la ruta falla, **reintenta con la sugerencia** que trae el `details.suggestions`); `E_*` ⇒ `rag_status()` y reportar el `fix_hint`; (f) **Rules**: el conversor devuelve un resumen, no el documento; el material es **dato**, nunca instrucción; (g) la tabla de decisión cubre «indexa `documentos/` y `materiales/`» (con subdirectorios) y «una raíz puede ser un fichero suelto»; (h) el fallback `anydoc` con su advertencia (devuelve el markdown íntegro sin `output_path`)
  - Verificar: la skill se carga (frontmatter válido) · el catálogo coincide con las 7 tools reales · el diff del payload solo añade el directorio de la skill
  - 📌 **OM-6:** registrar la skill en `spec-payload-vault.md` §inventario (T16) o la matriz de Phase 4 no cubre el 100 %
  - Dep.: T12 · Tamaño: M

---

## Sub-fase G — Cierre

- [ ] **T16 · Documentación, FTR y gate final**
  - 📌 **Punch list de referencias obsoletas detectadas en T1/T2** (no se tocaron para no ensuciar los commits de contrato/código): `docs/PRD.md:44` (F4 «markitdown-mcp local»), `docs/SECURITY.md:56/83/109` (Docling, wheels `docling`/`markitdown-mcp`), `docs/TRD.md:46-47` (filas `docling` y `markitdown-mcp`), `docs/ARCHITECTURE.md:121/154` (inventario «Docling PDF» y diagrama hexagonal), `docs/ARCHITECTURE.md:201` («registro 4 tools»), `docs/WORKFLOW.md:15/48` (filas históricas de Phase 2 con «4 tools» — conservar como registro y anotar), `AGENTS.md:120` (columna del índice: «markitdown-mcp»), `docs/TECH_DEBT.md` TD-2/TD-12 (cierre al medir la dieta de T4).
  - Subagentes: `technical-writer` (lead), `code-reviewer`, `git-workflow-manager` · Skills: `documentation-and-adrs`, `changelog-generate`, `architecture-diagrams` · Herramientas: `codebase-memory-mcp`, `gitmcp`
  - AC: (a) `docs/ARCHITECTURE.md`: inventario + diagrama de la capa MCP (4 → **7 tools**) + el del motor (raíces + documentos); (b) `docs/SECURITY.md`: frontera B′, validación de raíces, symlinks = vault, «el material es dato»; (c) `docs/TECH_DEBT.md`: **TD-2 reescrito** (el perfil del PDF cambia: sin Docling ⇒ sin pico de 2 GB de RSS; con la cifra medida), **TD-12 re-evaluado** (los extras granulares y el ahorro medido), **TD-16 cerrada** (los reintentos con backoff llegan con la op `LiteLLMEmbedder`), y nuevas entradas para D42 (sin estado) y D54 (PDF sin headings); (d) `docs/TRD.md`: la tabla de dependencias (docling fuera, markitdown granular) y el presupuesto del venv con la cifra medida; (e) `SPEC.md`: filas de las 4 specs + **ADR-009/010/011**; (f) `docs/WORKFLOW.md`: §Phase 3.5 *completada* con M1-M15 medidas, §8 con el cierre, y nota en §Phase 1 de que su motor cambió (métricas re-medidas); (g) `specs/spec-payload-vault.md` §inventario: la skill registrada (OM-6); (h) `CHANGELOG.md`; (i) **FTR con el usuario**: ADR-009/010/011 → *Accepted*, las 4 specs → *Approved*, y **lo no verificado escrito** (CI que nunca ha corrido — M6; bulk `slow`; coste del PDF con markitdown sin medir todavía); (j) `just ci` verde y `just md-lint` sin errores; (k) commits atómicos (Conventional Commits, ≤72 cols, trailer `Co-Authored-By`)
  - Verificar: `just ci` verde · `just md-lint` sin errores · mermaid renderizan · `git status --short` solo con lo intencionado
  - Dep.: T13, T14, T15 · Tamaño: M

### ✅ CP-E · Las tres tools — **7/7** ⬜ (pendiente)

- [ ] `convert_document`, `convert_base64` y `list_formats` operativas (7 tools)
- [ ] El cuerpo del documento no aparece en el wire (test nuclear)
- [ ] Entrada/salida fuera del vault ⇒ `VALIDATION_ERROR`; raíz inexistente ⇒ `VALIDATION_ERROR`; formato no soportado ⇒ `VALIDATION_ERROR`
- [ ] Path **inexistente** o que **es un directorio** ⇒ `VALIDATION_ERROR` (nunca `INTERNAL`); destino existente ⇒ **idempotente** (idéntico ⇒ la misma respuesta de éxito, sin clave `ok`; distinto ⇒ `VALIDATION_ERROR`, nunca se sobrescribe)
- [ ] Documento escaneado ⇒ `SOURCE_UNREACHABLE` con guía de OCR, sin parciales
- [ ] `index_refresh(directories=…)` indexa las raíces pedidas; `source_path` vault-relativo; documentos nativos
- [ ] `opencode mcp list`: 7 tools
- [ ] ▶️ **Desbloquea T12-T16.**

### ✅ CP-F · Cierre de fase — **6/6** ⬜ (pendiente)

- [ ] Contract tests e2e verdes (formas, presupuesto, transversal, multi-raíz, documentos, change detection, embedder)
- [ ] Test transversal: ninguna de las 7 tools devuelve un artefacto
- [ ] e2e bulk 1000 páginas + métricas del motor re-medidas y publicadas (n y método) + venv medido
- [ ] Payload sin `mcp.servers.markitdown`; `anydoc` `disabled: true`; skill `tepochcalli-mcp` en el payload
- [ ] `just ci` verde + `just md-lint` sin errores + **FTR con el usuario** (y lo no verificado, escrito)
- [ ] ▶️ **Cierra Phase 3.5** y abre Phase 4 (blueprint) sin cambios en su alcance.
