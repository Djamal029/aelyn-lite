"""Expose `EmailAgent`/`aelyn_email.client` à l'API.

`POST /email/{action_id}/validate` et `.../reject` exécutent/rejettent une
proposition de triage DÉJÀ FAITE (cf. `aelyn_email.agent.EmailAgent.triage`,
qui enregistre chaque proposition dans le Journal avant tout). Pas de
passkey ici (contrairement à `PATCH /settings`/`PUT /career/profile`, qui
changent une CONFIGURATION) : cliquer "valider" sur une proposition déjà
affichée dans l'UI n'est pas d'une nature différente de ce que la CLI fait
déjà avec une simple confirmation y/n, pour un assistant mono-utilisateur
sur sa propre machine. Auparavant, SEULE la CLI interactive pouvait
exécuter une action : `POST /chat/message` (API HTTP sans terminal)
refuse délibérément valider/rejeter (cf. `ConversationalAgent.
handle_message`, `confirm=False`), donc dire "valide l'action 3" dans le
chat web n'avait jamais rien fait d'autre qu'expliquer pourquoi - aucun
moyen d'agir sur une proposition de triage depuis le frontend web.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from aelyn.core.llm import LLMClient, LLMError
from aelyn_conversation.prompts import SYSTEM_SUMMARY
from aelyn_email import client
from aelyn_email.agent import EmailAgent
from aelyn_email.client import MailboxError

from aelyn_api.deps import get_email_agent, get_llm

router = APIRouter(prefix="/email", tags=["email"])


class ActionResultOut(BaseModel):
    status: str


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


@router.post("/{action_id}/validate", response_model=ActionResultOut)
def validate_action(action_id: int, agent: EmailAgent = Depends(get_email_agent)) -> ActionResultOut:
    try:
        ok = agent.execute(action_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    # `execute()` renvoie `False` (pas une exception) pour "repondre"
    # quand `ALLOW_AUTONOMOUS_SEND=false" (cf. son docstring) : un vrai
    # résultat à distinguer de "introuvable/déjà traité", pas une erreur.
    return ActionResultOut(status="executed" if ok else "not_executed")


@router.post("/{action_id}/reject", response_model=ActionResultOut)
def reject_action(action_id: int, agent: EmailAgent = Depends(get_email_agent)) -> ActionResultOut:
    try:
        agent.reject(action_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return ActionResultOut(status="rejected")
