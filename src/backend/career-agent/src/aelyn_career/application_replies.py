"""Détecte, parmi des mails récents, les réponses à des candidatures déjà
suivies (`ApplicationsStore`), et met à jour leur statut avec les détails
extraits (ex. date/heure d'entretien, contact recruteur).

Lecture seule côté boîte mail : ce module ne touche jamais un flag IMAP
(pas de `\\Seen`, pas d'archivage) - c'est un enrichissement du suivi des
candidatures, pas un agent mail de plus. Les mails à examiner viennent de
`aelyn_email.client.list_recent_or_flagged` (lus OU non lus, cf. son
docstring) plutôt que de `list_unread` : une réponse de recruteur déjà
consultée sur le téléphone, par exemple, doit quand même être détectée.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, Field

from aelyn.core.journal import ActionStatus, Journal
from aelyn.core.llm import LLMClient, LLMError
from aelyn_career.applications import Application, ApplicationsStore, ApplicationStatus
from aelyn_career.prompts import SYSTEM_APPLICATION_REPLY
from aelyn_email.models import Mail

logger = logging.getLogger(__name__)

AGENT_NAME = "career"


class ReplyOutcome(StrEnum):
    ENTRETIEN = "entretien"
    REFUS = "refus"
    ACCUSE_RECEPTION = "accuse_reception"
    RELANCE_DEMANDEE = "relance_demandee"
    AUTRE = "autre"
    NON_PERTINENT = "non_pertinent"


# Seules les issues sans ambiguïté font avancer le statut suivi : un
# "accusé de réception" ou une "relance demandée" ne doit pas écraser un
# statut déjà plus avancé (ex. déjà en "entretien"), donc ne déclenche
# aucune mise à jour automatique de `status` (seulement une note, cf.
# `check_application_replies`).
_OUTCOME_TO_STATUS: dict[ReplyOutcome, ApplicationStatus] = {
    ReplyOutcome.ENTRETIEN: ApplicationStatus.ENTRETIEN,
    ReplyOutcome.REFUS: ApplicationStatus.REFUSE,
}


class ReplyAnalysis(BaseModel):
    """Ce que le LLM doit produire pour UN mail candidat."""

    est_reponse_candidature: bool
    issue: ReplyOutcome
    resume: str = Field(max_length=300)
    details_entretien: str | None = None


@dataclass(slots=True, frozen=True)
class ApplicationReplyResult:
    mail: Mail
    application: Application
    analysis: ReplyAnalysis
    status_changed: bool


def match_application(
    store: ApplicationsStore, *, subject: str, sender: str, sender_email: str
) -> Application | None:
    """Associe un mail à une candidature suivie, par mots-clés (titre ou
    entreprise) dans l'objet ou le nom de l'expéditeur, puis en repli par
    le domaine de l'expéditeur contre le nom de l'entreprise suivie (ex.
    "laura.couepel@phosphea.com" -> "Phosphea") : utile quand ni l'objet
    ni le nom affiché ne mentionnent l'entreprise."""
    candidate = store.find_by_text(f"{subject} {sender}")
    if candidate is not None:
        return candidate
    domain = sender_email.rsplit("@", 1)[-1].split(".")[0] if "@" in sender_email else ""
    if len(domain) >= 3:
        return store.find_by_text(domain)
    return None


def analyze_reply(llm: LLMClient, mail: Mail) -> ReplyAnalysis | None:
    """`None` si le LLM est indisponible : une erreur de classification
    sur UN mail ne doit jamais interrompre l'examen des autres."""
    try:
        return llm.structured(
            schema=ReplyAnalysis,
            system=SYSTEM_APPLICATION_REPLY,
            user=mail.for_llm(max_chars=2500),
        )
    except LLMError:
        logger.exception("Analyse de réponse candidature impossible pour %s", mail.uid)
        return None


# Fenêtre large plutôt qu'un vrai "depuis toujours" : `Journal.since` ne
# prend qu'un nombre d'heures, pas de borne infinie. 5 ans couvre tout
# usage réel sans alourdir la requête.
_DEDUP_WINDOW_HOURS = 24 * 365 * 5


def _already_processed_uids(journal: Journal) -> set[str]:
    """UID des mails déjà passés par `check_application_replies` (qu'ils
    aient matché une candidature ou non n'a pas d'importance ici, cf.
    appelant) : sans ce filtre, rappeler la fonction (ex. bouton
    "actualiser" du suivi) réanalyserait et re-noterait les MÊMES mails
    à chaque fois, en plus de refaire un appel LLM inutile par mail déjà
    vu."""
    return {
        action.payload["mail_uid"]
        for action in journal.since(hours=_DEDUP_WINDOW_HOURS, agent=AGENT_NAME)
        if action.action == "reponse_candidature" and "mail_uid" in action.payload
    }


def check_application_replies(
    store: ApplicationsStore,
    llm: LLMClient,
    mails: list[Mail],
    *,
    journal: Journal | None = None,
) -> list[ApplicationReplyResult]:
    """Examine `mails`, ne garde que ceux qui matchent une candidature
    suivie, les fait classifier, et met à jour `store` + journalise
    chaque résultat retenu. Ne modifie jamais `mails` lui-même ni la
    boîte mail - purement un enrichissement du suivi.

    `journal`, s'il est fourni, sert aussi à ÉVITER de retraiter un mail
    déjà vu lors d'un appel précédent (cf. `_already_processed_uids`) :
    sans lui, chaque appel (ex. "actualiser" côté interface) repart de
    zéro sur TOUS les mails rendus par `list_recent_or_flagged`."""
    already_seen = _already_processed_uids(journal) if journal is not None else set()
    results: list[ApplicationReplyResult] = []

    for mail in mails:
        if mail.uid in already_seen:
            continue

        application = match_application(
            store, subject=mail.subject, sender=mail.sender, sender_email=mail.sender_email
        )
        if application is None:
            continue

        analysis = analyze_reply(llm, mail)
        if analysis is None:
            # Échec LLM (transitoire) : jamais marqué comme vu, pour
            # retenter au prochain appel plutôt que d'abandonner ce mail
            # silencieusement pour toujours.
            continue

        if not analysis.est_reponse_candidature:
            # Classé non pertinent : marqué comme vu quand même (sinon
            # un "actualiser" répété refacturerait le même appel LLM
            # indéfiniment sur ce mail), mais rien à rapporter.
            if journal is not None:
                journal.record(
                    agent=AGENT_NAME,
                    action="reponse_candidature",
                    target=application.company or application.title,
                    summary=f"{mail.subject} : non pertinent",
                    status=ActionStatus.EXECUTED,
                    payload={
                        "offer_id": application.offer_id,
                        "mail_uid": mail.uid,
                        "issue": analysis.issue.value,
                    },
                )
            continue

        new_status = _OUTCOME_TO_STATUS.get(analysis.issue)
        note_parts = [analysis.resume]
        if analysis.details_entretien:
            note_parts.append(f"Entretien : {analysis.details_entretien}")
        note_parts.append(f"(mail du {mail.sender}, objet « {mail.subject} »)")
        note = " ".join(note_parts)

        if new_status is not None:
            updated = store.update_status(application.offer_id, new_status, note=note)
            status_changed = updated is not None and updated.status != application.status
            application = updated or application
        else:
            # `accuse_reception`/`relance_demandee`/`autre` : statut
            # inchangé (jamais écrasé par une issue moins avancée qu'un
            # entretien déjà enregistré), mais la note reste utile.
            updated = store.update_status(application.offer_id, application.status, note=note)
            application = updated or application
            status_changed = False

        if journal is not None:
            journal.record(
                agent=AGENT_NAME,
                action="reponse_candidature",
                target=application.company or application.title,
                summary=f"{application.title} : {analysis.resume}",
                status=ActionStatus.EXECUTED,
                payload={
                    "offer_id": application.offer_id,
                    "mail_uid": mail.uid,
                    "issue": analysis.issue.value,
                    "nouveau_statut": application.status.value,
                },
            )

        results.append(
            ApplicationReplyResult(
                mail=mail,
                application=application,
                analysis=analysis,
                status_changed=status_changed,
            )
        )

    return results
