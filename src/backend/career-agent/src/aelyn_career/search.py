"""Service de recherche d'offres généraliste pour AELYN.

Le moteur reste généraliste et ne se limite pas aux métiers de l'IA : il
cherche des offres de n'importe quel domaine, puis classe celles qui sont
relativement pertinentes par rapport à un profil ou à un mot-clé.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable

from aelyn_career.france_travail.offers import FTOffers
from aelyn_career.job_sources import deduplicate_offers, enrich_offer, normalize_contract_type, offer_identity_hash
from aelyn_career.offer_cache import OfferCache, default_offer_cache_path
from aelyn_career.source_adapters import available_source_adapters


def _offer_company(offer: dict) -> str:
    company = offer.get("entreprise") or offer.get("company") or {}
    if isinstance(company, dict):
        return str(company.get("nom") or company.get("name") or "")
    return str(company or "")


class JobSearchService:
    """Service unique qui masque la logique d'agrégation multi-source."""

    def __init__(self, offers_agent: FTOffers | None = None, cache: OfferCache | None = None):
        self.offers_agent = offers_agent or FTOffers()
        # Un seul fichier SQLite partagé avec les embeddings d'offres (cf.
        # `default_offer_cache_path`) : persiste d'une recherche à l'autre,
        # d'un redémarrage à l'autre - c'est tout le but (cf. `search`
        # ci-dessous, qui priorise les offres jamais vues plutôt que de
        # remontrer les mêmes à chaque appel sur les mêmes mots-clés).
        self.cache = cache or OfferCache(default_offer_cache_path())

    def search(
        self,
        keywords: str | None = None,
        contract_type: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Retourne une liste d'offres enrichies, dédupliquées, prêtes à être affichées."""
        desired = max(limit, 10)

        if self.offers_agent.access_token is None:
            self.offers_agent.connect()

        source_keywords = keywords or next(
            (
                item.strip()
                for item in re.split(r",|\bet\b|&", self.offers_agent.keywords, flags=re.IGNORECASE)
                if item.strip()
            ),
            None,
        )

        raw_offers, _ = self.offers_agent.search_offers(
            keywords=keywords,
            contract_type=contract_type,
            limit=max(desired, 20),
        )

        enriched: list[dict] = []
        for offer in raw_offers:
            enr = enrich_offer(offer, source="francetravail")
            origin = offer.get("origineOffre") or {}
            partners = origin.get("partenaires") or []
            partner_url = next(
                (partner.get("url") for partner in partners if partner.get("url")),
                None,
            )
            partner_name = next(
                (partner.get("nom") for partner in partners if partner.get("url")),
                None,
            )
            offer_url = (
                (offer.get("application") or {}).get("url")
                or offer.get("url")
                or offer.get("urlOffre")
                or offer.get("lien")
                or partner_url
                or origin.get("urlOrigine")
            )
            if offer_url:
                enr["url"] = offer_url
                enr["sources_seen"][0]["url"] = offer_url
                enr["application"] = {
                    **(offer.get("application") or {}),
                    "url": offer_url,
                    "method": (offer.get("application") or {}).get("method") or "site",
                }
            if partner_name:
                enr["application_source"] = partner_name
            app = enr.get("application") or {}
            if not app.get("url") and enr.get("url"):
                app = {"url": enr["url"], "method": "site"}
                enr["application"] = app
            enriched.append(enr)

        if source_keywords and os.getenv("AELYN_ENABLE_PUBLIC_JOB_APIS", "0").lower() in {"1", "true", "yes", "on"}:
            for adapter in available_source_adapters():
                try:
                    adapter_results = adapter.search(
                        keywords=source_keywords,
                        contract_type=contract_type,
                        limit=max(5, desired),
                    )
                except Exception:
                    continue
                for offer in adapter_results:
                    actual_contract = normalize_contract_type(
                        offer.get("contract_type") or offer.get("contract")
                    )
                    requested_contract = normalize_contract_type(contract_type)
                    if (
                        contract_type
                        and actual_contract != "UNKNOWN"
                        and actual_contract != requested_contract
                    ):
                        continue
                    source_name = str(offer.get("source") or adapter.name)
                    enriched.append(enrich_offer(offer, source=source_name))

        deduped = deduplicate_offers(enriched)
        ordered = sorted(
            deduped,
            key=lambda offer: (
                float(offer.get("ai_score", 0.0) if isinstance(offer.get("ai_score"), (int, float)) else 0.0),
                str(offer.get("dateCreation") or offer.get("posted_at") or ""),
            ),
            reverse=True,
        )

        # Priorise les offres jamais vues dans une recherche PASSÉE (pas
        # seulement dédupliquées au sein de cet appel, cf.
        # `deduplicate_offers` ci-dessus) : relancer la même recherche de
        # mots-clés plus tard ne doit pas remontrer sans arrêt les mêmes
        # offres comme si elles étaient neuves. Jamais un filtrage strict :
        # si pas assez d'offres neuves, on complète avec les déjà-vues
        # plutôt que de renvoyer moins de résultats que demandé.
        already_seen = self.cache.seen_hashes()
        for offer in ordered:
            offer["already_seen"] = offer_identity_hash(offer) in already_seen
        fresh = [offer for offer in ordered if not offer["already_seen"]]
        stale = [offer for offer in ordered if offer["already_seen"]]
        result = (fresh + stale)[:limit]

        for offer in result:
            self.cache.mark_seen(
                offer_identity_hash(offer),
                title=str(offer.get("intitule") or offer.get("title") or ""),
                company=_offer_company(offer),
                source=str(offer.get("source") or ""),
                url=str(offer.get("url") or ""),
            )
        self.cache.log_search(
            query=keywords or source_keywords,
            contract_type=contract_type,
            result_count=len(result),
            new_count=sum(1 for offer in result if not offer["already_seen"]),
        )
        return result


def normalize_filters(filters: Iterable[str] | None) -> list[str]:
    if not filters:
        return []
    return [f.strip().lower() for f in filters if f and f.strip()]
