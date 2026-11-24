#!/usr/bin/env bash
# Sincroniza las etiquetas que necesita el flujo de CI en el repo.
# Uso: `just labels-sync`. Idempotente (`gh label create --force`): re-correr
# es seguro. Muta el REMOTO, así que nunca corre en un gate — solo bajo demanda.
set -euo pipefail

readonly REPO="Fisherk2/tepochcalli-opencode"

log() { printf '[labels] %s\n' "$*"; }
die() { printf '[labels] ERROR: %s\n' "$*" >&2; exit 1; }

command -v gh >/dev/null 2>&1 || die "gh (GitHub CLI) no está instalado"
gh auth status >/dev/null 2>&1 || die "gh no está autenticado (ejecuta: gh auth login)"

# nombre|color|descripcion (descripciones en español; color sin '#').
readonly LABELS=(
  "hotfix|d73a4a|Corrección urgente para producción"
  "release|0e8a16|Preparación y publicación de una release"
  "ci|c2e0c6|Integración continua y workflows"
  "dependencies|0366d6|Actualización de dependencias"
)

for entry in "${LABELS[@]}"; do
  IFS='|' read -r name color description <<< "${entry}"
  gh label create "${name}" \
    --repo "${REPO}" \
    --color "${color}" \
    --description "${description}" \
    --force
  log "etiqueta '${name}' sincronizada"
done

log "listo: ${#LABELS[@]} etiquetas en ${REPO}"
