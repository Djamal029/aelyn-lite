"""Modèles du domaine "conversation"."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Intent(BaseModel):
    """Ce que le LLM (ou le fast router) doit produire pour UNE phrase libre."""

    commande: Literal[
        "verifier",
        "triage",
        "valider",
        "rejeter",
        "rapport",
        "chercher_offres",
        "media",
        "camera",
        "inconnu",
    ]
    action_id: int | None = None
    limit: int | None = None
    hours: int | None = None
    mots_cles: str | None = None
    contract_type: Literal["cdi", "cdd", "alternance", "stage"] | None = None
    media_action: (
        Literal[
            "netflix",
            "youtube",
            "tv_power",
            "home",
            "back",
            "up",
            "down",
            "left",
            "right",
            "select",
            "play_pause",
            "next",
            "previous",
            "volume_up",
            "volume_down",
            "mute",
            "search_youtube",
            "search_netflix",
        ]
        | None
    ) = None
    media_query: str | None = None
    media_amount: int | None = None
    camera_name: Literal["entree", "salon"] | None = None
    reformulation: str


class TurnResult(BaseModel):
    """Résultat d'UN tour de conversation, indépendant de la présentation.

    `text` est TOUJOURS la réponse en langage naturel : ce que le CLI
    afficherait/parlerait via `_say`/`_say_stream`. `result_type`/`results`
    ne sont renseignés QUE lorsque `text` résume une LISTE structurée
    (offres, mails) qu'un appelant pourrait vouloir afficher comme un
    vrai tableau plutôt qu'une phrase, ex. le frontend web pour
    "cherche des offres" puis "affiche les offres".

    Utilisé par `ConversationalAgent.handle_message()` (point d'entrée
    non interactif, cf. `POST /chat/message` côté aelyn-api), PAS par
    le CLI, qui reste piloté par `_handle_phrase()`/`_say` directement.
    Les deux partagent la MÊME logique de routage (`_dispatch_phrase`) ;
    seule la présentation diffère.
    """

    text: str
    result_type: Literal["offers", "mails"] | None = None
    results: list[dict] | None = None
