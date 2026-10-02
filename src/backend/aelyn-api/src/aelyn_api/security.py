"""Passkey de réglages : protège toute route qui MODIFIE un réglage AELYN.

Flux en deux temps :

1. `POST /settings/auth {"passkey": "..."}` -> vérifie contre
   `settings.settings_passkey` (jamais renvoyé nulle part), émet un
   jeton aléatoire de courte durée de vie.
2. Toute route de modification exige ce jeton via
   `Authorization: Bearer <jeton>` (dépendance `require_settings_token`).

Le jeton est gardé EN MÉMOIRE (process unique, réseau local) : pas
besoin de JWT signé ni de stockage partagé pour un assistant personnel
mono-instance. Un redémarrage de l'API invalide tous les jetons émis,
ce qui est le comportement voulu : jamais un jeton qui survivrait à un
redémarrage sans repasser par le passkey.
"""

from __future__ import annotations

import secrets
import time

from fastapi import Header, HTTPException, status

from aelyn.core.config import settings

TOKEN_TTL_SECONDS = 15 * 60  # 15 minutes : assez pour une session de réglages
_tokens: dict[str, float] = {}  # token -> expiration (epoch seconds)


def verify_passkey(passkey: str) -> str:
    """Vérifie `passkey` contre `settings.settings_passkey` et émet un
    jeton temporaire en cas de succès.

    Lève `HTTPException` si le passkey n'est pas configuré côté serveur
    (refuse TOUTE modification plutôt que d'autoriser sans protection,
    jamais de "pas de code = ouvert à tous") ou si le passkey fourni est
    incorrect.
    """
    if not settings.settings_passkey:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "SETTINGS_PASSKEY n'est pas configuré côté serveur (.env), "
            "aucune modification des réglages n'est possible tant qu'il "
            "ne l'est pas.",
        )
    # `compare_digest` plutôt que `==` : évite une comparaison à temps
    # variable qui fuiterait la longueur/le préfixe du passkey correct.
    if not secrets.compare_digest(passkey, settings.settings_passkey):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Passkey incorrect.")

    token = secrets.token_urlsafe(32)
    _tokens[token] = time.time() + TOKEN_TTL_SECONDS
    return token


def _purge_expired() -> None:
    now = time.time()
    for token in [t for t, expiry in _tokens.items() if expiry < now]:
        del _tokens[token]


def require_settings_token(authorization: str | None = Header(default=None)) -> None:
    """Dépendance FastAPI à poser sur toute route qui modifie un réglage
    (ex. `dependencies=[Depends(require_settings_token)]`)."""
    _purge_expired()
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Jeton de réglages manquant, voir POST /settings/auth.",
        )
    token = authorization.split(" ", 1)[1].strip()
    if token not in _tokens:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Jeton de réglages invalide ou expiré, refais POST /settings/auth.",
        )
