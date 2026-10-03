# AELYN — version lite

Assistant personnel local, privé par défaut : un LLM auto-hébergé (Ollama) orchestre une
famille d'agents spécialisés (mails, carrière, multimédia, conversation) à travers un
monorepo Python (`uv` workspace) et une interface web (React + Vite).

**Ceci est une version simplifiée et publique d'AELYN.** La version complète (avec en
plus la reconnaissance faciale/anti-spoofing) reste privée.

## Installation rapide

Ouvre un terminal **à la racine du dépôt** (le dossier qui contient ce README), juste après
avoir cloné le projet.

**macOS / Linux / Git Bash (Windows)** :
```bash
chmod +x install.sh start.sh   # une seule fois, rend les scripts exécutables
./install.sh
./start.sh
```
Sur Windows, utilise **Git Bash** (installé avec Git) pour cette méthode, pas l'invite de
commandes (`cmd.exe`) ni PowerShell. Si `./install.sh` répond `Permission denied`, le
`chmod +x` ci-dessus n'a pas été exécuté (ou pas pris en compte) : relance-le, ou lance le
script autrement avec `bash install.sh` (fonctionne même sans le bit exécutable).

**Windows (PowerShell natif)** :
```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
powershell -ExecutionPolicy Bypass -File start.ps1
```
Le `-ExecutionPolicy Bypass` est nécessaire car PowerShell bloque par défaut l'exécution de
scripts `.ps1` qui ne sont pas signés numériquement ; ce flag l'autorise **pour cette seule
commande**, sans rien changer de façon permanente sur ta machine (pas besoin de
`Set-ExecutionPolicy`).

Le script d'installation détecte automatiquement si tu as un GPU NVIDIA compatible (sinon
installe une version CPU, aucune action de ta part), vérifie les prérequis, te demande tes
identifiants/secrets, installe tout, et tire les modèles Ollama nécessaires.

Une fois lancé : `http://localhost:5173` (interface web) et `http://localhost:8001/docs`
(API). Les deux scripts (`install`, `start`) peuvent être relancés sans risque : `install.sh`/
`.ps1` ne réécrase pas ce qui est déjà configuré, et `start.sh`/`.ps1` affiche les deux liens
ci-dessus à chaque lancement.

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
