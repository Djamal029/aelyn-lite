"""Suivi des candidatures envoyées (cf. `aelyn_career.applications`).

Pas protégé par `require_settings_token` (contrairement à `PUT
/career/profile`) : marquer une candidature "en entretien" est une
action normale d'usage courant, pas une modification de configuration
ou de secret."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from aelyn.core.journal import Journal
from aelyn.core.llm import LLMError
from aelyn_career.application_replies import check_application_replies
from aelyn_career.application_writer import ApplicationWriter
from aelyn_career.applications import (
    Application,
    ApplicationsStore,
    ApplicationStatus,
    status_label,
)
from aelyn_email.client import MailboxError, list_recent_or_flagged

from aelyn_api.deps import get_application_writer, get_applications_store, get_journal

router = APIRouter(prefix="/applications", tags=["applications"])


class ApplicationOut(BaseModel):
    offer_id: str
    title: str
    company: str | None = None
    status: str
    status_label: str
    applied_at: str
    updated_at: str
    notes: str | None = None
    description: str | None = None
    questions: str | None = None


def _to_out(app: Application) -> ApplicationOut:
    return ApplicationOut(
        offer_id=app.offer_id,
        title=app.title,
        company=app.company,
        status=app.status.value,
        status_label=status_label(app.status),
        applied_at=app.applied_ts.isoformat(),
        updated_at=app.updated_ts.isoformat(),
        notes=app.notes,
        description=app.description,
        questions=app.questions,
    )


def _parse_status(raw: str) -> ApplicationStatus:
    try:
        return ApplicationStatus(raw)
    except ValueError as exc:
        valid = ", ".join(s.value for s in ApplicationStatus)
        raise HTTPException(
            422, f"Statut inconnu : {raw!r} (valides : {valid})."
        ) from exc


@router.get("", response_model=list[ApplicationOut])
def list_applications(
    status: str | None = None,
    store: ApplicationsStore = Depends(get_applications_store),
) -> list[ApplicationOut]:
    status_filter = _parse_status(status) if status else None
    return [_to_out(a) for a in store.list(status_filter)]


class ApplicationPatchIn(BaseModel):
    status: str | None = None
    note: str | None = None
    description: str | None = None


@router.patch("/{offer_id}", response_model=ApplicationOut)
def update_application(
    offer_id: str,
    body: ApplicationPatchIn,
    store: ApplicationsStore = Depends(get_applications_store),
) -> ApplicationOut:
    current = store.get(offer_id)
    if current is None:
        raise HTTPException(404, f"Candidature {offer_id} inconnue.")

    new_status = _parse_status(body.status) if body.status else current.status
    updated = store.update_status(offer_id, new_status, note=body.note)
    # `current` existait déjà au-dessus : `updated` ne peut être `None`
    # ici, mais le type reste `Application | None` côté store.
    assert updated is not None
    if body.description is not None:
        updated = store.set_description(offer_id, body.description) or updated
    return _to_out(updated)


class CheckRepliesOut(BaseModel):
    checked: int
    found: list[ApplicationOut]


@router.post("/check-replies", response_model=CheckRepliesOut)
def check_replies(
    days: int = 30,
    store: ApplicationsStore = Depends(get_applications_store),
    writer: ApplicationWriter = Depends(get_application_writer),
    journal: Journal = Depends(get_journal),
) -> CheckRepliesOut:
    """Relit les mails des `days` derniers jours (lus ou non, + ceux
    marqués importants, cf. `list_recent_or_flagged`) pour y chercher des
    réponses à des candidatures suivies, et met à jour leur statut/notes.
    Les mails déjà traités lors d'un appel précédent sont ignorés (cf.
    `check_application_replies`) : rappeler cette route (bouton
    "actualiser" côté interface) ne refacture jamais un mail déjà vu."""
    if not store.list():
        return CheckRepliesOut(checked=0, found=[])
    try:
        mails = list_recent_or_flagged(days=days)
    except MailboxError as exc:
        raise HTTPException(502, f"Messagerie injoignable : {exc}") from exc

    try:
        results = check_application_replies(store, writer.llm, mails, journal=journal)
    except LLMError as exc:
        raise HTTPException(502, f"Analyse des réponses impossible : {exc}") from exc

    return CheckRepliesOut(
        checked=len(mails),
        found=[_to_out(r.application) for r in results],
    )


class GenerateQuestionsIn(BaseModel):
    description: str | None = None


@router.post("/{offer_id}/questions", response_model=ApplicationOut)
def generate_questions(
    offer_id: str,
    body: GenerateQuestionsIn,
    store: ApplicationsStore = Depends(get_applications_store),
    writer: ApplicationWriter = Depends(get_application_writer),
) -> ApplicationOut:
    """Génère (ou régénère) les questions à poser au recruteur pour cette
    candidature. `body.description`, si fourni, remplace d'abord la
    description enregistrée (ex. l'utilisateur colle le texte de l'offre
    juste avant de générer) : sans ça, une candidature trackée sans
    description n'aurait jamais de contexte à donner au LLM."""
    current = store.get(offer_id)
    if current is None:
        raise HTTPException(404, f"Candidature {offer_id} inconnue.")

    if body.description is not None:
        current = store.set_description(offer_id, body.description) or current

    try:
        questions = writer.generate_interview_questions(
            title=current.title, company=current.company, description=current.description,
        )
    except LLMError as exc:
        raise HTTPException(502, f"Génération des questions impossible : {exc}") from exc

    updated = store.set_questions(offer_id, questions)
    assert updated is not None
    return _to_out(updated)


@router.delete("/{offer_id}", status_code=204)
def delete_application(
    offer_id: str,
    store: ApplicationsStore = Depends(get_applications_store),
) -> None:
    """Retire une candidature du suivi (ex. une candidature trackée par
    erreur, cf. `ApplicationsStore.delete`). Même raisonnement que PATCH
    ci-dessus pour l'absence de protection par passkey : retirer une
    ligne de suivi est un geste d'usage courant, pas une modification de
    configuration/secret."""
    if not store.delete(offer_id):
        raise HTTPException(404, f"Candidature {offer_id} inconnue.")
