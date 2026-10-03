#!/usr/bin/env bash
# Point d'entrée racine : lance AELYN (API + frontend) sans jamais avoir à
# naviguer dans src/backend. Redirige vers le vrai script.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/src/backend/scripts/start.sh" "$@"
