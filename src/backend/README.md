# AELYN

Assistant personnel local, privé par défaut : un LLM auto-hébergé (Ollama) orchestre une
famille d'agents spécialisés (mails, carrière, multimédia, sécurité, conversation) à
travers un monorepo Python (`uv` workspace). Rien ne part vers un cloud tiers pour le
raisonnement ou la synthèse vocale.

Cible finale : 2 Raspberry Pi (cœur + vision/sécurité) + un PC optionnel pour le calcul
lourd. Le dépôt actuel tourne aujourd'hui sur un PC unique (Windows, GPU NVIDIA) ; le
découpage en paquets `uv` séparés est justement pensé pour pouvoir répartir plus tard
sans réécrire.

## Sommaire

- [Quickstart](#quickstart)
- [Architecture](#architecture)
- [Arborescence du dépôt](#arborescence-du-dépôt)
- [Prérequis](#prérequis)
- [Installation](#installation)
- [Configuration (.env)](#configuration-env)
- [Frontend](#frontend)
- [Utilisation](#utilisation)
- [Où modifier quoi](#où-modifier-quoi)
- [État du projet / CR](#état-du-projet--cr)
- [Contribuer](#contribuer)

## Quickstart

Pour une installation guidée (vérifie les prérequis, détecte automatiquement si tu as un
GPU NVIDIA compatible — **sinon installe une version CPU, aucune action de ta part**,
tout fonctionne quand même, juste plus lentement sur les embeddings/la transcription —,
demande tes identifiants/secrets, installe tout, tire les modèles Ollama) :

```bash
# macOS / Linux / Git Bash (Windows), depuis la racine du dépôt
./install.sh
./start.sh
```

```powershell
# Windows (PowerShell natif), depuis la racine du dépôt
powershell -ExecutionPolicy Bypass -File install.ps1
powershell -ExecutionPolicy Bypass -File start.ps1
```

(`install.sh`/`start.sh`/`.ps1` à la racine ne sont que de fins redirecteurs vers
`src/backend/scripts/` — pratique pour ne jamais avoir à naviguer dans `src/backend`.)

Une fois lancé : `http://localhost:5173` (interface web) et
`http://localhost:8001/docs` (API). Les sections ci-dessous détaillent ce
que ces scripts automatisent, utile pour comprendre/personnaliser
l'installation ou si le script ne fonctionne pas sur ta plateforme — tout
reste faisable à la main en suivant les étapes manuelles qui suivent.

## Architecture

```
Toi (texte ou voix)
        │
        ▼
aelyn_conversation   <- comprend une phrase libre, route vers une commande
   │   │   │   │
   │   │   │   └── aelyn_media     (Freebox Pop / Android TV : Netflix, YouTube, volume…)
   │   │   └────── aelyn_career    (recherche d'offres France Travail, matching profil)
   │   └────────── aelyn_email     (tri IMAP, brouillons, envoi validé)
   └────────────── aelyn (core)    (config, accès LLM/Ollama, journal des actions, voix)

aelyn_security (autonome, pas encore branché sur la conversation : scripts anti-spoofing /
reconnaissance faciale directs)
```

Chaque agent est un paquet `uv` indépendant avec ses propres dépendances (`pyproject.toml`),
ce qui permet d'en ajouter un nouveau (domotique, santé…) sans toucher aux autres, et de ne
tirer que les dépendances réellement utilisées par la machine qui l'exécute.

Le routage d'une phrase libre passe d'abord par un **routeur rapide** à base de regex
(`fast_router.py`, quasi instantané) pour les phrases sans ambiguïté ; seules les phrases
plus complexes (recherche d'offres avec mots-clés, contrôle média avec titre à chercher…)
passent par le LLM (`mistral:7b` si présent localement, sinon repli automatique sur
`qwen3:4b`, jamais de téléchargement à la volée).

## Arborescence du dépôt

```
aelyn/
├── data/                      # données perso (profil, non versionné pour l'essentiel)
├── src/
│   ├── backend/                        # tout le code Python, ce dépôt uv workspace
│   │   ├── core/                       # aelyn : config, LLM, journal, voix, partagé par tous
│   │   ├── email-agent/                # aelyn_email : tri, brouillons, envoi
│   │   ├── career-agent/               # aelyn_career : offres France Travail, matching profil
│   │   ├── media-agent/                # aelyn_media : contrôle Freebox Pop / Android TV
│   │   ├── security-agent/             # aelyn_security : anti-spoofing, reconnaissance faciale
│   │   └── conversational-agent/       # aelyn_conversation : routage phrase libre -> commande
│   └── frontend/
│       ├── mobile/                     # (vide, pas encore commencé)
│       └── web/                        # interface web (React + Vite + TS), parle à aelyn-api
└── .env / .env.example
```

`computer-agent/` et `gateway/` existent aussi à la racine de `src/backend/` comme
emplacements réservés pour de futurs agents, mais sont vides pour l'instant.

## Prérequis

- **Python 3.11+** et [**uv**](https://docs.astral.sh/uv/) (gère l'environnement virtuel et
  le workspace).
- **[Ollama](https://ollama.com/)** installé et lancé (`ollama serve`, ou le service
  démarré automatiquement selon l'installeur).
- **Windows** : [espeak-ng](https://github.com/espeak-ng/espeak-ng) pour la voix française
  de Kokoro : `winget install eSpeak-NG.eSpeak-NG`.
- **GPU NVIDIA (optionnel mais recommandé)** : accélère les embeddings du career-agent et
  la transcription vocale (faster-whisper). Sans GPU, tout fonctionne quand même sur CPU
  (plus lent), voir la note CUDA plus bas.
- **Un compte Gmail** avec un [mot de passe d'application](https://myaccount.google.com/apppasswords)
  (PAS le mot de passe du compte) si tu veux utiliser l'agent mail.
- **Une Freebox Pop** (ou autre boîtier Android TV) sur le même réseau si tu veux utiliser
  l'agent média.
- **Des identifiants France Travail** (optionnel, nécessaire pour la recherche d'offres
  d'emploi) : France Travail (anciennement Pôle Emploi, l'opérateur public français de
  l'emploi) expose une API publique et gratuite avec les offres d'emploi de tout le pays.
  Pour l'utiliser :
  1. Crée un compte sur [francetravail.io](https://francetravail.io).
  2. Dans l'espace développeur, crée une "application" : ça te donne un `Client ID` et un
     `Client Secret` (protocole OAuth2, pas un simple mot de passe).
  3. Abonne cette application au produit **"Offres d'emploi v2"** (gratuit, quelques clics).
  4. Renseigne les deux valeurs dans `.env` (`FRANCE_TRAVAIL_CLIENT_ID`/`_SECRET`) — le
     script d'installation te les demande directement, ou édite `.env` à la main.

  Sans ces identifiants, tout le reste d'AELYN fonctionne normalement ; seule la recherche
  d'offres (`career-agent`) reste indisponible.

## Installation

Le script d'installation (voir [Quickstart](#quickstart)) fait tout ça pour toi, y
compris choisir CPU/CUDA selon ton matériel. À la main :

```bash
git clone <url-du-dépôt>
cd aelyn/src/backend

# `torch` (career-agent, security-agent) pointe par défaut vers l'index CUDA
# 13.0 du poste de développement d'origine (pyproject.toml, placeholder
# AELYN_TORCH_INDEX substitué par le script d'installation). Sans GPU NVIDIA
# compatible, remplace-le toi-même AVANT `uv sync` :
#   sed -i 's/AELYN_TORCH_INDEX/pytorch-cpu/' career-agent/pyproject.toml security-agent/pyproject.toml
# (le script d'installation fait cette détection/substitution automatiquement)

# Dépendances courantes (mail/carrière/média/conversation/API) + voix.
# Ajoute --extra security UNIQUEMENT si tu travailles sur la reconnaissance
# faciale/anti-spoofing (lourd : tensorflow, ultralytics, mediapipe...), ce
# qui reste du ressort personnel de l'auteur, pas nécessaire pour le reste.
uv sync --extra voice
```

> **Piège à connaître avec `uv sync`** : `uv sync --package X` limité à un seul paquet
> du workspace peut désinstaller silencieusement les dépendances des AUTRES membres.
> Resynchronise avec `uv sync --extra voice` (ou `--all-packages --extra voice --extra
> security` si tu as aussi besoin de la reconnaissance faciale) plutôt qu'un sync ciblé
> sur un seul agent.

### Configuration

```bash
cp .env.example .env
```

Édite `.env`, au minimum `EMAIL_USER` / `EMAIL_PASS` pour que l'agent démarre (voir
[Configuration](#configuration-env) plus bas pour le détail de chaque variable).

### Modèles Ollama

```bash
ollama pull qwen3:4b          # modèle par défaut, léger, routage d'intention/conversation
ollama pull gemma3:4b         # génération CV/lettre de motivation (career-agent)
ollama pull mistral:7b        # optionnel : escalade pour le routage d'intention si présent
                               # localement, PC uniquement (jamais sur Raspberry Pi), sinon
                               # repli silencieux sur qwen3:4b
```

Seuls `qwen3:4b` et `gemma3:4b` sont nécessaires au fonctionnement normal ; `mistral:7b`
améliore juste la précision du routage d'intention s'il est disponible (voir
`is_model_available()` dans `core/src/aelyn/core/llm.py`, et le détail des benchmarks dans
`.env.example`).

### GPU / CUDA (optionnel)

`torch`/`torchvision` (career-agent, security-agent) pointent vers un index CUDA (`cu130`,
calibré sur le poste de développement d'origine, RTX 3060) via un placeholder
`AELYN_TORCH_INDEX` dans leurs `pyproject.toml` : le script d'installation le remplace
automatiquement par `pytorch-cu130` ou `pytorch-cpu` selon qu'un GPU NVIDIA compatible est
détecté (`nvidia-smi`). En installation manuelle :

- **GPU NVIDIA, autre version CUDA** : remplace `AELYN_TORCH_INDEX` par `pytorch-cu130`
  dans `career-agent/pyproject.toml` et `security-agent/pyproject.toml`, puis adapte l'URL
  de l'index `pytorch-cu130` dans `pyproject.toml` racine (`[[tool.uv.index]]`) à la
  version qui correspond à ta carte (`nvidia-smi` donne la version CUDA du driver).
- **Pas de GPU** : remplace `AELYN_TORCH_INDEX` par `pytorch-cpu` dans les deux fichiers
  ci-dessus, puis mets `WHISPER_DEVICE=cpu` et `EMBEDDING_DEVICE=cpu` dans `.env`. Tout
  fonctionne, juste plus lentement sur les embeddings/la transcription.
- **cuBLAS/cuDNN manquants** (`Library cublas64_12.dll is not found`) : l'extra `voice`
  installe déjà `nvidia-cublas-cu12`/`nvidia-cudnn-cu12`, mais Windows ne les trouve que si
  `voice._register_cuda_dll_dirs()` s'exécute (fait automatiquement au premier chargement
  du modèle Whisper).

### Voix (`aelyn chat --voix`)

- Premier lancement : télécharge le modèle Kokoro (~90 Mo) et le modèle Whisper "small"
  (~500 Mo, configurable via `WHISPER_MODEL_SIZE`), connexion internet nécessaire une
  seule fois, tout fonctionne hors ligne ensuite.
- Vérifie/ajuste `MICROPHONE_NAME` dans `.env` si le micro par défaut ne capte rien
  (`sr.Microphone.list_microphone_names()` pour lister les périphériques disponibles).

### Appairage TV (agent média, optionnel)

```bash
cd media-agent
uv run python scripts/text_chat.py
```

Suis les instructions à l'écran (code affiché sur la TV) lors du premier lancement, le
certificat/la clé générés sont ensuite réutilisés (`~/.aelyn/tv_cert.pem`,
`~/.aelyn/tv_key.pem`), pas besoin de réappairer à chaque fois.

## Configuration (.env)

Toutes les variables sont dans `.env.example` avec leur commentaire. Résumé par section :

| Section | Variables clés | Notes |
|---|---|---|
| Messagerie | `EMAIL_USER`, `EMAIL_PASS`, `IMAP_SERVER`, `SMTP_SERVER` | Mot de passe d'application Gmail, pas le vrai mot de passe |
| LLM (Ollama) | `OLLAMA_HOST`, `LLM_MODEL`, `LLM_MODEL_HEAVY`, `LLM_THINK` | `LLM_THINK=false` évite le raisonnement caché de qwen3 (très lent) |
| Sécurité (visage) | `FACES_DIR`, `FACE_MATCH_THRESHOLD` | Utilisé par `aelyn_security`, pas encore branché sur le chat |
| Carrière | `LLM_MODEL_CAREER`, `FRANCE_TRAVAIL_CLIENT_ID/SECRET`, `KEYWORDS`, `DEPARTMENT`, `WEIGHT_SCORE_*`, `TOP_K_CHUNKS` | France Travail = API publique de l'emploi public français (ex-Pôle Emploi) ; voir [Prérequis](#prérequis) pour obtenir `CLIENT_ID`/`CLIENT_SECRET`, optionnel |
| Voix | `MICROPHONE_NAME`, `WHISPER_MODEL_SIZE`, `WHISPER_DEVICE`, `WAKE_TIMEOUT_SECONDS` | Whisper tenté avant repli sur Google STT |
| Média (TV) | `TV_IP_ADRESS`, `TV_CERT_FILE`, `TV_KEY_FILE` | IP locale de la Freebox Pop |
| Garde-fous | `ALLOW_AUTONOMOUS_SEND`, `MAX_MAILS_PER_RUN` | Tant que `false`, aucun mail n'est envoyé sans validation humaine |

`.env` est dans `.gitignore`, ne le commite jamais (`.env.example` est le seul fichier de
config versionné, sans secrets).

## Frontend

L'interface web (`src/frontend/web`, React + Vite + TypeScript) est un processus
**séparé** de l'API (deux ports distincts, `aelyn-api` ne sert aucun fichier statique du
frontend) :

```bash
cd src/frontend/web
npm install
cp .env.example .env.local   # VITE_API_BASE_URL, http://localhost:8001 par défaut
npm run dev                  # http://localhost:5173
```

Si `aelyn-api` tourne sur un port différent de 8001, ajuste `VITE_API_BASE_URL` dans
`.env.local` (jamais dans `.env.example`, qui reste le gabarit versionné). Sans API
joignable, le frontend reste utilisable en mode démo hors-ligne (données factices
clairement indiquées comme telles), utile pour explorer l'interface sans backend lancé.

## Utilisation

Toutes les commandes ci-dessous se lancent depuis `src/backend`.

### CLI directe (mail)

```bash
uv run aelyn verifier              # liste les mails non lus, sans LLM (tableau Rich)
uv run aelyn triage                # propose une action par mail (rien n'est exécuté)
uv run aelyn valider 3             # exécute la proposition #3
uv run aelyn rejeter 3             # rejette la proposition #3
uv run aelyn rapport               # résumé des actions récentes (journal)
```

### Mode conversationnel

```bash
uv run aelyn chat                  # au clavier, phrase libre
uv run aelyn chat --voix           # au micro, réponses vocales (mot d'activation « Éline »)
```

Pas de commandes figées à mémoriser : une phrase libre suffit. Voici tout ce qu'AELYN
comprend nativement aujourd'hui.

**Mail**

| Dis... | AELYN... |
|---|---|
| « vérifie mes mails » | liste les non-lus (IMAP, sans LLM) |
| « trie mes mails » | propose une action (répondre/archiver/ignorer/lire plus tard/signaler) par mail, rien n'est exécuté |
| « résume-moi le mail de X » | résumé du mail le plus récent correspondant à X (nom, objet...) |
| « rédige un brouillon pour le mail de X » / « réponds à ce mail » | brouillon de réponse, proposé avant tout envoi |
| « valide l'action #3 » / « rejette l'action #3 » | exécute/rejette une proposition de triage déjà faite |
| « fais-moi un rapport » | résumé des actions des dernières 24h (journal) |

**Carrière**

| Dis... | AELYN... |
|---|---|
| « cherche des offres data scientist chez EDF » | recherche France Travail, classée par pertinence avec ton profil |
| « cherche 20 offres en intelligence artificielle » | comme ci-dessus, avec un nombre maximum de résultats explicite |
| « décris-moi la première offre » / « décris l'offre de X » | description complète d'une offre déjà listée |
| « prépare mon CV pour cette offre » | brouillon de CV ciblé (confirmation « oui »/« non » avant génération) |
| « rédige une lettre de motivation pour cette offre » | idem pour une lettre de motivation |
| « affine cette lettre, insiste sur X » | reprend la dernière lettre générée avec une consigne |

**Média (Freebox Pop / Android TV)**

| Dis... | AELYN... |
|---|---|
| « lance Netflix » / « lance YouTube » | ouvre l'appli sur la TV |
| « cherche Stranger Things sur Netflix/YouTube » | lance une recherche dans l'appli |
| « monte/baisse le son », « coupe le son » | ajuste le volume |
| « pause », « suivant », « précédent » | contrôle de lecture |
| « haut »/« bas »/« gauche »/« droite », « sélectionne », « retour », « accueil » | navigation D-pad |
| « allume/éteins la TV » | marche/veille (HDMI-CEC, support variable selon le téléviseur) |

**Système / divers**

| Dis... | AELYN... |
|---|---|
| « quelle heure est-il ? » | heure système, sans LLM |
| « quel jour on est ? » | date système, sans LLM |
| « affiche les offres »/« lis le premier » | relit la dernière liste (offres ou mails) déjà montrée ce tour-ci |
| « reformule ça » | redit la dernière réponse d'AELYN autrement |
| bonjour/salut, ou n'importe quoi d'autre | conversation libre (le LLM répond, aucune commande n'est exécutée) |

`valider`/`rejeter` ne s'exécutent que depuis la CLI interactive (confirmation au clavier) ;
depuis le chat web/API, AELYN l'explique plutôt que de bloquer sur une confirmation qui ne
peut pas venir d'un appel HTTP.

### Scripts de test manuels (appels réels, pas de mock)

```bash
cd career-agent && uv run python scripts/manual_offers_check.py [cdi|cdd|alternance|stage]
cd career-agent && uv run python scripts/manual_structure_check.py

cd media-agent && uv run python scripts/text_chat.py   # REPL texte -> vraie TV
```

### Tests

```bash
uv run --package aelyn-career pytest career-agent/tests -q
```

(Seul `career-agent` a une suite de tests pour l'instant, voir [CR](#état-du-projet--cr).)

## Où modifier quoi

| Je veux changer... | Fichier |
|---|---|
| Un réglage global (modèle LLM, seuils, chemins) | `core/src/aelyn/core/config.py` + `.env` |
| Le comportement du LLM (retry, parsing JSON, escalade de modèle) | `core/src/aelyn/core/llm.py` |
| La voix (TTS Edge/Kokoro, STT Whisper/Google, micro) | `core/src/aelyn/core/voice.py` |
| L'historique des actions (cache, compte-rendu) | `core/src/aelyn/core/journal.py` |
| Comment un mail est trié / résumé | `email-agent/src/aelyn_email/agent.py` + `prompts.py` |
| Comment une offre est cherchée / notée | `career-agent/src/aelyn_career/pipeline.py`, `embbeder.py`, `france_travail/offers.py` |
| Une nouvelle commande TV/média | `media-agent/src/aelyn_media/agent.py` (`MediaAgent`, `COMMANDS`) |
| Ce que le LLM comprend comme intention | `conversational-agent/src/aelyn_conversation/prompts.py` (`SYSTEM_INTENT`) + `models.py` (`Intent`) |
| Un raccourci rapide sans appel LLM | `conversational-agent/src/aelyn_conversation/fast_router.py` |
| Le rendu du chat en CLI (bulles, tableau) | `conversational-agent/src/aelyn_conversation/agent.py` (`_print_agent_bubble` et environs) |
| Les sous-commandes `aelyn <...>` disponibles | `core/src/aelyn/cli.py` |

## État du projet / CR

### Fait et fonctionnel

- **Mail** : tri IMAP avec proposition d'action (jamais d'exécution auto sauf validation),
  cache pour éviter de retriager un mail déjà vu, tableau Rich en CLI directe.
- **Carrière** : recherche France Travail (mots-clés, département, type de contrat),
  structuration LLM avec cache par ID d'offre, pipeline de scoring (BM25 + cosinus),
  ce dernier n'est **pas encore branché sur le chat en direct** (trop lent sans cache sur
  de nouvelles offres), utilisable via les scripts manuels seulement.
- **Conversation** : routage rapide (regex) + LLM en repli, conversation libre, lecture
  arrière (« lis le premier »), résolution de référence par position ou mot-clé, escalade
  automatique vers un modèle plus lourd si disponible localement.
- **Voix** : transcription locale (faster-whisper, GPU) avec repli automatique sur Google
  STT ; synthèse Edge TTS avec repli automatique sur Kokoro (local, hors-ligne) ; mot
  d'activation tolérant aux erreurs de reconnaissance à 1 caractère près.
- **Média** : navigation, volume, lecture/pause, lancement Netflix/YouTube, recherche
  YouTube (fonctionne, deep link propre), le tout piloté en voix/texte comme en CLI.

### Limites connues (pas des bugs à corriger, des contraintes réelles)

- **Recherche Netflix automatisée ne fonctionne pas** sur ce boîtier Freebox Pop : la
  touche `SEARCH` est interceptée par l'assistant Google système, le deep link de
  recherche Netflix est ignoré, et la navigation D-pad manuelle est elle-même interceptée
  (haut/bas ouvrent le volume). Testé et abandonné pour l'instant ; `netflix` (lancement
  simple) et `search_youtube` restent fiables.
- **`tv_power` (allumer la TV via HDMI-CEC)** : implémenté (`KEYCODE_TV_POWER`), jamais
  confirmé fonctionnel en usage réel ; dépend du CEC activé des deux côtés (Freebox et
  téléviseur).
- **La Freebox Pop peut s'éteindre avec la TV** (CEC "standby sync") : à vérifier/ajuster
  dans les réglages HDMI-CEC de la box si tu veux qu'AELYN reste joignable même TV éteinte.
- **`aelyn_security` n'est pas branché** sur `aelyn_conversation`/la CLI : scripts
  autonomes (`detector.py`, `train.py`...) pour l'anti-spoofing et la reconnaissance
  faciale, à intégrer plus tard (nouvelle commande + intent, sur le modèle des autres
  agents).
- **STT résiduel** : même avec Whisper + GPU, du bruit fort ou une élocution très rapide
  peut encore échouer, limite inhérente à toute reconnaissance vocale.
- **Routage d'intention** : qwen3:4b (modèle par défaut) reste occasionnellement imprécis
  sur l'extraction de champs (mots-clés, action média) ; mistral:7b est nettement meilleur
  mais nécessite d'être pullé localement (`ollama pull mistral:7b`), sinon repli silencieux.
- **Tests** : `pytest` (lancé depuis `src/backend`) couvre career-agent, conversational-agent,
  aelyn-api et le core ; `email-agent`/`media-agent`/`security-agent` restent sans suite
  dédiée. À compléter au fil de l'eau, pas de blocage particulier pour en ajouter.
- **`computer-agent/`, `gateway/`, `src/frontend/mobile`** : dossiers réservés, vides ;
  rien à ouvrir ici pour l'instant, juste des futurs emplacements prévus.

## Contribuer

Le dépôt est un `uv` workspace : chaque agent est un paquet Python indépendant sous
`src/backend/<nom>-agent/`, avec son propre `pyproject.toml`, importé par les autres via
`[tool.uv.sources] <paquet> = { workspace = true }`.

### Se mettre en route

1. Suis [Installation](#installation) ci-dessus en entier (uv sync, `.env`, modèles
   Ollama).
2. Lance `uv run aelyn chat` pour vérifier que tout répond avant de toucher au code.
3. `uv run --package aelyn-career pytest career-agent/tests -q` doit passer (22/22), si
   ce n'est pas le cas, quelque chose s'est mal installé.

### Ajouter un nouvel agent

Copie la structure d'un agent existant simple (`email-agent/` est le plus court) :

```
mon-agent/
├── pyproject.toml          # name = "aelyn-mon-agent", dependencies = ["aelyn", ...]
└── src/
    └── aelyn_mon_agent/
        ├── __init__.py
        └── agent.py         # classe + run_command(command, ...) -> (code, résultats)
```

Puis :
1. Ajoute-le à `[tool.uv.workspace] members` et `[tool.uv.sources]` dans le
   `pyproject.toml` racine.
2. Branche-le soit dans `core/src/aelyn/cli.py` (sous-commande directe), soit dans
   `aelyn_conversation` (nouvelle valeur dans `Intent.commande` + règles dans
   `SYSTEM_INTENT` + dispatch dans `agent.py`'s `_run_command`), voir comment
   `aelyn_career`/`aelyn_media` ont été branchés pour le modèle à suivre.
3. `uv sync --all-packages --all-extras` pour que le nouveau paquet soit installé partout
   où il faut.

### Convention de code

- Commentaires en français, seulement pour expliquer un **pourquoi** non évident (une
  contrainte cachée, un contournement, un comportement surprenant), pas pour redire ce
  que le code fait déjà.
- Un module = une responsabilité claire ; `run_command()` en bas de chaque `agent.py` est
  le point d'entrée partagé par la CLI directe et le chat (jamais de logique dupliquée
  entre les deux).
- Avant de pousser : `uv run python -m py_compile <fichiers touchés>` au minimum, et la
  suite de tests du paquet concerné si elle existe.
- Workflow git : branche par fonctionnalité + pull request vers `main`, même en solo/à
  deux, ça garde un historique propre et permet une relecture avant de fusionner.
