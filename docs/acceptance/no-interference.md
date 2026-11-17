# Criterio 1: no-interferencia con Obsidian (Phase 6 · T9)

> **Fecha:** 2026-11-13 · **Fase:** Phase 6 — E2E Acceptance · **Calpulli:** T9
> **Estado:** entregado; **sin commit** (lo integra el orquestador).
> **Fuente de verdad:** `docs/UH.md` línea 46 (inmutable) — «El vault de Obsidian funciona
> normalmente sin interferencias» · `tasks/plan.md` §Task T9 · `specs/spec-vault-structure.md`
> §Reglas de no-interferencia (reglas 1-6) y §Testing (checklist **ejecutado**, no reescrito) ·
> ADR-002/ADR-005 (sin daemon, sin puerto).
> **Jerarquía de evidencia (D8):** todo lo de §3-§6 es **`medido`** (vault instalado por el
> wizard + servidor real por stdio); la equivalencia con la API de workspace de Obsidian es
> **`declarado`** (§8).
> **Evidencia archivada:** [no-interference.json](no-interference.json) (comandos, hashes,
> las dos listas `ss -ltnp` completas, payload de `index_refresh`/`search` y veredicto).

## 1. Resultado en una línea

**PASS en las cuatro caras, con trabajo real del motor**: `.obsidian/` byte-idéntico
(`sha256 751186fc…`, 2 ficheros), **0 puertos nuevos** (12 listeners antes y después, la lista
se publica en §5), **0 basura oculta** fuera de las carpetas esperadas y el vault sigue siendo
válido; y la guarda **sabe fallar** (§6): dos corridas con fallo inyectado salen 1.

## 2. Método

| Paso | Qué hace | Qué prueba |
| --- | --- | --- |
| Install | `tepochcalli install --non-interactive --skip-model --vault <tmp> --payload <payload>`, con el payload = template **completo** de `obsidian-workspace/` (mismas exclusiones de runtime que `.github/workflows/release.yml`) | el vault es producto instalado por el wizard, no un directorio a mano |
| Embedder | `tepochcalli config embedder --non-interactive --confirm` (re-entrada que el propio wizard imprime para la ruta 5), con el snapshot del modelo enlazado desde el cache HF del host | el motor tiene índice y responde: `provider=local`, `dims 384`, `RSS pico 1240MB` |
| Obsidian | se crean `.obsidian/app.json` + `.obsidian/workspace.json` (el wizard no toca `.obsidian/`) | hay algo que Obsidian habría escrito y que el producto no puede modificar |
| Motor | `index_refresh()` + `search("marcador de la medición de no-interferencia")` por **stdio**, con el server spawneado **exactamente como el harness**: `command`/`args`/`cwd`/`environment` leídos de `opencode.json` | el camino real de escritura/lectura corre entre las dos capturas |
| Capturas | hash de árbol de `.obsidian/` (rutas + bytes, nunca `mtime`) y `ss -ltnp` antes/después; árbol de entradas ocultas; validez del vault | (a)-(d) |

Comando exacto:

```bash
CARGO_TARGET_DIR=/tmp/opencode/cargo-target just rust-build   # una vez
just python-no-interference --evidence docs/acceptance/no-interference.json   # ~2 min
```

Nota de flags: el wizard instala con `--vault <ruta>` (`spec-installer-wizard` §flags); `--dir`
no existe en este binario. El `--skip-model` deja salida-5 **degradada** (ADR-007 D7.1-5), y la
re-entrada documentada es la que se ejecuta en el paso «Embedder».

## 3. Resultado por cara

| Cara | Medición | Resultado |
| --- | --- | --- |
| (a) `.obsidian/` byte-idéntico | `sha256` de árbol antes `751186fc6685e6f3…` = después `751186fc6685e6f3…`; ficheros `app.json`, `workspace.json` | **PASS** |
| (b) 0 puertos nuevos | `ss -ltnp` antes 12 listeners, después 12 listeners; diferencia de endpoints = `[]` | **PASS** |
| (c) 0 basura oculta | raíz con solo `.gitignore`, `.opencode/`, `.tepochcalli/`, `.obsidian/` (+ ausentes `.git/`, `.trash/`); `.gitkeep` del payload en las bandejas; violaciones `[]` | **PASS** |
| (d) vault válido | `opencode.json` parseable y con `mcp.servers.tepochcalli-rag`; `AGENTS.md` presente; bandejas `00-resources`, `01-tasks`, `02-drafts`, `03-citations`, `04-review`, `05-outputs` presentes | **PASS** |
| — trabajo real del motor | `index_refresh` → `scanned=1, indexed=1, skipped=0, elapsed_ms=13281, roots=["00-resources"]`; `search` → 1 resultado, `source_path = 00-resources/nota-t9-no-interferencia.md` | **PASS** |

El motor hizo trabajo de verdad dentro de la ventana medida (un fichero nuevo indexado y
recuperado por `search`): no es un PASS por no haber invocado nada.

### Interpretación de (c) — declarada

`spec-vault-structure` §Testing pide «0 archivos `.`-prefijados listados en la API de workspace
de Obsidian». En un vault instalado hay carpetas ocultas **esperadas** y no cuentan como
interferencia: `.tepochcalli/` (runtime, D2), `.opencode/` (harness), `.obsidian/` (el usuario),
`.git/`, `.trash/` y el `.gitignore` del payload; y los `.gitkeep` con que el payload versiona
bandejas vacías. Lo que se persigue es que el producto **no esparza** basura oculta, así que
**cualquier otra** entrada punto-prefijada —en la raíz o a cualquier profundidad fuera de esos
subárboles— es violación. La comprobación recorre el árbol real (no hay API de Obsidian en un
test sin GUI): es la equivalencia `declarado` de §8.

## 4. Las reglas de `spec-vault-structure` §Reglas de no-interferencia, ejecutadas

| Regla | Cómo la cubre esta corrida |
| --- | --- |
| 1. Todo el runtime bajo punto-prefijo | (c): la única carpeta de runtime es `.tepochcalli/`; 0 entradas ocultas fuera de las esperadas |
| 2. Sin plugins ni JS en `.obsidian/` | (a): hash de árbol idéntico ⇒ cero escrituras |
| 3. Sin procesos residentes | el server se arranca por stdio **desde el test** y muere al cerrar la sesión; no queda proceso (el script no deja hijos) |
| 4. Sin puertos escuchados | (b) con `ss -ltnp` antes/después (§5) |
| 5. Escrituras atómicas dentro de `.tepochcalli/` | el árbol visible solo cambia donde el test lo pidió (`00-resources/nota-…md`); (c) no ve residuos |
| 6. Compatibilidad de sync | artefactos de runtime gitignored: `.tepochcalli/{db,models,venv,bin,config}` quedan dentro de la carpeta oculta, no en el árbol visible |

La checklist de §Testing se **ejecuta** tal cual (assert `.obsidian/` byte-idéntico, 0
puertos nuevos, 0 archivos punto-prefijados); no se reescribió la spec.

## 5. Las dos listas `ss -ltnp` (publicadas)

Idénticas antes y después (12 listeners, todos del host: opencode, plasmashell, megasync,
vesktop, kdeconnect, electron, sshd, cups). Ningún puerto del vault ni del motor.

```text
State  Recv-Q Send-Q Local Address:Port  Peer Address:PortProcess
LISTEN 0      4096       127.0.0.1:35001      0.0.0.0:*
LISTEN 0      512        127.0.0.1:49374      0.0.0.0:*    users:(("opencode",pid=5106,fd=10))
LISTEN 0      50         127.0.0.1:33053      0.0.0.0:*    users:(("plasmashell",pid=1185,fd=23))
LISTEN 0      4096       127.0.0.1:631        0.0.0.0:*
LISTEN 0      50         127.0.0.1:6341       0.0.0.0:*    users:(("megasync",pid=1499,fd=68))
LISTEN 0      511        127.0.0.1:6463       0.0.0.0:*    users:(("vesktop",pid=1510,fd=115))
LISTEN 0      128          0.0.0.0:22         0.0.0.0:*
LISTEN 0      4096               *:6566             *:*
LISTEN 0      4096           [::1]:631           [::]:*
LISTEN 0      128             [::]:22            [::]:*
LISTEN 0      50                 *:1716             *:*    users:(("kdeconnectd",pid=1505,fd=17))
LISTEN 0      511                *:34571            *:*    users:(("electron",pid=34811,fd=99))
```

`before` y `after` son la misma lista; la comparación se hace sobre el **conjunto de endpoints**
(`Local Address:Port`), no sobre el texto, para que un reordenamiento no dé un falso PASS ni un
falso FAIL. Si aparece un endpoint nuevo, se re-lee `ss` una vez tras 1 s: un puerto real
persiste, un ruido del host no (§6, RED 2).

## 6. RED archivado — la guarda sabe fallar

Dos corridas con `--fault` (inyección a propósito **entre** las capturas; nunca para aceptar):

**(1) `.obsidian/app.json` modificado a propósito** ⇒ falla (a) y sale 1:

```text
just python-no-interference --fault obsidian --evidence /tmp/opencode/t9-red-obsidian.json
resultados: {"obsidian_identical": false, "no_new_ports": true, "no_hidden_litter": true,
             "vault_valid": true, "engine_did_work": true}
VERDICT: FAIL                                  # exit 1
```

**(2) `socket` a la escucha abierto a propósito** ⇒ falla (b) y sale 1:

```text
just python-no-interference --fault port --evidence /tmp/opencode/t9-red-port.json
(b) puertos nuevos: ['127.0.0.1:47923']
resultados: {"obsidian_identical": true, "no_new_ports": false, "no_hidden_litter": true,
             "vault_valid": true, "engine_did_work": true}
VERDICT: FAIL                                  # exit 1
```

Ambas corridas instalan el vault y ejecutan el motor igual que la verde: lo único que cambia es
la interrupción inyectada. El resto de caras siguen PASS, así que el fallo es **del caso
provocado**, no un error de montaje.

## 7. Hallazgo colateral (no es criterio 1): alias `00-Resources` / `00-resources`

Medido en el mismo vault instalado: el wizard crea `00-Resources/` con sus 2 placeholders
(D22) y el payload trae `00-resources/` (con `.gitkeep`), y `index_refresh` reporta
`roots=["00-resources"]`. En un filesystem sensible a mayúsculas eso deja **dos** carpetas y el
material que el usuario escriba en `00-Resources/` (la carpeta que anuncia el `AGENTS.md` del
vault y D9.1) **no se indexa**. Es la *Open Question* de `spec-vault-structure` §Open Questions,
no una decisión de T9: se publica como observación en el JSON (`observations`) y queda para el
orquestador como deuda candidata. El criterio 1 no se ve afectado (la nota medida se depositó
en la raíz efectiva para que el motor trabajara de verdad).

**Resuelto 2026-11-13:** el canónico pasó a `00-resources/` en las tres capas (flow, payload y
wizard) — ver [spec-vault-structure](../../specs/spec-vault-structure.md) §Enmienda 2026-11-13.
Este apartado se conserva como registro de la medición (JSON y cifras sin tocar).

## 8. Límites de esta medición (declarados)

* **`n = 1`** corrida por cara: es un checklist, no una estadística. Sin latencia como criterio
  (eso es T4/T5); `elapsed_ms=13281` solo documenta que el refresh hizo trabajo.
* **No hay Obsidian en el bucle.** La igualdad con «la API de workspace de Obsidian» es
  `declarado`: se aproxima con el árbol real y el hash de bytes, y con `.obsidian/` sembrado a
  mano. Una corrida con Obsidian real es manual (§Phase 6, QA humano) y no se simula aquí.
* **Puertos:** `ss` ve sockets del host; la ventana es de ~2 min, así que un proceso ajeno que
  abriera un puerto justo entonces daría un FAIL con su endpoint publicado (y la re-lectura de
  1 s descarta el ruido de un cierre). No se filtra por proceso dueño para no ocultar un
  listener del motor.
* **Payload local** (mismo árbol que empaqueta `release.yml`, sin runtime) en vez del asset de
  una release publicada: el install es el mismo (`--payload` es la costura documentada de
  dev/tests); M6 sigue vigente, esta corrida **no** valida un asset de GitHub.
* El vault se instala en `btrfs/NVMe` (`/tmp/opencode`), no en el montaje NTFS-3G del repo: el
  bit de ejecución del venv no sobrevive en fuseblk, y aquí lo que se mide no es el FS.

## 9. Comando y artefactos

```bash
CARGO_TARGET_DIR=/tmp/opencode/cargo-target just rust-build
just python-no-interference --evidence docs/acceptance/no-interference.json
```

* Script: `tests/e2e/verify_no_interference.py` (recetas `rust-build` y `python-no-interference`).
* JSON de evidencia: [no-interference.json](no-interference.json) — incluye `install`,
  `embedder`, hashes antes/después, las dos listas `ss` crudas, el payload de las dos tools,
  `results` y `verdict`.
* No entra en ninguna suite de módulo (`just test-mcp` / `test-engine` / `test-converter`) como
  test: es un script de aceptación que **instala un vault** (~2 min) y no debe correr en cada
  push.
