# Corpus de escala reutilizable con manifiesto (Phase 6 · T1)

> **Fecha:** 2026-11-12 · **Fase:** Phase 6 — E2E Acceptance · **Calpulli:** T1
> **Estado:** entregado; **sin commit** (lo integra el orquestador).
> **Fuente de verdad:** `tasks/plan.md` §5 T1 · `tasks/todo.md` T1 · `docs/acceptance/protocol.md` §1 (host).
> **Jerarquía de evidencia (D8):** todas las cifras de este documento son **`medido`** en el host de
> referencia (btrfs/NVMe, `/tmp/opencode`) con el intérprete pineado del venv; cada una lleva su comando.

## 1. Qué se materializó

| Hecho | Valor |
| --- | --- |
| Notas markdown | **10 000** en **10 subdirs** `00-resources/notas-00…09` (1 000 cada uno) |
| PDFs | **1 000** de 1 página, PDF-1.4 válido (xref computado, texto extraíble), en `00-resources/pdfs/` |
| Semilla | **20261103** (la misma del bench `bench_delta_scale.py`; ahora es `DEFAULT_SEED` del generador) |
| `generator_version` | **"1"** |
| Manifiesto | `corpus-manifest.json` en la **raíz** del corpus (fuera de `00-resources/`, no indexable) |
| Raíz materializada | `/tmp/opencode/phase6-corpus` (btrfs: `df -T /tmp/opencode` → `/dev/nvme0n1p3 btrfs`) |
| Ficheros en disco | **11 001** (`find -type f` + `wc -l`: 11 000 del corpus + el manifiesto) |

El generador vive en **un solo sitio**, `tests/support/corpus.py`, y lo consumen los tres clientes:
el bench de escala (lo **importa**, ya no duplica la lógica), el CLI del propio módulo y los tests
del manifiesto.

## 2. Tiempo de materialización, tamaño y hash

| Medición | Valor | Método (comando) |
| --- | --- | --- |
| Materialización fría #1 | **2 677 ms** | reloj **monotónico** (`time.monotonic()`) dentro del CLI |
| Materialización fría #2 (dir nuevo) | **2 276 ms** (2,403 s de pared) | `time.monotonic()` + `time` del shell |
| Verificación de un corpus ya materializado | **1 348–1 495 ms** | el mismo CLI en modo reutilización (hashea 11 000 ficheros) |
| Tamaño aparente del corpus | **10 586 197 B** (10,1 MiB) en 11 000 ficheros | `totals.bytes` del manifiesto |
| Tamaño en disco | **45 M** | `du -sh /tmp/opencode/phase6-corpus` |
| Manifiesto | **1 623 185 B** (1,5 MiB) | `stat -c %s corpus-manifest.json` |

Los 45 M de `du` frente a los ~11,7 MiB aparentes (`du -sb` → 12 209 382 B) son el coste de bloque
en btrfs para ficheros de ~0,5-1,2 KB: **no** es un defecto del corpus, es cómo el FS redondea.
La materialización inicial es de segundos, no de los ~10 min que costaba la indexación en frío:
lo caro es el índice, no el corpus.

## 3. Reproducibilidad — hashes

| Artefacto | Valor |
| --- | --- |
| `tree_sha256` (sha256 de las líneas `<sha256>  <ruta>` ordenadas) | `27a20c0563902ca304128aff3d30c63ce6454e8802061f7e19226a0e4983ecd2` |
| `sha256` del fichero `corpus-manifest.json` | `559a2362cfd4a54a7d666e547d2e9c85fb8cc6e92c0d3bde1cbbd4e53c85e5b8` |

Evidencia de que es **el mismo corpus** y no una carpeta parecida:

1. **Tres materializaciones** (dos completas + una de medición) dieron el **mismo**
   `tree_sha256` y el **mismo** `sha256` de manifiesto; la segunda se materializó en
   `/tmp/opencode/phase6-corpus-b` y `cmp` de los dos JSON canónicos salió idéntico
   (`manifiestos byte a byte idénticos`). El directorio `-b` se borró después (lo creó ese script).
2. **Contraste con el generador anterior:** el `_seed_corpus` que vivía dentro de
   `bench_delta_scale.py` en `HEAD` se ejecutó aparte y los **11 000** `sha256sum` de los dos
   árboles son byte a byte iguales (`cmp` de las listas → OK). El refactor **no cambió un byte**
   de lo que el bench materializaba; solo le quitó la lógica duplicada.
3. El manifiesto **no contiene** timestamps, rutas absolutas ni orden de escritura: es
   `json.dumps(sort_keys=True, separators=(",", ":"))` sobre `files` ordenado por ruta. Por eso
   dos carpetas distintas producen el mismo texto.

## 4. Reutilización sin reindexar

`materialize_or_verify(root, ...)` es la puerta de los calpullis que necesitan el corpus
(T4/T5): si encuentra `corpus-manifest.json`, **verifica** los hashes y se salta la
materialización (1,3-1,5 s, medido arriba); si no lo encuentra, materializa.

Contrato defensivo (probado en el test y a mano sobre el corpus real):

* corpus íntegro ⇒ `reused: true`, **cero escrituras** (los `mtime_ns` de la muestra no cambian);
* un fichero alterado ⇒ `RuntimeError: corpus alterado en … (2 discrepancias): tamaño distinto …
  sha256 distinto …` y **no se regenera en silencio** (el fichero manipulado sigue como estaba);
* manifiesto de otra seed/cuenta ⇒ `RuntimeError` (no se pisa un corpus ajeno ni se borra nada).

## 5. Forma del manifiesto

```json
{"files":[{"bytes":907,"kind":"md","path":"00-resources/notas-00/nota-00000.md","sha256":"…"}],
 "generator_version":"1","seed":20261103,
 "totals":{"bytes":10586197,"files":11000,"md":10000,"pdf":1000},
 "tree_sha256":"27a20c…3ecd2"}
```

`path` es **relativo a la raíz del corpus** (POSIX), `kind` ∈ `md|pdf`. Cambiar el contenido
generado obliga a subir `GENERATOR_VERSION`, que es lo que invalida manifiestos viejos.

## 6. Guarda de no-interferencia

`obsidian-workspace/.tepochcalli/{db,models}` **no existen** en este checkout, antes ni después:

```text
stat: cannot statx '…/obsidian-workspace/.tepochcalli/db': No such file or directory
stat: cannot statx '…/obsidian-workspace/.tepochcalli/models': No such file or directory
-- ficheros del payload modificados durante la corrida (find -newer):
(vacío = el corpus no tocó el payload)
```

El corpus escribe **solo** bajo `--root`; el manifiesto va a la raíz de esa misma `--root`. No
hay ninguna ruta de escritura hacia el payload: el bench conserva su comprobación final y esta
medición la repite (`find obsidian-workspace -newer <marca>` vacío).

## 7. TDD: rojo antes del módulo

Test escrito primero (`tests/support/test_corpus_manifest.py`, corpus diminuto 5 md + 3 pdf):

```text
$ cd obsidian-workspace/.tepochcalli && uv run python -m pytest ../../tests/support/test_corpus_manifest.py -q
E   ModuleNotFoundError: No module named 'corpus'
ERROR ../../tests/support/test_corpus_manifest.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
```

Verde tras crear `tests/support/corpus.py`:

```text
5 passed in 0.23s
```

Cubre: (a) una entrada por fichero con `path`/`sha256`/`bytes`/`kind` + `seed`,
`generator_version` y `totals`; (b) misma seed ⇒ JSON canónico y hash de árbol idénticos;
(c) manifiesto válido ⇒ reutilización con `mtime_ns` intactos; (d) manifiesto ausente ⇒
materializa; (e) fichero alterado ⇒ discrepancias y `RuntimeError` sin regenerar.

`tests/support/` se añadió a `testpaths` en `obsidian-workspace/.tepochcalli/pyproject.toml`
(**una línea**): sin ella el gate no recolectaría el test del manifiesto. No se tocó ningún
fichero de contenido del payload (`.opencode/`, `AGENTS.md`, `opencode.json`).

## 8. Estado de los gates

| Gate | Resultado |
| --- | --- |
| `just python-lint` (`ruff check .`) | **All checks passed** |
| `just python-fmt-check` | **171 files already formatted** |
| `just python-typecheck` (`mypy --strict`, 40 ficheros) | **Success: no issues found** |
| `just md-lint` | **0 issues** |
| Suite completa (receta de la época: `python-test`; hoy `just ci`) | **747 passed, 3 deselected, 63 failed** |
| `just rust-ci` | **no ejecutable en este checkout** (ver abajo) |
| bench de escala | sigue **fuera** de `just ci` (no es `test_*`; runtime dominado por la indexación en frío) |

**Los 63 fallos de esa corrida (receta de la época: `python-test`) son pre-existentes y ajenos a T1** — todos en
`test_payload_permissions.py` (62) y `test_opencode_payload_registration.py` (1), que leen los
bloques `permissions` de `obsidian-workspace/.opencode/agents/*.md` y esperan `deny` donde hoy
hay `ask` (p. ej. `.env` en `itzamna.md`, que no declara reglas `read`). Verificado en un
worktree **limpio** en `HEAD` (`c2d19c9`, `/tmp/opencode/t1-pristine`, borrado después):
**63 failed, 26 passed en 3,51 s** — el mismo rojo, sin una sola línea mía en el árbol. No se
corrige aquí: el payload está **congelado** (D-P6-1) y el arreglo pertenece a su dueño. Queda
declarado como hallazgo abierto para el FTR.

**`rust-ci` no corre en este checkout:** `cargo clippy` falla compilando `libc 0.2.191` con
`could not execute process … /build-script-build (never executed): Permission denied (os error 13)`.
El repo vive en `fuseblk` (NTFS-3G) y el binario de build-script no es ejecutable ahí — es el
límite de entorno ya conocido del montaje, no un efecto de T1 (que no toca `crates/`:
`git status` no muestra ningún fichero de Rust). Por eso **`just quality` como receta completa
no puede salir verde en este checkout**; se ejecutaron sus mitades ejecutables una a una
(arriba) y el lado Rust se declara **no ejecutado**, no verde.

## 9. Comandos

```bash
# materializar (o reutilizar si el manifiesto verifica) el corpus completo.
# `UV_PROJECT_ENVIRONMENT=venv` es el quirk documentado del Justfile: sin él
# `uv` crea `.tepochcalli/.venv` (1,9 GB) en vez de reutilizar el venv del payload.
UV_PROJECT_ENVIRONMENT=venv uv run --project obsidian-workspace/.tepochcalli \
    python tests/support/corpus.py \
    --root /tmp/opencode/phase6-corpus --md 10000 --pdf 1000 --seed 20261103

# equivalente sin `uv` (el intérprete pineado del payload, el de las mediciones)
obsidian-workspace/.tepochcalli/venv/bin/python tests/support/corpus.py \
    --root /tmp/opencode/phase6-corpus --md 10000 --pdf 1000 --seed 20261103

# test del manifiesto (diminuto, <2 s, sí está en `just ci`)
just python-test-file corpus_manifest

# el bench de escala sigue igual de invocable (--dir/--keep intactos) y ahora importa el generador
cd obsidian-workspace/.tepochcalli && uv run python ../../tests/benchmarks/bench_delta_scale.py --dir /tmp/opencode
```

## 10. Lo que este calpulli NO hace

* No indexa el corpus (eso es T4/T5): aquí solo se materializa y se verifica.
* No publica cifras de Δ ni de `search` (criterios 2 y 3): esos números son de otros calpullis.
* No toca `docs/TRD.md`, `docs/BACKLOG.md`, `README.md` ni el payload de contenido.
* No commitea: deja 4 ficheros de código/config para el orquestador
  (`tests/support/corpus.py`, `tests/support/test_corpus_manifest.py`,
  `tests/benchmarks/bench_delta_scale.py` y la línea de `testpaths` en
  `obsidian-workspace/.tepochcalli/pyproject.toml`) más este informe.
