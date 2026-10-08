"""Agent carrière d'AELYN.

`run_command()` est le point d'entrée partagé par la CLI directe et
l'agent conversationnel, comme `aelyn_email.agent.run_command` pour le
mail : un seul endroit qui sait traduire un nom de commande en appel de
méthode et imprimer un résultat lisible par un humain.
"""

from __future__ import annotations

from datetime import datetime, timezone

from aelyn_career.france_travail.offers import FTOffers
from aelyn_career.pipeline import find_best_matches


DEFAULT_OFFERS_LIMIT = 10

# Noms d'affichage propres pour les sources d'offres : les adaptateurs
# (source_adapters.py) stockent l'identifiant technique en minuscules
# ("arbeitnow", "remoteok"...), jamais destiné à l'utilisateur final tel
# quel.
_SOURCE_LABELS = {
    "arbeitnow": "Arbeitnow",
    "remoteok": "RemoteOK",
    "remotive": "Remotive",
    "jooble": "Jooble",
    "adzuna": "Adzuna",
    "reed": "Reed",
    "careerjet": "Careerjet",
}


def _source_label(source: str) -> str:
    return _SOURCE_LABELS.get(source.lower(), source)


def _format_posted_date(value: object) -> str | None:
    """Convertit une date de publication, de format variable selon la
    source (epoch Arbeitnow, ISO 8601 ailleurs), en date lisible
    JJ/MM/AAAA. `None` si la valeur est absente ou illisible, plutôt que
    d'afficher un timestamp brut ou une chaîne incompréhensible."""
    if value is None or value == "":
        return None
    text = str(value).strip()
    if text.isdigit() and len(text) >= 9:
        try:
            return datetime.fromtimestamp(int(text), tz=timezone.utc).strftime("%d/%m/%Y")
        except (ValueError, OSError, OverflowError):
            return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%d/%m/%Y")
    except ValueError:
        return None


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
            criteria = f" pour « {mots_cles} »" if mots_cles else ""
            print(f"Aucune offre trouvée{criteria}.")
            return 0, []

        requested = f" (maximum demandé : {limit})" if limit is not None else ""
        print(
            f"{len(offres)} offre(s) trouvée(s){requested}, "
            "classées par pertinence avec ton profil :"
        )
        for offre in offres:
            company = offre.get("entreprise") or offre.get("company") or {}
            entreprise = (company.get("nom") or company.get("name")) if isinstance(company, dict) else company
            location = offre.get("lieuTravail") or offre.get("location") or offre.get("lieu") or {}
            lieu = (location.get("libelle") or location.get("city")) if isinstance(location, dict) else location
            contrat = offre.get("typeContrat") or offre.get("contract_type") or "?"
            contrat_part = f" | {contrat}" if contrat not in ("?", "UNKNOWN") else ""
            pct = round(offre["score"] * 100)
            titre = offre.get("intitule") or offre.get("title") or "Offre sans intitulé"
            source = _source_label(offre.get("source") or "France Travail")
            publication = _format_posted_date(offre.get("dateCreation") or offre.get("posted_at"))
            date_part = f" | publiée le {publication}" if publication else ""
            print(f"- [{pct}%] {titre} | {entreprise or '?'} | {lieu or '?'}{contrat_part} | {source}{date_part}")
        return 0, offres

    return 1, []
