# TODO — Phase 3: Wizard Rust `tepochcalli`

> Detalle completo en [tasks/plan.md](plan.md). Orden impuesto por el grafo de dependencias.
> Regla de la casa: **una calpulli = un camino completo**, con criterio de aceptación y
> verificación. Nada de Phase 4-5 (payload de agents/commands/skills del vault).

**Rama:** `feat/workspace-obsidian` · **Fuente:** [docs/WORKFLOW.md](../docs/WORKFLOW.md) §Phase 3
**Rama de código:** `crates/tepochcalli/` · **Rama de tests:** `crates/tepochcalli/tests/`
**Rama de código Python (tocada):** `obsidian-workspace/.tepochcalli/flow/tepochcalli_flow/` (solo T12)
**Historial:** este fichero sustituye al TODO de Phase 2, que se conserva íntegro en el
historial de git (`git show a070385:tasks/todo.md`).

---

## Sub-fase A — Anclaje y contratos (fail-fast)

- [x] **T1 · Reconciliar contratos: el §Merge de la spec y las olas D19-D27**
  - Subagentes: `technical-writer` (lead), `code-reviewer` · Skills: `documentation-and-adrs`, `spec-driven-development`, `clean-code`
  - AC: (a) `specs/spec-installer-wizard.md` §Merge deja de registrar `mcp.servers.markitdown` y explica que la conversión es **en proceso** (D19); (b) el §Merge dice que el comando del MCP se **genera por SO** (`venv/bin/python` POSIX · `venv/Scripts/python.exe` Windows) (D20); (c) la *Open Question* de `--resume` queda **resuelta** como «deducir por artefactos + marker `.install-state`» (D21); (d) la spec documenta que el wizard crea `00-Resources/` + placeholders (D22) y que el TUI es line-based (D23); (e) `docs/WORKFLOW.md` §8 registra las olas D19-D27 con su justificación; (f) la spec sigue en *Proposed* (el paso a *Approved* es T20, con FTR)
  - Verificar: `just md-lint` verde · `grep -n "markitdown" specs/spec-installer-wizard.md` no devuelve la entrada de registro · el diff de §8 es aditivo (no reescribe olas previas)
  - 📌 **Por qué primero:** la spec es el contrato que T3-T13 implementan; si el §Merge sigue diciendo `markitdown`, T13 implementaría el contrato equivocado.
  - Dep.: — · Tamaño: S

- [x] **T2 · Spike fail-fast: extracción de archivos segura + bootstrap de `uv` portable**
  - Subagentes: `rust-engineer` (lead), `security-auditor` · Skills: `test-driven-development`, `security-and-hardening`, `error-handling-patterns`, `doubt-driven-development`
  - AC: (a) existe un extractor capaz de desenvolver un `.tar.gz` **y** un `.zip` en un directorio destino; (b) **rechaza** con error tipado las 4 clases de ataque: `../` en el nombre (`zip-slip`/`tar-slip`), ruta absoluta POSIX (`/etc/passwd`), ruta absoluta Windows (`C:\...`), y symlink con destino absoluto o fuera del destino; (c) la comprobación ocurre **antes** de escribir en disco (test que verifica que el destino queda intacto); (d) se puede descargar el binario de `uv` de la release oficial **por plataforma** (`x86_64`/`aarch64` × linux/macos), verificar su SHA-256, dejarlo ejecutable y obtener `uv --version`; (e) el spike **no** usa scripts remotos (`install.sh`/`install.ps1`): solo artefactos released con checksum
  - Verificar: `cargo test` verde con los 4 casos de ataque como tests nominales (no `xfail`) · spike manual en linux y macos · **el AC de `cargo clippy -D warnings` limpio**
  - 📌 **Omen mayor OM-1**: un instalador que escribe en el vault del usuario es un extractor de archivos Writing-Outside-Dir. Este AC bloquea F3 y F4: no se avanza a verde sin él.
  - Dep.: T1 · Tamaño: M

- [x] **T3 · Esqueleto del crate: `Cargo.toml`, CLI y dominio**
  - Subagentes: `rust-engineer` (lead), `cli-developer` · Skills: `clean-ddd-hexagonal`, `design-patterns`, `solid`, `error-handling-patterns`
  - AC: (a) `crates/tepochcalli/Cargo.toml` con `name = "tepochcalli"`, `edition = "2021"`, binario `tepochcalli`; (b) `src/domain/` con `Phase` (F1..F8), `PhaseState`, `InstallPlan`, `VaultPath`, `EmbedderChoice`, `Badge`, `ResourceFacts`, `InstallOutcome` (`Ok` | `Degraded`), `WizardError` y `ExitCode`; (c) `ExitCode` respeta los rangos de la spec (0 · 10-19 · 20-29 · 30-39 · 40+) con el mapeo de §5.4 del plan; (d) `src/main.rs` con subcomandos `install`, `config embedder`, `reindex`, `uninstall` y `--help`/`--version` por subcomando; (e) `domain/` **no** importa nada de `adapters/` ni crates de infra (se comprueba en T4); (f) versionado semver del crate alineado con la release del payload (regla one-version)
  - Verificar: `cargo build`, `cargo test`, `cargo fmt --check`, `cargo clippy -D warnings` verdes · `tepochcalli --help` y `tepochcalli install --help` imprimen uso legible
  - Dep.: T2 · Tamaño: M

- [x] **T4 · Los 5 puertos + fakes + test de arquitectura**
  - Subagentes: `rust-engineer`, `test-engineer` · Skills: `clean-ddd-hexagonal`, `api-and-interface-design`, `test-driven-development`
  - AC: (a) `ports/` define `CommandRunner`, `HttpClient`, `HostProbe`, `PayloadSource`, `Ui` con **firma mínima** (nada de opciones "para luego"); (b) `tests/common/mod.rs` trae `FakeProc` (guion de respuestas por comando), `FakeHttp` (offline, 404, cuerpo corrupto), `FakeHost` (RAM/disco/GPU configurables) y `ScriptedUi` (respuestas predefinidas por pregunta); (c) `tests/architecture.rs` falla si `domain/` importa `adapters/`, `std::fs`, `std::process` o crates de infra (réplica de `tests/unit/test_architecture.py` del flow); (d) **no** hay puerto `FileSystem`: los tests de FS usan `tempfile` real (D26); (e) cada puerto tiene **al menos un test** que lo ejercita
  - Verificar: `cargo test` verde · el test de arquitectura **falla** si se añade `use std::fs` a `domain/` (se comprueba rompiéndolo a mano y revirtiendo)
  - Dep.: T3 · Tamaño: M

- [x] **T5 · Adapters reales: `std_proc`, `http`, `host` (sysinfo + probe de GPU)**
  - Subagentes: `rust-engineer`, `platform-engineer` · Skills: `source-driven-development`, `error-handling-patterns`, `performance-analysis`
  - AC: (a) `CommandRunner` real ejecuta con `cwd` y `env` dados, captura stdout/stderr y el exit code, y **no** usa `shell = true` salvo que el comando lo exija explícitamente; (b) `HttpClient` real: GET con timeout, redirecciones limitadas y descarga a fichero con **verificación SHA-256** (falla si no coincide); (c) `HostProbe` real con `sysinfo`: RAM total/disponible y disco libre; (d) probe de GPU **opcional**: busca `nvidia-smi` y `rocm-smi` en el PATH; **ausencia = "no hay GPU", no es error**; (e) el sondeo **nunca** hace que la instalación crashee: si `sysinfo` falla, se devuelven valores `None` y el menú cae a los valores declarados de `presets.toml` **sin badge** (D8.2)
  - Verificar: tests unitarios con `FakeHost` para la lógica de badges (T10) · test de `HttpClient` con SHA-256 incorrecto ⇒ error tipado · `cargo clippy -D warnings` limpio
  - Dep.: T4 · Tamaño: M

- [x] **T6 · UI: `TtyUi` (dialoguer) + `HeadlessUi` (`--non-interactive`)**
  - Subagentes: `cli-developer` (lead), `rust-engineer` · Skills: `clean-code`, `test-driven-development`, `crafting-effective-readmes`
  - AC: (a) `TtyUi` implementa `Ui` sobre `dialoguer`: `Select` con default preseleccionado, `Input` para texto, `Confirm` para confirmaciones; (b) `HeadlessUi` lee las respuestas de flags (`--skip-model`, `--non-interactive`) y **falla con error tipado** si le falta una respuesta (nunca adivina); (c) la TUI **nunca** se usa cuando no hay TTY: `--non-interactive` es obligatorio en CI; (d) los mensajes van a **stderr** y el resultado a stdout (para que el pipeline sea parseable); (e) el `panel` de error se renderiza en color cuando la salida es un terminal y en texto plano cuando no
  - Verificar: test con `ScriptedUi` que recorre el menú completo sin TTY · `tepochcalli install --non-interactive --skip-model` no intenta leer de stdin
  - Dep.: T4 · Tamaño: S

### ✅ CP-A · Anclaje — **6/6** ⬜ (pendiente)

- [ ] §Merge de la spec corregido (D19, D20) y olas D19-D27 en WORKFLOW §8
- [ ] Extracción segura: 4 clases de ataque rechazadas por test
- [ ] `cargo build`, `cargo fmt --check`, `cargo clippy -D warnings` y `cargo test` verdes
- [ ] Test de arquitectura: `domain/` no importa `adapters/` ni crates de infra
- [ ] `tepochcalli --help` y `--help` por subcomando funcionan
- [ ] `just quality` (gate Python) sigue verde
- ▶️ **Desbloquea T7-T13.**

---

## Sub-fase B — Las 8 fases (el camino de instalación)

- [x] **T7 · F1 detección de prerrequisitos + F2 directorio del vault**
  - Subagentes: `rust-engineer`, `platform-engineer` · Skills: `error-handling-patterns`, `clean-code`
  - AC: (a) F1 comprueba SO/arquitectura soportados, RAM (≥ 8 GB) y disco libre (≥ 4 GB); (b) detecta **Obsidian** y **OpenCode V2** si están presentes y **solo avisa** si faltan (la spec los pone en *Non-Goals*: no se instalan); (c) RAM < 8 GB ⇒ **aborta** con mensaje de requisitos y exit code 10-19 (spec-embeddings: no se instala «mitad»); (d) F2 elige el directorio del vault: `--vault <ruta>` lo fija; sin flag, la TUI pregunta con un default sensato; (e) si el directorio ya existe ⇒ se **reutiliza** (idempotencia), nunca se borra ni se sobreescribe contenido; (f) F1 y F2 **no se compensan** (no tocaron nada del usuario)
  - Verificar: tests con `FakeHost` (RAM 4 GB ⇒ aborta con 10-19; RAM 16 GB ⇒ pasa) · `--vault` no interactivo · 2ª corrida detecta el vault existente
  - Dep.: T6 · Tamaño: M

- [x] **T8 · F3 extraer el payload + `.install-intent` + `00-Resources/` + placeholders**
  - Subagentes: `rust-engineer` (lead), `security-auditor` · Skills: `security-and-hardening`, `test-driven-development`, `clean-code`
  - AC: (a) `PayloadSource` con dos adapters: `ReleasePayload` (asset `tepochcalli-workspace-<ver>.tar.gz` de la release + SHA-256) y `LocalPayload` (`--payload <ruta>`, para dev y tests); (b) la extracción **no sobreescribe** ningún fichero existente del usuario: los coincidentes se dejan intactos y se anotan como «ya estaba»; (c) **no toca** `.obsidian/` ni nada fuera del vault; (d) escribe `.tepochcalli/.install-intent` con la **lista exacta** de ficheros escritos (base de la compensación de F3); (e) crea `00-Resources/` con el **case exacto** que indexa el flow (`citation.py:32` → `00-Resources`) y deja 2 placeholders: 1 `.md` y 1 `.pdf` (D22) — el PDF va embebido en el crate (`include_bytes!`), no en el repo del payload; (f) el `.pdf` placeholder es un PDF válido y parseable por Docling; (g) **no** crea `02-drafts/`/`03-citations/`/`04-review/`/`05-outputs/` (eso es Phase 5, TD-8)
  - Verificar: test con `tempfile` y un payload fake que contiene un fichero que el usuario ya tiene ⇒ ese fichero queda **intacto** y el resto se copia · `.install-intent` coincide con lo escrito · Docling parsea el PDF placeholder
  - 📌 **OM-4 cerrado aquí**: sin este AC, F7 no puede producir índice.
  - Dep.: T7 · Tamaño: L

- [ ] **T9 · F4 bootstrap de `uv` + F5 `uv venv`/`uv sync` + fix de R6**
  - Subagentes: `rust-engineer` (lead), `devops-engineer`, `dependency-manager` · Skills: `bash-defensive-patterns`, `dependency-audit`, `debugging-and-error-recovery`
  - AC: (a) F4 descarga el binario de `uv` de la release oficial para la plataforma, **verifica su SHA-256**, lo deja en `.tepochcalli/bin/uv` con bit de ejecución y comprueba `uv --version`; (b) F4 **no** ejecuta scripts remotos; (c) F5 crea el venv **en `.tepochcalli/venv/`** (con `UV_PROJECT_ENVIRONMENT=venv`, quirk de uv 0.12.9) y ejecuta `uv sync --frozen` con el `uv.lock` del payload; (d) **R6**: `pyproject.toml` del payload pasa a declarar `tepochcalli_mcp.tools` (explícito o `find`) ⇒ **verificación**: `python -c "import tepochcalli_mcp.tools.search"` dentro del venv del vault; (e) las compensaciones son `rm .tepochcalli/bin/` (F4) y `rm -rf .tepochcalli/venv/` (F5), y **no tocan** `models/`, `db/` ni `config/`; (f) `uv python install 3.12` (CPython gestionado) deja el intérprete en `.tepochcalli/venv/`
  - Verificar: `cargo test` con `FakeProc` que simula el fallo de `uv` ⇒ compensación ejecutada y `bin/`/`venv/` ausentes · instalación real en `tempfile` con red ⇒ `uv --version` y `import tepochcalli_mcp.tools.search` OK · **R6 cerrado** (anotado en `docs/TECH_DEBT.md`)
  - Dep.: T8 · Tamaño: M

- [ ] **T10 · F6a: `presets.toml` embebido + parser + badges D8.1/D8.2/D8.3**
  - Subagentes: `rust-engineer`, `test-engineer` · Skills: `source-driven-development`, `test-driven-development`, `clean-code`
  - AC: (a) `src/config/presets.toml` embebido con `include_str!` (D7.2: **datos, no UI**) con los campos de D8.1 (`name`, `hf_id`, `dims`, `size_mb`, `disk_mb`, `min_ram_gb`, `rec_ram_gb`, `gpu_recommended`, `recommended_flag`); (b) el parser **falla con error tipado** ante un preset mal formado (no en silencio); (c) la función de badge computa el ratio `rec_ram_gb` / RAM disponible ⇒ `recommended` (≥ 50 % margen) · `viable` · `no recomendado` (excede RAM **o** `gpu_recommended` && sin GPU); (d) **fixture host 4 GB**: MiniLM = `recommended`, `BAAI/bge-m3` = `no recomendado`; (e) `no recomendado` **no bloquea** la selección (D8.3 — el test elige `bge-m3` y el menú lo acepta); (f) si el sondeo del host falla ⇒ **sin badge** y se usan los valores declarados, sin crash
  - Verificar: tests de la tabla de badges con `FakeHost` (4 GB, 8 GB, 16 GB, sin GPU, con GPU) · el caso «sin GPU» con `gpu_recommended = true` ⇒ `no recomendado` pero seleccionable
  - Dep.: T9 · Tamaño: M

- [ ] **T11 · F6b: menú de 5 salidas + gate test-embed + config atómico**
  - Subagentes: `rust-engineer` (lead), `test-engineer`, `security-auditor` · Skills: `test-driven-development`, `security-and-hardening`, `error-handling-patterns`
  - AC: (a) el menú presenta las 5 salidas de D7.1 con **default preseleccionado** = `paraphrase-multilingual-MiniLM-L12-v2`; (b) cada fila muestra `💾 disk (MB)` · `🧠 RAM` · `🎮 GPU` **con etiqueta de procedencia** (`medido` | `estimado` | `declarado`); (c) salida 3 (ID libre de HF) consulta la API de HF para estimar RAM/disco (`safetensors.parameters.total` → RAM = params × 4 B × 1.3) y avisa de `HF_TOKEN` si el repo es `gated`; (d) **gate test-embed**: para las salidas 1-3 el flow Python descarga el modelo, incrusta `"tepochcalli embedding check"` y devuelve dims + **RSS pico medido** (D25) — el RSS aparece en la fila con etiqueta `medido`; (e) la salida 3 actúa de **portero**: un repo HF que no es de embeddings ⇒ rechazo con `E_MODEL_INVALID` y **vuelta al menú sin escribir config**; (f) `config/tepochcalli.toml` se escribe **atómicamente** (fichero temporal + rename) **solo** tras un gate OK — nunca queda config a medias; (g) salida 4 (API externa) pide la clave, la escribe **solo** en `.tepochcalli/config/tepochcalli.toml` (gitignored) y **nunca** en logs, `opencode.json` ni el `.env` del repo; (h) salida 5 = "configurar después" ⇒ `provider = "none"`, RAG `degraded`, **sin** indexación inicial
  - Verificar: `ScriptedUi` recorre las 5 salidas · el repo HF no-embedding ⇒ rechazo sin escribir config · la clave de la salida 4 no aparece en el log (test de redacción) · config escrito de forma atómica (test que interrumpe la escritura ⇒ el fichero original intacto)
  - Dep.: T10 · Tamaño: L

- [ ] **T12 · F7 índice inicial + CLI `python -m tepochcalli_flow` (`refresh`, `embed-check`)**
  - Subagentes: `rust-engineer` (lead), `rag-pipeline-engineer`, `python-pro` · Skills: `incremental-implementation`, `observability-and-instrumentation`
  - AC: (a) **CLI nuevo y mínimo** en `flow/tepochcalli_flow/__main__.py` con 2 subcomandos: `refresh` (indexa y devuelve el `RefreshReport` en JSON) y `embed-check --model <id>` (descarga, incrusta la frase de control, devuelve `{ok, model, dims, rss_peak_bytes}`) (D24); (b) el RSS pico se mide **dentro** del proceso Python (`resource.getrusage().ru_maxrss`) y se **normaliza a bytes** (KB en Linux, bytes en macOS) — con test que documenta la diferencia por plataforma (OM-6); (c) el wizard invoca ese CLI con el venv del vault y `HF_HOME`/`SENTENCE_TRANSFORMERS_HOME` apuntando a `.tepochcalli/models/`; (d) F7 deja índice con chunks de los 2 placeholders y escribe `model` + `dims` en los metadatos del índice (`.tepochcalli/db/`); (e) **2ª corrida ⇒ `indexed: 0`** (idempotencia del índice) y 0 duplicados; (f) la salida 5 **omite F7** (no hay índice) y el vault queda completo
  - Verificar: `python -m tepochcalli_flow refresh` sobre un vault temporal ⇒ JSON con `{scanned, indexed, skipped, elapsed_ms}` · `embed-check` con un modelo malo ⇒ `ok: false` con el código esperado · la suite Python existente (`just quality`) sigue verde tras tocar `flow/`
  - Dep.: T11 · Tamaño: M

- [ ] **T13 · F8 merge de `mcp.servers` + `.bak` + comando portable por SO + verificación e2e**
  - Subagentes: `rust-engineer` (lead), `mcp-builder`, `security-auditor` · Skills: `api-and-interface-design`, `clean-code`, `test-driven-development`
  - AC: (a) copia de seguridad `.bak` de `opencode.json` **antes** de escribir; la compensación restaura el original byte a byte; (b) merge **conservador**: se preservan **todas** las entradas `mcp.servers` que ya tenía el usuario (p. ej. `excel`, `jupyter`) y solo se gestiona `tepochcalli-rag`; (c) `tepochcalli-rag` se (re)escribe **solo si difiere** de lo esperado, con el comando **portable por SO** (D20: `venv/bin/python` POSIX · `venv/Scripts/python.exe` Windows), `cwd` = vault y `TEPOCHCALLI_ROOT` = vault; (d) **no** se registra `mcp.servers.markitdown` (D19) — y si el usuario la tuviese, se **elimina** (política del payload, `MANAGED_KEYS` del test existente); (e) el JSON se conserva legible (2 espacios, misma forma que el payload) y **atómico**; (f) verificación e2e: lanzar el MCP desde el venv del vault y llamar `rag_status` ⇒ `health.state` correcto (`ok` o `degraded` con `fix_hint`) y la forma exacta de 4 bloques que fija `spec-mcp-server`; (g) la idempotencia de F8: 2ª corrida ⇒ **cero** entradas duplicadas
  - Verificar: test con un `opencode.json` del usuario que tiene 2 servers extra ⇒ se preservan · el `.bak` es idéntico al original · el test existente `tests/unit/test_opencode_payload_registration.py` sigue verde · e2e de `rag_status` en los dos estados
  - Dep.: T12 · Tamaño: L

### ✅ CP-B · Las 8 fases — **6/6** ⬜ (pendiente)

- [ ] Las 8 fases se ejecutan en orden sobre un `tempfile` real
- [ ] Cada fase tiene compensación ejecutada y probada
- [ ] `00-Resources/` canónico creado con 2 placeholders; el flow lo encuentra (case exacto)
- [ ] `uv` en `.tepochcalli/bin/`, venv en `.tepochcalli/venv/`, `import tepochcalli_mcp.tools.search` OK (R6 cerrado)
- [ ] `.tepochcalli/{config,models,db,venv,bin}` gitignorados; ningún secreto en logs
- [ ] Ningún fichero del usuario preexistente fue sobrescrito
- ▶️ **Desbloquea T14-T17.**

---

## Sub-fase C — Atomicidad y superficie post-instalación

- [ ] **T14 · Compensaciones por fase + `--resume` + `--offline` + idempotencia**
  - Subagentes: `rust-engineer` (lead), `test-engineer`, `chaos-engineer` · Skills: `test-driven-development`, `debugging-and-error-recovery`, `doubt-driven-development`
  - AC: (a) **test de fallo inducido en las 8 fases**: se inyecta el fallo en cada fase y se comprueba que la compensación se ejecuta y que **no se pierde ningún dato del usuario** (el comparador es «el árbol del vault antes y después, salvo lo que la fase escribió»); (b) `--resume` reanuda desde la fase correcta usando **artefactos + marker** `.tepochcalli/.install-state` (D21), no re-ejecuta las fases ya completadas y **no** re-descarga lo ya descargado; (c) `--offline`: sin red ⇒ payload local + modelo cacheado; si falta lo necesario ⇒ **fallo limpio** `E_OFFLINE_NO_CACHE` (exit 21) **antes** de tocar el vault; (d) **idempotencia**: install ×2 ⇒ 0 duplicados en `opencode.json`, 0 duplicados en `00-Resources/`, `indexed: 0` en la 2ª pasada; (e) `--skip-model` = salida 5 exacta (no interactivo, sin índice, RAG degraded); (f) la compensación de F6 cae a **salida 5** (instalación COMPLETA degradada), no a "instalación fallida"
  - Verificar: 8 tests de fallo inducido (uno por fase) · test de `--resume` que corta la instalación en F5 y la reanuda · test de `--offline` sin caché ⇒ vault intacto · test de install ×2
  - Dep.: T13 · Tamaño: L

- [ ] **T15 · UX de fallo: panel, log y códigos de salida**
  - Subagentes: `cli-developer` (lead), `technical-writer`, `security-auditor` · Skills: `error-handling-patterns`, `crafting-effective-readmes`, `security-and-hardening`
  - AC: (a) el fallo imprime un panel con **fase fallida**, **causa**, **comando de reintento** (`tepochcalli install --resume`) y **ruta del log**; (b) el log vive en `$XDG_STATE_HOME/tepochcalli/install-<ts>.log` (o `%LOCALAPPDATA%` en Windows) y **nunca** dentro del vault; (c) los códigos de salida respetan los rangos de la spec y el mapeo de §5.4 del plan; (d) **redacción**: la clave de la salida 4 nunca aparece en el log, en el panel ni en la salida de `opencode.json`; (e) el panel va a stderr y el resultado a stdout
  - Verificar: test que inyecta un error y comprueba el contenido del panel y del log · test de redacción con una clave falsa que **no** aparece en ningún artefacto · el log no está bajo el vault
  - Dep.: T14 · Tamaño: M

- [ ] **T16 · Swap atómico D8.4 (`tepochcalli config embedder`)**
  - Subagentes: `rust-engineer` (lead), `test-engineer`, `security-auditor` · Skills: `test-driven-development`, `doubt-driven-development`, `clean-ddd-hexagonal`
  - AC: (a) los 6 pasos de D8.4 en orden: mostrar estado actual (modelo, dims, filas, tamaño de db, forma de `rag_status`) → elegir embedder (mismo menú + badges) → **advertencia** de re-index completo (LanceDB no mezcla dims) + tiempo estimado + `--confirm` obligatorio → descarga + gate test-embed (RSS medido) + re-index → **conmutación atómica** de `config.model` + metadatos → **auto-GC** del modelo viejo; (b) durante todo el proceso, **el índice viejo sigue servable** (se consulta y responde); (c) `--keep-previous` desactiva el auto-GC; (d) fallo en **cualquier** paso ⇒ rollback con **cambio de estado cero** (config, índice y modelo idénticos byte a byte); (e) tras el éxito, el modelo viejo se purga de `.tepochcalli/models/`
  - Verificar: test de la descarga interrumpida ⇒ hash de config/índice/modelo idéntico antes y después · test de éxito ⇒ modelo viejo ausente (y presente con `--keep-previous`) · test de servabilidad del índice viejo durante el reindex
  - Dep.: T15 · Tamaño: L

- [ ] **T17 · `tepochcalli reindex --confirm` (TD-3) + `tepochcalli uninstall`**
  - Subagentes: `rust-engineer`, `test-engineer` · Skills: `test-driven-development`, `error-handling-patterns`
  - AC: (a) `reindex` exige `--confirm` **explícito** (sin él, no hace nada y explica por qué): borra el índice y lo reconstruye con el modelo actual, escribiendo `model` + `dims` en los metadatos; (b) detecta `E_MODEL_MISMATCH` (dims del modelo ≠ los del índice) y lo explica; (c) `uninstall --vault <ruta>` elimina `.tepochcalli/` (runtime: `venv/`, `bin/`, `db/`, `models/`, `config/`) y **deja** las notas, el payload y `opencode.json` del usuario; (d) `uninstall` **nunca** borra `00-Resources/` ni las notas; (e) ambos comandos soportan `--non-interactive`
  - Verificar: test de `reindex` sin `--confirm` ⇒ no hace nada · test de `uninstall` ⇒ `.tepochcalli/` ausente y notas intactas · **TD-3 cerrada** en `docs/TECH_DEBT.md`
  - Dep.: T16 · Tamaño: M

### ✅ CP-C · Atomicidad y swap — **6/6** ⬜ (pendiente)

- [ ] Fallo inducido en las 8 fases ⇒ compensación correcta, 0 datos del usuario perdidos
- [ ] `--resume` reanuda desde la fase correcta (artefactos + marker)
- [ ] `--offline` sin caché ⇒ `E_OFFLINE_NO_CACHE` limpio; con caché ⇒ instala sin red
- [ ] Idempotencia: install ×2 ⇒ 0 duplicados
- [ ] Swap D8.4: índice viejo servable; fallo ⇒ estado idéntico byte a byte; éxito ⇒ modelo viejo purgado
- [ ] `reindex --confirm` y `uninstall` con AC propios (TD-3 cerrada)
- ▶️ **Desbloquea T18-T20.**

---

## Sub-fase D — Distribución y cierre

- [ ] **T18 · `dist.toml` + workflow de release + matrix CI + recipes `just`**
  - Subagentes: `devops-engineer` (lead), `build-engineer`, `tooling-engineer` · Skills: `ci-cd-and-automation`, `shipping-and-launch`, `bash-defensive-patterns`
  - AC: (a) `crates/tepochcalli/dist.toml` con `ci = ["github"]`, `installers = ["shell", "powershell"]` y targets `x86_64-unknown-linux-gnu`, `aarch64-unknown-linux-gnu`, `x86_64-apple-darwin`, `aarch64-apple-darwin`, `x86_64-pc-windows-msvc` (D-b: **windows fuera de la matriz CI**, pero el target se compila para que el instalador exista); (b) `.github/workflows/release.yml` generado por `dist init --ci=github` y **revisado a mano** (acciones pineadas por SHA, como `phase1.yml`); (c) `.github/workflows/phase3.yml`: `cargo fmt --check` + `cargo clippy -D warnings` + `cargo test` en **ubuntu-latest** y **macos-latest**; (d) un job de **smoke de instalación** en ubuntu: VM limpia (sin Python/Node) que instala con `--payload` local y verifica que el vault queda con `00-Resources/` + `mcp.servers` válido; (e) la matrix cubre los **5 caminos** del menú de embedder (paths 1-5) con el camino 5 como el no interactivo por defecto (descargar un modelo de 470 MB en cada corrida de CI es caro: el resto de los caminos se cubre con `FakeHost` + `FakeHttp` en `cargo test`); (f) **nuevas recipes en el `Justfile`**: `rust-fmt`, `rust-lint`, `rust-test`, `rust-ci`, `wizard-smoke` — **nada de `cargo` crudo** (CODE_STYLE); (g) el workflow **declara explícitamente** que nunca se ha ejecutado (M6): no se dice «CI verde» en ninguna parte
  - Verificar: `just rust-test` y `just rust-lint` verdes en local · `dist plan` produce el plan de artefactos sin errores · los workflows tienen las acciones pineadas por SHA · `just md-lint` verde (el YAML cuenta)
  - Dep.: T17 · Tamaño: M

- [ ] **T19 · `install.sh`/`install.ps1` + asset del payload + regla one-version + SHA-256**
  - Subagentes: `devops-engineer` (lead), `security-auditor` · Skills: `security-and-hardening`, `ci-cd-and-automation`
  - AC: (a) `dist` genera `install.sh` y `install.ps1` que descargan el binario de la release, **verifican su SHA-256** y lo ejecutan; (b) el payload viaja como **asset de la misma release** (`tepochcalli-workspace-<ver>.tar.gz` + `.sha256`) y el wizard lo descarga con verificación de checksum (integrado con `ReleasePayload` de T8); (c) **regla one-version**: el binario v0.3.x instala **siempre** el payload v0.3.x (el binario pide su propia versión al asset, no una «latest» suelta); (d) el instalador **no** requiere Python ni Node en el host (es el criterio del gate); (e) `curl | sh` documenta el caveat de inspección antes de ejecutarlo
  - Verificar: `dist build` genera los installers · el smoke de T18 usa el payload **local** (no red) · test de la regla one-version (la versión del payload solicitada == la del binario) · checksum corrupto ⇒ fallo limpio
  - Dep.: T18 · Tamaño: M

- [ ] **T20 · Documentación + CHANGELOG + FTR Phase 3 → Phase 4**
  - Subagentes: `technical-writer` (lead), `code-reviewer` · Skills: `documentation-and-adrs`, `changelog-generate`, `crafting-effective-readmes`
  - AC: (a) `docs/APPFLOW.md` journeys d, e, f actualizados con el comportamiento real (instalación completa, salida 5, swap); (b) `docs/TECH_DEBT.md`: **R6 cerrada** (T9), **TD-3 cerrada** (T17), y **deuda nueva** registrada: «CI y release nunca ejecutados» (M6), «Windows fuera de la matrix» (D-b), «spec del wizard sin probar contra el gate de Phase 6»; (c) `CHANGELOG.md` con la entrada de Phase 3 (`changelog-generate`); (d) `specs/spec-installer-wizard.md` pasa a **Approved** (con el FTR del usuario) y `SPEC.md`/`docs/WORKFLOW.md` reflejan Phase 3 completada y Phase 4 liberado; (e) `docs/WORKFLOW.md` §1: estado de Phase 3 → completada con fecha; (f) **el FTR registra explícitamente lo NO verificado**: la matrix CI no se ejecutó, no hay release publicada, Windows no se probó
  - Verificar: `just md-lint` verde · `just quality` + `just rust-ci` verdes · la sección «no verificado» del FTR está escrita (no vacía)
  - ⚠️ **No se toca** `README.md`, `LICENSE`, `docs/UH.md` ni `obsidian-workspace/.opencode/` (vedados por AGENTS.md sin autorización explícita)
  - Dep.: T19 · Tamaño: M

### ✅ CP-D · Gate Phase 3 → Phase 4 — **6/6** ⬜ (pendiente)

- [ ] `dist.toml` + `release.yml` + `phase3.yml` escritos; `cargo test` verde en linux y macos **localmente**
- [ ] `install.sh`/`install.ps1` generados; asset del payload con SHA-256; regla one-version
- [ ] Los 5 caminos del menú de embedder cubiertos (paths 1-5)
- [ ] `just quality` (Python) + `just rust-ci` verdes; `just md-lint` verde
- [ ] Docs al día (APPFLOW, TECH_DEBT, CHANGELOG); spec-installer-wizard → *Approved*
- [ ] **FTR con el usuario** + registro explícito de lo que **no** se pudo verificar
- ▶️ **Desbloquea Phase 4 (blueprint del payload de agents/commands/skills).**

---

## Registro de commits (Conventional Commits, uno por tarea)

| Tarea | Commit |
| --- | --- |
| T1 | `docs(spec): Corrige el merge de mcp.servers y fija las olas D19-D27` |
| T2 | `test(wizard): Spike de extraccion segura y bootstrap de uv portable` |
| T3 | `feat(wizard): Esqueleto del crate con dominio de fases y codigos de salida` |
| T4 | `feat(wizard): Cinco puertos con fakes y test de arquitectura` |
| T5 | `feat(wizard): Adapters de proceso, http y sondeo de host` |
| T6 | `feat(wizard): UI de terminal y modo headless` |
| T7 | `feat(wizard): F1 prerrequisitos y F2 directorio del vault` |
| T8 | `feat(wizard): F3 extrae el payload sin sobreescribir y crea 00-Resources` |
| T9 | `feat(wizard): F4 bootstrap de uv y F5 venv con sync reproducible` |
| T10 | `feat(wizard): Presets embebidos y badges de hardware` |
| T11 | `feat(wizard): Menu de embedder con portero test-embed` |
| T12 | `feat(flow): CLI refresh y embed-check con RSS pico medido` |
| T13 | `feat(wizard): F8 fusiona mcp.servers con bak y comando portable` |
| T14 | `test(wizard): Compensaciones por fase, resume, offline e idempotencia` |
| T15 | `feat(wizard): Panel de fallo, log local y codigos de salida` |
| T16 | `feat(wizard): Swap atomico de embedder` |
| T17 | `feat(wizard): Comandos reindex y uninstall` |
| T18 | `ci: Workflow de release y matrix del wizard` |
| T19 | `feat(wizard): Asset del payload y regla one-version` |
| T20 | `docs: Fase 3 completada y FTR con lo no verificado` |

> Todos con trailer `Co-Authored-By: <agente> <dev@fisherk2.com>`.

## Decisiones ya tomadas (2026-10-28, usuario)

| # | Decisión |
| --- | --- |
| D-a | **Alcance de entrega**: crate completo + `dist.toml` + workflow de release, **sin publicar** (M6 sigue vigente) |
| D-b | **Windows**: fuera de la matrix CI (Linux + macOS), **pero** el comando del MCP se genera portable por SO |
| D-c | **Conflicto `markitdown`**: se corrige el §Merge de la spec + ola en WORKFLOW §8, **sin ADR** |
| D19 | `mcp.servers.markitdown` **NO** se registra en F8 (si el usuario la tenía, se elimina) |
| D20 | El comando del MCP se genera por SO (`venv/bin/python` vs `venv/Scripts/python.exe`) |
| D21 | `--resume` = deducir por artefactos + marker `.tepochcalli/.install-state` (cierra la Open Question de la spec) |
| D22 | El wizard crea `00-Resources/` + 2 placeholders; TD-8 (renombrar el scaffold del repo) sigue en Phase 4/5 |
| D23 | TUI line-based con `dialoguer` (no `ratatui` full-screen): debe correr sin TTY |
| D24 | F7 y el gate de embedder invocan un CLI nuevo `python -m tepochcalli_flow` (`refresh`, `embed-check`) |
| D25 | El wizard **no** descarga modelos: lo hace el flow Python, que **reporta el RSS pico medido** |
| D26 | **5 puertos** (`CommandRunner`, `HttpClient`, `HostProbe`, `PayloadSource`, `Ui`); **sin** puerto de FS (los tests usan `tempfile` real) |
| D27 | Los rangos de exit code los fija la spec; el número exacto y el mapeo a `E_*` los elige el wizard |
