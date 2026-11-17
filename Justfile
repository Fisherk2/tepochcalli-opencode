# Justfile — punto de entrada canónico de comandos de Tepochcalli.
#
# `just` sin argumentos ejecuta `quality`: el gate local de corrección
# (lint + formato + tipos + tests rápidos). `just ci` es el gate de integración:
# añade `sync`, el smoke de Δ y `rust-ci`.
#
# La cobertura NO está en `ci` (decisión del dueño 2026-11-12): `just coverage`
# es una corrida LOCAL de desarrollo, la más cara del repo, y se hace al cierre
# de fase. Ni `quality` ni `ci` la ejecutan, así que ambos caben en el día a
# día y coinciden con `.github/workflows/` (que tampoco la ejecuta). GitHub
# Actions nunca ha corrido en este repo (M6).
#
# REGLAS EXIGENTES DEL DUEÑO (2026-11-16):
#   1. La suite completa (cualquier lenguaje) dura ≤ 5 min.
#   2. `just coverage` dura < 30 min.
# Escritas por orden del dueño. El gate automático que las hace fallar NO
# existe aún: lo añade el orquestador en el paso siguiente con la cifra medida
# de 2026-11-16 (suite 27:53 con pytest-xdist -n 3; coverage 50m46s / 97 % ⇒
# la regla 2 todavía NO se cumple — medido honesto, sin maquillar).
#
# Se exporta UV_PROJECT_ENVIRONMENT=venv porque uv 0.12.9 ignora la clave
# `[tool.uv] project-environment` del pyproject.toml: la única forma de que uv
# reutilice obsidian-workspace/.tepochcalli/venv (en vez de crear `.venv`) es
# la variable de entorno. Exportarla aquí evita que cada persona la recuerde y
# garantiza paridad local ↔ CI, donde el workflow la fija exactamente igual.
#
# Contrato de nombres: `python-*` toca SOLO Python (venv del vault), `rust-*`
# toca SOLO el wizard Rust, y las recetas SIN prefijo son el punto de entrada
# agnóstico que conviene llamar (reparten a ambos lenguajes). Rust no tiene
# split `slow`/coverage/bench (`cargo tarpaulin` no está instalado): `test-unit`,
# `test-slow`, `test-file`, `coverage`, `bench`, `bench-smoke` y `bench-search`
# son solo-Python, y sus homónimas sin prefijo delegan únicamente en Python.
#
# Uso: `just --list` (recetas + descripción), `just --dry-run <receta>`.

# Falla ruidosamente en el primer error: ni pipes silenciosos ni variables vacías.
set shell := ["bash", "-euo", "pipefail", "-c"]

# Quirk uv 0.12.9 (ver cabecera): el venv del proyecto SOLO se honra por env var.
export UV_PROJECT_ENVIRONMENT := "venv"

# Raíz del proyecto Python (pyproject.toml + uv.lock + venv).
flow_dir := "obsidian-workspace/.tepochcalli"
# Ruff pineado a la misma versión que CI; corre desde la raíz para usar .ruff.toml.
ruff := "uvx ruff@0.17.1"

# Gate local completo por defecto: equivale a `just quality`.
default: quality

# --- Python: flow + MCP (todo lo `python-*` es exclusivo de este lenguaje) ---

# Sincroniza dependencias exactas de uv.lock dentro del venv del proyecto.
python-sync:
    cd {{flow_dir}} && uv sync --frozen

# Añade una dependencia al grupo dev del venv del vault. R1 (AGENTS.md):
# antes de ejecutar, verificar con `grep` en uv.lock/pyproject.toml que la
# capacidad no la aporta ya ninguna transitiva (nada de deps duplicadas).
# Ej.: `just python-add-dep pytest-xdist`.
python-add-dep name:
    cd {{flow_dir}} && uv add --group dev {{name}}

# ruff check desde la raíz del repo (aplica el .ruff.toml unificado).
python-lint:
    {{ruff}} check .

# ruff check con autofix; lo no mecánico se revisa a mano.
python-lint-fix:
    {{ruff}} check --fix .

# ruff format: reescribe los ficheros en sitio.
python-fmt:
    {{ruff}} format .

# ruff format --check: verifica sin escribir (modo CI).
python-fmt-check:
    {{ruff}} format --check .

# Sin argumentos: mypy usa `files = ["flow", "mcp"]` del pyproject — la
# superficie tipada que docs/CODE_STYLE.md anuncia desde la creación del
# paquete `tepochcalli_mcp` (Phase 2 T1). `python -m mypy` y no `mypy` a
# proposito: en este montaje NTFS el entrypoint venv/bin/mypy pierde el bit
# exec y `uv run mypy` cae en un mypy GLOBAL con otro Python, que no ve los
# tipos de terceros del venv (7 errores fantasma).
# Gate de tipos Python: mypy estricto sobre flow + mcp (misma forma que CI).
python-typecheck:
    cd {{flow_dir}} && uv run python -m mypy

# Suite de corrección: pytest -m "not slow" (el mismo filtro que usa CI).
# Medido 2026-11-16: 914 tests en 27:53–36:58 con pytest-xdist -n 3 (misma
# suite en serial: 45:25 el mismo día). Para iterar: `python-test-unit` /
# `python-test-file`.
python-test:
    cd {{flow_dir}} && uv run python -m pytest -m "not slow"

# Solo tests unitarios: iteración rápida sin integración ni e2e.
# `-c pyproject.toml` porque con un arg POSICIONAL (`../../tests/unit`) pytest
# busca la config en el ancestro común (raíz del repo, sin config) y NO lee el
# pyproject del vault: sin `-c`, unit se quedaría sin `-n 3` (medido 2026-11-16:
# sesión sin línea `configfile:` y sin workers gw*).
python-test-unit:
    cd {{flow_dir}} && uv run python -m pytest -c pyproject.toml ../../tests/unit

# Tests marcados `slow` (mediciones de latencia): no pertenecen a CI.
python-test-slow:
    cd {{flow_dir}} && uv run python -m pytest -m slow

# Tests que casan con un patrón -k: `just python-test-file delta`.
python-test-file name:
    cd {{flow_dir}} && uv run python -m pytest -k "{{name}}"

# Duraciones top-40 de la suite CORRECCION (misma suite que `python-test` con
# `--durations=40 -q`): auditoría de lentitud para la regla "suite completa
# ≤5 min" del dueño (2026-11-16) — ver qué tests se comen el tiempo.
# Medición local de desarrollo; NO está en `ci` ni en `quality`.
python-test-durations *args:
    cd {{flow_dir}} && uv run python -m pytest -m "not slow" --durations=40 -q {{args}}

# Gate de presupuesto de tiempo (regla exigente del dueño 2026-11-16): corre la
# suite COMPLETA y FALLA si supera los 300 s (5 min). Es el enforcement de la
# regla, no un comentario: mide, imprime la cifra y sale con 1 si se pasa.
# Cablearlo a `quality`/`ci` es decisión del hoy — hoy dejaría el gate en rojo
# (medido 27:53 el 2026-11-16), así que vive como receta propia.
suite-budget:
    #!/usr/bin/env bash
    # Sin `set -e` a propósito: un test en rojo NO debe cortar antes de imprimir
    # la cifra de presupuesto — es el dato que esta receta existe para dar.
    set -uo pipefail
    start="$(date +%s)"
    status=0
    cd {{flow_dir}} && uv run python -m pytest -m "not slow" -q || status=$?
    elapsed="$(( $(date +%s) - start ))"
    echo "suite-budget: ${elapsed}s de presupuesto 300s (regla del dueño 2026-11-16)"
    if [ "${status}" -ne 0 ]; then
        echo "FAIL: la suite está en rojo (exit ${status}); el presupuesto no se evalúa sobre una suite roja" >&2
        exit "${status}"
    fi
    if [ "${elapsed}" -gt 300 ]; then
        echo "FAIL: la suite completa excede el presupuesto de 300 s" >&2
        exit 1
    fi
    echo "PASS: la suite cabe en el presupuesto"

# Cobertura real con subprocesos (refresh/verify corren en hijos): gate >=95 %.
# Medido 2026-11-16: 50m46s, 97 % (regla 2 del dueño: <30 min — aún no cumplida).
python-coverage:
    cd {{flow_dir}} && uv run python -m coverage erase
    cd {{flow_dir}} && \
        PYTHONPATH=../../tests/support/covhook \
        COVERAGE_PROCESS_START=pyproject.toml \
        uv run python -m pytest -m "not slow" -q
    cd {{flow_dir}} && uv run python -m coverage combine
    cd {{flow_dir}} && uv run python -m coverage report -m

# Benchmark Δ completo con p95: medición local, nunca en CI.
python-bench:
    cd {{flow_dir}} && uv run python ../../tests/benchmarks/bench_delta.py

# Smoke Δ de 1 corrida con umbral generoso: el mismo bench que corre CI.
python-bench-smoke:
    cd {{flow_dir}} && uv run python ../../tests/benchmarks/bench_delta.py --smoke

# `just python-bench-search --smoke` = variante CI con umbral generoso (sin
# percentil); el p95 real NUNCA corre en CI (misma disciplina que bench, ver
# bench_search.py).
# Bench search p95 <500 ms (criterio 3) + presupuesto por etapa: medición LOCAL.
python-bench-search *args:
    cd {{flow_dir}} && uv run python ../../tests/benchmarks/bench_search.py {{args}}

# Bench de ESCALA del criterio 3 (10k md + 1k pdf, n=100) + deriva FTS ES/EN
# (Phase 6 T4): medición LOCAL, POR FASES en primer plano — la indexación en frío
# dura ~10 min y no cabe en una llamada. `--phase prepare|index|queries|stages|
# legs|probe|report` (o `all`); ver bench_search_scale.py.
python-bench-search-scale *args:
    cd {{flow_dir}} && uv run python ../../tests/benchmarks/bench_search_scale.py {{args}}

# Bench de extracción/indexación de documentos con markitdown (TD-2): medición LOCAL.
python-bench-documents *args:
    cd {{flow_dir}} && uv run python ../../tests/benchmarks/bench_documents.py {{args}}

# Impacto de D54 (Phase 6 T10, TD-27): headings que markitdown SÍ entrega en PDFs
# reales vs los que la política descarta, y campos de cita de una query cuyo único
# material es un PDF. Medición LOCAL, por fases: `--phase extract|corpus-sample|
# query|report`; ver bench_pdf_heading.py.
python-bench-pdf-heading *args:
    cd {{flow_dir}} && uv run python ../../tests/benchmarks/bench_pdf_heading.py {{args}}

# Criterio 1 (Phase 6 T9): no-interferencia sobre un vault INSTALADO por el
# wizard — `.obsidian/` byte-idéntico, 0 puertos nuevos, 0 basura oculta y
# vault válido tras `index_refresh`+`search`. Medición LOCAL.
# `--fault obsidian|port` demuestra que la guarda falla; `--evidence` archiva.
python-no-interference *args:
    cd {{flow_dir}} && uv run python ../../tests/e2e/verify_no_interference.py {{args}}

# Bench del criterio 6 a escala (Phase 6 T5): brazos 10 % vs 100 % (Δ p95 n=20 +
# search p95 n=100) y contraste btrfs vs fuseblk/NTFS-3G. Medición LOCAL, POR
# TRAMOS en primer plano: `--phase prepare|index10|search|walk|delta|ntfs|report`
# con `--arm b100|b10|ntfs --start N --cycles 5`; ver bench_scale_ratio.py.
python-bench-scale-ratio *args:
    cd {{flow_dir}} && uv run python ../../tests/benchmarks/bench_scale_ratio.py {{args}}

# --- Rust wizard (Phase 3, T18): nada de `cargo` crudo fuera de estas recipes ---
# `crate_dir` + `cd ... &&`: mismo patrón que `flow_dir` arriba (una línea
# por receta, porque `just` no conserva `cd` entre líneas).
crate_dir := "crates/tepochcalli"

# CARGO_TARGET_DIR (decisión del dueño 2026-11-16): en este montaje el repo
# vive en fuseblk/NTFS-3G, que no soporta el bit de ejecución, así que `cargo`
# muere compilando dependencias con `Permission denied (os error 13)` al lanzar
# el build-script de `libc` (verificado 2026-11-12; ver AGENTS.md).
# El directorio que pases DEBE estar en un filesystem que soporte ejecución
# (ext4, btrfs, tmpfs…): NUNCA en NTFS ni en ningún montaje fuseblk. `sudo` no
# lo arregla — es un límite del filesystem, no de permisos — y solo dejaría
# artefactos de root que después nadie puede limpiar.
# Sintaxis: receta primero y argumentos posicionales después,
# `just rust-test <directorio>`.
# REGLA DEL DUEÑO (2026-11-16): en ESTE entorno el directorio externo debe estar
# SIEMPRE bajo `/tmp/opencode/` — único directorio aprobado para uso externo.
# El agente NO debe crear directorios en ninguna otra ruta del sistema; si
# necesitas otro directorio de compilación, usa `/tmp/opencode/<nombre>`. El
# default de abajo ya cumple la regla. Fuera de este entorno, cualquier ruta que
# soporte ejecución vale, menos NTFS/fuseblk.
# El argumento es OPCIONAL (default abajo): sin él usamos este directorio, y así
# `just`, `just quality` y `just ci` —que encadenan a estas recetas sin reenviar
# argumentos— siguen funcionando. `rust-fmt` no lo necesita (`cargo fmt` no
# compila); solo lo necesitan las recetas que invocan `cargo build/test/clippy/
# run/publish`.
cargo_target := "/tmp/opencode/cargo-target"

# rustfmt en sitio: mismo comando que `rust-fmt`, pero escribiendo.
rust-fmt-fix:
    cd {{crate_dir}} && cargo fmt

# Compila el wizard (debug) para los scripts de aceptación.
rust-build target_dir=cargo_target:
    cd {{crate_dir}} && CARGO_TARGET_DIR="{{target_dir}}" cargo build --locked

# Formato del wizard (falla si algo habría que reescribir). No compila, así que
# no necesita el directorio de destino.
rust-fmt:
    cd {{crate_dir}} && cargo fmt --check

# Clippy estricto sobre lib + bins + tests (falla con el primer warning).
rust-lint target_dir=cargo_target:
    cd {{crate_dir}} && CARGO_TARGET_DIR="{{target_dir}}" cargo clippy --locked --all-targets -- -D warnings

# Suite del wizard (cubre los 5 caminos del menú con fakes, sin red).
rust-test target_dir=cargo_target:
    cd {{crate_dir}} && CARGO_TARGET_DIR="{{target_dir}}" cargo test --locked

# Tests Rust filtrados por subcadena del nombre (iteración sin re-ejecutar
# toda la suite): `just rust-test-filter f8_real_venv`. El directorio, si quieres
# pasarlo, va DESPUÉS del nombre: `just rust-test-filter f8_real_venv /ruta/dir`.
rust-test-filter name target_dir=cargo_target:
    cd {{crate_dir}} && CARGO_TARGET_DIR="{{target_dir}}" cargo test --locked {{name}}

# Gate Rust local: espejo del job `rust` de `.github/workflows/phase3.yml`.
# Reenvía el directorio a las dos recetas que compilan; `rust-fmt` no lo usa.
rust-ci target_dir=cargo_target: rust-fmt (rust-lint target_dir) (rust-test target_dir)

# Verifica el paquete tal como lo verá crates.io (metadata, .crate, build de
# verificación) SIN subir nada. Requiere red para el índice de crates.io.
# `--allow-dirty` porque el flujo normal es publicar desde un árbol con el
# cambio de versión aún sin commitear; no afecta a lo que se empaqueta.
rust-publish-dry-run target_dir=cargo_target:
    cd {{crate_dir}} && CARGO_TARGET_DIR="{{target_dir}}" cargo publish --dry-run --locked

# Publica la versión actual en crates.io (requiere `cargo login` antes).
# NUNCA en `ci`: publicar no es un gate.
rust-publish target_dir=cargo_target:
    cd {{crate_dir}} && CARGO_TARGET_DIR="{{target_dir}}" cargo publish --locked

# Path 5: `--skip-model`, sin descargar modelos de 470 MB; la red solo se usa
# para `uv` y `uv sync`. Espejo del job `smoke` de `phase3.yml` con el payload
# local del repo.
# Smoke local del instalador en un vault efímero.
rust-smoke target_dir=cargo_target:
    #!/usr/bin/env bash
    set -euo pipefail
    export CARGO_TARGET_DIR="{{target_dir}}"
    work="$(mktemp -d)"
    trap 'rm -rf -- "${work}"' EXIT
    payload="${work}/payload/.tepochcalli"
    vault="${work}/vault"
    mkdir -p "${payload}"
    cp obsidian-workspace/.tepochcalli/pyproject.toml \
        obsidian-workspace/.tepochcalli/uv.lock \
        "${payload}/"
    cp -r obsidian-workspace/.tepochcalli/flow \
        obsidian-workspace/.tepochcalli/mcp \
        "${payload}/"
    cargo run --locked --manifest-path crates/tepochcalli/Cargo.toml -- install \
        --non-interactive --skip-model \
        --vault "${vault}" \
        --payload "${work}/payload"
    test -f "${vault}/00-resources/ejemplo.md"
    test -f "${vault}/00-resources/ejemplo.pdf"
    grep -q '"tepochcalli-rag"' "${vault}/opencode.json"
    echo "wizard-smoke OK: path-5 instalado y verificado (vault efímero ya borrado)"

# Se conserva porque `.github/workflows/release.yml`, CHANGELOG.md y los
# registros de tareas citan el nombre antiguo; retirar tras actualizarlos.
# Alias obsoleto de `rust-smoke`.
wizard-smoke: rust-smoke

# --- Punto de entrada agnóstico: reparte a Python y Rust (las de un solo
# lenguaje se quedan abajo, documentadas como tales) ---

# Dependencias exactas del venv Python.
sync: python-sync

# Lint de ambos lenguajes: ruff + clippy.
lint: python-lint rust-lint

# Autofix Python. Rust no ofrece autofix: `clippy --fix` reescribe código en silencio.
lint-fix: python-lint-fix

# Formatea ambos lenguajes: ruff format + rustfmt en sitio.
fmt: python-fmt rust-fmt-fix

# Verifica formato sin escribir: ruff format --check + cargo fmt --check.
fmt-check: python-fmt-check rust-fmt

# Gate de tipos Python. El de Rust es `rust-lint`: clippy compila todo con `-D warnings`.
typecheck: python-typecheck

# Tests rápidos de ambos lenguajes.
test: python-test rust-test

# Solo unitarios Python: Rust no tiene split unit/integración a este nivel.
test-unit: python-test-unit

# Solo tests `slow` Python (latencia): Rust no tiene marca equivalente.
test-slow: python-test-slow

# Tests Python que casan con -k: `just test-file delta`.
test-file name: (python-test-file name)

# Cobertura Python con umbral 95 %: Rust no tiene equivalente (falta cargo tarpaulin).
coverage: python-coverage

# Benchmark Δ completo Python (p95).
bench: python-bench

# Smoke Δ Python de 1 corrida (el que corre CI).
bench-smoke: python-bench-smoke

# Destino del bench de búsqueda desde la raíz (`python-bench-search`).
# `args=` en vez de `*args`: just 1.59 no reenvía variádicos a una dependencia.
# `just bench-search --smoke` = variante CI del bench de búsqueda.
bench-search args="": (python-bench-search args)

# Bench de escala del criterio 3 (10k/1k, n=100) + deriva FTS ES/EN — por fases.
bench-search-scale args="": (python-bench-search-scale args)

# Destino del bench del criterio 6 (brazos 10 % vs 100 % + fuseblk) desde la raíz.
bench-scale-ratio args="": (python-bench-scale-ratio args)

# Markdown lint de docs/specs/AGENTS.md/SPEC.md (markdownlint-cli2 vía npx).
md-lint:
    npx --yes markdownlint-cli2 docs specs AGENTS.md SPEC.md

# Gate local: lint → fmt-check → typecheck → test (corta en el primer fallo).
# Cubre los dos lenguajes (Python + wizard Rust): no hay gate parcial de un solo lado.
quality: lint fmt-check typecheck test

# Espejo local del gate de integración: sync → lint → fmt-check → typecheck →
# test → smoke → rust-ci. La COBERTURA no entra (decisión del dueño 2026-11-12):
# `just coverage` corre la misma suite instrumentada (50m46s y 97 % medidos el
# 2026-11-16 con pytest-xdist -n 3 — fuera aún de la regla <30 min del dueño),
# subprocesos incluidos; es una medición local que se hace al cierre de fase,
# no en cada gate. `test` y `ci` son por tanto el mismo conjunto que ejecuta CI.
# Rust no tiene coverage: su lado corre `rust-ci` (= fmt + clippy + test).
# Gate de integración completo: Python (sync…bench-smoke) + rust-ci.
ci: python-sync lint fmt-check typecheck test bench-smoke rust-ci

# Cualquier `.venv` accidental lo crea un `uv` invocado a mano sin
# UV_PROJECT_ENVIRONMENT. No toca fuentes ni `venv/`.
# DESTRUCTIVO: borra caches locales y `.venv` accidentales.
clean:
    rm -r -f .pytest_cache .ruff_cache .mypy_cache {{flow_dir}}/.venv
    find . -name .git -prune -o -type d -name __pycache__ -prune -exec rm -r -f {} +
