# Bugs & tâches — AELYN

Reformulation des retours de test en cours (interface CLI actuelle + backend).

---

## 1. Bugs UI — chevauchement / responsive

- [ ] L'écran overview continue de présenter des éléments qui se chevauchent.
- [ ] Même problème de chevauchement ailleurs dans le système (pas isolé à l'overview) — vérifier tous les écrans, pas juste celui-ci.
- [ ] Gérer correctement la responsivité pour éviter ces chevauchements à différentes tailles d'écran/terminal.

## 2. Layout du chat

- [ ] Fixer la disposition : mes messages (moi) à droite, ceux d'AELYN à gauche.

## 3. Bug — le LLM "redémarre" / perd le contexte de la conversation

Constaté en test : après avoir décrit une offre (collective.work), les questions de suivi qui devraient s'appuyer sur cette même offre ("résume cette offre", "prépare un CV pour cette offre") ne sont pas reconnues — AELYN répond comme si aucune offre n'avait été mentionnée, jusqu'à ce que l'offre soit renommée explicitement dans la question ("l'offre de collective.work").

Exemple de session :
1. `decris celle de collective.work` → réponse correcte (détail de la mission, TJM, stack, etc.)
2. `resume cette offre` → AELYN ne fait pas le lien : *"Je ne sais pas de quel mail tu parles"*
3. `resume l'offre de collective.work` → même échec, alors que le nom est répété
4. `prepare un cv pour cette offre` → *"Je ne sais pas de quelle offre tu parles"*
5. `prepare un cv pour l'offre de collective work` → cette fois ça fonctionne (`D'accord, je regarde ça.`)

Deuxième cas observé, même symptôme : après génération d'une lettre de motivation complète (pour une offre donnée), `affiner cette lettre de motivation` échoue avec *"Je ne sais pas de quelle offre tu parles — cherche d'abord des offres."* — alors que la lettre vient d'être générée dans le même échange et que l'offre est donc évidente. Confirme que ce n'est pas isolé à l'agent carrière/CV : ça touche toute référence implicite à ce qui vient d'être produit ("cette lettre", "cette offre", "ce mail").

- [ ] Le contexte conversationnel doit persister sur les références implicites ("cette offre", "ce mail"), pas seulement quand le nom exact est répété à chaque tour.
- [ ] Trouver un moyen d'éviter que le LLM ne redémarre / perde son état entre les tours.

## 4. Sécurité — accès aux réglages

- [ ] Je dois pouvoir modifier les settings, mais l'accès doit être protégé par un passkey (stocké dans le `.env`) demandé avant toute modification.

## 5. Design — couleurs des messages du chat

- [ ] Revoir les couleurs des bulles de message (utilisateur / AELYN) — actuellement à corriger.

## 6. Intégration

- [ ] Brancher le backend et le frontend ensemble, puis lancer effectivement les tests de bout en bout (pas seulement préparer le branchement).

## 7. Performance des réponses

- [ ] Optimiser le temps/la fluidité des réponses (à préciser : latence perçue, streaming token par token, etc.). Exemple observé : génération de la lettre de motivation restée "en cours" plus de 200s avant réponse.

## 8. Commande vocale et réponse vocale

- [ ] Retour visuel pendant qu'AELYN parle : un indicateur qui clignote/pulse pendant la synthèse vocale (comme Siri), pas seulement du texte statique — l'utilisateur doit sentir que "l'IA parle".
- [ ] Même logique côté écoute : un indicateur pendant que la commande vocale est captée/traitée.

## 9. Cache des conversations et historique du chat

- [ ] Définir la stratégie de cache des conversations côté backend (ce qui est gardé en mémoire vive vs persisté).
- [ ] Définir comment l'historique du chat est stocké et rechargé (par session, par jour, illimité avec pagination ?).
- [ ] Clarifier le lien avec le bug de contexte perdu (§3) : le cache de conversation est probablement la même brique à corriger.

## 10. CR — API FastAPI (fait)

Structure livrée (`aelyn-api/`) :

```
aelyn-api/
├── main.py                # point d'entrée, assemble les routers
├── requirements.txt
└── routers/
    ├── email.py            # à réécrire (toi) — implémentation réelle IMAP/LLM
    ├── career.py           # fait
    ├── security.py         # fait
    └── media.py            # à écrire (toi) — 2 endpoints
```

Lancement : `uvicorn main:app --reload`, documentation interactive sur `/docs`.

Chaque agent a son router, monté sous son propre préfixe (`/email`, `/career`, `/security`, `/media`). Les données sont pour l'instant en dur (`FAKE_...`) avec un `TODO` explicite à l'endroit exact où brancher la vraie logique (IMAP, matching par embeddings, flux pi-vision) — la forme des endpoints est stable pendant que le contenu se branche derrière.

- **`/email`** *(repris par toi)* : `GET /email` (liste), `GET /email/{id}/summary` (résumé d'un mail) — squelette fourni avec données factices, à remplacer par l'appel réel à `EmailManager` (IMAP + analyse LLM)
- **`/career`** : `GET /career` (liste des offres), `POST /career/{id}/cv` (génération de CV)
- **`/security`** : `GET /security/cameras` (liste), `GET /security/cameras/{id}` (détail)
- **`/health`** : ping simple pour vérifier que l'API tourne

À écrire (toi) — laissé volontairement de côté dans `routers/media.py`, endpoints posés mais levant `NotImplementedError` :

- [ ] `POST /media/netflix/play` — piloter la TV (Android TV / HDMI-CEC) puis lancer le titre demandé sur Netflix. Piste trouvée : deep link `netflix://title/{id}` envoyé via intent ADB (`adb shell am start -a android.intent.action.VIEW -d "netflix://title/{id}" -n com.netflix.ninja/.MainActivity`) — reste à résoudre le nom du film/série vers cet ID Netflix (pas d'API officielle, mapping externe à trouver) et prévoir un fallback si l'intent échoue (non documenté officiellement, peut casser après mise à jour de l'app). Détail ajouté dans `routers/media.py`.
- [ ] `GET /media/youtube/search` — interroger YouTube (API ou autre) et retourner une liste de résultats exploitable par le frontend

Ces deux-là dépendent de choix techniques (API YouTube officielle vs scraping, protocole exact pour piloter la TV) laissés à ton appréciation plutôt que devinés.


