"""Historique de conversation + discussion en langage naturel.

`GET /chat/history` lit la même base SQLite que `ConversationalAgent`
(cf. `aelyn.core.chat_history`, écrite au fil de l'eau par
`ConversationalAgent._remember()`), le frontend web voit donc un
historique qui a pu commencer dans le CLI et continuer ici, et
réciproquement.

`POST /chat/message` route désormais par `ConversationalAgent.handle_message()`
(cf. aelyn_conversation/agent.py), le MÊME routage que le CLI (fast
router, LLM `SYSTEM_INTENT`, résolution de référence, follow-ups comme
"affiche les offres" après "cherche des offres"), PAS un simple appel
LLM sans mémoire ni intentions comme dans une version précédente de ce
fichier. CLI et API partagent la même logique de décision ; seule la
présentation diffère (cf. le docstring de `handle_message`).

`POST /chat/message/stream` : variante en flux (Server-Sent Events) du
même routage, via `ConversationalAgent.handle_message_stream()`. Bug
réel remonté en usage : une réponse lente (rechargement de modèle Ollama
forcé par la contention VRAM, PLUS le temps de génération) pouvait
dépasser le timeout du client AVANT que `/chat/message` (bloquant) ne
renvoie quoi que ce soit. Gardé EN PLUS de `/chat/message` (pas à sa
place) : un appelant simple (script, test) qui n'a pas besoin de flux
garde un endpoint classique à appeler d'un bloc.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from aelyn.core.chat_history import ChatHistory
from aelyn_conversation.agent import ConversationalAgent, _Heartbeat
from aelyn_conversation.models import TurnResult

from aelyn_api.deps import cache_offers, get_chat_history, get_conversational_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessageOut(BaseModel):
    id: int
    ts: str
    role: str
    content: str


class ChatMessageIn(BaseModel):
    message: str


class ChatReplyOut(BaseModel):
    text: str
    # "offers" | "mails" | None : renseigné quand `text` résume une LISTE
    # structurée plutôt qu'une simple phrase (ex. "cherche des offres"
    # puis "affiche les offres" renvoie la liste, pas juste "6 offres
    # trouvées"). Le frontend peut alors rendre un vrai tableau à partir
    # de `results` au lieu d'un texte brut.
    result_type: str | None = None
    results: list[dict] | None = None


@router.get("/history", response_model=list[ChatMessageOut])
def get_history(
    limit: int = 50,
    before_id: int | None = None,
    history: ChatHistory = Depends(get_chat_history),
) -> list[ChatMessageOut]:
    return [
        ChatMessageOut(id=m.id, ts=m.ts.isoformat(), role=m.role, content=m.content)
        for m in history.recent(limit, before_id=before_id)
    ]


@router.post("/message", response_model=ChatReplyOut)
def send_message(
    body: ChatMessageIn,
    agent: ConversationalAgent = Depends(get_conversational_agent),
) -> ChatReplyOut:
    """Traite `body.message` exactement comme le ferait `aelyn chat` au
    clavier : mêmes intentions, même résolution "cette offre"/"les
    offres", mêmes garde-fous (une commande qui modifie un état comme
    valider/rejeter n'est jamais exécutée depuis ce endpoint, cf.
    `ConversationalAgent._dispatch_phrase(confirm=False)` : le texte
    renvoyé l'explique plutôt que de bloquer sur une confirmation qui ne
    peut pas venir d'un appel HTTP sans terminal en face).

    N'importe quelle exception d'agent (LLM, IMAP, France Travail...) est
    volontairement laissée remonter en 500 par FastAPI plutôt que
    mappée ici un par un : `ConversationalAgent` avale déjà ses propres
    erreurs attendues (LLMError, MailboxError...) et les transforme en
    texte de réponse normal (cf. ses `_try_*`/`_run_command`) ; une
    exception qui s'échappe malgré tout est un bug réel, pas un cas
    attendu à absorber silencieusement ici.
    """
    result = agent.handle_message(body.message)
    # Sans ça, `POST /career/{id}/cv` répond 404 "inconnue, appelle GET
    # /career d'abord" pour TOUTE offre affichée via le chat (bug réel :
    # le tableau d'offres de l'UI web vient d'ici, pas de GET /career) -
    # même cache process que cette route (`aelyn_api.deps._offers_cache`),
    # pour qu'une offre devienne générable par CV peu importe par où elle
    # a été vue.
    if result.result_type == "offers" and result.results:
        cache_offers(result.results)
    return ChatReplyOut(text=result.text, result_type=result.result_type, results=result.results)


def _sse(event: dict) -> str:
    """Une ligne `data: <json>` SSE, le format attendu par `EventSource`
    côté navigateur (et par n'importe quel lecteur SSE générique côté
    appelant non-navigateur) : un objet JSON par évènement plutôt que du
    texte brut, pour transporter `type` + la charge utile dans le même
    évènement, sans flux séparé à corréler."""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _stream_events(agent: ConversationalAgent, message: str):
    """Traduit `ConversationalAgent.handle_message_stream()` (générateur
    Python interne : `str` | `_Heartbeat` | `TurnResult`, cf. son
    docstring dans aelyn_conversation/agent.py) en évènements SSE :

    - `{"type": "token", "text": "..."}` : un fragment de texte à
      ajouter à l'affichage, dans l'ordre reçu.
    - `: keep-alive` (commentaire SSE, PAS un évènement `data:`) : ignoré
      par construction par `EventSource` (la spec SSE saute toute ligne
      commençant par `:`), garde juste la connexion visiblement active
      pendant un rechargement de modèle Ollama sans le moindre token.
    - `{"type": "done", "text": "...", "result_type": ..., "results": ...}` :
      TOUJOURS le DERNIER évènement du flux. `text` est le texte COMPLET
      (source de vérité, au cas où le client préfère l'utiliser plutôt
      que sa propre concaténation des `token`), `result_type`/`results`
      arrivent UNIQUEMENT ici (jamais au fil de l'eau : une liste
      d'offres/mails est déjà connue d'un coup à la fin du routage, cf.
      docstring de `handle_message_stream`).
    - `{"type": "error", "message": "..."}` : un tour en flux était déjà
      en cours sur cette instance (mono-utilisateur, cf.
      `aelyn_api.deps.get_conversational_agent`) ou une exception
      imprévue s'est échappée de l'agent. Dans les deux cas, DERNIER
      évènement du flux (rien ne suit) ; le statut HTTP reste 200 (déjà
      envoyé au tout premier octet du flux, cf. `StreamingResponse`),
      c'est cet évènement qui porte l'échec, pas le code HTTP.
    """
    try:
        for item in agent.handle_message_stream(message):
            if isinstance(item, TurnResult):
                if item.result_type == "offers" and item.results:
                    cache_offers(item.results)
                yield _sse(
                    {
                        "type": "done",
                        "text": item.text,
                        "result_type": item.result_type,
                        "results": item.results,
                    }
                )
            elif isinstance(item, _Heartbeat):
                yield ": keep-alive\n\n"
            else:
                yield _sse({"type": "token", "text": item})
    except RuntimeError as exc:
        # Flux déjà en cours sur cette instance (cf. `handle_message_stream`).
        yield _sse({"type": "error", "message": str(exc)})
    except Exception:
        logger.exception("Erreur pendant /chat/message/stream")
        yield _sse({"type": "error", "message": "Erreur interne pendant la génération."})


@router.post("/message/stream")
def send_message_stream(
    body: ChatMessageIn,
    agent: ConversationalAgent = Depends(get_conversational_agent),
) -> StreamingResponse:
    """Variante en flux de `POST /chat/message` (voir le docstring de ce
    module, et celui de `ConversationalAgent.handle_message_stream` pour
    le pourquoi). MÊME routage, MÊMES garde-fous (confirm=False), seule
    la présentation diffère : la réponse texte arrive fragment par
    fragment (Server-Sent Events) au lieu d'un seul bloc JSON attendu
    jusqu'au bout.

    Côté client : ouvrir un flux SSE sur cette route (`EventSource` ne
    supporte que GET nativement, donc `fetch()` + lecture manuelle du
    corps en flux, ou toute lib SSE acceptant POST), et traiter chaque
    `data: {...}` comme un évènement JSON `{"type": ...}` (cf.
    `_stream_events` ci-dessus pour les types possibles : `token`,
    `done`, `error`). Les lignes commençant par `:` (commentaires de
    battement) sont à ignorer, pas à parser comme JSON.

    409 immédiat (PAS de flux ouvert) si un autre tour en flux est déjà
    en cours sur cette même instance mono-utilisateur, pour donner un
    vrai code d'erreur HTTP tant que la réponse n'a pas encore commencé
    (après quoi le statut ne peut plus changer, cf. `_stream_events`,
    où ce même cas redevient un évènement `error` si la course a lieu
    entre cette vérification et le premier octet envoyé).
    """
    if agent._stream_sink is not None:
        raise HTTPException(
            status_code=409,
            detail="Un autre message est déjà en cours de traitement, réessaie dans un instant.",
        )

    return StreamingResponse(
        _stream_events(agent, body.message),
        media_type="text/event-stream",
        headers={
            # Désactive le buffering d'un éventuel reverse proxy (nginx) :
            # sans cet en-tête, un proxy peut accumuler la réponse entière
            # avant de la transmettre, annulant tout le bénéfice du flux.
            # Sans effet (donc sans risque) quand il n'y a pas de proxy,
            # comme en développement local.
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
        },
    )
