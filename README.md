# AELYN — version lite

Assistant personnel local, privé par défaut : un LLM auto-hébergé (Ollama) orchestre une
famille d'agents spécialisés (mails, carrière, multimédia, conversation) à travers un
monorepo Python (`uv` workspace) et une interface web (React + Vite).

**Ceci est une version simplifiée et publique d'AELYN.** La version complète (avec en
plus la reconnaissance faciale/anti-spoofing) reste privée.

## Installation rapide

```bash
# macOS / Linux / Git Bash (Windows)
./install.sh
./start.sh
```

```powershell
# Windows (PowerShell natif)
powershell -ExecutionPolicy Bypass -File install.ps1
powershell -ExecutionPolicy Bypass -File start.ps1
```

Le script d'installation détecte automatiquement si tu as un GPU NVIDIA compatible (sinon
installe une version CPU, aucune action de ta part), vérifie les prérequis, te demande tes
identifiants/secrets, installe tout, et tire les modèles Ollama nécessaires.

Une fois lancé : `http://localhost:5173` (interface web) et `http://localhost:8001/docs`
(API).

## Prérequis

- **[uv](https://docs.astral.sh/uv/)** (gère l'environnement Python) et **Python 3.11+**.
- **[Ollama](https://ollama.com/)** installé et lancé (`ollama serve`).
- **Node.js** (pour le frontend web).
- **Windows uniquement, pour la voix** : [espeak-ng](https://github.com/espeak-ng/espeak-ng)
  (`winget install eSpeak-NG.eSpeak-NG`) — sans ça, installe avec `--no-voice`.
- **GPU NVIDIA** : optionnel. Le script d'installation détecte automatiquement sa présence
  et installe la bonne version de PyTorch (CUDA ou CPU) ; sans GPU, tout fonctionne, juste
  plus lentement sur les embeddings/la transcription vocale.
- **Un compte Gmail** avec un [mot de passe d'application](https://myaccount.google.com/apppasswords)
  (pas ton vrai mot de passe) si tu veux utiliser l'agent mail.
- **Des identifiants France Travail** (optionnel, uniquement pour la recherche d'offres
  d'emploi) : France Travail (ex-Pôle Emploi, l'opérateur public français de l'emploi)
  expose une API publique et gratuite avec les offres d'emploi de tout le pays.
  1. Crée un compte sur [francetravail.io](https://francetravail.io).
  2. Dans l'espace développeur, crée une "application" : ça te donne un `Client ID` et un
     `Client Secret` (protocole OAuth2).
  3. Abonne cette application au produit **"Offres d'emploi v2"** (gratuit).
  4. Le script d'installation te demande ces deux valeurs directement (ou édite `.env` à
     la main : `FRANCE_TRAVAIL_CLIENT_ID`/`FRANCE_TRAVAIL_CLIENT_SECRET`).

  Sans ces identifiants, tout le reste d'AELYN fonctionne normalement ; seule la recherche
  d'offres reste indisponible.

## Documentation complète

Ce dépôt a trois README :

- **Celui-ci** : vue d'ensemble, installation rapide.
- **[README.backend.md](README.backend.md)** (copie de
  [src/backend/README.md](src/backend/README.md)) : architecture détaillée, configuration
  complète (`.env`), chaque agent, limites connues.
- **[README.frontend.md](README.frontend.md)** (copie de
  [src/frontend/web/README.md](src/frontend/web/README.md)) : pages de l'interface web,
  variables d'environnement front, structure du code.

## Architecture (résumé)

```
Toi (texte ou voix)
        │
        ▼
aelyn_conversation   <- comprend une phrase libre, route vers une commande
   │   │   │
   │   │   └── aelyn_media     (Freebox Pop / Android TV : Netflix, YouTube, volume…)
   │   └────── aelyn_career    (recherche d'offres France Travail, matching profil)
   └────────── aelyn_email     (tri IMAP, brouillons, envoi validé)

aelyn (core)         <- config, accès LLM/Ollama, journal des actions, voix
src/frontend/web     <- interface web (React + Vite + TypeScript)
```

## Licence

Projet personnel, partagé à titre d'exemple/d'apprentissage.
Merci de t'abonner et de mettre un star si le projet te plait.
