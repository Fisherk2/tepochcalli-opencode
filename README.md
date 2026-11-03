# Tepochcalli

> Vault de Obsidian distribuible con búsqueda semántica **citada** sobre tus notas y PDFs,
> servida por OpenCode V2 + un motor RAG local (CocoIndex + LanceDB, embeddings en CPU).
> Requisitos: [docs/UH.md](docs/UH.md) · Especificación: [SPEC.md](SPEC.md) ·
> Arquitectura: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## Configuración (provisional)

El RAG se configura en dos sitios que no se solapan: el **entorno del harness**
(`opencode.json` → `mcp.servers.tepochcalli-rag.environment`) y el **`tepochcalli.toml`**
(gitignored, en `.tepochcalli/config/`).

### Variables de entorno del harness

| Variable | Default | Efecto |
| --- | --- | --- |
| `TEPOCHCALLI_ROOT` | `.` (si falta, el `cwd` del proceso) | Raíz del vault. Toda ruta del contrato se valida contra ella. |
| `INDEXER_DIR` | `00-Resources` | Raíces que el motor indexa cuando el agente llama `index_refresh()` **sin** `directories`. Multi-valor separado por **comas**. |
| `TEPOCHCALLI_TOP_K` | `5` | Default de `top_k` en `search`; el agente puede sobreescribirlo por llamada. |

Snippet exacto del payload:

```json
"tepochcalli-rag": {
  "type": "local",
  "command": [".tepochcalli/venv/bin/python", "-m", "tepochcalli_mcp"],
  "cwd": ".",
  "environment": {
    "TEPOCHCALLI_ROOT": ".",
    "INDEXER_DIR": "00-Resources",
    "TEPOCHCALLI_TOP_K": "5"
  }
}
```

`INDEXER_DIR` admite varias raíces: `"INDEXER_DIR": "00-Resources,03-Citations"` (split por coma,
`strip`, los vacíos se descartan — no es `os.pathsep`: `:` colisiona con `C:\`). Las rutas son
**relativas al vault**; una absoluta solo se acepta si cae **dentro** del vault. Una raíz puede ser
un **fichero suelto**, y las solapadas se deduplican. Fuera del vault, con `..` o inexistente ⇒
`VALIDATION_ERROR` con `details.suggestions` y `vault_dirs`.

* **`INDEXER_DIR` reemplaza el default, no lo suma.** Si declaras `"03-Citations"`,
  `00-Resources/` deja de indexarse en un `index_refresh()` sin argumentos salvo que la incluyas:
  `"00-Resources,03-Citations"`. La excepción es `add_source`, que declara
  `INDEXER_DIR ∪ 00-Resources` porque escribe ahí.
* **`INDEXER_DIR` vacío** (`""` o solo comas) ⇒ se usa `00-Resources`.
* **`TEPOCHCALLI_TOP_K` se lee al arrancar el proceso MCP**: cambiarla exige **reiniciar el
  server** (el `default` del schema de `search` refleja el valor de arranque). Rango útil 1–8 —el
  tope efectivo recorta a 8—; un valor no entero o ≤0 cae a 5.

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
