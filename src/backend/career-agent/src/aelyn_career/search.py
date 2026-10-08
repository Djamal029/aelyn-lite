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
from aelyn_career.job_sources import deduplicate_offers, enrich_offer, normalize_contract_type
from aelyn_career.source_adapters import available_source_adapters


class JobSearchService:
    """Service unique qui masque la logique d'agrégation multi-source."""

    def __init__(self, offers_agent: FTOffers | None = None):
        self.offers_agent = offers_agent or FTOffers()

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
        return ordered[:limit]


def normalize_filters(filters: Iterable[str] | None) -> list[str]:
    if not filters:
        return []
    return [f.strip().lower() for f in filters if f and f.strip()]
