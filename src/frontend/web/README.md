# AELYN — Frontend web

Interface web d'AELYN : React + Vite + TypeScript. C'est un processus **séparé** de
l'API (`aelyn-api`, FastAPI) — deux ports distincts, l'API ne sert aucun fichier
statique du frontend.

## Lancement

```bash
npm install
cp .env.example .env.local   # VITE_API_BASE_URL, http://localhost:8001 par défaut
npm run dev                  # http://localhost:5173
```

Si `aelyn-api` tourne sur un port différent de 8001, ajuste `VITE_API_BASE_URL` dans
`.env.local` (jamais dans `.env.example`, qui reste le gabarit versionné).

Sans API joignable, l'interface reste utilisable en mode démo hors-ligne : chaque page
retombe sur des données factices clairement indiquées comme telles (voir `src/mocks`),
utile pour explorer l'UI sans lancer le backend.

## Pages

| Route | Contenu |
|---|---|
| `/` (Overview) | Vue d'ensemble : CPU/RAM/GPU, caméras, événements sécurité, journal d'activité |
| `/cameras` | Flux caméra (absente en version lite, voir `VITE_LITE_MODE` ci-dessous) |
| `/security` | Événements de détection/reconnaissance |
| `/assistant` | Chat avec AELYN (texte + voix), historique réel via `GET /chat/history` |
| `/data` | Données brutes exposées par l'API |
| `/activity` | Journal complet des actions |
| `/system` | Détail par nœud : CPU, RAM, température, disque, GPU (si présent), services |
| `/settings` | Réglages, verrouillés par passkey (`PATCH /settings`) |

## Variables d'environnement (`.env.local`)

| Variable | Rôle |
|---|---|
| `VITE_API_BASE_URL` | URL de base de `aelyn-api` (défaut `http://localhost:8001`) |
| `VITE_LITE_MODE` | `true` masque les sections Caméras/Raspberry Pi (matériel absent chez la plupart des utilisateurs) ; CPU/RAM restent toujours visibles, GPU s'affiche seulement si `nvidia-smi` en détecte un |

## Structure

```
src/
├── components/    # UI réutilisable (chat, caméras, layout, sécurité, voix...)
├── lib/           # client API (api.ts), interpréteur de commandes, hooks (useCoreNode...)
├── mocks/         # données de démo, utilisées quand l'API est injoignable
├── pages/         # une page par route (voir tableau ci-dessus)
└── types/         # types partagés (chat, système, caméras...)
```

## Scripts

```bash
npm run dev       # serveur de dev (HMR)
npm run build     # type-check (tsc -b) + build de prod dans dist/
npm run lint      # oxlint
npm run preview   # sert le build de prod localement
```

## Lien avec le backend

Voir [../../backend/README.md](../../backend/README.md) pour lancer `aelyn-api` (et le
reste du backend) — ou `../../../start.sh`/`start.ps1` à la racine du dépôt, qui lance
les deux ensemble.
