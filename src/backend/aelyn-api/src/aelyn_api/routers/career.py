"""Expose `FTOffers`/`ApplicationWriter` (career-agent) à l'API."""

from __future__ import annotations

import json
import shutil

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from aelyn.core.llm import LLMError
from aelyn_career.application_writer import ApplicationWriter, offer_text
from aelyn_career.france_travail.offers import FTOffers
from aelyn_career.models import CVContent, CanonicalJobOffer, JobSearchResponse
from aelyn_career.pipeline import find_best_matches
from aelyn_career.search import JobSearchService
from aelyn_career.profil_manager import (
    load_profil_json,
    profil_path,
    validate_profil_structure,
)

from aelyn_api.deps import (
    cache_offers,
    get_application_writer,
    get_cached_offer,
    get_conversational_agent,
    get_offers_agent,
)
from aelyn_api.security import require_settings_token

router = APIRouter(prefix="/career", tags=["career"])


class OfferOut(BaseModel):
    id: str
    intitule: str
    entreprise: str | None = None
    lieu: str | None = None
    contrat: str | None = None
    date_creation: str | None = None
    date_publication: str | None = None
    date_limite: str | None = None
    deadline: str | None = None
    score: float | None = None
    url: str | None = None
    description: str | None = None


@router.get("/search", response_model=JobSearchResponse)
def search_general_offers(
    query: str | None = None,
    contract_type: str | None = None,
    limit: int = 10,
    page: int = 1,
    offers_agent: FTOffers = Depends(get_offers_agent),
) -> JobSearchResponse:
    """Recherche générale d'offres, pas seulement IA, avec déduplication,
    provenance et informations utiles pour postuler.
    """
    service = JobSearchService(offers_agent)
    try:
        offers = service.search(keywords=query, contract_type=contract_type, limit=limit)
    except Exception as exc:
        raise HTTPException(502, f"Recherche générale d'offres impossible : {exc}") from exc

    results = []
    for offer in offers:
        company = offer.get("company") or offer.get("entreprise") or {}
        if isinstance(company, dict):
            company_name = company.get("name") or company.get("nom")
        else:
            company_name = company
        location = offer.get("location") or offer.get("lieuTravail") or {}
        if isinstance(location, dict):
            city = location.get("city") or location.get("libelle") or location.get("raw")
            remote = location.get("remote")
        else:
            city = location
            remote = None
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
        application = offer.get("application") or {}
        apply_url = (
            application.get("url")
            or offer.get("url")
            or offer.get("urlOffre")
            or offer.get("lien")
            or partner_url
            or origin.get("urlOrigine")
        )
        publication = offer.get("dateCreation") or offer.get("posted_at")
        deadline = (
            offer.get("dateLimiteDePotentiel")
            or offer.get("dateLimite")
            or offer.get("dateFin")
            or offer.get("expires_at")
            or offer.get("deadline")
            or application.get("deadline")
        )
        results.append(
            CanonicalJobOffer(
                id=str(offer.get("id") or offer.get("external_id") or "unknown"),
                source=str(offer.get("source") or "unknown"),
                external_id=offer.get("external_id"),
                url=apply_url,
                title=offer.get("title") or offer.get("intitule"),
                company={"name": company_name},
                location={
                    "city": city,
                    "raw": city,
                    "remote": offer.get("telework") or offer.get("remote") or remote,
                },
                contract_type=str(offer.get("contract_type") or offer.get("typeContrat") or "UNKNOWN"),
                telework=offer.get("telework") or offer.get("remote"),
                salary=offer.get("salary"),
                posted_at=publication,
                expires_at=deadline,
                deadline=deadline,
                description=offer.get("description"),
                domain=offer.get("domain", "general"),
                is_ai_related=bool(offer.get("is_ai_related", False)),
                ai_score=offer.get("ai_score"),
                skills=offer.get("skills", []),
                tags=offer.get("tags", []),
                confidence=offer.get("confidence"),
                application={
                    **application,
                    "url": apply_url,
                    "source": offer.get("application_source") or partner_name,
                    "method": application.get("method") or ("site" if apply_url else None),
                    "deadline": deadline,
                } if application or apply_url or deadline else None,
                deduplicated=bool(offer.get("deduplicated", False)),
                duplicate_count=int(offer.get("duplicate_count", 1) or 1),
                sources_seen=[{"source": s.get("source", "unknown"), "url": s.get("url"), "seen_at": s.get("seen_at")} for s in offer.get("sources_seen", [])],
            )
        )

    return JobSearchResponse(
        total=len(results),
        page=page,
        per_page=limit,
        results=results,
        filters={"contract_type": [], "domains": []},
    )


@router.get("", response_model=list[OfferOut])
def search_offers(
    mots_cles: str | None = None,
    contract_type: str | None = None,
    limit: int | None = None,
    offers_agent: FTOffers = Depends(get_offers_agent),
) -> list[OfferOut]:
    if offers_agent.access_token is None:
        try:
            offers_agent.connect()
        except Exception as exc:
            raise HTTPException(502, f"France Travail injoignable : {exc}") from exc

    try:
        # `find_best_matches` (pas `offers_agent.search_offers` seul) :
        # même correctif que `aelyn_career.agent.run_command`, pour que
        # GET /career renvoie un vrai `score` (BM25/cosinus contre le
        # profil) au lieu de la liste brute non classée, jamais scorée
        # auparavant malgré "Score" déjà affiché côté frontend.
        #
        # `limit` (query param, ex. ?limit=30) suit `top_n`/`max_offers` :
        # sans aligner `max_offers`, demander plus que les 20 offres
        # structurées par défaut ne changeait rien au résultat.
        top_n = limit or 10
        offres = find_best_matches(
            contract_type=contract_type,
            keywords=mots_cles,
            ft=offers_agent,
            top_n=top_n,
            max_offers=max(20, top_n),
        )
    except Exception as exc:
        raise HTTPException(502, f"Recherche France Travail impossible : {exc}") from exc

    # Nécessaire pour POST /career/{id}/cv juste après (cf. deps.py) : sans
    # ce cache, le client devrait renvoyer l'offre complète lui-même.
    cache_offers(offres)

    return [
        OfferOut(
            id=str(offre.get("id")),
            intitule=offre.get("intitule") or offre.get("title") or "?",
            entreprise=(
                (offre.get("entreprise") or {}).get("nom")
                if isinstance(offre.get("entreprise"), dict)
                else offre.get("company") or offre.get("entreprise")
            ),
            lieu=(
                (offre.get("lieuTravail") or {}).get("libelle")
                if isinstance(offre.get("lieuTravail"), dict)
                else offre.get("location") or offre.get("lieu")
            ),
            contrat=offre.get("typeContrat") or offre.get("contract_type"),
            date_creation=offre.get("dateCreation") or offre.get("date_publication"),
            date_publication=offre.get("dateCreation") or offre.get("date_publication"),
            date_limite=(
                offre.get("dateLimiteDePotentiel")
                or offre.get("dateLimite")
                or offre.get("dateFin")
                or offre.get("deadline")
            ),
            deadline=(
                offre.get("dateLimiteDePotentiel")
                or offre.get("dateLimite")
                or offre.get("dateFin")
                or offre.get("deadline")
            ),
            score=offre.get("score"),
            url=(
                (offre.get("application") or {}).get("url")
                or offre.get("url")
                or offre.get("urlOffre")
                or offre.get("lien")
                or next(
                    (
                        partner.get("url")
                        for partner in ((offre.get("origineOffre") or {}).get("partenaires") or [])
                        if isinstance(partner, dict) and partner.get("url")
                    ),
                    None,
                )
                or ((offre.get("origineOffre") or {}).get("urlOrigine"))
            ),
            description=(offre.get("description") or "")[:2000],
        )
        for offre in offres
    ]


@router.post("/{offer_id}/cv", response_model=CVContent)
def generate_cv(
    offer_id: str,
    writer: ApplicationWriter = Depends(get_application_writer),
) -> CVContent:
    offre = get_cached_offer(offer_id)
    if offre is None:
        raise HTTPException(
            404,
            f"Offre {offer_id} inconnue - appelle GET /career d'abord pour la charger.",
        )
    try:
        return writer.draft_cv(offer_text(offre))
    except LLMError as exc:
        raise HTTPException(502, f"LLM indisponible : {exc}") from exc


@router.get("/profile")
def get_profile() -> dict:
    """Contenu BRUT actuel de `profil.json` (relu depuis le disque à
    chaque appel, pas une copie en mémoire potentiellement périmée) :
    le frontend peut l'afficher/éditer comme du JSON texte."""
    return load_profil_json()


@router.put("/profile", dependencies=[Depends(require_settings_token)])
def put_profile(body: dict) -> dict:
    """Remplace `profil.json` par `body`, validé d'abord (cf.
    `validate_profil_structure`) : un JSON valide mais structurellement
    incomplet (ex. une expérience sans 'company') casserait sinon TOUTE
    génération de CV/lettre de motivation plus tard, loin de cette
    requête, avec une erreur bien moins claire qu'un 422 ici et maintenant.

    Sauvegarde `profil.json.bak` (l'ANCIEN contenu, écrasé à chaque
    nouvelle écriture réussie - une seule génération de secours, pas un
    historique complet) AVANT d'écrire le nouveau contenu : assurance bon
    marché contre une édition malheureuse, sans la complexité d'un vrai
    versionnage.

    Recharge ENSUITE les `ApplicationWriter` déjà construits (singleton
    `aelyn_api.deps.get_application_writer` ET celui, séparé, de
    `ConversationalAgent` utilisé par `/chat/*`) pour que CV/lettre de
    motivation reflètent le nouveau profil dès la PROCHAINE génération,
    sans redémarrage de l'API.
    """
    problems = validate_profil_structure(body)
    if problems:
        # `loc` générique (le chemin précis est déjà dans chaque `msg`,
        # ex. "profile.experience[0] : champ 'company' manquant") : pas
        # de structure JSON Schema fine à reconstruire côté chemin, le
        # texte suffit pour qu'un humain corrige son édition.
        raise HTTPException(
            status_code=422,
            detail=[{"loc": ["body"], "msg": p, "type": "value_error.profile_structure"} for p in problems],
        )

    shutil.copyfile(profil_path, f"{profil_path}.bak")
    with open(profil_path, "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False, indent=2)

    get_application_writer().reload_profile()
    get_conversational_agent().application_writer.reload_profile()

    return {"status": "ok", "backup": f"{profil_path}.bak"}
