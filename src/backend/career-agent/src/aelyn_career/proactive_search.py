"""Recherche proactive d'offres : tourne en arrière-plan (cf. lifespan de
`aelyn_api.main`), sans qu'on ait besoin de demander. Compare chaque
recherche aux offres déjà vues (`SeenOffers`) et ne journalise QUE les
vraies nouveautés, pour que l'utilisateur les découvre via le flux
Activité déjà existant (le frontend poll `/activity` toutes les 15s,
cf. `useActivityEntries.ts`) sans ajouter ni endpoint, ni websocket, ni
notification répétée pour la même offre d'un cycle à l'autre.
"""

from __future__ import annotations

import asyncio
import logging

from aelyn.core.config import settings
from aelyn.core.journal import ActionStatus, Journal
from aelyn.core.seen_offers import SeenOffers
from aelyn_career.pipeline import find_best_matches

logger = logging.getLogger(__name__)
_AGENT_NAME = "career"
_ACTION_NAME = "recherche_proactive"
# Intervalle de vérification du réglage `proactive_search_enabled`/de
# l'horloge : COURT et peu coûteux (juste une comparaison, aucun appel
# réseau/LLM), pour qu'activer la recherche proactive depuis `/settings`
# prenne effet rapidement plutôt que d'attendre jusqu'à la fin d'un cycle
# déjà en cours (potentiellement long, cf. `proactive_search_interval_minutes`).
_TICK_SECONDS = 60


def _offer_label(offre: dict) -> tuple[str, str | None]:
    titre = offre.get("intitule") or offre.get("title") or "offre"
    entreprise = offre.get("entreprise")
    nom_entreprise = (
        entreprise.get("nom") if isinstance(entreprise, dict) else entreprise
    ) or offre.get("company")
    return titre, nom_entreprise


def run_proactive_search_once(
    *, seen_offers: SeenOffers | None = None, journal: Journal | None = None
) -> int:
    """Une itération : cherche, filtre les offres jamais vues, journalise
    chacune. Renvoie le nombre de nouvelles offres (0 en cas d'erreur
    réseau/LLM, jamais levée plus haut : un cycle raté ne doit pas
    arrêter la boucle de fond, le prochain cycle réessaiera)."""
    try:
        offres = find_best_matches(top_n=10, max_offers=20)
    except Exception:
        logger.warning(
            "Recherche proactive échouée, nouvelle tentative au prochain cycle",
            exc_info=True,
        )
        return 0

    seen = seen_offers or SeenOffers(settings.seen_offers_path)
    ids = [str(offre["id"]) for offre in offres if offre.get("id") is not None]
    new_ids = set(seen.filter_new(ids))
    nouvelles = [offre for offre in offres if str(offre.get("id")) in new_ids]

    journal = journal or Journal(settings.journal_path)
    for offre in nouvelles:
        titre, nom_entreprise = _offer_label(offre)
        resume = f"Nouvelle offre repérée en veille : {titre}"
        if nom_entreprise:
            resume += f" chez {nom_entreprise}"
        journal.record(
            agent=_AGENT_NAME,
            action=_ACTION_NAME,
            summary=resume,
            status=ActionStatus.EXECUTED,
            target=str(offre.get("id")),
            payload={"score": offre.get("score"), "url": offre.get("url")},
        )
    return len(nouvelles)


async def proactive_search_loop() -> None:
    """Boucle de fond, démarrée au lifespan de l'API (`aelyn_api.main`).
    Vérifie le réglage/l'horloge toutes les `_TICK_SECONDS`, mais ne
    déclenche une vraie recherche (coûteuse : réseau + LLM) qu'une fois
    `proactive_search_interval_minutes` écoulées. `asyncio.to_thread` :
    `find_best_matches` est bloquant (requêtes HTTP synchrones, appels
    Ollama synchrones), jamais appelé directement dans la boucle
    événementielle au risque de geler toute l'API pendant une recherche.

    `last_run` démarre à `None` (pas `0.0`) : avec `loop.time()` (horloge
    monotone depuis un repère arbitraire, PAS depuis l'epoch), un `0.0`
    initial aurait fait attendre un `interval_seconds` ENTIER avant la
    toute première recherche, même si la recherche proactive est activée
    dès le démarrage de l'API, jusqu'à 24h d'attente pour rien avec
    l'intervalle maximal. `None` déclenche la recherche dès le premier
    tick où le réglage est actif."""
    last_run: float | None = None
    loop = asyncio.get_running_loop()
    while True:
        await asyncio.sleep(_TICK_SECONDS)
        if not settings.proactive_search_enabled:
            continue
        interval_seconds = max(1, settings.proactive_search_interval_minutes) * 60
        now = loop.time()
        if last_run is not None and now - last_run < interval_seconds:
            continue
        last_run = now
        await asyncio.to_thread(run_proactive_search_once)
