# Directives front-end — AELYN

Document de référence pour l'agent chargé du développement front-end d'AELYN (dashboard web React et application mobile React Native). À faire surveiller/appliquer par l'agent à chaque tâche de développement d'interface.

Mockup de référence (direction visuelle validée, 4 écrans) : https://claude.ai/artifact/CJd9UMWpTpVPhA3odamtdB

---

## 1. Contexte produit (à garder en tête à chaque écran)

AELYN est un assistant personnel **local et privacy-first**, réparti sur 2 Raspberry Pi 4 (+ PC optionnel), accessible à distance via Tailscale, sans dépendance à un cloud externe pour le raisonnement. Trois interfaces : app mobile (React Native), dashboard web (React), interface vocale.

Le dashboard web n'est pas un produit SaaS grand public : c'est **un panneau de contrôle personnel et domestique** — vue caméras en direct, statut des agents (email, carrière, média, maison), chat/voix, fichiers, contrôle TV/domotique. L'utilisateur est le seul utilisateur. Le ton doit être celui d'un poste de contrôle sobre et fiable, pas celui d'un onboarding commercial.

**Implication directe pour le design : évite les codes visuels SaaS générique (cards uniformes à ombre grise, bandeaux marketing, CTA "Get Started").** Vise plutôt un objet fonctionnel, un peu "panneau d'instruments", proche d'un poste de supervision domestique.

---

## 2. Stack technique imposée

- **Web** : React, WebSocket natif (ou `socket.io` si le backend l'utilise) pour les flux temps réel (statut agents, caméras, notifications), pas de framework SaaS lourd type Material UI par défaut — composants sur-mesure.
- **Mobile** : React Native CLI pur (pas Expo managé — déjà utilisé sur le projet BDS).
- **Backend consommé** : FastAPI / WebSocket sur Raspberry Pi #1 (AELYN Core). Toujours prévoir un état "backend/PC injoignable" (le PC de calcul peut être off, le Pi doit rester fonctionnel en dégradé).
- **Auth** : accès via Tailscale (réseau privé) — l'UI doit quand même prévoir un écran de connexion/token, ne jamais supposer un réseau de confiance implicite côté UI.
- **Styling** : CSS-in-JS ou CSS modules au choix de l'agent, mais **jetons de design centralisés** (voir §3) — aucune couleur ou taille en dur dans les composants.

---

## 3. Direction de design (jetons)

### Palette (mode sombre par défaut — c'est un panneau de contrôle, pas un site vitrine)
- Fond principal : `#17181B` (noir chaud, pas un `#0B0B0B` neutre générique)
- Fond secondaire / panneaux : `#1F2125`
- Bordures / séparateurs : `#2C2F34`
- Texte principal : `#EAE7E0`
- Texte secondaire : `#95989F` · texte tertiaire (labels discrets) : `#63666D`
- Accent "présence AELYN" (agent actif, chat, focus) : `#6C78E6` (indigo sourd, halo `#3A3F7A`) — jamais de vert acide / vermillon par défaut
- Accent "alerte / sécurité" (détection caméra, notification urgente) : `#E0A458` (ambre chaud)
- État "en direct" (LIVE caméra, enregistrement) : rouge sourd `#C25A4C`, jamais un rouge saturé pur
- État "actif/en ligne" (agent, connexion) : `#7FB56B`
- Mode clair (secondaire, bascule utilisateur) : fond `#F1EFE9`, panneaux `#FFFFFF`/`#F7F5F0`, bordures `#DEDAD1`, texte `#1C1B19`/`#5C5A55` — mêmes accents

### Typographie (retenue dans le mockup)
- **UI / titres / navigation** : Space Grotesk, poids 500–600 pour les titres, jamais en dessous de 500 sur un titre.
- **Corps de texte / labels de formulaire** : IBM Plex Sans, poids 400 (500 pour les valeurs mises en avant).
- **Données / télémétrie** : JetBrains Mono, réservée à tout ce qui est mesure ou statut brut — timestamps caméra, score de confiance de détection, logs d'agents, IP/latence Tailscale, noms de modèles (`gguf q4`). Ce choix a un sens fonctionnel : distinguer visuellement "ce qui est mesuré par le système" de "ce que dit ou affiche AELYN".
- Ces trois familles suffisent pour tout l'écosystème (web + mobile) ; ne pas en introduire d'autres par écran.
- Pas de majuscules systématiques pour les labels, pas d'eyebrow au-dessus de chaque section, pas de flèche `→` en fin de bouton.

### Layout
- Dashboard en grille asymétrique, pas en cards identiques répétées : le panneau chat/voix est l'élément principal (le plus grand, le plus stable visuellement), les flux caméra et statuts d'agents sont des panneaux secondaires de tailles différentes selon leur importance réelle.
- Coins peu ou pas arrondis pour les panneaux de données (feeds caméra, logs) — cohérent avec un objet "instrument" ; coins légèrement arrondis seulement pour les éléments conversationnels (bulles de chat).
- Un seul moment d'animation orchestré par écran (ex. l'apparition d'une détection caméra), pas de hover/reveal sur chaque carte.

---

## 4. Écrans prioritaires et exigences spécifiques

### Dashboard principal (web)
- Panneau chat/voix central avec AELYN (texte + statut d'écoute vocale)
- Vue caméras (grille 1 ou 2 flux, bascule plein écran sur commande vocale ou clic — cf. scénario "montre-moi la caméra 2")
- Statut des agents : email, carrière/emploi, média, maison — chaque agent affiche son état (actif/inactif, dernière action)
- Indicateur "PC de calcul" : disponible / hors ligne (Wake-on-LAN), avec bascule visible du modèle utilisé (léger sur Pi vs modèle complet sur PC)
- Zone notifications (alertes sécurité, emails importants, offres d'emploi pertinentes)

### Configuration des agents (web + mobile)
- Un toggle par agent (email, carrière, média, sécurité), avec sous-titre technique en mono (protocole, méthode) et non un simple libellé marketing
- Sélecteur de stratégie de modèle : modèle léger sur le Pi par défaut, bascule explicite vers le modèle complet quand le PC est disponible (pas une case cachée dans un sous-menu)

### Réglages
- Réseau : statut Tailscale, IP/latence des deux Raspberry Pi en mono — c'est une donnée de diagnostic, pas un texte de bienvenue
- Apparence : bascule thème sombre/clair (sombre par défaut)
- Notifications : granularité par type d'alerte (caméra, offres, emails), pas un seul interrupteur global

### App mobile (React Native)
- Chat/voix en priorité, notifications push (alertes caméra, emails, offres)
- Contrôle à distance (TV, domotique) accessible en 1-2 taps
- Vue caméras allégée (flux à la demande, pas en continu, pour économiser la bande passante en 4G)

### États à toujours prévoir
- Backend Pi #1 injoignable (perte réseau/Tailscale)
- PC de calcul hors ligne → fallback modèle léger (message clair, pas une erreur générique)
- Flux caméra en perte de connexion
- Aucune donnée encore (premier lancement, aucun agent configuré)

---

## 5. Conventions de code pour l'agent

- Un composant = un rôle clair ; pas de composant fourre-tout "Panel" générique.
- Jetons de design (§3) centralisés dans un seul fichier de thème, jamais de valeurs en dur.
- Toute donnée temps réel (WebSocket) passe par un hook dédié par flux (`useAgentStatus`, `useCameraFeed`, `useAelynChat`) avec gestion explicite des états `connecting / connected / lost`.
- Mobile et web partagent la logique métier/état quand c'est possible (pas la UI) — cohérent avec le principe DRY déjà appliqué côté backend (monorepo `uv`).
- Accessibilité non négociable même en usage perso : focus clavier visible, contrastes suffisants, `prefers-reduced-motion` respecté.

---

## 6. Ce que l'agent doit vérifier avant de livrer un écran

1. Est-ce que l'écran ressemble à un dashboard SaaS générique généré par défaut ? Si oui, revoir la mise en page/palette.
2. Les états "backend indisponible" et "PC hors ligne" sont-ils gérés, pas juste le cas nominal ?
3. Les jetons de couleur/typo viennent-ils du thème centralisé, sans valeur en dur ?
4. Le mono est-il réservé aux données mesurées, le sans-serif au reste ?
5. Web et mobile restent-ils cohérents visuellement sans être un simple copier-coller (les usages diffèrent : contrôle vs supervision rapide) ?
