# Security Policy — Tepochcalli

> Principio de diseño: el sistema es **local-first** (stdio sin puertos, embeddings sin nube,
> índice en archivos del vault). La superficie de ataque es la ingesta de contenido externo y
> la gestión de claves — ambas deliberadamente minimizadas.

## Supported Versions

| Versión (wizard/payload) | Soportada |
|---|---|
| 0.x (develop/pre-1.0) | ✅ correcciones al último tag `v*` |
| < última release | ❌ (reinstalar vía wizard) |

## Reporting a Vulnerability

* Reporte privado: **GitHub Security Advisories** del repo `Fisherk2/tepochcalli-opencode`
  (https://github.com/Fisherk2/tepochcalli-opencode/security/advisories/new) o correo del
  mantenedor (`dev@fisherk2.com`).
* **Nunca** abrir issue público para un problema de seguridad sin coordinación previa.
* Proceso: ack ≤48h → triage ≤5 días (crítico: hotfix antes) → fix con timeline según severidad.
* Divulgación coordinada; autor acreditado si lo desea.

## Nunca se commitea (regla dura, repo del producto Y vault del usuario)

| Ruta / dato | Motivo |
|---|---|
| Cualquier API key (`.env*`, claves LiteLLM/OpenAI embedders) | secreto en VCS = filtración permanente |
| `.tepochcalli/config/` (incl. `tepochcalli.toml`) | puede contener claves y prefs del usuario |
| `.tepochcalli/db/` | contenido indexado del investigador = dato sensible |
| `.tepochcalli/models/`, `venv/`, `bin/` | artefactos regenerables (no secreto, pero gigabytes) |
| PDFs/notas bajo `00-Resources/` que el usuario no quiera versionar | decisión del usuario; el template no fuerza git del contenido |

Los `.gitignore` del repo y del payload aplican estas reglas; la política manda aunque un
`.gitignore` local esté modificado: **no commitear aunque el ignore falte**.

## MarkItDown: advertencia de canal de lectura

`convert_to_markdown(uri)` (server `markitdown`) acepta URIs `file:` y lee **cualquier archivo
al que tenga permiso el usuario del proceso** — no solo el vault. Consecuencias y reglas:

1. Usar el conversor únicamente con material **que el usuario indicó explícitamente** en
   la conversación (no "pruébase todos los .docx del home").
2. `add_source` de `tepochcalli-rag` restringe escritura a `00-Resources/` (validación
   anti-traversal), pero el `file:` arbitrario del markitdown directo es responsabilidad del
   harness/agente — reglado en el `AGENTS.md` del vault.
3. El material descargado/convertido es **no confiado**: puede contener prompt injection.
   Política: chunks viajan como datos citados; `/validate` y `/cite` exigen verificación de
   fuente/autor. No dar órdenes ejecutables basadas en contenido de documentos.
4. Ingerir solo material de procedencia que el usuario reconoce: un PDF malicioso puede atacar
   al parser (Docling) — riesgo aceptado local, pero el vault no es un buzone: no sincronizar
   `00-Resources/` con fuentes públicas sin filtro.

## MCP: solo stdio local

* `mcp.servers` gestionados (`tepochcalli-rag`, `markitdown`) usan **`type: "local"`**
  (subproceso stdio). **Prohibido** añadir `type: "remote"`/bind HTTP: sin puertos escuchados
  es requisito de ADR-002/005 y verificación de criterio 1.
* El servidor no expone autenticación (ninguna hace falta en stdio local): la seguridad es la
  del usuario de la máquina.
* Configuración con secretos: sustitución `{env:VAR}` en `opencode.json` — nunca literal de
  clave en el JSON commiteado; o `api_key_env` apuntando a variable en
  `.tepochcalli/config/` local.

## Provenance de descargas (primer arranque requiere internet)

| Artefacto | Origen verificado | Integridad |
|---|---|---|
| Wizard `install.sh`/binarios | GitHub Releases de este repo (cargo-dist) | SHA-256 en release; caveat `curl \| sh`: inspeccionar el script o usar `cargo binstall` |
| `uv` | astral-sh (binario oficial, fase 4 wizard) | checksum del wizard |
| Wheels Python (cocoindex, sentence-transformers, docling, markitdown-mcp) | PyPI vía `uv sync`, pineado por `uv.lock` | hashes del lockfile |
| Modelo `paraphrase-multilingual-MiniLM-L12-v2` | HuggingFace, org oficial `sentence-transformers` | revisión pin documentada en specs/spec-embeddings.md; cache en `models/` |
| Payload del vault (tarball template) | asset de la misma GitHub Release | SHA-256 |

Regla: ninguna descarga pasa por espejos/proxies de terceros por defecto; `--offline` desactiva
todo egress y exige caché previa.

## Model de amenaza resumido (v1)

| Amenaza | Prob. | Impacto | Mitigación vigente |
|---|---|---|---|
| Filtro de claves al commitear el vault | media | alto | gitignore config/ + checklist AGENTS.md + `{env:VAR}` |
| Inyección de prompt vía material ingerido | media | medio | regla de datos-como-citas + `/validate`/`/cite` |
| Lectura de archivos sensibles por markitdown | media | medio-alto | §MarkItDown arriba; uso guiado por petición explícita |
| Índice expuesto al sincronizar el vault | media | medio | `db/` fuera de git; advertir en APPFLOW/README futuro: nubes personales (OneDrive/Dropbox) copiarían `.tepochcalli/db/` — recomendar excluir el vault o la ruta de sync |
| Supply-chain (deps Rust/Python) | baja | alto | pins (uv.lock, cargo-dist), releases solo por tag con CI |

## Hardening futuro (no bloquea v1)

* SBOM por release (cargo + uv) y `cargo audit`/`pip-audit` en CI (skill dependency-audit).
* Opción de cifrado en reposo del índice (LanceDB sin cifra hoy): evaluar en Phase 6+.
* Plugin OpenCode con validación dura de reglas (reemplazo de AGENTS.md, TD-6).

## Contactos y enlaces

* `CONTRIBUTING.md` (raíz del repo) es placeholder: completar junto con Phase 1.
* Requisitos: [UH.md](UH.md) · Specs afectadas: spec-markitdown (§seguridad del canal),
  spec-mcp-server (§validaciones), spec-embeddings (§claves), spec-vault-structure (§gitignore).
