# Tepochcalli

> Vault de Obsidian distribuible con búsqueda semántica **citada** sobre tus notas y PDFs,
> servida por OpenCode V2 + un motor RAG local (CocoIndex + LanceDB, embeddings en CPU).
> Requisitos: [docs/BACKLOG.md](docs/BACKLOG.md) · Especificación: [SPEC.md](SPEC.md) ·
> Arquitectura: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## Instalación (beta 0.1.0-beta.1)

Primer beta. **Aún no hay rueda en PyPI ni binarios en el release**: hoy se instala **desde el
código fuente**. `uvx tepochcalli` es el canal objetivo
([ADR-014](docs/adr/adr-014-distribucion-uvx-pypi.md)) y funcionará cuando la rueda esté publicada.

**Requisitos:** `cargo` (Rust — el release se compila con 1.99) y `uv` en el host; el wizard hace
por ti el bootstrap de `uv`/CPython ([ADR-004](docs/adr/adr-004-uv-venv-aislado.md)).

1. `cargo install --path crates/tepochcalli --locked`
2. `tepochcalli install --vault ~/MiVault`
   — descarga `tepochcalli-workspace-0.1.0-beta.1.tar.gz` del GitHub Release y **verifica su
   SHA-256**; `--payload <dir>` o `--payload-url <url> --payload-sha256 <hex>` fijan la fuente.
3. Abre el vault en Obsidian y en OpenCode V2.

**Qué escribe:** `.opencode/`, `.tepochcalli/`, `.gitignore`, `opencode.json`, `AGENTS.md` y
`00-resources/`. **Nunca** toca notas, PDFs ni `.obsidian/`. `tepochcalli desinstall` retira lo del
instalador dejando un backup del `config/`.

**Sin red no se instala** ([ADR-016](docs/adr/adr-016-resiliencia-offline-y-rollback.md)): el
preflight corre antes del primer escrito y, ante cancelación, el rollback deja el vault como
estaba. Una cancelación sale con exit **41**; un fallo de fase con restos, **42**.

**Nota honesta:** este release no publica binarios ni rueda; el `install.sh` del repo solo sirve
cuando existan assets de binario.

## Rendimiento de ingesta (medido)

Lo que cuesta meter material al índice, por tamaño. **Primera ingesta** = extracción a Markdown
(markitdown) + chunking + embeddings + upsert en LanceDB. Después, el refresco es incremental: solo
se reprocesa lo que cambió.

| PDF | Páginas | Texto extraído | Extracción (p50) | Indexación (p50) | Primera ingesta | ms/página |
| --- | --- | --- | --- | --- | --- | --- |
| libro pequeño | 16 | 53 568 chars | 3,5 s | 6,4 s | **9,9 s** | 221 |
| documento | 30 | 51 761 chars | **3,1 s** | ≈5,4 s (derivado) | **≈8,5 s** | 105 |
| libro | 335 | 1 000 523 chars | 50,6 s | 108,5 s | **≈159 s** | 151 |
| libro | 444 | 527 068 chars | 95,1 s | — | — | 214 |
| libro | 952 | 2 278 941 chars | 121,5 s | — | — | 128 |
| libro | 1 313 | 3 344 734 chars | 128,0 s | — | — | 98 |

Notas `.md`/`.txt` no se miden por página: el benchmark de Δ toca/crea 50 notas y refresca en
**4,3 s p95**, con embeddings incluidos.

* **Método:** n=3 por fila, percentil nearest-rank, reloj monotónico, `VmHWM` pico del proceso hijo
  (markitdown 190-255 MiB; indexación ≈1,5-1,8 GiB porque carga el modelo). Host de desarrollo
  (i7-8750H, 12 vCPU, btrfs/NVMe, CPython 3.12.14), no la VM de 8 GB de [docs/TRD.md](docs/TRD.md) §6.1:
  en hardware menor, más lento. Detalle y JSON crudos en
  [docs/acceptance/documents.md](docs/acceptance/documents.md).
* **No extrapoles por página.** El coste por página cae de 221 ms a 98 ms al crecer el documento
  (se amortiza el arranque) y **no es monótono**: un PDF de 444 páginas con 527 k chars tarda más
  que uno de 335 con 1 M, porque manda la composición del PDF, no el número de páginas. La cifra
  que sirve es la medida, no la multiplicación.
* **Documentos grandes:** por encima de ~300 páginas la primera ingesta pasa de 30 s, y v1 **no
  limita páginas** (D51: los documentos binarios van aparte del presupuesto de Δ de 30 s de
  texto). `index_refresh` informa del progreso por documento en `stderr`; el refresco de un libro
  así tarda minutos, no segundos.
* **Contraste con la era Docling:** 49-51 s para 30 páginas. markitdown hace el mismo documento en
  3,1 s (≈16× menos) con 190 MiB de RSS en vez de ≈2 GiB.

## Configuración (provisional)

El RAG se configura en dos sitios que no se solapan: el **entorno del harness**
(`opencode.json` → `mcp.servers.tepochcalli-rag.environment`) y el **`tepochcalli.toml`**
(gitignored, en `.tepochcalli/config/`).

### Variables de entorno del harness

| Variable | Default | Efecto |
| --- | --- | --- |
| `TEPOCHCALLI_ROOT` | `.` (si falta, el `cwd` del proceso) | Raíz del vault. Toda ruta del contrato se valida contra ella. |
| `INDEXER_DIR` | `00-resources` | **Conjunto completo** de raíces del índice: es lo único que decide qué se indexa. `index_refresh()` no acepta argumentos y el MCP nunca modifica la variable. Multi-valor separado por **comas**; cambiarla exige reiniciar el MCP. |
| `TEPOCHCALLI_TOP_K` | `5` | Default de `top_k` en `search`; el agente puede sobreescribirlo por llamada. |

Snippet exacto del payload:

```json
"tepochcalli-rag": {
  "type": "local",
  "command": [".tepochcalli/venv/bin/python", "-m", "tepochcalli_mcp"],
  "cwd": ".",
  "environment": {
    "TEPOCHCALLI_ROOT": ".",
    "INDEXER_DIR": "00-resources",
    "TEPOCHCALLI_TOP_K": "5"
  }
}
```

`INDEXER_DIR` admite varias raíces: `"INDEXER_DIR": "00-resources,03-Citations"` (split por coma,
`strip`, los vacíos se descartan — no es `os.pathsep`: `:` colisiona con `C:\`). Las rutas son
**relativas al vault**; una absoluta solo se acepta si cae **dentro** del vault. Una raíz puede ser
un **fichero suelto**, y las solapadas se deduplican. Fuera del vault, con `..` o inexistente ⇒
`VALIDATION_ERROR` con `details.suggestions` y `vault_dirs`. Cambiar la variable exige **reiniciar
el MCP** (el proceso recibe su `environment` al arrancar).

* **`INDEXER_DIR` es el conjunto completo del índice, no una suma al default.** Si declaras
  `"03-Citations"`, `00-resources/` deja de indexarse salvo que la incluyas:
  `"00-resources,03-Citations"`. El agente **no puede** añadir ni quitar raíces por llamada —
  `index_refresh()` no tiene argumentos y el MCP nunca toca la variable.
* **`add_source` exige `00-resources` declarada.** Escribe ahí, así que si no está en
  `INDEXER_DIR` rechaza con `VALIDATION_ERROR` **antes de escribir** (`details: {requested,
  allowed, hint}`): añádela a la variable, o usa `convert_document` con un `output_path` dentro de
  una raíz indexada.
* **`INDEXER_DIR` vacío** (`""` o solo comas) ⇒ se usa `00-resources`.
* **`TEPOCHCALLI_TOP_K` se lee al arrancar el proceso MCP**: cambiarla exige **reiniciar el
  server** (el `default` del schema de `search` refleja el valor de arranque). Rango útil 1–8 —el
  tope efectivo recorta a 8—; un valor no entero o ≤0 cae a 5.
* **Si algo está mal escrito, `rag_status()` lo dice** antes de indexar nada: `config.valid` pasa a
  `false` y `config.problems` / `config.unknown_env` nombran el fallo (raíz inexistente, nombre mal
  escrito tipo `INDEXER_DRI`). No hay que adivinar por qué el índice no cambia.

### Qué vive en `tepochcalli.toml` (y por qué el modelo no está en `environment`)

| Clave | Sección | Cómo se cambia |
| --- | --- | --- |
| `provider`, `model`, `revision`, `api_key_env` / `api_key` | `[embedding]` | `tepochcalli config embedder` (nunca a mano) |
| `device` | `[embedding]` | editar el toml |
| `max_chunk_size`, `overlap` | `[chunking]` | editar el toml — **fuerza re-index** (cambia el troceado) |

`provider`/`model`/`revision`/`device` los escribe **atómicamente** `tepochcalli config embedder`
(gate test-embed + `--confirm` + re-index + rollback, ADR-008 §4.4), y el server **relee el toml en
cada llamada** (sin caché), invalidando el backend cuando la config cambia. Una copia en
`environment` se leería **una vez al arrancar** y **ensombrecería** el swap: índice del modelo nuevo
con queries del viejo ⇒ `E_MODEL_INVALID` (o dimensiones distintas si cambia el proveedor).

La sección `[search]` del toml está **jubilada**: un toml viejo que la traiga solo recibe el aviso
de sección desconocida y el valor se ignora — `top_k` se declara en `environment`.

### Cambiar de modelo o proveedor

```bash
tepochcalli config embedder     # menú de 5 salidas; swap atómico con re-index
```

Para `device` o `chunking`, edita `.tepochcalli/config/tepochcalli.toml` directamente (chunking
fuerza re-index; device no).

### Reinstalar no borra tu configuración

La fase F8 del wizard **conserva** las claves de `environment` que no gestiona e impone solo
`TEPOCHCALLI_ROOT`, así que tus ediciones de `INDEXER_DIR` y `TEPOCHCALLI_TOP_K` sobreviven a
reinstalar.
