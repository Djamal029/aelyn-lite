"""Suivi des candidatures envoyées (cf. `aelyn_career.applications`).

Pas protégé par `require_settings_token` (contrairement à `PUT
/career/profile`) : marquer une candidature "en entretien" est une
action normale d'usage courant, pas une modification de configuration
ou de secret."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from aelyn_career.applications import (
    Application,
    ApplicationsStore,
    ApplicationStatus,
    status_label,
)

from aelyn_api.deps import get_applications_store

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
    return _to_out(updated)
