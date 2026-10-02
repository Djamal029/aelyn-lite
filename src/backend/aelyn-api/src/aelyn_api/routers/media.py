"""Expose `MediaController` (TV Freebox Pop / Android TV) à l'API, plus
deux routes autonomes :

- `GET /media/youtube/search` : vraie recherche YouTube Data API v3
  (nécessite `YOUTUBE_API_KEY` dans .env, cf. core/config.py).
- `POST /media/netflix/play` : lance Netflix et tente une recherche du
  titre demandé, PAS une lecture précise garantie. Il n'existe AUCUNE
  API officielle Netflix pour résoudre un titre vers un identifiant de
  contenu précis, et ce problème exact a déjà été tenté trois fois plus
  tôt dans ce projet pour `search_netflix` (media-agent) : touche SEARCH
  interceptée par l'assistant vocal de la Freebox, deep link de
  recherche ignoré/peu fiable, navigation D-pad interceptée pour le
  volume. Aucun angle nouveau trouvé ici (pas d'accès ADB/shell sur ce
  montage, qui pilote la TV via le protocole Android TV Remote réseau,
  pas par un shell Android) : cette route réutilise donc EXACTEMENT
  `search_netflix` (déjà le plafond pratique accepté pour cette
  fonctionnalité) plutôt que de prétendre à une précision que la
  plateforme ne permet pas.

Mêmes actions que `Intent.media_action` côté chat (cf.
aelyn_conversation/models.py) pour les routes TV : `dispatch_action`/
`COMMANDS` sont la même fonction/table que `MediaController.dispatch`
utilise déjà, aucune logique dupliquée ici.
"""

from __future__ import annotations

import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from aelyn.core.config import settings
from aelyn_media.agent import COMMANDS, MediaController

from aelyn_api.deps import get_media_controller

router = APIRouter(prefix="/media", tags=["media"])

_SEARCH_ACTIONS = {"search_youtube", "search_netflix"}
_YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


class MediaActionIn(BaseModel):
    query: str | None = None
    amount: int | None = None


class YouTubeResultOut(BaseModel):
    video_id: str
    title: str
    channel: str
    thumbnail: str | None = None


class NetflixPlayIn(BaseModel):
    title: str


@router.get("/actions", response_model=list[str])
def list_actions() -> list[str]:
    """Actions valides pour `POST /media/{action}`, utile pour qu'un
    frontend construise ses boutons sans dupliquer cette liste."""
    return sorted(set(COMMANDS.values()) | _SEARCH_ACTIONS)


@router.post("/{action}")
def run_action(
    action: str,
    body: MediaActionIn | None = None,
    controller: MediaController = Depends(get_media_controller),
) -> dict:
    body = body or MediaActionIn()
    valid_actions = set(COMMANDS.values()) | _SEARCH_ACTIONS
    if action not in valid_actions:
        raise HTTPException(404, f"Action média inconnue : {action}")

    try:
        code = controller.dispatch(action, body.query, body.amount)
    except Exception as exc:
        # La TV peut être éteinte/injoignable à tout moment (veille,
        # coupure réseau), même principe que côté chat
        # (ConversationalAgent._run_command) : jamais une exception brute.
        raise HTTPException(502, f"TV injoignable : {exc}") from exc

    if code != 0:
        raise HTTPException(400, f"Action refusée par la TV : {action}")
    return {"status": "ok", "action": action}


@router.get("/youtube/search", response_model=list[YouTubeResultOut])
def youtube_search(q: str, max_results: int = 10) -> list[YouTubeResultOut]:
    """Vraie recherche YouTube (YouTube Data API v3), pas un scraping :
    nécessite `YOUTUBE_API_KEY` dans .env (cf. core/config.py). Le quota
    gratuit (10 000 unités/jour, une recherche = 100) suffit largement
    pour un usage personnel."""
    if not settings.youtube_api_key:
        raise HTTPException(
            503,
            "YOUTUBE_API_KEY n'est pas configuré côté serveur (.env), "
            "voir https://console.cloud.google.com/apis/credentials.",
        )

    try:
        response = requests.get(
            _YOUTUBE_SEARCH_URL,
            params={
                "part": "snippet",
                "q": q,
                "maxResults": max_results,
                "type": "video",
                "key": settings.youtube_api_key,
            },
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(502, f"YouTube injoignable : {exc}") from exc

    items = response.json().get("items", [])
    results: list[YouTubeResultOut] = []
    for item in items:
        video_id = item.get("id", {}).get("videoId")
        if not video_id:
            continue
        snippet = item.get("snippet", {})
        thumbnails = snippet.get("thumbnails", {})
        thumbnail = (
            thumbnails.get("medium", {}).get("url")
            or thumbnails.get("default", {}).get("url")
        )
        results.append(
            YouTubeResultOut(
                video_id=video_id,
                title=snippet.get("title", "?"),
                channel=snippet.get("channelTitle", "?"),
                thumbnail=thumbnail,
            )
        )
    return results


@router.post("/netflix/play")
def netflix_play(
    body: NetflixPlayIn,
    controller: MediaController = Depends(get_media_controller),
) -> dict:
    """Lance Netflix et tente une recherche du titre demandé sur la TV,
    PAS une lecture directe garantie d'un contenu précis (cf. docstring
    du module : aucune API officielle Netflix ne permet de résoudre un
    titre vers un identifiant de contenu, et cette limite a déjà été
    heurtée trois fois dans ce projet pour `search_netflix`). Réutilise
    donc EXACTEMENT ce même chemin plutôt que de réinventer une
    "solution" qui retomberait sur le même mur.
    """
    try:
        code = controller.dispatch("search_netflix", body.title, None)
    except Exception as exc:
        raise HTTPException(502, f"TV injoignable : {exc}") from exc

    if code != 0:
        raise HTTPException(400, "Impossible de lancer la recherche Netflix sur la TV.")

    return {
        "status": "ok",
        "title": body.title,
        "note": (
            "Netflix lancé avec une recherche best-effort pour ce titre, "
            "pas une lecture directe garantie : aucune API officielle "
            "Netflix ne permet de résoudre un titre vers un contenu précis."
        ),
    }
