#!/usr/bin/env bash
# Point d'entrée racine : installe AELYN sans jamais avoir à naviguer dans
# src/backend. Redirige simplement vers le vrai script (voir ce fichier pour
# le détail de ce que l'installation fait), en transmettant tous les
# arguments (ex. --reconfigure, --no-voice).
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/src/backend/scripts/install.sh" "$@"
