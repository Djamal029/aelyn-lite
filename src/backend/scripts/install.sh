#!/usr/bin/env bash
# Installation/configuration d'AELYN en une commande : vérifie les
# prérequis, détecte le GPU, crée .env (prompts interactifs pour les
# champs qu'aucune route web ne peut configurer : secrets, identité),
# installe les dépendances Python et frontend, et tire les modèles Ollama
# nécessaires. Idempotent : un re-run ne reprompte que les champs encore
# vides dans .env (sauf --reconfigure).
#
# Usage : ./install.sh [--reconfigure] [--no-voice] [--with-heavy-model]
set -euo pipefail

# `pwd -W` (extension MSYS/Git Bash) donne un chemin style Windows
# (E:/...) au lieu du style MSYS (/e/...) que `pwd` seul renvoie sous Git
# Bash : nécessaire pour que les chemins passés à `uv run python -c "..."`
# (Python natif Windows) résolvent correctement — `/e/...` ne veut rien
# dire pour un exécutable Windows, `os.path.exists()` renvoie silencieusement
# False dessus (bug réel rencontré en testant ce script). Sur un vrai
# Mac/Linux, `pwd -W` n'existe pas et échoue : on retombe alors sur `pwd`
# normal, déjà correct dans ce cas.
abspath() { (cd "$1" && { pwd -W 2>/dev/null || pwd; }); }

SCRIPT_DIR="$(abspath "$(dirname "${BASH_SOURCE[0]}")")"
BACKEND_DIR="$(abspath "$SCRIPT_DIR/..")"
FRONTEND_DIR="$(abspath "$BACKEND_DIR/../frontend/web")"
ENV_FILE="$BACKEND_DIR/.env"
ENV_EXAMPLE="$BACKEND_DIR/.env.example"

RECONFIGURE=false
WITH_VOICE=true
WITH_HEAVY_MODEL=false
for arg in "$@"; do
  case "$arg" in
    --reconfigure) RECONFIGURE=true ;;
    --no-voice) WITH_VOICE=false ;;
    --with-heavy-model) WITH_HEAVY_MODEL=true ;;
    *) echo "Option inconnue : $arg" >&2; exit 1 ;;
  esac
done

say()  { printf '\n\033[1;36m%s\033[0m\n' "$1"; }
warn() { printf '\033[1;33m! %s\033[0m\n' "$1"; }
err()  { printf '\033[1;31mx %s\033[0m\n' "$1" >&2; }

# ---------------------------------------------------------------- 1. prérequis

say "1/7 Vérification des prérequis"

if ! command -v uv >/dev/null 2>&1; then
  err "uv est introuvable. Installe-le : https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi
echo "  uv : $(uv --version)"

if ! command -v ollama >/dev/null 2>&1; then
  err "Ollama est introuvable. Installe-le : https://ollama.com/download"
  exit 1
fi
if ! ollama list >/dev/null 2>&1; then
  err "Ollama est installé mais ne répond pas. Lance 'ollama serve' dans un autre terminal puis relance ce script."
  exit 1
fi
echo "  ollama : $(ollama --version 2>&1 | head -n1)"

if ! command -v npm >/dev/null 2>&1; then
  err "npm est introuvable. Installe Node.js : https://nodejs.org"
  exit 1
fi
echo "  npm : $(npm --version)"

if $WITH_VOICE && ! command -v espeak-ng >/dev/null 2>&1; then
  warn "espeak-ng introuvable (voix Kokoro indisponible sans lui)."
  warn "Windows : winget install eSpeak-NG.eSpeak-NG — sinon relance avec --no-voice."
fi

# ---------------------------------------------------------------- 2. GPU

say "2/7 Détection GPU"

GPU_INDEX="pytorch-cpu"
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi --query-gpu=name --format=csv,noheader >/dev/null 2>&1; then
  GPU_NAME="$(nvidia-smi --query-gpu=name --format=csv,noheader | head -n1)"
  echo "  GPU NVIDIA détecté : $GPU_NAME -> torch CUDA (pytorch-cu130)"
  GPU_INDEX="pytorch-cu130"
else
  echo "  Aucun GPU NVIDIA détecté -> torch CPU (plus lent sur les embeddings/la transcription, mais fonctionne partout)"
fi

# Réécrit le placeholder AELYN_TORCH_INDEX dans les deux pyproject.toml qui
# en ont besoin (career-agent et security-agent, cf. leurs commentaires) :
# pas une fonctionnalité uv native (cf. ces mêmes commentaires), un simple
# remplacement de texte, robuste et sans dépendance supplémentaire.
for proj in "$BACKEND_DIR/career-agent/pyproject.toml" "$BACKEND_DIR/security-agent/pyproject.toml"; do
  if grep -q "AELYN_TORCH_INDEX" "$proj"; then
    sed -i.bak "s/{ index = \"AELYN_TORCH_INDEX\" }/{ index = \"$GPU_INDEX\" }/" "$proj"
    rm -f "$proj.bak"
  fi
done

# ---------------------------------------------------------------- 3. .env

say "3/7 Configuration (.env)"

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  echo "  .env créé depuis .env.example"
fi

# `profil.json` est volontairement non versionné (données perso) : sans ce
# copier, aelyn-api plante au tout premier démarrage (profil_manager le
# charge à l'import du module, donc avant même qu'une route réponde),
# observé en direct sur un clone neuf de la version lite.
PROFIL_FILE="$BACKEND_DIR/career-agent/src/aelyn_career/profil.json"
PROFIL_EXAMPLE="$BACKEND_DIR/career-agent/src/aelyn_career/profil.example.json"
if [[ ! -f "$PROFIL_FILE" ]] && [[ -f "$PROFIL_EXAMPLE" ]]; then
  cp "$PROFIL_EXAMPLE" "$PROFIL_FILE"
  echo "  profil.json créé depuis profil.example.json (édite-le avec tes vraies infos pour un CV/lettre pertinents)"
fi

env_get() {
  uv run --project "$BACKEND_DIR" python -c "
import dotenv, sys
v = dotenv.dotenv_values('$ENV_FILE').get('$1')
sys.stdout.write(v or '')
" 2>/dev/null
}

env_set() {
  uv run --project "$BACKEND_DIR" python -c "
from aelyn_api.env_file import set_env_value
set_env_value('$1', '''$2''')
" >/dev/null 2>&1
}

# Prompte uniquement si vide (ou --reconfigure), garde la valeur existante sinon.
prompt_field() {
  local key="$1" label="$2" default="${3:-}"
  local current
  current="$(env_get "$key")"
  if [[ -n "$current" && "$RECONFIGURE" != true ]]; then
    ALREADY_SET+=("$key")
    return
  fi
  local hint=""
  [[ -n "$default" ]] && hint=" [$default]"
  read -r -p "$label$hint : " value
  value="${value:-$default}"
  env_set "$key" "$value"
  PROMPTED+=("$key")
}

prompt_secret() {
  local key="$1" label="$2"
  local current
  current="$(env_get "$key")"
  if [[ -n "$current" && "$RECONFIGURE" != true ]]; then
    ALREADY_SET+=("$key")
    return
  fi
  read -r -s -p "$label : " value
  echo
  env_set "$key" "$value"
  PROMPTED+=("$key")
}

ALREADY_SET=()
PROMPTED=()

prompt_field USER_NAME "Ton prénom (utilisé pour signer les brouillons de mail)"
prompt_field USER_FULL_NAME "Ton nom complet (en-tête CV/lettre de motivation)"
EMAIL_USER_CURRENT="$(env_get EMAIL_USER)"
prompt_field USER_CONTACT_EMAIL "Email de contact pour le CV/la lettre de motivation" "$EMAIL_USER_CURRENT"
prompt_field USER_PHONE "Téléphone (optionnel)"
prompt_field USER_LINKEDIN "LinkedIn (optionnel)"
prompt_field USER_CITY "Ville (optionnel)"

prompt_field EMAIL_USER "Adresse Gmail (agent mail)"
if [[ -z "$(env_get EMAIL_PASS)" || "$RECONFIGURE" == true ]]; then
  echo "  Mot de passe d'application Gmail (PAS ton mot de passe normal) :"
  echo "  https://myaccount.google.com/apppasswords"
fi
prompt_secret EMAIL_PASS "Mot de passe d'application Gmail"

if [[ -z "$(env_get SETTINGS_PASSKEY)" || "$RECONFIGURE" == true ]]; then
  GENERATED_PASSKEY="$(openssl rand -hex 24 2>/dev/null || head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  read -r -p "Passkey pour modifier les réglages depuis le frontend [Entrée pour accepter $GENERATED_PASSKEY, ou tape la tienne] : " value
  env_set SETTINGS_PASSKEY "${value:-$GENERATED_PASSKEY}"
  PROMPTED+=(SETTINGS_PASSKEY)
else
  ALREADY_SET+=(SETTINGS_PASSKEY)
fi

echo "  France Travail (recherche d'offres, optionnel — Entrée pour passer) : https://francetravail.io"
prompt_field FRANCE_TRAVAIL_CLIENT_ID "  Client ID France Travail"
prompt_field FRANCE_TRAVAIL_CLIENT_SECRET "  Client Secret France Travail"

prompt_field KEYWORDS "Mots-clés de recherche d'offres, séparés par des virgules" "Data Scientist,Machine Learning,Intelligence artificielle"
prompt_field DEPARTMENT "Codes département (INSEE, 2 chiffres), séparés par des virgules" "35,75"

echo "  YouTube (recherche vidéo, optionnel — Entrée pour passer) : https://console.cloud.google.com/apis/credentials"
prompt_field YOUTUBE_API_KEY "  Clé API YouTube Data v3"

if [[ "$GPU_INDEX" == "pytorch-cu130" ]]; then
  env_set EMBEDDING_DEVICE cuda
  env_set WHISPER_DEVICE cuda
else
  env_set EMBEDDING_DEVICE cpu
  env_set WHISPER_DEVICE cpu
fi

if [[ ${#ALREADY_SET[@]} -gt 0 ]]; then
  echo "  Déjà configuré, laissé tel quel : ${ALREADY_SET[*]}"
fi
if [[ ${#PROMPTED[@]} -gt 0 ]]; then
  echo "  Configuré à l'instant : ${PROMPTED[*]}"
fi

# ---------------------------------------------------------------- 4. uv sync

say "4/7 Installation des dépendances Python (peut prendre plusieurs minutes)"

SYNC_ARGS=(--project "$BACKEND_DIR")
if $WITH_VOICE; then
  SYNC_ARGS+=(--extra voice)
  echo "  Avec la voix (reconnaissance + synthèse) — relance avec --no-voice pour sauter cette étape."
fi
(cd "$BACKEND_DIR" && uv sync "${SYNC_ARGS[@]}")

# ---------------------------------------------------------------- 5. ollama

say "5/7 Téléchargement des modèles Ollama"

ollama pull qwen3:4b
ollama pull gemma3:4b
if $WITH_HEAVY_MODEL; then
  ollama pull mistral:7b
else
  echo "  Optionnel : 'ollama pull mistral:7b' améliore le routage d'intention sur PC (pas sur Raspberry Pi), ignoré par défaut."
fi

# ---------------------------------------------------------------- 6. frontend

say "6/7 Installation du frontend"

(cd "$FRONTEND_DIR" && npm install)
if [[ ! -f "$FRONTEND_DIR/.env.local" ]]; then
  cp "$FRONTEND_DIR/.env.example" "$FRONTEND_DIR/.env.local"
  echo "  $FRONTEND_DIR/.env.local créé depuis .env.example"
fi

# ---------------------------------------------------------------- 7. résumé

say "7/7 Terminé"

echo "Pour lancer AELYN : $SCRIPT_DIR/start.sh"
echo "  Frontend : http://localhost:5173"
echo "  API      : http://localhost:8001/docs"
if [[ -z "$(env_get FRANCE_TRAVAIL_CLIENT_ID)" ]]; then
  warn "France Travail non configuré : la recherche d'offres ne fonctionnera pas tant que FRANCE_TRAVAIL_CLIENT_ID/_SECRET ne sont pas renseignés dans $ENV_FILE."
fi
