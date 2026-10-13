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
    boîte mail - purement un enrichissement du suivi."""
    results: list[ApplicationReplyResult] = []

    for mail in mails:
        application = match_application(
            store, subject=mail.subject, sender=mail.sender, sender_email=mail.sender_email
        )
        if application is None:
            continue

        analysis = analyze_reply(llm, mail)
        if analysis is None or not analysis.est_reponse_candidature:
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
