"""Expose `EmailAgent`/`aelyn_email.client` à l'API.

Mêmes garde-fous que le CLI/chat : aucun mail n'est envoyé ni archivé
ici (pas de route d'exécution pour l'instant : `execute()`/`reject()`
touchent l'état réel de la boîte et méritent le même soin de conception
que la confirmation du chat avant d'être exposés en HTTP ; laissé pour
une prochaine itération plutôt que bâclé ici).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from aelyn.core.llm import LLMClient, LLMError
from aelyn_conversation.prompts import SYSTEM_SUMMARY
from aelyn_email import client
from aelyn_email.client import MailboxError

from aelyn_api.deps import get_llm

router = APIRouter(prefix="/email", tags=["email"])


class MailOut(BaseModel):
    uid: str
    sender: str
    sender_email: str
    subject: str
    date: str | None = None
    preview: str
    has_attachments: bool


class MailSummaryOut(BaseModel):
    uid: str
    subject: str
    summary: str


def _preview(body: str, max_chars: int = 160) -> str:
    lignes = [line.strip() for line in body.splitlines() if line.strip()]
    text = " ".join(lignes)
    return text[:max_chars] + ("…" if len(text) > max_chars else "")


@router.get("", response_model=list[MailOut])
def list_unread(limit: int | None = None) -> list[MailOut]:
    try:
        mails = client.list_unread(limit)
    except MailboxError as exc:
        raise HTTPException(502, f"Boîte mail injoignable : {exc}") from exc

    return [
        MailOut(
            uid=mail.uid,
            sender=mail.sender,
            sender_email=mail.sender_email,
            subject=mail.subject,
            date=mail.date.isoformat() if mail.date else None,
            preview=_preview(mail.body),
            has_attachments=mail.has_attachments,
        )
        for mail in mails
    ]


@router.get("/{uid}/summary", response_model=MailSummaryOut)
def summarize(uid: str, llm: LLMClient = Depends(get_llm)) -> MailSummaryOut:
    # Pas de "get mail by uid" côté aelyn_email.client (seul `list_unread`
    # existe, cf. son docstring) : on refetch les non-lus et on cherche
    # dedans, comme `ConversationalAgent._find_mail` le fait déjà côté chat.
    try:
        mails = client.list_unread()
    except MailboxError as exc:
        raise HTTPException(502, f"Boîte mail injoignable : {exc}") from exc

    mail = next((m for m in mails if m.uid == uid), None)
    if mail is None:
        raise HTTPException(404, f"Mail {uid} introuvable parmi les non-lus.")

    try:
        summary = llm.text(system=SYSTEM_SUMMARY, user=mail.for_llm())
    except LLMError as exc:
        raise HTTPException(502, f"LLM indisponible : {exc}") from exc

    return MailSummaryOut(uid=mail.uid, subject=mail.subject, summary=summary)
