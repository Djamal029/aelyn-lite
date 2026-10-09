"""Dépendances partagées de l'API : mêmes principes que
`ConversationalAgent.__init__` (cf. aelyn_conversation/agent.py) : un
seul client par ressource coûteuse (LLM, jeton France Travail,
event loop TV) réutilisé entre requêtes plutôt que recréé à chaque
appel. `lru_cache` sur des fonctions sans argument = un singleton créé
paresseusement, à la première requête qui en a besoin.
"""

from __future__ import annotations

from functools import lru_cache

from aelyn.core.chat_history import ChatHistory
from aelyn.core.config import settings
from aelyn.core.journal import Journal
from aelyn.core.llm import LLMClient
from aelyn_career.application_writer import ApplicationWriter
from aelyn_career.applications import ApplicationsStore
from aelyn_career.france_travail.offers import FTOffers
from aelyn_conversation.agent import ConversationalAgent
from aelyn_email.agent import EmailAgent
from aelyn_media.agent import MediaController


@lru_cache
def get_llm() -> LLMClient:
    return LLMClient()


@lru_cache
def get_email_agent() -> EmailAgent:
    return EmailAgent()


@lru_cache
def get_offers_agent() -> FTOffers:
    return FTOffers()


@lru_cache
def get_application_writer() -> ApplicationWriter:
    return ApplicationWriter()


@lru_cache
def get_media_controller() -> MediaController:
    # `MediaController()` démarre déjà son event loop dédié sans se
    # connecter à la TV (connexion paresseuse à son premier `dispatch()`,
    # cf. media-agent/src/aelyn_media/agent.py), un seul par process API.
    return MediaController()


@lru_cache
def get_chat_history() -> ChatHistory:
    return ChatHistory(settings.chat_history_path)


@lru_cache
def get_journal() -> Journal:
    # Même fichier SQLite que `EmailAgent`/`LLMOfferStructurer` (tous deux
    # construisent leur propre `Journal(settings.journal_path)` sans
    # passer par ce singleton) : une seule table `actions`, lue ici en
    # lecture seule pour GET /activity.
    return Journal(settings.journal_path)


@lru_cache
def get_applications_store() -> ApplicationsStore:
    return ApplicationsStore(settings.applications_path)


@lru_cache
def get_conversational_agent() -> ConversationalAgent:
    """Instance UNIQUE pour toute la durée de vie du process API : un
    assistant personnel mono-utilisateur n'a pas besoin d'isolement par
    session (cf. `POST /chat/message`, qui route désormais par ici plutôt
    que par un simple appel LLM sans mémoire ni intentions).

    `voice=False` : l'API ne doit JAMAIS tenter de parler sur les
    haut-parleurs de la machine qui l'héberge (souvent pas la même que
    celle de la personne qui utilise le frontend web), cf. `POST /tts`,
    qui laisse le NAVIGATEUR jouer le son à la place.
    """
    return ConversationalAgent(voice=False)


# Cache des dernières offres cherchées, par id France Travail, nécessaire
# pour POST /career/{id}/cv (générer un CV pour un id vu via un GET
# /career précédent) sans redemander l'offre complète au client. Même
# principe que `ConversationalAgent._last_offers`/`_find_offer`, mais un
# simple dict de process ici : une recherche d'offres n'a pas besoin de
# survivre à un redémarrage de l'API, contrairement à l'historique de chat.
_offers_cache: dict[str, dict] = {}


def cache_offers(offres: list[dict]) -> None:
    for offre in offres:
        offer_id = offre.get("id")
        if offer_id:
            _offers_cache[str(offer_id)] = offre


def get_cached_offer(offer_id: str) -> dict | None:
    return _offers_cache.get(offer_id)
