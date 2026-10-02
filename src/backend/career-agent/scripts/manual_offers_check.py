"""Script manuel : appelle vraiment l'API France Travail pour voir ce que
FTOffers.connect() et FTOffers.search_offers() retournent concrètement.

Contrairement à tests/test_offers.py (mocké, pas d'appel réseau), ce script
utilise les vrais identifiants FRANCE_TRAVAIL_CLIENT_ID/SECRET du .env.

Usage :
    cd career-agent
    uv run python scripts/manual_offers_check.py [cdi|cdd|alternance|stage]
"""

import sys

from aelyn_career.france_travail.offers import FTOffers


def main() -> int:
    contract_type = sys.argv[1] if len(sys.argv) > 1 else None

    ft = FTOffers()

    print(f"Mots-clés  : {ft.keywords}")
    print(f"Départements : {ft.departments}")
    print(f"Type de contrat : {contract_type or '(tous)'}")
    print()

    try:
        ft.connect()
    except Exception as exc:
        print(f"Échec de connexion : {exc}", file=sys.stderr)
        return 1

    print(f"Connecté. access_token = {ft.access_token[:12]}...")
    print()

    try:
        offres, possible_filters = ft.search_offers(contract_type=contract_type)
    except Exception as exc:
        print(f"Échec de la recherche : {exc}", file=sys.stderr)
        return 1

    print(f"{len(offres)} offre(s) trouvée(s), du plus récent au plus ancien.\n")
    for offre in offres:
        intitule = offre.get("intitule", "?")
        entreprise = offre.get("entreprise", {}).get("nom", "?")
        lieu = offre.get("lieuTravail", {}).get("libelle", "?")
        date = offre.get("dateCreation", "?")
        contrat = offre.get("typeContratLibelle", "?")
        url = offre.get("origineOffre", {}).get("urlOrigine", "?")
        description = offre.get("description", "").strip()

        print(f"- [{date[:10]}] {intitule} | {entreprise} | {lieu} | {contrat}")
        print(f"    {url}")
        if description:
            print(f"    {description}")
        print()

    print("Filtres possibles renvoyés par l'API :")
    print(possible_filters)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
