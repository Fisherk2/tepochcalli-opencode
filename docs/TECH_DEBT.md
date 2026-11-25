# Technical Debt Register — Tepochcalli v1

**Date:** 2026-10-21 | **Author:** Arquitecto (entrevista /spec) | **Status:** Active.

Deuda conocida y aceptada al diseñar el sistema. Cada entrada: descripción, por qué existe, coste si se ignora, y acción/oráculo para pagarla.

> Estado a 2026-11-25: **28 completadas** y **69 pendientes**. La tabla de pendientes está ordenada de mayor a menor complejidad (L → M → S); se considera pendiente toda deuda marcada «Acotada» o parcialmente pagada.

## Deuda técnica completada

| ID | Deuda | Cierre (fecha y evidencia) |
| --- | --- | --- |
| TD-1 | Glue flow+MCP propio con tests de contrato y golden vault | 2026-10-27 Phase 2: «Pagada»; 404 tests, capa fina vía `ChunkReader` |
| TD-2 | Coste PDFs/docx fuera del Δ de 30 s | 2026-11-12 T2: CERRADA A+B; 335 pág = 50,6 s; progreso en `stderr` |
| TD-3 | Cambio de modelo exige re-index; detección y comando | 2026-10-28 T17: cerrada; `reindex --confirm` real, 16 tests e2e |
| TD-8 | Alias de carpetas `00-Resources`/`01-Tasks` vs canónico | 2026-11-13: extendida y resuelta; case exacto en flow/payload/wizard |
| TD-13 | Cita no re-verificada contra el archivo vivo | 2026-11-13 T7: CERRADA; `--spot-check` 6/6, exit 1 al editar |
| TD-15 | Sin eval de relevancia de recuperación | 2026-11-12 T3: CERRADA; recall@5 = 1.00 (10/10), 20 notas |
| TD-16 | Read path sin reintentos ante fallo LiteLLM | 2026-11-03 T6: CERRADA; `LiteLLMEmbedder` con backoff (D56) |
| TD-18 | Lectores config/JSON duplicados en el wizard | 2026-10-29: PAGADO; set único en `text.rs`, +692/−836 |
| TD-26 | D42: raíces del índice viajaban por llamada | 2026-11-03: Cerrada; `INDEXER_DIR` persistente, `index_refresh()` sin args |
| TD-27 | D54: PDF sin jerarquía de headings | 2026-11-13 T10: CERRADA; reafirmada, 0/6 303 citas con heading |
| TD-28 | `embedder_menu.rs` en 894 líneas | 2026-11-13 T11-a: CERRADA; 298 + 4 módulos planos, 178 literales |
| TD-29 | `require_local_model` solo veía directorio no vacío | 2026-11-13 T11-b: CERRADA; `snapshot_defect`, 4 tests |
| TD-30 | Fixture de merge rebasado (compara payload consigo mismo) | 2026-11-09: CERRADA; merge sintético D-P5-9, idempotencia 875 ficheros |
| TD-33 | Formato revisado del payload (ADR-012) sin documentar | 2026-11-11: pagada en la ola; ADR-012 + 4 specs + SPEC.md |
| TD-45 | Divergencia de versión one-version Cargo vs pyproject | 2026-11-19 T1: CERRADA; ambos a `0.1.0` canónica |
| TD-46 | ADR-014/015 Proposed y deps sin aprobar | 2026-11-19 T0/T1: CERRADA; Accepted + maturin/ratatui/crossterm |
| TD-47 | Drift de `device`: presets sin campo y swap lo pisa | 2026-11-19 T4: CERRADA; `Preset.device`, preservado, 386 tests |
| TD-48 | `update`/`desinstall` inexistentes o con alcance reducido | 2026-11-19 T5: CERRADA; backup `.bak`, 0,293 s / 1,44 s |
| TD-49 | TUI full-screen con botones (ratatui+crossterm) | 2026-11-19 T8: CERRADA; verificado en TTY real 80×24 |
| TD-50 | Guarda anti-exfiltración del loader sin test | 2026-11-19 T6: CERRADA; `test_config.py:412`, 707 tests |
| TD-51 | Retiro materializado de cargo-dist no ejecutado | 2026-11-23 Phase 6.7: CERRADA; `dist.toml` borrado, `release.yml` 1 job |
| TD-54 | `e2e_swap.rs` en 1068 líneas | 2026-11-23 `c2bad3c`: CERRADA; 4 ficheros, 24 tests idénticos |
| TD-59 | Directorios vacíos tras el rollback | 2026-11-23 `8e7ba72`: CERRADA; `compensate_phase3` poda ancestros |
| TD-68 | ENOSPC mapeado como `PermissionDenied` | 2026-11-23 `8b329c3`: CERRADA; `StorageFull`→`DiskFull` (30) |
| R6 | `pyproject.toml` omite el subpaquete `tepochcalli_mcp.tools` | 2026-10-28 T9: cerrada; import verificado en F5, re-check en T20 |
| D-b | Windows fuera de matriz y sin probar | 2026-11-13: CERRADA firmada como «declarado»; verificación en TD-52/55 |
| M6 | Release nunca ejecutada (CI y release con assets) | 2026-11-24 CI run `45316624910`; tags beta.1/beta.2 con tar+sha256; wheels PyPI 0.1.0b1/b2 |
| `opencode_payload_before_t9.json` | Fixture pre-T9 que envejece con el payload | 2026-11-09 (TD-30): sustituido por `opencode_payload_synthetic.json` (verificado) |

## Deuda técnica pendiente

| ID | Deuda | Complejidad | Próxima acción |
| --- | --- | --- | --- |
| TD-4 | Obsolescencia del índice con editores externos; sin watcher | L | Decidir `auto_refresh` opt-in en spec nueva (rompe ADR-002) |
| TD-5 | Migración LEANN sin ejecutar (97 % menos storage) | L | Revisar en 2027-04 con bench bajo contrato ADR-005 |
| TD-6 | MCP-first en prompt editable; tracker de plugin/tool abierto | L | Verificar regla en prompts y decidir plugin Phase 6+ |
| TD-11 | TOCTOU de symlinks/hardlinks sin re-chequeo fd | L | Re-chequear al leer si el conector expone `O_NOFOLLOW` |
| TD-22 | OfficeCLI 0.2.0 y retiro de 6 skills + MCP `excel` | L | Implementar instalación latest+SHA256SUMS y retirar skills/entrada |
| TD-31 | Corrida D9 de los 9 comandos diferida al QA | L | Correr runbook con transcript y árbol final; enmendar si falla |
| TD-35 | FTS en inglés sobre corpus ES: 4/7 pares flexivos | L | Medir 3 opciones con `fts_probe.py` y escribir ADR |
| TD-36 | Criterio 6: ratio Δ 6,17× (15,7 s vs 2,5 s) | L | Decidir ADR sobre walk; medir con `bench_scale_ratio.py` |
| TD-37 | Techo 1600 tokens es estimación: 1789 reales, 5 de margen | L | Bajar techo a ~1500 o reformular con ADR sobre ADR-005 |
| TD-43 | Refactors estructurales deferidos (run_phases 10 params, matches) | L | Pasada de refactoring dedicada, sin mezclar con features |
| TD-44 | Diez sugerencias de seguridad sin fijar (http, secretos, @latest) | L | Hardening por tandas; empezar por (a) downgrade http y (j) DNS |
| TD-52 | Smoke TTY/uvx en Windows nunca ejercitado | L | Runner windows-latest con consola real, recorrer 4 escenarios H5 |
| TD-55 | Ctrl+C y rollback bajo `uvx` en Windows sin probar | L | Cancelar a mitad de descarga en Windows y verificar rollback |
| TD-57 | Residuo de F3 sin intent: copias no distinguibles | L | Journal por fichero o snapshot del árbol F3 para borrar |
| TD-65 | Barra real salvo H6: sin feed de bytes para F3–F8 | L | Añadir feed de bytes al contrato del flow para F3–F8 |
| TD-71 | Canal publicado incompleto: OIDC y decisión de binarios | L | Migrar `publish.yml` a Trusted Publishing y decidir binarios |
| D6-4 | Fallos API dentro del update de cocoindex salen `INTERNAL` | L | Engancharse a retries/batch de cocoindex o aceptar como límite |
| CR-6 | SDK responde tipos inválidos con texto libre | L | Adoptar validación/hook canónico si MCP v2 lo publica |
| F-T20 | Spec wizard Approved sin probar contra tabla §6.3 | L | Ejecutar tabla §6.3; divergencias ⇒ ADR o nota de mapeo |
| TD-14 | Regla de cita y `/validate`/`/cite` con evidencia desactualizada | M | Re-verificar regla en prompts y refrescar evidencia |
| TD-17 | `E_API_AUTH` nombra solo la env var, no el toml | M | Redactar mensaje sin fuente; sync docstring/spec/test |
| TD-19 | Cuatro loops de flags CLI copiados en `main.rs` | M | Extraer parser con tabla de spec y test nuevo |
| TD-20 | `map_io`/`map_fs_err` blanket vs clasificación de `http.rs` | M | Aplicar bandas V-6 con test por `ErrorKind` |
| TD-21 | Mini-parsers JSON hand-rolled con `serde_json` disponible | M | Migrar con auditoría byte-a-byte de fixtures |
| TD-23 | `WizardError::ModelMismatch` variante muerta | M | Decidir guarda real o documentar como reservado MCP |
| TD-24 | F5 import-check: segundo spawn python fuera de `flow_cli.rs` | M | Adoptar `run_flow_cli` con `extra_env=&[]` o documentar |
| TD-25 | `swap.rs` swallow `unwrap_or(("", ""))` en litellm sin NUL | M | `ok_or(Internal)?` + test `litellm sin NUL → Err` |
| TD-32 | `installer.rs` 795 y `int_phase_f8_mcp_merge.rs` 854 líneas | M | Extraer a <500 y `RecordingProc` a `tests/common/` |
| TD-38 | `mcp-tools` 15:33 y `engine` 13:53 sobre tope 10 min | M | Partir de nuevo o re-baselinear con medición |
| TD-39 | Segundo `os.walk` + lstat por fichero en `walk_skips` | M | Tras reasentar tests, iterar `DirEntry` de `scandir` |
| TD-40 | `index_models()` materializa ~100-200k dicts por `search` | M | Cachear por mtime/`table.version()` + `to_arrow().unique()` |
| TD-41 | Extracción two-phase retiene hasta 2 GiB en RAM | M | Streaming al stage cuando el payload se acerque al cap |
| TD-42 | Brazo `{ok:false}` de `parse_refresh` inalcanzable en wire | M | Reasentar 4 tests a la forma real o documentar defensa |
| TD-53 | `--payload` del checkout arrastra `venv/` de 2,1 GB | M | Excluir runtime en `LocalPayload` o validar y abortar |
| TD-56 | Barra de progreso verificada solo en `TestBackend` | M | Smoke en TTY real capturando 2 frames separados |
| TD-58 | Byte-identidad en `db/`, `bin/`, `venv/` tras re-ejecución | M | Comparar árboles derivados o excluir del contrato |
| TD-60 | Panel dice «sin red» aunque el host esté inalcanzable | M | Distinguir host inalcanzable de sin red + e2e |
| TD-61 | `mirror_pending` sin sonda tras el consentimiento TUI | M | Sonda post-consentimiento con TTY simulado |
| TD-62 | Carrera hijo-ya-muerto no determinista en `run_inner` | M | Puerto/reloj inyectable para el veredicto del watcher |
| TD-64 | Test #9 Linux-only: depende de `setsid` | M | Sustituto portable o medirlo en Windows (TD-55) |
| TD-67 | `payload.rs` 759 líneas; walker duplicado ~25-30 líneas | M | Extraer walker con visitante (symlink/prune) y bajar a 500 |
| TD-69 | Redirecciones `ureq` sin re-validar esquema por salto | M | Decidir threat model; usar `https_only` por petición |
| TD-70 | `update` sin panel de consentimiento y `https_only` fijo | M | Resolver de payload único entre `install` y `update` |
| D6-3 | `verify.py` ignora provider y embebe en local siempre | M | Reusar fábrica `tepochcalli_mcp.embedder` desde `verify.py` |
| CR-1 | `_scrub` solo borra la cadena exacta del secreto | M | Normalizar encodings conocidos (URL, escapes JSON) |
| CR-7 | `O_EXCL`/retry multiusuario en `_write_atomic` | M | Solo si aparece caso multiusuario (TD-11/R5) |
| CR-8 | `db_size_bytes` sigue con `rglob` recursivo de `db/` | M | `os.scandir` de 1 nivel o caché por sesión |
| TD-7 | 40 skills logradas; `spec-payload-skills.md` aún dice 41 | S | Enmendar una línea a 40 en próxima pasada docs |
| TD-9 | `FutureWarning` de `get_sentence_embedding_dimension` sin disparar | S | Correr suite Phase 1 antes de aceptar bumps |
| TD-10 | `default_env_loop` interno de cocoindex tras pin 1.0.25 | S | Mantener oráculo: `uv.lock` + suite delta en cada bump |
| TD-12 | Extras de markitdown: venv 1,9 GiB aceptado en v1 | S | Revisar solo si aparece extra mínimo para PDF |
| TD-34 | Refs a skills/subagentes del payload sin verificar | S | `ls .opencode/skills` + grep de carga en QA (TD-31) |
| TD-63 | `split_once('\0')` sin ejercitador tras acotación | S | Extraer helper con test si aparece tercer consumidor |
| TD-66 | Guion agotado y Ctrl+C ambos `UserAborted` | S | Añadir contexto de uso si se necesita diagnóstico |
| TD-72 | `release.yml` ejecutado; falta archivar evidencia del guard | S | Archivar release+asset+`sha256sum -c` del guard |
| TD-73 | `THIRD-PARTY.md` sin textos completos de licencia | S | Generar aviso con textos antes de release GA |
| R5 | TOCTOU de slug en `add_source`, aceptado single-user | S | Evaluar `O_EXCL`/reintento si llega multi-proceso |
| D6-1 | `md-lint` con 422 errores de baseline (D12) | S | Limpiar baseline en pasada de aseo docs (ver nota) |
| D6-2 | `spec-embeddings` §37 omite `none` como provider | S | Enmendar línea a los tres valores: `local`, `litellm` y `none` |
| D6-6 | Primera indexación litellm: llamada extra de dims | S | Vigilar que cocoindex no la añada por pasada |
| F-T7-4 | Spec pide asserts de `took_ms` <500 en CI (anti-flake) | S | Enmendar §Testing: bench local, no CI |
| FIX_OFFLINE_NO_CACHE | Literal del `fix_hint` sin ancla en spec | S | Fijar literal en spec o test con fuente externa |
| Q-1 | CI sin gate de cobertura que `just ci` sí exige | S | Confirmar decisión: cobertura local-only |
| Q-2 | 4 puntos de margen: `refresh_lock` 83 %, `verify` 94 % | S | Cubrir ramas del lock y `verify.py` |
| Q-3 | Precedencia `VALIDATION_ERROR > E_NO_EMBEDDER` sin test | S | Test por pares al tocar `add_source` |
| CR-2 | `INDEXED_FIELDS` sin `Final` | S | Añadir `Final` al tocar `add_source` |
| CR-3 | `_meta_seam` rename pendiente en `rag_status` | S | Renombrar con el próximo wiring de `rag_status` |
| CR-4 | Shadowing de `effective_top_k` en `search.py` | S | Renombrar variable en próxima pasada sobre `search` |
| CR-5 | `.gitignore` propio del payload no verificado en el registro | S | Verificar cierre: ya existe con rutas runtime |

## Deuda no aceptada (evitada por diseño)

* RAG desde cero (BACKLOG.md lo prohíbe explícitamente) → mitigado por ADR-001.
* Daemon/puerto del índice o del MCP → evitado por ADR-002/005, verificable en bench.
* Python en el host del usuario → evitado por ADR-004 (uv gestiona CPython).
* Versiones de deps sin pinear → pyproject + uv.lock (TRD §4).
