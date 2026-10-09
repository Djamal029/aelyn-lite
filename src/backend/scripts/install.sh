#!/usr/bin/env bash
# Installation/configuration d'AELYN en une commande : demande la langue
# d'affichage du script (pas celle d'AELYN lui-même, qui reste en français
# cf. SYSTEM_PERSONA/SYSTEM_INTENT), vérifie les prérequis, détecte le GPU,
# crée .env (prompts interactifs pour les champs qu'aucune route web ne peut
# configurer : secrets, identité), guide la création de profil.json à partir
# d'un assistant IA, installe les dépendances Python et frontend, et tire
# les modèles Ollama nécessaires. Idempotent : un re-run ne reprompte que
# les champs encore vides dans .env (sauf --reconfigure).
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
    *) echo "Option inconnue / unknown option: $arg" >&2; exit 1 ;;
  esac
done

# ---------------------------------------------------------- 0. langue du script
#
# Langue d'AFFICHAGE DE CE SCRIPT uniquement : AELYN lui-même (prompts LLM,
# routage de phrases, interface web) reste entièrement en français quel que
# soit ce choix - le traduire est un chantier séparé bien plus gros
# (SYSTEM_PERSONA/SYSTEM_INTENT, toutes les regex françaises du fast
# router, toute l'UI React), pas celui de cet installeur.
LANG_CHOICE="fr"
echo ""
echo "Langue du script d'installation / Installer script language :"
echo "  1) Français (par défaut)"
echo "  2) English"
read -r -p "> " lang_answer || true
case "${lang_answer:-}" in
  2|en|EN|English|english) LANG_CHOICE="en" ;;
  *) LANG_CHOICE="fr" ;;
esac

# Table de messages bilingue : une fonction plutôt qu'un tableau associatif
# (`declare -A` n'existe qu'en bash 4+, absent par défaut sur macOS qui
# ships bash 3.2) pour rester portable sur les trois plateformes visées.
t() {
  local key="$1"
  if [[ "$LANG_CHOICE" == "en" ]]; then
    case "$key" in
      step_prereq) echo "1/8 Checking prerequisites" ;;
      step_gpu) echo "2/8 GPU detection" ;;
      step_env) echo "3/8 Configuration (.env)" ;;
      step_profile) echo "4/8 Your profile (profil.json)" ;;
      step_sync) echo "5/8 Installing Python dependencies (can take several minutes)" ;;
      step_ollama) echo "6/8 Downloading Ollama models" ;;
      step_frontend) echo "7/8 Installing the frontend" ;;
      step_done) echo "8/8 Done" ;;
      err_uv) echo "uv not found. Install it: https://docs.astral.sh/uv/getting-started/installation/" ;;
      err_ollama_missing) echo "Ollama not found. Install it: https://ollama.com/download" ;;
      err_ollama_down) echo "Ollama is installed but not responding. Run 'ollama serve' in another terminal, then re-run this script." ;;
      err_npm) echo "npm not found. Install Node.js: https://nodejs.org" ;;
      warn_espeak) echo "espeak-ng not found (Kokoro voice unavailable without it)." ;;
      warn_espeak_win) echo "Windows: winget install eSpeak-NG.eSpeak-NG — or re-run with --no-voice." ;;
      warn_portaudio_linux) echo "PortAudio dev headers not found: PyAudio (voice) is likely to fail to compile. Install it first, e.g. 'sudo apt install portaudio19-dev python3-dev' on Debian/Ubuntu (or your distro's equivalent), then re-run. If you skip this, the install will still complete, just without voice (see step 5/8)." ;;
      warn_no_compiler_linux) echo "No C compiler found (gcc/cc): PyAudio (voice) cannot be built. Install one first, e.g. 'sudo apt install build-essential' on Debian/Ubuntu (or your distro's equivalent). If you skip this, the install will still complete, just without voice." ;;
      gpu_found) echo "NVIDIA GPU detected:" ;;
      gpu_none) echo "No NVIDIA GPU detected -> CPU torch (slower on embeddings/transcription, but works everywhere)" ;;
      gpu_other_vendor) echo "Note: a non-NVIDIA GPU (AMD/Intel) was detected, but there is no reliable Windows PyTorch build for it yet (ROCm is Linux-only, Intel XPU is experimental) -> falling back to CPU." ;;
      env_created) echo ".env created from .env.example" ;;
      profil_created) echo "profil.json created from profil.example.json (follow the next step to fill it with your real info)" ;;
      already_set) echo "Already configured, left as-is:" ;;
      prompted) echo "Configured just now:" ;;
      user_name) echo "Your first name (used to sign draft emails)" ;;
      user_full_name) echo "Your full name (CV / cover letter header)" ;;
      user_contact_email) echo "Contact email for the CV / cover letter" ;;
      user_phone) echo "Phone (optional)" ;;
      user_linkedin) echo "LinkedIn (optional)" ;;
      user_city) echo "City (optional)" ;;
      email_user) echo "Gmail address (email agent)" ;;
      email_pass_deferred) echo "Gmail app password: left EMPTY on purpose (see the reminder at the end of this install)." ;;
      passkey_prompt) echo "Passkey to change settings from the web frontend [Enter to accept GENERATED, or type your own]: " ;;
      ft_intro) echo "France Travail (job search, optional - Enter to skip): https://francetravail.io" ;;
      ft_client_id) echo "  France Travail Client ID" ;;
      ft_client_secret) echo "  France Travail Client Secret" ;;
      keywords) echo "Job search keywords, comma-separated" ;;
      department) echo "Department codes (INSEE, 2 digits), comma-separated" ;;
      youtube_intro) echo "YouTube (video search, optional - Enter to skip): https://console.cloud.google.com/apis/credentials" ;;
      youtube_key) echo "  YouTube Data v3 API key" ;;
      public_apis_intro) echo "Extra job sources (optional, complement France Travail - Enter to skip each one)." ;;
      public_apis_enable) echo "Enable extra job sources now? [y/N]: " ;;
      adzuna_intro) echo "  Adzuna (international): https://developer.adzuna.com" ;;
      adzuna_app_id) echo "  Adzuna app_id" ;;
      adzuna_app_key) echo "  Adzuna app_key" ;;
      reed_intro) echo "  Reed (UK): https://www.reed.co.uk/developers" ;;
      reed_key) echo "  Reed API key" ;;
      careerjet_intro) echo "  Careerjet (publisher program): https://careerjet.com/partners/register/as-publisher" ;;
      careerjet_key) echo "  Careerjet API key" ;;
      jooble_intro) echo "  Jooble: https://fr.jooble.org/api/about" ;;
      jooble_key) echo "  Jooble API key" ;;
      public_apis_free_note) echo "  RemoteOK, Remotive and Arbeitnow need no API key and are used automatically once extra sources are enabled." ;;
      profil_intro) echo "Let's fill in your real profile (used word-for-word for your CV/cover letters, nothing is ever invented beyond it)." ;;
      profil_howto_1) echo "  1. Open the example file below, and your own CV/LinkedIn export/notes." ;;
      profil_howto_2) echo "  2. Paste BOTH into an AI assistant (ChatGPT, Claude...) and ask it to rewrite YOUR information into EXACTLY this JSON structure." ;;
      profil_howto_3) echo "  3. Paste the JSON result below, then type a line with only: EOF" ;;
      profil_howto_skip) echo "  (Or just type: skip  — to keep the example for now and edit profil.json by hand later.)" ;;
      profil_example_path) echo "  Example file:" ;;
      profil_paste_prompt) echo "Paste your JSON now:" ;;
      profil_ok) echo "  profil.json updated with your information." ;;
      profil_skip) echo "  Skipped - profil.json keeps the example content. Edit it by hand later, or re-run with --reconfigure." ;;
      profil_invalid) echo "  Not valid, profil.json left unchanged (example kept):" ;;
      profil_already_customized) echo "  profil.json already looks customized (different from the example) - left as-is. Re-run with --reconfigure to redo this step." ;;
      sync_voice) echo "  With voice (speech recognition + synthesis) — re-run with --no-voice to skip this." ;;
      warn_voice_sync_failed) echo "Installing voice dependencies failed (PyAudio often needs PortAudio headers + a C compiler). Continuing WITHOUT voice: the rest of AELYN works fine without it. Fix PortAudio/build tools and re-run with --reconfigure to add voice back later." ;;
      ollama_heavy_note) echo "  Optional: 'ollama pull mistral:7b' improves intent routing on a PC (not on Raspberry Pi), skipped by default." ;;
      frontend_env_created) echo "created from .env.example" ;;
      done_launch) echo "To launch AELYN:" ;;
      done_frontend) echo "  Frontend:" ;;
      done_api) echo "  API:" ;;
      warn_ft_missing) echo "France Travail not configured: job search will not work until FRANCE_TRAVAIL_CLIENT_ID/_SECRET are set in" ;;
      reminder_title) echo "IMPORTANT - one manual step left:" ;;
      reminder_email_pass_1) echo "  Open the .env file above and set EMAIL_PASS by hand (a Gmail APP password, not your normal password):" ;;
      reminder_email_pass_2) echo "  1. Turn on 2-Step Verification on your Google account if not already on: https://myaccount.google.com/security" ;;
      reminder_email_pass_3) echo "  2. Generate an app password here: https://myaccount.google.com/apppasswords" ;;
      reminder_email_pass_4) echo "  3. Paste it as EMAIL_PASS=... in" ;;
      reminder_email_pass_done) echo "  (Already set — nothing to do here.)" ;;
      *) echo "$key" ;;
    esac
  else
    case "$key" in
      step_prereq) echo "1/8 Vérification des prérequis" ;;
      step_gpu) echo "2/8 Détection GPU" ;;
      step_env) echo "3/8 Configuration (.env)" ;;
      step_profile) echo "4/8 Ton profil (profil.json)" ;;
      step_sync) echo "5/8 Installation des dépendances Python (peut prendre plusieurs minutes)" ;;
      step_ollama) echo "6/8 Téléchargement des modèles Ollama" ;;
      step_frontend) echo "7/8 Installation du frontend" ;;
      step_done) echo "8/8 Terminé" ;;
      err_uv) echo "uv est introuvable. Installe-le : https://docs.astral.sh/uv/getting-started/installation/" ;;
      err_ollama_missing) echo "Ollama est introuvable. Installe-le : https://ollama.com/download" ;;
      err_ollama_down) echo "Ollama est installé mais ne répond pas. Lance 'ollama serve' dans un autre terminal puis relance ce script." ;;
      err_npm) echo "npm est introuvable. Installe Node.js : https://nodejs.org" ;;
      warn_espeak) echo "espeak-ng introuvable (voix Kokoro indisponible sans lui)." ;;
      warn_espeak_win) echo "Windows : winget install eSpeak-NG.eSpeak-NG — sinon relance avec --no-voice." ;;
      warn_portaudio_linux) echo "En-têtes de dev PortAudio introuvables : PyAudio (voix) risque d'échouer à compiler. Installe-les d'abord, ex. 'sudo apt install portaudio19-dev python3-dev' sur Debian/Ubuntu (ou l'équivalent de ta distribution), puis relance. Si tu ignores ce message, l'installation ira quand même au bout, juste sans la voix (voir étape 5/8)." ;;
      warn_no_compiler_linux) echo "Aucun compilateur C trouvé (gcc/cc) : PyAudio (voix) ne pourra pas compiler. Installe-en un d'abord, ex. 'sudo apt install build-essential' sur Debian/Ubuntu (ou l'équivalent de ta distribution). Si tu ignores ce message, l'installation ira quand même au bout, juste sans la voix." ;;
      gpu_found) echo "GPU NVIDIA détecté :" ;;
      gpu_none) echo "Aucun GPU NVIDIA détecté -> torch CPU (plus lent sur les embeddings/la transcription, mais fonctionne partout)" ;;
      gpu_other_vendor) echo "Remarque : une carte graphique non-NVIDIA (AMD/Intel) a été détectée, mais il n'existe pas de build PyTorch Windows fiable pour elle (ROCm Linux uniquement, Intel XPU expérimental) -> repli sur CPU." ;;
      env_created) echo ".env créé depuis .env.example" ;;
      profil_created) echo "profil.json créé depuis profil.example.json (suis l'étape suivante pour le remplir avec tes vraies infos)" ;;
      already_set) echo "Déjà configuré, laissé tel quel :" ;;
      prompted) echo "Configuré à l'instant :" ;;
      user_name) echo "Ton prénom (utilisé pour signer les brouillons de mail)" ;;
      user_full_name) echo "Ton nom complet (en-tête CV/lettre de motivation)" ;;
      user_contact_email) echo "Email de contact pour le CV/la lettre de motivation" ;;
      user_phone) echo "Téléphone (optionnel)" ;;
      user_linkedin) echo "LinkedIn (optionnel)" ;;
      user_city) echo "Ville (optionnel)" ;;
      email_user) echo "Adresse Gmail (agent mail)" ;;
      email_pass_deferred) echo "Mot de passe d'application Gmail : laissé VIDE volontairement (voir le rappel à la fin de l'installation)." ;;
      passkey_prompt) echo "Passkey pour modifier les réglages depuis le frontend [Entrée pour accepter GENERATED, ou tape la tienne] : " ;;
      ft_intro) echo "France Travail (recherche d'offres, optionnel — Entrée pour passer) : https://francetravail.io" ;;
      ft_client_id) echo "  Client ID France Travail" ;;
      ft_client_secret) echo "  Client Secret France Travail" ;;
      keywords) echo "Mots-clés de recherche d'offres, séparés par des virgules" ;;
      department) echo "Codes département (INSEE, 2 chiffres), séparés par des virgules" ;;
      youtube_intro) echo "YouTube (recherche vidéo, optionnel — Entrée pour passer) : https://console.cloud.google.com/apis/credentials" ;;
      youtube_key) echo "  Clé API YouTube Data v3" ;;
      public_apis_intro) echo "Sources d'offres complémentaires (optionnel, en plus de France Travail — Entrée pour passer chacune)." ;;
      public_apis_enable) echo "Activer les sources complémentaires maintenant ? [o/N] : " ;;
      adzuna_intro) echo "  Adzuna (international) : https://developer.adzuna.com" ;;
      adzuna_app_id) echo "  Adzuna app_id" ;;
      adzuna_app_key) echo "  Adzuna app_key" ;;
      reed_intro) echo "  Reed (Royaume-Uni) : https://www.reed.co.uk/developers" ;;
      reed_key) echo "  Clé API Reed" ;;
      careerjet_intro) echo "  Careerjet (programme Publisher) : https://careerjet.com/partners/register/as-publisher" ;;
      careerjet_key) echo "  Clé API Careerjet" ;;
      jooble_intro) echo "  Jooble : https://fr.jooble.org/api/about" ;;
      jooble_key) echo "  Clé API Jooble" ;;
      public_apis_free_note) echo "  RemoteOK, Remotive et Arbeitnow ne demandent aucune clé et sont utilisées automatiquement dès que les sources complémentaires sont activées." ;;
      profil_intro) echo "Remplissons ton vrai profil (repris mot pour mot pour ton CV/tes lettres de motivation, rien n'est jamais inventé au-delà)." ;;
      profil_howto_1) echo "  1. Ouvre le fichier exemple ci-dessous, et ton propre CV/export LinkedIn/tes notes." ;;
      profil_howto_2) echo "  2. Colle LES DEUX dans un assistant IA (ChatGPT, Claude...) et demande-lui de réécrire TES informations dans EXACTEMENT cette structure JSON." ;;
      profil_howto_3) echo "  3. Colle le résultat JSON ci-dessous, puis tape une ligne contenant juste : EOF" ;;
      profil_howto_skip) echo "  (Ou tape simplement : skip  — pour garder l'exemple pour l'instant et éditer profil.json à la main plus tard.)" ;;
      profil_example_path) echo "  Fichier exemple :" ;;
      profil_paste_prompt) echo "Colle ton JSON maintenant :" ;;
      profil_ok) echo "  profil.json mis à jour avec tes informations." ;;
      profil_skip) echo "  Étape ignorée - profil.json garde le contenu de l'exemple. Édite-le à la main plus tard, ou relance avec --reconfigure." ;;
      profil_invalid) echo "  Non valide, profil.json laissé tel quel (exemple gardé) :" ;;
      profil_already_customized) echo "  profil.json a déjà l'air personnalisé (différent de l'exemple) - laissé tel quel. Relance avec --reconfigure pour refaire cette étape." ;;
      sync_voice) echo "  Avec la voix (reconnaissance + synthèse) — relance avec --no-voice pour sauter cette étape." ;;
      warn_voice_sync_failed) echo "L'installation des dépendances vocales a échoué (PyAudio a souvent besoin des en-têtes PortAudio + d'un compilateur C). On continue SANS la voix : le reste d'AELYN fonctionne très bien sans elle. Corrige PortAudio/les outils de build et relance avec --reconfigure pour rajouter la voix plus tard." ;;
      ollama_heavy_note) echo "  Optionnel : 'ollama pull mistral:7b' améliore le routage d'intention sur PC (pas sur Raspberry Pi), ignoré par défaut." ;;
      frontend_env_created) echo "créé depuis .env.example" ;;
      done_launch) echo "Pour lancer AELYN :" ;;
      done_frontend) echo "  Frontend :" ;;
      done_api) echo "  API :" ;;
      warn_ft_missing) echo "France Travail non configuré : la recherche d'offres ne fonctionnera pas tant que FRANCE_TRAVAIL_CLIENT_ID/_SECRET ne sont pas renseignés dans" ;;
      reminder_title) echo "IMPORTANT - il te reste une étape manuelle :" ;;
      reminder_email_pass_1) echo "  Ouvre le fichier .env ci-dessus et renseigne EMAIL_PASS à la main (un mot de passe d'APPLICATION Gmail, pas ton mot de passe normal) :" ;;
      reminder_email_pass_2) echo "  1. Active la validation en deux étapes sur ton compte Google si ce n'est pas déjà fait : https://myaccount.google.com/security" ;;
      reminder_email_pass_3) echo "  2. Génère un mot de passe d'application ici : https://myaccount.google.com/apppasswords" ;;
      reminder_email_pass_4) echo "  3. Colle-le comme EMAIL_PASS=... dans" ;;
      reminder_email_pass_done) echo "  (Déjà renseigné — rien à faire ici.)" ;;
      *) echo "$key" ;;
    esac
  fi
}

say()  { printf '\n\033[1;36m%s\033[0m\n' "$1"; }
warn() { printf '\033[1;33m! %s\033[0m\n' "$1"; }
err()  { printf '\033[1;31mx %s\033[0m\n' "$1" >&2; }

# ---------------------------------------------------------------- 1. prérequis

say "$(t step_prereq)"

if ! command -v uv >/dev/null 2>&1; then
  err "$(t err_uv)"
  exit 1
fi
echo "  uv : $(uv --version)"

if ! command -v ollama >/dev/null 2>&1; then
  err "$(t err_ollama_missing)"
  exit 1
fi
if ! ollama list >/dev/null 2>&1; then
  err "$(t err_ollama_down)"
  exit 1
fi
echo "  ollama : $(ollama --version 2>&1 | head -n1)"

if ! command -v npm >/dev/null 2>&1; then
  err "$(t err_npm)"
  exit 1
fi
echo "  npm : $(npm --version)"

if $WITH_VOICE && ! command -v espeak-ng >/dev/null 2>&1; then
  warn "$(t warn_espeak)"
  warn "$(t warn_espeak_win)"
fi

# PyAudio (extra voice) a besoin des en-têtes PortAudio ET d'un
# compilateur C pour compiler depuis les sources sur Linux (pas de wheel
# prébuilt officiel) : vérifié AVANT `uv sync --extra voice` (pas
# seulement après coup via le repli de l'étape 5) pour que l'échec, s'il
# a lieu, soit déjà expliqué clairement plutôt qu'une sortie uv brute et
# cryptique. N'empêche jamais l'installation de continuer : seulement un
# avertissement, le repli sans voix (étape 5) reste le filet de sécurité
# réel si l'utilisateur ignore ce message.
if $WITH_VOICE && [ "$(uname -s 2>/dev/null)" = "Linux" ]; then
  PORTAUDIO_OK=false
  if command -v pkg-config >/dev/null 2>&1 && pkg-config --exists portaudio-2.0 2>/dev/null; then
    PORTAUDIO_OK=true
  elif [ -f /usr/include/portaudio.h ] || [ -f /usr/local/include/portaudio.h ]; then
    PORTAUDIO_OK=true
  fi
  if ! $PORTAUDIO_OK; then
    warn "$(t warn_portaudio_linux)"
  fi
  if ! command -v cc >/dev/null 2>&1 && ! command -v gcc >/dev/null 2>&1; then
    warn "$(t warn_no_compiler_linux)"
  fi
fi

# ---------------------------------------------------------------- 2. GPU

say "$(t step_gpu)"

GPU_INDEX="pytorch-cpu"
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi --query-gpu=name --format=csv,noheader >/dev/null 2>&1; then
  GPU_NAME="$(nvidia-smi --query-gpu=name --format=csv,noheader | head -n1)"
  echo "  $(t gpu_found) $GPU_NAME -> torch CUDA (pytorch-cu130)"
  GPU_INDEX="pytorch-cu130"
else
  echo "  $(t gpu_none)"
  # Repli informatif seulement : AMD/Intel détecté ou non, le résultat est
  # le même (CPU) tant qu'aucun wheel PyTorch fiable n'existe pour eux sous
  # Windows (cf. commentaire du message gpu_other_vendor) - inutile de
  # risquer une install cassée avec un chemin DirectML non testé.
  if command -v wmic >/dev/null 2>&1; then
    GPU_LIST="$(wmic path win32_VideoController get name 2>/dev/null | grep -iE 'amd|radeon|intel' || true)"
    [[ -n "$GPU_LIST" ]] && echo "  $(t gpu_other_vendor)"
  fi
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

say "$(t step_env)"

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  echo "  $(t env_created)"
fi

# `profil.json` est volontairement non versionné (données perso) : sans ce
# copier, aelyn-api plante au tout premier démarrage (profil_manager le
# charge à l'import du module, donc avant même qu'une route réponde),
# observé en direct sur un clone neuf de la version lite.
PROFIL_FILE="$BACKEND_DIR/career-agent/src/aelyn_career/profil.json"
PROFIL_EXAMPLE="$BACKEND_DIR/career-agent/src/aelyn_career/profil.example.json"
PROFIL_JUST_CREATED=false
if [[ ! -f "$PROFIL_FILE" ]] && [[ -f "$PROFIL_EXAMPLE" ]]; then
  cp "$PROFIL_EXAMPLE" "$PROFIL_FILE"
  echo "  $(t profil_created)"
  PROFIL_JUST_CREATED=true
fi

env_get() {
  # `</dev/null` : ce sous-processus ne doit JAMAIS hériter du stdin du
  # script (en cours de consommation par les `read` interactifs
  # ci-dessous) - sans ça, une lecture accidentelle côté `uv`/Python peut
  # voler une ligne destinée à un `read` plus loin, ou bloquer en
  # attendant une entrée qui ne viendra jamais.
  uv run --project "$BACKEND_DIR" python -c "
import dotenv, sys
v = dotenv.dotenv_values('$ENV_FILE').get('$1')
sys.stdout.write(v or '')
" 2>/dev/null </dev/null
}

env_set() {
  # `cd "$BACKEND_DIR" &&` est nécessaire ICI (pas juste `--project`) :
  # `set_env_value` (aelyn_api/env_file.py) résout le `.env` via
  # `dotenv.find_dotenv(usecwd=True)`, qui remonte depuis le RÉPERTOIRE DE
  # TRAVAIL du process Python, jamais depuis `--project`. Bug réel
  # constaté en testant ce script : invoqué depuis la racine du dépôt
  # (le point d'entrée documenté, `./install.sh`), aucun `.env` n'était
  # trouvé en remontant depuis la racine (il est dans `src/backend/`, pas
  # un ancêtre) - `FileNotFoundError` silencieuse puisque la sortie est
  # redirigée vers /dev/null, chaque champ repartait donc vide à chaque
  # relance sans jamais le signaler.
  (cd "$BACKEND_DIR" && uv run --project "$BACKEND_DIR" python -c "
from aelyn_api.env_file import set_env_value
set_env_value('$1', '''$2''')
") >/dev/null 2>&1 </dev/null
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

ALREADY_SET=()
PROMPTED=()

prompt_field USER_NAME "$(t user_name)"
prompt_field USER_FULL_NAME "$(t user_full_name)"
EMAIL_USER_CURRENT="$(env_get EMAIL_USER)"
prompt_field USER_CONTACT_EMAIL "$(t user_contact_email)" "$EMAIL_USER_CURRENT"
prompt_field USER_PHONE "$(t user_phone)"
prompt_field USER_LINKEDIN "$(t user_linkedin)"
prompt_field USER_CITY "$(t user_city)"

prompt_field EMAIL_USER "$(t email_user)"
# EMAIL_PASS n'est PLUS demandé ici : obtenir un mot de passe d'application
# Gmail implique de quitter le terminal (activer la validation en deux
# étapes si besoin, puis générer le mot de passe sur un site Google), ce
# qui coupe le flux d'install en plein milieu pour rien - un rappel clair
# en fin de script (étape 8/8) suffit et n'interrompt plus rien ici.
echo "  $(t email_pass_deferred)"

if [[ -z "$(env_get SETTINGS_PASSKEY)" || "$RECONFIGURE" == true ]]; then
  GENERATED_PASSKEY="$(openssl rand -hex 24 2>/dev/null || head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  PASSKEY_LABEL="$(t passkey_prompt)"
  read -r -p "${PASSKEY_LABEL/GENERATED/$GENERATED_PASSKEY}" value
  env_set SETTINGS_PASSKEY "${value:-$GENERATED_PASSKEY}"
  PROMPTED+=(SETTINGS_PASSKEY)
else
  ALREADY_SET+=(SETTINGS_PASSKEY)
fi

echo "$(t ft_intro)"
prompt_field FRANCE_TRAVAIL_CLIENT_ID "$(t ft_client_id)"
prompt_field FRANCE_TRAVAIL_CLIENT_SECRET "$(t ft_client_secret)"

prompt_field KEYWORDS "$(t keywords)" "Data Scientist,Machine Learning,Intelligence artificielle"
prompt_field DEPARTMENT "$(t department)" "35,75"

echo "$(t youtube_intro)"
prompt_field YOUTUBE_API_KEY "$(t youtube_key)"

# Sources d'offres complémentaires (Adzuna/Reed/Careerjet/Jooble, + RemoteOK/
# Remotive/Arbeitnow qui ne demandent aucune clé) : désactivées par défaut
# (AELYN_ENABLE_PUBLIC_JOB_APIS=false dans .env.example), on ne les propose
# que si l'utilisateur dit explicitement oui, pour éviter des appels réseau
# et des quotas inattendus à qui ne les veut pas.
echo ""
echo "$(t public_apis_intro)"
ENABLE_PUBLIC_APIS_CURRENT="$(env_get AELYN_ENABLE_PUBLIC_JOB_APIS)"
if [[ "$ENABLE_PUBLIC_APIS_CURRENT" != "true" || "$RECONFIGURE" == true ]]; then
  read -r -p "$(t public_apis_enable)" enable_answer
  case "${enable_answer:-}" in
    y|Y|yes|YES|o|O|oui|OUI)
      env_set AELYN_ENABLE_PUBLIC_JOB_APIS "true"
      echo "$(t adzuna_intro)"
      prompt_field ADZUNA_APP_ID "$(t adzuna_app_id)"
      prompt_field ADZUNA_APP_KEY "$(t adzuna_app_key)"
      echo "$(t reed_intro)"
      prompt_field REED_API_KEY "$(t reed_key)"
      echo "$(t careerjet_intro)"
      prompt_field CAREERJET_API_KEY "$(t careerjet_key)"
      echo "$(t jooble_intro)"
      prompt_field JOOBLE_API_KEY "$(t jooble_key)"
      echo "$(t public_apis_free_note)"
      ;;
    *)
      env_set AELYN_ENABLE_PUBLIC_JOB_APIS "false"
      ;;
  esac
else
  ALREADY_SET+=(AELYN_ENABLE_PUBLIC_JOB_APIS)
fi

if [[ "$GPU_INDEX" == "pytorch-cu130" ]]; then
  env_set EMBEDDING_DEVICE cuda
  env_set WHISPER_DEVICE cuda
else
  env_set EMBEDDING_DEVICE cpu
  env_set WHISPER_DEVICE cpu
fi

if [[ ${#ALREADY_SET[@]} -gt 0 ]]; then
  echo "  $(t already_set) ${ALREADY_SET[*]}"
fi
if [[ ${#PROMPTED[@]} -gt 0 ]]; then
  echo "  $(t prompted) ${PROMPTED[*]}"
fi

# ------------------------------------------------------------- 4. profil.json

say "$(t step_profile)"

PROFIL_IS_DEFAULT=false
if [[ -f "$PROFIL_FILE" ]] && [[ -f "$PROFIL_EXAMPLE" ]] && diff -q "$PROFIL_FILE" "$PROFIL_EXAMPLE" >/dev/null 2>&1; then
  PROFIL_IS_DEFAULT=true
fi

if $PROFIL_IS_DEFAULT || $RECONFIGURE; then
  echo "$(t profil_intro)"
  echo "$(t profil_howto_1)"
  echo "$(t profil_example_path) $PROFIL_EXAMPLE"
  echo "$(t profil_howto_2)"
  echo "$(t profil_howto_3)"
  echo "$(t profil_howto_skip)"
  echo "$(t profil_paste_prompt)"

  PASTE_FILE="$(mktemp)"
  trap 'rm -f "$PASTE_FILE"' EXIT
  SKIP_PROFIL=false
  FIRST_LINE=true
  while IFS= read -r line; do
    if $FIRST_LINE && [[ "$line" == "skip" ]]; then
      SKIP_PROFIL=true
      break
    fi
    FIRST_LINE=false
    [[ "$line" == "EOF" ]] && break
    printf '%s\n' "$line" >> "$PASTE_FILE"
  done

  if $SKIP_PROFIL || [[ ! -s "$PASTE_FILE" ]]; then
    echo "$(t profil_skip)"
  else
    VALIDATION="$(uv run --project "$BACKEND_DIR" python -c "
import json
from aelyn_career.profil_manager import validate_profil_structure

with open('$PASTE_FILE', encoding='utf-8') as f:
    text = f.read()
try:
    data = json.loads(text)
except json.JSONDecodeError as exc:
    print(f'JSON invalide/invalid JSON: {exc}')
    raise SystemExit(1)
problems = validate_profil_structure(data)
if problems:
    print(chr(10).join(problems))
    raise SystemExit(1)
with open('$PROFIL_FILE', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print('OK')
" 2>&1 </dev/null)" || true
    if [[ "$VALIDATION" == "OK" ]]; then
      echo "$(t profil_ok)"
    else
      warn "$(t profil_invalid)"
      echo "$VALIDATION"
    fi
  fi
  rm -f "$PASTE_FILE"
  trap - EXIT
else
  echo "$(t profil_already_customized)"
fi

# ---------------------------------------------------------------- 5. uv sync

say "$(t step_sync)"

SYNC_ARGS=(--project "$BACKEND_DIR")
if $WITH_VOICE; then
  SYNC_ARGS+=(--extra voice)
  echo "$(t sync_voice)"
fi
# `PyAudio` (extra `voice`) compile depuis les sources sur beaucoup de
# machines (pas de wheel prébuilt pour toutes les combinaisons
# OS/Python) et a besoin des en-têtes PortAudio + d'un compilateur C :
# un échec de build ici ne doit PAS faire échouer `set -e` et tuer le
# reste de l'installation (Ollama, frontend) - bug réel rencontré par un
# utilisateur. En cas d'échec AVEC --extra voice, on retente SANS (le
# reste d'AELYN fonctionne très bien sans la voix, cf. `aelyn.core.voice`,
# dont les imports lourds sont tous paresseux) plutôt que d'abandonner.
if ! (cd "$BACKEND_DIR" && uv sync "${SYNC_ARGS[@]}"); then
  if $WITH_VOICE; then
    warn "$(t warn_voice_sync_failed)"
    (cd "$BACKEND_DIR" && uv sync --project "$BACKEND_DIR")
    WITH_VOICE=false
  else
    exit 1
  fi
fi

# ---------------------------------------------------------------- 6. ollama

say "$(t step_ollama)"

ollama pull qwen3:4b
ollama pull gemma3:4b
if $WITH_HEAVY_MODEL; then
  ollama pull mistral:7b
else
  echo "$(t ollama_heavy_note)"
fi

# ---------------------------------------------------------------- 7. frontend

say "$(t step_frontend)"

(cd "$FRONTEND_DIR" && npm install)
if [[ ! -f "$FRONTEND_DIR/.env.local" ]]; then
  cp "$FRONTEND_DIR/.env.example" "$FRONTEND_DIR/.env.local"
  echo "  $FRONTEND_DIR/.env.local $(t frontend_env_created)"
fi

# ---------------------------------------------------------------- 8. résumé

say "$(t step_done)"

echo "$(t done_launch) $SCRIPT_DIR/start.sh"
echo "$(t done_frontend) http://localhost:5173"
echo "$(t done_api) http://localhost:8001/docs"
if [[ -z "$(env_get FRANCE_TRAVAIL_CLIENT_ID)" ]]; then
  warn "$(t warn_ft_missing) $ENV_FILE."
fi

say "$(t reminder_title)"
if [[ -z "$(env_get EMAIL_PASS)" ]]; then
  echo "$(t reminder_email_pass_1) $ENV_FILE"
  echo "$(t reminder_email_pass_2)"
  echo "$(t reminder_email_pass_3)"
  echo "$(t reminder_email_pass_4) $ENV_FILE"
else
  echo "$(t reminder_email_pass_done)"
fi
