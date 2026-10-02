"""Pipeline bout-en-bout : cherche des offres, les structure via le LLM
(avec cache), les score contre le profil (BM25 + cosinus), et retourne les
meilleures correspondances.

Chaque brique existe et est testée séparément (`FTOffers`,
`LLMOfferStructurer`, `TextEmbbeder`, `ProfilManager`) ; ce module se
contente de les enchaîner, aucune nouvelle logique métier.
"""

from __future__ import annotations

import os

import dotenv
import numpy as np

from aelyn_career.embbeder import TextEmbbeder, niveau_adequacy
from aelyn_career.france_travail.offers import FTOffers
from aelyn_career.llm_structurer import LLMOfferStructurer
from aelyn_career.profil_manager import ProfilManager, chunk_label

dotenv.load_dotenv()
TOP_K_CHUNKS = int(os.getenv("TOP_K_CHUNKS", "5"))


def _offer_text(offre: dict) -> str:
    """Représentation texte d'une offre, envoyée au LLM pour la structurer."""
    return f"{offre.get('intitule', '')}\n{offre.get('description', '')}"


def find_best_matches(
    contract_type: str | None = None,
    keywords: str | None = None,
    top_n: int = 10,
    max_offers: int | None = 20,
    ft: FTOffers | None = None,
    structurer: LLMOfferStructurer | None = None,
    embedder: TextEmbbeder | None = None,
    profil_manager: ProfilManager | None = None,
) -> list[dict]:
    """Cherche des offres, les structure, les score contre le profil.

    `keywords` : mots-clés de recherche France Travail (cf.
    `FTOffers.search_offers`), `None` pour les mots-clés par défaut de
    l'agent (profil `KEYWORDS`). Avant ce paramètre, cette fonction ne
    pouvait pas servir une recherche ponctuelle ("cherche des offres de
    data scientist") : seul l'appel sans mot-clé était possible.

    `max_offers` limite le nombre d'offres réellement structurées/scorées
    (une offre non encore vue coûte un appel LLM), mettre `None` pour
    traiter toutes les offres trouvées, une fois le cache bien rempli.

    Retourne les `top_n` offres les mieux classées, chacune enrichie de :
    - `structured` : compétences/niveau extraits par le LLM ;
    - `score` : moyenne des `TOP_K_CHUNKS` meilleurs chunks du profil pour
      cette offre (pas la moyenne de tout le profil, qui noierait le signal
      dans les chunks sans rapport) ;
    - `raisons` : les éléments du profil (traduits en langage naturel via
      `chunk_label`) qui ont fait matcher cette offre, pas juste un score,
      de quoi expliquer le choix à l'utilisateur.
    """
    ft = ft or FTOffers()
    structurer = structurer or LLMOfferStructurer()
    embedder = embedder or TextEmbbeder()
    profil_manager = profil_manager or ProfilManager()

    if ft.access_token is None:
        ft.connect()
    offres, _ = ft.search_offers(contract_type=contract_type, keywords=keywords)
    if max_offers is not None:
        offres = offres[:max_offers]

    chunks = profil_manager.parse_profile()

    resultats = []
    for offre in offres:
        offre_structuree = structurer.structure_offers(offre["id"], _offer_text(offre))
        scores = np.asarray(embedder.final_score(chunks, offre_structuree))

        top_indices = np.argsort(scores)[::-1][:TOP_K_CHUNKS]
        raisons = [chunk_label(chunks[i]) for i in top_indices]

        # Le match mots-clés/sémantique seul ne dit rien de l'accessibilité
        # réelle de l'offre : une offre "postdoc" peut matcher parfaitement
        # sur les compétences sans être obtenable pour un profil junior (ou
        # inversement pour un profil senior visant du "stage"). Le facteur
        # s'adapte à CANDIDATE_LEVEL, pas seulement au profil de l'auteur.
        adequacy = niveau_adequacy(offre_structuree["niveau_requis"])

        resultats.append(
            {
                **offre,
                "structured": offre_structuree,
                "score": float(np.mean(scores[top_indices])) * adequacy,
                "niveau_adequacy": adequacy,
                "raisons": raisons,
            }
        )

    resultats.sort(key=lambda o: o["score"], reverse=True)
    return resultats[:top_n]
