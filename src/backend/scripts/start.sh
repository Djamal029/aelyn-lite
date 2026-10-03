#!/usr/bin/env bash
# Lance l'API (aelyn-api) et le frontend web ensemble, affiche les deux
# URLs, et arrête les deux proprement sur Ctrl+C.
set -uo pipefail

abspath() { (cd "$1" && { pwd -W 2>/dev/null || pwd; }); }

SCRIPT_DIR="$(abspath "$(dirname "${BASH_SOURCE[0]}")")"
BACKEND_DIR="$(abspath "$SCRIPT_DIR/..")"
FRONTEND_DIR="$(abspath "$BACKEND_DIR/../frontend/web")"
BACKEND_PORT=8001
FRONTEND_PORT=5173

if [[ ! -f "$BACKEND_DIR/.env" ]]; then
  echo "Aucun .env trouvé. Lance d'abord $SCRIPT_DIR/install.sh" >&2
  exit 1
fi

(cd "$BACKEND_DIR" && exec uv run uvicorn aelyn_api.main:app --port "$BACKEND_PORT" --app-dir aelyn-api/src) &
BACKEND_PID=$!

(cd "$FRONTEND_DIR" && exec npm run dev) &
FRONTEND_PID=$!

# Tue par PORT, pas par PID capturé au lancement : sous Git Bash, `exec`
# sur une commande qui lance un .exe natif Windows (uv.exe, npm.cmd) ne
# préserve PAS le PID comme un vrai `execve()` POSIX le ferait (Windows n'a
# pas d'équivalent) — `$!` capturé après le `&` correspond à un process qui
# a déjà disparu au moment du nettoyage (confirmé en testant ce script :
# `taskkill` répondait "process not found" sur ce PID alors qu'un autre
# process tournait bel et bien sur le port visé). Chercher le VRAI PID qui
# écoute sur le port au moment de nettoyer est fiable quel que soit le
# nombre de processus intermédiaires (uv -> python, npm -> node).
pid_on_port() {
  local port="$1"
  if command -v taskkill >/dev/null 2>&1; then
    netstat -ano 2>/dev/null | grep "LISTENING" | grep ":$port " | awk '{print $NF}' | head -n1
  else
    lsof -ti ":$port" 2>/dev/null | head -n1
  fi
}

# Plusieurs passes avec une courte pause : sous Git Bash, un signal reçu
# pile pendant qu'une commande externe (netstat/taskkill) tourne peut
# retarder d'une itération la disparition réelle du process côté
# Windows — constaté en testant ce script (le port restait occupé après un
# premier essai de nettoyage, mais se libérait bien à la repasse
# suivante). Pas une solution parfaite, mais fiable en pratique.
kill_port() {
  local port="$1" pid attempt
  for attempt in 1 2 3; do
    pid="$(pid_on_port "$port")"
    [[ -z "$pid" ]] && return 0
    if command -v taskkill >/dev/null 2>&1; then
      taskkill //PID "$pid" //T //F >/dev/null 2>&1
    else
      kill "$pid" 2>/dev/null
    fi
    sleep 0.5
  done
}

cleanup() {
  kill_port "$BACKEND_PORT"
  kill_port "$FRONTEND_PORT"
  wait 2>/dev/null
}
trap cleanup INT TERM EXIT

echo
echo "AELYN démarre…"
echo "  API      : http://localhost:$BACKEND_PORT/docs"
echo "  Frontend : http://localhost:$FRONTEND_PORT"
echo "(Ctrl+C pour tout arrêter)"
echo

# Boucle courte (pas un `wait` bloquant unique) : un signal reçu pendant un
# `wait` bloqué sur un process Windows natif n'interrompait pas fiablement
# l'attente dans nos tests — un `sleep` court et répété laisse bash
# revérifier les signaux en attente entre chaque itération.
while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 1
done
