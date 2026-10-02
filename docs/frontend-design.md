# AELYN — Direction de design frontend

Ce document fixe la direction visuelle et fonctionnelle du frontend AELYN
(web puis mobile). Objectif : un vrai poste de contrôle opérationnel —
pas un "dashboard IA" générique.

## Principe directeur

**AELYN doit ressembler à un produit logiciel de monitoring qui existe
depuis 3 ans, avec de vrais utilisateurs, des contraintes opérationnelles
réelles, de vrais logs, de vraies erreurs, de vrais réglages — pas à une
interface générée par IA.**

Références : consoles de monitoring professionnelles (NOC/SOC), outils
réseau, outils développeur, applications de contrôle caméra — pas des
dashboards IA génériques.

### À éviter systématiquement

- Glassmorphism excessif, cartes flottantes translucides
- Dégradés néon violet/bleu
- Bordures lumineuses ("glow") décoratives
- Grandes sections hero, objets 3D décoratifs
- Statistiques sans signification réelle
- Typographie surdimensionnée
- Effets "magie IA" génériques
- Cartes arrondies à outrance, dashboard composé uniquement de cartes indépendantes
- Faux graphiques purement décoratifs
- Emojis aléatoires, avatar robot/IA générique
- Illustrations superflues
- Apparence "concept Dribbble"

**Chaque élément doit exister parce que l'utilisateur peut observer
quelque chose, comprendre quelque chose, ou agir sur quelque chose.**

## Style visuel

- Fond neutre sombre, couleurs d'accent restreintes.
- La couleur communique un **état**, jamais une décoration :
  - neutre = information
  - vert = opérationnel
  - ambre = avertissement
  - rouge = critique
  - bleu = actif / sélectionné
- Typographie à forte hiérarchie, très lisible.
- Bordures fines, séparateurs, élévation de surface subtile — pas
  d'ombres lourdes ni d'effets verre.
- Contrôles compacts : tables, timelines, logs, panneaux vidéo,
  indicateurs d'état.
- Densité suffisante pour ressembler à un logiciel utilisé tous les
  jours, pas à une page de présentation.
- Contenu réaliste (jamais de lorem ipsum) — mais aucune fonctionnalité
  inventée qui n'existe pas réellement dans AELYN.

## Desktop / Web

Poste de contrôle dense mais lisible. L'écran principal expose
immédiatement :

1. **État système** — AELYN Core, Raspberry Pi #1, Raspberry Pi #2
   (vision), CPU, RAM, température, disque, réseau, connectivité
   Tailscale, services actifs.
2. **Caméras** — flux en direct, nom, statut de connexion, FPS,
   résolution, latence, dernière détection, statut d'enregistrement,
   vue plein écran dédiée par caméra.
3. **Événements sécurité/vision** — reconnaissance faciale, personne
   inconnue détectée, mouvement, intrusion, horodatage, caméra source,
   confiance, sévérité.
4. **Activité AELYN** — flux d'événements réel de ce que l'assistant a
   fait (façon log système), pas une carte décorative :
   ```
   12:41:03  Commande vocale reçue
   12:41:04  Caméra 02 activée
   12:41:05  Personne détectée
   12:41:06  Visage reconnu
   12:41:07  Notification envoyée
   ```
5. **Commandes** — zone persistante : taper une commande, utiliser la
   voix, voir ce qu'AELYN a compris, valider une action sensible, voir
   le statut d'exécution.
   ```
   > AELYN, montre-moi la caméra de l'entrée
   COMPRIS : Ouvrir caméra / Entrée
   EXÉCUTION...
   ```
6. **Analyse de données** — métriques système, statistiques caméra,
   fréquence d'événements, historique de détection, consommation de
   ressources, tendances temporelles réelles (pas d'analytics fabriqués).

### Navigation (desktop)

Structure fonctionnelle, pas une sidebar décorative :

`Overview` · `Cameras` · `Security` · `Assistant` · `Data` · `Activity` ·
`System` · `Settings`

La navigation indique clairement la position actuelle et affiche des
indicateurs d'état utiles quand c'est pertinent.

### Maquette de référence (desktop)

```text
┌─────────────────────────────────────────────────────────────────────┐
│ AELYN        ● SYSTEM ONLINE        12:42       TAILSCALE ●        │
├──────────────┬──────────────────────────────────────────────────────┤
│              │                                                      │
│ OVERVIEW     │  SYSTEM                                              │
│              │  CPU 23%   RAM 61%   TEMP 48°C   NET 1.2 Mb/s      │
│ CAMERAS      │                                                      │
│              ├─────────────────────────┬────────────────────────────┤
│ SECURITY     │                         │                            │
│              │     CAMERA 01           │      CAMERA 02             │
│ ASSISTANT    │     LIVE                │      LIVE                   │
│              │                         │                            │
│ DATA         │                         │                            │
│              ├─────────────────────────┴────────────────────────────┤
│ ACTIVITY     │  SECURITY EVENTS                                     │
│              │  12:41  Person detected      Entrance       ●        │
│ SYSTEM       │  12:38  Face recognized      Office         ●        │
│              │  12:32  Motion detected      Garden         ●        │
│ SETTINGS     ├──────────────────────────────────────────────────────┤
│              │ > AELYN, show camera 01                              │
│              │   EXECUTED                                            │
└──────────────┴──────────────────────────────────────────────────────┘
```

## Mobile (React Native — phase ultérieure)

L'interface mobile n'est **pas** une version compressée du dashboard
desktop : la hiérarchie d'information est repensée pour un usage à une
main.

Navigation basse : `Home` · `Cameras` · `Events` · `AELYN` · `More`

L'écran d'accueil priorise : 1) état système global, 2) événements
urgents, 3) accès caméra, 4) contrôle vocal AELYN, 5) actions récentes.

L'écran caméra priorise le flux vidéo avec des contrôles larges,
utilisables physiquement. L'écran AELYN se comporte comme une vraie
console de commande, avec interaction vocale et historique d'exécution
visible. Ne pas transformer l'application mobile en collection de cartes.

```text
┌──────────────────────┐
│ AELYN          ●     │
│ System operational   │
│                      │
│ ┌──────────────────┐ │
│ │   CAMERA 01      │ │
│ │      LIVE        │ │
│ └──────────────────┘ │
│                      │
│ SECURITY             │
│ ● No active threat   │
│                      │
│ RECENT EVENTS        │
│ Person detected      │
│ 2 min ago            │
│ ──────────────────── │
│         ◉            │
│     Hold to talk     │
├──────────────────────┤
│ Home Camera Events   │
│       AELYN More     │
└──────────────────────┘
```

## Assistant / Chat

- Historique de conversation complet, consultable, façon messagerie
  professionnelle (pas de bulles "SMS" cartoon) — messages utilisateur
  et AELYN clairement distingués, horodatés.
- Chaque échange affiche, quand pertinent, ce qu'AELYN a **compris**
  (l'intention routée) avant le résultat, pour rester transparent sur
  le fonctionnement réel du système.
- Historique persistant entre sessions, consultable/recherchable —
  pas juste le fil de la session en cours.

## Interaction vocale — direction "Siri"

- Un déclencheur vocal unique, visuellement central quand actif : un
  indicateur circulaire (orbe/onde) qui réagit à la voix en temps réel
  (amplitude), pas une simple icône micro statique.
- États visuels distincts et immédiats : veille → écoute → traitement
  → réponse — chaque état a une animation/couleur propre, cohérente
  avec la palette d'état définie plus haut (bleu = actif, neutre =
  veille).
- La transcription de ce qui est compris s'affiche en direct pendant
  l'écoute (comme Siri affiche le texte reconnu en temps réel), pas
  seulement après coup.
- Le mode vocal reste consultable comme conversation texte ensuite —
  jamais une interaction "perdue" une fois terminée.

## Stack technique (web)

- React + TypeScript + Vite.
- Pas de librairie de composants "AI dashboard" clé en main (évite le
  piège du look générique) — composants construits sur-mesure avec une
  base de tokens CSS (couleurs, espacements, typographie) cohérente
  avec ce document.
- Données réalistes en dur (mock) tant que l'API AELYN Core (FastAPI,
  non commencée) n'existe pas — structurées comme si elles venaient
  d'un vrai backend, pour faciliter le branchement futur.
