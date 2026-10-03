"""Point d'entrée FastAPI d'AELYN : assemble un routeur par agent.

Lancement (depuis `src/backend`, workspace uv) :
    uv run uvicorn aelyn_api.main:app --reload --app-dir aelyn-api/src

ou, depuis `aelyn-api/src/aelyn_api/` directement :
    uvicorn main:app --reload

`/docs` donne la console interactive (Swagger UI) une fois lancé.

Objectif du produit (cf. README/consignes) : UNE seule surface pour
tous les agents (mail/carrière/média/sécurité), "un peu comme JARVIS",
pas un tas de micro-API disjointes. D'où un seul process FastAPI, un
routeur par domaine, tous montés ici.
"""

from __future__ import annotations

import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aelyn_api.routers import activity, career, chat, email, health, media, security, system, tts
from aelyn_api.routers import settings as settings_router

# Même correctif que `aelyn.cli.main()` : la console Windows encode en
# cp1252 par défaut. Ce process réutilise `ConversationalAgent` (via
# `handle_message()`), dont l'affichage CLI (Rich, `_print_agent_bubble`)
# écrit sur stdout en tant qu'effet de bord, même ici, où personne ne lit
# jamais ce terminal : un caractère hors cp1252 dans une réponse libre
# (observé en direct : une requête "quelle heure est-il" a planté tout le
# worker avec `UnicodeEncodeError`, sans jamais répondre au client HTTP,
# qui restait bloqué jusqu'au timeout) faisait planter tout le worker.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

app = FastAPI(
    title="AELYN API",
    description=(
        "Assistant personnel local AELYN : une seule surface pour mail, "
        "carrière, média (TV) et caméras locales."
    ),
    version="0.1.0",
)

# CORS ouvert en développement (frontend web sur un port différent du
# backend) ; à restreindre à l'origine réelle du frontend avant tout
# déploiement au-delà d'une machine de dev locale.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(activity.router)
app.include_router(system.router)
app.include_router(email.router)
app.include_router(career.router)
app.include_router(media.router)
app.include_router(security.router)
app.include_router(chat.router)
app.include_router(settings_router.router)
app.include_router(tts.router)
