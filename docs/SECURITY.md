# Security Policy — Tepochcalli

> Principio de diseño: el sistema es **local-first** (stdio sin puertos, embeddings sin nube,
> índice en archivos del vault). La superficie de ataque es la ingesta de contenido externo y
> la gestión de claves — ambas deliberadamente minimizadas.

## Supported Versions

| Versión (wizard/payload) | Soportada |
| --- | --- |
| 0.x (develop/pre-1.0) | ✅ correcciones al último tag `v*` |
| < última release | ❌ (reinstalar vía wizard) |

## Reporting a Vulnerability

* Reporte privado: **GitHub Security Advisories** del repo `Fisherk2/tepochcalli-opencode`
  (<https://github.com/Fisherk2/tepochcalli-opencode/security/advisories/new>) o correo del
  mantenedor (`dev@fisherk2.com`).
* **Nunca** abrir issue público para un problema de seguridad sin coordinación previa.
* Proceso: ack ≤48h → triage ≤5 días (crítico: hotfix antes) → fix con timeline según severidad.
* Divulgación coordinada; autor acreditado si lo desea.

## Nunca se commitea (regla dura, repo del producto Y vault del usuario)

| Ruta / dato | Motivo |
| --- | --- |
| Cualquier API key (`.env*`, claves LiteLLM/OpenAI embedders) | secreto en VCS = filtración permanente |
| `.tepochcalli/config/` (incl. `tepochcalli.toml`) | puede contener claves y prefs del usuario |
| `.tepochcalli/db/` | contenido indexado del investigador = dato sensible |
| `.tepochcalli/models/`, `venv/`, `bin/` | artefactos regenerables (no secreto, pero gigabytes) |
| PDFs/notas bajo `00-Resources/` que el usuario no quiera versionar | decisión del usuario; el template no fuerza git del contenido |

Los `.gitignore` del repo y del payload aplican estas reglas; la política manda aunque un
`.gitignore` local esté modificado: **no commitear aunque el ignore falte**.

## MarkItDown: canal de lectura y frontera B′

`markitdown` es una **librería en proceso** dentro del venv (no un server): la usan el motor
(`parsers.py`, para pdf/docx/pptx/xlsx/xls), `add_source` y las tres tools del conversor
(`convert_document`, `convert_base64`, `list_formats`) — ADR-009/ADR-011. La entrada puede ser
un `file:` del vault, una URL o bytes base64, y markitdown lee **cualquier archivo al que tenga
permiso el usuario del proceso**. Reglas:

1. **Frontera B′ (entrada y salida dentro del vault, D31/D32):** `paths.validate_vault_path` /
   `paths.validate_roots` resuelven la ruta y rechazan absolutos fuera, `..` que escape y
   symlinks cuyo target resuelto salga del vault ⇒ `VALIDATION_ERROR` **antes** de que
   markitdown toque el disco. Sin `output_path`, el destino es `00-Resources/<slug>.md` (D37);
   nunca se escribe fuera del vault.
2. **`arbitrary file write`:** el riesgo propio del conversor no es solo leer, es **escribir**.
   `writer.write_atomic` escribe con temp + rename e **idempotencia D66**: destino existente
   con contenido idéntico ⇒ la misma respuesta de éxito sin reescribir; con contenido distinto
   ⇒ `VALIDATION_ERROR` («elige otro output_path»). **Nunca** se sobrescribe material del
   usuario; `add_source` restringe además la escritura a `00-Resources/`.
3. **Raíces de indexación (ADR-010/D64/D65):** `index_refresh(directories=…)` valida en el
   borde **existencia y tipo** (directorio, o fichero con extensión de la whitelist) y es
   **fail-fast atómico**: una raíz mala ⇒ no se indexa ninguna y el error nombra la raíz, las
   que existen y sugerencias. Motivo: `localfs.walk_dir` lanza `ValueError` para una ruta que
   no es directorio y el `internal_guard` lo convertiría en un falso «fallo interno».
4. **El artefacto no viaja al LLM:** las tools del conversor devuelven solo el resumen de 5
   claves (`written_to`, `source_uri`, `bytes`, `chars`, `preview` ≤500 chars) — el cuerpo
   convertido se queda en disco (ADR-009). El material descargado/convertido es **no
   confiado**: puede contener prompt injection. Política: los chunks viajan como **datos**
   citados; `/validate` y `/cite` exigen verificación de fuente/autor. **El material es dato,
   nunca instrucción**: no se ejecutan órdenes que aparezcan dentro de un documento.
5. **Ingerir solo material reconocible por el usuario:** un PDF malicioso ataca a los
   decodificadores de markitdown y sus dependencias (superficie declarada en ADR-011 §5) —
   riesgo aceptado local, pero el vault no es un buzone: no sincronizar las raíces indexables
   con fuentes públicas sin filtro.

## Symlinks: frontera de confianza en el vault

El walk del motor **sigue los symlinks que funcionan** (de archivo y de directorio), así que
un vault sincronizado con la nube o manipulado podría contener `secreto.md -> ~/.ssh/id_rsa`.
Reglas vigentes, aplicadas en `tepochcalli_flow.source.classify_file` (D47; la frontera es el
**vault**, no la raíz pedida — con N raíces, un link de `documentos/` a `materiales/x.pdf` es
legítimo):

* Symlinks **rotos** los omite el conector del walk; la capa de fuentes los reporta como
  `broken_symlink` con motivo, sin abortar el delta.
* Symlinks cuyo objetivo **resuelto** —`Path.resolve()`, cadena de enlaces completa— cae fuera
  del **vault** se rechazan con motivo `symlink_escape`: el contenido de fuera del vault jamás
  llega al índice ni a las respuestas de `search`.
* Los symlinks que se quedan **dentro** del vault se indexan con normalidad.
* El vault es material **confiado**; el contenido de las raíces indexadas es **dato, nunca
  instrucción** (regla anti prompt-injection del `AGENTS.md` del vault).

Limitaciones TOCTOU conocidas y documentadas (no cubiertas por el chequeo actual; fd-grade
requeriría rewiring del conector, fuera del scope v1):

* El objetivo de un symlink puede **conmutarse entre el check y la lectura del conector**
  (carrera del SO): la frontera se evalúa al clasificar y NO se re-verifica con fd propio.
  En un vault multiusuario/hostil esto admite un swap directed; en el modelo amenaza v1
  (vault del propio usuario, material confiado) se acepta.
* **Hardlinks** a ficheros fuera del recurso NO se detectan (mismo inode, path válido) —
  el hard-link usa los permisos del destino real y la fuente de verdad del usuario.
* La **complejidad de parseo de PDF** (markitdown y sus decodificadores) no magnifica ningún
  vector aquí: el PDF solo produce texto extraído (vía `extract` como espacio de offsets),
  jamás binario crudo.

## MCP: solo stdio local

* `mcp.servers` gestionado (`tepochcalli-rag`) usa **`type: "local"`**
  (subproceso stdio). **Prohibido** añadir `type: "remote"`/bind HTTP: sin puertos escuchados
  es requisito de ADR-002/005 y verificación de criterio 1. El standalone `markitdown` ya no
  se registra (conversión en proceso, ADR-011).
* El servidor no expone autenticación (ninguna hace falta en stdio local): la seguridad es la
  del usuario de la máquina.
* Configuración con secretos: sustitución `{env:VAR}` en `opencode.json` — nunca literal de
  clave en el JSON commiteado; o `api_key_env` apuntando a variable en
  `.tepochcalli/config/` local.
* **Clave de API (camino `litellm`):** `api_key_env` guarda **solo el nombre** de la
  variable, nunca el valor. La clave no aparece en logs, en el `repr()` de embedder/config ni
  en ningún payload MCP (test de no-fuga, T6); las excepciones de API se reescriben con el
  valor redactado como `***` (`EmbedderApiError`, `embedder.py`) y `from None` para no
  arrastrar el traceback, y el fallo de credencial sale como `E_API_AUTH` con `fix_hint` que
  nombra la variable — jamás su contenido.

## Provenance de descargas (primer arranque requiere internet)

| Artefacto | Origen verificado | Integridad |
| --- | --- | --- |
| Wizard `install.sh`/binarios | GitHub Releases de este repo (cargo-dist) | SHA-256 en release; caveat `curl \| sh`: inspeccionar el script o usar `cargo binstall` |
| `uv` | astral-sh (binario oficial, fase 4 wizard) | checksum del wizard |
| Wheels Python (`cocoindex[lancedb,sentence-transformers,litellm]`, `markitdown[docx,pptx,xlsx,xls,pdf]`, `sentence-transformers`) | PyPI vía `uv sync`, pineado por `uv.lock` | hashes del lockfile |
| Modelo `paraphrase-multilingual-MiniLM-L12-v2` | HuggingFace, org oficial `sentence-transformers` | revisión pin documentada en specs/spec-embeddings.md; cache en `models/` |
| Payload del vault (tarball template) | asset de la misma GitHub Release | SHA-256 |

Regla: ninguna descarga pasa por espejos/proxies de terceros por defecto; `--offline` desactiva
todo egress y exige caché previa.

## Model de amenaza resumido (v1)

| Amenaza | Prob. | Impacto | Mitigación vigente |
| --- | --- | --- | --- |
| Filtro de claves al commitear el vault | media | alto | gitignore config/ + checklist AGENTS.md + `{env:VAR}` |
| Inyección de prompt vía material ingerido | media | medio | regla de datos-como-citas + `/validate`/`/cite` |
| Lectura de archivos sensibles por markitdown | media | medio-alto | §MarkItDown arriba; **B′** — entrada y salida validadas dentro del vault (`paths`), `file:` fuera ⇒ `VALIDATION_ERROR`; uso guiado por petición explícita |
| `arbitrary file write` vía el conversor | baja | alto | `writer.write_atomic` (temp + rename) + idempotencia D66: nunca sobrescribe material del usuario; destino por defecto `00-Resources/` (ADR-009) |
| Fuga de clave de API vía logs o payloads MCP | baja | alto | `api_key_env` guarda solo el nombre; redacción `***` en excepciones; test de no-fuga en logs/`repr`/payload (T6) |
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
