"""Historique réel de l'utilisation d'AELYN.

Les échanges viennent de ChatHistory et les propositions/actions persistées
viennent du Journal. Aucun événement d'exemple n'est inséré : une installation
neuve renvoie une liste vide et se remplit au fil des usages réels.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from aelyn.core.chat_history import ChatHistory
from aelyn.core.journal import ActionStatus, Journal
from aelyn_api.deps import get_chat_history, get_journal

router = APIRouter(prefix="/activity", tags=["activity"])

_STATUS_SUFFIX = {
    ActionStatus.EXECUTED: " (exécuté)",
    ActionStatus.REJECTED: " (rejeté)",
    ActionStatus.FAILED: " (échec)",
}
_EXCLUDED_ACTIONS = {"structure_offer"}


class ActivityEntryOut(BaseModel):
    id: str
    timestamp: str
    message: str
    source: str


@router.get("", response_model=list[ActivityEntryOut])
def get_activity(
    hours: int = 168,
    journal: Journal = Depends(get_journal),
    history: ChatHistory = Depends(get_chat_history),
) -> list[ActivityEntryOut]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, hours))
    entries = [
        ActivityEntryOut(
            id=f"chat-{message.id}",
            timestamp=message.ts.isoformat(),
            message=f"{('Vous' if message.role == 'user' else 'AELYN')} : {message.content}",
            source="text" if message.role == "user" else "system",
        )
        for message in history.recent(limit=500)
        if message.ts >= cutoff
    ]
    entries.extend(
        ActivityEntryOut(
            id=f"action-{action.id}",
            timestamp=action.ts.isoformat(),
            message=f"{action.action} proposé : {action.summary}{_STATUS_SUFFIX.get(action.status, '')}",
            source=action.agent if action.agent in {"email", "career", "media"} else "system",
        )
        for action in journal.since(hours=max(1, hours))
        if action.action not in _EXCLUDED_ACTIONS
    )
    entries.sort(key=lambda entry: entry.timestamp, reverse=True)
    return entries