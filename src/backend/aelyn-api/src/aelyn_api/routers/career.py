"""Expose `FTOffers`/`ApplicationWriter` (career-agent) à l'API."""

from __future__ import annotations

import json
import shutil

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from aelyn.core.llm import LLMError
from aelyn_career.application_writer import ApplicationWriter, offer_text
from aelyn_career.france_travail.offers import FTOffers
from aelyn_career.models import CVContent
from aelyn_career.pipeline import find_best_matches
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
    score: float | None = None


@router.get("", response_model=list[OfferOut])
def search_offers(
    mots_cles: str | None = None,
    contract_type: str | None = None,
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
        offres = find_best_matches(contract_type=contract_type, keywords=mots_cles, ft=offers_agent)
    except Exception as exc:
        raise HTTPException(502, f"Recherche France Travail impossible : {exc}") from exc

    # Nécessaire pour POST /career/{id}/cv juste après (cf. deps.py) : sans
    # ce cache, le client devrait renvoyer l'offre complète lui-même.
    cache_offers(offres)

    return [
        OfferOut(
            id=str(offre.get("id")),
            intitule=offre.get("intitule", "?"),
            entreprise=offre.get("entreprise", {}).get("nom"),
            lieu=offre.get("lieuTravail", {}).get("libelle"),
            contrat=offre.get("typeContrat"),
            date_creation=offre.get("dateCreation"),
            score=offre.get("score"),
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
