# Justfile — punto de entrada canónico de comandos de Tepochcalli.
#
# `just` sin argumentos ejecuta `quality`: el gate local de corrección
# (lint + formato + tipos + tests rápidos). `just ci` reproduce el orden exacto
# del gate de .github/workflows/phase1.yml, para verificar en local lo mismo
# que muerde en CI.
#
# Se exporta UV_PROJECT_ENVIRONMENT=venv porque uv 0.12.9 ignora la clave
# `[tool.uv] project-environment` del pyproject.toml: la única forma de que uv
# reutilice obsidian-workspace/.tepochcalli/venv (en vez de crear `.venv`) es
# la variable de entorno. Exportarla aquí evita que cada persona la recuerde y
# garantiza paridad local ↔ CI, donde el workflow la fija exactamente igual.
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

# Sincroniza dependencias exactas de uv.lock dentro del venv del proyecto.
sync:
    cd {{flow_dir}} && uv sync --frozen

# ruff check desde la raíz del repo (aplica el .ruff.toml unificado).
lint:
    {{ruff}} check .

# ruff check con autofix; lo no mecánico se revisa a mano.
lint-fix:
    {{ruff}} check --fix .

# ruff format: reescribe los ficheros en sitio.
fmt:
    {{ruff}} format .

# ruff format --check: verifica sin escribir (modo CI).
fmt-check:
    {{ruff}} format --check .

# mypy estricto sobre flow + mcp (misma forma que CI: `python -m`, ver abajo).
# Sin argumentos: mypy usa `files = ["flow", "mcp"]` del pyproject — la
# superficie tipada que docs/CODE_STYLE.md anuncia desde la creación del
# paquete `tepochcalli_mcp` (Phase 2 T1).
#
# `python -m mypy` y no `mypy` a proposito: en este montaje NTFS el entrypoint
# venv/bin/mypy pierde el bit exec y `uv run mypy` cae en un mypy GLOBAL con
# otro Python, que no ve los tipos de terceros del venv (7 errores fantasma).
# `python -m` resuelve siempre el mypy del venv; en CI el resultado es identico.
typecheck:
    cd {{flow_dir}} && uv run python -m mypy

# Suite de corrección: pytest -m "not slow" (el mismo filtro que usa CI).
test:
    cd {{flow_dir}} && uv run python -m pytest -m "not slow"

# Solo tests unitarios: iteración rápida sin integración ni e2e.
test-unit:
    cd {{flow_dir}} && uv run python -m pytest ../../tests/unit

# Tests marcados `slow` (mediciones de latencia): no pertenecen a CI.
test-slow:
    cd {{flow_dir}} && uv run python -m pytest -m slow

# Tests que casan con un patrón -k: `just test-file delta`.
test-file name:
    cd {{flow_dir}} && uv run python -m pytest -k "{{name}}"

# Cobertura real con subprocesos (refresh/verify corren en hijos): gate >=95 %.
coverage:
    cd {{flow_dir}} && uv run python -m coverage erase
    cd {{flow_dir}} && \
        PYTHONPATH=../../tests/support/covhook \
        COVERAGE_PROCESS_START=pyproject.toml \
        uv run python -m pytest -m "not slow" -q
    cd {{flow_dir}} && uv run python -m coverage combine
    cd {{flow_dir}} && uv run python -m coverage report -m

# Benchmark Δ completo con p95: medición local, nunca en CI.
bench:
    cd {{flow_dir}} && uv run python ../../tests/benchmarks/bench_delta.py

# Smoke Δ de 1 corrida con umbral generoso: el mismo bench que corre CI.
bench-smoke:
    cd {{flow_dir}} && uv run python ../../tests/benchmarks/bench_delta.py --smoke

# Bench search p95 <500 ms (criterio 3) + presupuesto por etapa: medición LOCAL.
# `just bench-search --smoke` = variante CI con umbral generoso (sin percentil);
# el p95 real NUNCA corre en CI (misma disciplina que bench, ver bench_search.py).
bench-search *args:
    cd {{flow_dir}} && uv run python ../../tests/benchmarks/bench_search.py {{args}}

# Markdown lint de docs/specs/AGENTS.md/SPEC.md (markdownlint-cli2 vía npx).
md-lint:
    npx --yes markdownlint-cli2 docs specs AGENTS.md SPEC.md

# Gate local: lint → fmt-check → typecheck → test (corta en el primer fallo).
quality: lint fmt-check typecheck test

# Espejo local del gate de CI: sync → lint → fmt-check → typecheck → test → smoke.
ci: sync lint fmt-check typecheck test bench-smoke

# DESTRUCTIVO: borra caches locales y cualquier `.venv` accidental (creado por un
# `uv` invocado a mano sin UV_PROJECT_ENVIRONMENT); no toca fuentes ni `venv/`.
clean:
    rm -r -f .pytest_cache .ruff_cache .mypy_cache {{flow_dir}}/.venv
    find . -name .git -prune -o -type d -name __pycache__ -prune -exec rm -r -f {} +
