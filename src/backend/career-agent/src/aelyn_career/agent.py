"""Agent carrière d'AELYN.

`run_command()` est le point d'entrée partagé par la CLI directe et
l'agent conversationnel, comme `aelyn_email.agent.run_command` pour le
mail : un seul endroit qui sait traduire un nom de commande en appel de
méthode et imprimer un résultat lisible par un humain.
"""

from __future__ import annotations

from aelyn_career.france_travail.offers import FTOffers
from aelyn_career.pipeline import find_best_matches


DEFAULT_OFFERS_LIMIT = 10


def run_command(
    command: str,
    *,
    offers_agent: FTOffers | None = None,
    mots_cles: str | None = None,
    contract_type: str | None = None,
    limit: int | None = None,
    **_: object,
) -> tuple[int, list[dict]]:
    if command == "chercher_offres":
        agent = offers_agent or FTOffers()
        if agent.access_token is None:
            agent.connect()

        # `find_best_matches` (pas `agent.search_offers` seul) : la
        # recherche brute ne scorait jamais rien contre le profil malgré
        # tout le pipeline déjà construit pour ça (LLM structurer,
        # embeddings BM25/cosinus, cache par hash) — resté orphelin,
        # jamais appelé nulle part avant ce correctif. Chaque offre
        # renvoyée porte désormais un vrai `score`, pas `None`/absent.
        #
        # `top_n`/`max_offers` suivent `limit` (demandé explicitement par
        # l'utilisateur, ex. "cherche 20 offres") plutôt qu'un défaut figé
        # à 10 : sans `max_offers` aligné, demander 30 offres ne renvoyait
        # jamais plus que les 20 premières structurées par défaut, même si
        # France Travail en avait bien plus. Si moins d'offres existent
        # que `limit`, `find_best_matches` renvoie simplement ce qu'il
        # trouve (`resultats[:top_n]` sur une liste plus courte), jamais
        # une erreur.
        top_n = limit or DEFAULT_OFFERS_LIMIT
        offres = find_best_matches(
            contract_type=contract_type,
            keywords=mots_cles,
            ft=agent,
            top_n=top_n,
            max_offers=max(20, top_n),
        )
        if not offres:
            print("Aucune offre trouvée.")
            return 0, []

        print(f"{len(offres)} offre(s) trouvée(s), classées par pertinence avec ton profil :")
        for offre in offres:
            entreprise = offre.get("entreprise", {}).get("nom", "?")
            lieu = offre.get("lieuTravail", {}).get("libelle", "?")
            contrat = offre.get("typeContrat", "?")
            pct = round(offre["score"] * 100)
            print(f"- [{pct}%] {offre.get('intitule')} | {entreprise} | {lieu} | {contrat}")
        return 0, offres

    return 1, []
