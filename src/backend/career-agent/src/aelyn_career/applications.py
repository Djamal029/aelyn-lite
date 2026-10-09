"""Suivi des candidatures envoyées (career-agent).

Répond à "où en sont mes candidatures ?" : le Journal (`aelyn.core.journal`)
garde une trace BRUTE de l'ENVOI lui-même (action `apply_by_mail`,
chronologique, jamais modifiée après coup), mais aucune mémoire du SUIVI
qui vient ensuite - relance à faire, entretien obtenu, refus... - qui
change dans le temps et n'a de sens que pour UNE offre donnée (un statut
courant), pas comme une liste d'actions passées. Cette table comble ce
manque : une ligne par offre postulée, mise à jour en place.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path

from sqlalchemy import String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class ApplicationStatus(StrEnum):
    POSTULE = "postule"
    RELANCE = "relance"
    ENTRETIEN = "entretien"
    REFUSE = "refuse"
    ACCEPTE = "accepte"


# Libellés humains, jamais le nom technique de l'enum affiché tel quel
# (cf. bug réel déjà corrigé ailleurs sur les clés snake_case de
# profil.json affichées brutes sur un CV).
_STATUS_LABELS: dict[ApplicationStatus, str] = {
    ApplicationStatus.POSTULE: "postulé",
    ApplicationStatus.RELANCE: "relance à faire",
    ApplicationStatus.ENTRETIEN: "entretien",
    ApplicationStatus.REFUSE: "refusé",
    ApplicationStatus.ACCEPTE: "accepté",
}


def status_label(status: ApplicationStatus) -> str:
    return _STATUS_LABELS[status]


class Base(DeclarativeBase):
    pass


class ApplicationRow(Base):
    __tablename__ = "applications"

    offer_id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    company: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    applied_ts: Mapped[str] = mapped_column(String, nullable=False)
    updated_ts: Mapped[str] = mapped_column(String, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


@dataclass(slots=True, frozen=True)
class Application:
    offer_id: str
    title: str
    company: str | None
    status: ApplicationStatus
    applied_ts: datetime
    updated_ts: datetime
    notes: str | None

    def to_line(self) -> str:
        moment = self.applied_ts.astimezone().strftime("%d/%m")
        cible = f" chez {self.company}" if self.company else ""
        return f"{moment} | {status_label(self.status):<16} | {self.title}{cible}"


class ApplicationsStore:
    def __init__(self, path: Path) -> None:
        self._engine = create_engine(f"sqlite:///{path}")
        Base.metadata.create_all(self._engine)

    def record(
        self, *, offer_id: str, title: str, company: str | None = None
    ) -> Application:
        """Enregistre une candidature tout juste envoyée, statut POSTULE.
        Idempotent : si `offer_id` existe déjà (ex. "envoie par mail"
        rappelé sur la même offre), renvoie la ligne EXISTANTE sans
        écraser son statut déjà suivi (relance/entretien/refus...)."""
        with Session(self._engine) as session:
            existing = session.get(ApplicationRow, offer_id)
            if existing is not None:
                return _to_application(existing)
            now = datetime.now(timezone.utc).isoformat()
            row = ApplicationRow(
                offer_id=offer_id,
                title=title,
                company=company,
                status=ApplicationStatus.POSTULE.value,
                applied_ts=now,
                updated_ts=now,
                notes=None,
            )
            session.add(row)
            session.commit()
            return _to_application(row)

    def update_status(
        self, offer_id: str, status: ApplicationStatus, *, note: str | None = None
    ) -> Application | None:
        with Session(self._engine) as session:
            row = session.get(ApplicationRow, offer_id)
            if row is None:
                return None
            row.status = status.value
            row.updated_ts = datetime.now(timezone.utc).isoformat()
            if note:
                row.notes = f"{row.notes}\n{note}" if row.notes else note
            session.commit()
            return _to_application(row)

    def get(self, offer_id: str) -> Application | None:
        with Session(self._engine) as session:
            row = session.get(ApplicationRow, offer_id)
            return _to_application(row) if row else None

    def find_by_text(self, text: str) -> Application | None:
        """Retrouve UNE candidature par mot-clé (intitulé/entreprise),
        la plus récemment mise à jour en cas de plusieurs correspondances
        - même principe que `ConversationalAgent._find_offer`.

        Chaque mot significatif de `text` doit apparaître (comme simple
        sous-chaîne, pas forcément comme mot entier) dans le titre ou
        l'entreprise - pas `text` entier comme UNE SEULE sous-chaîne : un
        nom d'entreprise avec ponctuation (ex. "Collective.work") est
        découpé en plusieurs mots par l'appelant (`\\w+` ne matche pas
        "."), un match sur la phrase entière échouerait toujours sur un
        tel nom (bug réel observé : "chez Collective.work" ne retrouvait
        jamais l'entreprise "Collective.work")."""
        words = [w for w in re.findall(r"\w+", text.lower()) if len(w) >= 2]
        if not words:
            return None
        matches = [
            app
            for app in self.list()
            if all(word in f"{app.title} {app.company or ''}".lower() for word in words)
        ]
        return matches[0] if matches else None

    def list(self, status: ApplicationStatus | None = None) -> list[Application]:
        with Session(self._engine) as session:
            stmt = select(ApplicationRow)
            if status is not None:
                stmt = stmt.where(ApplicationRow.status == status.value)
            stmt = stmt.order_by(ApplicationRow.updated_ts.desc())
            rows = session.scalars(stmt).all()
            return [_to_application(r) for r in rows]


def _to_application(row: ApplicationRow) -> Application:
    return Application(
        offer_id=row.offer_id,
        title=row.title,
        company=row.company,
        status=ApplicationStatus(row.status),
        applied_ts=datetime.fromisoformat(row.applied_ts),
        updated_ts=datetime.fromisoformat(row.updated_ts),
        notes=row.notes,
    )
