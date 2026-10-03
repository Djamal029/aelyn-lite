# AELYN — version lite

Assistant personnel local, privé par défaut : un LLM auto-hébergé (Ollama) orchestre une
famille d'agents spécialisés (mails, carrière, multimédia, conversation) à travers un
monorepo Python (`uv` workspace) et une interface web (React + Vite).

**Ceci est une version simplifiée et publique d'AELYN.** La version complète (avec en
plus la reconnaissance faciale/anti-spoofing) reste privée.

## Installation rapide

```bash
# macOS / Linux / Git Bash (Windows)
./src/backend/scripts/install.sh
./src/backend/scripts/start.sh
```

```powershell
# Windows (PowerShell natif)
powershell -ExecutionPolicy Bypass -File src\backend\scripts\install.ps1
powershell -ExecutionPolicy Bypass -File src\backend\scripts\start.ps1
```

Le script d'installation détecte automatiquement si tu as un GPU NVIDIA compatible (sinon
installe une version CPU, aucune action de ta part), vérifie les prérequis, te demande tes
identifiants/secrets, installe tout, et tire les modèles Ollama nécessaires.

Une fois lancé : `http://localhost:5173` (interface web) et `http://localhost:8001/docs`
(API).

## Documentation complète

Voir **[src/backend/README.md](src/backend/README.md)** pour : l'architecture détaillée,
les prérequis complets, la configuration (`.env`), l'obtention des identifiants France
Travail, le détail de chaque agent, et la liste des limitations connues.

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
